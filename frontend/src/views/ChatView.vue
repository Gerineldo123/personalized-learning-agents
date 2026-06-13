<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted, reactive } from 'vue'
import { chatStream } from '../api/chat'
import type { ResourceEvent } from '../api/workflow'
import { useUserStore } from '../stores/user'
import api from '../api'
import { useRouter } from 'vue-router'
import MarkdownIt from 'markdown-it'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { ElMessage } from 'element-plus'

const md = new MarkdownIt({ html: false, breaks: true, linkify: true })
const userStore = useUserStore()
const router = useRouter()

onMounted(() => {
  if (!userStore.userId) {
    userStore.setUserId('user_' + Date.now())
  }
  loadConversations()
  document.addEventListener('click', handleDocumentClick)
})

onUnmounted(() => {
  document.removeEventListener('click', handleDocumentClick)
})

let msgUid = 0

interface Message {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  uid: number
  time: string
  thinking?: string
  thinkingEnd?: boolean
  quizResourceId?: number
  resources?: ResourceEvent[]
}

interface ConvItem {
  id: number
  title: string
  msg_count: number
  updated_at: string
}

interface QuestionItem {
  summary: string
  index: number
}

const messages = ref<Message[]>([])
const conversations = ref<ConvItem[]>([])
const currentConvId = ref<number | null>(null)
const inputText = ref('')
const isStreaming = ref(false)
const chatContainer = ref<HTMLElement | null>(null)
const showConvList = ref(false)

const questionHistory = ref<QuestionItem[]>([])
const panelOpen = ref(false)
const highlightIndex = ref(-1)
const thinkingExpanded = reactive<Record<number, boolean>>({})

function toggleThinking(uid: number) {
  thinkingExpanded[uid] = !thinkingExpanded[uid]
}

function generateSummary(text: string): string {
  const cleaned = text.replace(/\s+/g, ' ').trim()
  if (cleaned.length <= 28) return cleaned
  return cleaned.substring(0, 28) + '...'
}

function rebuildQuestionHistory() {
  questionHistory.value = []
  messages.value.forEach((msg, i) => {
    if (msg.role === 'user' && !msg.streaming) {
      questionHistory.value.push({ summary: generateSummary(msg.content), index: i })
    }
  })
}

