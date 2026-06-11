<script setup lang="ts">
import { ref, computed } from 'vue'
import type { AgentStep, ResultData } from '../../../types/agent'
import MarkdownIt from 'markdown-it'
import katex from 'katex'
import 'katex/dist/katex.min.css'

const md = new MarkdownIt({ html: false, breaks: true, linkify: true })

const props = defineProps<{ step: AgentStep }>()
const expanded = ref(true)
const data = props.step.data as ResultData

const renderedHtml = computed(() => {
  if (!data.content) return ''
  return md.render(data.content)
})

function toggleExpand() {
  expanded.value = !expanded.value
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
      <div class="markdown-body" v-html="renderedHtml"></div>
    </div>
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
</style>
