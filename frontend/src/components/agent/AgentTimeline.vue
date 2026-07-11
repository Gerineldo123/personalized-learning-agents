<script setup lang="ts">
import type { AgentStep } from '../../types/agent'
import ThinkingStep from './steps/ThinkingStep.vue'
import SearchStep from './steps/SearchStep.vue'
import MemoryStep from './steps/MemoryStep.vue'
import CodeStep from './steps/CodeStep.vue'
import ScrapeStep from './steps/ScrapeStep.vue'
import SkillStep from './steps/SkillStep.vue'
import ResultStep from './steps/ResultStep.vue'
import { normalizeAgentName } from '../../utils/agentLabels'

defineProps<{
  steps: AgentStep[]
  isExecuting: boolean
}>()

const emit = defineEmits<{ (e: 'rerun'): void }>()

function getStepIcon(stepType: string): string {
  const icons: Record<string, string> = {
    user: '👤',
    thinking: '🧭',
    search: '🔎',
    memory: '📝',
    code: '💻',
    scrape: '🌐',
    skill: '🔧',
    result: '✅',
  }
  return icons[stepType] || '📌'
}

function userStepData(step: AgentStep) {
  return step.data as { content: string; fileName?: string }
}
</script>

<template>
  <div class="timeline" v-if="steps.length > 0 || isExecuting">
    <div
      v-for="(step, index) in steps"
      :key="step.stepId"
      class="timeline-node"
      :class="{ 'wide-node': step.stepType === 'code' }"
    >
      <div class="timeline-line-col">
        <div
          class="timeline-dot"
          :class="{
            running: step.status === 'running',
            completed: step.status === 'completed',
            error: step.status === 'error',
          }"
        >
          <span>{{ getStepIcon(step.stepType) }}</span>
        </div>
        <div
          v-if="index < steps.length - 1"
          class="timeline-vline"
          :class="{ dashed: step.status === 'completed' }"
        />
      </div>

      <div class="timeline-card-wrapper">
        <div v-if="step.agentName" class="step-agent-badge">{{ normalizeAgentName(step.agentName) }}</div>

        <div v-if="step.stepType === 'user'" class="user-step-card">
          <div class="user-step-header">
            <span class="user-step-icon">👤</span>
            <span class="user-step-title">{{ step.title }}</span>
          </div>
          <div class="user-step-content">
            <div v-if="userStepData(step).fileName" class="user-file">📎 {{ userStepData(step).fileName }}</div>
            <div class="user-text">{{ userStepData(step).content }}</div>
          </div>
        </div>

        <ThinkingStep v-else-if="step.stepType === 'thinking'" :step="step" />
        <SearchStep v-else-if="step.stepType === 'search'" :step="step" />
        <CodeStep v-else-if="step.stepType === 'code'" :step="step" />
        <MemoryStep v-else-if="step.stepType === 'memory'" :step="step" />
        <ScrapeStep v-else-if="step.stepType === 'scrape'" :step="step" />
        <SkillStep v-else-if="step.stepType === 'skill'" :step="step" />
        <ResultStep v-else-if="step.stepType === 'result'" :step="step" @rerun="emit('rerun')" />
      </div>
    </div>

    <div v-if="isExecuting" class="timeline-node">
      <div class="timeline-line-col">
        <div class="timeline-dot running pulse"><span>⏳</span></div>
      </div>
      <div class="timeline-card-wrapper">
        <div class="executing-indicator">执行中...</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.timeline {
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
}
.timeline-node {
  display: flex;
  gap: 14px;
  animation: fadeIn 0.35s cubic-bezier(.4,0,.2,1);
}
.timeline-line-col {
  display: flex;
  align-items: center;
  flex-direction: column;
  flex-shrink: 0;
  width: 44px;
}
.timeline-dot {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: #fff5eb;
  border: 2px solid #e8c29c;
  color: #7c5c3c;
  font-size: 16px;
}
.timeline-dot.running {
  border-color: #dba878;
  box-shadow: 0 0 0 6px rgba(219, 168, 120, 0.16);
}
.timeline-dot.completed {
  border-color: #98c9b3;
  background: #f0faf5;
}
.timeline-dot.error {
  border-color: #f2b8a2;
  background: #fff1f0;
}
.timeline-vline {
  width: 2px;
  flex: 1;
  min-height: 28px;
  background: #ead7bf;
}
.timeline-vline.dashed {
  background: repeating-linear-gradient(to bottom, #e8c29c 0, #e8c29c 5px, transparent 5px, transparent 10px);
}
.timeline-card-wrapper {
  flex: 1;
  min-width: 0;
  margin-bottom: 18px;
}
.step-agent-badge {
  font-size: 11px;
  color: #6b635c;
  background: #fff5eb;
  border: 1px solid #efe6dc;
  border-radius: 6px;
  padding: 2px 8px;
  display: inline-block;
  margin-bottom: 4px;
}
.user-step-card {
  border: 1px solid #efe6dc;
  border-radius: 12px;
  background: #fffbf5;
  overflow: hidden;
}
.user-step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #fff5eb;
  font-weight: 700;
  color: #3a332e;
}
.user-step-content {
  padding: 12px 14px;
  color: #4d4034;
  line-height: 1.7;
}
.user-file {
  margin-bottom: 8px;
  color: #7c5c3c;
}
.user-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.executing-indicator {
  padding: 14px;
  color: #8a7b6a;
}
.pulse {
  animation: pulse-glow 1.4s ease-in-out infinite;
}
@keyframes pulse-glow {
  0%, 100% { box-shadow: 0 0 0 4px rgba(219, 168, 120, 0.14); }
  50% { box-shadow: 0 0 0 9px rgba(219, 168, 120, 0.06); }
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