function scrollToMessage(index: number) {
  const el = document.getElementById(`msg-${index}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    highlightIndex.value = index
    panelOpen.value = false
    setTimeout(() => { highlightIndex.value = -1 }, 2000)
  }
}

function renderProcessedContent(content: string): string {
  // 检测视频搜索结果，渲染为卡片
  try {
    const data = JSON.parse(content)
    if (data.agent === 'video' && Array.isArray(data.videos)) {
      const cards = data.videos.map((v: any) => `
        <div class="video-card">
          <div class="video-card-title">📺 ${escapeHtml(v.title || '')}</div>
          <div class="video-card-meta">${escapeHtml(v.source || '')}${v.duration ? ' · ' + escapeHtml(v.duration) : ''}</div>
          <div class="video-card-reason">${escapeHtml(v.reason || '')}</div>
          ${v.url ? `<a class="video-card-link" href="${escapeHtml(v.url)}" target="_blank" rel="noopener">▶ 观看</a>` : ''}
        </div>`).join('')
      const summary = data.search_summary ? `<div class="video-summary">${escapeHtml(data.search_summary)}</div>` : ''
      return `<div class="video-results"><div class="video-results-header">🎬 为你推荐的教学视频</div>${summary}${cards}</div>`
    }
  } catch {}

  const codeBlockList: Array<{ lang: string; code: string }> = []
  const mathBlocks: Array<{ formula: string; display: boolean }> = []

  let processed = content.replace(/```(\w*)\s*\n([\s\S]*?)```/g, (_m, lang, code) => {
    const idx = codeBlockList.length
    codeBlockList.push({ lang: lang || '', code })
    return `\uFFF0CB${idx}\uFFF1`
  })

  processed = processed
    .replace(/\$\$([\s\S]*?)\$\$/g, (_m, formula) => {
      const idx = mathBlocks.length
      mathBlocks.push({ formula: formula.trim(), display: true })
      return `\uFFF0MB${idx}\uFFF1`
    })
    .replace(/\\\[([\s\S]*?)\\\]/g, (_m, formula) => {
      const idx = mathBlocks.length
      mathBlocks.push({ formula: formula.trim(), display: true })
      return `\uFFF0MB${idx}\uFFF1`
    })
    .replace(/\$([^$\n]+?)\$/g, (_m, formula) => {
      const idx = mathBlocks.length
      mathBlocks.push({ formula: formula.trim(), display: false })
      return `\uFFF0MB${idx}\uFFF1`
    })
    .replace(/\\\(([\s\S]*?)\\\)/g, (_m, formula) => {
      const idx = mathBlocks.length
      mathBlocks.push({ formula: formula.trim(), display: false })
      return `\uFFF0MB${idx}\uFFF1`
    })

  let html = md.render(processed)

  html = html.replace(/\uFFF0CB(\d+)\uFFF1/g, (_m, idxStr) => {
    const idx = +idxStr
    const { lang, code } = codeBlockList[idx]
    const id = `code-${codeBlockSeq++}`
    codeBlocks.value[id] = code
    const cls = lang ? ` class="language-${lang}"` : ''
    return `<div class="code-block-wrapper">
      <div class="code-header"><span class="code-lang">${lang}</span><span class="code-copy-btn" data-code-id="${id}">复制</span></div>
      <pre><code${cls}>${escapeHtml(code)}</code></pre>
    </div>`
  })

  html = html.replace(/\uFFF0MB(\d+)\uFFF1/g, (_m, idxStr) => {
    const idx = +idxStr
    const { formula, display } = mathBlocks[idx]
    try {
      const rendered = katex.renderToString(formula, { displayMode: display, throwOnError: false })
      return display
        ? `<div class="math-block">${rendered}</div>`
        : `<span class="math-inline">${rendered}</span>`
    } catch {
      return display
        ? `<div class="math-block">${escapeHtml(formula)}</div>`
        : `<span class="math-inline">${escapeHtml(formula)}</span>`
    }
  })

  html = html.replace(/\[\[(.+?)\]\]/g, (_m: string, term: string) => {
    const safe = escapeHtml(term)
    return `<span class="term-highlight" data-term="${safe}">${safe}</span>`
  })

  return html
}

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function formatConvTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour}小时前`
  const diffDay = Math.floor(diffHour / 24)
  if (diffDay < 7) return `${diffDay}天前`
  const m = d.getMonth() + 1
  const day = d.getDate()
  return `${m}/${day}`
}

function formatMsgTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const msgDay = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const diffDays = Math.floor((today.getTime() - msgDay.getTime()) / 86400000)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const time = `${hh}:${mm}`
  if (diffDays === 0) return `今天 ${time}`
  if (diffDays === 1) return `昨天 ${time}`
  const m = d.getMonth() + 1
  const day = d.getDate()
  return `${m}/${day} ${time}`
}

const codeBlocks = ref<Record<string, string>>({})
let codeBlockSeq = 0

const globalGlossary = ref<Record<string, string>>({})

const popoverVisible = ref(false)
const popoverTerm = ref('')
const popoverExplanation = ref('')
const popoverLoading = ref(false)
const popoverX = ref(0)
const popoverY = ref(0)
const popoverLeft = ref(0)
const popoverTop = ref(0)
const isDragging = ref(false)
const dragStartX = ref(0)
const dragStartY = ref(0)
const dragStartLeft = ref(0)
const dragStartTop = ref(0)

async function explainTerm(term: string, x: number, y: number) {
  if (popoverVisible.value && popoverTerm.value === term) {
    popoverVisible.value = false
    return
  }
  popoverTerm.value = term
  popoverExplanation.value = ''
  popoverX.value = x
  popoverY.value = y
  popoverLeft.value = x
  popoverTop.value = y
  popoverVisible.value = true

  if (globalGlossary.value[term]) {
    popoverExplanation.value = globalGlossary.value[term]
    return
  }

  popoverLoading.value = true
  try {
    const r = await api.post('/chat/explain-term', {
      term,
      user_id: userStore.userId,
      context: messages.value.slice(-2).map(m => m.content).join(' '),
    })
    popoverExplanation.value = r.data.explanation || '暂无解释'
  } catch {
    popoverExplanation.value = '获取解释失败，请稍后重试'
  } finally {
    popoverLoading.value = false
  }
}

