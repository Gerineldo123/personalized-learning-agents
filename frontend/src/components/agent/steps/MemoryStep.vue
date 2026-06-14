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
.memory-tag { font-size: 11px; padding: 2px 8px; border-radius: var(--radius-sm); flex-shrink: 0; font-weight: 600; }
.memory-tag.write { background: var(--color-success-bg); color: var(--color-success); }
.memory-tag.read { background: var(--color-primary-bg); color: var(--color-primary); }
.step-arrow { font-size: 12px; color: var(--text-secondary); flex-shrink: 0; }
.step-content { padding: 0 14px 14px; border-top: 1px solid var(--border-light); }
.memory-item { padding-top: 12px; }
.memory-row { display: flex; align-items: center; margin-bottom: 8px; font-size: 13px; }
.memory-label { color: var(--text-secondary); min-width: 50px; flex-shrink: 0; }
.memory-value { font-weight: 500; }
.memory-value.write { color: var(--color-success); }
.memory-value.read { color: var(--color-primary); }
.memory-key { background: var(--bg-overlay); padding: 2px 8px; border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: 12px; color: var(--color-warning); }
.memory-value-text { color: var(--text-regular); word-break: break-all; }
</style>
