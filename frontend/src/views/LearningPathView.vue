<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useUserStore } from '../stores/user'

const userStore = useUserStore()
const router = useRouter()

type StepStatus = 'pending' | 'learning' | 'done'
type MasteryStatus = 'unverified' | 'verified' | 'failed'
type PathStatus = 'active' | 'completed' | 'archived' | 'empty'

interface StepResource {
  id: number
  title: string
  type: string
}

interface PptSession {
  session_id?: string
  topic?: string
  resource_id?: number
}

interface StepEvidence {
  learned_at?: string
  quiz_record_id?: number
  score?: number
  verified_at?: string
}

interface RemediationQuestion {
  question_id?: number | string
  question?: string
  type?: string
  knowledge_points?: string[]
  user_answer?: string
  correct_answer?: string
  explanation?: string
}

interface RemediationAttempt {
  attempt_no: number
  failed_quiz_record_id?: number
  failed_check_resource_id?: number
  failed_score?: number
  passing_score?: number
  weak_knowledge_points?: string[]
  wrong_questions?: RemediationQuestion[]
  diagnosis?: string
  resource_ids?: number[]
  resources?: StepResource[]
  resource_failures?: Array<{ type: string; error: string }>
  new_check_resource_id?: number | null
  created_at?: string
}

interface PathStep {
  order: number
  title: string
  description: string
  course_name?: string
  knowledge_points?: string[]
  relation_context?: string
  resource_types?: string[]
  resource_ids?: number[]
  resources?: StepResource[]
  ppt_sessions?: PptSession[]
  resource_failures?: Array<{ type: string; error: string }>
  duration_estimate?: string
  checkpoint?: string
  completion_rule?: string
  status: StepStatus
  mastery_status?: MasteryStatus
  passing_score?: number
  check_resource_id?: number | null
  evidence?: StepEvidence
  completed_at?: string | null
  generation_note?: string
  remediation_attempts?: RemediationAttempt[]
}

interface CoursePath {
  id: number
  course_name: string
  display_name?: string
  steps: PathStep[]
  total_steps: number
  done_steps: number
  learning_steps?: number
  progress: number
  status: PathStatus
  is_archived?: boolean
  archived_at?: string | null
  path_scope?: 'course' | 'knowledge_point' | 'weak_point'
  coverage_ratio?: number
  covered_knowledge_points?: string[]
  knowledge_points?: string[]
  next_step?: PathStep | null
  created_at: string | null
}

interface RecommendedCourse {
  course_name: string
  status: string
  status_label: string
  mastery: number
  mastery_percent: number
  semester: string | number
  category: string
  has_kp_graph: boolean
  reason: string
  priority: number
}

const paths = ref<CoursePath[]>([])
const selectedPath = ref<CoursePath | null>(null)
const loading = ref(false)
const generatingResources = ref(false)
const checkingStep = ref<number | null>(null)
const verifyingStep = ref<number | null>(null)
const remediationDrawerVisible = ref(false)
const remediationLoading = ref(false)
const remediationGenerating = ref(false)
const remediationChecking = ref(false)
const remediatingStep = ref<PathStep | null>(null)
const remediationData = ref<any>(null)
const quickCourseName = ref('')
const quickKnowledgePoints = ref('')
const quickGenerating = ref(false)
const managingPathId = ref<number | null>(null)

const recommendations = ref<RecommendedCourse[]>([])
const recommendLoading = ref(false)
const generatingFromRec = ref<string | null>(null)

async function loadRecommendations() {
  if (!userStore.userId) return
  recommendLoading.value = true
  try {
    const resp = await api.get('/path/course/recommend', { params: { user_id: userStore.userId, limit: 6 } })
    recommendations.value = resp.data.items || []
  } catch {
    // 推荐加载失败不打扰用户，静默忽略
  } finally {
    recommendLoading.value = false
  }
}

async function generateFromRecommend(course: RecommendedCourse) {
  if (!userStore.userId) return
  generatingFromRec.value = course.course_name
  quickCourseName.value = course.course_name
  try {
    const resp = await api.post('/path/course/generate', null, {
      params: { user_id: userStore.userId, course_name: course.course_name },
      timeout: 120000,
    })
    await loadPaths()
    await loadRecommendations()
    selectedPath.value = paths.value.find((p) => p.id === resp.data.id) || paths.value[0] || null
    quickCourseName.value = ''
    ElMessage.success(`已为「${course.course_name}」生成学习路径`)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '生成学习路径失败，请稍后重试')
  } finally {
    generatingFromRec.value = null
  }
}

function recStatusType(status: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'learning') return 'success'
  if (status === 'weak') return 'danger'
  return 'warning'
}

const nextStepOrder = computed(() => {
  const pending = selectedPath.value?.steps?.find((step) => step.status !== 'done')
  return pending?.order ?? -1
})

const coveredPoints = computed(() => selectedPath.value?.covered_knowledge_points || selectedPath.value?.knowledge_points || [])

function scopeLabel(scope?: string) {
  const map: Record<string, string> = {
    course: '课程路径',
    knowledge_point: '知识点专项',
    weak_point: '薄弱点补强',
  }
  return map[scope || 'course'] || '课程路径'
}

