<script setup lang="ts">
import { ref, computed, inject } from 'vue'
import type { AgentStep, ResultData } from '../../../types/agent'
import MarkdownIt from 'markdown-it'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import api from '../../../api'
import { ElMessage } from 'element-plus'

const md = new MarkdownIt({ html: false, breaks: true, linkify: true })

// 所有链接在新标签页打开
const defaultRender = md.renderer.rules.link_open || function (tokens: any, idx: any, options: any, _env: any, self: any) {
  return self.renderToken(tokens, idx, options)
}
md.renderer.rules.link_open = function (tokens: any, idx: any, options: any, env: any, self: any) {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  return defaultRender(tokens, idx, options, env, self)
}

const props = defineProps<{ step: AgentStep }>()
const emit = defineEmits<{ (e: 'rerun'): void }>()
const expanded = ref(true)

// 术语释义弹窗
const popoverVisible = ref(false)
const popoverTerm = ref('')
const popoverExplanation = ref('')
const popoverLoading = ref(false)
const popoverLeft = ref(0)
const popoverTop = ref(0)

function escapeHtml(str: string) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

const renderedHtml = computed(() => {
  const data = props.step.data as ResultData
  if (!data.content) return ''

  // 视频搜索结果渲染为卡片
  try {
    const json = JSON.parse(data.content)
    if (json.agent === 'video' && Array.isArray(json.videos)) {
      const cards = json.videos.map((v: any) => `
        <div class="video-card">
          <div class="video-card-title">📺 ${escapeHtml(v.title || '')}</div>
          <div class="video-card-meta">${escapeHtml(v.source || '')}${v.duration ? ' · ' + escapeHtml(v.duration) : ''}</div>
          <div class="video-card-reason">${escapeHtml(v.reason || '')}</div>
          ${v.url ? `<a class="video-card-link" href="${escapeHtml(v.url)}" target="_blank" rel="noopener">▶ 观看</a>` : ''}
        </div>`).join('')
      const summary = json.search_summary ? `<div class="video-summary">${escapeHtml(json.search_summary)}</div>` : ''
      return `<div class="video-results"><div class="video-results-header">🎬 为你推荐的教学视频</div>${summary}${cards}</div>`
    }
  } catch {}

  const mathBlocks: Array<{ formula: string; display: boolean }> = []
  let processed = data.content
    .replace(/\$\$([\s\S]*?)\$\$/g, (_m, f) => { mathBlocks.push({ formula: f.trim(), display: true }); return `\uFFF0MB${mathBlocks.length - 1}\uFFF1` })
    .replace(/\$([^$\n]+?)\$/g, (_m, f) => { mathBlocks.push({ formula: f.trim(), display: false }); return `\uFFF0MB${mathBlocks.length - 1}\uFFF1` })

  let html = md.render(processed)

  html = html.replace(/\uFFF0MB(\d+)\uFFF1/g, (_m, i) => {
    const { formula, display } = mathBlocks[+i]
    try {
      const rendered = katex.renderToString(formula, { displayMode: display, throwOnError: false })
      return display ? `<div class="math-block">${rendered}</div>` : `<span class="math-inline">${rendered}</span>`
    } catch { return display ? `<div class="math-block">${formula}</div>` : `<span class="math-inline">${formula}</span>` }
  })

  html = html.replace(/\[\[(.+?)\]\]/g, (_m, term) => {
    const safe = term.replace(/</g, '&lt;').replace(/>/g, '&gt;')
    return `<span class="term-highlight" data-term="${safe}">${safe}</span>`
  })

  // 渲染 [建议] 为可点击按钮
  html = html.replace(/\[建议\]\s*(.+?)(?=\n|$|<br|<\/p|<\/div|$)/g, (_m, text) => {
    const safe = text.trim().replace(/</g, '&lt;').replace(/>/g, '&gt;')
    return `<button class="suggestion-btn" data-suggestion="${safe}">${safe}</button>`
  })

  return html
})

const rawContent = computed(() => {
  const data = props.step.data as ResultData
  return data.content || ''
})

function toggleExpand() {
  expanded.value = !expanded.value
}

