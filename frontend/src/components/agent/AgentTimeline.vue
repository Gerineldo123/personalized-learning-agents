<script setup lang="ts">
import type { AgentStep } from '../../types/agent'
import ThinkingStep from './steps/ThinkingStep.vue'
import SearchStep from './steps/SearchStep.vue'
import MemoryStep from './steps/MemoryStep.vue'
import CodeStep from './steps/CodeStep.vue'
import ScrapeStep from './steps/ScrapeStep.vue'
import SkillStep from './steps/SkillStep.vue'
import ResultStep from './steps/ResultStep.vue'

defineProps<{
  steps: AgentStep[]
  isExecuting: boolean
}>()

const emit = defineEmits<{ (e: 'rerun'): void }>()

function getStepIcon(stepType: string): string {
  const icons: Record<string, string> = {
    thinking: '🦉',
    search: '🔍',
    code: '💻',
    memory: '📝',
    scrape: '🌐',
    skill: '⚡',
    result: '✅',
  }
  return icons[stepType] || '📌'
}
</script>

<template>
  <div class="timeline" v-if="steps.length > 0">
    <div
      v-for="(step, index) in steps"
      :key="step.stepId"
      class="timeline-node"
    >
      <div class="timeline-line-col">
        <div class="timeline-dot" :class="{ running: step.status === 'running', completed: step.status === 'completed', error: step.status === 'error' }">
          <span>{{ getStepIcon(step.stepType) }}</span>
        </div>
        <div v-if="index < steps.length - 1" class="timeline-vline" :class="{ dashed: step.status === 'completed' }"></div>
      </div>

      <div class="timeline-card-wrapper">
        <ThinkingStep
          v-if="step.stepType === 'thinking'"
          :step="step"
        />
        <SearchStep
          v-else-if="step.stepType === 'search'"
          :step="step"
        />
        <CodeStep
          v-else-if="step.stepType === 'code'"
          :step="step"
        />
        <MemoryStep
          v-else-if="step.stepType === 'memory'"
          :step="step"
        />
        <ScrapeStep
          v-else-if="step.stepType === 'scrape'"
          :step="step"
        />
        <SkillStep
          v-else-if="step.stepType === 'skill'"
          :step="step"
        />
        <ResultStep
          v-else-if="step.stepType === 'result'"
          :step="step"
          @rerun="emit('rerun')"
        />
      </div>
    </div>

    <div v-if="isExecuting" class="timeline-node">
      <div class="timeline-line-col">
        <div class="timeline-dot running pulse">
          <span>⏳</span>
        </div>
      </div>
      <div class="timeline-card-wrapper">
        <div class="executing-indicator">执行中...</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.timeline {
  max-width: 900px;
  margin: 0 auto;
}

.timeline-node {
  display: flex;
  gap: 14px;
}

.timeline-line-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 40px;
  flex-shrink: 0;
}

.timeline-dot {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #e4e7ed;
  font-size: 16px;
  flex-shrink: 0;
  transition: all 0.3s ease;
}

.timeline-dot.running {
  background: #ecf5ff;
  border: 2px solid #409eff;
  animation: pulse-glow 1.5s ease-in-out infinite;
}

.timeline-dot.completed {
  background: #f0f9eb;
  border: 2px solid #67c23a;
}

.timeline-dot.error {
  background: #fef0f0;
  border: 2px solid #f56c6c;
}

.timeline-vline {
  width: 2px;
  flex: 1;
  min-height: 20px;
  background: #dcdfe6;
  margin: 4px 0;
}

.timeline-vline.dashed {
  background: repeating-linear-gradient(
    to bottom,
    #c0c4cc 0px,
    #c0c4cc 4px,
    transparent 4px,
    transparent 8px
  );
}

.timeline-card-wrapper {
  flex: 1;
  min-width: 0;
  padding-bottom: 16px;
}

.executing-indicator {
  padding: 20px;
  color: #909399;
  font-style: italic;
  animation: fade-pulse 1.5s ease-in-out infinite;
}

@keyframes pulse-glow {
  0%, 100% { box-shadow: 0 0 0 0 rgba(64, 158, 255, 0.4); }
  50% { box-shadow: 0 0 0 6px rgba(64, 158, 255, 0); }
}

@keyframes fade-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}
</style>
