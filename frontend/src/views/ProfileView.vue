<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import api from '../api'
import ProfileQuestionnaire from '../components/profile/ProfileQuestionnaire.vue'
import KnowledgeGraph from '../components/profile/KnowledgeGraph.vue'
import { useUserStore } from '../stores/user'
import { useEventStore } from '../stores/event'
import { ElMessage, ElMessageBox } from 'element-plus'
import SausageIcon from '../components/SausageIcon.vue'
import LoadingSausage from '../components/LoadingSausage.vue'

const userStore = useUserStore()
const eventStore = useEventStore()
const router = useRouter()

const profile = ref<any>(null)
const loading = ref(false)
const completeness = ref(0)
const profileHistory = ref<Array<{ trigger: string; snapshot: any; created_at: string }>>([])
const historyChartRef = ref<HTMLElement | null>(null)
let historyChart: echarts.ECharts | null = null
const TRIGGER_LABELS: Record<string, string> = { quiz: '答题', focus: '专注', path_step: '路径步骤', chat: '对话', questionnaire: '问卷' }
const quizStats = ref({
  total: 0,
  avg_score_percent: 0,
  latest_score_percent: null as number | null,
})

const showQuestionnaire = ref(false)
const showRebuildDialog = ref(false)
const rebuildLoading = ref(false)
const selectedCourse = ref<any>(null)

const abilityDims = ['知识记忆', '逻辑推理', '应用实践', '信息整合', '应试能力']
const courseColors = ['#E35749', '#49BBC8', '#F3B86B']
const radarChartRef = ref<HTMLElement | null>(null)
let radarChart: echarts.ECharts | null = null

function initOverviewRadar() {
  if (!radarChartRef.value || !profile.value?.weak_courses?.length) return
  if (!radarChart) radarChart = echarts.init(radarChartRef.value)
  const weakCourses = profile.value.weak_courses.slice(0, 3)
  const seriesData: any[] = []
  const legendData: string[] = []
  weakCourses.forEach((course: any, i: number) => {
    const scores = course.course_ability_scores || {}
    const values = abilityDims.map(d => scores[d] || 0)
    const color = courseColors[i]
    seriesData.push({ value: values, name: course.name, lineStyle: { color }, itemStyle: { color }, areaStyle: { color } })
    legendData.push(course.name)
  })
  radarChart.setOption({
    radar: {
      center: ['50%', '50%'], radius: '60%',
      indicator: abilityDims.map(d => ({ name: d, max: 10 })),
      axisName: { color: '#3A332E', fontSize: 11, fontWeight: 500, borderRadius: 3, padding: [3, 5] },
      axisLine: { lineStyle: { color: '#EFE6DC' } },
      splitLine: { lineStyle: { color: '#EFE6DC' } },
      splitArea: { areaStyle: { color: ['rgba(255,251,245,0.3)', 'rgba(255,251,245,0.5)'] } },
    },
    series: [{ type: 'radar', lineStyle: { width: 2 }, areaStyle: { opacity: 0.15 }, data: seriesData }],
    legend: { show: true, data: legendData, bottom: 0, textStyle: { color: '#7C5C3C', fontSize: 11 }, itemWidth: 10, itemHeight: 10 },
  })
  radarChart.off('click')
  radarChart.on('click', (params: any) => {
    if (params?.name && profile.value?.weak_courses) {
      const match = profile.value.weak_courses.find((c: any) => c.name === params.name)
      if (match) selectedCourse.value = match
    }
  })
  radarChart.resize()
}

