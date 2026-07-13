<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted, watch, computed, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { chatStream } from '../api/chat'
import type { ResourceEvent } from '../api/workflow'
import { useUserStore } from '../stores/user'
import api from '../api'
import MarkdownIt from 'markdown-it'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatMessageTime, parseServerDate } from '../utils/dateTime'

const md = new MarkdownIt({ html: false, breaks: true, linkify: true })
const userStore = useUserStore()
const route = useRoute()
const router = useRouter()

const isBootstrappingFromHome = ref(false)

function getHomeQueryText(): string {
  const q = route.query.q
  if (Array.isArray(q)) return String(q[0] || '')
  return typeof q === 'string' ? q : ''
}

async function bootstrapConversationFromHome() {
  if (route.query.from !== 'home' || isBootstrappingFromHome.value) return
  isBootstrappingFromHome.value = true
  try {
    await newConversation()
    const question = getHomeQueryText().trim()
    if (question) { inputText.value = question; sendMessage() }
    await router.replace({ path: '/chat' })
  } finally {
    isBootstrappingFromHome.value = false
  }
}

async function clickSuggestion(q: string) {
  if (!currentConvId.value) {
    try {
      const r = await api.post('/conversations', null, { params: { user_id: userStore.userId, title: '新对话' } })
      currentConvId.value = r.data.id
      await loadConversations()
    } catch { ElMessage.error('创建对话失败'); return }
  }
  inputText.value = q
  sendMessage()
}

async function loadSuggestedQuestions() {
  if (!userStore.userId) return
  try {
    const r = await api.get('/resources', { params: { user_id: userStore.userId, limit: 20 } })
    const items: Array<{ title?: string }> = r.data.items || []
    const questions: string[] = []
    for (const item of items) {
      const title = item.title
      if (!title || title.length < 2) continue
      if (title.length <= 20) {
        questions.push(`讲解一下"${title}"的核心概念`)
        questions.push(`"${title}"的重点是什么？`)
      } else {
        questions.push(`请帮我理解"${title}"`)
      }
      if (questions.length >= 20) break
    }
    suggestedQuestions.value = questions
  } catch { suggestedQuestions.value = [] }
}

onMounted(() => {
  if (!userStore.userId) {
    userStore.setUserId('user_' + Date.now())
  }
  loadConversations()
  loadPinnedConversations()
  loadSuggestedQuestions()
  bootstrapConversationFromHome()
  document.addEventListener('click', handleDocumentClick)
})

watch(() => route.query.t, () => { bootstrapConversationFromHome() })

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
const pinnedConversationIds = ref<number[]>([])
const convMenuVisible = ref(false)
const convMenuX = ref(0)
const convMenuY = ref(0)
const convMenuTarget = ref<ConvItem | null>(null)

const suggestedQuestions = ref<string[]>([])
const questionHistory = ref<QuestionItem[]>([])
const highlightIndex = ref(-1)
const thinkingExpanded = reactive<Record<number, boolean>>({})

const sortedConversations = computed(() => {
  const pinned = new Set(pinnedConversationIds.value)
  return [...conversations.value].sort((a, b) => {
    const ap = pinned.has(a.id) ? 1 : 0
    const bp = pinned.has(b.id) ? 1 : 0
    if (ap !== bp) return bp - ap
    return (parseServerDate(b.updated_at)?.getTime() || 0) - (parseServerDate(a.updated_at)?.getTime() || 0)
  })
})

function loadPinnedConversations() {
  try {
    const raw = localStorage.getItem(`chat_pinned_${userStore.userId}`)
    pinnedConversationIds.value = raw ? JSON.parse(raw) : []
  } catch { pinnedConversationIds.value = [] }
}

function savePinnedConversations() {
  localStorage.setItem(`chat_pinned_${userStore.userId}`, JSON.stringify(pinnedConversationIds.value))
}

function isPinned(id: number) { return pinnedConversationIds.value.includes(id) }

function togglePinConversation() {
  const target = convMenuTarget.value
  if (!target) return
  if (isPinned(target.id)) {
    pinnedConversationIds.value = pinnedConversationIds.value.filter((x) => x !== target.id)
  } else {
    pinnedConversationIds.value = [target.id, ...pinnedConversationIds.value]
  }
  savePinnedConversations()
  convMenuVisible.value = false
}

