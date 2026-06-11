<script setup lang="ts">
import { ref } from 'vue'
import type { AgentStep, MemoryData } from '../../../types/agent'

const props = defineProps<{ step: AgentStep }>()

const expanded = ref(props.step.status === 'running')
const data = props.step.data as MemoryData

function toggleExpand() {
  expanded.value = !expanded.value
}
</script>

<template>
  <div class="step-card" :class="{ expanded }">
    <div class="step-header" @click="toggleExpand">
      <span class="step-icon">📝</span>
      <span class="step-title">{{ step.title }}</span>
      <span class="memory-tag" :class="data.action">
        {{ data.action === 'write' ? 'WRITE' : 'READ' }}
      </span>
      <span class="step-arrow">{{ expanded ? '▾' : '▸' }}</span>
    </div>
    <div v-show="expanded" class="step-content">
      <div class="memory-item">
        <div class="memory-row">
          <span class="memory-label">操作：</span>
          <span class="memory-value" :class="data.action">{{ data.action === 'write' ? '写入' : '读取' }}</span>
        </div>
        <div class="memory-row">
          <span class="memory-label">Key：</span>
          <code class="memory-key">{{ data.key }}</code>
        </div>
        <div class="memory-row" v-if="data.value">
          <span class="memory-label">Value：</span>
          <span class="memory-value-text">{{ data.value }}</span>
        </div>
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

.memory-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  flex-shrink: 0;
  font-weight: 600;
}

.memory-tag.write {
  background: #f0f9eb;
  color: #67c23a;
}

.memory-tag.read {
  background: #ecf5ff;
  color: #409eff;
}

.step-arrow {
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
}

.step-content {
  padding: 0 14px 14px;
  border-top: 1px solid #f0f0f0;
}

.memory-item {
  padding-top: 12px;
}

.memory-row {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
  font-size: 13px;
}

.memory-label {
  color: #909399;
  min-width: 50px;
  flex-shrink: 0;
}

.memory-value {
  font-weight: 500;
}

.memory-value.write {
  color: #67c23a;
}

.memory-value.read {
  color: #409eff;
}

.memory-key {
  background: #f5f7fa;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: 'Menlo', 'Consolas', monospace;
  font-size: 12px;
  color: #e6a23c;
}

.memory-value-text {
  color: #606266;
  word-break: break-all;
}
</style>