function initCourseRadar() {
  if (!radarChartRef.value || !selectedCourse.value) return
  if (!radarChart) radarChart = echarts.init(radarChartRef.value)
  const scores = selectedCourse.value.course_ability_scores || {}
  const values = abilityDims.map(d => scores[d] || 0)
  radarChart.setOption({
    radar: {
      center: ['50%', '50%'], radius: '60%',
      indicator: abilityDims.map(d => ({ name: d, max: 10 })),
      axisName: { color: '#3A332E', fontSize: 11, fontWeight: 500, borderRadius: 3, padding: [3, 5] },
      axisLine: { lineStyle: { color: '#EFE6DC' } },
      splitLine: { lineStyle: { color: '#EFE6DC' } },
      splitArea: { areaStyle: { color: ['rgba(255,251,245,0.3)', 'rgba(255,251,245,0.5)'] } },
    },
    series: [{
      type: 'radar', lineStyle: { width: 2, color: '#E35749' },
      areaStyle: { opacity: 0.15, color: '#E35749' },
      itemStyle: { color: '#E35749' },
      data: [{ value: values, name: selectedCourse.value.name }],
    }],
    legend: { show: false },
  })
  radarChart.resize()
}

const onRadarResize = () => { radarChart?.resize(); historyChart?.resize() }

const completenessHints = computed(() => {
  if (!profile.value) return []
  const p = profile.value, hints: string[] = []
  if (!p.weak_courses?.length) hints.push('填写薄弱课程（在问卷中补充）')
  if (!p.ability_scores || !Object.values(p.ability_scores).some(Boolean)) hints.push('完成一套题库以获得能力评分')
  if (!p.cognitive_style) hints.push('通过对话告诉我你的学习偏好')
  return hints.slice(0, 2)
})

const knowledgeGraphData = computed(() => profile.value?.knowledge_base || {})

function renderHistoryChart() {
  if (!historyChartRef.value || profileHistory.value.length < 2) return
  if (!historyChart) historyChart = echarts.init(historyChartRef.value)
  const times = profileHistory.value.map(h => { const d = new Date(h.created_at); return `${d.getMonth()+1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2,'0')}` })
  const series = abilityDims.map(dim => ({ name: dim, type: 'line', smooth: true, data: profileHistory.value.map(h => { const v = h.snapshot?.ability_scores?.[dim]; return v != null ? Math.round(v*10) : null }), connectNulls: true }))
  historyChart.setOption({ tooltip: { trigger: 'axis' }, legend: { data: abilityDims, bottom: 0, textStyle: { fontSize: 11, color: '#6B635C' } }, grid: { top: 16, left: 40, right: 16, bottom: 48 }, xAxis: { type: 'category', data: times, axisLabel: { fontSize: 10, rotate: 30, color: '#948A80' } }, yAxis: { type: 'value', min: 0, max: 10 }, series, backgroundColor: 'transparent' })
}

watch(profileHistory, () => { setTimeout(renderHistoryChart, 100) }, { deep: true })

