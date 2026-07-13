<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { useUserStore } from '../stores/user'
import { useEventStore } from '../stores/event'
import MindMapViewer from '../components/resource/MindMapViewer.vue'
import QuizCard from '../components/resource/QuizCard.vue'
import PptViewer from '../components/resource/PptViewer.vue'
import ResourceLineagePanel from '../components/resource/ResourceLineagePanel.vue'
import { ElMessage } from 'element-plus'
import { renderMarkdownEnhanced as renderMdCommon, codeBlockStore } from '../utils/markdown'
import type { AgentCollaborationEvent } from '../types/agent'

const userStore = useUserStore()
const eventStore = useEventStore()
const route = useRoute()
const router = useRouter()

const resources = ref<any[]>([])
const totalResources = ref(0)
const page = ref(1)
const pageSize = ref(12)
const profile = ref<any>(null)
const recommendedSeeds = ref<any[]>([])
const weakPoints = ref<string[]>([])
const weakPointItems = ref<any[]>([])
const typeFilter = ref('')
const courseFilter = ref('')
const kpFilter = ref('')
const statusFilter = ref('')
const lineageGroupFilter = ref('')
const curriculumCourses = ref<any[]>([])
const kpOptions = ref<any[]>([])
const loading = ref(false)
const detailLoading = ref(false)
const selected = ref<any>(null)
const showGenDialog = ref(false)
const genTopic = ref('')
const genTypes = ref<string[]>(['article'])
const genCourseName = ref('')
const genKnowledgePoints = ref<string[]>([])
const genKpOptions = ref<any[]>([])
const genQuestionCount = ref(5)
const genDifficulty = ref('中等')
const genQuestionTypes = ref<string[]>(['single_choice'])
const genCodeLanguage = ref('python')
const graphCourseName = ref('')
const graphKnowledgePoints = ref<string[]>([])
const graphKpOptions = ref<any[]>([])
const graphPackageType = ref('知识点补弱')
const graphPackageLoading = ref(false)
const graphCollaborationEvents = ref<AgentCollaborationEvent[]>([])
const graphPackageStreamResult = ref<any>(null)
const genLoading = ref(false)
const starterLoading = ref(false)
const orchestrateLoading = ref(false)
const autoTagLoading = ref(false)
const feedbackLoading = ref(false)
const articleQuizLoading = ref(false)
const lineageRebuildLoading = ref(false)
const recommendItems = ref<any[]>([])
const manageMode = ref(false)
const selectedIds = ref<number[]>([])
const courseKpCache = ref<Record<string, any[]>>({})
let weakPointHydrateSeq = 0
type GenerationStatus = 'idle' | 'running' | 'success' | 'error'
const generationProgress = ref<{
  visible: boolean
  jobId: string
  title: string
  message: string
  percent: number
  status: GenerationStatus
  current: number
  total: number
  logs: string[]
}>({
  visible: false,
  jobId: '',
  title: '',
  message: '',
  percent: 0,
  status: 'idle',
  current: 0,
  total: 0,
  logs: [],
})
let generationProgressTimer: number | null = null

function markdownSource(content: any): string {
  if (typeof content === 'string') return content
  if (content && typeof content === 'object') {
    if (typeof content.text === 'string') return content.text
    if (typeof content.markdown === 'string') return content.markdown
    if (typeof content.code === 'string') {
      const lang = content.language || 'python'
      return '```' + lang + '\n' + content.code + '\n```'
    }
  }
  return JSON.stringify(content, null, 2)
}

function renderMarkdown(content: any): string {
  return renderMdCommon(markdownSource(content))
}

function animeHtmlContent(content: any): string {
  if (typeof content === 'string') return content
  if (!content || typeof content !== 'object') return ''
  return content.code || content.html || content.text || ''
}

function handleDetailClick(e: MouseEvent) {
  const copyBtn = (e.target as HTMLElement).closest('.code-copy-btn') as HTMLElement | null
  if (copyBtn) {
    const id = copyBtn.dataset.codeId
    if (id && codeBlockStore[id]) {
      navigator.clipboard.writeText(codeBlockStore[id]).then(() => {
        copyBtn.textContent = '已复制'
        setTimeout(() => { copyBtn.textContent = '复制' }, 1500)
      }).catch(() => {})
    }
  }
}

function updateSelectedContent(content: any) {
  if (selected.value) selected.value.content = content
}

function normalizeGraphName(value: string) {
  return String(value || '').replace(/\s+/g, '').toLowerCase()
}

function courseDisplayName(seed: any) {
  return seed?.course || seed?.course_name || seed?.label || seed?.topic || ''
}

const resourceTypes = ['', 'article', 'quiz', 'code', 'anime', 'mindmap', 'ppt', 'video', 'evaluation']
const genTypeOptions = [
  { value: 'article', label: '文章' },
  { value: 'quiz', label: '题库' },
  { value: 'code', label: '代码' },
  { value: 'mindmap', label: '思维导图' },
  { value: 'ppt', label: 'PPT课件' },
  { value: 'video', label: '视频推荐' },
  { value: 'evaluation', label: '学习评估' },
]
const difficultyOptions = ['简单', '中等', '较难', '挑战']
const codeLangOptions = [
  { value: 'python', label: 'Python' },
  { value: 'cpp', label: 'C++' },
  { value: 'java', label: 'Java' },
  { value: 'javascript', label: 'JavaScript' },
  { value: 'c', label: 'C' },
]
const statusOptions = [
  { value: '', label: '全部状态' },
  { value: 'not_started', label: '未开始' },
  { value: 'learning', label: '学习中' },
  { value: 'completed', label: '已完成' },
]
const graphPackageOptions = [
  '课程总览',
  '阶段复习',
  '先修补弱',
  '后继预习',
  '知识点补弱',
  '专项练习',
  '实操案例',
  'PPT课件',
  '完整资源包',
]
function packageIncludesPpt(packageType: string) {
  return ['课程总览', 'PPT课件', '完整资源包'].includes(packageType)
}
void packageIncludesPpt
const feedbackOptions = [
  { value: 'too_hard', label: '太难' },
  { value: 'too_easy', label: '太简单' },
  { value: 'helpful', label: '有帮助' },
  { value: 'irrelevant', label: '不相关' },
]