async function renameConversation() {
  const target = convMenuTarget.value
  if (!target) return
  try {
    const r = await ElMessageBox.prompt('请输入新的对话名称', '重命名对话', {
      inputValue: target.title, confirmButtonText: '确定', cancelButtonText: '取消',
    })
    const title = (r.value || '').trim()
    if (!title) return
    await api.put(`/conversations/${target.id}`, null, { params: { title } })
    await loadConversations()
  } catch {}
  convMenuVisible.value = false
}

async function removeConversationFromMenu() {
  const target = convMenuTarget.value
  if (!target) return
  await deleteConversation(target.id)
  pinnedConversationIds.value = pinnedConversationIds.value.filter((x) => x !== target.id)
  savePinnedConversations()
  convMenuVisible.value = false
}

function openConversationMenu(e: MouseEvent, conv: ConvItem) {
  e.preventDefault()
  convMenuTarget.value = conv
  convMenuX.value = e.clientX
  convMenuY.value = e.clientY
  convMenuVisible.value = true
}

function toggleThinking(uid: number) { thinkingExpanded[uid] = !thinkingExpanded[uid] }

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

function renderProcessedContent(content: string): string {
  // 检测视频搜索结果，渲染为卡片
  try {
    const data = JSON.parse(content)
    if (data.agent === 'video' && Array.isArray(data.videos)) {
      const cards = data.videos.map((v: any) => {
        const bvMatch = (v.url || '').match(/\/video\/(BV\w+)/)
        const avMatch = (v.url || '').match(/\/video\/av(\d+)/)
        const pageMatch = (v.url || '').match(/[?&](?:p|page)=(\d+)/)
        const bvid = bvMatch ? bvMatch[1] : ''
        const avid = avMatch ? avMatch[1] : ''
        const pageParam = pageMatch ? `&page=${pageMatch[1]}` : ''
        const embedSrc = bvid
          ? `//player.bilibili.com/player.html?bvid=${bvid}${pageParam}&autoplay=0&danmaku=0`
          : avid ? `//player.bilibili.com/player.html?aid=${avid}${pageParam}&autoplay=0&danmaku=0` : ''
        const embedOrLink = embedSrc
          ? `<div class="video-card-embed-wrap"><iframe src="${embedSrc}" scrolling="no" frameborder="0" allowfullscreen class="video-card-iframe"></iframe></div>`
          : (v.url ? `<a class="video-card-link" href="${escapeHtml(v.url)}">▶ 在 B 站打开</a>` : '')
        return `
        <div class="video-card">
          <div class="video-card-title">📺 ${escapeHtml(v.title || '')}</div>
          <div class="video-card-meta">${escapeHtml(v.source || '')}${v.duration ? ' · ' + escapeHtml(v.duration) : ''}</div>
          <div class="video-card-reason">${escapeHtml(v.reason || '')}</div>
          ${embedOrLink}
        </div>`
      }).join('')
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

function formatMsgTime(iso: string): string {
  return formatMessageTime(iso)
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
  if (!target.closest('.conv-context-menu')) {
    convMenuVisible.value = false
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
    loadSuggestedQuestions()
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
    <div class="chat-shell">
      <aside class="history-pane animate-up animate-delay-1">
        <div class="history-controls">
          <el-button class="warm-btn" @click="newConversation">开启新对话</el-button>
          <el-button class="warm-btn history-label-btn" disabled>历史对话</el-button>
        </div>
        <div class="conversation-list">
          <div v-if="conversations.length === 0" class="panel-empty">暂无历史对话</div>
          <div
            v-for="c in sortedConversations"
            :key="c.id"
            class="conversation-item"
            :class="{ active: c.id === currentConvId }"
            @click="switchConversation(c.id)"
            @contextmenu="openConversationMenu($event, c)"
          >
            <div class="conv-item">
              <span v-if="isPinned(c.id)" class="conv-pin">置顶</span>
              <span class="conv-title">{{ c.title }}</span>
              <span class="conv-meta">{{ c.msg_count }}条</span>
              <el-button size="small" type="danger" text class="conv-del" @click.stop="deleteConversation(c.id)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
        </div>
        <div class="history-footer">
          <span class="user-id">用户: {{ userStore.userId }}</span>
        </div>
      </aside>

      <section class="chat-view">
        <h2 class="chat-title animate-up animate-delay-1">今天想学点什么？</h2>

        <div ref="chatContainer" class="chat-messages animate-up animate-delay-2" @click="handleContentClick">
          <div v-if="messages.length === 0" class="empty-hint">
            <div class="empty-hint-icon">💬</div>
            <p style="margin:12px 0 0">输入你的问题，AI 将立刻开始思考并回答</p>
          </div>
          <div v-if="messages.length === 0 && suggestedQuestions.length > 0" class="suggested-questions">
            <div class="suggest-row">
              <div class="suggest-track track-ltr">
                <button v-for="(q, i) in suggestedQuestions" :key="'ltr-' + i" class="suggest-btn" @click="clickSuggestion(q)">{{ q }}</button>
                <button v-for="(q, i) in suggestedQuestions" :key="'ltr-dup-' + i" class="suggest-btn" @click="clickSuggestion(q)">{{ q }}</button>
              </div>
            </div>
            <div class="suggest-row">
              <div class="suggest-track track-rtl">
                <button v-for="(q, i) in suggestedQuestions" :key="'rtl-' + i" class="suggest-btn" @click="clickSuggestion(q)">{{ q }}</button>
                <button v-for="(q, i) in suggestedQuestions" :key="'rtl-dup-' + i" class="suggest-btn" @click="clickSuggestion(q)">{{ q }}</button>
              </div>
            </div>
          </div>

          <div
            v-for="(msg, i) in messages"
            :key="msg.uid"
            :id="`msg-${i}`"
            :class="['message', msg.role, { highlight: i === highlightIndex }]"
          >
            <div v-if="msg.role === 'user' && msg.time" class="msg-time">{{ formatMsgTime(msg.time) }}</div>
            <div v-if="msg.role === 'assistant' && msg.thinking" class="thinking-area">
              <span class="thinking-toggle" @click="toggleThinking(msg.uid)">
                {{ thinkingExpanded[msg.uid] ? '📖 收起思路 ▾' : '📖 查看思路 ▸' }}
              </span>
              <div v-if="thinkingExpanded[msg.uid]" class="thinking-content">{{ msg.thinking }}</div>
            </div>
            <div class="message-content" v-if="msg.role === 'assistant' && !msg.streaming" v-html="renderProcessedContent(msg.content)" />
            <div class="message-content" v-else>
              {{ msg.content }}
              <span v-if="msg.streaming" class="cursor">|</span>
            </div>

            <div v-if="msg.role === 'assistant' && msg.resources?.length && !msg.streaming" class="msg-resources">
              <div v-for="r in msg.resources" :key="r.resource_id ?? r.title ?? 'resource'" class="resource-card-inline">
                <span class="resource-badge">{{ r.resource_type === 'mindmap' ? '🧠' : r.resource_type === 'quiz' ? '📝' : '📄' }} {{ r.title || '学习资源' }}</span>
                <span class="resource-type-tag">{{ r.resource_type === 'mindmap' ? '思维导图' : r.resource_type === 'quiz' ? '题库' : r.resource_type === 'article' ? '文章' : r.resource_type }}</span>
                <span class="resource-jump-btn" @click="router.push({ path: '/resources', query: { open: String(r.resource_id) } })">查看 →</span>
              </div>
            </div>

            <div class="message-actions" v-if="!msg.streaming">
              <span class="action-btn" @click="copyMessage(msg.content)" title="复制">复制</span>
              <template v-if="msg.role === 'user'">
                <span class="action-btn" @click="editMessage(i)" title="编辑">编辑</span>
              </template>
              <template v-else>
                <span class="action-btn" :class="{ disabled: isStreaming }" @click="regenerateMessage(i)" title="重新生成">刷新</span>
                <span v-if="msg.quizResourceId" class="action-btn quiz-btn" @click="router.push({ path: '/resources', query: { open: String(msg.quizResourceId) } })">📝 前往答题</span>
              </template>
            </div>
          </div>
        </div>

        <div class="chat-input-wrap animate-up animate-delay-3">
          <div class="chat-input">
            <el-input
              v-model="inputText"
              type="textarea"
              :rows="3"
              placeholder="输入你的问题..."
              :disabled="isStreaming"
              @keydown="handleKeydown"
            />
            <el-button
              class="send-btn"
              :disabled="!inputText.trim() || isStreaming"
              :loading="isStreaming"
              @click="sendMessage"
            >
              发送
            </el-button>
          </div>
        </div>
      </section>
    </div>
  </div>

  <Teleport to="body">
    <div
      v-if="convMenuVisible && convMenuTarget"
      class="conv-context-menu"
      :style="{ left: `${convMenuX}px`, top: `${convMenuY}px` }"
      @click.stop
    >
      <button class="context-item" type="button" @click="togglePinConversation">{{ isPinned(convMenuTarget.id) ? '取消置顶' : '置顶' }}</button>
      <button class="context-item" type="button" @click="renameConversation">重命名</button>
      <button class="context-item danger" type="button" @click="removeConversationFromMenu">删除</button>
    </div>

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
  min-height: calc(100vh - 60px);
  background: linear-gradient(180deg, #F9D9B8 0%, #FFF5EB 45%, #FFFBF5 100%);
  padding: 28px 20px 34px;
}

.chat-shell {
  max-width: 1260px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 24px;
  align-items: stretch;
}

@keyframes floatUpIn {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-up { opacity: 0; animation: floatUpIn 0.55s cubic-bezier(0.2, 0.75, 0.22, 1) forwards; }
.animate-delay-1 { animation-delay: 0.08s; }
.animate-delay-2 { animation-delay: 0.16s; }
.animate-delay-3 { animation-delay: 0.24s; }

.history-pane {
  background: #FFFBF5;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(58, 51, 46, 0.08);
  display: flex;
  flex-direction: column;
  height: calc(100vh - 126px);
  min-height: 640px;
  overflow: hidden;
}

.history-controls {
  padding: 14px 14px 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.conversation-list {
  flex: 1;
  overflow-y: scroll;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0 14px 10px;
  scrollbar-width: thin;
  scrollbar-color: #d9cbb8 transparent;
}
.conversation-list::-webkit-scrollbar { width: 8px; }
.conversation-list::-webkit-scrollbar-track { background: transparent; }
.conversation-list::-webkit-scrollbar-thumb { background: #d9cbb8; border-radius: 999px; }
.conversation-list::-webkit-scrollbar-thumb:hover { background: #c7b39a; }

.history-label-btn { pointer-events: none; }

.conversation-item {
  padding: 8px 10px;
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.18s;
}
.conversation-item:hover { background: #FFF5EB; }
.conversation-item.active { background: rgba(249, 217, 184, 0.3); }

.panel-empty { text-align: center; color: #948A80; padding: 40px 16px; font-size: 14px; }

.history-footer { margin-top: auto; padding: 10px 16px 14px; border-top: 1px solid #EFE6DC; }

.chat-view {
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: calc(100vh - 126px);
  min-height: 640px;
}

.chat-title {
  margin: 0 0 18px;
  color: #3A332E;
  font-size: 24px;
  line-height: 1.4;
  font-weight: 600;
  font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  text-align: center;
}

.warm-btn {
  border-radius: 8px;
  border: 1.5px solid #EFE6DC;
  color: #3A332E;
  background: transparent;
  font-weight: 500;
}
.history-controls :deep(.el-button) { width: 100%; justify-content: center; }
.history-controls :deep(.el-button + .el-button) { margin-left: 0; }
.warm-btn:hover { color: #3A332E; border-color: #E8C29C; background: #FFF5EB; }

.user-id { font-size: 12px; color: #948A80; }

.conv-item { display: flex; align-items: center; gap: 8px; min-width: 0; }
.conv-pin { flex-shrink: 0; font-size: 11px; color: #DBA878; background: rgba(219, 168, 120, 0.12); border-radius: 999px; padding: 2px 6px; }
.conv-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; color: #3A332E; }
.conv-meta { font-size: 14px; color: #948A80; }
.conv-del { margin-left: auto; }

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 40px 20px;
  background: #FFFBF5;
  border-radius: 12px;
  margin-bottom: 14px;
  scroll-behavior: smooth;
  box-shadow: 0 4px 24px rgba(58, 51, 46, 0.08);
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: #d9cbb8 transparent;
}
.chat-messages::-webkit-scrollbar { width: 8px; }
.chat-messages::-webkit-scrollbar-track { background: transparent; }
.chat-messages::-webkit-scrollbar-thumb { background: #d9cbb8; border-radius: 999px; }
.chat-messages::-webkit-scrollbar-thumb:hover { background: #c7b39a; }

.empty-hint {
  text-align: center;
  color: #948A80;
  padding: 60px 0 40px;
  font-size: 14px;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.empty-hint-icon {
  width: 58px;
  height: 58px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 18px;
  background: rgba(64, 158, 255, 0.08);
  font-size: 28px;
}

.suggested-questions { padding: 0 0 40px; overflow: hidden; }
.suggest-row { overflow: hidden; margin-bottom: 8px; }
.suggest-row:hover .suggest-track { animation-play-state: paused; }
.suggest-track { display: flex; gap: 10px; width: max-content; animation-timing-function: linear; animation-iteration-count: infinite; }
.track-ltr { animation: scrollLtr 120s linear infinite; }
.track-rtl { animation: scrollRtl 110s linear infinite; }
@keyframes scrollLtr { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
@keyframes scrollRtl { 0% { transform: translateX(-50%); } 100% { transform: translateX(0); } }
.suggest-btn {
  flex-shrink: 0;
  padding: 8px 20px;
  border: 1.5px solid #EFE6DC;
  border-radius: 22px;
  background: #FFFBF5;
  color: #948A80;
  font-size: 13px;
  font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}
.suggest-btn:hover { border-color: #E8C29C; background: #FFF5EB; transform: translateY(-1px); box-shadow: 0 2px 8px rgba(58, 51, 46, 0.08); }

.message { margin-bottom: 16px; }

.msg-time { font-size: 11px; color: #948A80; margin-bottom: 3px; }

.message-actions {
  display: flex; gap: 2px; margin-top: 4px; opacity: 0; transition: opacity 0.15s;
}
.message:hover .message-actions { opacity: 1; }
.message.user .message-actions { justify-content: flex-end; margin-right: 2px; }
.message.assistant .message-actions { margin-left: 2px; }

.action-btn {
  font-size: 12px; color: #948A80; cursor: pointer; padding: 2px 6px; border-radius: 4px; transition: all 0.15s; user-select: none;
}
.action-btn:hover { color: #DBA878; background: rgba(219, 168, 120, 0.1); }
.action-btn.disabled { color: #948A80; cursor: not-allowed; pointer-events: none; }
.action-btn.quiz-btn { color: #DBA878; background: rgba(219, 168, 120, 0.1); }

.message.user .message-content {
  background: rgba(249,217,184,0.3);
  color: #3A332E;
  margin-left: 60px;
  border-radius: 12px 4px 12px 12px;
  border: 1px solid #EFE6DC;
}
.message.assistant .message-content {
  background: #FFF5EB;
  color: #3A332E;
  margin-right: 60px;
  border-radius: 4px 12px 12px 12px;
  border: 1px solid #EFE6DC;
}

.message.highlight .message-content { animation: highlightPulse 0.6s ease-in-out 2; }
@keyframes highlightPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(64, 158, 255, 0); }
  50% { box-shadow: 0 0 0 6px rgba(64, 158, 255, 0.35); }
}

.message-content {
  padding: 12px 16px;
  line-height: 1.6;
  word-break: break-word;
  color: #3A332E;
  font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 14px;
  font-weight: 400;
}
.message-content :deep(h1), .message-content :deep(h2), .message-content :deep(h3) { margin: 12px 0 8px; font-weight: 500; color: #3A332E; font-family: inherit; font-size: inherit; }
.message-content :deep(p) { margin: 10px 0; color: #3A332E; font-family: inherit; }
.message-content :deep(ul), .message-content :deep(ol) { padding-left: 20px; margin: 10px 0; color: #3A332E; font-family: inherit; }
.message-content :deep(li) { margin: 6px 0; line-height: 1.7; color: #3A332E; font-family: inherit; }
.message-content :deep(code) { background: #FFF5EB; padding: 2px 6px; border-radius: 3px; font-size: inherit; font-family: inherit; color: #3A332E; }
.message-content :deep(strong), .message-content :deep(em), .message-content :deep(small), .message-content :deep(td), .message-content :deep(th) { color: #3A332E; font-family: inherit; font-weight: 500; }
.message-content :deep(pre) { background: #2f3541; color: #f0f4f9; padding: 14px 18px; border-radius: 0 0 6px 6px; overflow-x: auto; margin: 0; }
.message-content :deep(pre code) { background: none; padding: 0; color: inherit; font-size: 13px; white-space: pre; tab-size: 4; -moz-tab-size: 4; }
.message-content :deep(.code-block-wrapper) { margin: 12px 0; border-radius: 6px; overflow: hidden; }
.message-content :deep(.code-header) { display: flex; justify-content: space-between; align-items: center; background: #21252b; padding: 6px 14px; border-radius: 6px 6px 0 0; }
.message-content :deep(.code-lang) { font-size: 11px; color: #948A80; text-transform: uppercase; }
.message-content :deep(.code-copy-btn) { font-size: 11px; color: #948A80; cursor: pointer; padding: 2px 8px; border-radius: 3px; transition: all 0.15s; user-select: none; }
.message-content :deep(.code-copy-btn:hover) { color: #FFFBF5; background: rgba(255, 255, 255, 0.1); }
.message-content :deep(blockquote) { border-left: 3px solid #DBA878; padding: 4px 12px; margin: 8px 0; color: #3A332E; background: rgba(219, 168, 120, 0.08); }
.message-content :deep(table) { border-collapse: collapse; margin: 8px 0; width: 100%; }
.message-content :deep(th), .message-content :deep(td) { border: 1px solid #EFE6DC; padding: 6px 10px; text-align: left; }
.message-content :deep(th) { background: #FFF5EB; font-weight: 500; }
.message-content :deep(strong) { font-weight: 700; }
.message-content :deep(a) { color: #DBA878; text-decoration: none; }
.message-content :deep(a:hover) { text-decoration: underline; }
.message-content :deep(.term-highlight) { color: #DBA878; font-weight: 700; cursor: pointer; border-bottom: 1px dashed #DBA878; padding: 0 2px; transition: background 0.15s; }
.message-content :deep(.term-highlight:hover) { background: rgba(219, 168, 120, 0.1); border-radius: 3px; }
.message-content :deep(.math-block) { display: block; text-align: center; margin: 14px 0; overflow-x: auto; }
.message-content :deep(.math-inline) { padding: 0 2px; }

.message-content :deep(.video-results) { background: rgba(249,217,184,0.1); border-radius: 8px; padding: 12px 14px; border: 1px solid #EFE6DC; }
.message-content :deep(.video-results-header) { font-size: 14px; font-weight: 500; color: #3A332E; margin-bottom: 8px; }
.message-content :deep(.video-summary) { font-size: 12px; color: #948A80; margin-bottom: 10px; }
.message-content :deep(.video-card) { background: #FFFBF5; border: 1px solid #EFE6DC; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; }
.message-content :deep(.video-card-title) { font-size: 14px; font-weight: 500; color: #3A332E; margin-bottom: 4px; }
.message-content :deep(.video-card-meta) { font-size: 12px; color: #948A80; margin-bottom: 4px; }
.message-content :deep(.video-card-reason) { font-size: 12px; color: #6B635C; margin-bottom: 6px; }
.message-content :deep(.video-card-link) { display: inline-block; font-size: 12px; color: #DBA878; text-decoration: none; border: 1px solid #DBA878; border-radius: 4px; padding: 2px 10px; }
.message-content :deep(.video-card-link:hover) { background: #FFF5EB; }
.message-content :deep(.video-card-embed-wrap) { position: relative; width: 100%; padding-top: 56.25%; margin-top: 8px; }
.message-content :deep(.video-card-iframe) { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none; border-radius: 4px; }

.cursor { animation: blink 0.8s infinite; font-weight: 700; color: #DBA878; }
@keyframes blink { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0; } }

.chat-input-wrap { background: #FFFBF5; border-radius: 12px; box-shadow: 0 4px 24px rgba(58, 51, 46, 0.08); padding: 14px; }
.chat-input { display: flex; gap: 12px; align-items: stretch; }
.chat-input .el-textarea { flex: 1; }
.send-btn { min-width: 96px; border-radius: 8px; border: 1.5px solid #EFE6DC; color: #3A332E; background: transparent; font-weight: 500; }
.send-btn:hover, .send-btn:focus { color: #3A332E; border-color: #E8C29C; background: #FFF5EB; }
:deep(.chat-input .el-textarea__inner) { border-radius: 8px; border: 1.5px solid #EFE6DC; color: #3A332E; background: #FFFBF5; box-shadow: none; }
:deep(.chat-input .el-textarea__inner::placeholder) { color: #948A80; }

.msg-resources { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.resource-card-inline { display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; background: rgba(152, 201, 179, 0.1); border: 1px solid rgba(152, 201, 179, 0.4); border-radius: 6px; font-size: 12px; }
.resource-badge { color: #3A332E; font-weight: 500; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.resource-type-tag { font-size: 11px; color: #948A80; background: #FFF5EB; padding: 1px 6px; border-radius: 3px; }
.resource-jump-btn { color: #DBA878; cursor: pointer; font-size: 12px; padding: 1px 6px; border-radius: 3px; transition: all 0.15s; user-select: none; white-space: nowrap; }
.resource-jump-btn:hover { background: rgba(219, 168, 120, 0.1); }

@media (max-width: 1100px) {
  .chat-shell { grid-template-columns: 1fr; }
  .history-pane { height: auto; min-height: 240px; max-height: 280px; }
  .chat-view { height: auto; min-height: 480px; }
}
@media (max-width: 768px) {
  .chat-page { padding: 14px 12px 18px; }
  .message.user .message-content, .message.assistant .message-content { margin-left: 0; margin-right: 0; }
  .chat-input { flex-direction: column; }
  .send-btn { width: 100%; }
}
</style>

<style>
.conv-context-menu {
  position: fixed;
  z-index: 10020;
  min-width: 132px;
  background: #FFFBF5;
  border: 1.5px solid #EFE6DC;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(58, 51, 46, 0.12);
  padding: 6px;
  transform: translate(8px, 8px);
}
.conv-context-menu .context-item {
  width: 100%; border: none; background: transparent; text-align: left; padding: 8px 10px; border-radius: 8px; color: #3A332E; font-size: 13px; cursor: pointer;
}
.conv-context-menu .context-item:hover { background: #FFF5EB; }
.conv-context-menu .context-item.danger { color: #F2B8A2; }

.term-popover {
  position: fixed;
  z-index: 9999;
  max-width: 360px;
  min-width: 220px;
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 10px;
  box-shadow: 0 4px 20px rgba(58, 51, 46, 0.15);
  transform: translate(12px, -50%);
  font-size: 13px;
  animation: popoverIn 0.18s ease;
}
@keyframes popoverIn {
  from { opacity: 0; transform: translate(12px, -50%) scale(0.92); }
  to { opacity: 1; transform: translate(12px, -50%) scale(1); }
}
.popover-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 14px 8px; border-bottom: 1px solid #EFE6DC; cursor: grab; user-select: none; }
.popover-header:active { cursor: grabbing; }
.term-popover.dragging { opacity: 0.92; transition: none; }
.term-popover.dragging .popover-header { cursor: grabbing; }
.popover-term { font-weight: 700; color: #DBA878; font-size: 14px; }
.popover-close { cursor: pointer; color: #948A80; font-size: 14px; padding: 2px 6px; border-radius: 4px; transition: all 0.15s; }
.popover-close:hover { color: #6B635C; background: #FFF5EB; }
.popover-body { padding: 10px 14px 14px; line-height: 1.7; color: #3A332E; max-height: 260px; overflow-y: auto; font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif; }
.popover-body p { margin: 6px 0; }
.popover-body strong { color: #3A332E; font-weight: 700; }
.popover-body h1, .popover-body h2, .popover-body h3 { font-size: 14px; margin: 8px 0 4px; }
.popover-body ul, .popover-body ol { padding-left: 18px; margin: 4px 0; }
.popover-body code { background: rgba(58, 51, 46, 0.06); padding: 1px 5px; border-radius: 3px; font-size: 12px; }
.popover-loading { color: #948A80; font-style: italic; }
.popover-text :deep(strong) { font-weight: 700; color: #3A332E; }

.thinking-area { margin-bottom: 6px; }
.thinking-toggle { display: inline-block; font-size: 12px; color: #948A80; cursor: pointer; padding: 2px 8px; border-radius: 4px; transition: all 0.15s; user-select: none; }
.thinking-toggle:hover { color: #DBA878; background: rgba(249, 217, 184, 0.15); }
.thinking-content { margin-top: 8px; padding: 10px 14px; background: #FFF5EB; border-left: 3px solid #EFE6DC; border-radius: 4px; font-size: 13px; color: #6B635C; line-height: 1.7; white-space: pre-wrap; word-break: break-word; max-height: 300px; overflow-y: auto; }
</style>
