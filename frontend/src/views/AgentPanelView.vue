<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted, provide, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'
import { useAgentStore } from '../stores/agent'
import { useThemeStore } from '../stores/theme'
import { agentExecuteStream, uploadFile } from '../api/agent'
import { chatStream } from '../api/chat'
import { workflowStream, type WorkflowType } from '../api/workflow'
import type { ResourceEvent } from '../api/workflow'
import { runDemo } from '../mock/agentDemo'
import type { AgentCollaborationEvent, AgentStep, StepEvent, UploadedFile } from '../types/agent'
import AgentTimeline from '../components/agent/AgentTimeline.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { renderMarkdownEnhanced, escapeHtml } from '../utils/markdown'

const userStore = useUserStore()
const agentStore = useAgentStore()
const themeStore = useThemeStore()
const route = useRoute()
const router = useRouter()

if (!userStore.userId) userStore.setUserId('user_' + Date.now())
provide('userId', userStore.userId)

onMounted(async () => {
  await initializeAgentPanel()
  window.addEventListener('keydown', handleTermKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', handleTermKeydown)
  stopTermDrag()
})

// 鈹€鈹€ 鐘舵€?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const inputText = ref('')
const mainContainer = ref<HTMLElement | null>(null)
const uploadedFile = ref<UploadedFile | null>(null)
const uploading = ref(false)

// 鈹€鈹€ 浼氳瘽绠＄悊 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
interface ConvItem { id: number; title: string; updated_at: string }
const conversations = ref<ConvItem[]>([])
const currentConvId = ref<number | null>(null)
// convId -> history messages
const historyMap = ref<Record<number, { role: string; content: string }[]>>({})
// convId -> mode ('chat' | 'task')
const convModeMap = ref<Record<number, 'chat' | 'task'>>({})
// convId -> chat messages (瀵硅瘽妯″紡)
type TaskOnlyIntent = 'video' | 'anime' | 'resource' | 'quiz' | 'ppt' | 'mindmap' | 'path' | 'mistake_review'
interface ChatHandoff {
  taskText: string
  intentType: TaskOnlyIntent
  label: string
  dismissed?: boolean
}
interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  uid: number
  glossary?: Record<string, string>
  handoff?: ChatHandoff
}
const chatMsgMap = ref<Record<number, ChatMsg[]>>({})
let msgUid = 0

const currentMode = computed(() => currentConvId.value ? (convModeMap.value[currentConvId.value] || 'chat') : 'chat')
const currentChatMsgs = computed(() => currentConvId.value ? (chatMsgMap.value[currentConvId.value] || []) : [])
// 鍙樉绀哄綋鍓嶄細璇濈殑浠诲姟
const currentConvTasks = computed(() =>
  agentStore.tasks.filter((t: any) => t.convId === currentConvId.value)
)
const currentTask = computed(() =>
  currentConvTasks.value.find(t => t.id === agentStore.currentTaskId) || currentConvTasks.value[0] || null
)

function panelStorageKey(suffix: string) {
  return `agent_panel_${suffix}:${userStore.userId || 'anonymous'}`
}

function readStoredCurrentConvId(): number | null {
  try {
    const raw = localStorage.getItem(panelStorageKey('current_conv_id'))
    const id = raw ? Number(JSON.parse(raw)) : null
    return Number.isFinite(id) && id ? id : null
  } catch {
    return null
  }
}

function saveStoredCurrentConvId(id: number | null) {
  try {
    if (id) localStorage.setItem(panelStorageKey('current_conv_id'), JSON.stringify(id))
    else localStorage.removeItem(panelStorageKey('current_conv_id'))
  } catch {}
}

function readStoredConvModes(): Record<number, 'chat' | 'task'> {
  try {
    return JSON.parse(localStorage.getItem(panelStorageKey('conv_modes')) || '{}')
  } catch {
    return {}
  }
}

function saveStoredConvModes() {
  try {
    localStorage.setItem(panelStorageKey('conv_modes'), JSON.stringify(convModeMap.value))
  } catch {}
}

async function initializeAgentPanel() {
  await loadConversations()
  convModeMap.value = { ...readStoredConvModes(), ...convModeMap.value }
  const handled = await consumeAgentQuery()
  if (!handled) await restoreLastConversation()
}

async function restoreLastConversation() {
  if (currentConvId.value) return
  const storedId = readStoredCurrentConvId()
  const exists = storedId && conversations.value.some(c => c.id === storedId)
  const fallbackId = conversations.value[0]?.id || null
  const targetId = exists ? storedId : fallbackId
  if (targetId) await selectConversation(targetId)
}

async function loadConversations() {
  try {
    const r = await api.get('/conversations', { params: { user_id: userStore.userId } })
    conversations.value = r.data.items || []
    return conversations.value
  } catch {}
  return []
}

async function newConversation() {
  try {
    const r = await api.post('/conversations', null, { params: { user_id: userStore.userId, title: '新对话' } })
    currentConvId.value = r.data.id
    historyMap.value[r.data.id] = []
    chatMsgMap.value[r.data.id] = []
    convModeMap.value[r.data.id] = 'chat'
    await loadConversations()
    return r.data.id as number
  } catch {
    ElMessage.error('创建对话失败')
    return null
  }
}

async function selectConversation(id: number) {
  currentConvId.value = id
  agentStore.currentTaskId = currentConvTasks.value[0]?.id || null
  if (!historyMap.value[id]) {
    try {
      const r = await api.get(`/conversations/${id}/messages`)
      const msgs = r.data.items || []
      historyMap.value[id] = msgs.map((m: any) => ({ role: m.role, content: m.content }))
      // 如果是对话模式，恢复消息列表
      if (!chatMsgMap.value[id]) {
        chatMsgMap.value[id] = msgs.map((m: any) => ({ role: m.role, content: m.content, uid: msgUid++ }))
      }
    } catch { historyMap.value[id] = [] }
  }
}

async function deleteConversation(id: number, e: Event) {
  e.stopPropagation()
  try {
    await api.delete(`/conversations/${id}`)
    if (currentConvId.value === id) currentConvId.value = null
    await loadConversations()
  } catch { ElMessage.error('删除失败') }
}

async function saveMessage(role: string, content: string) {
  if (!currentConvId.value) return
  try {
    await api.post(`/conversations/${currentConvId.value}/messages`, null, { params: { role, content } })
    if (!historyMap.value[currentConvId.value]) historyMap.value[currentConvId.value] = []
    historyMap.value[currentConvId.value].push({ role, content })
  } catch {}
}

function currentHistory() {
  if (!currentConvId.value) return []
  return (historyMap.value[currentConvId.value] || []).slice(-20)
}

function setMode(mode: 'chat' | 'task') {
  if (!currentConvId.value) return
  convModeMap.value[currentConvId.value] = mode
}

watch(currentConvId, (id) => saveStoredCurrentConvId(id))
watch(convModeMap, () => saveStoredConvModes(), { deep: true })
watch(() => route.fullPath, async () => {
  await consumeAgentQuery()
})

// Task 元信息
interface TaskMeta {
  suggestions?: Array<{ text: string; action: WorkflowType | null; topic: string }>
  resources?: ResourceEvent[]
  collaborationEvents?: AgentCollaborationEvent[]
}
const taskMeta = ref<Record<number, TaskMeta>>({})

function stripSuggestionLines(content: string): string {
  return String(content || '').replace(/^\s*(?:\[建议\]|【建议】).*(?:\r?\n|$)/gm, '').trim()
}

function parseSuggestions(taskId: number, content: string) {
  void content
  if (!taskMeta.value[taskId]) taskMeta.value[taskId] = {}
  taskMeta.value[taskId].suggestions = []
}

function appendCollaborationEvent(taskId: number, event: AgentCollaborationEvent) {
  if (!taskMeta.value[taskId]) taskMeta.value[taskId] = {}
  const events = taskMeta.value[taskId].collaborationEvents || []
  if (!events.some((item) => item.event_id === event.event_id)) {
    taskMeta.value[taskId].collaborationEvents = [...events, event]
  }
}

// 滚动
function scrollToBottom() {
  nextTick(() => { if (mainContainer.value) mainContainer.value.scrollTop = mainContainer.value.scrollHeight })
}

let streamScrollTimer: ReturnType<typeof setTimeout> | null = null
function scheduleStreamScroll() {
  if (streamScrollTimer) return
  streamScrollTimer = setTimeout(() => {
    streamScrollTimer = null
    scrollToBottom()
  }, 60)
}