function startDrag(e: MouseEvent) {
  isDragging.value = true
  dragStartX.value = e.clientX
  dragStartY.value = e.clientY
  dragStartLeft.value = popoverLeft.value
  dragStartTop.value = popoverTop.value
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
}

function onDrag(e: MouseEvent) {
  if (!isDragging.value) return
  const dx = e.clientX - dragStartX.value
  const dy = e.clientY - dragStartY.value
  popoverLeft.value = Math.max(0, dragStartLeft.value + dx)
  popoverTop.value = Math.max(0, dragStartTop.value + dy)
}

function stopDrag() {
  isDragging.value = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
}

function handleContentClick(e: MouseEvent) {
  const copyBtn = (e.target as HTMLElement).closest('.code-copy-btn') as HTMLElement | null
  if (copyBtn) {
    const id = copyBtn.dataset.codeId
    if (id && codeBlocks.value[id]) {
      navigator.clipboard.writeText(codeBlocks.value[id]).then(() => {
        copyBtn.textContent = '已复制'
        setTimeout(() => { copyBtn.textContent = '复制' }, 1500)
      }).catch(() => {})
    }
    return
  }

  const target = (e.target as HTMLElement).closest('.term-highlight') as HTMLElement | null
  if (target) {
    e.stopPropagation()
    const term = target.dataset.term || ''
    explainTerm(term, e.clientX, e.clientY)
  } else {
    popoverVisible.value = false
  }
}

function handleDocumentClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.term-popover') && !target.closest('.term-highlight') && !target.closest('.code-copy-btn')) {
    popoverVisible.value = false
  }
}

