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

.step-arrow {
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
}

.step-content {
  padding: 0 14px 14px;
  border-top: 1px solid #f0f0f0;
}

.search-query {
  padding-top: 10px;
  font-size: 13px;
  color: #606266;
}

.search-answer {
  padding-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: #333;
  background: #f5f7fa;
  padding: 10px;
  border-radius: 6px;
  margin-top: 8px;
}

.search-results {
  margin-top: 10px;
}

.results-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  font-weight: 500;
}

.result-item {
  padding: 8px 0;
  border-bottom: 1px solid #f5f5f5;
}

.result-item:last-child {
  border-bottom: none;
}

.result-title {
  font-size: 13px;
  color: #409eff;
  text-decoration: none;
  font-weight: 500;
  display: block;
  margin-bottom: 4px;
}

.result-title:hover {
  text-decoration: underline;
}

.result-snippet {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin: 0;
}

.no-results {
  padding-top: 10px;
  font-size: 13px;
  color: #c0c4cc;
  font-style: italic;
}
</style>
