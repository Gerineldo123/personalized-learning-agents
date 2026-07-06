<script setup lang="ts">
import { ref, watch, onMounted, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import ConversationalOnboarding from '../components/profile/ConversationalOnboarding.vue'
import CurriculumGraph from '../components/profile/CurriculumGraph.vue'
import { useUserStore } from '../stores/user'
import { useEventStore } from '../stores/event'
import { ElMessage } from 'element-plus'

const userStore = useUserStore()
const eventStore = useEventStore()
const router = useRouter()

const profile = ref<any>(null)
const loading = ref(false)
const profileHistory = ref<Array<{ trigger: string; snapshot: any; created_at: string }>>([])
const TRIGGER_LABELS: Record<string, string> = { quiz: '答题', focus: '专注', path_step: '路径步骤', chat: '对话', onboarding: '对话建档', questionnaire: '旧问卷' }
const quizStats = ref({
  total: 0,
  avg_score_percent: 0,
  latest_score_percent: null as number | null,
})

const showOnboarding = ref(false)
const showRebuildDialog = ref(false)
const rebuildLoading = ref(false)

const preferredFormats = computed(() => {
  const value = profile.value?.preferred_format
  if (Array.isArray(value)) return value.filter(Boolean).join('、') || '待补充'
  return value || '待补充'
})

const weakPointPreview = computed(() => {
  const points = profile.value?.weak_points
  return Array.isArray(points) ? points.slice(0, 8) : []
})

const latestEvidenceText = computed(() => {
  const latest = profileHistory.value[profileHistory.value.length - 1]
  if (!latest) return '暂无更新记录'
  const trigger = TRIGGER_LABELS[latest.trigger] || latest.trigger || '系统更新'
  return `${trigger} · ${new Date(latest.created_at).toLocaleString()}`
})

const profileEvidence = computed(() => profile.value?.profile_evidence || {})
function evidenceFor(key: string) {
  return profileEvidence.value?.[key] || latestEvidenceText.value
}

const knowledgeGraphData = computed(() => profile.value?.knowledge_base || {})

onMounted(() => {
  if (userStore.userId) loadProfile(true)
  eventStore.connect(userStore.userId || 'user_default')
})

watch(() => eventStore.lastEvent, (evt) => {
  if (evt?.event === 'profile.updated') {
    nextTick().then(() => loadProfile(true))
  }
  if (evt?.event === 'quiz.submitted') {
    // 功能6: 答题后自动重建画像以刷新知识图谱
    nextTick().then(() => loadProfile(true))
    api.post('/profile/rebuild', null, { params: { user_id: userStore.userId } })
      .then(() => loadProfile())
      .catch(() => {})
  }
})

watch(() => userStore.userId, (newId) => {
  if (newId) loadProfile(true)
})

async function loadProfile(initial = false) {
  if (!userStore.userId) return
  if (initial) loading.value = true
  try {
    const r = await api.get('/profile', { params: { user_id: userStore.userId } })
    if (r.data.found) {
      profile.value = r.data.profile
      profileHistory.value = r.data.history || []
    } else {
      profile.value = null
    }

    const qr = await api.get('/quiz/stats', { params: { user_id: userStore.userId } })
    quizStats.value = {
      total: qr.data.total || 0,
      avg_score_percent: qr.data.avg_score_percent || 0,
      latest_score_percent: qr.data.latest_score_percent ?? null,
    }
  } catch { profile.value = null }
  finally {
    if (initial) loading.value = false
  }
}

const quizAnalysis = computed(() => {
  const total = quizStats.value.total
  const avg = quizStats.value.avg_score_percent
  if (!total) return '你还没有答题记录，建议先完成一套题库，系统会基于结果分析你的薄弱点。'
  if (avg >= 85) return '你的整体掌握度较高，可以增加综合题与迁移题训练，重点提升解题速度和稳定性。'
  if (avg >= 60) return '你的基础已建立，但存在不稳定点。建议优先复盘错题并按知识点做专项巩固。'
  return '当前正确率偏低，建议先回到基础概念与核心例题，采用“小步快练+即时复盘”的节奏。'
})

function onOnboardingDone(p: any) {
  profile.value = p
  showOnboarding.value = false
  ElMessage.success('学习画像构建完成')
  api.post('/resources/generate/starter', null, {
    params: { user_id: userStore.userId, max_courses: 3 },
    timeout: 180000,
  }).then((r) => {
    if ((r.data.generated || 0) > 0) ElMessage.success(`已根据画像自动生成 ${r.data.generated} 个入门资源，请前往学习资源查看`)
  }).catch(() => {})
}

function onOnboardingCancel() {
  showOnboarding.value = false
}

async function doRebuildProfile() {
  rebuildLoading.value = true
  try {
    const r = await api.post('/profile/rebuild', null, { params: { user_id: userStore.userId } })
    ElMessage.success(`画像已重新构建（分析 ${r.data.data_sources?.conversations_analyzed || 0} 个对话、${r.data.data_sources?.quiz_records_analyzed || 0} 条答题记录）`)
    showRebuildDialog.value = false
    loadProfile()
  } catch { ElMessage.error('智能重建失败，请手动构建') }
  finally { rebuildLoading.value = false }
}

const coursePath = ref<any>(null)
const pathLoading = ref(false)
const pathGenerating = ref(false)
const pathResourceLoading = ref(false)

async function loadCoursePath(courseName: string) {
  pathLoading.value = true
  try {
    const r = await api.get('/path/course', { params: { user_id: userStore.userId, course_name: courseName } })
    coursePath.value = r.data.found ? r.data : null
  } catch { coursePath.value = null }
  finally { pathLoading.value = false }
}

async function generateCoursePath(c: any) {
  if (!c) return
  pathGenerating.value = true
  try {
    const r = await api.post('/path/course/generate', null, {
      params: {
        user_id: userStore.userId,
        course_name: c.name,
        knowledge_points: c.knowledge_points || '',
        difficulty_types: (c.difficulty_types || []).join('、'),
        impacts: (c.impacts || []).join('、'),
        goal: c.goal || '',
        strategies: (c.strategies || []).join('、'),
      },
      timeout: 120000,
    })
    coursePath.value = r.data
    ElMessage.success(`已生成 ${c.name} 的学习路径`)
  } catch (err: any) {
    const msg = err?.response?.data?.detail || err?.message || '请求失败'
    ElMessage.error(`路径生成失败：${msg}`)
  }
  finally { pathGenerating.value = false }
}


async function generatePathResources() {
  if (!coursePath.value?.id) return
  pathResourceLoading.value = true
  try {
    const r = await api.post(`/path/course/${coursePath.value.id}/generate-resources`, null, {
      params: { user_id: userStore.userId },
      timeout: 300000,
    })
    coursePath.value.steps = r.data.steps || []
    ElMessage.success('路径资源已生成')
  } catch (err: any) {
    ElMessage.error('资源生成失败')
  }
  finally { pathResourceLoading.value = false }
}

function openPathResource(resourceId: number) {
  router.push({ path: '/resources', query: { open: String(resourceId) } })
}

function openCourseResources(courseName: string) {
  router.push({ path: '/resources', query: { course: courseName, package: '课程总览' } })
}

function openKnowledgePointResources(knowledgePoint: string, courseName?: string) {
  router.push({
    path: '/resources',
    query: {
      course: courseName || '',
      kp: knowledgePoint,
      package: '知识点补弱',
    },
  })
}

async function toggleStepDone(pathId: number, stepOrder: number, done: boolean) {
  try {
    const r = await api.patch(`/path/course/${pathId}/step/${stepOrder}`, null, {
      params: { done },
    })
    if (r.data.ok && coursePath.value) {
      coursePath.value.done_steps = r.data.done_steps
      coursePath.value.progress = r.data.progress
      coursePath.value.status = r.data.status
      const steps = coursePath.value.steps || []
      const step = steps.find((s: any) => s.order === stepOrder)
      if (step) step.status = done ? 'done' : 'pending'
    }
  } catch { ElMessage.error('更新步骤状态失败') }
}

// ── AI 深度解读 ──────────────────────────────────────
const aiInterpretLoading = ref(false)
const aiInterpretText = ref('')

async function fetchAiInterpret() {
  if (!userStore.userId || !profile.value) return
  aiInterpretLoading.value = true
  aiInterpretText.value = ''
  const scores = profile.value.ability_scores || {}
  const weakNames = (profile.value.weak_courses || []).map((c: any) => c.name).join('、')
  const message = `请根据我当前的学习画像给出深度解读和个性化建议。能力评分：${JSON.stringify(scores)}；薄弱课程：${weakNames || '暂无'}；认知风格：${profile.value.cognitive_style || '未知'}；能力摘要：${profile.value.ability_summary || ''}。请用2-3段话给出有针对性的学习建议。`
  try {
    await api.post('/profile/run', null, {
      params: { user_id: userStore.userId, message },
      timeout: 60000,
    })
    // /profile/run 只返回 {ok:true}，刷新画像后读 ability_summary 更新
    await loadProfile()
    aiInterpretText.value = profile.value?.ability_summary || '解读完成，画像已更新。'
  } catch { aiInterpretText.value = '解读失败，请稍后重试。' }
  finally { aiInterpretLoading.value = false }
}

// ── 薄弱课程排序权重 ──────────────────────────────────
const IMPACT_WEIGHT: Record<string, number> = {
  '担心挂科或补考': 10, '影响保研或奖学金': 9, '影响期末成绩': 8,
  '影响后续课程学习': 7, '影响实习或就业': 6,
}
function courseImpactScore(course: any): number {
  return ((course.impacts || []) as string[])
    .reduce((sum, i) => sum + (IMPACT_WEIGHT[i] ?? 3), 0)
}
const sortedWeakCourses = computed(() => {
  if (!profile.value?.weak_courses) return []
  return [...profile.value.weak_courses].sort((a, b) => courseImpactScore(b) - courseImpactScore(a))
})

const chatUpdateInput = ref('')
const chatUpdateLoading = ref(false)
const chatUpdateResult = ref('')

async function submitChatUpdate() {
  if (!chatUpdateInput.value.trim() || !userStore.userId) return
  chatUpdateLoading.value = true
  chatUpdateResult.value = ''
  try {
    await api.post('/profile/run', null, { params: { user_id: userStore.userId, message: chatUpdateInput.value } })
    chatUpdateInput.value = ''
    chatUpdateResult.value = '画像已更新'
    await loadProfile()
  } catch { chatUpdateResult.value = '更新失败，请重试' }
  finally { chatUpdateLoading.value = false }
}
</script>

<template>
  <div class="profile-view">
    <div v-if="loading" class="loading-box">
      <div class="plain-loading">
        <el-icon class="is-loading"><component :is="'Loading'" /></el-icon>
        <span>加载画像...</span>
      </div>
    </div>

    <div v-else-if="!profile" class="empty-box animate-up">
      <div class="profile-empty">
        <div class="profile-empty-icon">👤</div>
        <p class="sa-empty-text">该用户暂无画像数据</p>
        <el-button style="background:#F9D9B8;color:#3A332E;border:none;border-radius:8px;font-weight:500" @click="showOnboarding = true">开始对话建档</el-button>
      </div>
    </div>

    <div v-else class="profile-main animate-up animate-delay-2">
      <section class="profile-hero animate-up animate-delay-1">
        <div class="profile-identity-card" @click="showOnboarding = true">
          <div class="profile-avatar">
            <span>AI</span>
          </div>
          <div class="profile-id-body">
            <el-tag size="small" class="profile-edu-tag">{{ profile.education_level || profile.grade || '-' }}</el-tag>
            <div class="profile-major">{{ profile.discipline }}{{ profile.major ? ' · ' + profile.major : '' }}</div>
            <div class="profile-cross" v-if="profile.cross_disciplines?.length">
              + {{ profile.cross_disciplines.join('、') }}
            </div>
          </div>
        </div>
        <div class="profile-hero-summary">
          <div class="hero-summary-title">画像摘要</div>
          <p>{{ profile.learning_goal || '暂无明确学习目标，可通过对话建档补充。' }}</p>
          <div class="profile-source-tags">
            <el-tag v-if="profile.cognitive_style" size="small" type="info">{{ profile.cognitive_style }}</el-tag>
            <el-tag v-if="preferredFormats !== '待补充'" size="small" type="success">{{ preferredFormats }}</el-tag>
          </div>
        </div>
        <div class="profile-actions">
          <el-button size="small" @click="showOnboarding = true">对话建档</el-button>
          <el-button size="small" @click="showRebuildDialog = true">智能重建</el-button>
        </div>
      </section>

        <div v-if="profile.ability_summary" class="ability-summary">
          <div class="ability-summary-text">{{ aiInterpretText || profile.ability_summary }}</div>
          <el-button
            size="small" text type="primary"
            :loading="aiInterpretLoading"
            class="ai-interpret-btn"
            @click="fetchAiInterpret"
          >{{ aiInterpretLoading ? '解读中...' : 'AI 深度解读' }}</el-button>
        </div>

        <div class="profile-summary-grid">
          <div class="summary-card">
            <span>学习目标</span>
            <strong>{{ profile.learning_goal || '待补充' }}</strong>
            <small>来源：{{ evidenceFor('learning_goal') }}</small>
          </div>
          <div class="summary-card">
            <span>认知风格</span>
            <strong>{{ profile.cognitive_style || '待补充' }}</strong>
            <small>来源：{{ evidenceFor('cognitive_style') }}</small>
          </div>
          <div class="summary-card">
            <span>资源偏好</span>
            <strong>{{ preferredFormats }}</strong>
            <small>来源：{{ evidenceFor('preferred_format') }}</small>
          </div>
          <div class="summary-card">
            <span>最近更新依据</span>
            <strong>{{ latestEvidenceText }}</strong>
          </div>
        </div>

        <div v-if="weakPointPreview.length" class="weak-point-summary">
          <span class="weak-point-title">薄弱知识点</span>
          <div class="weak-point-tags">
            <el-tag v-for="kp in weakPointPreview" :key="kp" size="small" type="warning">{{ kp }}</el-tag>
          </div>
        </div>

        <div class="quiz-summary">
          <div class="quiz-head">
            <h3>习题正确率分析</h3>
            <el-tag>平均 {{ quizStats.avg_score_percent.toFixed(1) }}%</el-tag>
          </div>
          <div class="quiz-meta">
            <span>累计作答：{{ quizStats.total }} 次</span>
            <span v-if="quizStats.latest_score_percent !== null">最近一次：{{ quizStats.latest_score_percent.toFixed(1) }}%</span>
          </div>
          <p class="quiz-analysis">{{ quizAnalysis }}</p>
        </div>

        <!-- 对话式更新画像 -->
        <div class="chat-update-box">
          <div class="chat-update-title">通过对话更新画像</div>
          <div class="chat-update-row">
            <el-input v-model="chatUpdateInput" placeholder="例如：我最近在学强化学习，感觉概率基础比较薄弱" @keydown.enter="submitChatUpdate" />
            <el-button type="primary" :loading="chatUpdateLoading" @click="submitChatUpdate">更新</el-button>
          </div>
          <div v-if="chatUpdateResult" class="chat-update-result">{{ chatUpdateResult }}</div>
        </div>

        <!-- 知识图谱 -->
        <div class="kg-section">
          <div class="section-title">知识图谱</div>
          <CurriculumGraph
            :userId="userStore.userId"
            :major="profile.major"
            :knowledgeBase="knowledgeGraphData"
            @course-click="openCourseResources"
            @node-click="openKnowledgePointResources"
          />
        </div>
    </div>

    <ConversationalOnboarding
      v-if="showOnboarding"
      @done="onOnboardingDone"
      @cancel="onOnboardingCancel"
    />

    <el-dialog v-model="showRebuildDialog" title="重新构建画像" width="500px">
      <p class="rebuild-hint">
        系统将从以下数据源综合分析，重新生成你的学习画像：
      </p>
      <ul class="rebuild-sources">
        <li><el-icon><component :is="'ChatDotRound'" /></el-icon> 历史对话记录</li>
        <li><el-icon><component :is="'EditPen'" /></el-icon> 答题记录与正确率</li>
      </ul>
      <p class="rebuild-warn">
        <el-icon><component :is="'WarningFilled'" /></el-icon>
        此操作将删除当前画像并基于历史数据重新生成，不可撤销。
      </p>
      <template #footer>
        <el-button @click="showRebuildDialog = false">取消</el-button>
        <el-button type="warning" :loading="rebuildLoading" @click="doRebuildProfile">
          确认重建
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.profile-view {
  max-width: 1260px;
  padding: 24px 20px 40px;
  margin: 0 auto;
  box-sizing: border-box;
  background: linear-gradient(160deg, #F9D9B8 0%, #FFF5EB 40%, #FFFBF5 100%);
  min-height: 100vh;
}
.loading-box { height: 200px; }
.empty-box { margin-top: 40px; color: #948A80; }
.plain-loading {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #948A80;
}

.profile-main {
  width: min(100%, 1120px);
  margin: 0 auto;
  min-width: 0;
}

.profile-hero {
  display: grid;
  grid-template-columns: minmax(260px, 340px) 1fr auto;
  gap: 14px;
  align-items: stretch;
  margin-bottom: 14px;
}

.profile-identity-card,
.profile-hero-summary,
.profile-actions {
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 14px;
  box-shadow: 0 2px 8px rgba(219,168,120,0.08);
}

.profile-identity-card {
  padding: 16px;
  display: flex;
  gap: 14px;
  align-items: center;
  cursor: pointer;
  transition: all 0.2s;
}
.profile-identity-card:hover {
  border-color: #DBA878;
  box-shadow: 0 4px 16px rgba(219,168,120,0.15);
  transform: translateY(-1px);
}

.profile-avatar {
  background: linear-gradient(135deg, #3A332E, #6B5445);
  width: 64px;
  height: 64px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #fff;
  font-weight: 800;
  letter-spacing: 0.04em;
  box-shadow: 0 8px 20px rgba(58, 51, 46, 0.18);
}

.profile-id-body {
  flex: 1;
  min-width: 0;
  color: #3A332E;
}

.profile-edu-tag {
  display: inline-block;
  margin-bottom: 10px;
}

.profile-major {
  font-weight: 600;
  font-size: 15px;
  color: #3A332E;
  line-height: 1.5;
}

.profile-cross {
  font-size: 12px;
  color: #6B635C;
  margin-top: 6px;
}

.profile-hero-summary {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hero-summary-title { font-size: 13px; font-weight: 700; color: #3A332E; }
.profile-hero-summary p { margin: 0; color: #6B635C; font-size: 13px; line-height: 1.7; }
.profile-source-tags { display: flex; flex-wrap: wrap; gap: 6px; }

.profile-actions {
  padding: 14px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}
.profile-actions .el-button {
  margin-left: 0;
  background: transparent !important;
  border-color: #EFE6DC !important;
  color: #3A332E;
}

@media (max-width: 900px) {
  .profile-hero {
    grid-template-columns: 1fr;
  }
  .profile-actions {
    flex-direction: row;
  }
  .profile-summary-grid {
    grid-template-columns: 1fr;
  }
}

.quiz-summary {
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(219,168,120,0.06);
}

.profile-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.summary-card {
  padding: 14px 16px;
  border: 1px solid #EFE6DC;
  border-radius: 12px;
  background: #FFFBF5;
}
.summary-card span {
  display: block;
  margin-bottom: 6px;
  color: #948A80;
  font-size: 12px;
}
.summary-card strong {
  color: #3A332E;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}
.summary-card small {
  display: block;
  margin-top: 6px;
  color: #948A80;
  font-size: 11px;
  line-height: 1.5;
}
.weak-point-summary {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 12px;
  border: 1px solid rgba(235, 177, 95, 0.4);
  border-radius: 12px;
  background: rgba(253,246,236,0.9);
}
.weak-point-title {
  color: #DBA878;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  padding-top: 2px;
}
.weak-point-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.quiz-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.quiz-head h3 {
  margin: 0;
  color: #3A332E;
  font-size: 20px;
  font-weight: 500;
}

.quiz-meta {
  display: flex;
  gap: 16px;
  color: #948A80;
  font-size: 12px;
  margin-bottom: 8px;
}

.quiz-analysis {
  margin: 0;
  color: #3A332E;
  font-size: 14px;
  line-height: 1.8;
}

.bottom-area {
  margin-top: 16px;
}

.ba-card {
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 12px;
  display: flex;
  min-height: 320px;
}

.ba-radar-cell {
  flex-grow: 1;
  flex-shrink: 1;
  flex-basis: 0%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  transition: flex-grow 0.5s cubic-bezier(0.4, 0, 0.2, 1),
              flex-shrink 0.5s cubic-bezier(0.4, 0, 0.2, 1),
              flex-basis 0.5s cubic-bezier(0.4, 0, 0.2, 1),
              padding 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

.ba-radar-cell.ba-shrink {
  flex-grow: 0;
  flex-shrink: 0;
  flex-basis: 280px;
  padding: 16px 0 16px 16px;
}

.ba-chart {
  width: 300px;
  height: 280px;
  flex-shrink: 0;
}

.ba-detail {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 24px 24px 24px 0;
  margin-left: 24px;
}

.ba-slide-enter-active,
.ba-slide-leave-active {
  transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

.ba-slide-enter-from,
.ba-slide-leave-to {
  opacity: 0;
  transform: translateX(30px);
}

.cd-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.cd-title {
  font-weight: 500;
  color: #3A332E;
  font-size: 16px;
}

.cd-blocks {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.cd-block { }
.cd-label {
  display: block;
  font-size: 12px;
  color: #6B635C;
  margin-bottom: 4px;
}
.cd-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.cd-tags .el-tag { background: transparent !important; border: 1px solid #EFE6DC !important; }

.course-path-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #EFE6DC;
}

.cp-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.cp-title {
  font-weight: 500;
  color: #3A332E;
  font-size: 15px;
}

.cp-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
  flex-wrap: wrap;
}

.cp-progress-text {
  font-size: 13px;
  color: #6B635C;
  white-space: nowrap;
}

.cp-steps { margin-top: 4px; }

.cp-step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 0;
  border-bottom: 1px solid #EFE6DC;
}

.cp-step:last-child { border-bottom: none; }

.cp-step-body { flex: 1; min-width: 0; }

.cp-step-title {
  font-weight: 500;
  color: #3A332E;
  font-size: 14px;
  margin-bottom: 4px;
}

.cp-step-desc {
  color: #6B635C;
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 6px;
}

.cp-step-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.cp-step-duration {
  font-size: 12px;
  color: #6B635C;
  background: rgba(249,217,184,0.2);
  padding: 2px 8px;
  border-radius: 6px;
}

.cp-resources { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
.cp-res-label { font-size: 12px; color: #3A332E; opacity: 0.7; }
.cp-res-btn { font-size: 12px; }
.cp-checkpoint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 12px;
  background: rgba(249,217,184,0.15);
  border-radius: 8px;
  color: #3A332E;
  font-size: 12px;
  line-height: 1.5;
}

.cp-empty { padding: 16px 0; }
.cp-empty p { color: #3A332E; opacity: 0.6; font-size: 13px; margin: 0 0 10px; }

.rebuild-hint { color: #3A332E; font-size: 14px; line-height: 1.8; margin-bottom: 12px; }
.rebuild-sources { padding-left: 20px; margin: 0 0 16px; color: #3A332E; font-size: 14px; list-style: none; }
.rebuild-sources li { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; color: #3A332E; }
.rebuild-warn { display: flex; align-items: center; gap: 6px; color: #DBA878; font-size: 13px; padding: 10px 12px; background: rgba(238, 155, 143, 0.1); border-radius: 4px; }

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
.animate-delay-3 { animation-delay: 0.24s; }

.sa-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 40px 20px;
}
.sa-empty-text {
  margin: 0;
  font-size: 14px;
  color: #948A80;
  text-align: center;
  line-height: 1.8;
}
.profile-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 40px 20px;
}
.profile-empty-icon {
  width: 72px;
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 22px;
  background: rgba(64, 158, 255, 0.08);
  font-size: 34px;
}

.chat-update-box {
  background: #FFFBF5; border: 1px solid #EFE6DC; border-radius: 12px;
  padding: 16px 18px; margin-top: 16px;
  box-shadow: 0 2px 8px rgba(219,168,120,0.06);
}
.chat-update-title { font-size: 13px; font-weight: 500; color: #DBA878; margin-bottom: 10px; }
.chat-update-row { display: flex; gap: 10px; }
.chat-update-result { margin-top: 8px; font-size: 12px; color: #98C9B3; }

.section-title { font-size: 14px; font-weight: 500; color: #3A332E; margin: 0 0 12px; }

.kg-section { margin-top: 16px; }

/* AI 深度解读 */
.ability-summary {
  background: #FFFBF5;
  border-left: 3px solid #DBA878;
  border-radius: 4px;
  padding: 12px 16px;
  margin-bottom: 12px;
  box-shadow: 0 2px 8px rgba(219,168,120,0.06);
}
.ability-summary-text {
  color: #3A332E;
  font-size: 14px;
  line-height: 1.7;
}
.ai-interpret-btn {
  margin-top: 8px;
  padding: 0;
  font-size: 12px;
}

/* 薄弱课程优先徽标 */
.sc-priority-badge {
  font-size: 10px;
  font-weight: 600;
  color: #fff;
  background: #E35749;
  border-radius: 4px;
  padding: 1px 5px;
  flex-shrink: 0;
}

</style>







