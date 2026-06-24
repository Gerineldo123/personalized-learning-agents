<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted, provide } from 'vue'
import { useUserStore } from '../stores/user'
import { useAgentStore } from '../stores/agent'
import { useThemeStore } from '../stores/theme'
import { agentExecuteStream, uploadFile } from '../api/agent'
import { chatStream } from '../api/chat'
import { workflowStream, type WorkflowType } from '../api/workflow'
import type { ResourceEvent } from '../api/workflow'
import { runDemo } from '../mock/agentDemo'
import type { AgentStep, StepEvent, UploadedFile } from '../types/agent'
import AgentTimeline from '../components/agent/AgentTimeline.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { renderMarkdownEnhanced, escapeHtml } from '../utils/markdown'

const userStore = useUserStore()
const agentStore = useAgentStore()
const themeStore = useThemeStore()

onMounted(() => {
  if (!userStore.userId) userStore.setUserId('user_' + Date.now())
  provide('userId', userStore.userId)
  loadConversations()
  document.addEventListener('click', handleDocumentClick)
})
onUnmounted(() => document.removeEventListener('click', handleDocumentClick))

// ── 状态 ──────────────────────────────────────────
const inputText = ref('')
const mainContainer = ref<HTMLElement | null>(null)
const uploadedFile = ref<UploadedFile | null>(null)
const uploading = ref(false)

// ── 会话管理 ──────────────────────────────────────
interface ConvItem { id: number; title: string; updated_at: string }
const conversations = ref<ConvItem[]>([])
const currentConvId = ref<number | null>(null)
// convId -> history messages
const historyMap = ref<Record<number, { role: string; content: string }[]>>({})
// convId -> mode ('chat' | 'task')
const convModeMap = ref<Record<number, 'chat' | 'task'>>({})
// convId -> chat messages (对话模式)
interface ChatMsg { role: 'user' | 'assistant'; content: string; streaming?: boolean; uid: number }
const chatMsgMap = ref<Record<number, ChatMsg[]>>({})
let msgUid = 0

const currentMode = computed(() => currentConvId.value ? (convModeMap.value[currentConvId.value] || 'chat') : 'chat')
const currentChatMsgs = computed(() => currentConvId.value ? (chatMsgMap.value[currentConvId.value] || []) : [])
// 只显示当前会话的任务
const currentConvTasks = computed(() =>
  agentStore.tasks.filter((t: any) => t.convId === currentConvId.value)
)
const currentTask = computed(() =>
  currentConvTasks.value.find(t => t.id === agentStore.currentTaskId) || currentConvTasks.value[0] || null
)

async function loadConversations() {
  try {
    const r = await api.get('/conversations', { params: { user_id: userStore.userId } })
    conversations.value = r.data.items || []
  } catch {}
}