// 对话模式发送
const isStreaming = ref(false)

interface ChatSendOptions {
  textOverride?: string
  skipTaskHandoff?: boolean
  forceNewConversation?: boolean
}

function detectTaskOnlyIntent(text: string): { intentType: TaskOnlyIntent; label: string } | null {
  const normalized = text.replace(/\s+/g, '')
  const rules: Array<{ intentType: TaskOnlyIntent; label: string; pattern: RegExp }> = [
    { intentType: 'anime', label: '动画生成', pattern: /可视化动画|动画演示|演示动画|生成.*动画|可视化.*演示/ },
    { intentType: 'video', label: '视频搜索', pattern: /推荐.*视频|搜索.*视频|找.*视频|教学视频|视频资源/ },
    { intentType: 'ppt', label: 'PPT课件', pattern: /PPT|ppt|课件|幻灯片/ },
    { intentType: 'mindmap', label: '思维导图', pattern: /思维导图|脑图|知识导图/ },
    { intentType: 'quiz', label: '题库生成', pattern: /生成.*题库|生成.*练习题|生成.*测试题|出题|专项练习|针对性练习/ },
    { intentType: 'mistake_review', label: '错题补弱', pattern: /分析.*错题|错题.*练习|错题.*补弱|错题.*针对/ },
    { intentType: 'path', label: '学习路径', pattern: /学习路径|规划.*路径|学习计划|规划.*学习/ },
    { intentType: 'resource', label: '资源生成', pattern: /生成.*资源|学习资源|资源包|系统学习|多模态.*资源/ },
  ]
  return rules.find((rule) => rule.pattern.test(normalized)) || null
}

async function appendTaskHandoffMessage(text: string, intent: { intentType: TaskOnlyIntent; label: string }, forceNewConversation = false) {
  if (forceNewConversation || !currentConvId.value) {
    const id = await newConversation()
    if (!id) return
  }
  setMode('chat')
  if (inputText.value.trim() === text) inputText.value = ''

  if (!chatMsgMap.value[currentConvId.value!]) chatMsgMap.value[currentConvId.value!] = []
  const msgs = chatMsgMap.value[currentConvId.value!]
  msgs.push({ role: 'user', content: text, uid: msgUid++ })
  await saveMessage('user', text)

  const content = [
    `这个需求需要切换到 **任务模式** 执行。`,
    '',
    `对话模式适合概念解释、公式推导和学习建议；${intent.label} 需要调用对应工具智能体，才能生成可执行或可保存的结果。`,
  ].join('\n')
  msgs.push({
    role: 'assistant',
    content,
    uid: msgUid++,
    handoff: {
      taskText: text,
      intentType: intent.intentType,
      label: intent.label,
    },
  })
  await saveMessage('assistant', content)
  await loadConversations()
  scrollToBottom()
}

async function sendChatMessage(options: ChatSendOptions = {}) {
  const text = (options.textOverride ?? inputText.value).trim()
  if (!text || isStreaming.value || agentStore.isExecuting) return

  const taskOnlyIntent = detectTaskOnlyIntent(text)
  if (taskOnlyIntent && !options.skipTaskHandoff) {
    await appendTaskHandoffMessage(text, taskOnlyIntent, options.forceNewConversation)
    return
  }

  if (options.forceNewConversation || !currentConvId.value) {
    const id = await newConversation()
    if (!id) return
  }
  setMode('chat')
  if (!options.textOverride || inputText.value.trim() === text) inputText.value = ''

  if (!chatMsgMap.value[currentConvId.value!]) chatMsgMap.value[currentConvId.value!] = []
  const msgs = chatMsgMap.value[currentConvId.value!]
  msgs.push({ role: 'user', content: text, uid: msgUid++ })
  saveMessage('user', text)
  scrollToBottom()

  const aiMsg: ChatMsg = { role: 'assistant', content: '', streaming: true, uid: msgUid++ }
  msgs.push(aiMsg)
  isStreaming.value = true
  const aiIdx = msgs.length - 1
  const history = currentHistory()

  chatStream(
    userStore.userId, text, history,
    (chunk) => { msgs[aiIdx].content += chunk; scheduleStreamScroll() },
    async () => {
      msgs[aiIdx].streaming = false
      isStreaming.value = false
      const finalContent = stripSuggestionLines(msgs[aiIdx].content)
      msgs[aiIdx].content = finalContent
      await saveMessage('assistant', finalContent)
      await loadConversations()
      try {
        const r = await api.post('/chat/mark-terms', { text: finalContent })
        const marked = r.data.marked_text
        const glossary = r.data.glossary || {}
        msgs[aiIdx].glossary = glossary
        cacheGlossary(glossary)
        if (marked && marked !== finalContent) msgs[aiIdx].content = marked
      } catch {}
    },
    (err) => {
      msgs[aiIdx].content = `[错误] ${err.message}`
      msgs[aiIdx].streaming = false
      isStreaming.value = false
    },
  )
}

// 任务模式执行
async function executeTask(taskDescription?: string) {
  const text = (typeof taskDescription === 'string') ? taskDescription : inputText.value.trim()
  if (!text || agentStore.isExecuting) return
  if (!currentConvId.value) await newConversation()
  if (typeof taskDescription !== 'string') inputText.value = ''

  const convId = currentConvId.value!
  const taskTitle = uploadedFile.value ? `[${uploadedFile.value.fileName}] ${text}` : text
  const task = agentStore.createTask(taskTitle)
  ;(task as any).convId = convId
  agentStore.setTaskStatus(task.id, 'running')
  agentStore.isExecuting = true
  taskMeta.value[task.id] = {}
  agentStore.upsertStep(task.id, {
    stepId: `local-user-${task.id}`,
    stepType: 'user',
    status: 'completed',
    title: '已提交任务',
    data: {
      content: text,
      fileName: uploadedFile.value?.fileName,
    },
    expanded: true,
    timestamp: Date.now(),
  })
  scrollToBottom()

  const persistUserMessage = saveMessage('user', text).catch(() => {})
  const history = currentHistory()

  const ctrl = agentExecuteStream(
    userStore.userId, text,
    (evt) => handleStepEvent(evt, task.id),
    async () => {
      agentStore.isExecuting = false
      agentStore.setTaskStatus(task.id, 'completed')
      const resultStep = agentStore.tasks.find((t: any) => t.id === task.id)?.steps.find((s: any) => s.stepType === 'result')
      if (resultStep) {
        await persistUserMessage
        await saveMessage('assistant', (resultStep.data as any)?.content || '')
        await loadConversations()
      }
    },
    (err) => { console.error(err); agentStore.isExecuting = false; agentStore.setTaskStatus(task.id, 'completed') },
    uploadedFile.value?.content, uploadedFile.value?.fileName, history,
    (stepId, delta) => { agentStore.appendStepContent(task.id, stepId, delta); scheduleStreamScroll() },
    (event) => { appendCollaborationEvent(task.id, event); scheduleStreamScroll() },
  )
  agentStore.setAbortController(ctrl)
  uploadedFile.value = null
  scrollToBottom()
}

function runHandoffTask(msg: ChatMsg) {
  if (!msg.handoff || agentStore.isExecuting) return
  const taskText = msg.handoff.taskText
  msg.handoff.dismissed = true
  setMode('task')
  executeTask(taskText)
}

function dismissHandoff(msg: ChatMsg) {
  if (!msg.handoff) return
  msg.handoff.dismissed = true
}

function handleStepEvent(evt: StepEvent, taskId: number) {
  const step: AgentStep = {
    stepId: evt.step_id, stepType: evt.step_type, status: evt.status,
    title: evt.title, agentName: evt.agent_name, data: evt.data as unknown as AgentStep['data'],
    expanded: evt.status === 'running', timestamp: Date.now(),
  }
  agentStore.upsertStep(taskId, step)
  if (evt.status === 'completed' && evt.step_type === 'result') {
    agentStore.setTaskStatus(taskId, 'completed')
    agentStore.isExecuting = false
    parseSuggestions(taskId, (evt.data as any)?.content || '')
  }
  if (evt.status === 'error') { agentStore.isExecuting = false; agentStore.setTaskStatus(taskId, 'completed') }
  scrollToBottom()
}

