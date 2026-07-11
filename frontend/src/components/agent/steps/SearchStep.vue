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
      <span class="step-icon">馃攳</span>
      <span class="step-title">{{ step.title }}</span>
      <el-tag size="small" :type="step.status === 'completed' ? 'success' : step.status === 'running' ? 'warning' : 'danger'">
        {{ step.status === 'completed' ? 'done' : step.status === 'running' ? 'searching...' : 'error' }}
      </el-tag>
      <span class="step-arrow">{{ expanded ? '▾' : '▸' }}</span>
    </div>
    <div v-show="expanded" class="step-content">
      <div v-if="data.query" class="search-query">
        <strong>鎼滅储璇嶏細</strong>{{ data.query }}
      </div>
      <div v-if="data.answer" class="search-answer">
        <strong>AI 鎽樿锛</strong>{{ data.answer }}
      </div>
      <div v-if="data.results && data.results.length > 0" class="search-results">
        <div class="results-label">鎼滅储缁撴灉 ({{ data.results.length }})锛</div>
        <div v-for="(r, i) in data.results" :key="i" class="result-item">
          <a :href="r.url" class="result-title">{{ r.title || '无标题' }}</a>
          <p class="result-snippet">{{ r.snippet }}</p>
        </div>
      </div>
      <div v-if="data.results && data.results.length === 0 && step.status === 'completed'" class="no-results">
        鏈壘鍒扮浉鍏崇粨鏋?
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
.search-query { padding-top: 10px; font-size: 13px; color: #6B635C; }
.search-answer { padding: 10px; font-size: 13px; line-height: 1.6; color: #6B635C; background: #FFF5EB; border-radius: 8px; margin-top: 8px; border-left: 3px solid #F9D9B8; }
.search-results { margin-top: 10px; }
.results-label { font-size: 12px; color: #948A80; margin-bottom: 8px; font-weight: 500; }
.result-item { padding: 8px 0; border-bottom: 1px solid #EFE6DC; }
.result-item:last-child { border-bottom: none; }
.result-title { font-size: 13px; color: #DBA878; text-decoration: none; font-weight: 500; display: block; margin-bottom: 4px; transition: color 0.2s; }
.result-title:hover { color: #E8C29C; text-decoration: underline; }
.result-snippet { font-size: 12px; color: #948A80; line-height: 1.5; margin: 0; }
.no-results { padding-top: 10px; font-size: 13px; color: #948A80; font-style: italic; }
</style>