async function newConversation() {
  try {
    const r = await api.post('/conversations', null, { params: { user_id: userStore.userId, title: '新对话' } })
    currentConvId.value = r.data.id
    historyMap.value[r.data.id] = []
    chatMsgMap.value[r.data.id] = []
    convModeMap.value[r.data.id] = 'chat'
    await loadConversations()
  } catch { ElMessage.error('创建对话失败') }
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

// ── TaskMeta ([建议] 和 资源) ─────────────────────
interface TaskMeta {
  suggestions?: Array<{ text: string; action: WorkflowType | null; topic: string }>
  resources?: ResourceEvent[]
}
const taskMeta = ref<Record<number, TaskMeta>>({})

function parseSuggestions(taskId: number, content: string) {
  const suggestions: TaskMeta['suggestions'] = []
  const re = /\[建议\]\s*(.+)/g
  let m
  while ((m = re.exec(content)) !== null) {
    const text = m[1].trim()
    const topic = (text.match(/【(.+?)】/) || [])[1] || text
    const action: WorkflowType | null = text.includes('分析错题') ? 'review'
      : text.includes('学习评估') ? 'evaluation'
      : text.includes('搜索视频') ? 'video'
      : text.includes('系统学习') ? 'study' : null
    suggestions.push({ text, action, topic })
  }
  if (!taskMeta.value[taskId]) taskMeta.value[taskId] = {}
  taskMeta.value[taskId].suggestions = suggestions
}

// ── 滚动 ──────────────────────────────────────────
function scrollToBottom() {
  nextTick(() => { if (mainContainer.value) mainContainer.value.scrollTop = mainContainer.value.scrollHeight })
}

// ── 对话模式发送 ──────────────────────────────────
const isStreaming = ref(false)

async function sendChatMessage() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value || agentStore.isExecuting) return

  // 检测资源查找意图，提示切换任务模式
  const resourceIntent = /搜索|查找|找.*资源|生成.*资源|推荐.*视频|搜.*视频|学习资源|系统学习|分析错题|学习评估|制作.*思维导图|生成.*题库|出题/.test(text)
  if (resourceIntent) {
    try {
      await ElMessageBox.confirm(
        '该需求适合使用「任务模式」，Agent 会自动生成学习资源（文章、题库、思维导图等）。是否切换？',
        '切换到任务模式',
        { confirmButtonText: '切换并执行', cancelButtonText: '继续对话', type: 'info' }
      )
      setMode('task')
      await executeTask(text)
      inputText.value = ''
      return
    } catch {
      // 用户选择继续对话，不拦截
    }
  }

  if (!currentConvId.value) await newConversation()
  inputText.value = ''

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
    (chunk) => { msgs[aiIdx].content += chunk; scrollToBottom() },
    async () => {
      msgs[aiIdx].streaming = false
      isStreaming.value = false
      const finalContent = msgs[aiIdx].content
      await saveMessage('assistant', finalContent)
      await loadConversations()
      try {
        const r = await api.post('/chat/mark-terms', { text: finalContent })
        const marked = r.data.marked_text
        if (marked && marked !== finalContent) msgs[aiIdx].content = marked
      } catch {}
    },
    (err) => { msgs[aiIdx].content = `[错误] ${err.message}`; msgs[aiIdx].streaming = false; isStreaming.value = false },
  )
}

// ── 任务模式执行 ──────────────────────────────────
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

  await saveMessage('user', text)
  const history = currentHistory()

  const ctrl = agentExecuteStream(
    userStore.userId, text,
    (evt) => handleStepEvent(evt, task.id),
    async () => {
      agentStore.isExecuting = false
      agentStore.setTaskStatus(task.id, 'completed')
      const resultStep = agentStore.tasks.find((t: any) => t.id === task.id)?.steps.find((s: any) => s.stepType === 'result')
      if (resultStep) {
        await saveMessage('assistant', (resultStep.data as any)?.content || '')
        await loadConversations()
      }
    },
    (err) => { console.error(err); agentStore.isExecuting = false; agentStore.setTaskStatus(task.id, 'completed') },
    uploadedFile.value?.content, uploadedFile.value?.fileName, history,
    (stepId, delta) => { agentStore.appendStepContent(task.id, stepId, delta); scrollToBottom() },
  )
  agentStore.setAbortController(ctrl)
  uploadedFile.value = null
  scrollToBottom()
}