function statusLabel(status: PathStatus) {
  const map: Record<string, string> = {
    active: '进行中',
    completed: '已完成',
    archived: '已归档',
    empty: '暂无路径',
  }
  return map[status] || status
}

function stepStatusLabel(step: PathStep) {
  if (step.status === 'done' && step.mastery_status === 'verified') return '已验收'
  if (step.status === 'learning') return '已学习'
  return '待学习'
}

function masteryLabel(status?: MasteryStatus) {
  const map: Record<string, string> = {
    verified: '检查通过',
    failed: '检查未通过',
    unverified: '未验收',
  }
  return map[status || 'unverified'] || '未验收'
}

function masteryTag(status?: MasteryStatus) {
  if (status === 'verified') return 'success'
  if (status === 'failed') return 'danger'
  return 'info'
}

function progressColor(progress: number) {
  if (progress >= 100) return '#98C9B3'
  if (progress >= 60) return '#DBA878'
  if (progress >= 30) return '#E8C29C'
  return '#F2B8A2'
}

function pathDisplayName(path: CoursePath | null | undefined) {
  return path?.display_name || path?.course_name || ''
}

function resourceTypeLabel(type: string) {
  const map: Record<string, string> = {
    article: '文章',
    quiz: '题库',
    mindmap: '思维导图',
    code: '代码',
    anime: '动画',
    video: '视频',
    ppt: 'PPT课件',
  }
  return map[type] || type
}

function resourceTypeTag(type: string) {
  const map: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = {
    article: '',
    quiz: 'warning',
    mindmap: 'info',
    code: 'success',
    anime: 'success',
    video: '',
    ppt: 'danger',
  }
  return map[type] || 'info'
}

function formatTime(value?: string | null) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString()
}

function formatPercent(value?: number) {
  return `${Math.round((value || 0) * 100)}%`
}

function stepCardClass(step: PathStep) {
  return {
    'step-card': true,
    done: step.status === 'done',
    learning: step.status === 'learning',
    failed: step.mastery_status === 'failed',
    current: step.order === nextStepOrder.value,
  }
}

function applyPathPayload(data: any) {
  if (!selectedPath.value || !data?.id) return
  const updated: CoursePath = {
    ...selectedPath.value,
    ...data,
    steps: data.steps || selectedPath.value.steps || [],
  }
  selectedPath.value = updated
  const index = paths.value.findIndex((path) => path.id === updated.id)
  if (index >= 0) paths.value[index] = updated
}

async function loadPaths() {
  if (!userStore.userId) return
  loading.value = true
  try {
    const resp = await api.get('/path/course/list', { params: { user_id: userStore.userId } })
    paths.value = resp.data.items || []
    if (paths.value.length > 0) {
      const currentId = selectedPath.value?.id
      selectedPath.value = paths.value.find((path) => path.id === currentId) || paths.value[0]
    } else {
      selectedPath.value = null
    }
  } catch {
    ElMessage.error('加载学习路径失败')
  } finally {
    loading.value = false
  }
}

async function quickGenerate() {
  if (!userStore.userId) return
  if (!quickCourseName.value.trim()) {
    ElMessage.warning('请先输入课程名称')
    return
  }
  quickGenerating.value = true
  try {
    const resp = await api.post('/path/course/generate', null, {
      params: {
        user_id: userStore.userId,
        course_name: quickCourseName.value.trim(),
        knowledge_points: quickKnowledgePoints.value.trim() || undefined,
      },
      timeout: 120000,
    })
    await loadPaths()
    selectedPath.value = paths.value.find((path) => path.id === resp.data.id) || paths.value[0] || null
    quickCourseName.value = ''
    quickKnowledgePoints.value = ''
    ElMessage.success('已生成图谱化学习路径')
  } catch {
    ElMessage.error('生成学习路径失败，请稍后重试')
  } finally {
    quickGenerating.value = false
  }
}

async function generateResources() {
  if (!selectedPath.value) return
  generatingResources.value = true
  try {
    const resp = await api.post(`/path/course/${selectedPath.value.id}/generate-resources`, null, { timeout: 180000 })
    applyPathPayload(resp.data)
    ElMessage.success('已生成步骤配套资源')
  } catch {
    ElMessage.error('生成步骤资源失败')
  } finally {
    generatingResources.value = false
  }
}

async function setLearning(step: PathStep, status: 'pending' | 'learning') {
  if (!selectedPath.value) return
  try {
    const resp = await api.patch(`/path/course/${selectedPath.value.id}/step/${step.order}`, null, {
      params: { status },
    })
    applyPathPayload(resp.data)
    ElMessage.success(status === 'learning' ? '已记录学习进度，掌握度需通过检查题验证' : '已重置为待学习')
  } catch {
    ElMessage.error('更新步骤状态失败')
  }
}

async function createCheck(step: PathStep) {
  if (!selectedPath.value) return
  checkingStep.value = step.order
  try {
    const force = Boolean(step.check_resource_id)
    const resp = await api.post(`/path/course/${selectedPath.value.id}/step/${step.order}/check`, null, {
      params: { force },
      timeout: 120000,
    })
    if (resp.data?.ok === false) {
      ElMessage.error(resp.data.error || '生成检查题失败')
      return
    }
    applyPathPayload(resp.data)
    ElMessage.success(force ? '已重新生成步骤检查题' : '已生成步骤检查题')
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.response?.data?.error || '生成检查题失败')
  } finally {
    checkingStep.value = null
  }
}

