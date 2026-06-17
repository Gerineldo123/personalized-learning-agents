<script setup lang="ts">
import { ref } from 'vue'
import type { AgentStep, ScrapeData } from '../../../types/agent'

const props = defineProps<{ step: AgentStep }>()

const expanded = ref(props.step.status === 'running')
const data = props.step.data as ScrapeData
const fullContent = ref(false)

function toggleExpand() {
  expanded.value = !expanded.value
}

const displayContent = ref(
  data.content ? data.content.slice(0, 300) : ''
)

function toggleFullContent() {
  fullContent.value = !fullContent.value
  if (fullContent.value) {
    displayContent.value = data.content
  } else {
    displayContent.value = data.content.slice(0, 300)
  }
}
</script>

<template>
  <div class="step-card" :class="{ expanded }">
    <div class="step-header" @click="toggleExpand">
      <span class="step-icon">🌐</span>
      <span class="step-title">{{ step.title }}</span>
      <span class="step-arrow">{{ expanded ? '▾' : '▸' }}</span>
    </div>
    <div v-show="expanded" class="step-content">
      <div class="scrape-url">
        <strong>目标 URL：</strong>
        <a :href="data.url" target="_blank" rel="noopener">{{ data.url }}</a>
      </div>
      <div v-if="data.content" class="scrape-preview">
        <div class="preview-label">提取内容：</div>
        <div class="preview-text">{{ displayContent }}</div>
        <button
          v-if="data.content.length > 300"
          class="toggle-btn"
          @click="toggleFullContent"
        >
          {{ fullContent ? '收起' : '展开更多...' }}
        </button>
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
.step-arrow { font-size: 12px; color: #948A80; flex-shrink: 0; }
.step-content { padding: 0 14px 14px; border-top: 1px solid #EFE6DC; }
.scrape-url { padding-top: 10px; font-size: 13px; color: #6B635C; }
.scrape-url a { color: #DBA878; text-decoration: none; word-break: break-all; transition: color 0.2s; }
.scrape-url a:hover { color: #E8C29C; text-decoration: underline; }
.scrape-preview { margin-top: 10px; }
.preview-label { font-size: 12px; color: #948A80; margin-bottom: 6px; }
.preview-text { font-size: 13px; line-height: 1.6; color: #6B635C; background: #FFF5EB; padding: 10px; border-radius: 8px; white-space: pre-wrap; word-break: break-word; max-height: 200px; overflow-y: auto; border: 1px solid #EFE6DC; }
.toggle-btn { margin-top: 6px; font-size: 12px; color: #DBA878; background: none; border: none; cursor: pointer; padding: 0; }
.toggle-btn:hover { text-decoration: underline; }
</style>
