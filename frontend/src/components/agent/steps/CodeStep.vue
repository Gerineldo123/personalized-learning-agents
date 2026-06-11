<script setup lang="ts">
import { ref, computed } from 'vue'
import type { AgentStep, CodeData } from '../../../types/agent'

const props = defineProps<{ step: AgentStep }>()

const expanded = ref(props.step.status === 'running')
const copied = ref(false)
const data = props.step.data as CodeData

function toggleExpand() {
  expanded.value = !expanded.value
}

function copyCode() {
  navigator.clipboard.writeText(data.code).then(() => {
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  })
}

const statusText = computed(() => {
  if (data.status === 'running') return 'Running'
  if (data.status === 'error') return 'Error'
  return 'Completed'
})

const statusIcon = computed(() => {
  if (data.status === 'running') return '⟳'
  if (data.status === 'error') return '✗'
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
        <span class="code-lang">{{ data.language === 'javascript' ? 'JavaScript/Node.js' : 'Python' }}</span>
        <button class="copy-btn" @click.stop="copyCode">
          {{ copied ? '已复制' : '复制代码' }}
        </button>
      </div>
      <div class="code-editor">
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
.step-card {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
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
}

.step-header:hover {
  background: #fafafa;
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

.lang-tag {
  font-size: 11px;
  background: #ecf5ff;
  color: #409eff;
  padding: 2px 8px;
  border-radius: 4px;
  flex-shrink: 0;
}

.exec-status {
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.exec-status.running { color: #e6a23c; }
.exec-status.completed { color: #67c23a; }
.exec-status.error { color: #f56c6c; }

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}

.status-dot.running {
  background: #e6a23c;
  animation: pulse 1s ease-in-out infinite;
}

.status-dot.completed { background: #67c23a; }
.status-dot.error { background: #f56c6c; }

.step-arrow {
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
}

.step-content { border-top: 1px solid #f0f0f0; }

.code-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: #2d2d3f;
}

.code-lang {
  font-size: 12px;
  color: #888;
}

.copy-btn {
  font-size: 12px;
  padding: 4px 12px;
  border: 1px solid #555;
  border-radius: 4px;
  background: #3d3d4f;
  color: #ccc;
  cursor: pointer;
  transition: all 0.2s;
}

.copy-btn:hover {
  border-color: #409eff;
  color: #409eff;
}

.code-editor {
  background: #1e1e2e;
  overflow-x: auto;
}

.code-block {
  font-family: 'Menlo', 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  padding: 14px;
  margin: 0;
  display: block;
  color: #cdd6f4;
  white-space: pre;
  tab-size: 2;
}

.output-section { border-top: 1px solid #e4e7ed; }

.output-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: #fafafa;
}

.output-label {
  font-size: 12px;
  color: #606266;
  font-weight: 500;
}

.output-status { font-size: 12px; }
.output-status.running { color: #e6a23c; }
.output-status.completed { color: #67c23a; }
.output-status.error { color: #f56c6c; }

.output-content {
  margin: 0;
  padding: 10px 14px;
  font-family: 'Menlo', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.5;
  background: #fafafa;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
  color: #333;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
