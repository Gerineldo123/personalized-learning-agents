<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AgentStep, CodeData } from '../../../types/agent'
import AnimationViewer from '../../resource/AnimationViewer.vue'

const props = defineProps<{ step: AgentStep }>()

const expanded = ref(props.step.status === 'running')
const copied = ref(false)
const previewVisible = ref(false)
const data = computed(() => props.step.data as CodeData)
const isHtml = computed(() => ['html', 'htm'].includes((data.value.language || '').toLowerCase()))

const previewSrcdoc = computed(() => {
  const code = data.value.code || ''
  const fitCss = `
<style id="agent-code-preview-fit">
  html, body { width: 100% !important; min-width: 0 !important; margin: 0 !important; overflow-x: hidden !important; box-sizing: border-box !important; }
  body { min-height: 100vh !important; }
  .container, .wrapper, .app, .demo, main, #app { width: min(1180px, calc(100vw - 32px)) !important; max-width: min(1180px, calc(100vw - 32px)) !important; }
  canvas, svg { max-width: 100% !important; }
</style>`
  if (/<\/head>/i.test(code)) return code.replace(/<\/head>/i, `${fitCss}</head>`)
  if (code.includes('<body')) return code.replace(/<body([^>]*)>/i, `<body$1>${fitCss}`)
  return `${fitCss}${code}`
})

const langLabel = computed(() => {
  const map: Record<string, string> = {
    python: 'Python',
    javascript: 'JavaScript/Node.js',
    js: 'JavaScript/Node.js',
    html: 'HTML',
    cpp: 'C++',
    'c++': 'C++',
    c: 'C',
    java: 'Java',
  }
  return map[(data.value.language || '').toLowerCase()] || data.value.language
})

const statusText = computed(() => {
  if (data.value.status === 'running') return '运行中'
  if (data.value.status === 'error') return '错误'
  return '完成'
})

const statusIcon = computed(() => {
  if (data.value.status === 'running') return '⏳'
  if (data.value.status === 'error') return '❌'
  return '✅'
})

function toggleExpand() {
  expanded.value = !expanded.value
}

function copyCode() {
  navigator.clipboard.writeText(data.value.code || '').then(() => {
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  })
}

</script>

<template>
  <div class="step-card code-step" :class="{ expanded }">
    <div class="step-header" @click="toggleExpand">
      <span class="step-icon">💻</span>
      <span class="step-title">{{ step.title }}</span>
      <span class="lang-tag">{{ data.language }}</span>
      <span class="exec-status" :class="data.status">
        <span class="status-dot" :class="data.status" />
        {{ statusText }}
      </span>
      <span class="step-arrow">{{ expanded ? '▾' : '▸' }}</span>
    </div>

    <div v-show="expanded" class="step-content">
      <div class="code-toolbar">
        <span class="code-lang">{{ langLabel }}</span>
        <div class="toolbar-actions">
          <button v-if="isHtml" class="preview-btn" @click.stop="previewVisible = !previewVisible">
            {{ previewVisible ? '显示代码' : '运行预览' }}
          </button>
          <button class="copy-btn" @click.stop="copyCode">
            {{ copied ? '已复制' : '复制代码' }}
          </button>
        </div>
      </div>

      <div v-if="isHtml && previewVisible" class="preview-shell">
        <AnimationViewer
          :html="previewSrcdoc"
          title="HTML 动画预览"
          description="动画已按当前窗口自动适配。"
          compact
        />
      </div>

      <div v-else class="code-editor">
        <pre><code class="code-block">{{ data.code }}</code></pre>
      </div>

      <div v-if="data.output" class="output-section">
        <div class="output-header">
          <span class="output-label">控制台输出</span>
          <span class="output-status" :class="data.status">{{ statusIcon }} {{ statusText }}</span>
        </div>
        <pre class="output-content">{{ data.output }}</pre>
      </div>
    </div>

  </div>
</template>

<style scoped>
.step-card { background: #FFFBF5; border-radius: 14px; border: 1px solid #EFE6DC; overflow: hidden; transition: all 0.25s cubic-bezier(.4,0,.2,1); width: 100%; }
.step-card:hover { box-shadow: 0 2px 10px rgba(58,51,46,0.08); transform: translateY(-1px); }
.step-header { display: flex; align-items: center; padding: 10px 14px; cursor: pointer; gap: 8px; user-select: none; transition: background 0.2s; }
.step-header:hover { background: #FFF5EB; }
.step-icon { font-size: 18px; flex-shrink: 0; }
.step-title { flex: 1; font-size: 14px; font-weight: 500; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #3A332E; }
.lang-tag { font-size: 11px; background: #FFF5EB; color: #6B635C; padding: 2px 8px; border-radius: 6px; flex-shrink: 0; border: 1px solid #EFE6DC; }
.exec-status { font-size: 12px; display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.exec-status.running { color: #DBA878; }
.exec-status.completed { color: #98C9B3; }
.exec-status.error { color: #F2B8A2; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.status-dot.running { background: #DBA878; animation: pulse 1s ease-in-out infinite; }
.status-dot.completed { background: #98C9B3; }
.status-dot.error { background: #F2B8A2; }
.step-arrow { font-size: 12px; color: #948A80; flex-shrink: 0; }
.step-content { border-top: 1px solid #EFE6DC; }
.code-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 14px; background: #2d2d3f; }
.code-lang { font-size: 12px; color: #ccc; }
.toolbar-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
.copy-btn, .preview-btn { font-size: 12px; padding: 4px 12px; border: 1px solid #555; border-radius: 6px; background: #3d3d4f; color: #ddd; cursor: pointer; transition: all 0.2s; }
.preview-btn { border-color: #98C9B3; color: #98C9B3; }
.copy-btn:hover, .preview-btn:hover { border-color: #E8C29C; color: #E8C29C; }
.preview-shell { background: #FFF8F1; padding: 20px; border-top: 1px solid rgba(255,255,255,0.45); }
.code-editor { background: #1e1e2e; overflow-x: auto; }
.code-block { font-family: var(--font-mono); font-size: 13px; line-height: 1.6; padding: 14px; margin: 0; display: block; color: #cdd6f4; white-space: pre; tab-size: 2; }
.output-section { border-top: 1px solid #EFE6DC; }
.output-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 14px; background: #FFF5EB; }
.output-label { font-size: 12px; color: #6B635C; font-weight: 500; }
.output-content { margin: 0; padding: 12px 14px; background: #FFFBF5; color: #6B635C; white-space: pre-wrap; overflow-x: auto; }
@keyframes pulse { 50% { opacity: 0.4; } }
</style>
