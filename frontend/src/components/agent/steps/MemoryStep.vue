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
.step-card { background: #FFFBF5; border-radius: 12px; border: 1px solid #EFE6DC; overflow: hidden; transition: all 0.25s cubic-bezier(.4,0,.2,1); }
.step-card:hover { box-shadow: 0 2px 10px rgba(58,51,46,0.08); transform: translateY(-1px); }
.step-header { display: flex; align-items: center; padding: 10px 14px; cursor: pointer; gap: 8px; user-select: none; transition: background 0.2s; }
.step-header:hover { background: #FFF5EB; }
.step-icon { font-size: 18px; flex-shrink: 0; }
.step-title { flex: 1; font-size: 14px; font-weight: 500; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #3A332E; }
.memory-tag { font-size: 11px; padding: 2px 8px; border-radius: 6px; flex-shrink: 0; font-weight: 600; }
.memory-tag.write { background: #F0FAF5; color: #98C9B3; }
.memory-tag.read { background: #FFF5EB; color: #DBA878; }
.step-arrow { font-size: 12px; color: #948A80; flex-shrink: 0; }
.step-content { padding: 0 14px 14px; border-top: 1px solid #EFE6DC; }
.memory-item { padding-top: 12px; }
.memory-row { display: flex; align-items: center; margin-bottom: 8px; font-size: 13px; }
.memory-label { color: #948A80; min-width: 50px; flex-shrink: 0; }
.memory-value { font-weight: 500; }
.memory-value.write { color: #98C9B3; }
.memory-value.read { color: #DBA878; }
.memory-key { background: #FFF5EB; padding: 2px 8px; border-radius: 6px; font-family: var(--font-mono); font-size: 12px; color: #E8C29C; border: 1px solid #EFE6DC; }
.memory-value-text { color: #6B635C; word-break: break-all; }
</style>
