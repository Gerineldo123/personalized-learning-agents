<script setup lang="ts">
import { ref, computed } from 'vue'
import type { AgentStep, CodeData } from '../../../types/agent'

const props = defineProps<{ step: AgentStep }>()

const expanded = ref(props.step.status === 'running')
const copied = ref(false)
const previewVisible = ref(false)
const data = computed(() => props.step.data as CodeData)
const isHtml = computed(() => ['html', 'htm'].includes((data.value.language || '').toLowerCase()))
const iframeHeight = ref(500)

function onIframeLoad(e: Event) {
  const iframe = e.target as HTMLIFrameElement
  try {
    const h = iframe.contentDocument?.documentElement?.scrollHeight
    if (h && h > 100) iframeHeight.value = h
  } catch {}
}

function toggleExpand() {
  expanded.value = !expanded.value
}

function copyCode() {
  navigator.clipboard.writeText(data.value.code).then(() => {
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  })
}

const langLabel = computed(() => {
  const map: Record<string, string> = {
    python: 'Python',
    javascript: 'JavaScript/Node.js',
    js: 'JavaScript/Node.js',
    cpp: 'C++',
    'c++': 'C++',
    c: 'C',
    java: 'Java',
  }
  return map[data.value.language] || data.value.language
})

const statusText = computed(() => {
  if (data.value.status === 'running') return 'Running'
  if (data.value.status === 'error') return 'Error'
  return 'Completed'
})

const statusIcon = computed(() => {
  if (data.value.status === 'running') return '⟳'
  if (data.value.status === 'error') return '✗'
  return '✓'
})
</script>

<template>
  <div class="step-card code-step" :class="{ expanded }">
    <div class="step-header" @click="toggleExpand">
      <span class="step-icon">💻</span>
      <span class="step-title">{{ step.title }}</span>
      <span class="lang-tag">{{ data.language }}</span>
      <span class="exec-status" :class="data.status">
        <span class="status-dot" :class="data.status"></span>
        {{ statusText }}
      </span>
      <span class="step-arrow">{{ expanded ? '▾' : '▸' }}</span>
    </div>
    <div v-show="expanded" class="step-content">
      <div class="code-toolbar">
        <span class="code-lang">{{ langLabel }}</span>
        <button v-if="isHtml" class="preview-btn" @click.stop="previewVisible = !previewVisible">
          {{ previewVisible ? '📄 显示代码' : '▶ 运行预览' }}
        </button>
        <button class="copy-btn" @click.stop="copyCode">
          {{ copied ? '已复制' : '复制代码' }}
        </button>
      </div>
      <iframe
        v-if="isHtml && previewVisible"
        :srcdoc="data.code"
        sandbox="allow-scripts"
        class="html-preview"
        :style="{ height: iframeHeight + 'px' }"
        @load="onIframeLoad"
      />
      <div v-else class="code-editor">
        <pre><code class="code-block">{{ data.code }}</code></pre>
      </div>
      <div v-if="data.output" class="output-section">
        <div class="output-header">
          <span class="output-label">Console Output</span>
          <span class="output-status" :class="data.status">{{ statusIcon }} {{ statusText }}</span>
        </div>
        <pre class="output-content">{{ data.output }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.step-card { background: #FFFBF5; border-radius: 12px; border: 1px solid #EFE6DC; overflow: hidden; transition: all 0.25s cubic-bezier(.4,0,.2,1); }
.step-card:hover { box-shadow: 0 2px 10px rgba(58,51,46,0.08); transform: translateY(-1px); }
.step-header { display: flex; align-items: center; padding: 10px 14px; cursor: pointer; gap: 8px; user-select: none; transition: background 0.2s; }
.step-header:hover { background: #FFF5EB; }
.step-icon { font-size: 18px; flex-shrink: 0; }
.step-title { flex: 1; font-size: 14px; font-weight: 500; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #3A332E; }
.lang-tag { font-size: 11px; background: #FFF5EB; color: #6B635C; padding: 2px 8px; border-radius: 6px; flex-shrink: 0; border: 1px solid #EFE6DC; }
.exec-status { font-size: 12px; display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.exec-status.running { color: #FBCFA8; }
.exec-status.completed { color: #98C9B3; }
.exec-status.error { color: #F2B8A2; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.status-dot.running { background: #FBCFA8; animation: pulse 1s ease-in-out infinite; }
.status-dot.completed { background: #98C9B3; }
.status-dot.error { background: #F2B8A2; }
.step-arrow { font-size: 12px; color: #948A80; flex-shrink: 0; }
.step-content { border-top: 1px solid #EFE6DC; }
.code-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 8px 14px; background: #2d2d3f; }
.code-lang { font-size: 12px; color: #888; }
.copy-btn { font-size: 12px; padding: 4px 12px; border: 1px solid #555; border-radius: var(--radius-sm); background: #3d3d4f; color: #ccc; cursor: pointer; transition: all var(--transition-fast); }
.copy-btn:hover { border-color: var(--color-primary); color: var(--color-primary); }
.preview-btn { font-size: 12px; padding: 4px 12px; border: 1px solid var(--color-success); border-radius: var(--radius-sm); background: #3d3d4f; color: var(--color-success); cursor: pointer; transition: all var(--transition-fast); margin-right: 6px; }
.preview-btn:hover { background: var(--color-success); color: #fff; }
.html-preview { width: 100%; min-height: 500px; border: none; background: #fff; display: block; transition: height 0.2s; }
.code-editor { background: #1e1e2e; overflow-x: auto; }
.code-block { font-family: var(--font-mono); font-size: 13px; line-height: 1.6; padding: 14px; margin: 0; display: block; color: #cdd6f4; white-space: pre; tab-size: 2; }
.copy-btn:hover { border-color: #E8C29C; color: #E8C29C; }
.preview-btn:hover { background: #98C9B3; border-color: #98C9B3; color: #fff; }
.output-section { border-top: 1px solid #EFE6DC; }
.output-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 14px; background: #FFF5EB; }
.output-label { font-size: 12px; color: #6B635C; font-weight: 500; }
.output-status { font-size: 12px; }
.output-status.running { color: #FBCFA8; }
.output-status.completed { color: #98C9B3; }
.output-status.error { color: #F2B8A2; }
.output-content { margin: 0; padding: 10px 14px; font-family: var(--font-mono); font-size: 12px; line-height: 1.5; background: #FFF5EB; white-space: pre-wrap; word-break: break-word; max-height: 200px; overflow-y: auto; color: #6B635C; border: none; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
</style>