async function verifyStep(step: PathStep) {
  if (!selectedPath.value) return
  verifyingStep.value = step.order
  try {
    const resp = await api.post(`/path/course/${selectedPath.value.id}/step/${step.order}/verify`)
    applyPathPayload(resp.data)
    if (resp.data.passed) {
      ElMessage.success(`检查通过：${Math.round((resp.data.score || 0) * 100)}%`)
    } else if (resp.data.score === null || resp.data.score === undefined) {
      ElMessage.warning(resp.data.message || '请先完成检查题')
    } else {
      ElMessage.warning(`检查未通过：${Math.round((resp.data.score || 0) * 100)}%，请继续补弱`)
    }
  } catch {
    ElMessage.error('查看检查结果失败')
  } finally {
    verifyingStep.value = null
  }
}

function openResource(resource: StepResource) {
  if (!resource?.id) return
  router.push({
    path: '/resources',
    query: { open: String(resource.id), type: resource.type },
  })
}

function openCheck(step: PathStep) {
  if (!step.check_resource_id) return
  router.push({
    path: '/resources',
    query: { open: String(step.check_resource_id), type: 'quiz' },
  })
}

function openKnowledgePoint(point: string) {
  if (!selectedPath.value) return
  router.push({
    path: '/resources',
    query: {
      course: selectedPath.value.course_name,
      kp: point,
      package: '知识点补弱',
    },
  })
}

function currentRemediationAttempt(): RemediationAttempt | null {
  return remediationData.value?.attempt || remediatingStep.value?.remediation_attempts?.slice(-1)[0] || null
}

async function renamePath(path: CoursePath) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新的路径名称', '重命名学习路径', {
      inputValue: pathDisplayName(path),
      inputPlaceholder: '例如：概率论期末复习路径',
      inputValidator: (value) => {
        const text = String(value || '').trim()
        if (!text) return '路径名称不能为空'
        if (text.length > 80) return '路径名称不能超过 80 个字符'
        return true
      },
      confirmButtonText: '保存',
      cancelButtonText: '取消',
    })
    managingPathId.value = path.id
    const resp = await api.patch(`/path/course/${path.id}/meta`, {
      display_name: String(value || '').trim(),
    })
    const updated = resp.data as CoursePath
    const index = paths.value.findIndex((item) => item.id === path.id)
    if (index >= 0) paths.value[index] = { ...paths.value[index], ...updated }
    if (selectedPath.value?.id === path.id) selectedPath.value = { ...selectedPath.value, ...updated }
    ElMessage.success('已重命名学习路径')
  } catch (err: any) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err?.response?.data?.detail || '重命名失败')
  } finally {
    managingPathId.value = null
  }
}

async function archivePath(path: CoursePath) {
  try {
    await ElMessageBox.confirm(
      `归档「${pathDisplayName(path)}」后，默认路径列表将不再显示它。已生成资源和掌握度不会被删除。`,
      '归档学习路径',
      { type: 'warning', confirmButtonText: '归档', cancelButtonText: '取消' },
    )
    managingPathId.value = path.id
    await api.patch(`/path/course/${path.id}/archive`)
    paths.value = paths.value.filter((item) => item.id !== path.id)
    selectedPath.value = selectedPath.value?.id === path.id ? paths.value[0] || null : selectedPath.value
    ElMessage.success('已归档学习路径')
  } catch (err: any) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err?.response?.data?.detail || '归档失败')
  } finally {
    managingPathId.value = null
  }
}