onMounted(() => {
  if (userStore.userId) loadProfile(true)
  eventStore.connect(userStore.userId || 'user_default')
  window.addEventListener('resize', onRadarResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onRadarResize)
  radarChart?.dispose()
  historyChart?.dispose()
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
      completeness.value = r.data.completeness ?? 0
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
    if (profile.value?.weak_courses?.length && !selectedCourse.value) {
      nextTick().then(() => initOverviewRadar())
    }
    setTimeout(renderHistoryChart, 150)
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

function onQuestionnaireDone(p: any) {
  profile.value = p
  showQuestionnaire.value = false
  ElMessage.success('学习画像构建完成')
  api.post('/resources/generate/starter', null, {
    params: { user_id: userStore.userId, max_courses: 3 },
    timeout: 180000,
  }).then((r) => {
    if ((r.data.generated || 0) > 0) ElMessage.success(`已根据画像自动生成 ${r.data.generated} 个入门资源，请前往学习资源查看`)
  }).catch(() => {})
}

function onQuestionnaireCancel() {
  showQuestionnaire.value = false
}

async function askReProfile() {
  try {
    await ElMessageBox.confirm('是否重新填写个人信息？', '提示', {
      confirmButtonText: '是',
      cancelButtonText: '否',
      type: 'info',
    })
    showQuestionnaire.value = true
  } catch {}
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

watch(selectedCourse, async (c) => {
  coursePath.value = null
  if (c?.name) await loadCoursePath(c.name)
  await nextTick()
  if (c) {
    initCourseRadar()
    setTimeout(() => radarChart?.resize(), 550)
  } else {
    setTimeout(() => {
      initOverviewRadar()
      radarChart?.resize()
    }, 500)
  }
})

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
    const r = await api.post('/profile/run', null, {
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

// ── 能力维度与答题联动 ────────────────────────────────
const abilityQuizHint = computed(() => {
  if (!profile.value?.ability_scores || !quizStats.value.total) return []
  const scores = profile.value.ability_scores as Record<string, number>
  return abilityDims
    .map(d => ({ dim: d, score: scores[d] ?? 0 }))
    .sort((a, b) => a.score - b.score)
    .slice(0, 3)
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
    <div v-if="loading" class="loading-box"><LoadingSausage text="加载画像..." /></div>

    <div v-else-if="!profile" class="empty-box animate-up">
      <div class="sa-empty">
        <SausageIcon :size="72" animate />
        <p class="sa-empty-text">该用户暂无画像数据</p>
        <el-button style="background:#F9D9B8;color:#3A332E;border:none;border-radius:8px;font-weight:500" @click="showQuestionnaire = true">开始构建画像</el-button>
      </div>
    </div>

    <div v-else class="profile-layout">
      <aside class="profile-sidebar animate-up animate-delay-1">
        <div class="sidebar-top-card" @click="askReProfile">
          <div class="sidebar-avatar">
            <SausageIcon :size="50" />
          </div>
          <div class="sidebar-body">
            <el-tag size="small" class="sidebar-edu-tag">{{ profile.education_level || profile.grade || '-' }}</el-tag>
            <div class="sidebar-major">{{ profile.discipline }}{{ profile.major ? ' · ' + profile.major : '' }}</div>
            <div class="sidebar-cross" v-if="profile.cross_disciplines?.length">
              + {{ profile.cross_disciplines.join('、') }}
            </div>
          </div>
        </div>
        <div class="sidebar-courses-wrapper">
          <template v-for="(c, idx) in sortedWeakCourses" :key="c.name">
            <div
              :class="['sidebar-course', { active: selectedCourse?.name === c.name }]"
              @click="selectedCourse = c"
            >
              <div class="sc-row">
                <div class="sc-priority-badge" v-if="idx === 0">优先</div>
                <div class="sc-name">{{ c.name }}</div>
                <div class="sc-tags">
                  <span v-for="t in c.difficulty_types" :key="t" class="sc-tag">{{ t }}</span>
                  <span v-for="i in c.impacts" :key="i" class="sc-tag sc-tag-impact">{{ i }}</span>
                </div>
              </div>
              <div class="sc-points">{{ c.knowledge_points }}</div>
            </div>
          </template>
        </div>
        <div class="sidebar-actions">
          <el-button size="small" @click="showQuestionnaire = true">重新填写</el-button>
          <el-button size="small" @click="showRebuildDialog = true">智能重建</el-button>
        </div>
      </aside>

      <main class="profile-main animate-up animate-delay-2">
        <div v-if="profile.ability_summary" class="ability-summary">
          <div class="ability-summary-text">{{ aiInterpretText || profile.ability_summary }}</div>
          <el-button
            size="small" text type="primary"
            :loading="aiInterpretLoading"
            class="ai-interpret-btn"
            @click="fetchAiInterpret"
          >{{ aiInterpretLoading ? '解读中...' : 'AI 深度解读' }}</el-button>
        </div>

        <!-- 画像健全度 -->
        <div class="completeness-bar">
          <span class="completeness-label">画像健全度</span>
          <el-progress :percentage="completeness" :stroke-width="8" :color="completeness >= 80 ? '#98C9B3' : completeness >= 50 ? '#DBA878' : '#E35749'" style="flex:1" />
          <span v-if="completeness < 80" class="completeness-hint">继续对话或完成答题可提升健全度</span>
        </div>

        <!-- 健全度引导卡片 -->
        <div v-if="completenessHints.length" class="guide-card">
          <span class="guide-title">提升建议</span>
          <ul class="guide-list">
            <li v-for="hint in completenessHints" :key="hint">{{ hint }}</li>
          </ul>
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
          <!-- 能力维度联动：显示最弱的3个维度，点击高亮雷达图 -->
          <div v-if="abilityQuizHint.length" class="ability-dim-hint">
            <span class="adh-label">待提升维度</span>
            <div class="adh-bars">
              <div
                v-for="item in abilityQuizHint" :key="item.dim"
                class="adh-bar-row"
                @click="selectedCourse = null"
              >
                <span class="adh-dim">{{ item.dim }}</span>
                <el-progress
                  :percentage="item.score * 10"
                  :stroke-width="6"
                  :color="item.score < 4 ? '#E35749' : item.score < 7 ? '#DBA878' : '#98C9B3'"
                  style="flex:1"
                />
                <span class="adh-score">{{ item.score.toFixed(1) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="bottom-area">
          <div class="ba-card">
            <div class="ba-radar-cell" :class="{ 'ba-shrink': !!selectedCourse }">
              <div ref="radarChartRef" class="ba-chart" />
            </div>
            <Transition name="ba-slide">
              <div v-if="selectedCourse" class="ba-detail">
                <div class="cd-header">
                  <span class="cd-title">{{ selectedCourse.name }}</span>
                  <el-button size="small" text @click="selectedCourse = null">收起</el-button>
                </div>
                <div class="cd-blocks">
                  <div class="cd-block">
                    <span class="cd-label">困难类型</span>
                    <div class="cd-tags">
                      <el-tag v-for="t in selectedCourse.difficulty_types" :key="t" size="small">{{ t }}</el-tag>
                    </div>
                  </div>
                  <div class="cd-block">
                    <span class="cd-label">影响范围</span>
                    <div class="cd-tags">
                      <el-tag v-for="i in selectedCourse.impacts" :key="i" size="small" type="warning">{{ i }}</el-tag>
                    </div>
                  </div>
                  <div class="cd-block">
                    <span class="cd-label">学习目标</span>
                    <el-tag size="small" type="primary">{{ selectedCourse.goal }}</el-tag>
                  </div>
                  <div class="cd-block" v-if="selectedCourse.strategies?.length">
                    <span class="cd-label">推荐策略</span>
                    <div class="cd-tags">
                      <el-tag v-for="s in selectedCourse.strategies" :key="s" size="small" type="success">{{ s }}</el-tag>
                    </div>
                  </div>
                </div>
                <div class="course-path-section">
                  <div class="cp-header">
                    <span class="cp-title">补救学习路径</span>
                    <el-tag v-if="coursePath && coursePath.status === 'completed'" type="success" size="small">已完成</el-tag>
                  </div>
                  <template v-if="coursePath">
                    <div class="cp-progress">
                      <el-progress :percentage="Math.round((coursePath.progress || 0) * 100)" :stroke-width="10" :color="coursePath.status === 'completed' ? '#98C9B3' : '#DBA878'" />
                      <span class="cp-progress-text">{{ coursePath.done_steps || 0 }} / {{ coursePath.total_steps || 0 }} 步完成</span>
                      <el-button size="small" type="success" :loading="pathResourceLoading" @click="generatePathResources()" style="margin-left: 12px">生成学习资源</el-button>
                      <el-button size="small" text type="warning" :loading="pathGenerating" @click="generateCoursePath(selectedCourse)" style="margin-left: auto">
                        重新生成
                      </el-button>
                    </div>
                    <div class="cp-steps">
                      <div v-for="s in coursePath.steps" :key="s.order" :class="['cp-step', { 'cp-step-done': s.status === 'done' }]">
                        <el-checkbox
                          :model-value="s.status === 'done'"
                          size="large"
                          @change="(v: boolean) => toggleStepDone(coursePath.id, s.order, v)"
                        />
                        <div class="cp-step-body">
                          <div class="cp-step-title">{{ s.title }}</div>
                          <div class="cp-step-desc">{{ s.description }}</div>
                          <div class="cp-step-meta">
                            <span class="cp-step-duration">{{ s.duration_estimate }}</span>
                            <el-tag v-for="q in s.resource_queries" :key="q" size="small" type="warning">{{ q }}</el-tag>
                          </div>
                          <div v-if="s.resources && s.resources.length" class="cp-resources">
                            <span class="cp-res-label">学习资源：</span>
                            <el-button
                              v-for="r in s.resources"
                              :key="r.id"
                              size="small"
                              :type="r.type === 'quiz' ? 'warning' : 'primary'"
                              plain
                              class="cp-res-btn"
                              @click="openPathResource(r.id)"
                            >
                              {{ r.type === 'quiz' ? '📝' : '📄' }} 打开：{{ r.title }}
                            </el-button>
                          </div>
                          <div v-if="s.checkpoint" class="cp-checkpoint">
                            <el-icon><CircleCheck /></el-icon>
                            <span>{{ s.checkpoint }}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </template>
                  <div v-else-if="pathLoading" class="cp-empty">
                    <span style="color:#666;font-size:13px">加载中...</span>
                  </div>
                  <div v-else class="cp-empty">
                    <p>暂未生成学习路径</p>
                    <el-button type="primary" size="small" :loading="pathGenerating" @click="generateCoursePath(selectedCourse)">
                      生成学习路径
                    </el-button>
                  </div>
                </div>
              </div>
            </Transition>
          </div>
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

        <!-- 能力成长折线图 -->
        <div v-if="profileHistory.length >= 2" class="history-section">
          <div class="section-title">能力成长趋势</div>
          <div ref="historyChartRef" class="history-chart" />
          <div class="history-triggers">
            <span v-for="h in profileHistory.slice(-8)" :key="h.created_at" class="trigger-dot">
              <el-tag size="small" :type="h.trigger === 'quiz' ? 'warning' : h.trigger === 'focus' ? 'success' : 'info'">
                {{ TRIGGER_LABELS[h.trigger] || h.trigger }}
              </el-tag>
            </span>
          </div>
        </div>

        <!-- 知识图谱 -->
        <div class="kg-section">
          <div class="section-title">知识图谱</div>
          <KnowledgeGraph
            :knowledgeBase="knowledgeGraphData"
            :discipline="profile.discipline"
            @node-click="(id) => router.push({ path: '/resources', query: { search: id } })"
          />
        </div>
      </main>
    </div>

    <ProfileQuestionnaire
      v-if="showQuestionnaire"
      @done="onQuestionnaireDone"
      @cancel="onQuestionnaireCancel"
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

.profile-layout {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

.profile-sidebar {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  position: sticky;
  top: 16px;
}

.sidebar-top-card {
  background: linear-gradient(135deg, #FFFBF5 0%, #FFF0E0 100%);
  border: 1px solid #EFE6DC;
  border-radius: 14px;
  padding: 16px;
  display: flex;
  gap: 14px;
  align-items: center;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(219,168,120,0.08);
}
.sidebar-top-card:hover {
  border-color: #DBA878;
  box-shadow: 0 4px 16px rgba(219,168,120,0.15);
  transform: translateY(-1px);
}

.sidebar-avatar {
  background: #FFF5EB;
  width: 64px;
  height: 64px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1.5px solid #EFE6DC;
}

.sidebar-body {
  flex: 1;
  min-width: 0;
  color: #3A332E;
}

.sidebar-edu-tag {
  display: inline-block;
  margin-bottom: 10px;
}

.sidebar-major {
  font-weight: 500;
  font-size: 14px;
  color: #3A332E;
  margin-bottom: 6px;
  line-height: 1.4;
}

.sidebar-cross {
  font-size: 12px;
  color: #6B635C;
  margin-bottom: 12px;
}

.sidebar-actions {
  display: flex;
  flex-direction: row;
  gap: 8px;
}
.sidebar-actions .el-button {
  flex: 1;
  background: transparent !important;
  border-color: #EFE6DC !important;
  color: #3A332E;
}

.profile-main {
  flex: 1;
  min-width: 0;
}


.sidebar-courses-wrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sidebar-course {
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
  transition: 0.2s;
  color: #3A332E;
}
.sidebar-course:hover {
  background: #FFF0E0;
  border-color: #DBA878;
}
.sidebar-course.active {
  background: #FFF0E0;
  outline: 2px solid #DBA878;
  outline-offset: 1px;
}

.sc-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sc-name {
  font-weight: 500;
  font-size: 14px;
  color: #3A332E;
  white-space: nowrap;
}

.sc-points {
  font-size: 12px;
  color: #948A80;
  opacity: 0.9;
  line-height: 1.4;
  margin-top: 4px;
}

.sc-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.sc-tag {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 6px;
  background: rgba(249,217,184,0.2);
  color: #3A332E;
  font-size: 11px;
}
.sc-tag-impact {
  background: rgba(238, 155, 143, 0.4);
}

.quiz-summary {
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(219,168,120,0.06);
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

.completeness-bar {
  display: flex; align-items: center; gap: 12px; margin-bottom: 12px;
  padding: 12px 16px; background: #FFFBF5; border: 1px solid #EFE6DC; border-radius: 12px;
  box-shadow: 0 2px 8px rgba(219,168,120,0.06);
}
.completeness-label { font-size: 13px; color: #6B635C; white-space: nowrap; font-weight: 500; }
.completeness-hint { font-size: 12px; color: #948A80; white-space: nowrap; }

.guide-card {
  background: rgba(253,246,236,0.9); border: 1px solid rgba(235,177,95,0.4);
  border-radius: 12px; padding: 12px 16px; margin-bottom: 12px;
  display: flex; align-items: flex-start; gap: 12px;
  box-shadow: 0 2px 8px rgba(219,168,120,0.06);
}
.guide-title { font-size: 12px; font-weight: 500; color: #DBA878; white-space: nowrap; padding-top: 2px; }
.guide-list { margin: 0; padding-left: 16px; font-size: 12px; color: #6B635C; line-height: 1.8; }

.chat-update-box {
  background: #FFFBF5; border: 1px solid #EFE6DC; border-radius: 12px;
  padding: 16px 18px; margin-top: 16px;
  box-shadow: 0 2px 8px rgba(219,168,120,0.06);
}
.chat-update-title { font-size: 13px; font-weight: 500; color: #DBA878; margin-bottom: 10px; }
.chat-update-row { display: flex; gap: 10px; }
.chat-update-result { margin-top: 8px; font-size: 12px; color: #98C9B3; }

.history-section { margin-top: 16px; }
.history-chart { width: 100%; height: 240px; background: #FFFBF5; border-radius: 12px; border: 1px solid #EFE6DC; box-shadow: 0 2px 8px rgba(219,168,120,0.06); }
.history-triggers { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.trigger-dot { cursor: default; }

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

/* 能力维度联动 */
.ability-dim-hint {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #EFE6DC;
}
.adh-label {
  font-size: 12px;
  font-weight: 500;
  color: #6B635C;
  display: block;
  margin-bottom: 8px;
}
.adh-bars { display: flex; flex-direction: column; gap: 6px; }
.adh-bar-row {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}
.adh-dim {
  font-size: 12px;
  color: #3A332E;
  width: 56px;
  flex-shrink: 0;
}
.adh-score {
  font-size: 12px;
  color: #948A80;
  width: 26px;
  text-align: right;
  flex-shrink: 0;
}
</style>