// 工作流阶段展示
const stageTitleMap: Record<string, string> = {
  profile_analyzed: '画像分析',
  diagnosis_done: '学情诊断',
  resource_planned: '资源规划',
  resource_started: '开始生成资源',
  resource_created: '资源生成完成',
  resource_failed: '资源生成失败',
  safety_reviewed: '安全审查',
  knowledge_tagged: '知识图谱标注',
  path_updated: '学习路径更新',
  done: '闭环完成',
}

function stageTitle(stage: string) {
  return stageTitleMap[stage] || stage
}

function stageAgent(stage: string, data: any) {
  const type = data?.resource_type || ''
  if (type === 'mindmap') return '导图智能体'
  if (type === 'quiz') return '出题智能体'
  if (type === 'code') return '代码智能体'
  if (type === 'anime') return '动画智能体'
  if (type === 'ppt' || type === 'ppt_session') return '课件智能体'
  if (type === 'video') return '视频智能体'
  if (stage.includes('profile')) return '画像智能体'
  if (stage.includes('diagnosis') || stage.includes('planned')) return '规划智能体'
  if (stage.includes('safety')) return '审查智能体'
  if (stage.includes('knowledge')) return '知识图谱智能体'
  if (stage.includes('path')) return '路径智能体'
  if (stage === 'done') return '汇总智能体'
  return '资源智能体'
}

function formatStageData(data: any): string {
  if (typeof data === 'string') return data
  if (Array.isArray(data)) {
    return data.map((item) => {
      if (typeof item === 'string') return `- ${item}`
      const name = item.resource_type ? resourceTypeLabel(item.resource_type) : (item.stage || item.purpose || item.title || JSON.stringify(item))
      const desc = item.purpose || item.agent || ''
      return `- ${name}${desc ? `：${desc}` : ''}`
    }).join('\n')
  }
  if (data && typeof data === 'object') {
    const lines: string[] = []
    if (data.course_name) lines.push(`课程：${data.course_name}`)
    if (data.resource_type) lines.push(`资源类型：${resourceTypeLabel(data.resource_type)}`)
    if (data.title) lines.push(`标题：${data.title}`)
    if (Array.isArray(data.focus_knowledge_points)) lines.push(`重点知识点：${data.focus_knowledge_points.join('、')}`)
    if (Array.isArray(data.knowledge_points)) lines.push(`知识点：${data.knowledge_points.join('、')}`)
    if (data.resource_count !== undefined) lines.push(`资源数量：${data.resource_count}`)
    if (data.total_steps !== undefined) lines.push(`路径步骤：${data.total_steps}`)
    if (data.status) lines.push(`状态：${data.status}`)
    if (data.error) lines.push(`错误：${data.error}`)
    return lines.length ? lines.join('\n') : JSON.stringify(data, null, 2)
  }
  return String(data ?? '')
}

function resourceIcon(type: string): string {
  const map: Record<string, string> = {
    article: '📄',
    quiz: '📝',
    mindmap: '🧠',
    code: '💻',
    anime: '🎞️',
    ppt: '📊',
    ppt_session: '📊',
    video: '🎬',
    evaluation: '📈',
  }
  return map[type] || '📌'
}

function resourceTypeLabel(type: string): string {
  const map: Record<string, string> = {
    article: '文章',
    quiz: '题库',
    anime: '动画',
    mindmap: '思维导图',
    ppt: 'PPT课件',
    ppt_session: 'PPT课件',
    video: '视频',
    code: '代码',
    evaluation: '学习评估',
  }
  return map[type] || type
}

function resourceKey(resource: ResourceEvent, index: number): string {
  return String(resource.resource_id || resource.ppt_session?.session_id || `${resource.resource_type}-${index}`)
}

function resourceHref(resource: ResourceEvent): string {
  if (resource.ppt_session) {
    const session = resource.ppt_session || {}
    const params = new URLSearchParams()
    if (session.session_id && !session.pending_binding) params.set('session_id', session.session_id)
    if (session.topic) params.set('topic', session.topic)
    if (session.course_name) params.set('course', session.course_name)
    if (Array.isArray(session.knowledge_points) && session.knowledge_points.length) {
      params.set('kp', session.knowledge_points.join(','))
    }
    if (session.scope === 'extension') params.set('scope', 'extension')
    return `/ppt${params.toString() ? `?${params.toString()}` : ''}`
  }
  return resource.resource_id ? `/resources?open=${resource.resource_id}` : '/resources'
}

function resourceActionLabel(resource: ResourceEvent): string {
  return resource.ppt_session ? '进入 AiPPT 分步流程 →' : '查看 →'
}

function triggerWorkflow(action: WorkflowType, topic: string) {
  if (agentStore.isExecuting || isStreaming.value) return
  // 切换到任务模式执行工作流
  if (currentConvId.value) convModeMap.value[currentConvId.value] = 'task'

  const labelMap: Record<string, string> = { study: '系统学习', review: '分析错题', evaluation: '学习评估', video: '搜索视频' }
  const taskTitle = `${labelMap[action]}：${topic}`
  const convId = currentConvId.value!
  const task = agentStore.createTask(taskTitle)
  ;(task as any).convId = convId
  agentStore.setTaskStatus(task.id, 'running')
  agentStore.isExecuting = true
  taskMeta.value[task.id] = { resources: [] }
  const step_id = 'wf-' + task.id
  let fullContent = ''
  let stageSeq = 0

  workflowStream(
    action, userStore.userId, topic, currentHistory(),
    (chunk) => {
      fullContent += chunk
      agentStore.upsertStep(task.id, { stepId: step_id, stepType: 'result', status: 'running', title: taskTitle, data: { content: fullContent } as any, expanded: true, timestamp: Date.now() })
      scrollToBottom()
    },
    (stage, data) => {
      stageSeq += 1
      agentStore.upsertStep(task.id, {
        stepId: `wf-${task.id}-${stage}-${stageSeq}`,
        stepType: 'thinking',
        status: stage === 'resource_failed' ? 'error' : 'completed',
        title: stageTitle(stage),
        agentName: stageAgent(stage, data),
        data: { content: formatStageData(data) } as any,
        expanded: stage === 'resource_failed' || stage === 'done',
        timestamp: Date.now(),
      })
      scrollToBottom()
    },
    async () => {
      agentStore.isExecuting = false
      agentStore.setTaskStatus(task.id, 'completed')
      agentStore.upsertStep(task.id, { stepId: step_id, stepType: 'result', status: 'completed', title: taskTitle, data: { content: fullContent } as any, expanded: true, timestamp: Date.now() })
      parseSuggestions(task.id, fullContent)
      await saveMessage('assistant', fullContent)
      await loadConversations()
    },
    (err) => { agentStore.isExecuting = false; agentStore.setTaskStatus(task.id, 'completed'); ElMessage.error(`工作流失败：${err.message}`) },
    (resource) => {
      if (!taskMeta.value[task.id]) taskMeta.value[task.id] = {}
      const resources = taskMeta.value[task.id].resources || []
      const nextKey = resourceKey(resource, resources.length)
      if (!resources.some((r: ResourceEvent, i: number) => resourceKey(r, i) === nextKey)) {
        resources.push(resource)
        taskMeta.value[task.id].resources = resources
      }
    },
    (event) => { appendCollaborationEvent(task.id, event); scrollToBottom() },
  )
}
void triggerWorkflow

function queryText(value: unknown) {
  return Array.isArray(value) ? String(value[0] || '') : String(value || '')
}

function agentLaunchKey(q: string) {
  return [
    queryText(route.query.from) || 'unknown',
    queryText(route.query.t) || 'no-ts',
    q,
  ].join('|')
}

async function cleanAgentQuery() {
  if (Object.keys(route.query).length === 0) return
  try {
    await router.replace({ path: '/agent', query: {} })
  } catch {}
}

async function consumeAgentQuery(): Promise<boolean> {
  if (route.path !== '/agent') return false
  const q = queryText(route.query.q).trim()
  const autoSubmit = queryText(route.query.auto_submit) === '1'
  if (!q || !autoSubmit) {
    if (!q && queryText(route.query.from) === 'home') await cleanAgentQuery()
    return false
  }

  const key = agentLaunchKey(q)
  const consumedKey = `agent_home_launch_consumed:${key}`
  if (sessionStorage.getItem(consumedKey)) {
    await cleanAgentQuery()
    return false
  }
  if (isStreaming.value || agentStore.isExecuting) return true

  sessionStorage.setItem(consumedKey, '1')
  await cleanAgentQuery()
  await sendChatMessage({
    textOverride: q,
    forceNewConversation: true,
  })
  return true
}

