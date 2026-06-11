<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useUserStore } from '../stores/user'
import { useAgentStore } from '../stores/agent'
import { useThemeStore } from '../stores/theme'
import { agentExecuteStream, uploadFile } from '../api/agent'
import { runDemo } from '../mock/agentDemo'
import type { AgentStep, StepEvent, UploadedFile } from '../types/agent'
import AgentTimeline from '../components/agent/AgentTimeline.vue'
import { ElMessage } from 'element-plus'

const userStore = useUserStore()
const agentStore = useAgentStore()
const themeStore = useThemeStore()

onMounted(() => {
  if (!userStore.userId) {
    userStore.setUserId('user_' + Date.now())
  }
})

const inputText = ref('')
const timelineContainer = ref<HTMLElement | null>(null)
const showSidebar = ref(false)
const uploadedFile = ref<UploadedFile | null>(null)
const uploading = ref(false)

function scrollToBottom() {
  nextTick(() => {
    if (timelineContainer.value) {
      timelineContainer.value.scrollTop = timelineContainer.value.scrollHeight
    }
  })
}

function handleStepEvent(evt: StepEvent) {
  const taskId = agentStore.currentTaskId
  if (!taskId) return

  const step: AgentStep = {
    stepId: evt.step_id,
    stepType: evt.step_type,
    status: evt.status,
    title: evt.title,
    data: evt.data as AgentStep['data'],
    expanded: evt.status === 'running',
    timestamp: Date.now(),
  }

  agentStore.upsertStep(taskId, step)

  if (evt.status === 'completed' && evt.step_type === 'result') {
    agentStore.setTaskStatus(taskId, 'completed')
    agentStore.isExecuting = false
  }

  if (evt.status === 'error') {
    agentStore.isExecuting = false
    agentStore.setTaskStatus(taskId, 'completed')
  }

  scrollToBottom()
}

async function executeTask() {
  const text = inputText.value.trim()
  if (!text || agentStore.isExecuting) return

  inputText.value = ''
  const taskTitle = uploadedFile.value ? `[${uploadedFile.value.fileName}] ${text}` : text
  const task = agentStore.createTask(taskTitle)
  agentStore.setTaskStatus(task.id, 'running')
  agentStore.isExecuting = true

  const ctrl = agentExecuteStream(
    userStore.userId,
    text,
    handleStepEvent,
    () => {
      agentStore.isExecuting = false
      agentStore.setTaskStatus(task.id, 'completed')
    },
    (err) => {
      console.error('Agent execute error:', err)
      agentStore.isExecuting = false
      agentStore.setTaskStatus(task.id, 'completed')
    },
    uploadedFile.value?.content,
    uploadedFile.value?.fileName,
  )
  agentStore.setAbortController(ctrl)
  uploadedFile.value = null
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
      ElMessage.error(result.error || '文件上传失败')
    }
  } catch {
    ElMessage.error('文件上传失败')
  } finally {
    uploading.value = false
    input.value = ''
  }
}

function clearFile() {
  uploadedFile.value = null
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / 1024 / 1024).toFixed(1) + 'MB'
}

function runDemoMode() {
  if (agentStore.isExecuting) return

  const task = agentStore.createTask('斐波那契数列跨学科分析')
  agentStore.setTaskStatus(task.id, 'running')
  agentStore.isExecuting = true

  runDemo(
    task.id,
    (step) => {
      agentStore.upsertStep(task.id, step)
      scrollToBottom()
    },
    () => {
      agentStore.isExecuting = false
      agentStore.setTaskStatus(task.id, 'completed')
    },
  )
}

function selectTask(id: number) {
  agentStore.currentTaskId = id
  showSidebar.value = false
}

function toggleSidebar() {
  showSidebar.value = !showSidebar.value
}
</script>

