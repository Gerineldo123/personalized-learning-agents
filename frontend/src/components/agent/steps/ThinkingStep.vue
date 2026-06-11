<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import type { AgentStep, ThinkingData } from '../../../types/agent'

const props = defineProps<{ step: AgentStep }>()

const expanded = ref(props.step.status === 'running')
const displayedContent = ref('')

const data = props.step.data as ThinkingData
let charIndex = 0
let timer: ReturnType<typeof setInterval> | null = null

watch(
  () => props.step,
  (newStep) => {
    const newData = newStep.data as ThinkingData
    if (newStep.status === 'running' && newData.content) {
      if (timer) clearInterval(timer)
      charIndex = 0
      displayedContent.value = ''
      expanded.value = true
      timer = setInterval(() => {
        if (charIndex < newData.content.length) {
          displayedContent.value += newData.content[charIndex]
          charIndex++
        } else {
          if (timer) clearInterval(timer)
        }
      }, 15)
    } else if (newStep.status === 'completed') {
      displayedContent.value = newData.content
      if (timer) clearInterval(timer)
    }
  },
  { deep: true, immediate: true },
)

function toggleExpand() {
  expanded.value = !expanded.value
}

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="step-card" :class="{ expanded }">
    <div class="step-header" @click="toggleExpand">
      <span class="step-icon">🦉</span>
      <span class="step-title">{{ step.title }}</span>
      <span class="step-status" :class="step.status">
        {{ step.status === 'running' ? '思考中...' : step.status === 'completed' ? '完成' : '错误' }}
      </span>
      <span class="step-arrow">{{ expanded ? '▾' : '▸' }}</span>
    </div>
    <div v-show="expanded" class="step-content">
      <div class="typewriter">
        {{ displayedContent }}
        <span v-if="step.status === 'running'" class="cursor-blink">|</span>
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

.step-status {
  font-size: 12px;
  flex-shrink: 0;
}

.step-status.running {
  color: #409eff;
}

.step-status.completed {
  color: #67c23a;
}

.step-status.error {
  color: #f56c6c;
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

.typewriter {
  padding-top: 10px;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  color: #333;
}

.cursor-blink {
  animation: blink 1s step-end infinite;
  color: #409eff;
  font-weight: bold;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
