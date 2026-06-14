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
.step-card {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
  overflow: hidden;
  transition: all var(--transition-fast);
}
.step-card:hover { box-shadow: var(--shadow-sm); }
.step-header { display: flex; align-items: center; padding: 10px 14px; cursor: pointer; gap: 8px; user-select: none; transition: background var(--transition-fast); }
.step-header:hover { background: var(--bg-card-hover); }
.step-icon { font-size: 18px; flex-shrink: 0; }
.step-title { flex: 1; font-size: 14px; font-weight: 500; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.step-arrow { font-size: 12px; color: var(--text-secondary); flex-shrink: 0; }
.step-content { padding: 0 14px 14px; border-top: 1px solid var(--border-light); }
.scrape-url { padding-top: 10px; font-size: 13px; }
.scrape-url a { color: var(--color-primary); text-decoration: none; word-break: break-all; }
.scrape-url a:hover { text-decoration: underline; }
.scrape-preview { margin-top: 10px; }
.preview-label { font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }
.preview-text { font-size: 13px; line-height: 1.6; color: var(--text-regular); background: var(--bg-overlay); padding: 10px; border-radius: var(--radius-sm); white-space: pre-wrap; word-break: break-word; max-height: 200px; overflow-y: auto; }
.toggle-btn { margin-top: 6px; font-size: 12px; color: var(--color-primary); background: none; border: none; cursor: pointer; padding: 0; }
.toggle-btn:hover { text-decoration: underline; }
</style>