async function deletePath(path: CoursePath) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${pathDisplayName(path)}」吗？此操作只删除路径记录，不删除已生成的学习资源、题库记录和掌握度。`,
      '删除学习路径',
      { type: 'error', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    managingPathId.value = path.id
    await api.delete(`/path/course/${path.id}`)
    paths.value = paths.value.filter((item) => item.id !== path.id)
    selectedPath.value = selectedPath.value?.id === path.id ? paths.value[0] || null : selectedPath.value
    ElMessage.success('已删除学习路径')
  } catch (err: any) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err?.response?.data?.detail || '删除失败')
  } finally {
    managingPathId.value = null
  }
}

function handlePathCommand(command: string, path: CoursePath) {
  if (command === 'rename') renamePath(path)
  if (command === 'archive') archivePath(path)
  if (command === 'delete') deletePath(path)
}

function remediationResources() {
  const attempt = currentRemediationAttempt()
  return attempt?.resources || []
}

async function remediateStep(step: PathStep) {
  if (!selectedPath.value) return
  remediatingStep.value = step
  remediationData.value = null
  remediationDrawerVisible.value = true
  remediationLoading.value = true
  try {
    const resp = await api.post(
      `/path/course/${selectedPath.value.id}/step/${step.order}/remediate`,
      null,
      { params: { generate_resources: false } }
    )
    if (resp.data?.ok === false) {
      ElMessage.warning(resp.data.error || '请先完成检查题后再继续补弱')
      remediationData.value = resp.data
      return
    }
    applyPathPayload(resp.data)
    remediatingStep.value = resp.data.step || step
    remediationData.value = resp.data
  } catch {
    ElMessage.error('加载补弱诊断失败')
  } finally {
    remediationLoading.value = false
  }
}

async function generateRemediationResources() {
  if (!selectedPath.value || !remediatingStep.value) return
  remediationGenerating.value = true
  try {
    const resp = await api.post(
      `/path/course/${selectedPath.value.id}/step/${remediatingStep.value.order}/remediate`,
      null,
      { params: { generate_resources: true }, timeout: 120000 }
    )
    if (resp.data?.ok === false) {
      ElMessage.warning(resp.data.error || '生成补弱资源失败')
      remediationData.value = resp.data
      return
    }
    applyPathPayload(resp.data)
    remediatingStep.value = resp.data.step || remediatingStep.value
    remediationData.value = resp.data
    const resources = resp.data?.attempt?.resources || []
    ElMessage.success(resources.length ? '已生成本轮补弱资源' : '已记录本轮补弱，可重新生成检查题')
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.response?.data?.error || '生成补弱资源失败')
  } finally {
    remediationGenerating.value = false
  }
}

async function createRemediationCheck() {
  if (!selectedPath.value || !remediatingStep.value) return
  remediationChecking.value = true
  try {
    const resp = await api.post(
      `/path/course/${selectedPath.value.id}/step/${remediatingStep.value.order}/check`,
      null,
      { params: { force: true }, timeout: 120000 }
    )
    if (resp.data?.ok === false) {
      ElMessage.error(resp.data.error || '生成新检查题失败')
      return
    }
    applyPathPayload(resp.data)
    remediatingStep.value = resp.data.step || remediatingStep.value
    if (remediationData.value) {
      remediationData.value.step = resp.data.step
      remediationData.value.new_check_resource_id = resp.data.resource?.id
    }
    ElMessage.success('已生成新一轮检查题，请完成后再查看检查结果')
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.response?.data?.error || '生成新检查题失败')
  } finally {
    remediationChecking.value = false
  }
}

onMounted(() => {
  loadPaths()
  loadRecommendations()
})

watch(
  () => userStore.userId,
  () => {
    loadPaths()
    loadRecommendations()
  }
)
</script>

<template>
  <div class="path-page">
    <section class="hero-card">
      <div>
        <p class="eyebrow">学习路径</p>
        <h2>图谱驱动的课程学习计划</h2>
        <p class="hero-desc">
          路径步骤现在采用“学习进度 + 检查验收”机制。手动记录只代表学过，知识点掌握度由检查题和题目级正确率更新。
        </p>
      </div>
      <div class="quick-create">
        <el-input v-model="quickCourseName" placeholder="输入课程名称，例如：离散数学（2-2）" clearable />
        <el-input v-model="quickKnowledgePoints" placeholder="可选：指定知识点，多个用逗号分隔" clearable />
        <el-button type="primary" :loading="quickGenerating" @click="quickGenerate">生成路径</el-button>
      </div>
    </section>

    <el-alert
      class="mastery-rule-alert"
      type="warning"
      show-icon
      :closable="false"
      title="掌握度只由题目正确率自动更新；标记已学习只记录进度，提交检查题后才会更新知识点掌握度。"
    />

    <section v-if="recommendations.length || recommendLoading" class="recommend-card">
      <div class="recommend-header">
        <div>
          <p class="eyebrow">智能推荐</p>
          <h3>不知道从哪门课开始？试试这些</h3>
          <p class="muted">基于你的专业、当前学期和知识点掌握度筛选出最适合现在学的课程。</p>
        </div>
      </div>
      <el-skeleton v-if="recommendLoading" :rows="3" animated />
      <div v-else class="recommend-grid">
        <article
          v-for="course in recommendations"
          :key="course.course_name"
          class="recommend-item"
          :class="{ 'no-graph': !course.has_kp_graph }"
        >
          <div class="recommend-item-head">
            <div class="recommend-title">
              <strong>{{ course.course_name }}</strong>
              <el-tag size="small" :type="recStatusType(course.status)">{{ course.status_label }}</el-tag>
            </div>
            <span class="recommend-meta">第 {{ course.semester }} 学期 · {{ course.category }}</span>
          </div>
          <p class="recommend-reason">{{ course.reason }}</p>
          <div v-if="course.has_kp_graph" class="recommend-mastery">
            <span class="muted">当前掌握度</span>
            <el-progress
              :percentage="course.mastery_percent"
              :stroke-width="6"
              :color="progressColor(course.mastery_percent)"
              :show-text="false"
            />
            <span class="mastery-value">{{ course.mastery_percent }}%</span>
          </div>
          <el-button
            type="primary"
            plain
            size="small"
            :loading="generatingFromRec === course.course_name"
            :disabled="!course.has_kp_graph"
            @click="generateFromRecommend(course)"
          >
            {{ course.has_kp_graph ? '一键生成学习路径' : '暂无知识图谱' }}
          </el-button>
        </article>
      </div>
    </section>

    <el-skeleton v-if="loading" :rows="8" animated />

    <div v-else-if="!paths.length" class="empty-card">
      <h3>还没有学习路径</h3>
      <p>输入课程名称后，系统会结合培养方案关系、课程知识点图谱和你的画像掌握度生成路径。</p>
      <p class="muted" v-if="recommendations.length">或直接从上方"智能推荐"中选择一门课快速开始。</p>
      <el-button type="primary" @click="quickGenerate">立即生成</el-button>
    </div>

    <div v-else class="path-layout">
      <aside class="path-list">
        <div class="panel-title">我的路径</div>
        <button
          v-for="path in paths"
          :key="path.id"
          class="path-item"
          :class="{ active: selectedPath?.id === path.id }"
          @click="selectedPath = path"
        >
          <div class="path-item-main">
            <strong>{{ pathDisplayName(path) }}</strong>
            <el-tag size="small" :type="path.status === 'completed' ? 'success' : 'info'">
              {{ scopeLabel(path.path_scope) }}
            </el-tag>
            <el-dropdown
              trigger="click"
              class="path-manage-dropdown"
              @click.stop
              @command="(command: string) => handlePathCommand(command, path)"
            >
              <span class="path-manage-trigger" @click.stop>⋯</span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="rename">重命名</el-dropdown-item>
                  <el-dropdown-item command="archive">归档</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
          <div class="path-item-meta">
            已验收 {{ path.done_steps }}/{{ path.total_steps }} · 学习中 {{ path.learning_steps || 0 }}
          </div>
          <el-progress :percentage="Math.round(path.progress || 0)" :show-text="false" :color="progressColor(path.progress || 0)" />
        </button>
      </aside>

      <main v-if="selectedPath" class="path-detail">
        <section class="detail-header">
          <div>
            <p class="eyebrow">当前路径</p>
            <h2>{{ pathDisplayName(selectedPath) }}</h2>
            <p class="muted">
              {{ selectedPath.course_name }}
              · {{ scopeLabel(selectedPath.path_scope) }} · {{ statusLabel(selectedPath.status) }}
              · 已验收 {{ selectedPath.done_steps }}/{{ selectedPath.total_steps }}
              · 覆盖 {{ coveredPoints.length }} 个知识点
              <span v-if="selectedPath.coverage_ratio !== undefined">（{{ formatPercent(selectedPath.coverage_ratio) }}）</span>
            </p>
          </div>
          <div class="detail-actions">
            <el-progress
              type="circle"
              :percentage="Math.round(selectedPath.progress || 0)"
              :width="72"
              :color="progressColor(selectedPath.progress || 0)"
            />
            <el-button type="primary" :loading="generatingResources" @click="generateResources">
              生成步骤资源
            </el-button>
            <el-dropdown
              trigger="click"
              @command="(command: string) => selectedPath && handlePathCommand(command, selectedPath)"
            >
              <el-button :loading="managingPathId === selectedPath.id">管理路径</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="rename">重命名</el-dropdown-item>
                  <el-dropdown-item command="archive">归档</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </section>

        <section v-if="coveredPoints.length" class="evidence-card">
          <span class="evidence-label">路径覆盖知识点</span>
          <el-tag
            v-for="point in coveredPoints.slice(0, 12)"
            :key="point"
            class="kp-tag"
            type="warning"
            effect="plain"
            @click="openKnowledgePoint(point)"
          >
            {{ point }}
          </el-tag>
        </section>

        <section class="steps">
          <article v-for="step in selectedPath.steps" :key="step.order" :class="stepCardClass(step)">
            <div class="step-index">
              <span>{{ step.order }}</span>
            </div>
            <div class="step-body">
              <div class="step-head">
                <div>
                  <h3>{{ step.title }}</h3>
                  <p class="muted">
                    {{ step.duration_estimate || '建议 45 分钟' }}
                    <span v-if="step.order === nextStepOrder"> · 下一步</span>
                    <span v-if="step.evidence?.learned_at"> · 学习于 {{ formatTime(step.evidence.learned_at) }}</span>
                    <span v-if="step.completed_at"> · 验收于 {{ formatTime(step.completed_at) }}</span>
                  </p>
                </div>
                <div class="status-stack">
                  <el-tag :type="step.status === 'done' ? 'success' : step.status === 'learning' ? 'warning' : 'info'">
                    {{ stepStatusLabel(step) }}
                  </el-tag>
                  <el-tag :type="masteryTag(step.mastery_status)" effect="plain">
                    {{ masteryLabel(step.mastery_status) }}
                  </el-tag>
                </div>
              </div>

              <p class="step-desc">{{ step.description }}</p>
              <p v-if="step.relation_context" class="relation">依据：{{ step.relation_context }}</p>
              <p v-if="step.generation_note" class="warning-line">{{ step.generation_note }}</p>

              <div class="tag-row" v-if="step.knowledge_points?.length">
                <span class="tag-label">知识点</span>
                <el-tag
                  v-for="point in step.knowledge_points"
                  :key="point"
                  class="kp-tag"
                  effect="plain"
                  @click="openKnowledgePoint(point)"
                >
                  {{ point }}
                </el-tag>
              </div>

              <div class="tag-row" v-if="step.resource_types?.length">
                <span class="tag-label">推荐资源</span>
                <el-tag
                  v-for="type in step.resource_types"
                  :key="type"
                  :type="resourceTypeTag(type)"
                  effect="light"
                >
                  {{ resourceTypeLabel(type) }}
                </el-tag>
              </div>

              <div class="rule-box">
                <strong>验收标准</strong>
                <span>{{ step.completion_rule || step.checkpoint || '完成检查题并达到通过阈值。' }}</span>
                <small>
                  通过阈值：{{ Math.round((step.passing_score || 0.7) * 100) }}%
                  <template v-if="step.evidence?.score !== undefined">
                    · 最近检查：{{ Math.round((step.evidence.score || 0) * 100) }}%
                  </template>
                </small>
              </div>

              <div class="step-actions">
                <el-button
                  v-if="step.status === 'pending'"
                  type="primary"
                  plain
                  @click="setLearning(step, 'learning')"
                >
                  开始学习 / 已学习
                </el-button>
                <el-button
                  v-else-if="step.status === 'learning'"
                  plain
                  @click="setLearning(step, 'pending')"
                >
                  重置为待学习
                </el-button>
                <el-button
                  type="warning"
                  plain
                  :loading="checkingStep === step.order"
                  @click="createCheck(step)"
                >
                  {{ step.check_resource_id ? '重新获取检查题' : '生成检查题' }}
                </el-button>
                <el-button
                  :disabled="!step.check_resource_id"
                  @click="openCheck(step)"
                >
                  去完成检查
                </el-button>
                <el-button
                  type="success"
                  plain
                  :disabled="!step.check_resource_id"
                  :loading="verifyingStep === step.order"
                  @click="verifyStep(step)"
                >
                  查看检查结果
                </el-button>
                <el-button
                  v-if="step.mastery_status === 'failed'"
                  type="danger"
                  plain
                  @click="remediateStep(step)"
                >
                  继续补弱
                </el-button>
              </div>

              <div v-if="step.resources?.length || step.ppt_sessions?.length" class="resource-box">
                <strong>关联资源</strong>
                <div class="resource-list">
                  <el-button
                    v-for="resource in step.resources"
                    :key="resource.id"
                    size="small"
                    @click="openResource(resource)"
                  >
                    {{ resourceTypeLabel(resource.type) }} · {{ resource.title }}
                  </el-button>
                  <el-tag
                    v-for="session in step.ppt_sessions"
                    :key="session.session_id || session.topic"
                    type="danger"
                    effect="plain"
                  >
                    PPT 分步会话：{{ session.topic || '待确认大纲和模板' }}
                  </el-tag>
                </div>
              </div>

              <div v-if="step.resource_failures?.length" class="failure-box">
                <strong>资源生成失败</strong>
                <span v-for="failure in step.resource_failures" :key="failure.type + failure.error">
                  {{ resourceTypeLabel(failure.type) }}：{{ failure.error }}
                </span>
              </div>
            </div>
          </article>
        </section>
      </main>
    </div>

    <el-drawer
      v-model="remediationDrawerVisible"
      size="560px"
      title="继续补弱"
      class="remediation-drawer"
    >
      <el-skeleton v-if="remediationLoading" :rows="8" animated />

      <div v-else-if="remediationData?.ok === false" class="remediation-empty">
        <h3>暂时不能补弱</h3>
        <p>{{ remediationData.error || '请先完成检查题，再根据结果生成补弱资源。' }}</p>
      </div>

      <div v-else-if="remediationData" class="remediation-content">
        <section class="remediation-summary">
          <div>
            <p class="eyebrow">补弱对象</p>
            <h3>{{ remediatingStep?.title }}</h3>
            <p class="muted">
              最近检查：{{ Math.round((remediationData.score || 0) * 100) }}%
              · 通过阈值：{{ Math.round((remediationData.passing_score || 0.7) * 100) }}%
            </p>
          </div>
          <el-tag type="danger" effect="plain">检查未通过</el-tag>
        </section>

        <section class="remediation-section">
          <strong>薄弱知识点</strong>
          <div class="tag-row compact">
            <el-tag
              v-for="point in remediationData.weak_knowledge_points || []"
              :key="point"
              type="warning"
              effect="plain"
            >
              {{ point }}
            </el-tag>
          </div>
        </section>

        <section v-if="currentRemediationAttempt()?.diagnosis" class="remediation-section diagnosis-box">
          {{ currentRemediationAttempt()?.diagnosis }}
        </section>

        <section class="remediation-section">
          <strong>错题定位</strong>
          <div v-if="(remediationData.wrong_questions || []).length" class="wrong-question-list">
            <div
              v-for="item in remediationData.wrong_questions"
              :key="String(item.question_id)"
              class="wrong-question"
            >
              <p>{{ item.question || '未命名题目' }}</p>
              <small>
                你的答案：{{ item.user_answer || '未作答' }} · 正确答案：{{ item.correct_answer || '未提供' }}
              </small>
              <div class="tag-row compact" v-if="item.knowledge_points?.length">
                <el-tag v-for="point in item.knowledge_points" :key="point" size="small" effect="plain">
                  {{ point }}
                </el-tag>
              </div>
            </div>
          </div>
          <p v-else class="muted">没有拿到题目级错因，系统会按本步骤绑定知识点补弱。</p>
        </section>

        <section class="remediation-section">
          <div class="section-title-row">
            <strong>本轮补弱资源</strong>
            <el-button
              type="primary"
              plain
              size="small"
              :loading="remediationGenerating"
              @click="generateRemediationResources"
            >
              {{ remediationResources().length ? '查看/补充资源' : '生成补弱资源' }}
            </el-button>
          </div>
          <div v-if="remediationResources().length" class="resource-list vertical">
            <el-button
              v-for="resource in remediationResources()"
              :key="resource.id"
              @click="openResource(resource)"
            >
              {{ resourceTypeLabel(resource.type) }} · {{ resource.title }}
            </el-button>
          </div>
          <p v-else class="muted">建议先生成补弱资源，再开启新一轮检查题。</p>
        </section>

        <section v-if="currentRemediationAttempt()?.resource_failures?.length" class="failure-box">
          <strong>补弱资源生成失败</strong>
          <span
            v-for="failure in currentRemediationAttempt()?.resource_failures"
            :key="failure.type + failure.error"
          >
            {{ resourceTypeLabel(failure.type) }}：{{ failure.error }}
          </span>
        </section>

        <section class="remediation-section">
          <div class="section-title-row">
            <strong>重新验收</strong>
            <el-button
              type="warning"
              size="small"
              :loading="remediationChecking"
              @click="createRemediationCheck"
            >
              生成新一轮检查题
            </el-button>
          </div>
          <p class="muted">新检查题会替换当前步骤检查入口。提交题目后，掌握度会由题目正确率自动更新。</p>
          <el-button
            v-if="remediatingStep?.check_resource_id"
            class="remediation-check-btn"
            @click="openCheck(remediatingStep)"
          >
            去完成当前检查题
          </el-button>
        </section>

        <section v-if="remediatingStep?.remediation_attempts?.length" class="remediation-section">
          <strong>补弱轮次记录</strong>
          <div class="attempt-list">
            <div
              v-for="attempt in remediatingStep.remediation_attempts"
              :key="attempt.attempt_no"
              class="attempt-item"
            >
              第 {{ attempt.attempt_no }} 轮 · 失败分数 {{ Math.round((attempt.failed_score || 0) * 100) }}%
              <span v-if="attempt.new_check_resource_id"> · 已生成新检查题 #{{ attempt.new_check_resource_id }}</span>
            </div>
          </div>
        </section>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.path-page {
  max-width: 1440px;
  margin: 0 auto;
  padding: 32px;
  color: #2f2a24;
  overflow-x: hidden;
}

.hero-card,
.empty-card,
.path-list,
.path-detail,
.evidence-card {
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(228, 184, 132, 0.35);
  border-radius: 18px;
  box-shadow: 0 12px 30px rgba(184, 120, 48, 0.08);
}

.hero-card {
  display: grid;
  grid-template-columns: 1fr minmax(360px, 520px);
  gap: 24px;
  align-items: center;
  margin-bottom: 24px;
  padding: 26px;
}

.mastery-rule-alert {
  margin: -8px 0 20px;
  border-radius: 12px;
}

.recommend-card {
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(228, 184, 132, 0.35);
  border-radius: 18px;
  box-shadow: 0 12px 30px rgba(184, 120, 48, 0.08);
  padding: 22px 24px;
  margin-bottom: 24px;
}

.recommend-header {
  margin-bottom: 18px;
}

.recommend-header h3 {
  margin: 4px 0 4px;
  font-size: 17px;
}

.recommend-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}

.recommend-item {
  background: #fffaf4;
  border: 1px solid #f0ddc5;
  border-radius: 14px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: all 0.2s ease;
}

.recommend-item:hover {
  border-color: #e6a45e;
  box-shadow: 0 6px 18px rgba(216, 142, 62, 0.13);
  transform: translateY(-2px);
}

.recommend-item.no-graph {
  opacity: 0.65;
}

.recommend-item-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.recommend-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.recommend-meta {
  font-size: 12px;
  color: #a08060;
}

.recommend-reason {
  font-size: 13px;
  color: #7a6a58;
  line-height: 1.7;
  flex: 1;
}

.recommend-mastery {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #8a7b6a;
}

.recommend-mastery .el-progress {
  flex: 1;
}

.mastery-value {
  min-width: 32px;
  text-align: right;
  font-weight: 600;
  color: #b37a3f;
}

.eyebrow {
  margin: 0 0 8px;
  color: #d58b3c;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

h2,
h3,
p {
  margin: 0;
}

.hero-desc,
.muted {
  color: #8a7b6a;
  line-height: 1.8;
}

.quick-create {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

.empty-card {
  padding: 48px;
  text-align: center;
}

.empty-card p {
  margin: 12px auto 24px;
  max-width: 620px;
  color: #8a7b6a;
}

.path-layout {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 22px;
  align-items: start;
  width: 100%;
  min-width: 0;
}

.path-manage-dropdown {
  margin-left: auto;
  flex-shrink: 0;
}

.path-manage-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  color: #9a7a56;
  cursor: pointer;
}

.path-manage-trigger:hover {
  background: #fff5eb;
  color: #3a332e;
}

.path-list {
  position: sticky;
  top: 96px;
  padding: 18px;
}

.panel-title {
  margin-bottom: 12px;
  font-weight: 700;
}

.path-item {
  width: 100%;
  min-width: 0;
  margin-bottom: 12px;
  padding: 14px;
  text-align: left;
  background: #fffaf4;
  border: 1px solid #f0ddc5;
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.path-item:hover,
.path-item.active {
  border-color: #e6a45e;
  box-shadow: 0 8px 20px rgba(216, 142, 62, 0.14);
  transform: translateY(-1px);
}

.path-item-main,
.detail-header,
.step-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  min-width: 0;
}

.path-item-main strong,
.step-head h3,
.detail-header h2 {
  overflow-wrap: anywhere;
}

.path-item-meta {
  margin: 8px 0;
  color: #8a7b6a;
  font-size: 13px;
}

.path-detail {
  padding: 24px;
  min-width: 0;
  overflow: hidden;
}

.detail-header {
  align-items: center;
  padding-bottom: 20px;
  border-bottom: 1px solid #f1e2d0;
}

.detail-actions {
  display: flex;
  gap: 16px;
  align-items: center;
}

.evidence-card {
  margin: 18px 0;
  padding: 14px 16px;
}

.evidence-label,
.tag-label {
  margin-right: 10px;
  color: #b37a3f;
  font-weight: 700;
}

.kp-tag {
  margin: 4px 6px 4px 0;
  cursor: pointer;
}

.steps {
  display: grid;
  gap: 16px;
}

.step-card {
  display: grid;
  grid-template-columns: 48px 1fr;
  gap: 14px;
  padding: 18px;
  background: #fffdf9;
  border: 1px solid #f0dfcc;
  border-radius: 16px;
  min-width: 0;
  overflow: hidden;
}

.step-card.current {
  border-color: #DBA878;
  box-shadow: 0 10px 24px rgba(219, 168, 120, 0.16);
}

.step-card.learning {
  background: #fffbf1;
  border-color: #E8C29C;
}

.step-card.done {
  background: #F8FCF9;
  border-color: #B9DDCB;
}

.step-card.failed {
  border-color: #F2B8A2;
  background: #FFF8F4;
}

.step-index span {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  background: #f8d6ab;
  border-radius: 50%;
  font-weight: 800;
}

.step-card.done .step-index span {
  color: #fff;
  background: #98C9B3;
}

.step-body {
  min-width: 0;
}

.status-stack {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.step-desc {
  margin-top: 12px;
  color: #4d4034;
  line-height: 1.8;
}

.relation,
.warning-line {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #fff7eb;
  color: #9b6b35;
}

.warning-line {
  background: #fff1f0;
  color: #d45a45;
}

.tag-row,
.rule-box,
.resource-box,
.failure-box,
.step-actions {
  margin-top: 14px;
  min-width: 0;
}

.rule-box,
.resource-box,
.failure-box {
  display: grid;
  gap: 8px;
  padding: 12px;
  background: #fbf7f1;
  border-radius: 12px;
  color: #655547;
}

.rule-box small {
  color: #9a8978;
}

.step-actions,
.resource-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
  max-width: 100%;
}

.step-actions :deep(.el-button),
.resource-list :deep(.el-button) {
  margin-left: 0;
  max-width: 100%;
  min-height: 32px;
  white-space: normal;
  overflow-wrap: anywhere;
}

.resource-list :deep(.el-button > span) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tag-row :deep(.el-tag),
.evidence-card :deep(.el-tag),
.resource-list :deep(.el-tag) {
  max-width: 100%;
  height: auto;
  min-height: 24px;
  white-space: normal;
  overflow-wrap: anywhere;
}

.failure-box {
  color: #c45656;
  background: #fff3f3;
}

.remediation-empty {
  padding: 24px;
  color: #8a7b6a;
  background: #fff7eb;
  border-radius: 14px;
}

.remediation-content {
  display: grid;
  gap: 16px;
}

.remediation-summary,
.remediation-section {
  padding: 16px;
  background: #fffaf4;
  border: 1px solid #f0dfcc;
  border-radius: 14px;
}

.remediation-summary,
.section-title-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.diagnosis-box {
  color: #8a5a28;
  line-height: 1.8;
  background: #fff7eb;
}

.tag-row.compact {
  margin-top: 8px;
}

.wrong-question-list,
.attempt-list {
  display: grid;
  gap: 10px;
  margin-top: 10px;
}

.wrong-question,
.attempt-item {
  padding: 12px;
  background: #fff;
  border: 1px solid #f1e2d0;
  border-radius: 10px;
}

.wrong-question p {
  margin-bottom: 8px;
  line-height: 1.7;
}

.wrong-question small,
.attempt-item {
  color: #8a7b6a;
}

.resource-list.vertical {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.resource-list.vertical .el-button {
  justify-content: flex-start;
  margin-left: 0;
  white-space: normal;
}

.remediation-check-btn {
  margin-top: 10px;
}

@media (max-width: 1100px) {
  .hero-card,
  .path-layout {
    grid-template-columns: 1fr;
  }

  .path-list {
    position: static;
  }
}
</style>