function handleStepEvent(evt: StepEvent, taskId: number) {
  const step: AgentStep = {
    stepId: evt.step_id, stepType: evt.step_type, status: evt.status,
    title: evt.title, agentName: evt.agent_name, data: evt.data as AgentStep['data'],
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

// ── 工作流触发 ────────────────────────────────────
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

  workflowStream(
    action, userStore.userId, topic, currentHistory(),
    (chunk) => {
      fullContent += chunk
      agentStore.upsertStep(task.id, { stepId: step_id, stepType: 'result', status: 'running', title: taskTitle, data: { content: fullContent } as any, expanded: true, timestamp: Date.now() })
      scrollToBottom()
    },
    (_stage) => {},
    async () => {
      agentStore.isExecuting = false
      agentStore.setTaskStatus(task.id, 'completed')
      agentStore.upsertStep(task.id, { stepId: step_id, stepType: 'result', status: 'completed', title: taskTitle, data: { content: fullContent } as any, expanded: true, timestamp: Date.now() })
      parseSuggestions(task.id, fullContent)
      await saveMessage('assistant', fullContent)
      await loadConversations()
    },
    (err) => { agentStore.isExecuting = false; agentStore.setTaskStatus(task.id, 'completed'); ElMessage.error(`工作流失败: ${err.message}`) },
    (resource) => {
      if (!taskMeta.value[task.id]) taskMeta.value[task.id] = {}
      const resources = taskMeta.value[task.id].resources || []
      if (!resources.some((r: ResourceEvent) => r.resource_id === resource.resource_id)) {
        resources.push(resource)
        taskMeta.value[task.id].resources = resources
      }
    },
  )
}

// ── 提交入口（按模式路由）────────────────────────
function handleSubmit() {
  if (currentMode.value === 'chat') sendChatMessage()
  else executeTask()
}

// ── Markdown + 术语渲染 ──────────────────────────────────
function renderChatContent(content: string): string {
  let html = renderMarkdownEnhanced(content)
  html = html.replace(/\[\[(.+?)\]\]/g, (_m, term) => {
    const safe = escapeHtml(term)
    return `<span class="term-highlight" data-term="${safe}">${safe}</span>`
  })
  return html
}

const popoverVisible = ref(false)
const popoverTerm = ref('')
const popoverExplanation = ref('')
const popoverLoading = ref(false)
const popoverLeft = ref(0)
const popoverTop = ref(0)

async function explainTerm(term: string, x: number, y: number) {
  popoverTerm.value = term
  popoverExplanation.value = ''
  popoverLoading.value = true
  popoverVisible.value = true
  popoverLeft.value = x + 12
  popoverTop.value = y + 12
  try {
    const r = await api.post('/chat/explain-term', { term, user_id: userStore.userId, context: '' })
    popoverExplanation.value = r.data.explanation || '暂无解释'
  } catch { popoverExplanation.value = '解释加载失败' }
  finally { popoverLoading.value = false }
}

function handleChatClick(e: MouseEvent) {
  const target = (e.target as HTMLElement).closest('.term-highlight') as HTMLElement | null
  if (target) {
    e.stopPropagation()
    explainTerm(target.dataset.term || '', e.clientX, e.clientY)
  }
}

// ── 其他工具函数 ──────────────────────────────────
function handleDocumentClick(_e: MouseEvent) { popoverVisible.value = false }

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
  if (file.size > 10 * 1024 * 1024) { ElMessage.warning('文件不能超过 10MB'); return }
  uploading.value = true
  try {
    const result = await uploadFile(file)
    if (result.ok) {
      uploadedFile.value = { fileName: result.file_name, content: result.content, size: result.size }
      ElMessage.success(`已读取 ${result.file_name}（${(result.size / 1024).toFixed(1)}KB）`)
    } else ElMessage.error(result.error || '上传失败')
  } catch { ElMessage.error('上传失败') }
  finally { uploading.value = false; input.value = '' }
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
  if (!currentConvId.value) { ElMessage.warning('请先创建会话'); return }
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

// 当前会话的问题列表（对话模式 = 用户消息；任务模式 = 任务标题）
const questionList = computed(() => {
  if (currentMode.value === 'chat') {
    return currentChatMsgs.value
      .filter(m => m.role === 'user')
      .map((m, i) => ({ label: m.content.slice(0, 30) + (m.content.length > 30 ? '...' : ''), idx: i }))
  } else {
    return currentConvTasks.value.map((t, i) => ({ label: t.title.slice(0, 30) + (t.title.length > 30 ? '...' : ''), id: t.id, idx: i }))
  }
})

const questionPanelOpen = ref(false)
</script>

<template>
  <div class="agent-panel" :class="{ dark: themeStore.isDark }">
    <!-- 左侧：会话列表 -->
    <aside class="conv-sidebar">
      <div class="sidebar-header">
        <h3>会话</h3>
        <el-button size="small" type="primary" plain @click="newConversation">+ 新建</el-button>
      </div>
      <div class="conv-list">
        <div v-for="c in conversations" :key="c.id" class="conv-item"
          :class="{ active: c.id === currentConvId }" @click="selectConversation(c.id)">
          <div class="conv-item-title">{{ c.title }}</div>
          <div class="conv-item-meta">
            <span class="conv-item-time">{{ formatConvTime(c.updated_at) }}</span>
            <span class="conv-del-btn" @click.stop="deleteConversation(c.id, $event)">🗑</span>
          </div>
        </div>
        <div v-if="conversations.length === 0" class="conv-empty">暂无会话，点击「+ 新建」开始</div>
      </div>
    </aside>

    <!-- 右侧：主区域 -->
    <main class="work-area">
      <header class="task-header">
        <div class="header-left">
          <h2 v-if="currentConvId" class="conv-title-display">
            {{ conversations.find(c => c.id === currentConvId)?.title || '对话' }}
          </h2>
          <h2 v-else class="placeholder-title">AI 智能助手</h2>
        </div>
        <div class="header-right">
          <!-- 模式切换 -->
          <div v-if="currentConvId" class="mode-switch">
            <button :class="['mode-btn', { active: currentMode === 'chat' }]" @click="setMode('chat')">💬 对话</button>
            <button :class="['mode-btn', { active: currentMode === 'task' }]" @click="setMode('task')">🤖 任务</button>
          </div>
          <!-- 任务模式工具 -->
          <template v-if="currentMode === 'task' && currentConvId">
            <el-button size="small" text @click="questionPanelOpen = !questionPanelOpen" title="任务列表">📋</el-button>
            <el-button size="small" @click="runDemoMode" :disabled="agentStore.isExecuting">演示</el-button>
            <el-button size="small" type="danger" plain @click="clearAllTasks" :disabled="currentConvTasks.length === 0">清空</el-button>
          </template>
          <el-button text @click="themeStore.toggle">{{ themeStore.isDark ? '☀️' : '🌙' }}</el-button>
          <el-button v-if="agentStore.isExecuting || isStreaming" type="danger" size="small"
            @click="agentStore.cancelExecution(); isStreaming = false">停止</el-button>
        </div>
      </header>

      <div class="work-content">
        <div class="main-scroll" ref="mainContainer">

          <!-- 未选择会话 -->
          <div v-if="!currentConvId" class="empty-state">
            <div class="empty-icon">🤖</div>
            <p>从左侧选择会话，或点击「+ 新建」开始</p>
          </div>

          <!-- 对话模式 -->
          <template v-else-if="currentMode === 'chat'">
            <div v-if="currentChatMsgs.length === 0" class="empty-state">
              <div class="empty-icon">💬</div>
              <p>直接提问，AI 会结合你的学习画像回答</p>
            </div>
            <div v-for="msg in currentChatMsgs" :key="msg.uid"
              :class="['chat-msg', msg.role]">
              <div class="chat-bubble" @click="msg.role === 'assistant' ? handleChatClick($event) : undefined">
                <template v-if="msg.role === 'user'">{{ msg.content }}</template>
                <template v-else-if="msg.streaming">{{ msg.content }}<span class="cursor">|</span></template>
                <div v-else class="markdown-body" v-html="renderChatContent(msg.content)" />
              </div>
            </div>
          </template>

          <!-- 任务模式 -->
          <template v-else>
            <div v-if="currentConvTasks.length === 0" class="empty-state">
              <div class="empty-icon">🤖</div>
              <p>描述任务，Agent 将展示思考与执行过程</p>
            </div>
            <!-- 任务选择标签（多个任务时显示） -->
            <div v-if="currentConvTasks.length > 1" class="task-tabs">
              <div v-for="t in currentConvTasks" :key="t.id" class="task-tab"
                :class="{ active: t.id === (currentTask?.id) }"
                @click="agentStore.currentTaskId = t.id">
                {{ t.title.slice(0, 20) }}{{ t.title.length > 20 ? '...' : '' }}
                <span class="tab-del" @click.stop="deleteTask(t.id)">✕</span>
              </div>
            </div>
            <AgentTimeline v-if="currentTask"
              :steps="currentTask.steps" :is-executing="agentStore.isExecuting" @rerun="handleRerun" />
            <!-- [建议] 按钮 -->
            <div v-if="currentTask && taskMeta[currentTask.id]?.suggestions?.length && currentTask.status === 'completed'"
              class="suggestion-area">
              <button v-for="(s, i) in taskMeta[currentTask.id].suggestions" :key="i"
                class="suggestion-btn" :disabled="agentStore.isExecuting || !s.action"
                @click="s.action && triggerWorkflow(s.action, s.topic)">{{ s.text }}</button>
            </div>
            <!-- 资源卡片 -->
            <div v-if="currentTask && taskMeta[currentTask.id]?.resources?.length" class="resource-area">
              <div v-for="r in taskMeta[currentTask.id].resources" :key="r.resource_id" class="resource-card-inline">
                <span>{{ r.resource_type === 'quiz' ? '📝' : r.resource_type === 'mindmap' ? '🧠' : '📄' }} {{ r.title || '学习资源' }}</span>
                <a :href="`/resources?open=${r.resource_id}`" target="_blank" class="resource-jump">查看 →</a>
              </div>
            </div>
          </template>
        </div>

        <!-- 问题列表面板（任务模式） -->
        <aside v-if="questionPanelOpen && currentMode === 'task'" class="question-panel">
          <div class="qp-header">
            <span>任务列表</span>
            <span class="qp-close" @click="questionPanelOpen = false">✕</span>
          </div>
          <div class="qp-list">
            <div v-for="(q, i) in questionList" :key="i" class="qp-item"
              :class="{ active: (q as any).id === currentTask?.id }"
              @click="agentStore.currentTaskId = (q as any).id">
              <span class="qp-badge">{{ i + 1 }}</span>
              <span class="qp-text">{{ q.label }}</span>
            </div>
            <div v-if="questionList.length === 0" class="qp-empty">暂无任务</div>
          </div>
        </aside>
      </div>

      <!-- 输入区 -->
      <div class="input-area">
        <div v-if="uploadedFile" class="file-preview">
          <span class="file-name">📄 {{ uploadedFile.fileName }}</span>
          <span class="file-size">{{ formatSize(uploadedFile.size) }}</span>
          <el-button size="small" text @click="clearFile">✕</el-button>
        </div>
        <div class="input-row">
          <label v-if="currentMode === 'task'" class="upload-btn" :class="{ disabled: agentStore.isExecuting }">
            <input type="file"
              accept=".txt,.md,.pdf,.json,.csv,.xml,.yaml,.yml,.py,.js,.ts,.java,.c,.cpp,.rs,.go,.log"
              @change="handleFileChange" :disabled="agentStore.isExecuting" />
            <span v-if="uploading">⏳</span><span v-else>📎</span>
          </label>
          <el-input v-model="inputText" type="textarea" :rows="2"
            :placeholder="currentMode === 'chat' ? '输入问题，Enter 发送...' : (uploadedFile ? '输入任务描述...' : '描述任务，如：分析离散数学在AI领域的应用...')"
            :disabled="agentStore.isExecuting || isStreaming"
            @keydown.enter.exact.prevent="handleSubmit" />
          <el-button type="primary"
            :disabled="(!inputText.trim() && !uploadedFile) || agentStore.isExecuting || isStreaming"
            :loading="agentStore.isExecuting || isStreaming"
            @click="handleSubmit">
            {{ currentMode === 'chat' ? '发送' : '执行' }}
          </el-button>
        </div>
      </div>
    </main>
  </div>

  <!-- 术语释义弹窗 -->
  <Teleport to="body">
    <div v-if="popoverVisible" class="term-popover" :style="{ left: popoverLeft + 'px', top: popoverTop + 'px' }" @click.stop>
      <div class="popover-header">
        <span class="popover-term">{{ popoverTerm }}</span>
        <span class="popover-close" @click="popoverVisible = false">✕</span>
      </div>
      <div class="popover-body">
        <span v-if="popoverLoading">加载中...</span>
        <span v-else>{{ popoverExplanation }}</span>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.agent-panel { display: flex; height: calc(100vh - 48px); background: #FFF5EB; overflow: hidden; }
.agent-panel.dark { background: var(--bg-page); color: var(--text-regular); }

/* ── 侧边栏 ── */
.conv-sidebar {
  width: 240px; min-width: 240px;
  background: #FFFBF5;
  border-right: 1px solid #EFE6DC;
  display: flex; flex-direction: column;
}
.sidebar-header {
  padding: 16px;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid #EFE6DC;
  flex-shrink: 0;
}
.sidebar-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #3A332E; }
.conv-list { flex: 1; overflow-y: auto; padding: 8px; }
.conv-item {
  padding: 10px 12px;
  border-radius: 12px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: all 0.25s cubic-bezier(.4,0,.2,1);
  border: 1px solid transparent;
}
.conv-item:hover { background: #FFF5EB; transform: translateY(-1px); box-shadow: 0 2px 8px rgba(58,51,46,0.08); }
.conv-item.active { background: #FFF5EB; border-color: #F9D9B8; box-shadow: 0 2px 8px rgba(58,51,46,0.08); }
.conv-item-title { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 4px; color: #3A332E; }
.conv-item-meta { display: flex; align-items: center; justify-content: space-between; }
.conv-item-time { font-size: 11px; color: #948A80; }
.conv-del-btn { font-size: 12px; cursor: pointer; opacity: 0; color: #948A80; transition: all 0.25s; padding: 2px 5px; border-radius: 6px; }
.conv-item:hover .conv-del-btn { opacity: 1; }
.conv-del-btn:hover { color: var(--color-danger); background: var(--color-danger-bg); }
.conv-empty {
  text-align: center; padding: 48px 16px; color: #948A80; font-size: 13px; line-height: 2;
}

/* ── 主区域 ── */
.work-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; background: #FFF5EB; }
.work-content { flex: 1; display: flex; overflow: hidden; }

.task-header {
  padding: 14px 24px;
  background: #FFFBF5;
  border-bottom: 1px solid #EFE6DC;
  display: flex; align-items: center; justify-content: space-between;
  flex-shrink: 0; min-height: 58px;
}
.header-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
.conv-title-display { margin: 0; font-size: 16px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #3A332E; }
.placeholder-title { margin: 0; font-size: 16px; color: #948A80; }
.header-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

.mode-switch { display: flex; background: #FFF5EB; border-radius: 10px; padding: 3px; gap: 2px; border: 1px solid #EFE6DC; }
.mode-btn {
  padding: 5px 14px; border: none; border-radius: 8px;
  cursor: pointer; font-size: 13px; color: #948A80;
  background: transparent; transition: all 0.25s cubic-bezier(.4,0,.2,1); white-space: nowrap;
}
.mode-btn.active { background: #FFFBF5; color: #3A332E; box-shadow: 0 1px 4px rgba(58,51,46,0.1); font-weight: 600; }
.mode-btn:hover:not(.active) { color: #3A332E; background: rgba(249,217,184,0.3); }

/* ── 内容滚动区 ── */
.main-scroll { flex: 1; overflow-y: auto; padding: 24px 28px; display: flex; flex-direction: column; gap: 16px; }

/* ── 空状态 ── */
.empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #948A80; gap: 12px; padding: 48px 0; }
.empty-icon { font-size: 48px; opacity: 0.7; }
.empty-state p { font-size: 14px; color: #948A80; margin: 0; }

/* ── 对话气泡 ── */
.chat-msg { display: flex; animation: fadeIn 0.3s cubic-bezier(.4,0,.2,1); }
.chat-msg.user { justify-content: flex-end; }
.chat-msg.assistant { justify-content: flex-start; }
.chat-bubble {
  max-width: 72%; padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px; line-height: 1.7; word-break: break-word;
}
.chat-msg.user .chat-bubble {
  background: #F9D9B8; color: #3A332E;
  border-bottom-right-radius: 4px;
  white-space: pre-wrap;
  box-shadow: 0 2px 8px rgba(58,51,46,0.10);
}
.chat-msg.assistant .chat-bubble {
  background: #FFFBF5; border: 1px solid #EFE6DC;
  border-bottom-left-radius: 4px;
  box-shadow: 0 2px 8px rgba(58,51,46,0.06);
  animation: bubbleFadeUp 0.3s cubic-bezier(.4,0,.2,1);
}
.cursor { animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }
@keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
@keyframes bubbleFadeUp { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

/* ── 任务标签 ── */
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

/* ── 建议按钮 ── */
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

/* ── 任务列表面板 ── */
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

/* ── 输入区 ── */
.input-area {
  padding: 14px 24px 16px;
  background: #FFFBF5;
  border-top: 1px solid #EFE6DC;
  display: flex; flex-direction: column; gap: 8px;
  flex-shrink: 0;
}
.input-row { display: flex; gap: 10px; align-items: flex-end; }
.file-preview {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px; background: #FFF5EB;
  border-radius: 8px; font-size: 12px; border: 1px solid #F9D9B8;
}
.file-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; color: #6B635C; }
.file-size { color: #948A80; flex-shrink: 0; }
.upload-btn {
  display: flex; align-items: center; justify-content: center;
  width: 40px; height: 40px; cursor: pointer;
  border: 1px solid #EFE6DC; border-radius: 8px;
  background: #FFFBF5; font-size: 16px; flex-shrink: 0;
  transition: all 0.25s cubic-bezier(.4,0,.2,1);
}
.upload-btn:hover { border-color: #E8C29C; background: #FFF5EB; transform: translateY(-1px); }
.upload-btn.disabled { cursor: not-allowed; opacity: 0.4; }
.upload-btn input { display: none; }

/* ── 气泡内 Markdown ── */
.chat-bubble .markdown-body { white-space: normal; }
.chat-bubble :deep(.term-highlight) { color: #DBA878; font-weight: 600; cursor: pointer; border-bottom: 1px dashed #DBA878; transition: all 0.2s; }
.chat-bubble :deep(.term-highlight:hover) { background: #FFF5EB; border-radius: 2px; }
.chat-bubble :deep(p) { margin: 4px 0; }
.chat-bubble :deep(pre) { background: #FFF5EB; border-radius: 6px; padding: 10px; overflow-x: auto; font-size: 12px; border: 1px solid #EFE6DC; }
.chat-bubble :deep(code) { font-family: var(--font-mono); }
.chat-bubble :deep(ul), .chat-bubble :deep(ol) { padding-left: 20px; margin: 4px 0; }

/* ── 视频卡片 ── */
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

/* ── 术语弹窗 ── */
.term-popover {
  position: fixed; z-index: 9999;
  background: #FFFBF5; border: 1px solid #EFE6DC;
  border-radius: 12px; box-shadow: 0 8px 24px rgba(58,51,46,0.12);
  min-width: 200px; max-width: 320px;
  animation: popFadeIn 0.2s cubic-bezier(.4,0,.2,1);
}
@keyframes popFadeIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
.popover-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-bottom: 1px solid #EFE6DC; }
.popover-term { font-weight: 600; color: #DBA878; font-size: 14px; }
.popover-close { cursor: pointer; color: #948A80; font-size: 14px; padding: 2px 6px; border-radius: 6px; transition: all 0.2s; }
.popover-close:hover { color: var(--color-danger); }
.popover-body { padding: 12px 14px; font-size: 13px; color: #6B635C; line-height: 1.6; }
</style>
