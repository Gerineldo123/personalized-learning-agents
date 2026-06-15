<script setup lang="ts">
import { computed } from 'vue'
import type { AgentStep } from '../../types/agent'
import ThinkingStep from './steps/ThinkingStep.vue'
import SearchStep from './steps/SearchStep.vue'
import MemoryStep from './steps/MemoryStep.vue'
import CodeStep from './steps/CodeStep.vue'
import ScrapeStep from './steps/ScrapeStep.vue'
import SkillStep from './steps/SkillStep.vue'
import ResultStep from './steps/ResultStep.vue'

const props = defineProps<{
  steps: AgentStep[]
  isExecuting: boolean
}>()

const emit = defineEmits<{ (e: 'rerun'): void }>()

// 从 steps 中提取参与的智能体列表（去重、按首次出现顺序）
const activeAgents = computed(() => {
  const seen = new Set<string>()
  const list: { name: string; icon: string; done: boolean }[] = []
  const skillIconMap: Record<string, string> = {
    deep_search: '🔍', code_analysis: '💻', mindmap_gen: '🧠', quiz_gen: '📝', video_search: '🎬',
  }
  for (const step of props.steps) {
    // 来自 agent_name 字段
    const name = step.agentName || (
      step.stepType === 'thinking' ? '规划智能体' :
      step.stepType === 'result' ? '汇总智能体' : null
    )
    if (name && !seen.has(name)) {
      seen.add(name)
      list.push({ name, icon: agentIcon(name), done: step.status === 'completed' })
    }
    // 来自 skill 步骤的 skill_name
    if (step.stepType === 'skill') {
      const sname = (step.data as any)?.skill_name as string
      const skillAgentName = skillAgentLabel(sname)
      if (skillAgentName && !seen.has(skillAgentName)) {
        seen.add(skillAgentName)
        const icon = skillIconMap[sname] || '⚡'
        list.push({ name: skillAgentName, icon, done: step.status === 'completed' })
      }
    }
  }
  return list
})

function agentIcon(name: string): string {
  if (name.includes('规划')) return '🦉'
  if (name.includes('对话')) return '💬'
  if (name.includes('汇总')) return '✅'
  return '🤖'
}

function skillAgentLabel(skillName: string): string {
  const map: Record<string, string> = {
    deep_search: '搜索智能体', code_analysis: '代码智能体',
    mindmap_gen: '导图智能体', quiz_gen: '出题智能体', video_search: '视频智能体',
  }
  return map[skillName] || ''
}

function getStepIcon(stepType: string): string {
  const icons: Record<string, string> = {
    thinking: '🦉', search: '🔍', code: '💻', memory: '📝',
    scrape: '🌐', skill: '⚡', result: '✅',
  }
  return icons[stepType] || '📌'
}
</script>

<template>
  <div class="timeline" v-if="steps.length > 0">
    <!-- 智能体协作状态栏 -->
    <div v-if="activeAgents.length > 0" class="agent-collab-bar">
      <span class="collab-label">智能体协作</span>
      <div class="agent-chips">
        <div
          v-for="agent in activeAgents" :key="agent.name"
          :class="['agent-chip', { active: isExecuting && !agent.done }]"
        >
          <span class="agent-chip-icon">{{ agent.icon }}</span>
          <span class="agent-chip-name">{{ agent.name }}</span>
        </div>
      </div>
    </div>

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
        <!-- 智能体标签 -->
        <div v-if="step.agentName" class="step-agent-badge">{{ step.agentName }}</div>
        <ThinkingStep v-if="step.stepType === 'thinking'" :step="step" />
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
.timeline { max-width: 900px; margin: 0 auto; }

.agent-collab-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding: 10px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
}
.collab-label {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  font-weight: 500;
}
.agent-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.agent-chip {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  background: var(--bg-overlay);
  border: 1px solid var(--border-light);
  font-size: 12px;
  color: var(--text-regular);
  transition: all var(--transition-fast);
}
.agent-chip.active {
  background: var(--color-primary-bg);
  border-color: var(--color-primary-border);
  color: var(--color-primary);
  animation: pulse-glow 1.5s ease-in-out infinite;
}
.agent-chip-icon { font-size: 14px; }
.agent-chip-name { font-size: 12px; font-weight: 500; }

.step-agent-badge {
  font-size: 11px;
  color: var(--color-primary);
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-sm);
  padding: 2px 8px;
  display: inline-block;
  margin-bottom: 4px;
}

.timeline-node { display: flex; gap: 14px; animation: fadeIn 0.35s ease; }
.timeline-line-col { display: flex; flex-direction: column; align-items: center; width: 40px; flex-shrink: 0; }
.timeline-dot {
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: var(--bg-overlay); border: 2px solid var(--border-base);
  font-size: 16px; flex-shrink: 0; transition: all 0.3s ease;
}
.timeline-dot.running { background: var(--color-primary-bg); border-color: var(--color-primary); animation: pulse-glow 1.5s ease-in-out infinite; }
.timeline-dot.completed { background: var(--color-success-bg); border-color: var(--color-success); }
.timeline-dot.error { background: var(--color-danger-bg); border-color: var(--color-danger); }
.timeline-vline { width: 2px; flex: 1; min-height: 20px; background: var(--border-light); margin: 4px 0; }
.timeline-vline.dashed {
  background: repeating-linear-gradient(to bottom, var(--text-placeholder) 0px, var(--text-placeholder) 4px, transparent 4px, transparent 8px);
}
.timeline-card-wrapper { flex: 1; min-width: 0; padding-bottom: 16px; }
.executing-indicator { padding: 20px; color: var(--text-secondary); font-style: italic; animation: fade-pulse 1.5s ease-in-out infinite; }

@keyframes pulse-glow { 0%, 100% { box-shadow: 0 0 0 0 rgba(249,217,184,0.6); } 50% { box-shadow: 0 0 0 8px rgba(249,217,184,0); } }
@keyframes fade-pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
</style>

