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
      <span class="step-icon">✅</span>
      <span class="step-title">{{ step.title }}</span>
      <span class="step-status done">完成</span>
      <span class="step-arrow">{{ expanded ? '▾' : '▸' }}</span>
    </div>
    <div v-show="expanded" class="step-content">
      <!-- 操作按钮栏 -->
      <div class="result-actions" v-if="step.status === 'completed'">
        <button class="action-btn" @click.stop="copyContent" title="复制内容">📋 复制</button>
        <button class="action-btn" @click.stop="reExecute" title="重新执行任务">🔄 重新执行</button>
      </div>

      <div class="markdown-body" @click="handleClick" v-html="renderedHtml"></div>
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
  background: #fff;
  border-radius: 8px;
  border: 1px solid #67c23a;
  overflow: hidden;
  transition: box-shadow 0.2s;
}

.step-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.step-header {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  cursor: pointer;
  gap: 8px;
  user-select: none;
  background: #f0f9eb;
}

.step-header:hover {
  background: #e8f5e0;
}

.step-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.step-title {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-status {
  font-size: 12px;
  flex-shrink: 0;
}

.step-status.done {
  color: #67c23a;
}

.step-arrow {
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
}

.step-content {
  padding: 14px;
  border-top: 1px solid #e8f5e0;
}

.result-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f0f0f0;
}

.action-btn {
  font-size: 12px;
  padding: 4px 10px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #fff;
  color: #606266;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  border-color: #409eff;
  color: #409eff;
  background: #ecf5ff;
}

.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: #333;
}

.markdown-body :deep(h2) {
  font-size: 18px;
  margin: 14px 0 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #eee;
}

.markdown-body :deep(h3) {
  font-size: 15px;
  margin: 12px 0 6px;
}

.markdown-body :deep(p) {
  margin: 6px 0;
}

.markdown-body :deep(ul), .markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}

.markdown-body :deep(li) {
  margin: 3px 0;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 10px 0;
}

.markdown-body :deep(th), .markdown-body :deep(td) {
  border: 1px solid #e4e7ed;
  padding: 6px 12px;
  text-align: left;
  font-size: 13px;
}

.markdown-body :deep(th) {
  background: #f5f7fa;
  font-weight: 500;
}

.markdown-body :deep(code) {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Menlo', 'Consolas', monospace;
  font-size: 12px;
}

.markdown-body :deep(pre) {
  background: #1e1e2e;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
}

.markdown-body :deep(pre code) {
  background: none;
  color: #cdd6f4;
  padding: 0;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid #409eff;
  padding-left: 12px;
  color: #606266;
  margin: 8px 0;
}

/* 术语高亮标签 */
.markdown-body :deep(.term-highlight) {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  color: #1a73e8;
  padding: 1px 6px;
  border-radius: 3px;
  cursor: pointer;
  font-weight: 500;
  border-bottom: 1px dashed #1a73e8;
  transition: all 0.2s;
}

.markdown-body :deep(.term-highlight:hover) {
  background: #1a73e8;
  color: #fff;
  border-bottom-color: transparent;
}
</style>

<!-- 术语弹窗全局样式（非scoped） -->
<style>
.term-popover {
  position: fixed;
  z-index: 9999;
  min-width: 240px;
  max-width: 360px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.12);
  animation: popFadeIn 0.2s ease;
}

@keyframes popFadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.popover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid #f0f0f0;
}

.popover-term {
  font-size: 14px;
  font-weight: 600;
  color: #1a73e8;
}

.popover-close {
  cursor: pointer;
  color: #909399;
  font-size: 14px;
  padding: 2px;
}

.popover-close:hover {
  color: #f56c6c;
}

.popover-body {
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.7;
  color: #333;
  max-height: 200px;
  overflow-y: auto;
}

.popover-loading {
  color: #909399;
  font-style: italic;
}

/* 视频卡片 */
.markdown-body :deep(.video-results) { display: flex; flex-direction: column; gap: 10px; }
.markdown-body :deep(.video-results-header) { font-weight: 600; font-size: 15px; color: #303133; margin-bottom: 4px; }
.markdown-body :deep(.video-summary) { color: #606266; font-size: 13px; margin-bottom: 6px; }
.markdown-body :deep(.video-card) { border: 1px solid #e4e7ed; border-radius: 8px; padding: 12px 14px; background: #fafafa; display: flex; flex-direction: column; gap: 4px; }
.markdown-body :deep(.video-card-title) { font-weight: 600; font-size: 14px; color: #303133; }
.markdown-body :deep(.video-card-meta) { font-size: 12px; color: #909399; }
.markdown-body :deep(.video-card-reason) { font-size: 13px; color: #606266; }
.markdown-body :deep(.video-card-link) { align-self: flex-start; margin-top: 4px; padding: 3px 10px; background: #409eff; color: #fff; border-radius: 4px; font-size: 12px; text-decoration: none; }
.markdown-body :deep(.video-card-link:hover) { background: #337ecc; }
</style>
