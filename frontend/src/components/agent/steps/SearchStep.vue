<script setup lang="ts">
import { ref, computed } from 'vue'
import type { AgentStep, SearchData } from '../../../types/agent'

const props = defineProps<{ step: AgentStep }>()

const expanded = ref(props.step.status === 'running')
const data = computed(() => props.step.data as SearchData)

function toggleExpand() {
  expanded.value = !expanded.value
}
</script>

<template>
  <div class="step-card" :class="{ expanded }">
    <div class="step-header" @click="toggleExpand">
      <span class="step-icon">🔍</span>
      <span class="step-title">{{ step.title }}</span>
      <el-tag size="small" :type="step.status === 'completed' ? 'success' : step.status === 'running' ? 'warning' : 'danger'">
        {{ step.status === 'completed' ? 'done' : step.status === 'running' ? 'searching...' : 'error' }}
      </el-tag>
      <span class="step-arrow">{{ expanded ? '▾' : '▸' }}</span>
    </div>
    <div v-show="expanded" class="step-content">
      <div v-if="data.query" class="search-query">
        <strong>搜索词：</strong>{{ data.query }}
      </div>
      <div v-if="data.answer" class="search-answer">
        <strong>AI 摘要：</strong>{{ data.answer }}
      </div>
      <div v-if="data.results && data.results.length > 0" class="search-results">
        <div class="results-label">搜索结果 ({{ data.results.length }})：</div>
        <div v-for="(r, i) in data.results" :key="i" class="result-item">
          <a :href="r.url" target="_blank" rel="noopener" class="result-title">{{ r.title || '无标题' }}</a>
          <p class="result-snippet">{{ r.snippet }}</p>
        </div>
      </div>
      <div v-if="data.results && data.results.length === 0 && step.status === 'completed'" class="no-results">
        未找到相关结果
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
.search-query { padding-top: 10px; font-size: 13px; color: var(--text-regular); }
.search-answer { padding-top: 8px; font-size: 13px; line-height: 1.6; color: var(--text-regular); background: var(--bg-overlay); padding: 10px; border-radius: var(--radius-sm); margin-top: 8px; }
.search-results { margin-top: 10px; }
.results-label { font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; font-weight: 500; }
.result-item { padding: 8px 0; border-bottom: 1px solid var(--border-light); }
.result-item:last-child { border-bottom: none; }
.result-title { font-size: 13px; color: var(--color-primary); text-decoration: none; font-weight: 500; display: block; margin-bottom: 4px; }
.result-title:hover { text-decoration: underline; }
.result-snippet { font-size: 12px; color: var(--text-secondary); line-height: 1.5; margin: 0; }
.no-results { padding-top: 10px; font-size: 13px; color: var(--text-placeholder); font-style: italic; }
</style>