// 提交入口：按当前模式路由
function handleSubmit() {
  if (currentMode.value === 'chat') sendChatMessage()
  else executeTask()
}

// Markdown 与术语渲染
function renderChatContent(content: string): string {
  let html = renderMarkdownEnhanced(stripSuggestionLines(content))
  html = html.replace(/\[\[(.+?)\]\]/g, (_m, term) => {
    const safe = escapeHtml(term)
    return `<span class="term-highlight" data-term="${safe}">${safe}</span>`
  })
  return html
}

interface TermCard {
  id: number
  term: string
  explanation: string
  loading: boolean
  x: number
  y: number
  zIndex: number
  error?: string
}
interface TermCacheItem { explanation: string; cached_at: string }

const termCards = ref<TermCard[]>([])
let termCardId = 0
let topTermZIndex = 10000
const TERM_CARD_WIDTH = 380
const TERM_CARD_HEIGHT = 420

let activeTermDrag: {
  id: number
  startX: number
  startY: number
  originX: number
  originY: number
} | null = null

function normalizeTerm(term: string) {
  return String(term || '').replace(/\s+/g, ' ').trim()
}

function termCacheKey() {
  return `term_explain_cache_v1:${userStore.userId || 'anonymous'}`
}

function readTermCache(): Record<string, TermCacheItem> {
  try {
    return JSON.parse(localStorage.getItem(termCacheKey()) || '{}')
  } catch {
    return {}
  }
}

function getCachedTermExplanation(term: string): string {
  return readTermCache()[normalizeTerm(term)]?.explanation || ''
}

function setCachedTermExplanation(term: string, explanation: string) {
  const key = normalizeTerm(term)
  if (!key || !explanation) return
  const cache = readTermCache()
  cache[key] = { explanation, cached_at: new Date().toISOString() }
  try {
    localStorage.setItem(termCacheKey(), JSON.stringify(cache))
  } catch {}
}

function cacheGlossary(glossary: Record<string, string>) {
  for (const [term, explanation] of Object.entries(glossary || {})) {
    setCachedTermExplanation(term, explanation)
  }
}

function lookupGlossary(glossary: Record<string, string> | undefined, term: string): string {
  const normalized = normalizeTerm(term)
  if (!glossary || !normalized) return ''
  for (const [key, value] of Object.entries(glossary)) {
    if (normalizeTerm(key) === normalized) return value
  }
  return ''
}

function clampTermCardPosition(x: number, y: number) {
  const maxX = Math.max(8, window.innerWidth - TERM_CARD_WIDTH - 12)
  const maxY = Math.max(8, window.innerHeight - TERM_CARD_HEIGHT - 12)
  return {
    x: Math.min(Math.max(8, x), maxX),
    y: Math.min(Math.max(8, y), maxY),
  }
}

function bringTermCardToFront(id: number) {
  const card = termCards.value.find(item => item.id === id)
  if (card) card.zIndex = ++topTermZIndex
}

function closeTermCard(id: number) {
  termCards.value = termCards.value.filter(item => item.id !== id)
}

function closeTopTermCard() {
  const top = [...termCards.value].sort((a, b) => b.zIndex - a.zIndex)[0]
  if (top) closeTermCard(top.id)
}

function renderTermExplanation(explanation: string) {
  return renderMarkdownEnhanced(explanation || '暂无解释')
}

async function explainTerm(term: string, x: number, y: number, glossary?: Record<string, string>) {
  const normalized = normalizeTerm(term)
  if (!normalized) return

  const existing = termCards.value.find(card => normalizeTerm(card.term) === normalized)
  if (existing) {
    bringTermCardToFront(existing.id)
    return
  }

  const pos = clampTermCardPosition(x + 12, y + 12)
  const glossaryExplanation = lookupGlossary(glossary, normalized)
  const cachedExplanation = glossaryExplanation || getCachedTermExplanation(normalized)
  const card: TermCard = {
    id: ++termCardId,
    term: normalized,
    explanation: cachedExplanation,
    loading: !cachedExplanation,
    x: pos.x,
    y: pos.y,
    zIndex: ++topTermZIndex,
  }
  termCards.value.push(card)

  if (cachedExplanation) {
    if (glossaryExplanation) setCachedTermExplanation(normalized, glossaryExplanation)
    return
  }

  try {
    const r = await api.post('/chat/explain-term', { term: normalized, user_id: userStore.userId, context: '' })
    const explanation = r.data.explanation || '暂无解释'
    card.explanation = explanation
    setCachedTermExplanation(normalized, explanation)
  } catch {
    card.error = '解释加载失败'
  } finally {
    card.loading = false
  }
}

function handleChatClick(e: MouseEvent, msg: ChatMsg) {
  const target = (e.target as HTMLElement).closest('.term-highlight') as HTMLElement | null
  if (target) {
    e.stopPropagation()
    explainTerm(target.dataset.term || '', e.clientX, e.clientY, msg.glossary)
  }
}

function startTermDrag(e: MouseEvent, card: TermCard) {
  bringTermCardToFront(card.id)
  activeTermDrag = {
    id: card.id,
    startX: e.clientX,
    startY: e.clientY,
    originX: card.x,
    originY: card.y,
  }
  window.addEventListener('mousemove', handleTermDrag)
  window.addEventListener('mouseup', stopTermDrag)
}

function handleTermDrag(e: MouseEvent) {
  if (!activeTermDrag) return
  const card = termCards.value.find(item => item.id === activeTermDrag?.id)
  if (!card) return
  const next = clampTermCardPosition(
    activeTermDrag.originX + e.clientX - activeTermDrag.startX,
    activeTermDrag.originY + e.clientY - activeTermDrag.startY,
  )
  card.x = next.x
  card.y = next.y
}

function stopTermDrag() {
  if (!activeTermDrag) return
  window.removeEventListener('mousemove', handleTermDrag)
  window.removeEventListener('mouseup', stopTermDrag)
  activeTermDrag = null
}

function handleTermKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') closeTopTermCard()
}

// 鈹€鈹€ 鍏朵粬宸ュ叿鍑芥暟 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

function handleRerun() {
  const task = currentTask.value
  if (!task || agentStore.isExecuting) return
  const match = task.title.match(/^\[.+?\]\s*(.+)$/)
  executeTask(match ? match[1] : task.title)
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.warning('文件不能超过 10MB')
    return
  }
  uploading.value = true
  try {
    const result = await uploadFile(file)
    if (result.ok) {
      uploadedFile.value = { fileName: result.file_name, content: result.content, size: result.size }
      ElMessage.success(`已读取 ${result.file_name}（${(result.size / 1024).toFixed(1)}KB）`)
    } else {
      ElMessage.error(result.error || '上传失败')
    }
  } catch {
    ElMessage.error('上传失败')
  } finally {
    uploading.value = false
    input.value = ''
  }
}

function clearFile() { uploadedFile.value = null }
function formatSize(b: number) {
  if (b < 1024) return b + 'B'
  if (b < 1048576) return (b / 1024).toFixed(1) + 'KB'
  return (b / 1048576).toFixed(1) + 'MB'
}
function formatConvTime(iso: string) {
  if (!iso) return ''
  const diffMin = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `${diffH}小时前`
  return `${Math.floor(diffH / 24)}天前`
}

function runDemoMode() {
  if (agentStore.isExecuting) return
  if (!currentConvId.value) {
    ElMessage.warning('请先创建会话')
    return
  }
  convModeMap.value[currentConvId.value] = 'task'
  const convId = currentConvId.value
  const task = agentStore.createTask('斐波那契数列跨学科分析')
  ;(task as any).convId = convId
  agentStore.setTaskStatus(task.id, 'running')
  agentStore.isExecuting = true
  runDemo(task.id, (step) => { agentStore.upsertStep(task.id, step); scrollToBottom() }, () => { agentStore.isExecuting = false; agentStore.setTaskStatus(task.id, 'completed') })
}

async function deleteTask(taskId: number) {
  const idx = agentStore.tasks.findIndex((t: any) => t.id === taskId)
  if (idx < 0) return
  agentStore.tasks.splice(idx, 1)
  if (agentStore.currentTaskId === taskId)
    agentStore.currentTaskId = currentConvTasks.value[0]?.id || null
}