async function copyContent() {
  try {
    await navigator.clipboard.writeText(rawContent.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

function reExecute() {
  emit('rerun')
}

function handleClick(e: MouseEvent) {
  const target = (e.target as HTMLElement).closest('.term-highlight') as HTMLElement | null
  if (target) {
    e.stopPropagation()
    const term = target.dataset.term || ''
    explainTerm(term, e.clientX, e.clientY)
  } else if (!(e.target as HTMLElement).closest('.term-popover')) {
    popoverVisible.value = false
  }
}

async function explainTerm(term: string, x: number, y: number) {
  if (popoverVisible.value && popoverTerm.value === term) {
    popoverVisible.value = false
    return
  }
  popoverTerm.value = term
  popoverExplanation.value = ''
  popoverLeft.value = Math.min(x, window.innerWidth - 320)
  popoverTop.value = Math.min(y + 10, window.innerHeight - 200)
  popoverVisible.value = true
  popoverLoading.value = true

  try {
    const r = await api.post('/chat/explain-term', {
      term,
      user_id: inject<string>('userId', 'unknown'),
      context: rawContent.value.slice(0, 500),
    })
    popoverExplanation.value = r.data.explanation || '暂无解释'
  } catch {
    popoverExplanation.value = '获取解释失败'
  } finally {
    popoverLoading.value = false
  }
}
</script>

<template>
  <div class="step-card result-step" :class="{ expanded }">
    <div class="step-header" @click="toggleExpand">
      <span class="step-icon">{{ step.status === 'running' ? '⏳' : '✅' }}</span>
      <span class="step-title">{{ step.title }}</span>
      <span class="step-status" :class="step.status === 'running' ? 'running' : 'done'">
        {{ step.status === 'running' ? '生成中...' : '完成' }}
      </span>
      <span class="step-arrow">{{ expanded ? '▾' : '▸' }}</span>
    </div>
    <div v-show="expanded" class="step-content">
      <!-- 操作按钮栏 -->
      <div class="result-actions" v-if="step.status === 'completed'">
        <button class="action-btn" @click.stop="copyContent" title="复制内容">📋 复制</button>
        <button class="action-btn" @click.stop="reExecute" title="重新执行任务">🔄 重新执行</button>
      </div>

      <div class="markdown-body" @click="handleClick" v-html="renderedHtml"></div>
      <span v-if="step.status === 'running'" class="stream-cursor">▌</span>
    </div>

    <!-- 术语释义弹窗 -->
    <Teleport to="body">
      <div
        v-if="popoverVisible"
        class="term-popover"
        :style="{ left: popoverLeft + 'px', top: popoverTop + 'px' }"
      >
        <div class="popover-header">
          <span class="popover-term">{{ popoverTerm }}</span>
          <span class="popover-close" @click="popoverVisible = false">✕</span>
        </div>
        <div class="popover-body">
          <div v-if="popoverLoading" class="popover-loading">加载中...</div>
          <div v-else class="popover-text">{{ popoverExplanation }}</div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.step-card {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-success);
  overflow: hidden;
  transition: all var(--transition-fast);
}
.step-card:hover { box-shadow: var(--shadow-sm); }
.step-header { display: flex; align-items: center; padding: 10px 14px; cursor: pointer; gap: 8px; user-select: none; background: var(--color-success-bg); transition: background var(--transition-fast); }
.step-header:hover { background: rgba(82,196,26,0.14); }
.step-icon { font-size: 18px; flex-shrink: 0; }
.step-title { flex: 1; font-size: 14px; font-weight: 500; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.step-status { font-size: 12px; flex-shrink: 0; }
.step-status.done { color: var(--color-success); }
.step-status.running { color: var(--color-primary); }
.stream-cursor { display: inline-block; animation: blink 0.8s step-end infinite; color: var(--color-primary); font-weight: bold; margin-left: 2px; }
@keyframes blink { 50% { opacity: 0; } }
.step-arrow { font-size: 12px; color: var(--text-secondary); flex-shrink: 0; }
.step-content { padding: 14px; border-top: 1px solid rgba(82,196,26,0.2); }
.result-actions { display: flex; gap: 8px; margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid var(--border-light); }
.action-btn { font-size: 12px; padding: 5px 12px; border: 1px solid var(--border-base); border-radius: var(--radius-sm); background: var(--bg-card); color: var(--text-regular); cursor: pointer; transition: all var(--transition-fast); }
.action-btn:hover { border-color: var(--color-primary); color: var(--color-primary); background: var(--color-primary-bg); }
.markdown-body { font-size: 14px; line-height: 1.7; color: var(--text-regular); }
.markdown-body :deep(h2) { font-size: 18px; margin: 14px 0 8px; padding-bottom: 6px; border-bottom: 1px solid var(--border-light); }
.markdown-body :deep(h3) { font-size: 15px; margin: 12px 0 6px; }
.markdown-body :deep(p) { margin: 6px 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 20px; margin: 6px 0; }
.markdown-body :deep(li) { margin: 3px 0; }
.markdown-body :deep(table) { border-collapse: collapse; width: 100%; margin: 10px 0; }
.markdown-body :deep(th), .markdown-body :deep(td) { border: 1px solid var(--border-light); padding: 6px 12px; text-align: left; font-size: 13px; }
.markdown-body :deep(th) { background: var(--bg-overlay); font-weight: 500; }
.markdown-body :deep(code) { background: var(--bg-overlay); padding: 2px 6px; border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: 12px; }
.markdown-body :deep(pre) { background: #1e1e2e; padding: 12px; border-radius: var(--radius-sm); overflow-x: auto; }
.markdown-body :deep(pre code) { background: none; color: #cdd6f4; padding: 0; }
.markdown-body :deep(blockquote) { border-left: 3px solid var(--color-primary); padding-left: 12px; color: var(--text-regular); margin: 8px 0; }
.markdown-body :deep(.term-highlight) { background: linear-gradient(135deg, var(--color-primary-bg), rgba(167,139,250,0.1)); color: var(--color-primary); padding: 1px 6px; border-radius: var(--radius-sm); cursor: pointer; font-weight: 500; border-bottom: 1px dashed var(--color-primary); transition: all var(--transition-fast); }
.markdown-body :deep(.term-highlight:hover) { background: var(--color-primary); color: #fff; border-bottom-color: transparent; }
</style>

<style>
.term-popover {
  position: fixed;
  z-index: 9999;
  min-width: 240px;
  max-width: 360px;
  background: var(--bg-elevated, #fff);
  border: 1px solid var(--border-light, #e4e7ed);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  animation: popFadeIn 0.2s ease;
}
@keyframes popFadeIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
.popover-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; border-bottom: 1px solid var(--border-light, #f0f0f0); }
.popover-term { font-size: 14px; font-weight: 600; color: var(--color-primary); }
.popover-close { cursor: pointer; color: var(--text-secondary, #909399); font-size: 14px; padding: 2px; }
.popover-close:hover { color: var(--color-danger); }
.popover-body { padding: 12px 14px; font-size: 13px; line-height: 1.7; color: var(--text-regular, #333); max-height: 200px; overflow-y: auto; }
.popover-loading { color: var(--text-secondary, #909399); font-style: italic; }

.markdown-body :deep(.video-results) { display: flex; flex-direction: column; gap: 14px; }
.markdown-body :deep(.video-results-header) { font-weight: 600; font-size: 15px; color: var(--text-primary); margin-bottom: 4px; }
.markdown-body :deep(.video-summary) { color: var(--text-regular); font-size: 13px; margin-bottom: 6px; }

.markdown-body :deep(.video-card) {
  display: block;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  overflow: hidden;
  text-decoration: none;
  color: inherit;
  transition: all 0.25s ease;
  box-shadow: var(--shadow-xs);
}
.markdown-body :deep(.video-card:hover) { transform: translateY(-3px); box-shadow: var(--shadow-lg); border-color: var(--color-primary); }

.markdown-body :deep(.video-cover) { position: relative; width: 100%; padding-top: 56.25%; background: var(--bg-overlay); overflow: hidden; }
.markdown-body :deep(.video-cover img) { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; }
.markdown-body :deep(.video-cover span) {
  position: absolute; top: 0; left: 0; width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #F9D9B8 0%, #E8C29C 100%); font-size: 36px;
}
.markdown-body :deep(.video-duration) {
  position: absolute; bottom: 6px; right: 6px;
  background: rgba(0,0,0,0.78); color: #fff;
  font-size: 11px; padding: 2px 6px; border-radius: var(--radius-sm);
  font-family: var(--font-mono);
}

.markdown-body :deep(.video-info) { padding: 10px 12px 12px; }
.markdown-body :deep(.video-title) { font-size: 13px; font-weight: 500; line-height: 1.4; color: var(--text-primary); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis; margin-bottom: 8px; }
.markdown-body :deep(.video-card:hover .video-title) { color: var(--color-primary); }
.markdown-body :deep(.video-meta) { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--text-secondary); }
.markdown-body :deep(.meta-author) { color: var(--text-regular); font-weight: 500; }
.markdown-body :deep(.meta-play) { color: var(--text-secondary); }
</style>