async function scrollToBottom() {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

async function loadConversations() {
  try {
    const r = await api.get('/conversations', { params: { user_id: userStore.userId } })
    conversations.value = r.data.items || []
  } catch {}
}

async function newConversation() {
  try {
    const r = await api.post('/conversations', null, {
      params: { user_id: userStore.userId, title: '新对话' },
    })
    currentConvId.value = r.data.id
    messages.value = []
    questionHistory.value = []
    codeBlocks.value = {}
    showConvList.value = false
    await loadConversations()
  } catch {
    ElMessage.error('创建对话失败')
  }
}

async function switchConversation(id: number) {
  if (isStreaming.value) return
  currentConvId.value = id
  showConvList.value = false
  try {
    const r = await api.get(`/conversations/${id}/messages`)
    messages.value = r.data.items.map((m: { role: string; content: string; created_at?: string }) => ({
      role: m.role as 'user' | 'assistant',
      content: m.content,
      streaming: false,
      uid: msgUid++,
      time: m.created_at || '',
    }))
    rebuildQuestionHistory()
    scrollToBottom()
  } catch {
    messages.value = []
  }
}

async function deleteConversation(id: number) {
  try {
    await api.delete(`/conversations/${id}`)
    if (currentConvId.value === id) {
      currentConvId.value = null
      messages.value = []
    }
    await loadConversations()
  } catch {
    ElMessage.error('删除失败')
  }
}

async function saveMessage(role: string, content: string) {
  if (!currentConvId.value) return
  try {
    await api.post(`/conversations/${currentConvId.value}/messages`, null, {
      params: { role, content },
    })
  } catch {}
}

function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return

  if (!currentConvId.value) {
    ElMessage.warning('请先创建或选择一个对话')
    return
  }

  const history = messages.value
    .filter((m) => !m.streaming)
    .map((m) => ({ role: m.role, content: m.content }))

  messages.value.push({ role: 'user', content: text, uid: msgUid++, time: new Date().toISOString() })
  questionHistory.value.push({ summary: generateSummary(text), index: messages.value.length - 1 })
  saveMessage('user', text)
  inputText.value = ''
  scrollToBottom()

  const msgIdx = messages.value.length
  const assistant: Message = { role: 'assistant', content: '', streaming: true, uid: msgUid++, time: new Date().toISOString() }
  messages.value.push(assistant)
  isStreaming.value = true

  let fullContent = ''
  chatStream(
    userStore.userId,
    text,
    history,
    (chunk) => {
      fullContent += chunk
      messages.value[msgIdx].content = fullContent
      scrollToBottom()
    },
    async () => {
      messages.value[msgIdx].streaming = false
      isStreaming.value = false
      await saveMessage('assistant', fullContent)
      await loadConversations()

      try {
        const r = await api.post('/chat/mark-terms', { text: fullContent })
        const marked = r.data.marked_text
        const glossary = r.data.glossary || {}
        if (marked && marked !== fullContent) {
          messages.value[msgIdx].content = marked
        }
        if (glossary && typeof glossary === 'object') {
          for (const [term, expl] of Object.entries(glossary)) {
            if (!globalGlossary.value[term]) {
              globalGlossary.value[term] = expl as string
            }
          }
        }
      } catch {}
    },
    (err) => {
      messages.value[msgIdx].content = `[错误] ${err.message}`
      messages.value[msgIdx].streaming = false
      isStreaming.value = false
      saveMessage('assistant', `[错误] ${err.message}`)
    },
    (stage, data) => {
      if (stage === 'quiz' && data) {
        try {
          const resourceId = typeof data === 'object' ? data.resource_db_id : null
          if (resourceId) messages.value[msgIdx].quizResourceId = resourceId
        } catch {}
      }
    },
    (thinkingType, thinkingText) => {
      if (thinkingType === 'start') {
        messages.value[msgIdx].thinking = ''
      } else if (thinkingType === 'end') {
        messages.value[msgIdx].thinkingEnd = true
      } else if (thinkingType === 'chunk' && thinkingText) {
        if (!messages.value[msgIdx].thinking) messages.value[msgIdx].thinking = ''
        messages.value[msgIdx].thinking += thinkingText
        scrollToBottom()
      }
    },
  )
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

async function copyMessage(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

function editMessage(index: number) {
  inputText.value = messages.value[index].content
  scrollToBottom()
}

function regenerateMessage(aiIndex: number) {
  if (isStreaming.value) return
  const userMsg = messages.value[aiIndex - 1]
  if (!userMsg || userMsg.role !== 'user' || userMsg.streaming) return
  const userText = userMsg.content

  const aiMsg = messages.value[aiIndex]
  aiMsg.content = ''
  aiMsg.streaming = true
  isStreaming.value = true
  scrollToBottom()

  const history = messages.value
    .filter((m, i) => !m.streaming && i < aiIndex)
    .map((m) => ({ role: m.role, content: m.content }))

  let fullContent = ''
  chatStream(
    userStore.userId,
    userText,
    history,
    (chunk) => {
      fullContent += chunk
      aiMsg.content = fullContent
      scrollToBottom()
    },
    async () => {
      aiMsg.streaming = false
      isStreaming.value = false
      await saveMessage('assistant', fullContent)
      await loadConversations()
      try {
        const r = await api.post('/chat/mark-terms', { text: fullContent })
        const marked = r.data.marked_text
        const glossary = r.data.glossary || {}
        if (marked && marked !== fullContent) {
          aiMsg.content = marked
        }
        if (glossary && typeof glossary === 'object') {
          for (const [term, expl] of Object.entries(glossary)) {
            if (!globalGlossary.value[term]) {
              globalGlossary.value[term] = expl as string
            }
          }
        }
      } catch {}
    },
    (err) => {
      aiMsg.content = `[错误] ${err.message}`
      aiMsg.streaming = false
      isStreaming.value = false
      saveMessage('assistant', `[错误] ${err.message}`)
    },
    undefined,
    (thinkingType, thinkingText) => {
      if (thinkingType === 'start') {
        aiMsg.thinking = ''
      } else if (thinkingType === 'end') {
        aiMsg.thinkingEnd = true
      } else if (thinkingType === 'chunk' && thinkingText) {
        if (!aiMsg.thinking) aiMsg.thinking = ''
        aiMsg.thinking += thinkingText
        scrollToBottom()
      }
    },
  )
}
</script>

<template>
  <div class="chat-page">
    <div class="panel-area" :class="{ open: panelOpen }">
      <div class="panel-tab" @click="panelOpen = !panelOpen">
        <span class="tab-icon">{{ panelOpen ? '▶' : '◀' }}</span>
        <span class="tab-text">问题列表</span>
      </div>
      <div class="question-panel">
        <div class="panel-header">问题列表</div>
        <div class="panel-list">
          <div v-if="questionHistory.length === 0" class="panel-empty">
            暂无问题记录
          </div>
          <div
            v-for="(item, idx) in questionHistory"
            :key="idx"
            class="question-item"
            :class="{ active: item.index === highlightIndex }"
            @click="scrollToMessage(item.index)"
          >
            <span class="question-idx">{{ idx + 1 }}</span>
            <span class="question-text">{{ item.summary }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="chat-view">
      <div class="chat-header">
        <h2>AI 对话</h2>
        <div class="conv-controls">
          <el-button size="small" @click="newConversation">+ 新对话</el-button>
          <el-dropdown trigger="click" @command="switchConversation">
            <el-button size="small">
              历史对话 <el-icon><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu v-if="conversations.length > 0">
                <el-dropdown-item
                  v-for="c in conversations"
                  :key="c.id"
                  :command="c.id"
                  :class="{ active: c.id === currentConvId }"
                >
                  <div class="conv-item">
                    <span class="conv-title">{{ c.title }}</span>
                    <span class="conv-meta">{{ formatConvTime(c.updated_at) }}</span>
                    <el-button
                      size="small"
                      type="danger"
                      text
                      class="conv-del"
                      @click.stop="deleteConversation(c.id)"
                    >
                      <el-icon><Delete /></el-icon>
                    </el-button>
                  </div>
                </el-dropdown-item>
              </el-dropdown-menu>
              <el-dropdown-item v-else disabled>暂无历史对话</el-dropdown-item>
            </template>
          </el-dropdown>
          <span class="user-id">用户: {{ userStore.userId }}</span>
        </div>
      </div>

      <div ref="chatContainer" class="chat-messages" @click="handleContentClick">
        <div v-if="messages.length === 0" class="empty-hint">
          点击「+ 新对话」开始，或从「历史对话」中选择
        </div>

        <div
          v-for="(msg, i) in messages"
          :key="msg.uid"
          :id="`msg-${i}`"
          :class="['message', msg.role, { highlight: i === highlightIndex }]"
        >
          <div v-if="msg.role === 'user' && msg.time" class="msg-time">{{ formatMsgTime(msg.time) }}</div>
          <div v-if="msg.role === 'assistant' && msg.thinking" class="thinking-area">
            <span
              class="thinking-toggle"
              @click="toggleThinking(msg.uid)"
            >
              {{ thinkingExpanded[msg.uid] ? '📖 收起思路 ▾' : '📖 查看思路 ▸' }}
            </span>
            <div v-if="thinkingExpanded[msg.uid]" class="thinking-content">
              {{ msg.thinking }}
            </div>
          </div>
          <div
            class="message-content"
            v-if="msg.role === 'assistant' && !msg.streaming"
            v-html="renderProcessedContent(msg.content)"
          />
          <div class="message-content" v-else>
            {{ msg.content }}
            <span v-if="msg.streaming" class="cursor">|</span>
          </div>

          <div v-if="msg.role === 'assistant' && msg.resources?.length && !msg.streaming" class="msg-resources">
            <div v-for="r in msg.resources" :key="r.resource_id" class="resource-card-inline">
              <span class="resource-badge">{{ r.resource_type === 'mindmap' ? '🧠' : r.resource_type === 'quiz' ? '📝' : '📄' }} {{ r.title || '学习资源' }}</span>
              <span class="resource-type-tag">{{ r.resource_type === 'mindmap' ? '思维导图' : r.resource_type === 'quiz' ? '题库' : r.resource_type === 'article' ? '文章' : r.resource_type }}</span>
              <span
                class="resource-jump-btn"
                @click="router.push({ path: '/resources', query: { open: String(r.resource_id) } })"
              >查看 →</span>
            </div>
          </div>

          <div class="message-actions" v-if="!msg.streaming">
            <span class="action-btn" @click="copyMessage(msg.content)" title="复制">复制</span>
            <template v-if="msg.role === 'user'">
              <span class="action-btn" @click="editMessage(i)" title="编辑">编辑</span>
            </template>
            <template v-else>
              <span class="action-btn" :class="{ disabled: isStreaming }" @click="regenerateMessage(i)" title="重新生成">刷新</span>
              <span
                v-if="msg.quizResourceId"
                class="action-btn quiz-btn"
                @click="router.push({ path: '/resources', query: { open: String(msg.quizResourceId) } })"
              >📝 前往答题</span>
            </template>
          </div>
      </div>

      <div class="chat-input">
        <el-input
          v-model="inputText"
          type="textarea"
          :rows="3"
          placeholder="输入您的问题..."
          :disabled="isStreaming"
          @keydown="handleKeydown"
        />
        <el-button
          type="primary"
          :disabled="!inputText.trim() || isStreaming"
          :loading="isStreaming"
          @click="sendMessage"
        >
          发送
        </el-button>
      </div>
    </div>
  </div>

  <Teleport to="body">
    <div
      v-if="popoverVisible"
      class="term-popover"
      :class="{ dragging: isDragging }"
      :style="{ left: popoverLeft + 'px', top: popoverTop + 'px' }"
      @click.stop
    >
      <div class="popover-header" @mousedown="startDrag">
        <span class="popover-term">{{ popoverTerm }}</span>
        <span class="popover-close" @mousedown.stop @click="popoverVisible = false">✕</span>
      </div>
      <div class="popover-body">
        <span v-if="popoverLoading" class="popover-loading">加载中...</span>
        <span v-else v-html="renderProcessedContent(popoverExplanation)" class="popover-text"></span>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.chat-page {
  display: flex;
  justify-content: center;
  height: calc(100vh - 48px);
  position: relative;
  overflow: hidden;
}

.panel-area {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  z-index: 20;
  display: flex;
  transform: translateX(calc(100% - 32px));
  transition: transform 0.28s ease;
}

.panel-area.open {
  transform: translateX(0);
}

.panel-tab {
  width: 32px;
  flex-shrink: 0;
  background: #f0f2f5;
  border: 1px solid #e4e7ed;
  border-right: none;
  border-radius: 8px 0 0 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  user-select: none;
  gap: 6px;
  transition: background 0.2s;
}

.panel-tab:hover {
  background: #e4e7ed;
}

.tab-icon {
  font-size: 12px;
  color: #909399;
  line-height: 1;
}

.tab-text {
  writing-mode: vertical-rl;
  font-size: 12px;
  color: #606266;
  letter-spacing: 2px;
}

.question-panel {
  width: 260px;
  flex-shrink: 0;
  background: #fff;
  border-left: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.06);
}

.panel-header {
  padding: 14px 16px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  border-bottom: 1px solid #ebeef5;
  flex-shrink: 0;
}

.panel-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.panel-empty {
  text-align: center;
  color: #c0c4cc;
  padding: 40px 16px;
  font-size: 13px;
}

.question-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background 0.15s;
  border-left: 2px solid transparent;
}

.question-item:hover {
  background: #f5f7fa;
}

.question-item.active {
  background: #ecf5ff;
  border-left-color: #409eff;
}

.question-idx {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #f0f2f5;
  color: #909399;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
}

.question-item.active .question-idx {
  background: #409eff;
  color: #fff;
}

.question-text {
  flex: 1;
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
  word-break: break-all;
}

.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-width: 800px;
  width: 100%;
  margin: 0 auto;
  transition: margin-right 0.28s ease;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.chat-header h2 { margin: 0; color: #303133; }

.conv-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-id { font-size: 12px; color: #909399; }

.conv-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 260px;
}

.conv-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-meta {
  font-size: 11px;
  color: #909399;
}

.conv-del { margin-left: auto; }

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  margin-bottom: 16px;
  scroll-behavior: smooth;
}

.empty-hint {
  text-align: center;
  color: #c0c4cc;
  padding: 60px 0;
  font-size: 14px;
}

.message { margin-bottom: 16px; }

.msg-time {
  font-size: 11px;
  color: #c0c4cc;
  margin-bottom: 3px;
}

.msg-time.user {
  text-align: right;
}

.msg-time.assistant {
  text-align: left;
}

.message-actions {
  display: flex;
  gap: 2px;
  margin-top: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}

.message:hover .message-actions {
  opacity: 1;
}

.message.user .message-actions {
  justify-content: flex-end;
}

.message.assistant .message-actions {
  margin-left: 2px;
}

.action-btn {
  font-size: 12px;
  color: #909399;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all 0.15s;
  user-select: none;
}

.action-btn:hover {
  color: #409eff;
  background: rgba(64, 158, 255, 0.08);
}

.action-btn.disabled {
  color: #c0c4cc;
  cursor: not-allowed;
}

.action-btn.quiz-btn {
  color: #e6a23c;
  background: rgba(230, 162, 60, 0.08);
}


.message.user .message-content {
  background: #409eff;
  color: #fff;
  margin-left: auto;
  max-width: 75%;
  border-radius: 12px 4px 12px 12px;
}

.message.assistant .message-content {
  background: #f0f2f5;
  color: #303133;
  margin-right: auto;
  max-width: 85%;
  border-radius: 4px 12px 12px 12px;
}

.message.highlight .message-content {
  animation: highlightPulse 0.6s ease-in-out 2;
}

@keyframes highlightPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(64, 158, 255, 0); }
  50% { box-shadow: 0 0 0 6px rgba(64, 158, 255, 0.35); }
}

