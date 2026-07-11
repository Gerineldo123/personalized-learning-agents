<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import type { AgentStep, ResultData } from '../../../types/agent'
import { ElMessage } from 'element-plus'
import api from '../../../api'
import { escapeHtml, renderMarkdownEnhanced, stripThinkingBlocks } from '../../../utils/markdown'

const props = defineProps<{ step: AgentStep }>()
const emit = defineEmits<{ (e: 'rerun'): void }>()
const expanded = ref(true)

const popoverVisible = ref(false)
const popoverTerm = ref('')
const popoverExplanation = ref('')
const popoverLoading = ref(false)
const popoverLeft = ref(0)
const popoverTop = ref(0)

function stripSuggestionLines(content: string) {
  return stripThinkingBlocks(String(content || ''))
    .replace(/^\s*(?:\[建议\]|【建议】).*(?:\r?\n|$)/gm, '')
    .trim()
}

const rawContent = computed(() => (props.step.data as ResultData).content || '')

const renderedHtml = computed(() => {
  const content = stripSuggestionLines(rawContent.value)
  if (!content) return ''

  try {
    const json = JSON.parse(content)
    if (json.agent === 'video' && Array.isArray(json.videos)) {
      const cards = json.videos.map((video: any) => `
        <div class="video-card">
          <div class="video-card-title">🎬 ${escapeHtml(video.title || '')}</div>
          <div class="video-card-meta">${escapeHtml(video.source || '')}${video.duration ? ' · ' + escapeHtml(video.duration) : ''}</div>
          <div class="video-card-reason">${escapeHtml(video.reason || '')}</div>
          ${video.url ? `<a class="video-card-link" href="${escapeHtml(video.url)}">观看</a>` : ''}
        </div>`).join('')
      const summary = json.search_summary ? `<div class="video-summary">${escapeHtml(json.search_summary)}</div>` : ''
      return `<div class="video-results"><div class="video-results-header">🎬 为你推荐的教学视频</div>${summary}${cards}</div>`
    }
  } catch {}

  return renderMarkdownEnhanced(content).replace(/\[\[(.+?)\]\]/g, (_m, term) => {
    const safe = escapeHtml(term)
    return `<span class="term-highlight" data-term="${safe}">${safe}</span>`
  })
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
  if (!target) return
  e.stopPropagation()
  const term = target.dataset.term || ''
  explainTerm(term, e.clientX, e.clientY)
}

async function explainTerm(term: string, x: number, y: number) {
  if (!term) return
  if (popoverVisible.value && popoverTerm.value === term) {
    popoverVisible.value = false
    return
  }
  popoverTerm.value = term
  popoverExplanation.value = ''
  popoverLeft.value = Math.min(x, window.innerWidth - 360)
  popoverTop.value = Math.min(y + 10, window.innerHeight - 240)
  popoverVisible.value = true
  popoverLoading.value = true
  try {
    const response = await api.post('/chat/explain-term', {
      term,
      user_id: inject<string>('userId', 'unknown'),
      context: rawContent.value.slice(0, 500),
    })
    popoverExplanation.value = response.data.explanation || '暂无解释'
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
      <div class="result-actions" v-if="step.status === 'completed'">
        <button class="action-btn" @click.stop="copyContent">📋 复制</button>
        <button class="action-btn" @click.stop="reExecute">🔄 重新执行</button>
      </div>
      <div class="markdown-body" @click="handleClick" v-html="renderedHtml" />
      <span v-if="step.status === 'running'" class="stream-cursor">▌</span>
    </div>

    <Teleport to="body">
      <div
        v-if="popoverVisible"
        class="term-popover"
        :style="{ left: popoverLeft + 'px', top: popoverTop + 'px' }"
      >
        <div class="popover-header">
          <span class="popover-term">{{ popoverTerm }}</span>
          <span class="popover-close" @click="popoverVisible = false">×</span>
        </div>
        <div class="popover-body">
          <div v-if="popoverLoading" class="popover-loading">加载中...</div>
          <div v-else class="markdown-body" v-html="renderMarkdownEnhanced(popoverExplanation)" />
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.step-card { background: #FFFBF5; border-radius: 12px; border: 1px solid #98C9B3; overflow: hidden; transition: all 0.25s cubic-bezier(.4,0,.2,1); }
.step-card:hover { box-shadow: 0 4px 16px rgba(58,51,46,0.10); transform: translateY(-1px); }
.step-header { display: flex; align-items: center; padding: 10px 14px; cursor: pointer; gap: 8px; user-select: none; background: #F0FAF5; transition: background 0.2s; }
.step-header:hover { background: rgba(152,201,179,0.18); }
.step-icon { font-size: 18px; flex-shrink: 0; }
.step-title { flex: 1; font-size: 14px; font-weight: 500; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #3A332E; }
.step-status { font-size: 12px; flex-shrink: 0; }
.step-status.done { color: #98C9B3; }
.step-status.running { color: #DBA878; }
.stream-cursor { display: inline-block; animation: blink 0.8s step-end infinite; color: #DBA878; font-weight: bold; margin-left: 2px; }
.step-arrow { font-size: 12px; color: #948A80; flex-shrink: 0; }
.step-content { min-width: 0; max-width: 100%; padding: 14px; border-top: 1px solid rgba(152,201,179,0.3); overflow: visible; }
.result-actions { display: flex; gap: 8px; margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid #EFE6DC; }
.action-btn { font-size: 12px; padding: 5px 12px; border: 1px solid #EFE6DC; border-radius: 6px; background: #FFFBF5; color: #6B635C; cursor: pointer; transition: all 0.2s; }
.action-btn:hover { border-color: #E8C29C; color: #3A332E; background: #FFF5EB; }
.markdown-body { min-width: 0; max-width: 100%; font-size: 14px; line-height: 1.75; color: #3A332E; overflow-wrap: anywhere; }
.markdown-body :deep(.markdown-table-wrap) { width: 100%; max-width: 100%; margin: 10px 0; overflow-x: auto; border: 1px solid #EFE6DC; border-radius: 8px; }
.markdown-body :deep(table) { min-width: 520px; border-collapse: collapse; width: 100%; margin: 0; }
.markdown-body :deep(th), .markdown-body :deep(td) { border: 1px solid #EFE6DC; padding: 7px 12px; text-align: left; font-size: 13px; }
.markdown-body :deep(th) { background: #FFF5EB; font-weight: 600; color: #3A332E; }
.markdown-body :deep(pre) { background: #1e1e2e; padding: 12px; border-radius: 8px; overflow-x: auto; }
.markdown-body :deep(pre code) { background: none; color: #cdd6f4; padding: 0; }
.markdown-body :deep(code) { background: #FFF5EB; padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono); font-size: 12px; }
.markdown-body :deep(blockquote) { border-left: 3px solid #F9D9B8; padding-left: 12px; color: #6B635C; margin: 8px 0; }
.markdown-body :deep(.term-highlight) { background: #FFF5EB; color: #DBA878; padding: 1px 6px; border-radius: 4px; cursor: pointer; font-weight: 500; border-bottom: 1px dashed #DBA878; transition: all 0.2s; }
.markdown-body :deep(.term-highlight:hover) { background: #F9D9B8; color: #3A332E; border-bottom-color: transparent; }
.video-results { display: grid; gap: 12px; }
.video-results-header { font-weight: 700; color: #3A332E; }
.video-summary { color: #6B635C; }
.video-card { border: 1px solid #EFE6DC; border-radius: 12px; padding: 12px; background: #FFFBF5; }
.video-card-title { font-weight: 700; color: #3A332E; }
.video-card-meta, .video-card-reason { color: #6B635C; font-size: 13px; margin-top: 4px; }
.video-card-link { display: inline-block; margin-top: 8px; color: #DBA878; text-decoration: none; font-weight: 700; }
@keyframes blink { 50% { opacity: 0; } }
</style>

<style>
.term-popover {
  position: fixed;
  z-index: 9999;
  min-width: 240px;
  max-width: 380px;
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(58,51,46,0.12);
}
.popover-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; border-bottom: 1px solid #EFE6DC; }
.popover-term { font-size: 14px; font-weight: 600; color: #DBA878; }
.popover-close { cursor: pointer; color: #948A80; font-size: 18px; padding: 2px; }
.popover-body { padding: 12px 14px; max-height: 260px; overflow-y: auto; }
.popover-loading { color: #948A80; font-style: italic; }
</style>