function makeGenerationJobId() {
  return `resource_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

function clearGenerationTimer() {
  if (generationProgressTimer !== null) {
    window.clearInterval(generationProgressTimer)
    generationProgressTimer = null
  }
}

function startGenerationFallbackTimer() {
  clearGenerationTimer()
  generationProgressTimer = window.setInterval(() => {
    if (!generationProgress.value.visible || generationProgress.value.status !== 'running') return
    if (generationProgress.value.percent >= 90) return
    const step = generationProgress.value.percent < 45 ? 3 : generationProgress.value.percent < 75 ? 2 : 1
    generationProgress.value.percent = Math.min(90, generationProgress.value.percent + step)
  }, 1400)
}

function beginGenerationProgress(title: string, message: string, total = 0) {
  const jobId = makeGenerationJobId()
  generationProgress.value = {
    visible: true,
    jobId,
    title,
    message,
    percent: 3,
    status: 'running',
    current: 0,
    total,
    logs: [message],
  }
  startGenerationFallbackTimer()
  return jobId
}

function appendGenerationLog(message: string) {
  if (!message) return
  const logs = generationProgress.value.logs
  if (logs[logs.length - 1] === message) return
  generationProgress.value.logs = [...logs, message].slice(-5)
}

function updateGenerationProgress(data: any) {
  if (!data || data.user_id !== userStore.userId) return
  if (generationProgress.value.jobId && data.job_id && data.job_id !== generationProgress.value.jobId) return
  if (!generationProgress.value.visible) {
    generationProgress.value.visible = true
    generationProgress.value.jobId = data.job_id || ''
    generationProgress.value.title = '学习资源生成进度'
  }
  generationProgress.value.jobId = data.job_id || generationProgress.value.jobId
  generationProgress.value.message = data.message || generationProgress.value.message
  generationProgress.value.percent = Math.max(
    generationProgress.value.percent,
    Number.isFinite(Number(data.progress)) ? Number(data.progress) : generationProgress.value.percent,
  )
  generationProgress.value.current = Number(data.current || generationProgress.value.current || 0)
  generationProgress.value.total = Number(data.total || generationProgress.value.total || 0)
  appendGenerationLog(data.message || '')
  if (data.status === 'completed') {
    generationProgress.value.status = 'success'
    generationProgress.value.percent = 100
    clearGenerationTimer()
  } else if (data.status === 'failed') {
    generationProgress.value.status = 'error'
    generationProgress.value.percent = Math.max(generationProgress.value.percent, 8)
    clearGenerationTimer()
  } else {
    generationProgress.value.status = 'running'
  }
}

function finishGenerationProgress(message = '资源生成完成') {
  if (!generationProgress.value.visible) return
  generationProgress.value.status = 'success'
  generationProgress.value.percent = 100
  generationProgress.value.message = message
  appendGenerationLog(message)
  clearGenerationTimer()
}

function failGenerationProgress(message = '资源生成失败') {
  if (!generationProgress.value.visible) return
  generationProgress.value.status = 'error'
  generationProgress.value.message = message
  appendGenerationLog(message)
  clearGenerationTimer()
}

function closeGenerationProgress() {
  clearGenerationTimer()
  generationProgress.value.visible = false
}

function generationProgressStatus() {
  if (generationProgress.value.status === 'success') return 'success'
  if (generationProgress.value.status === 'error') return 'exception'
  return undefined
}

function generationStatusText() {
  const map: Record<GenerationStatus, string> = {
    idle: '等待中',
    running: '生成中',
    success: '已完成',
    error: '失败',
  }
  return map[generationProgress.value.status]
}

function generationStatusTagType() {
  if (generationProgress.value.status === 'success') return 'success'
  if (generationProgress.value.status === 'error') return 'danger'
  return 'warning'
}

onMounted(async () => {
  if (route.query.type) typeFilter.value = route.query.type as string
  if (userStore.userId) {
    await loadProfileAndSeeds()
    await loadCurriculumCourses()
    await applyGraphQuery()
    loadResources()
    loadRecommend()
  }
  eventStore.connect(userStore.userId || 'user_default')
})

onUnmounted(() => {
  clearGenerationTimer()
})

watch(() => eventStore.lastEvent, (evt) => {
  if (!evt) return
  if (evt.event === 'resource.generation_progress') {
    updateGenerationProgress(evt.data)
    return
  }
  if (evt.event === 'resource.created' && (!evt.data?.user_id || evt.data.user_id === userStore.userId)) {
    loadResources()
    if (evt.data?.job_id && evt.data.job_id === generationProgress.value.jobId) {
      finishGenerationProgress('资源已生成并刷新列表')
    }
  }
  if ((evt.event === 'quiz.submitted' || evt.event === 'profile.updated') && (!evt.data?.user_id || evt.data.user_id === userStore.userId)) {
    loadProfileAndSeeds()
    loadRecommend()
  }
})

watch(() => userStore.userId, async (newId) => {
  if (newId) {
    await loadProfileAndSeeds()
    await loadCurriculumCourses()
    await applyGraphQuery()
    loadResources()
    loadRecommend()
  }
})

watch(() => route.query, async () => {
  const newType = route.query.type as string
  const typeChanged = typeFilter.value !== (newType || '')

  if (typeChanged) {
    typeFilter.value = newType || ''
    page.value = 1
  }

  await applyGraphQuery()
  loadResources()
}, { deep: true })

async function loadProfileAndSeeds() {
  if (!userStore.userId) return
  try {
    const r = await api.get('/profile', { params: { user_id: userStore.userId } })
    profile.value = r.data?.found ? r.data.profile : null
    const weak = profile.value?.weak_courses || []
    recommendedSeeds.value = weak.slice(0, 6).map((c: any) => ({
      course: c.name || '未命名课程',
      topic: c.knowledge_points || c.name || '核心概念',
      goal: c.goal || '扎实基础',
    }))
    weakPoints.value = profile.value?.weak_points || []
    if (curriculumCourses.value.length > 0) void hydrateWeakPointItems()
  } catch {
    profile.value = null
    recommendedSeeds.value = []
    weakPoints.value = []
    weakPointItems.value = []
  }
}

async function loadCurriculumCourses() {
  if (!userStore.userId) return
  try {
    const r = await api.get('/curriculum/graph', {
      params: { user_id: userStore.userId, major: profile.value?.major || '' },
    })
    curriculumCourses.value = r.data?.nodes || []
    await hydrateWeakPointItems()
  } catch {
    curriculumCourses.value = []
    weakPointItems.value = weakPoints.value.map((pt) => ({ label: pt, topic: pt, course: '', knowledgePoint: '' }))
  }
}

async function fetchCourseKps(courseName: string) {
  if (!courseName) return []
  if (courseKpCache.value[courseName]) return courseKpCache.value[courseName]
  try {
    const r = await api.get(`/curriculum/kp/${encodeURIComponent(courseName)}`)
    const nodes = r.data?.nodes || []
    courseKpCache.value = { ...courseKpCache.value, [courseName]: nodes }
    return nodes
  } catch {
    return []
  }
}

async function findCourseByKnowledgePoint(point: string) {
  const target = normalizeGraphName(point)
  if (!target) return ''
  for (const course of curriculumCourses.value) {
    const courseName = course.id || course.name
    if (!courseName) continue
    const nodes = await fetchCourseKps(courseName)
    const matched = nodes.some((kp: any) => {
      const kpName = kp.id || kp.name || ''
      const normalized = normalizeGraphName(kpName)
      return normalized === target || normalized.includes(target) || target.includes(normalized)
    })
    if (matched) return courseName
  }
  return ''
}

async function hydrateWeakPointItems() {
  const seq = ++weakPointHydrateSeq
  const points = weakPoints.value.filter(Boolean).slice(0, 12)
  if (points.length === 0) {
    weakPointItems.value = []
    return
  }
  const items = []
  for (const point of points) {
    const course = await findCourseByKnowledgePoint(point)
    items.push({
      label: point,
      topic: point,
      course,
      knowledgePoint: course ? point : '',
    })
  }
  if (seq === weakPointHydrateSeq) weakPointItems.value = items
}

async function onCourseFilterChange() {
  kpFilter.value = ''
  kpOptions.value = await fetchCourseKps(courseFilter.value)
  page.value = 1
  loadResources()
}

async function onGenCourseChange() {
  genKnowledgePoints.value = []
  genKpOptions.value = await fetchCourseKps(genCourseName.value)
}

async function onGraphCourseChange() {
  graphKnowledgePoints.value = []
  graphKpOptions.value = await fetchCourseKps(graphCourseName.value)
}

async function applyGraphQuery() {
  const course = String(route.query.course || '')
  const kp = String(route.query.kp || '')
  const pkg = String(route.query.package || '')
  const search = String(route.query.search || '')

  if (course) {
    courseFilter.value = course
    graphCourseName.value = course
    genCourseName.value = course
    graphKpOptions.value = await fetchCourseKps(course)
    kpOptions.value = graphKpOptions.value
    genKpOptions.value = graphKpOptions.value
    if (kp) {
      kpFilter.value = kp
      graphKnowledgePoints.value = [kp]
      genKnowledgePoints.value = [kp]
    }
    if (pkg && graphPackageOptions.includes(pkg)) {
      graphPackageType.value = pkg
    }
    page.value = 1
    return
  }

  if (search) {
    genTopic.value = search
    showGenDialog.value = true
  }
}

async function loadResources() {
  if (!userStore.userId) return
  loading.value = true
  try {
    const offset = (page.value - 1) * pageSize.value
    const params: any = { user_id: userStore.userId, limit: pageSize.value, offset }
    if (typeFilter.value) params.resource_type = typeFilter.value
    if (courseFilter.value) params.course_name = courseFilter.value
    if (kpFilter.value) params.knowledge_point = kpFilter.value
    if (statusFilter.value) params.learning_status = statusFilter.value
    if (lineageGroupFilter.value) params.lineage_group_id = lineageGroupFilter.value
    const r = await api.get('/resources', { params })
    resources.value = r.data.items || []
    totalResources.value = r.data.total || 0

    const openId = Number(route.query.open || 0)
    if (openId > 0) {
      const target = resources.value.find((x: any) => x.id === openId)
      if (target) selected.value = target
    }
  } catch { resources.value = [] }
  finally { loading.value = false }
}

function onPageChange(p: number) {
  page.value = p
  loadResources()
}

function openPptStepFlow(topic: string, courseName = '', knowledgePoints: string[] = [], sessionId = '') {
  const query: Record<string, string> = { topic }
  if (sessionId) query.session_id = sessionId
  if (courseName) query.course = courseName
  if (knowledgePoints.length) query.kp = knowledgePoints.join(',')
  router.push({ path: '/ppt', query })
}

function handlePptSessionsFromResponse(data: any, fallbackTopic: string, fallbackCourse = '', fallbackKps: string[] = []) {
  const sessions = data?.ppt_sessions || []
  if (!sessions.length) return false
  const session = sessions[0] || {}
  const course = session.course_name || data.course_name || fallbackCourse
  const kps = session.knowledge_points || data.knowledge_points || fallbackKps
  const topic = session.topic || fallbackTopic
  ElMessage.info('PPT 已创建分步生成任务，请确认大纲并选择模板')
  openPptStepFlow(topic, course, kps, session.session_id || '')
  return true
}

async function startGenerate() {
  if (!genTopic.value.trim()) { ElMessage.warning('请输入主题'); return }
  if (genTypes.value.length === 0) { ElMessage.warning('请选择类型'); return }
  const selectedTypes = [...genTypes.value]
  const wantsPpt = selectedTypes.includes('ppt')
  const nonPptTypes = selectedTypes.filter(t => t !== 'ppt')
  if (wantsPpt && nonPptTypes.length === 0) {
    showGenDialog.value = false
    openPptStepFlow(genTopic.value.trim(), genCourseName.value, genKnowledgePoints.value)
    return
  }
  genLoading.value = true
  const jobId = beginGenerationProgress(
    '手动生成学习资源',
    `准备生成：${nonPptTypes.map(typeLabel).join('、')}${wantsPpt ? '，PPT 将进入分步流程' : ''}`,
    nonPptTypes.length,
  )
  try {
    await api.post('/resources/generate', null, {
      params: {
        user_id: userStore.userId,
        topic: genTopic.value.trim(),
        resource_types: nonPptTypes.join(','),
        course_name: genCourseName.value,
        knowledge_points: genKnowledgePoints.value.join(','),
        question_count: genQuestionCount.value,
        difficulty: genDifficulty.value,
        question_types: genQuestionTypes.value.join(','),
        code_language: genCodeLanguage.value,
        job_id: jobId,
      }
    })
    finishGenerationProgress('手动学习资源生成完成')
    ElMessage.success(wantsPpt ? '非 PPT 资源已生成，接下来进入 PPT 分步流程' : '资源生成完成')
    if (wantsPpt) {
      openPptStepFlow(genTopic.value.trim(), genCourseName.value, genKnowledgePoints.value)
    }
    showGenDialog.value = false
    genTopic.value = ''
    genTypes.value = ['article']
    genCourseName.value = ''
    genKnowledgePoints.value = []
    genKpOptions.value = []
    genQuestionCount.value = 5
    genDifficulty.value = '中等'
    genQuestionTypes.value = ['single_choice']
    genCodeLanguage.value = 'python'
    page.value = 1
    loadResources()
  } catch (e: any) {
    const message = e?.response?.data?.detail || '生成失败'
    failGenerationProgress(message)
    ElMessage.error(message)
  }
  finally { genLoading.value = false }
}

async function generateQuick(seed: any, type: 'article' | 'quiz') {
  const courseName = seed.course || seed.course_name || ''
  const topicText = seed.topic || seed.knowledgePoint || seed.label || courseName
  const knowledgePoint = seed.knowledgePoint || (topicText && topicText !== courseName ? topicText : '')
  const requestTopic = courseName && topicText ? `${courseName}：${topicText}` : topicText
  const jobId = beginGenerationProgress(
    '快速生成学习资源',
    `准备生成${type === 'article' ? '文章' : '题库'}：${courseDisplayName(seed)}`,
    1,
  )
  try {
    const params: any = {
      user_id: userStore.userId,
      topic: requestTopic,
      resource_types: type,
      job_id: jobId,
    }
    if (courseName && isKnownCourse(courseName)) params.course_name = courseName
    if (knowledgePoint) params.knowledge_points = knowledgePoint
    await api.post('/resources/generate', null, {
      params,
    })
    finishGenerationProgress('快速生成完成')
    ElMessage.success(`已生成${type === 'article' ? '文章' : '题库'}：${courseDisplayName(seed)}`)
    page.value = 1
    loadResources()
  } catch {
    failGenerationProgress('快速生成失败')
    ElMessage.error('快速生成失败')
  }
}

function isKnownCourse(name: string) {
  return curriculumCourses.value.some((c: any) => c.id === name)
}

async function generateStarterPack() {
  starterLoading.value = true
  const jobId = beginGenerationProgress('入门资源包生成', '正在根据画像生成入门文章和题库', 6)
  try {
    const r = await api.post('/resources/generate/starter', null, {
      params: { user_id: userStore.userId, max_courses: 3, job_id: jobId },
      timeout: 180000,
    })
    finishGenerationProgress('入门资源包生成完成')
    ElMessage.success(`已生成 ${r.data.generated || 0} 个资源`)
    page.value = 1
    await loadResources()
  } catch {
    failGenerationProgress('入门资源包生成失败')
    ElMessage.error('入门资源包生成失败')
  } finally {
    starterLoading.value = false
  }
}

async function generateOrchestrated(topic: string, options: { courseName?: string; knowledgePoints?: string[] } = {}) {
  orchestrateLoading.value = true
  const jobId = beginGenerationProgress('多智能体协同生成', '正在启动文章、导图、题库、代码、PPT和视频生成', 6)
  try {
    const r = await api.post('/resources/generate/orchestrate', null, {
      params: {
        user_id: userStore.userId,
        topic,
        course_name: options.courseName || '',
        knowledge_points: (options.knowledgePoints || []).join(','),
        job_id: jobId,
      },
      timeout: 300000,
    })
    finishGenerationProgress('多智能体协同生成完成')
    const openedPpt = handlePptSessionsFromResponse(r.data, topic, options.courseName || '', options.knowledgePoints || [])
    ElMessage.success(openedPpt ? '非 PPT 资源已生成，PPT 请在分步工作台完成' : '多智能体协同生成完成')
    page.value = 1
    await loadResources()
  } catch {
    failGenerationProgress('协同生成失败')
    ElMessage.error('协同生成失败')
  } finally {
    orchestrateLoading.value = false
  }
}

function appendGraphAgentEvent(event: AgentCollaborationEvent) {
  if (!graphCollaborationEvents.value.some((item) => item.event_id === event.event_id)) {
    graphCollaborationEvents.value.push(event)
  }
}

async function streamGraphPackage(params: {
  user_id: string
  course_name: string
  knowledge_points: string
  package_type: string
}) {
  const query = new URLSearchParams(params).toString()
  const response = await fetch(`/api/resources/generate/graph_package/stream?${query}`, {
    method: 'POST',
    headers: { Accept: 'text/event-stream' },
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const reader = response.body?.getReader()
  if (!reader) throw new Error('无法读取生成流')
  const decoder = new TextDecoder()
  let buffer = ''
  let donePayload: any = null
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let eventEnd: number
    while ((eventEnd = buffer.indexOf('\n\n')) !== -1) {
      const event = buffer.slice(0, eventEnd)
      buffer = buffer.slice(eventEnd + 2)
      const raw = event
        .split('\n')
        .filter((line) => line.startsWith('data: '))
        .map((line) => line.slice(6))
        .join('\n')
      if (!raw) continue
      let parsed: any
      try {
        parsed = JSON.parse(raw)
      } catch {
        continue
      }
      if (parsed.type === 'agent_event' && parsed.event) {
        appendGraphAgentEvent(parsed.event)
      } else if (parsed.type === 'done') {
        donePayload = parsed
      } else if (parsed.type === 'error') {
        throw new Error(parsed.message || '图谱资源包生成失败')
      }
    }
  }
  return donePayload
}

async function generateGraphPackage() {
  if (!graphCourseName.value) { ElMessage.warning('请先选择课程节点'); return }
  graphPackageLoading.value = true
  graphCollaborationEvents.value = []
  graphPackageStreamResult.value = null
  closeGenerationProgress()
  try {
    const result = await streamGraphPackage({
      user_id: userStore.userId,
      course_name: graphCourseName.value,
      knowledge_points: graphKnowledgePoints.value.join(','),
      package_type: graphPackageType.value,
    })
    graphPackageStreamResult.value = result
    const openedPpt = handlePptSessionsFromResponse(result, `${graphCourseName.value} ${graphPackageType.value}`, graphCourseName.value, graphKnowledgePoints.value)
    ElMessage.success(openedPpt ? `已生成 ${result?.generated || 0} 个非 PPT 图谱资源，PPT 请在分步工作台完成` : `已生成 ${result?.generated || 0} 个图谱资源`)
    courseFilter.value = graphCourseName.value
    kpFilter.value = graphKnowledgePoints.value[0] || ''
    page.value = 1
    await loadResources()
  } catch (e: any) {
    const message = e?.response?.data?.detail || e?.message || '图谱资源包生成失败'
    ElMessage.error(message)
  } finally {
    graphPackageLoading.value = false
  }
}

async function loadRecommend() {
  if (!userStore.userId) return
  try {
    const r = await api.get('/resources/recommend', { params: { user_id: userStore.userId, top_k: 8 } })
    recommendItems.value = r.data.items || []
  } catch {
    recommendItems.value = []
  }
}

async function viewResource(r: any) {
  if (manageMode.value) { toggleSelect(r.id); return }
  if (!r?.id || r.content) {
    selected.value = r
    return
  }
  detailLoading.value = true
  try {
    const resp = await api.get(`/resources/${r.id}`)
    if (resp.data?.found) {
      selected.value = resp.data
    } else {
      ElMessage.warning('资源不存在或已被删除')
    }
  } catch {
    ElMessage.error('资源详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

function toggleManageMode() {
  manageMode.value = !manageMode.value
  if (!manageMode.value) selectedIds.value = []
}

function toggleSelect(id: number) {
  if (!manageMode.value) return
  if (selectedIds.value.includes(id)) {
    selectedIds.value = selectedIds.value.filter((x) => x !== id)
  } else {
    selectedIds.value.push(id)
  }
}

async function batchPin(pinned: 0 | 1) {
  if (selectedIds.value.length === 0) { ElMessage.warning('请先选择资源'); return }
  try {
    await api.post('/resources/batch_pin', null, {
      params: { user_id: userStore.userId, ids: selectedIds.value.join(','), pinned },
    })
    ElMessage.success(pinned ? '已批量置顶' : '已取消置顶')
    await loadResources()
  } catch { ElMessage.error('操作失败') }
}

async function batchDelete() {
  if (selectedIds.value.length === 0) { ElMessage.warning('请先选择资源'); return }
  try {
    await api.post('/resources/batch_delete', null, {
      params: { user_id: userStore.userId, ids: selectedIds.value.join(',') },
    })
    ElMessage.success('已批量删除')
    selectedIds.value = []
    await loadResources()
  } catch { ElMessage.error('删除失败') }
}

async function autoTagResources() {
  autoTagLoading.value = true
  try {
    const ids = selectedIds.value.length > 0 ? selectedIds.value.join(',') : undefined
    const r = await api.post('/resources/auto_tag', null, {
      params: { user_id: userStore.userId, ids },
    })
    ElMessage.success(`已自动归类 ${r.data.updated || 0} 个资源`)
    await loadResources()
  } catch {
    ElMessage.error('自动归类失败')
  } finally {
    autoTagLoading.value = false
  }
}

async function completeSelectedResource() {
  if (!selected.value) return
  try {
    const r = await api.post(`/resources/${selected.value.id}/complete`, null, {
      params: { user_id: userStore.userId },
    })
    selected.value = r.data.resource || selected.value
    ElMessage.success('已记录学习进度；掌握度将在提交题目后自动更新')
    await loadResources()
  } catch {
    ElMessage.error('完成状态更新失败')
  }
}

async function generateQuizFromSelectedArticle() {
  if (!selected.value || selected.value.resource_type !== 'article') return
  articleQuizLoading.value = true
  try {
    const r = await api.post(`/resources/${selected.value.id}/generate_quiz_from_article`, null, {
      params: {
        user_id: userStore.userId,
        question_count: 6,
        difficulty: '中等',
      },
      timeout: 180000,
    })
    const resource = r.data?.resource
    if (resource) {
      selected.value = resource
      typeFilter.value = 'quiz'
      page.value = 1
      ElMessage.success('已根据本文生成测试题，提交后会按题目知识点更新掌握度')
      await loadResources()
    }
  } catch (e: any) {
    const message = e?.response?.data?.detail || '根据文章生成测试题失败'
    ElMessage.error(message)
  } finally {
    articleQuizLoading.value = false
  }
}

async function submitResourceFeedback(feedback: string) {
  if (!selected.value || !userStore.userId) return
  feedbackLoading.value = true
  try {
    await api.post(`/resources/${selected.value.id}/feedback`, {
      user_id: userStore.userId,
      feedback,
    })
    ElMessage.success('反馈已记录，后续推荐会参考该偏好')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '反馈提交失败')
  } finally {
    feedbackLoading.value = false
  }
}

function typeLabel(t: string) {
  const map: Record<string, string> = { article: '文章', quiz: '题库', code: '代码', anime: '动画', mindmap: '思维导图', ppt: 'PPT课件', video: '视频', evaluation: '学习评估' }
  return map[t] || t
}

function statusLabel(status: string) {
  const map: Record<string, string> = { not_started: '未开始', learning: '学习中', completed: '已完成' }
  return map[status] || '未开始'
}

function typeTag(t: string) {
  const map: Record<string, string> = { article: '', quiz: 'warning', code: 'success', anime: 'success', mindmap: 'info', ppt: 'danger', video: '', evaluation: 'info' }
  return map[t] || ''
}

function lineageBadge(resource: any) {
  const summary = resource?.lineage_summary || {}
  if ((summary.child_count || 0) > 0) return `已派生 ${summary.child_count} 个`
  const map: Record<string, string> = {
    generated_from_article: '由文章生成',
    generated_from_quiz: '由题库生成',
    same_package: '资源包成员',
    path_step: '路径步骤资源',
    path_check: '路径检查题',
    remediation: '补弱资源',
    ppt_session: 'AiPPT生成',
    manual: '助手/手动保存',
  }
  return map[summary.relation_type] || (summary.has_lineage ? '有关联' : '独立资源')
}

function lineageTagType(resource: any) {
  const relation = resource?.lineage_summary?.relation_type
  if (relation === 'remediation') return 'danger'
  if (relation === 'path_check' || relation === 'generated_from_article') return 'warning'
  if (relation === 'same_package' || relation === 'path_step') return 'success'
  if (relation === 'ppt_session') return 'danger'
  return 'info'
}

function viewResourceById(id: number) {
  if (!id) return
  viewResource({ id })
}

function applyLineageGroupFilter(groupId: string) {
  if (!groupId) return
  lineageGroupFilter.value = groupId
  selected.value = null
  page.value = 1
  loadResources()
}

function clearLineageGroupFilter() {
  lineageGroupFilter.value = ''
  page.value = 1
  loadResources()
}

async function rebuildResourceLineage() {
  if (!userStore.userId) return
  lineageRebuildLoading.value = true
  try {
    const resp = await api.post('/resources/lineage/rebuild', null, {
      params: { user_id: userStore.userId },
    })
    ElMessage.success(`已重建 ${resp.data?.updated || 0} 个资源关系`)
    await loadResources()
  } catch {
    ElMessage.error('重建资源关系失败')
  } finally {
    lineageRebuildLoading.value = false
  }
}

function courseBindingsOf(resource: any) {
  const bindings = resource?.course_bindings || resource?.content?.course_bindings || []
  return Array.isArray(bindings) ? bindings.filter((item: any) => item && (item.course_name || item.knowledge_points?.length)) : []
}

function graphCourseTags(resource: any) {
  const courses = courseBindingsOf(resource).map((item: any) => item.course_name).filter(Boolean)
  if (resource?.course_name) courses.unshift(resource.course_name)
  return Array.from(new Set(courses))
}

function graphKnowledgeTags(resource: any) {
  const kps = courseBindingsOf(resource).flatMap((item: any) => Array.isArray(item.knowledge_points) ? item.knowledge_points : [])
  if (Array.isArray(resource?.knowledge_points)) kps.unshift(...resource.knowledge_points)
  return Array.from(new Set(kps.filter(Boolean)))
}

function bvidFromUrl(url: string): string {
  if (!url) return ''
  const bv = url.match(/\/video\/(BV\w+)/)
  return bv ? bv[1] : ''
}

function avidFromUrl(url: string): string {
  if (!url) return ''
  const av = url.match(/\/video\/av(\d+)/)
  return av ? av[1] : ''
}

function biliPageFromUrl(url: string): string {
  if (!url) return ''
  try {
    const parsed = new URL(url, window.location.origin)
    return parsed.searchParams.get('p') || parsed.searchParams.get('page') || ''
  } catch {
    const page = url.match(/[?&](?:p|page)=(\d+)/)
    return page ? page[1] : ''
  }
}

function biliPlayerSrc(url: string): string {
  const bvid = bvidFromUrl(url)
  const aid = avidFromUrl(url)
  const page = biliPageFromUrl(url)
  const pageParam = page ? `&page=${page}` : ''
  if (bvid) return `//player.bilibili.com/player.html?bvid=${bvid}${pageParam}&autoplay=0&danmaku=0`
  if (aid) return `//player.bilibili.com/player.html?aid=${aid}${pageParam}&autoplay=0&danmaku=0`
  return ''
}
</script>