.message-content {
  padding: 12px 16px;
  line-height: 1.6;
  word-break: break-word;
  text-align: left;
}

.message-content :deep(h1),
.message-content :deep(h2),
.message-content :deep(h3) {
  margin: 12px 0 8px;
  font-weight: 600;
  text-align: left;
}

.message-content :deep(h1) { font-size: 20px; }
.message-content :deep(h2) { font-size: 17px; }
.message-content :deep(h3) { font-size: 15px; }
.message-content :deep(p) { margin: 10px 0; text-align: left; }
.message-content :deep(ul),
.message-content :deep(ol) { padding-left: 20px; margin: 10px 0; text-align: left; }
.message-content :deep(li) { margin: 6px 0; line-height: 1.7; text-align: left; }

.message-content :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 13px;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}

.message-content :deep(pre) {
  background: #282c34;
  color: #abb2bf;
  padding: 14px 18px;
  border-radius: 0 0 6px 6px;
  overflow-x: auto;
  margin: 0;
}

.message-content :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
  font-size: 13px;
  white-space: pre;
  tab-size: 4;
  -moz-tab-size: 4;
}

.message-content :deep(.code-block-wrapper) {
  margin: 12px 0;
  border-radius: 6px;
  overflow: hidden;
}

.message-content :deep(.code-header) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #21252b;
  padding: 6px 14px;
  border-radius: 6px 6px 0 0;
}