<template>
  <div class="agent-panel" :class="{ dark: themeStore.isDark }">
    <aside class="task-sidebar" :class="{ visible: showSidebar }">
      <div class="sidebar-header">
        <h3>任务列表</h3>
        <el-button type="primary" size="small" @click="runDemoMode" :disabled="agentStore.isExecuting">
          演示模式
        </el-button>
      </div>
      <div class="task-list">
        <div
          v-for="task in agentStore.tasks"
          :key="task.id"
          class="task-item"
          :class="{ active: task.id === agentStore.currentTaskId }"
          @click="selectTask(task.id)"
        >
          <div class="task-item-title">{{ task.title }}</div>
          <div class="task-item-meta">
            <el-tag size="small" :type="task.status === 'running' ? 'warning' : task.status === 'completed' ? 'success' : 'info'">
              {{ task.status === 'running' ? '执行中' : task.status === 'completed' ? '已完成' : '待执行' }}
            </el-tag>
            <span class="task-item-time">{{ new Date(task.createdAt).toLocaleTimeString() }}</span>
          </div>
        </div>
        <div v-if="agentStore.tasks.length === 0" class="task-empty">
          暂无任务，输入内容开始执行
        </div>
      </div>
    </aside>

    <main class="work-area">
      <header class="task-header">
        <div class="header-left">
          <el-button class="menu-toggle" @click="toggleSidebar" text>
            <span>☰</span>
          </el-button>
          <h2 v-if="agentStore.currentTask">{{ agentStore.currentTask.title }}</h2>
          <h2 v-else class="placeholder-title">AI Agent 任务执行面板</h2>
        </div>
        <div class="header-right">
          <el-button text @click="themeStore.toggle">
            {{ themeStore.isDark ? '☀️' : '🌙' }}
          </el-button>
          <el-button
            v-if="agentStore.isExecuting"
            type="danger"
            size="small"
            @click="agentStore.cancelExecution"
          >
            停止执行
          </el-button>
        </div>
      </header>

      <div class="timeline-scroll" ref="timelineContainer">
        <AgentTimeline
          v-if="agentStore.currentTask"
          :steps="agentStore.currentTask.steps"
          :is-executing="agentStore.isExecuting"
        />
        <div v-else class="empty-state">
          <div class="empty-icon">🤖</div>
          <p>输入任务描述，Agent 将逐步展示思考与执行过程</p>
        </div>
      </div>

      <div class="input-area">
        <div v-if="uploadedFile" class="file-preview">
          <span class="file-name">📄 {{ uploadedFile.fileName }}</span>
          <span class="file-size">{{ formatSize(uploadedFile.size) }}</span>
          <el-button size="small" text @click="clearFile">✕</el-button>
        </div>
        <div class="input-row">
          <label class="upload-btn" :class="{ disabled: agentStore.isExecuting }">
            <input
              type="file"
              accept=".txt,.md,.pdf,.json,.csv,.xml,.yaml,.yml,.py,.js,.ts,.jsx,.tsx,.vue,.html,.css,.java,.c,.cpp,.rs,.go,.log"
              @change="handleFileChange"
              :disabled="agentStore.isExecuting"
            />
            <span v-if="uploading">⏳</span>
            <span v-else>📎</span>
          </label>
          <el-input
            v-model="inputText"
            type="textarea"
            :rows="2"
            :placeholder="uploadedFile ? '输入任务描述（如：总结这份文档的核心内容）...' : '描述你的任务，如：分析离散数学在人工智能领域的应用...'"
            :disabled="agentStore.isExecuting"
            @keydown.enter.exact.prevent="executeTask"
          />
          <el-button
            type="primary"
            :disabled="(!inputText.trim() && !uploadedFile) || agentStore.isExecuting"
            :loading="agentStore.isExecuting"
            @click="executeTask"
          >
            执行任务
          </el-button>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.agent-panel {
  display: flex;
  height: calc(100vh - 48px);
  background: #f5f7fa;
  overflow: hidden;
}

.agent-panel.dark {
  background: #1a1a2e;
  color: #e0e0e0;
}

.task-sidebar {
  width: 260px;
  min-width: 260px;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  transition: transform 0.3s ease;
  z-index: 10;
}

.dark .task-sidebar {
  background: #16213e;
  border-color: #0f3460;
}

.sidebar-header {
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e4e7ed;
  flex-shrink: 0;
}

.dark .sidebar-header {
  border-color: #0f3460;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 15px;
}

.task-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.task-item {
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.2s;
}

.task-item:hover {
  background: #f0f2f5;
}

.dark .task-item:hover {
  background: #1a1a3e;
}

.task-item.active {
  background: #ecf5ff;
  border: 1px solid #409eff;
}

.dark .task-item.active {
  background: #1a2744;
  border-color: #409eff;
}

.task-item-title {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-item-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.task-item-time {
  font-size: 11px;
  color: #909399;
}

.dark .task-item-time {
  color: #888;
}

.task-empty {
  text-align: center;
  padding: 24px;
  color: #909399;
  font-size: 13px;
}

.work-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.task-header {
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  min-height: 52px;
}

.dark .task-header {
  background: #16213e;
  border-color: #0f3460;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.header-left h2 {
  margin: 0;
  font-size: 16px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.placeholder-title {
  color: #909399;
}

.menu-toggle {
  display: none;
  font-size: 20px;
  padding: 4px 8px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.timeline-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-state p {
  font-size: 14px;
}

.input-area {
  padding: 12px 20px;
  background: #fff;
  border-top: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

.dark .input-area {
  background: #16213e;
  border-color: #0f3460;
}

.input-area .el-textarea {
  flex: 1;
}

.input-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.file-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #ecf5ff;
  border-radius: 6px;
  font-size: 12px;
}

.dark .file-preview {
  background: #1a2744;
}

.file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.file-size {
  color: #909399;
  flex-shrink: 0;
}

.upload-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 32px;
  cursor: pointer;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fff;
  font-size: 16px;
  flex-shrink: 0;
  transition: border-color 0.2s;
}

.upload-btn:hover {
  border-color: #409eff;
}

.upload-btn.disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.upload-btn input {
  display: none;
}

.dark .upload-btn {
  background: #16213e;
  border-color: #0f3460;
}

@media (max-width: 768px) {
  .task-sidebar {
    position: fixed;
    top: 0;
    left: 0;
    height: 100vh;
    transform: translateX(-100%);
    box-shadow: 2px 0 12px rgba(0, 0, 0, 0.15);
  }

  .task-sidebar.visible {
    transform: translateX(0);
  }

  .menu-toggle {
    display: inline-flex;
  }

  .work-area {
    width: 100%;
  }
}
</style>
