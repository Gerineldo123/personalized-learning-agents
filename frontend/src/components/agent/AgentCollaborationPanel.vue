<script setup lang="ts">
import { computed } from 'vue'
import type { AgentCollaborationEvent } from '../../types/agent'

const props = defineProps<{
  events: AgentCollaborationEvent[]
  title?: string
  compact?: boolean
}>()

const statusRank: Record<string, number> = {
  waiting: 0,
  running: 1,
  completed: 2,
  error: 3,
}

const statusLabel: Record<string, string> = {
  waiting: '等待中',
  running: '执行中',
  completed: '已完成',
  error: '失败',
}

const statusTagType: Record<string, 'info' | 'warning' | 'success' | 'danger'> = {
  waiting: 'info',
  running: 'warning',
  completed: 'success',
  error: 'danger',
}

const resourceLabel: Record<string, string> = {
  article: '文章',
  quiz: '题库',
  code: '代码',
  anime: '动画',
  mindmap: '思维导图',
  ppt: 'PPT课件',
  video: '视频',
  evaluation: '评估',
}

const agentIcon: Record<string, string> = {
  planner: '🧭',
  profile: '👤',
  diagnosis: '🔎',
  content_article: '📄',
  mindmap: '🧠',
  quiz: '❓',
  code: '💻',
  anime: '🎬',
  ppt: '📊',
  video: '🎞️',
  evaluation: '📈',
  review: '🛡️',
  knowledge_graph: '🕸️',
  path: '🧭',
  summary: '✅',
}

const agents = computed(() => {
  const map = new Map<string, AgentCollaborationEvent>()
  for (const event of props.events) {
    const previous = map.get(event.agent_key)
    if (!previous || statusRank[event.status] >= statusRank[previous.status]) {
      map.set(event.agent_key, event)
    }
  }
  return Array.from(map.values())
})

const currentEvent = computed(() =>
  [...props.events].reverse().find((event) => event.status === 'running') || props.events[props.events.length - 1],
)

const resources = computed(() =>
  props.events.filter((event) => event.resource_id && event.status === 'completed'),
)

function displayStatus(status: string) {
  return statusLabel[status] || status
}

function tagType(status: string) {
  return statusTagType[status] || 'info'
}

function formatTime(value: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString('zh-CN', { hour12: false })
}
</script>

<template>
  <section v-if="events.length > 0" class="collab-panel" :class="{ compact }">
    <div class="collab-head">
      <div>
        <div class="collab-title">{{ title || '澶氭櫤鑳戒綋鍗忎綔杩囩▼' }}</div>
        <div class="collab-subtitle">
          {{ currentEvent ? `${currentEvent.agent_name} 路 ${currentEvent.role}` : '绛夊緟鍗忎綔浜嬩欢' }}
        </div>
      </div>
      <el-tag v-if="currentEvent" :type="tagType(currentEvent.status)" size="small">
        {{ displayStatus(currentEvent.status) }}
      </el-tag>
    </div>

    <div class="agent-grid">
      <div
        v-for="agent in agents"
        :key="agent.agent_key"
        class="agent-card"
        :class="[`status-${agent.status}`]"
      >
        <div class="agent-card-top">
          <span class="agent-icon">{{ agentIcon[agent.agent_key] || '馃' }}</span>
          <el-tag :type="tagType(agent.status)" size="small">{{ displayStatus(agent.status) }}</el-tag>
        </div>
        <div class="agent-name">{{ agent.agent_name }}</div>
        <div class="agent-role">{{ agent.role }}</div>
        <div v-if="agent.resource_type" class="agent-resource">
          {{ resourceLabel[agent.resource_type] || agent.resource_type }}
          <template v-if="agent.resource_title"> 路 {{ agent.resource_title }}</template>
        </div>
        <div v-if="agent.error" class="agent-error">{{ agent.error }}</div>
      </div>
    </div>

    <div v-if="resources.length > 0" class="resource-links">
      <a
        v-for="event in resources"
        :key="event.event_id"
        :href="`/resources?open=${event.resource_id}`"
      >
        {{ resourceLabel[event.resource_type || ''] || event.resource_type }}锛歿{ event.resource_title || event.resource_id }}
      </a>
    </div>

    <div class="event-timeline">
      <div v-for="event in events" :key="event.event_id" class="event-row">
        <span class="event-time">{{ formatTime(event.timestamp) }}</span>
        <span class="event-dot" :class="`status-${event.status}`"></span>
        <span class="event-agent">{{ event.agent_name }}</span>
        <span class="event-text">{{ event.output_summary || event.role }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.collab-panel {
  margin: 12px 0 18px;
  padding: 16px;
  border: 1px solid #f0d8bd;
  border-radius: 18px;
  background: linear-gradient(135deg, #fffaf4 0%, #fffdf9 100%);
  box-shadow: 0 10px 30px rgba(188, 126, 73, 0.08);
}
.collab-panel.compact {
  margin: 10px 0;
  padding: 14px;
}
.collab-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 14px;
}
.collab-title {
  font-size: 16px;
  font-weight: 700;
  color: #30251e;
}
.collab-subtitle {
  margin-top: 4px;
  color: #8a7664;
  font-size: 13px;
}
.agent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 10px;
}
.agent-card {
  min-height: 118px;
  padding: 12px;
  border: 1px solid #eee0d2;
  border-radius: 14px;
  background: #fff;
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.agent-card.status-running {
  border-color: #e6a23c;
  box-shadow: 0 8px 22px rgba(230, 162, 60, 0.16);
  animation: collabPulse 1.4s ease-in-out infinite;
}
.agent-card.status-completed {
  border-color: #95d5aa;
}
.agent-card.status-error {
  border-color: #f3a6a6;
  background: #fff8f8;
}
.agent-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.agent-icon {
  font-size: 22px;
}
.agent-name {
  color: #2f2924;
  font-weight: 700;
  font-size: 14px;
}
.agent-role,
.agent-resource {
  margin-top: 5px;
  color: #75675c;
  font-size: 12px;
  line-height: 1.45;
}
.agent-error {
  margin-top: 6px;
  color: #d64b4b;
  font-size: 12px;
}
.resource-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.resource-links a {
  padding: 6px 10px;
  border: 1px solid #e8d3bd;
  border-radius: 999px;
  background: #fff8ef;
  color: #a6662c;
  text-decoration: none;
  font-size: 12px;
}
.event-timeline {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed #ead8c6;
  max-height: 220px;
  overflow: auto;
}
.event-row {
  display: grid;
  grid-template-columns: 72px 12px 120px 1fr;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  color: #66584e;
  font-size: 12px;
}
.event-time {
  color: #a49487;
  font-variant-numeric: tabular-nums;
}
.event-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #c8c8c8;
}
.event-dot.status-running { background: #e6a23c; }
.event-dot.status-completed { background: #67c23a; }
.event-dot.status-error { background: #f56c6c; }
.event-agent {
  font-weight: 600;
  color: #3d342d;
}
.event-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@keyframes collabPulse {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-2px); }
}
</style>