async function clearAllTasks() {
  if (currentConvTasks.value.length === 0) return
  try {
    await ElMessageBox.confirm('清空当前会话的所有任务记录？', '确认', { type: 'warning' })
    const ids = new Set(currentConvTasks.value.map(t => t.id))
    agentStore.tasks.splice(0, agentStore.tasks.length, ...agentStore.tasks.filter((t: any) => !ids.has(t.id)))
    agentStore.currentTaskId = null
    ElMessage.success('已清空')
  } catch {}
}

const questionList = computed(() => {
  if (currentMode.value === 'chat') {
    return currentChatMsgs.value
      .filter(m => m.role === 'user')
      .map((m, i) => ({ label: m.content.slice(0, 30) + (m.content.length > 30 ? '...' : ''), idx: i }))
  }
  return currentConvTasks.value.map((t, i) => ({ label: t.title.slice(0, 30) + (t.title.length > 30 ? '...' : ''), id: t.id, idx: i }))
})

const questionPanelOpen = ref(false)
</script>

<template>
  <div class="agent-panel" :class="{ dark: themeStore.isDark }">
    <aside class="conv-sidebar">
      <div class="sidebar-header">
        <div class="sidebar-brand">
          <div class="brand-icon">AI</div>
          <div>
            <h3>智能助手</h3>
            <p>对话 / 多智能体任务</p>
          </div>
        </div>
        <el-button class="new-conv-btn" size="small" type="primary" @click="newConversation">+ 新建</el-button>
      </div>
      <div class="conv-list">
        <div
          v-for="c in conversations"
          :key="c.id"
          class="conv-item"
          :class="{ active: c.id === currentConvId }"
          @click="selectConversation(c.id)"
        >
          <div class="conv-item-title">{{ c.title }}</div>
          <div class="conv-item-meta">
            <span class="conv-item-time">{{ formatConvTime(c.updated_at) }}</span>
            <span class="conv-del-btn" @click.stop="deleteConversation(c.id, $event)">删除</span>
          </div>
        </div>
        <div v-if="conversations.length === 0" class="conv-empty">暂无会话，点击“新建”开始</div>
      </div>
    </aside>

    <main class="work-area">
      <header class="task-header">
        <div class="header-left title-block">
          <div class="assistant-avatar">✦</div>
          <div>
            <h2 v-if="currentConvId" class="conv-title-display">
              {{ conversations.find(c => c.id === currentConvId)?.title || '对话' }}
            </h2>
            <h2 v-else class="placeholder-title">AI 智能助手</h2>
            <p class="header-subtitle">
              {{ currentMode === 'chat' ? '问答辅导 · 术语解释 · 学习建议' : '任务编排 · 资源生成 · 过程追踪' }}
            </p>
          </div>
        </div>
        <div class="header-right">
          <div v-if="currentConvId" class="mode-switch">
            <button :class="['mode-btn', { active: currentMode === 'chat' }]" @click="setMode('chat')">💬 对话</button>
            <button :class="['mode-btn', { active: currentMode === 'task' }]" @click="setMode('task')">🤖 任务</button>
          </div>
          <template v-if="currentMode === 'task' && currentConvId">
            <el-button size="small" text @click="questionPanelOpen = !questionPanelOpen" title="任务列表">📋</el-button>
            <el-button size="small" @click="runDemoMode" :disabled="agentStore.isExecuting">演示</el-button>
            <el-button size="small" type="danger" plain @click="clearAllTasks" :disabled="currentConvTasks.length === 0">清空</el-button>
          </template>
          <el-button text @click="themeStore.toggle">{{ themeStore.isDark ? '☀️' : '🌙' }}</el-button>
          <el-button
            v-if="agentStore.isExecuting || isStreaming"
            type="danger"
            size="small"
            @click="agentStore.cancelExecution(); isStreaming = false"
          >停止</el-button>
        </div>
      </header>

      <div class="work-content">
        <div class="main-scroll" ref="mainContainer">
          <div v-if="!currentConvId" class="empty-state">
            <div class="empty-hero">
              <div class="empty-icon">🤖</div>
              <h3>开始一次个性化学习对话</h3>
              <p>创建会话后，可以直接提问，也可以切换到任务模式生成学习资源。</p>
              <button class="empty-primary-btn" @click="newConversation">创建新会话</button>
            </div>
          </div>

          <template v-else-if="currentMode === 'chat'">
            <div v-if="currentChatMsgs.length === 0" class="empty-state">
              <div class="empty-hero">
                <div class="empty-icon">💬</div>
                <h3>今天想解决什么学习问题？</h3>
                <p>AI 会结合你的学习画像、历史学习记录和知识图谱给出解释。</p>
                <div class="quick-prompts">
                  <button @click="inputText = '请根据我的学习画像，给我一个今天的学习建议'">今日学习建议</button>
                  <button @click="inputText = '帮我解释一个我容易混淆的知识点，并给出例题'">讲解薄弱知识点</button>
                  <button @click="inputText = '根据我的错题，总结我最近的易错原因'">分析易错原因</button>
                </div>
              </div>
            </div>
            <div v-for="msg in currentChatMsgs" :key="msg.uid" :class="['chat-msg', msg.role]">
              <div v-if="msg.role === 'assistant'" class="msg-avatar assistant-avatar-small">AI</div>
              <div class="chat-bubble" @click="msg.role === 'assistant' ? handleChatClick($event, msg) : undefined">
                <template v-if="msg.role === 'user'">{{ msg.content }}</template>
                <div v-else class="markdown-body" v-html="renderChatContent(msg.content)" />
                <span v-if="msg.role === 'assistant' && msg.streaming" class="cursor">|</span>
                <div
                  v-if="msg.role === 'assistant' && msg.handoff && !msg.handoff.dismissed"
                  class="chat-handoff-card"
                  @click.stop
                >
                  <div class="handoff-card-head">
                    <span class="handoff-badge">{{ msg.handoff.label }}</span>
                    <span class="handoff-note">需要任务模式</span>
                  </div>
                  <div class="handoff-task">{{ msg.handoff.taskText }}</div>
                  <div class="handoff-actions">
                    <button class="handoff-primary" :disabled="agentStore.isExecuting" @click.stop="runHandoffTask(msg)">
                      进入任务模式执行
                    </button>
                    <button class="handoff-secondary" @click.stop="dismissHandoff(msg)">
                      留在对话模式继续提问
                    </button>
                  </div>
                </div>
              </div>
              <div v-if="msg.role === 'user'" class="msg-avatar user-avatar-small">我</div>
            </div>
          </template>

          <template v-else>
            <div v-if="currentConvTasks.length === 0" class="empty-state">
              <div class="empty-hero">
                <div class="empty-icon">🤖</div>
                <h3>把复杂学习需求交给任务模式</h3>
                <p>输入目标后，系统会展示规划、生成和汇总过程。</p>
                <div class="quick-prompts">
                  <button @click="inputText = '围绕我当前薄弱知识点，生成一套学习资源包'">生成资源包</button>
                  <button @click="inputText = '为我规划一条本周学习路径，并说明顺序理由'">规划学习路径</button>
                  <button @click="inputText = '分析我的错题并生成针对性练习'">错题补弱任务</button>
                </div>
              </div>
            </div>
            <div v-if="currentConvTasks.length > 1" class="task-tabs">
              <div
                v-for="t in currentConvTasks"
                :key="t.id"
                class="task-tab"
                :class="{ active: t.id === (currentTask?.id) }"
                @click="agentStore.currentTaskId = t.id"
              >
                {{ t.title.slice(0, 20) }}{{ t.title.length > 20 ? '...' : '' }}
                <span class="tab-del" @click.stop="deleteTask(t.id)">×</span>
              </div>
            </div>
            <AgentTimeline
              v-if="currentTask"
              :steps="currentTask.steps"
              :is-executing="agentStore.isExecuting"
              @rerun="handleRerun"
            />
            <div v-if="currentTask && taskMeta[currentTask.id]?.resources?.length" class="resource-area">
              <div v-for="(r, i) in taskMeta[currentTask.id].resources" :key="resourceKey(r, i)" class="resource-card-inline">
                <span>{{ resourceIcon(r.resource_type) }} {{ resourceTypeLabel(r.resource_type) }} · {{ r.title || '学习资源' }}</span>
                <a :href="resourceHref(r)" class="resource-jump">{{ resourceActionLabel(r) }}</a>
              </div>
            </div>
          </template>
        </div>

        <aside v-if="questionPanelOpen && currentMode === 'task'" class="question-panel">
          <div class="qp-header">
            <span>任务列表</span>
            <span class="qp-close" @click="questionPanelOpen = false">×</span>
          </div>
          <div class="qp-list">
            <div
              v-for="(q, i) in questionList"
              :key="i"
              class="qp-item"
              :class="{ active: (q as any).id === currentTask?.id }"
              @click="agentStore.currentTaskId = (q as any).id"
            >
              <span class="qp-badge">{{ i + 1 }}</span>
              <span class="qp-text">{{ q.label }}</span>
            </div>
            <div v-if="questionList.length === 0" class="qp-empty">暂无任务</div>
          </div>
        </aside>
      </div>

      <div class="input-area">
        <div class="input-hint">
          <span>{{ currentMode === 'chat' ? '对话模式：适合概念解释、答疑、学习建议' : '任务模式：适合生成资源、分析错题、规划路径' }}</span>
          <span class="input-hotkey">Enter 发送 · Shift + Enter 换行</span>
        </div>
        <div v-if="uploadedFile" class="file-preview">
          <span class="file-name">📄 {{ uploadedFile.fileName }}</span>
          <span class="file-size">{{ formatSize(uploadedFile.size) }}</span>
          <el-button size="small" text @click="clearFile">×</el-button>
        </div>
        <div class="input-row">
          <label v-if="currentMode === 'task'" class="upload-btn" :class="{ disabled: agentStore.isExecuting }">
            <input
              type="file"
              accept=".txt,.md,.pdf,.json,.csv,.xml,.yaml,.yml,.py,.js,.ts,.java,.c,.cpp,.rs,.go,.log"
              @change="handleFileChange"
              :disabled="agentStore.isExecuting"
            />
            <span v-if="uploading">⏳</span><span v-else>📎</span>
          </label>
          <el-input
            v-model="inputText"
            type="textarea"
            :rows="2"
            :placeholder="currentMode === 'chat' ? '输入问题，Enter 发送...' : (uploadedFile ? '输入任务描述...' : '描述任务，如：分析离散数学在 AI 领域的应用...')"
            :disabled="agentStore.isExecuting || isStreaming"
            @keydown.enter.exact.prevent="handleSubmit"
          />
          <el-button
            type="primary"
            :disabled="(!inputText.trim() && !uploadedFile) || agentStore.isExecuting || isStreaming"
            :loading="agentStore.isExecuting || isStreaming"
            @click="handleSubmit"
          >
            {{ currentMode === 'chat' ? '发送' : '执行' }}
          </el-button>
        </div>
      </div>
    </main>
  </div>

  <Teleport to="body">
    <div
      v-for="card in termCards"
      :key="card.id"
      class="term-popover"
      :style="{ left: card.x + 'px', top: card.y + 'px', zIndex: card.zIndex }"
      @mousedown="bringTermCardToFront(card.id)"
      @click.stop
    >
      <div class="popover-header" @mousedown.prevent="startTermDrag($event, card)">
        <span class="popover-term">{{ card.term }}</span>
        <span class="popover-close" @mousedown.stop @click.stop="closeTermCard(card.id)">×</span>
      </div>
      <div class="popover-body">
        <span v-if="card.loading">加载中...</span>
        <span v-else-if="card.error" class="popover-error">{{ card.error }}</span>
        <div v-else class="markdown-body" v-html="renderTermExplanation(card.explanation)" />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.agent-panel {
  display: flex;
  height: 100%;
  flex: 1;
  background:
    radial-gradient(circle at 18% 8%, rgba(249, 217, 184, 0.75), transparent 28%),
    radial-gradient(circle at 92% 12%, rgba(232, 194, 156, 0.32), transparent 26%),
    linear-gradient(180deg, #FFF5EB 0%, #FFFBF5 58%, #FFF5EB 100%);
  overflow: hidden;
  padding: 14px;
  gap: 14px;
  box-sizing: border-box;
}
.agent-panel.dark { background: var(--bg-page); color: var(--text-regular); }

/* 鈹€鈹€ 渚ц竟鏍?鈹€鈹€ */
.conv-sidebar {
  width: 276px; min-width: 276px;
  background: rgba(255, 251, 245, 0.9);
  border: 1px solid rgba(232, 194, 156, 0.75);
  border-radius: 22px;
  box-shadow: 0 16px 48px rgba(58, 51, 46, 0.10);
  backdrop-filter: blur(14px);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.sidebar-header {
  padding: 18px;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid rgba(239, 230, 220, 0.85);
  flex-shrink: 0;
  gap: 12px;
}
.sidebar-brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
.brand-icon {
  width: 36px; height: 36px; border-radius: 13px;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #3A332E, #7C5C3C);
  color: #FFFBF5; font-size: 13px; font-weight: 800; letter-spacing: 0.04em;
  box-shadow: 0 8px 18px rgba(58, 51, 46, 0.18);
  flex-shrink: 0;
}
.sidebar-header h3 { margin: 0; font-size: 16px; font-weight: 700; color: #3A332E; }
.sidebar-header p { margin: 2px 0 0; color: #948A80; font-size: 11px; white-space: nowrap; }
.new-conv-btn { border-radius: 999px; box-shadow: 0 8px 16px rgba(64, 158, 255, 0.18); }
.conv-list { flex: 1; overflow-y: auto; padding: 12px; }
.conv-item {
  padding: 12px 13px;
  border-radius: 16px;
  cursor: pointer;
  margin-bottom: 8px;
  transition: all 0.25s cubic-bezier(.4,0,.2,1);
  border: 1px solid transparent;
  background: rgba(255, 245, 235, 0.58);
}
.conv-item:hover { background: #FFFBF5; transform: translateY(-2px); box-shadow: 0 8px 20px rgba(58,51,46,0.09); }
.conv-item.active { background: #FFFBF5; border-color: #E8C29C; box-shadow: 0 10px 24px rgba(58,51,46,0.10); }
.conv-item-title { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 4px; color: #3A332E; }
.conv-item-meta { display: flex; align-items: center; justify-content: space-between; }
.conv-item-time { font-size: 11px; color: #948A80; }
.conv-del-btn { font-size: 12px; cursor: pointer; opacity: 0; color: #948A80; transition: all 0.25s; padding: 2px 5px; border-radius: 6px; }
.conv-item:hover .conv-del-btn { opacity: 1; }
.conv-del-btn:hover { color: var(--color-danger); background: var(--color-danger-bg); }
.conv-empty {
  text-align: center; padding: 48px 16px; color: #948A80; font-size: 13px; line-height: 2;
}

/* 鈹€鈹€ 涓诲尯鍩?鈹€鈹€ */
.work-area {
  flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0;
  background: rgba(255, 251, 245, 0.76);
  border: 1px solid rgba(232, 194, 156, 0.72);
  border-radius: 24px;
  box-shadow: 0 18px 52px rgba(58, 51, 46, 0.11);
  backdrop-filter: blur(14px);
}
.work-content { flex: 1; display: flex; overflow: hidden; }

.task-header {
  padding: 16px 22px;
  background: linear-gradient(135deg, rgba(255, 251, 245, 0.94), rgba(255, 245, 235, 0.82));
  border-bottom: 1px solid rgba(239, 230, 220, 0.9);
  display: flex; align-items: center; justify-content: space-between;
  flex-shrink: 0; min-height: 68px;
}
.header-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
.title-block { gap: 12px; }
.assistant-avatar {
  width: 42px; height: 42px; border-radius: 16px;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #F9D9B8, #E8C29C);
  color: #3A332E; font-size: 18px; font-weight: 800;
  box-shadow: 0 10px 22px rgba(219, 168, 120, 0.25);
  flex-shrink: 0;
}
.conv-title-display { margin: 0; font-size: 16px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #3A332E; }
.placeholder-title { margin: 0; font-size: 16px; color: #948A80; }
.header-subtitle { margin: 3px 0 0; color: #948A80; font-size: 12px; }
.header-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

.mode-switch { display: flex; background: rgba(255, 245, 235, 0.8); border-radius: 999px; padding: 4px; gap: 3px; border: 1px solid #EFE6DC; }
.mode-btn {
  padding: 7px 16px; border: none; border-radius: 999px;
  cursor: pointer; font-size: 13px; color: #948A80;
  background: transparent; transition: all 0.25s cubic-bezier(.4,0,.2,1); white-space: nowrap;
}
.mode-btn.active { background: #FFFBF5; color: #3A332E; box-shadow: 0 6px 14px rgba(58,51,46,0.10); font-weight: 700; }
.mode-btn:hover:not(.active) { color: #3A332E; background: rgba(249,217,184,0.3); }

/* 鈹€鈹€ 鍐呭婊氬姩鍖?鈹€鈹€ */
.main-scroll { flex: 1; overflow-y: auto; padding: 28px 34px; display: flex; flex-direction: column; gap: 18px; scroll-behavior: smooth; }
.main-scroll::-webkit-scrollbar, .conv-list::-webkit-scrollbar { width: 8px; }
.main-scroll::-webkit-scrollbar-thumb, .conv-list::-webkit-scrollbar-thumb { background: rgba(199, 179, 154, 0.7); border-radius: 999px; }
.main-scroll::-webkit-scrollbar-track, .conv-list::-webkit-scrollbar-track { background: transparent; }

/* 鈹€鈹€ 绌虹姸鎬?鈹€鈹€ */
.empty-state { flex: 1; display: flex; align-items: center; justify-content: center; color: #948A80; padding: 48px 0; }
.empty-hero {
  width: min(620px, 100%);
  padding: 38px 36px;
  border: 1px solid rgba(232, 194, 156, 0.65);
  border-radius: 26px;
  background:
    radial-gradient(circle at 14% 12%, rgba(249, 217, 184, 0.38), transparent 30%),
    linear-gradient(135deg, rgba(255, 251, 245, 0.96), rgba(255, 245, 235, 0.82));
  box-shadow: 0 18px 52px rgba(58, 51, 46, 0.09);
  text-align: center;
}
.empty-icon {
  width: 72px; height: 72px; margin: 0 auto 14px;
  display: flex; align-items: center; justify-content: center;
  font-size: 38px; border-radius: 24px;
  background: #FFFBF5;
  box-shadow: 0 10px 26px rgba(58, 51, 46, 0.09);
}
.empty-state h3 { margin: 0 0 8px; color: #3A332E; font-size: 22px; font-weight: 800; }
.empty-state p { font-size: 14px; color: #6B635C; margin: 0; line-height: 1.8; }
.quick-prompts {
  display: flex; flex-wrap: wrap; justify-content: center; gap: 10px;
  margin-top: 22px;
}
.quick-prompts button,
.empty-primary-btn {
  border: 1px solid #E8C29C;
  background: #FFFBF5;
  color: #7C5C3C;
  border-radius: 999px;
  padding: 9px 16px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.quick-prompts button:hover,
.empty-primary-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 18px rgba(58,51,46,0.10);
  border-color: #DBA878;
  color: #3A332E;
}
.empty-primary-btn { margin-top: 20px; background: linear-gradient(135deg, #F9D9B8, #E8C29C); font-weight: 700; }

/* 鈹€鈹€ 瀵硅瘽姘旀场 鈹€鈹€ */
.chat-msg { display: flex; align-items: flex-start; gap: 10px; animation: fadeIn 0.3s cubic-bezier(.4,0,.2,1); }
.chat-msg.user { justify-content: flex-end; }
.chat-msg.assistant { justify-content: flex-start; }
.msg-avatar {
  width: 32px; height: 32px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 800; flex-shrink: 0;
  box-shadow: 0 6px 14px rgba(58,51,46,0.09);
}
.assistant-avatar-small { background: linear-gradient(135deg, #3A332E, #7C5C3C); color: #FFFBF5; }
.user-avatar-small { background: linear-gradient(135deg, #F9D9B8, #E8C29C); color: #3A332E; }
.chat-bubble {
  max-width: min(760px, 72%); padding: 13px 17px;
  border-radius: 18px;
  font-size: 14px; line-height: 1.7; word-break: break-word;
}
.chat-msg.user .chat-bubble {
  background: linear-gradient(135deg, #F9D9B8, #E8C29C); color: #3A332E;
  border-bottom-right-radius: 6px;
  white-space: pre-wrap;
  box-shadow: 0 10px 24px rgba(58,51,46,0.11);
}
.chat-msg.assistant .chat-bubble {
  background: rgba(255, 251, 245, 0.96); border: 1px solid #EFE6DC;
  border-bottom-left-radius: 6px;
  box-shadow: 0 10px 24px rgba(58,51,46,0.08);
  animation: bubbleFadeUp 0.3s cubic-bezier(.4,0,.2,1);
}
.chat-handoff-card {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid rgba(232, 194, 156, 0.92);
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(255, 245, 235, 0.94), rgba(255, 251, 245, 0.98));
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.65);
}
.handoff-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}
.handoff-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 3px 10px;
  background: #F9D9B8;
  color: #7C5C3C;
  font-size: 12px;
  font-weight: 700;
}
.handoff-note {
  color: #948A80;
  font-size: 12px;
}
.handoff-task {
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(255, 251, 245, 0.9);
  border: 1px solid #EFE6DC;
  color: #3A332E;
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 10px;
}
.handoff-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.handoff-primary,
.handoff-secondary {
  border: 1px solid #E8C29C;
  border-radius: 999px;
  padding: 7px 13px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.handoff-primary {
  background: linear-gradient(135deg, #F9D9B8, #E8C29C);
  color: #3A332E;
  font-weight: 700;
}
.handoff-secondary {
  background: #FFFBF5;
  color: #7C5C3C;
}
.handoff-primary:hover:not(:disabled),
.handoff-secondary:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 14px rgba(58,51,46,0.10);
}
.handoff-primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.cursor { animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }
@keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
@keyframes bubbleFadeUp { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

/* 鈹€鈹€ 浠诲姟鏍囩 鈹€鈹€ */
.task-tabs { display: flex; flex-wrap: wrap; gap: 8px; padding-bottom: 16px; border-bottom: 1px solid #EFE6DC; }
.task-tab {
  padding: 5px 12px; border-radius: 8px; border: 1px solid #EFE6DC;
  font-size: 12px; cursor: pointer; background: #FFFBF5;
  display: flex; align-items: center; gap: 6px;
  transition: all 0.25s cubic-bezier(.4,0,.2,1); color: #6B635C;
}
.task-tab:hover { border-color: #E8C29C; background: #FFF5EB; }
.task-tab.active { background: #FFF5EB; border-color: #F9D9B8; color: #3A332E; font-weight: 500; }
.tab-del { color: #948A80; font-size: 11px; }
.tab-del:hover { color: var(--color-danger); }

/* 鈹€鈹€ 寤鸿鎸夐挳 鈹€鈹€ */
.suggestion-area { display: flex; flex-wrap: wrap; gap: 8px; padding: 8px 0; }
.suggestion-btn {
  background: linear-gradient(135deg, #F9D9B8 0%, #E8C29C 100%);
  color: #3A332E; border: none; border-radius: 20px;
  padding: 8px 18px; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all 0.25s cubic-bezier(.4,0,.2,1);
  box-shadow: 0 2px 6px rgba(58,51,46,0.10);
}
.suggestion-btn:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(58,51,46,0.15); }
.suggestion-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.resource-area { display: flex; flex-wrap: wrap; gap: 8px; }
.resource-card-inline {
  display: flex; align-items: center; gap: 8px;
  background: #FFFBF5; border: 1px solid #EFE6DC;
  border-radius: 8px; padding: 8px 14px; font-size: 13px;
  transition: all 0.25s;
}
.resource-card-inline:hover { border-color: #E8C29C; background: #FFF5EB; }
.resource-jump { color: #DBA878; text-decoration: none; font-size: 12px; font-weight: 500; }
.resource-jump:hover { text-decoration: underline; }

/* 鈹€鈹€ 浠诲姟鍒楄〃闈㈡澘 鈹€鈹€ */
.question-panel { width: 220px; min-width: 220px; background: #FFFBF5; border-left: 1px solid #EFE6DC; display: flex; flex-direction: column; overflow: hidden; }
.qp-header { display: flex; align-items: center; justify-content: space-between; padding: 14px; border-bottom: 1px solid #EFE6DC; font-size: 13px; font-weight: 600; color: #3A332E; }
.qp-close { cursor: pointer; color: #948A80; font-size: 14px; padding: 2px 6px; border-radius: 6px; transition: all 0.2s; }
.qp-close:hover { color: var(--color-danger); background: var(--color-danger-bg); }
.qp-list { flex: 1; overflow-y: auto; padding: 8px; }
.qp-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 8px; cursor: pointer; margin-bottom: 3px; transition: background 0.2s; }
.qp-item:hover { background: #FFF5EB; }
.qp-item.active { background: #FFF5EB; border-left: 2px solid #F9D9B8; }
.qp-badge { width: 20px; height: 20px; border-radius: 50%; background: #F9D9B8; color: #3A332E; font-size: 10px; font-weight: 600; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.qp-text { font-size: 12px; color: #6B635C; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.qp-empty { text-align: center; padding: 24px 16px; color: #948A80; font-size: 12px; }

/* 鈹€鈹€ 杈撳叆鍖?鈹€鈹€ */
.input-area {
  padding: 12px 22px 18px;
  background: rgba(255, 251, 245, 0.94);
  border-top: 1px solid rgba(239, 230, 220, 0.9);
  display: flex; flex-direction: column; gap: 8px;
  flex-shrink: 0;
}
.input-hint {
  display: flex; justify-content: space-between; gap: 12px;
  color: #948A80; font-size: 12px; padding: 0 2px;
}
.input-hotkey { white-space: nowrap; }
.input-row {
  display: flex; gap: 10px; align-items: flex-end;
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 18px;
  padding: 10px;
  box-shadow: 0 10px 28px rgba(58, 51, 46, 0.08);
}
.file-preview {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px; background: #FFF5EB;
  border-radius: 8px; font-size: 12px; border: 1px solid #F9D9B8;
}
.file-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; color: #6B635C; }
.file-size { color: #948A80; flex-shrink: 0; }
.upload-btn {
  display: flex; align-items: center; justify-content: center;
  width: 42px; height: 42px; cursor: pointer;
  border: 1px solid #EFE6DC; border-radius: 14px;
  background: #FFFBF5; font-size: 16px; flex-shrink: 0;
  transition: all 0.25s cubic-bezier(.4,0,.2,1);
}
.upload-btn:hover { border-color: #E8C29C; background: #FFF5EB; transform: translateY(-1px); }
.upload-btn.disabled { cursor: not-allowed; opacity: 0.4; }
.upload-btn input { display: none; }
.input-row :deep(.el-textarea__inner) {
  min-height: 44px !important;
  border: none;
  box-shadow: none;
  background: transparent;
  color: #3A332E;
  resize: none;
  padding: 8px 10px;
}
.input-row :deep(.el-textarea__inner::placeholder) { color: #B0A296; }
.input-row :deep(.el-button) {
  min-width: 86px;
  height: 42px;
  border-radius: 14px;
  font-weight: 700;
}

/* 鈹€鈹€ 姘旀场鍐?Markdown 鈹€鈹€ */
.chat-bubble .markdown-body { white-space: normal; }
.chat-bubble :deep(.term-highlight) { color: #DBA878; font-weight: 600; cursor: pointer; border-bottom: 1px dashed #DBA878; transition: all 0.2s; }
.chat-bubble :deep(.term-highlight:hover) { background: #FFF5EB; border-radius: 2px; }
.chat-bubble :deep(p) { margin: 4px 0; }
.chat-bubble :deep(pre) { background: #FFF5EB; border-radius: 6px; padding: 10px; overflow-x: auto; font-size: 12px; border: 1px solid #EFE6DC; }
.chat-bubble :deep(code) { font-family: var(--font-mono); }
.chat-bubble :deep(ul), .chat-bubble :deep(ol) { padding-left: 20px; margin: 4px 0; }
.chat-bubble :deep(.markdown-table-wrap) { width: 100%; overflow-x: auto; margin: 10px 0; border: 1px solid #EFE6DC; border-radius: 10px; }
.chat-bubble :deep(table) { width: 100%; min-width: 480px; border-collapse: collapse; background: #FFFBF5; }
.chat-bubble :deep(th), .chat-bubble :deep(td) { padding: 8px 10px; border-bottom: 1px solid #EFE6DC; text-align: left; vertical-align: top; }
.chat-bubble :deep(th) { background: #FFF5EB; color: #3A332E; font-weight: 700; }
.chat-bubble :deep(tr:last-child td) { border-bottom: none; }
.chat-bubble :deep(.katex-display) { overflow-x: auto; overflow-y: hidden; padding: 6px 0; }

/* 鈹€鈹€ 瑙嗛鍗＄墖 鈹€鈹€ */
.chat-bubble :deep(.video-results) { display: flex; flex-direction: column; gap: 12px; margin: 10px 0; }
.chat-bubble :deep(.video-results-header) { font-weight: 600; font-size: 14px; color: #3A332E; margin-bottom: 2px; }
.chat-bubble :deep(.video-card) { display: block; background: #FFFBF5; border: 1px solid #EFE6DC; border-radius: 12px; overflow: hidden; text-decoration: none; color: inherit; transition: all 0.25s; }
.chat-bubble :deep(.video-card:hover) { transform: translateY(-2px); box-shadow: 0 4px 14px rgba(58,51,46,0.10); border-color: #E8C29C; }
.chat-bubble :deep(.video-cover) { position: relative; width: 100%; padding-top: 56.25%; background: #FFF5EB; overflow: hidden; }
.chat-bubble :deep(.video-cover img) { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; }
.chat-bubble :deep(.video-duration) { position: absolute; bottom: 6px; right: 6px; background: rgba(58,51,46,0.75); color: #FFFBF5; font-size: 11px; padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono); }
.chat-bubble :deep(.video-info) { padding: 8px 12px 10px; }
.chat-bubble :deep(.video-title) { font-size: 13px; font-weight: 500; line-height: 1.4; color: #3A332E; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis; margin-bottom: 6px; }
.chat-bubble :deep(.video-meta) { display: flex; align-items: center; gap: 8px; font-size: 11px; color: #948A80; }
.chat-bubble :deep(.meta-author) { max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; color: #6B635C; }
.chat-bubble :deep(.meta-play) { white-space: nowrap; }

/* 鈹€鈹€ 鏈寮圭獥 鈹€鈹€ */
.term-popover {
  position: fixed;
  background: #FFFBF5; border: 1px solid #EFE6DC;
  border-radius: 12px; box-shadow: 0 8px 24px rgba(58,51,46,0.12);
  width: 380px;
  max-width: calc(100vw - 24px);
  max-height: 420px;
  display: flex;
  flex-direction: column;
  animation: popFadeIn 0.2s cubic-bezier(.4,0,.2,1);
}
@keyframes popFadeIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
.popover-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-bottom: 1px solid #EFE6DC; cursor: move; user-select: none; flex-shrink: 0; }
.popover-term { font-weight: 600; color: #DBA878; font-size: 14px; }
.popover-close { cursor: pointer; color: #948A80; font-size: 14px; padding: 2px 6px; border-radius: 6px; transition: all 0.2s; }
.popover-close:hover { color: var(--color-danger); }
.popover-body { padding: 12px 14px; font-size: 13px; color: #6B635C; line-height: 1.6; overflow: auto; min-height: 80px; }
.popover-error { color: var(--color-danger); }
.popover-body :deep(.markdown-body) { color: #6B635C; line-height: 1.7; }
.popover-body :deep(.markdown-body p) { margin: 4px 0 8px; }
.popover-body :deep(.markdown-body ul), .popover-body :deep(.markdown-body ol) { margin: 6px 0; padding-left: 20px; }
.popover-body :deep(.markdown-body strong) { color: #3A332E; }
.popover-body :deep(.markdown-table-wrap) { max-width: 100%; overflow-x: auto; }
.popover-body :deep(pre) { background: #FFF5EB; border: 1px solid #EFE6DC; border-radius: 8px; padding: 8px; overflow-x: auto; }

@media (max-width: 1024px) {
  .agent-panel { flex-direction: column; height: auto; min-height: calc(100vh - 48px); overflow-y: auto; }
  .conv-sidebar { width: 100%; min-width: 0; max-height: 260px; }
  .work-area { min-height: 640px; }
}

@media (max-width: 720px) {
  .agent-panel { padding: 10px; gap: 10px; }
  .task-header { align-items: flex-start; flex-direction: column; gap: 12px; }
  .header-right { width: 100%; justify-content: space-between; flex-wrap: wrap; }
  .main-scroll { padding: 18px 14px; }
  .chat-bubble { max-width: calc(100vw - 120px); }
  .input-hint { flex-direction: column; gap: 2px; }
  .input-row { align-items: stretch; }
  .input-row :deep(.el-button) { min-width: 70px; }
}
</style>