.message-content :deep(.code-lang) {
  font-size: 11px;
  color: #abb2bf;
  text-transform: uppercase;
}

.message-content :deep(.code-copy-btn) {
  font-size: 11px;
  color: #abb2bf;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 3px;
  transition: all 0.15s;
  user-select: none;
}

.message-content :deep(.code-copy-btn:hover) {
  color: #fff;
  background: rgba(255, 255, 255, 0.1);
}

.message-content :deep(blockquote) {
  border-left: 3px solid #409eff;
  padding: 4px 12px;
  margin: 8px 0;
  color: #606266;
  background: rgba(64, 158, 255, 0.04);
}

.message-content :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
  width: 100%;
}

.message-content :deep(th),
.message-content :deep(td) {
  border: 1px solid #dcdfe6;
  padding: 6px 10px;
  text-align: left;
}

.message-content :deep(th) { background: #f5f7fa; font-weight: 600; }
.message-content :deep(strong) { font-weight: 700; }
.message-content :deep(a) { color: #409eff; text-decoration: none; }
.message-content :deep(a:hover) { text-decoration: underline; }

.cursor {
  animation: blink 0.8s infinite;
  font-weight: 700;
  color: #409eff;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.chat-input { display: flex; gap: 12px; align-items: flex-end; }

.chat-input .el-textarea { flex: 1; }

.message-content :deep(.term-highlight) {
  color: #409eff;
  font-weight: 700;
  cursor: pointer;
  border-bottom: 1px dashed #409eff;
  padding: 0 2px;
  transition: background 0.15s;
}

.message-content :deep(.term-highlight:hover) {
  background: #ecf5ff;
  border-radius: 3px;
}

.message-content :deep(.math-block) {
  display: block;
  text-align: center;
  margin: 14px 0;
  overflow-x: auto;
}

.message-content :deep(.math-inline) {
  padding: 0 2px;
}

.message-content :deep(.video-results) {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 12px 14px;
}
.message-content :deep(.video-results-header) {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}
.message-content :deep(.video-summary) {
  font-size: 12px;
  color: #909399;
  margin-bottom: 10px;
}
.message-content :deep(.video-card) {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
}
.message-content :deep(.video-card-title) {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}
.message-content :deep(.video-card-meta) {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.message-content :deep(.video-card-reason) {
  font-size: 12px;
  color: #606266;
  margin-bottom: 6px;
}
.message-content :deep(.video-card-link) {
  display: inline-block;
  font-size: 12px;
  color: #409eff;
  text-decoration: none;
  border: 1px solid #409eff;
  border-radius: 4px;
  padding: 2px 10px;
}
.message-content :deep(.video-card-link:hover) {
  background: #ecf5ff;
}
</style>

<style>
.term-popover {
  position: fixed;
  z-index: 9999;
  max-width: 360px;
  min-width: 220px;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  transform: translate(12px, -50%);
  font-size: 13px;
  animation: popoverIn 0.18s ease;
}

@keyframes popoverIn {
  from { opacity: 0; transform: translate(12px, -50%) scale(0.92); }
  to { opacity: 1; transform: translate(12px, -50%) scale(1); }
}

.popover-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px 8px;
  border-bottom: 1px solid #f0f0f0;
  cursor: grab;
  user-select: none;
}

.popover-header:active {
  cursor: grabbing;
}

.term-popover.dragging {
  opacity: 0.92;
  transition: none;
}

.term-popover.dragging .popover-header {
  cursor: grabbing;
}

.popover-term {
  font-weight: 700;
  color: #409eff;
  font-size: 14px;
}

.popover-close {
  cursor: pointer;
  color: #c0c4cc;
  font-size: 14px;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all 0.15s;
}

.popover-close:hover {
  color: #606266;
  background: #f5f7fa;
}

.popover-body {
  padding: 10px 14px 14px;
  line-height: 1.7;
  color: #303133;
  max-height: 260px;
  overflow-y: auto;
}

.popover-body p {
  margin: 6px 0;
}

.popover-body strong {
  color: #303133;
  font-weight: 700;
}

.popover-body h1, .popover-body h2, .popover-body h3 {
  font-size: 14px;
  margin: 8px 0 4px;
}

.popover-body ul, .popover-body ol {
  padding-left: 18px;
  margin: 4px 0;
}

.popover-body code {
  background: rgba(0, 0, 0, 0.05);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
}

.popover-loading {
  color: #909399;
  font-style: italic;
}

.popover-text :deep(strong) {
  font-weight: 700;
  color: #303133;
}

.thinking-area {
  margin-bottom: 6px;
}

.thinking-toggle {
  display: inline-block;
  font-size: 12px;
  color: #909399;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 4px;
  transition: all 0.15s;
  user-select: none;
}

.thinking-toggle:hover {
  color: #409eff;
  background: rgba(64, 158, 255, 0.06);
}

.thinking-content {
  margin-top: 8px;
  padding: 10px 14px;
  background: #fafbfc;
  border-left: 3px solid #d0d7de;
  border-radius: 4px;
  font-size: 13px;
  color: #656d76;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}

.msg-resources {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.resource-card-inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  background: #f0f9eb;
  border: 1px solid #c2e7b0;
  border-radius: 6px;
  font-size: 12px;
}

.resource-badge {
  color: #303133;
  font-weight: 500;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-type-tag {
  font-size: 11px;
  color: #909399;
  background: #f4f4f5;
  padding: 1px 6px;
  border-radius: 3px;
}

.resource-jump-btn {
  color: #409eff;
  cursor: pointer;
  font-size: 12px;
  padding: 1px 6px;
  border-radius: 3px;
  transition: all 0.15s;
  user-select: none;
  white-space: nowrap;
}

.resource-jump-btn:hover {
  background: rgba(64, 158, 255, 0.1);
}
</style>