<template>
  <div class="resources-view">
    <div class="toolbar animate-up animate-delay-1">
      <el-select v-model="typeFilter" placeholder="全部类型" @change="page = 1; loadResources()" style="width: 160px">
        <el-option v-for="t in resourceTypes" :key="t" :label="t ? typeLabel(t) : '全部'" :value="t" />
      </el-select>
      <el-select v-model="courseFilter" placeholder="按课程筛选" clearable filterable @change="onCourseFilterChange" style="width: 200px">
        <el-option v-for="c in curriculumCourses" :key="c.id" :label="c.id" :value="c.id" />
      </el-select>
      <el-select v-model="kpFilter" placeholder="按知识点筛选" clearable filterable :disabled="!courseFilter" @change="page = 1; loadResources()" style="width: 200px">
        <el-option v-for="kp in kpOptions" :key="kp.id" :label="kp.id" :value="kp.id" />
      </el-select>
      <el-select v-model="statusFilter" placeholder="学习状态" @change="page = 1; loadResources()" style="width: 130px">
        <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <el-button @click="loadResources" style="margin-left: 8px">刷新</el-button>
      <el-button style="margin-left: 8px" @click="toggleManageMode">{{ manageMode ? '完成管理' : '管理资源' }}</el-button>
      <el-button style="margin-left: 8px" :loading="autoTagLoading" @click="autoTagResources">
        {{ selectedIds.length > 0 ? '归类所选' : '自动归类' }}
      </el-button>
      <el-button style="margin-left: 8px" :loading="lineageRebuildLoading" @click="rebuildResourceLineage">
        重建资源关系
      </el-button>
      <el-button v-if="manageMode" style="margin-left: 8px" @click="batchPin(1)">批量置顶</el-button>
      <el-button v-if="manageMode" style="margin-left: 8px" @click="batchPin(0)">取消置顶</el-button>
      <el-button v-if="manageMode" style="margin-left: 8px" type="danger" @click="batchDelete">批量删除</el-button>
      <el-button type="primary" @click="showGenDialog = true" style="margin-left: auto">+ 手动生成</el-button>
    </div>

    <div v-if="lineageGroupFilter" class="lineage-filter-banner animate-up animate-delay-1">
      <span>正在只看当前资源族：{{ lineageGroupFilter }}</span>
      <el-button size="small" text @click="clearLineageGroupFilter">清除筛选</el-button>
    </div>

    <div v-if="generationProgress.visible" class="generation-progress-card animate-up animate-delay-1">
      <div class="generation-progress-head">
        <div>
          <div class="generation-progress-title">{{ generationProgress.title || '学习资源生成进度' }}</div>
          <div class="generation-progress-message">{{ generationProgress.message }}</div>
        </div>
        <div class="generation-progress-actions">
          <el-tag :type="generationStatusTagType()" size="small">{{ generationStatusText() }}</el-tag>
          <el-button
            v-if="generationProgress.status === 'success' || generationProgress.status === 'error'"
            size="small"
            text
            @click="closeGenerationProgress"
          >
            收起
          </el-button>
        </div>
      </div>
      <el-progress
        :percentage="generationProgress.percent"
        :status="generationProgressStatus()"
        :stroke-width="12"
        striped
        striped-flow
      />
      <div class="generation-progress-meta">
        <span v-if="generationProgress.total > 0">
          {{ generationProgress.current }} / {{ generationProgress.total }} 项完成
        </span>
        <span v-else>正在等待后端返回生成阶段</span>
      </div>
      <div v-if="generationProgress.logs.length > 0" class="generation-progress-logs">
        <span v-for="(log, idx) in generationProgress.logs" :key="idx">{{ log }}</span>
      </div>
    </div>

    <div v-if="!selected" class="graph-gen-panel animate-up animate-delay-2">
      <div class="graph-gen-head">
        <div>
          <div class="graph-gen-title">图谱驱动生成</div>
          <div class="graph-gen-desc">从培养方案课程节点和课内知识点出发，一键生成绑定图谱标签的资源包。</div>
        </div>
        <el-button type="primary" :loading="graphPackageLoading" @click="generateGraphPackage">
          生成图谱资源包
        </el-button>
      </div>
      <div class="graph-gen-form">
        <el-select v-model="graphCourseName" placeholder="选择课程节点" clearable filterable style="min-width: 220px" @change="onGraphCourseChange">
          <el-option v-for="c in curriculumCourses" :key="c.id" :label="c.name || c.id" :value="c.id" />
        </el-select>
        <el-select v-model="graphKnowledgePoints" placeholder="选择知识点（可选）" multiple clearable filterable :disabled="!graphCourseName" style="min-width: 260px">
          <el-option v-for="kp in graphKpOptions" :key="kp.id" :label="kp.id" :value="kp.id" />
        </el-select>
        <el-select v-model="graphPackageType" placeholder="资源包类型" style="min-width: 160px">
          <el-option v-for="pkg in graphPackageOptions" :key="pkg" :label="pkg" :value="pkg" />
        </el-select>
      </div>
      <div v-if="graphCourseName && graphKpOptions.length === 0" class="graph-empty-hint">
        当前课程暂未配置课内知识点图谱，将按课程级标签生成资源，不会伪造知识点标签。
      </div>
    </div>

    <!-- 为你推荐区 -->
    <div v-if="recommendItems.length > 0 && !selected" class="recommend-banner animate-up animate-delay-2">
      <div class="recommend-head">
        <span class="recommend-title">为你推荐</span>
        <span class="recommend-hint">基于画像智能匹配</span>
        <el-button size="small" text @click="loadRecommend" style="margin-left:auto">刷新</el-button>
      </div>
      <div class="recommend-list">
        <div v-for="r in recommendItems" :key="r.id" class="recommend-item" @click="viewResource(r)">
          <el-tag :type="typeTag(r.resource_type)" size="small">{{ typeLabel(r.resource_type) }}</el-tag>
          <span class="recommend-item-title">{{ r.title }}</span>
        </div>
      </div>
    </div>

    <!-- 薄弱知识点专项推荐 -->
    <div v-if="weakPointItems.length > 0 && !selected" class="weak-banner animate-up animate-delay-2">
      <div class="weak-banner-head">
        <span class="weak-banner-title">薄弱知识点专项推荐</span>
        <span class="weak-banner-hint">基于你的学习画像和答题记录自动生成</span>
      </div>
      <div class="weak-tags">
        <el-tag
          v-for="item in weakPointItems.slice(0, 8)"
          :key="item.label"
          type="warning"
          size="small"
          class="weak-tag"
          @click="generateQuick(item, 'article')"
        >{{ item.label }} → 生成讲解</el-tag>
        <el-tag
          v-for="item in weakPointItems.slice(0, 4)"
          :key="'q_' + item.label"
          type="danger"
          size="small"
          class="weak-tag"
          @click="generateQuick(item, 'quiz')"
        >{{ item.label }} → 生成题库</el-tag>
      </div>
    </div>

    <div v-if="(!loading && resources.length === 0)" class="starter-panel animate-up animate-delay-2">
      <div class="starter-head">
        <h3>根据你的学习画像推荐</h3>
        <div style="display:flex;gap:8px">
          <el-button type="success" :loading="starterLoading" @click="generateStarterPack">
            一键生成入门资源包
          </el-button>
        </div>
      </div>
      <p class="starter-desc">系统会优先根据你的薄弱课程，自动生成「文章 + 题库」组合资源，帮助你快速开始学习。</p>

      <div v-if="recommendedSeeds.length > 0" class="seed-grid">
        <div v-for="s in recommendedSeeds" :key="s.course + s.topic" class="seed-card">
          <div class="seed-title">{{ s.course }}</div>
          <div class="seed-topic">{{ s.topic }}</div>
          <div class="seed-actions">
            <el-button size="small" @click="generateQuick(s, 'article')">生成文章</el-button>
            <el-button size="small" type="warning" @click="generateQuick(s, 'quiz')">生成题库</el-button>
            <el-button
              size="small"
              type="primary"
              :loading="orchestrateLoading"
              @click="generateOrchestrated(`${s.course}：${s.topic}`, { courseName: isKnownCourse(s.course) ? s.course : '', knowledgePoints: s.topic && s.topic !== s.course ? [s.topic] : [] })"
            >
              协同生成
            </el-button>
          </div>
        </div>
      </div>

      <div v-else class="empty-state">
        <div class="empty-state-icon">📚</div>
        <p class="empty-state-text">尚未检测到可推荐的薄弱课程<br/>可先去学习画像完成建档</p>
      </div>
    </div>

    <div v-if="loading || detailLoading" class="loading-box">
      <div class="plain-loading">
        <el-icon class="is-loading"><component :is="'Loading'" /></el-icon>
        <span>{{ detailLoading ? '加载资源详情...' : '加载资源...' }}</span>
      </div>
    </div>

    <div v-else-if="selected" class="detail-view animate-up animate-delay-2">
      <el-button @click="selected = null" style="margin-bottom: 16px">返回列表</el-button>
      <div class="detail-graph-meta">
        <div class="detail-tags">
          <el-tag :type="typeTag(selected.resource_type)" size="small">{{ typeLabel(selected.resource_type) }}</el-tag>
          <el-tag v-for="course in graphCourseTags(selected)" :key="`course-${course}`" type="success" size="small">{{ course }}</el-tag>
          <el-tag v-for="kp in graphKnowledgeTags(selected)" :key="`kp-${kp}`" type="info" size="small">{{ kp }}</el-tag>
          <el-tag :type="lineageTagType(selected)" size="small" effect="plain">{{ lineageBadge(selected) }}</el-tag>
          <el-tag size="small" effect="plain">{{ statusLabel(selected.learning_status) }}</el-tag>
        </div>
        <el-button
          v-if="selected.learning_status !== 'completed'"
          size="small"
          type="primary"
          @click="completeSelectedResource"
        >
          标记已学完
        </el-button>
      </div>
      <div class="resource-feedback-box">
        <span class="feedback-title">资源反馈</span>
        <el-button
          v-for="item in feedbackOptions"
          :key="item.value"
          size="small"
          :loading="feedbackLoading"
          @click="submitResourceFeedback(item.value)"
        >
          {{ item.label }}
        </el-button>
      </div>
      <ResourceLineagePanel
        v-if="selected?.id"
        :resource-id="selected.id"
        :user-id="userStore.userId"
        @open="viewResourceById"
        @filter-group="applyLineageGroupFilter"
      />
      <div v-if="selected.resource_type === 'article'" class="article-quiz-box">
        <div>
          <strong>课后检测</strong>
          <p>根据本文生成带知识点标签的测试题，提交后按题目级正确率更新知识点掌握度。</p>
        </div>
        <el-button type="primary" :loading="articleQuizLoading" @click="generateQuizFromSelectedArticle">
          根据本文生成测试题
        </el-button>
      </div>
      <QuizCard v-if="selected.resource_type === 'quiz'" :content="selected.content" :resourceId="selected.id" :userId="userStore.userId" />
      <MindMapViewer v-else-if="selected.resource_type === 'mindmap'" :markdown="selected.content?.markdown || ''" />
      <PptViewer
        v-else-if="selected.resource_type === 'ppt'"
        :content="selected.content"
        :resource-id="selected.id"
        :user-id="userStore.userId"
        @updated="updateSelectedContent"
      />
      <div v-else-if="selected.resource_type === 'anime'" class="anime-viewer">
        <div class="anime-toolbar">
          <div>
            <strong>可视化动画预览</strong>
            <p>动画以沙箱 iframe 方式运行，源文件已保存到学习资源。</p>
          </div>
        </div>
        <iframe
          v-if="animeHtmlContent(selected.content)"
          :srcdoc="animeHtmlContent(selected.content)"
          sandbox="allow-scripts"
          class="anime-iframe"
        />
        <div v-else class="anime-empty">该动画资源缺少可预览的 HTML 内容。</div>
      </div>
      <div v-else-if="selected.resource_type === 'video'" class="video-viewer">
        <div v-if="biliPlayerSrc(selected.content?.url)" class="video-embed-wrap">
          <iframe
            :src="biliPlayerSrc(selected.content?.url)"
            scrolling="no" border="0" frameborder="no" framespacing="0" allowfullscreen="true"
            class="bili-iframe"
          />
        </div>
        <div v-else class="video-fallback">
          <p>{{ selected.content?.reason }}</p>
          <a :href="selected.content?.url">在 B 站打开</a>
        </div>
        <div class="video-meta">
          <span class="video-source">{{ selected.content?.source }}</span>
          <p class="video-reason">{{ selected.content?.reason }}</p>
        </div>
      </div>
      <div v-else class="text-content markdown-body" v-html="renderMarkdown(selected.content)" @click="handleDetailClick"></div>
    </div>

    <div v-else-if="resources.length > 0" class="resource-list animate-up animate-delay-2">
      <div v-for="r in resources" :key="r.id" class="resource-card animate-up" @click="viewResource(r)">
        <div class="card-header">
          <el-checkbox
            v-if="manageMode"
            :model-value="selectedIds.includes(r.id)"
            @change="() => toggleSelect(r.id)"
            @click.stop
          />
          <el-tag v-if="r.pinned" type="danger" size="small">置顶</el-tag>
          <el-tag :type="typeTag(r.resource_type)" size="small">{{ typeLabel(r.resource_type) }}</el-tag>
          <span class="card-date">{{ r.created_at?.slice(0, 10) }}</span>
        </div>
        <h4 class="card-title">{{ r.title }}</h4>
        <div class="graph-tags">
          <el-tag v-for="course in graphCourseTags(r).slice(0, 2)" :key="`course-${r.id}-${course}`" size="small" type="success">{{ course }}</el-tag>
          <el-tag v-for="kp in graphKnowledgeTags(r).slice(0, 2)" :key="`kp-${r.id}-${kp}`" size="small" type="info">{{ kp }}</el-tag>
          <el-tag :type="lineageTagType(r)" size="small" effect="plain">{{ lineageBadge(r) }}</el-tag>
          <el-tag size="small" effect="plain">{{ statusLabel(r.learning_status) }}</el-tag>
        </div>
        <div class="card-deco">📘</div>
      </div>
    </div>

    <div v-else class="empty-box animate-up animate-delay-2">
      <div class="empty-state">
        <div class="empty-state-icon">📚</div>
        <p class="empty-state-text">还没有学习资源<br/>尝试生成或刷新看看吧</p>
      </div>
    </div>

    <div v-if="!selected && !loading && totalResources > pageSize" class="pagination-box animate-up animate-delay-3">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="totalResources"
        layout="prev, pager, next, total"
        @current-change="onPageChange"
      />
    </div>

    <el-dialog v-model="showGenDialog" title="生成学习资源" width="480px">
      <el-form label-width="80px">
        <el-form-item label="主题">
          <el-input v-model="genTopic" placeholder="例如：排序算法" />
        </el-form-item>
        <el-form-item label="课程">
          <el-select v-model="genCourseName" placeholder="选择课程节点（可选）" clearable filterable style="width: 100%" @change="onGenCourseChange">
            <el-option v-for="c in curriculumCourses" :key="c.id" :label="c.id" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="知识点">
          <el-select v-model="genKnowledgePoints" placeholder="选择知识点标签（可多选）" multiple clearable filterable :disabled="!genCourseName" style="width: 100%">
            <el-option v-for="kp in genKpOptions" :key="kp.id" :label="kp.id" :value="kp.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="资源类型">
          <el-checkbox-group v-model="genTypes">
            <el-checkbox v-for="o in genTypeOptions" :key="o.value" :value="o.value">{{ o.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item v-if="genTypes.includes('code') || genTypes.includes('quiz')" label="编程语言">
          <el-select v-model="genCodeLanguage" placeholder="选择语言" style="width: 160px">
            <el-option v-for="l in codeLangOptions" :key="l.value" :label="l.label" :value="l.value" />
          </el-select>
        </el-form-item>
        <template v-if="genTypes.includes('quiz')">
          <el-form-item label="题目数量">
            <el-input-number v-model="genQuestionCount" :min="3" :max="30" :step="1" />
            <span style="margin-left:8px;color:#948A80;font-size:12px">建议 5~15 题</span>
          </el-form-item>
          <el-form-item label="题库难度">
            <el-radio-group v-model="genDifficulty">
              <el-radio v-for="d in difficultyOptions" :key="d" :value="d">{{ d }}</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="题目类型">
            <el-checkbox-group v-model="genQuestionTypes">
              <el-checkbox value="single_choice">选择题</el-checkbox>
              <el-checkbox value="fill_blank">填空题</el-checkbox>
              <el-checkbox value="coding">编程题</el-checkbox>
            </el-checkbox-group>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showGenDialog = false">取消</el-button>
        <el-button
          type="success"
          :loading="orchestrateLoading"
          @click="() => { if (!genTopic.trim()) { ElMessage.warning('请输入主题'); return } showGenDialog = false; generateOrchestrated(genTopic.trim(), { courseName: genCourseName, knowledgePoints: genKnowledgePoints }) }"
        >
          多智能体协同生成
        </el-button>
        <el-button type="primary" :loading="genLoading" @click="startGenerate">生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.resources-view { max-width: 1280px; padding: 28px 20px 34px; margin: 0 auto; box-sizing: border-box; background: linear-gradient(180deg, #F9D9B8 0%, #FFF5EB 45%, #FFFBF5 100%); }
.toolbar { display: flex; align-items: center; margin-bottom: 20px; padding-top: 4px; flex-wrap: wrap; gap: 4px; }
.loading-box { height: 200px; }

.lineage-filter-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin: -8px 0 16px;
  padding: 10px 14px;
  color: #8a5a28;
  background: #fff7eb;
  border: 1px solid #f0ddc5;
  border-radius: 12px;
}

.generation-progress-card {
  background: #FFFBF5;
  border: 1.5px solid #E8C29C;
  border-radius: 14px;
  padding: 14px 16px;
  margin-bottom: 18px;
  box-shadow: 0 4px 16px rgba(58, 51, 46, 0.08);
}
.generation-progress-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}
.generation-progress-title {
  font-size: 15px;
  font-weight: 700;
  color: #3A332E;
  margin-bottom: 4px;
}
.generation-progress-message {
  color: #6B635C;
  font-size: 13px;
  line-height: 1.5;
}
.generation-progress-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.generation-progress-meta {
  display: flex;
  justify-content: space-between;
  color: #948A80;
  font-size: 12px;
  margin-top: 8px;
}
.generation-progress-logs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.generation-progress-logs span {
  max-width: 100%;
  padding: 3px 8px;
  color: #7C5C3C;
  background: #FFF5EB;
  border: 1px solid #EFE6DC;
  border-radius: 999px;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.starter-panel {
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 12px;
  padding: 18px;
  margin-bottom: 20px;
}
.starter-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.starter-head h3 { margin: 0; color: #3A332E; font-size: 20px; font-weight: 500; }
.starter-desc { margin: 0 0 14px; color: #6B635C; font-size: 13px; line-height: 1.7; }

.graph-gen-panel {
  margin-bottom: 16px;
  background: #FFFBF5;
  border: 1.5px solid #E8C29C;
  border-radius: 14px;
  padding: 16px;
  box-shadow: 0 3px 12px rgba(58,51,46,0.06);
}
.graph-gen-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 12px;
}
.graph-gen-title { font-size: 16px; font-weight: 700; color: #3A332E; margin-bottom: 4px; }
.graph-gen-desc { color: #6B635C; font-size: 13px; }
.graph-gen-form { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.graph-empty-hint { margin-top: 10px; color: #9A6A2F; font-size: 13px; background: #fff7e6; border: 1px solid #f5d29a; border-radius: 8px; padding: 8px 10px; }

.seed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.seed-card {
  background: #FFFBF5;
  border: 1.5px solid #EFE6DC;
  border-radius: 12px;
  padding: 12px;
}
.seed-title { font-weight: 500; color: #3A332E; margin-bottom: 4px; }
.seed-topic { color: #6B635C; font-size: 13px; min-height: 40px; line-height: 1.5; }
.seed-actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }

.weak-banner {
  background: rgba(253, 246, 236, 0.9);
  border: 1px solid rgba(235, 177, 95, 0.4);
  border-radius: 12px;
  padding: 14px 18px;
  margin-bottom: 18px;
}
.weak-banner-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.weak-banner-title { font-weight: 500; color: #DBA878; font-size: 14px; }
.weak-banner-hint { font-size: 12px; color: #948A80; }
.weak-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.weak-tag { cursor: pointer; }
.weak-tag:hover { opacity: 0.85; transform: scale(1.03); }

.recommend-banner {
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 12px;
  padding: 12px 16px;
  margin-bottom: 18px;
}
.recommend-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.recommend-title { font-weight: 500; color: #3A332E; font-size: 14px; }
.recommend-hint { font-size: 12px; color: #948A80; }
.recommend-list { display: flex; flex-wrap: wrap; gap: 8px; }
.recommend-item {
  display: flex; align-items: center; gap: 6px;
  background: #FFF5EB; border: 1px solid #EFE6DC;
  border-radius: 8px; padding: 4px 10px;
  cursor: pointer; font-size: 13px; transition: all 0.2s;
}
.recommend-item:hover { border-color: #E8C29C; box-shadow: 0 2px 8px rgba(58,51,46,0.08); }
.recommend-item-title { color: #3A332E; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.resource-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }

.resource-card {
  display: flex; flex-direction: column; gap: 8px;
  min-height: 83px;
  padding: 14px 14px;
  border: 1.5px solid #EFE6DC;
  border-radius: 12px;
  background: #FFFBF5;
  cursor: pointer;
  transition: all 0.2s;
}
.resource-card:hover {
  border-color: #E8C29C;
  background: linear-gradient(135deg, #FFFBF5, color-mix(in srgb, #E8C29C 8%, #FFFBF5));
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(58,51,46,0.08);
}

.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-date { font-size: 11px; color: #948A80; }
.card-title { margin: 0; color: #3A332E; font-size: 14px; font-weight: 500; line-height: 1.5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.graph-tags { display: flex; gap: 6px; flex-wrap: wrap; min-height: 24px; }
.detail-graph-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.detail-tags { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.resource-feedback-box {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #FFFBF5;
  border: 1px dashed #E8C29C;
  border-radius: 10px;
}
.feedback-title {
  font-size: 12px;
  color: #7C5C3C;
  margin-right: 2px;
}

.pagination-box { display: flex; justify-content: center; margin-top: 24px; }

.text-content {
  background: #FFF5EB;
  color: #3A332E;
  border-radius: 4px 12px 12px 12px;
  border: 1px solid #EFE6DC;
  padding: 12px 16px;
  line-height: 1.6;
  word-break: break-word;
  font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 14px;
  font-weight: normal;
}
.text-content :deep(h1),
.text-content :deep(h2),
.text-content :deep(h3) { margin: 12px 0 8px; font-weight: normal; color: #3A332E; font-family: inherit; font-size: inherit; }
.text-content :deep(p) { margin: 10px 0; color: #3A332E; font-family: inherit; }
.text-content :deep(ul),
.text-content :deep(ol) { padding-left: 20px; margin: 10px 0; color: #3A332E; font-family: inherit; }
.text-content :deep(li) { margin: 6px 0; line-height: 1.7; color: #3A332E; font-family: inherit; }
.text-content :deep(code) { background: #f5ebdf; padding: 2px 6px; border-radius: 3px; font-size: inherit; font-family: inherit; color: #3A332E; }
.text-content :deep(strong),
.text-content :deep(em),
.text-content :deep(small),
.text-content :deep(td),
.text-content :deep(th) { color: #3A332E; font-family: inherit; font-weight: normal; }
.text-content :deep(pre) { background: #2f3541; color: #f0f4f9; padding: 14px 18px; border-radius: 0 0 6px 6px; overflow-x: auto; margin: 0; }
.text-content :deep(pre code) { background: none; padding: 0; color: inherit; font-size: 13px; white-space: pre; tab-size: 4; -moz-tab-size: 4; }
.text-content :deep(.code-block-wrapper) { margin: 12px 0; border-radius: 6px; overflow: hidden; }
.text-content :deep(.code-header) { display: flex; justify-content: space-between; align-items: center; background: #21252b; padding: 6px 14px; border-radius: 6px 6px 0 0; }
.text-content :deep(.code-lang) { font-size: 11px; color: #3A332E; text-transform: uppercase; }
.text-content :deep(.code-copy-btn) { font-size: 11px; color: #3A332E; cursor: pointer; padding: 2px 8px; border-radius: 3px; transition: all 0.15s; user-select: none; }
.text-content :deep(.code-copy-btn:hover) { color: #fff; background: rgba(255,255,255,0.1); }
.text-content :deep(blockquote) { border-left: 3px solid #e35749; padding: 4px 12px; margin: 8px 0; color: #3A332E; background: rgba(227,87,73,0.08); }
.text-content :deep(table) { border-collapse: collapse; margin: 8px 0; width: 100%; }
.text-content :deep(th),
.text-content :deep(td) { border: 1px solid #EFE6DC; padding: 6px 10px; text-align: left; }
.text-content :deep(th) { background: #FFF5EB; font-weight: 600; }
.text-content :deep(strong) { font-weight: 700; }
.text-content :deep(a) { color: #3A332E; text-decoration: none; }
.text-content :deep(a:hover) { text-decoration: underline; }
.text-content :deep(.math-block) { display: block; text-align: center; margin: 14px 0; overflow-x: auto; }
.text-content :deep(.math-inline) { padding: 0 2px; }

.video-viewer {
  background: #FFFBF5;
  border-radius: 12px;
  border: 1px solid #EFE6DC;
  overflow: hidden;
}
.video-embed-wrap { position: relative; width: 100%; padding-top: 56.25%; background: #000; }
.bili-iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none; }
.video-fallback { padding: 32px; text-align: center; }
.video-fallback a { color: #DBA878; text-decoration: none; font-size: 15px; }
.video-meta { padding: 14px 18px; }
.video-source { font-size: 12px; color: #948A80; }
.video-reason { margin: 6px 0 0; color: #3A332E; font-size: 14px; line-height: 1.6; }
.anime-viewer {
  background: #FFFBF5;
  border-radius: 12px;
  border: 1px solid #EFE6DC;
  overflow: hidden;
}
.anime-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid #EFE6DC;
  background: #fff8ef;
}
.anime-toolbar strong { color: #3A332E; }
.anime-toolbar p { margin: 4px 0 0; color: #7A6A5C; font-size: 13px; }
.anime-iframe {
  width: 100%;
  height: min(72vh, 760px);
  min-height: 560px;
  border: none;
  background: #fff;
}
.anime-empty { padding: 48px; text-align: center; color: #948A80; }

@keyframes floatUpIn {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-up {
  opacity: 0;
  animation: floatUpIn 0.55s cubic-bezier(0.2, 0.75, 0.22, 1) forwards;
}
.animate-delay-1 { animation-delay: 0.08s; }
.animate-delay-2 { animation-delay: 0.16s; }
.animate-delay-3 { animation-delay: 0.28s; }
.animate-delay-4 { animation-delay: 0.40s; }

.resource-card.animate-up { animation-duration: 0.4s; }
.resource-card:nth-child(1) { animation-delay: 0.10s; }
.resource-card:nth-child(2) { animation-delay: 0.14s; }
.resource-card:nth-child(3) { animation-delay: 0.18s; }
.resource-card:nth-child(4) { animation-delay: 0.22s; }
.resource-card:nth-child(5) { animation-delay: 0.26s; }
.resource-card:nth-child(6) { animation-delay: 0.30s; }
.resource-card:nth-child(7) { animation-delay: 0.34s; }
.resource-card:nth-child(8) { animation-delay: 0.38s; }
.resource-card:nth-child(9) { animation-delay: 0.42s; }
.resource-card:nth-child(10) { animation-delay: 0.46s; }
.resource-card:nth-child(11) { animation-delay: 0.50s; }
.resource-card:nth-child(12) { animation-delay: 0.54s; }

@media (max-width: 1024px) {
  .resource-list { grid-template-columns: repeat(2, 1fr); gap: 12px; }
}
@media (max-width: 640px) {
  .resource-list { grid-template-columns: 1fr; gap: 12px; }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 40px 20px;
}
.empty-state-icon {
  width: 70px;
  height: 70px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 22px;
  background: rgba(64, 158, 255, 0.08);
  font-size: 34px;
}
.empty-state-text {
  margin: 0;
  font-size: 14px;
  color: #948A80;
  text-align: center;
  line-height: 1.8;
}
.plain-loading {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #948A80;
}
.card-deco {
  display: flex;
  justify-content: flex-end;
  opacity: 0.25;
  margin-top: auto;
  font-size: 18px;
}
.article-quiz-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  margin-bottom: 16px;
  border: 1px solid rgba(64, 158, 255, 0.2);
  border-radius: 12px;
  background: rgba(64, 158, 255, 0.06);
}
.article-quiz-box strong {
  color: #3A332E;
}
.article-quiz-box p {
  margin: 4px 0 0;
  color: #6B635C;
  font-size: 13px;
  line-height: 1.6;
}
</style>
