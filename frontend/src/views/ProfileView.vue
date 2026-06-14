<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import ProfileRadar from '../components/profile/ProfileRadar.vue'
import ProfileQuestionnaire from '../components/profile/ProfileQuestionnaire.vue'
import KnowledgeGraph from '../components/profile/KnowledgeGraph.vue'
import { useUserStore } from '../stores/user'
import { useEventStore } from '../stores/event'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'

const userStore = useUserStore()
const eventStore = useEventStore()
const router = useRouter()

const profile = ref<any>(null)
const loading = ref(false)
const completeness = ref(0)
const profileHistory = ref<Array<{ trigger: string; snapshot: any; created_at: string }>>([])
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

const abilityDimDesc: Record<string, string> = {
  '知识记忆': '对核心概念、公式、定义的记忆与复现能力',
  '逻辑推理': '分析问题、推导结论、判断因果关系的能力',
  '应用实践': '将知识迁移到实际问题、动手编程或实验的能力',
  '信息整合': '跨知识点归纳、构建知识体系的能力',
  '应试能力': '在限时条件下稳定发挥、准确解题的能力',
}

// 画像健全度：统计已填字段占比
const profileCompleteness = computed(() => {
  if (!profile.value) return 0
  const p = profile.value
  const checks = [
    p.major, p.grade || p.education_level, p.learning_goal,
    p.cognitive_style, (p.weak_points?.length > 0), (p.preferred_format?.length > 0),
    (p.weak_courses?.length > 0), (p.ability_scores && Object.keys(p.ability_scores).length > 0),
  ]
  return Math.round(checks.filter(Boolean).length / checks.length * 100)
})

onMounted(() => {
  if (userStore.userId) loadProfile()
  eventStore.connect(userStore.userId || 'user_default')
})

onUnmounted(() => {
})

watch(() => eventStore.lastEvent, (evt) => {
  if (evt?.event === 'profile.updated') loadProfile()
  if (evt?.event === 'quiz.submitted') loadProfile()
})

watch(() => userStore.userId, (newId) => {
  if (newId) loadProfile()
})

async function loadProfile() {
  if (!userStore.userId) return
  loading.value = true
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
  finally { loading.value = false }
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
  // 首次构建画像后，静默触发入门资源包生成
  api.post('/resources/generate/starter', null, {
    params: { user_id: userStore.userId, max_courses: 3 },
    timeout: 180000,
  }).then((r) => {
    if ((r.data.generated || 0) > 0) {
      ElMessage.success(`已根据画像自动生成 ${r.data.generated} 个入门资源，请前往学习资源查看`)
    }
  }).catch(() => {})
}

function onQuestionnaireCancel() {
  showQuestionnaire.value = false
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

const abilityRadarData = computed(() => {
  const scores = profile.value?.ability_scores || {}
  const data: Record<string, number> = {}
  for (const d of abilityDims) {
    data[d] = scores[d] || 0
  }
  return data
})

const courseRadarData = computed(() => {
  if (!selectedCourse.value) return {}
  const scores = selectedCourse.value.course_ability_scores || {}
  const data: Record<string, number> = {}
  for (const d of abilityDims) {
    data[d] = scores[d] || 0
  }
  return data
})

const coursePath = ref<any>(null)
const pathLoading = ref(false)
const pathGenerating = ref(false)
const pathResourceLoading = ref(false)

watch(selectedCourse, async (c) => {
  coursePath.value = null
  if (c?.name) await loadCoursePath(c.name)
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
const chatUpdateInput = ref('')
const chatUpdateLoading = ref(false)
const chatUpdateResult = ref('')

async function submitChatUpdate() {
  if (!chatUpdateInput.value.trim() || !userStore.userId) return
  chatUpdateLoading.value = true
  chatUpdateResult.value = ''
  try {
    await api.post('/profile/run', null, {
      params: { user_id: userStore.userId, message: chatUpdateInput.value },
    })
    chatUpdateInput.value = ''
    chatUpdateResult.value = '画像已更新'
    await loadProfile()
  } catch {
    chatUpdateResult.value = '更新失败，请重试'
  } finally {
    chatUpdateLoading.value = false
  }
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

// 历史折线图
const historyChartRef = ref<HTMLElement | null>(null)
let historyChart: echarts.ECharts | null = null
const TRIGGER_LABELS: Record<string, string> = {
  quiz: '答题', focus: '专注', path_step: '路径步骤', chat: '对话', questionnaire: '问卷'
}

function renderHistoryChart() {
  if (!historyChartRef.value || profileHistory.value.length < 2) return
  if (!historyChart) historyChart = echarts.init(historyChartRef.value)

  const dims = ['知识记忆', '逻辑推理', '应用实践', '信息整合', '应试能力']
  const times = profileHistory.value.map(h => {
    const d = new Date(h.created_at)
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
  })
  const series = dims.map(dim => ({
    name: dim,
    type: 'line',
    smooth: true,
    data: profileHistory.value.map(h => {
      const v = h.snapshot?.ability_scores?.[dim]
      return v != null ? Math.round(v * 10) : null
    }),
    connectNulls: true,
  }))

  historyChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: dims, bottom: 0, textStyle: { fontSize: 11 } },
    grid: { top: 16, left: 40, right: 16, bottom: 48 },
    xAxis: { type: 'category', data: times, axisLabel: { fontSize: 10, rotate: 30 } },
    yAxis: { type: 'value', min: 0, max: 10, name: '评分', nameTextStyle: { fontSize: 10 } },
    series,
  })
}

watch(profileHistory, () => {
  setTimeout(renderHistoryChart, 100)
}, { deep: true })

// 健全度引导提示
const completenessHints = computed(() => {
  if (!profile.value) return []
  const p = profile.value
  const hints: string[] = []
  if (!p.weak_courses?.length) hints.push('填写薄弱课程（在问卷中补充）')
  if (!p.ability_scores || !Object.values(p.ability_scores).some(Boolean)) hints.push('完成一套题库以获得能力评分')
  if (!p.cognitive_style) hints.push('通过对话告诉我你的学习偏好')
  return hints.slice(0, 2)
})

// 知识图谱数据：将 knowledge_base 合并入 ability_scores 给图谱着色
const knowledgeGraphData = computed(() => {
  if (!profile.value) return {}
  const kb = profile.value.knowledge_base || {}
  const as_ = profile.value.ability_scores || {}
  return { ...kb, ...as_ }
})
</script>

<template>
  <div class="profile-view">
    <h2 class="page-title">学习画像</h2>

    <div v-if="loading" v-loading="loading" class="loading-box" />

    <div v-else-if="!profile" class="empty-box">
      <el-empty description="该用户暂无画像数据">
        <el-button type="primary" @click="showQuestionnaire = true">开始构建画像</el-button>
      </el-empty>
    </div>

    <div v-else class="profile-detail">
      <div class="profile-header">
        <div>
          <el-tag size="large" type="primary">{{ profile.education_level || profile.grade || '-' }}</el-tag>
          <span style="margin-left:8px;color:#303133;font-weight:600">{{ profile.discipline }}{{ profile.major ? ' · ' + profile.major : '' }}</span>
          <template v-if="profile.cross_disciplines?.length">
            <span style="color:#909399;font-size:12px;margin-left:8px">
              + {{ profile.cross_disciplines.join('、') }}
            </span>
          </template>
        </div>
        <div>
          <el-button size="small" @click="showQuestionnaire = true">重新填写问卷</el-button>
          <el-button type="warning" size="small" @click="showRebuildDialog = true">智能重建</el-button>
        </div>
      </div>

      <!-- 画像健全度 -->
      <div class="completeness-bar">
        <span class="completeness-label">画像健全度</span>
        <el-progress
          :percentage="completeness"
          :stroke-width="8"
          :color="completeness >= 80 ? '#67c23a' : completeness >= 50 ? '#e6a23c' : '#409eff'"
          style="flex:1"
        />
        <span class="completeness-hint" v-if="completeness < 80">
          继续对话或完成答题可提升健全度
        </span>
      </div>

      <!-- 健全度引导卡片 -->
      <div v-if="completenessHints.length" class="guide-card">
        <span class="guide-title">提升建议</span>
        <ul class="guide-list">
          <li v-for="hint in completenessHints" :key="hint">{{ hint }}</li>
        </ul>
      </div>

      <div v-if="profile.ability_summary" class="ability-summary">
        {{ profile.ability_summary }}
      </div>

      <div class="quiz-summary">
        <div class="quiz-head">
          <h3>习题正确率分析</h3>
          <el-tag type="primary">平均 {{ quizStats.avg_score_percent.toFixed(1) }}%</el-tag>
        </div>
        <div class="quiz-meta">
          <span>累计作答：{{ quizStats.total }} 次</span>
          <span v-if="quizStats.latest_score_percent !== null">最近一次：{{ quizStats.latest_score_percent.toFixed(1) }}%</span>
        </div>
        <p class="quiz-analysis">{{ quizAnalysis }}</p>
      </div>

      <div v-if="abilityRadarData && Object.keys(abilityRadarData).length" class="radar-section">
        <ProfileRadar
          :knowledgeBase="abilityRadarData"
          title="能力雷达图"
        />
        <div class="dim-tooltips">
          <el-tooltip
            v-for="dim in abilityDims" :key="dim"
            :content="abilityDimDesc[dim]"
            placement="top"
          >
            <el-tag size="small" type="info" class="dim-tag">{{ dim }}</el-tag>
          </el-tooltip>
        </div>
      </div>

      <!-- 对话式更新入口 -->
      <div class="chat-update-box">
        <div class="chat-update-title">通过对话更新画像</div>
        <div class="chat-update-row">
          <el-input
            v-model="chatUpdateInput"
            placeholder="例如：我最近在学强化学习，感觉概率基础比较薄弱"
            size="default"
            @keydown.enter="submitChatUpdate"
          />
          <el-button type="primary" :loading="chatUpdateLoading" @click="submitChatUpdate">更新</el-button>
        </div>
        <div v-if="chatUpdateResult" class="chat-update-result">{{ chatUpdateResult }}</div>
      </div>

      <!-- 能力成长折线图 -->
      <div v-if="profileHistory.length >= 2" class="history-section">
        <h3 class="section-title">能力成长趋势</h3>
        <div ref="historyChartRef" class="history-chart" />
        <div class="history-triggers">
          <span v-for="h in profileHistory.slice(-8)" :key="h.created_at" class="trigger-dot" :title="h.created_at">
            <el-tag size="small" :type="h.trigger === 'quiz' ? 'warning' : h.trigger === 'focus' ? 'success' : 'info'">
              {{ TRIGGER_LABELS[h.trigger] || h.trigger }}
            </el-tag>
          </span>
        </div>
      </div>

      <!-- 知识图谱 -->
      <div class="kg-section">
        <h3 class="section-title">知识图谱</h3>
        <KnowledgeGraph :knowledgeBase="knowledgeGraphData" />
      </div>

      <div v-if="profile.weak_courses?.length" class="courses-section">
        <h3>薄弱课程（{{ profile.weak_courses.length }}门）</h3>
        <div class="course-cards">
          <div
            v-for="c in profile.weak_courses" :key="c.name"
            :class="['course-card', { active: selectedCourse?.name === c.name }]"
            @click="selectedCourse = c"
          >
            <div class="cc-header">
              <span class="cc-name">{{ c.name }}</span>
              <el-tag size="small" :type="c.goal === '短期应试' ? 'danger' : c.goal === '长期应试' ? 'warning' : c.goal === '项目驱动' ? 'success' : ''">
                {{ c.goal }}
              </el-tag>
            </div>
            <div class="cc-points">{{ c.knowledge_points }}</div>
            <div class="cc-tags">
              <el-tag v-for="t in c.difficulty_types" :key="t" size="small" type="info">{{ t }}</el-tag>
            </div>
          </div>
        </div>
      </div>

      <div v-if="selectedCourse" class="course-detail">
        <h3>
          {{ selectedCourse.name }}
          <el-button size="small" text @click="selectedCourse = null" style="margin-left:8px">收起</el-button>
        </h3>
        <div class="cd-grid">
          <div class="cd-left">
            <ProfileRadar
              v-if="courseRadarData && Object.keys(courseRadarData).length"
              :knowledgeBase="courseRadarData"
              :title="selectedCourse.name + ' - 能力分布'"
            />
          </div>
          <div class="cd-right">
            <div class="cd-block">
              <span class="cd-label">薄弱知识点</span>
              <p>{{ selectedCourse.knowledge_points }}</p>
            </div>
            <div class="cd-block">
              <span class="cd-label">困难类型</span>
              <div class="cd-tags">
                <el-tag v-for="t in selectedCourse.difficulty_types" :key="t" size="small" type="info">{{ t }}</el-tag>
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

          <div class="course-path-section">
            <div class="cp-header">
              <span class="cp-title">补救学习路径</span>
              <el-tag v-if="coursePath && coursePath.status === 'completed'" type="success" size="small">已完成</el-tag>
            </div>

            <template v-if="coursePath">
              <div class="cp-progress">
                <el-progress :percentage="Math.round((coursePath.progress || 0) * 100)" :stroke-width="10" :color="coursePath.status === 'completed' ? '#67c23a' : '#409eff'" />
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
              <span style="color:#909399;font-size:13px">加载中...</span>
            </div>

            <div v-else class="cp-empty">
              <p>暂未生成学习路径</p>
              <el-button type="primary" size="small" :loading="pathGenerating" @click="generateCoursePath(selectedCourse)">
                生成学习路径
              </el-button>
            </div>
          </div>
        </div>
        </div>
      </div>
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
.profile-view { max-width: 960px; }
.page-title { margin-bottom: 28px; }
.empty-box { margin-top: 40px; }

.profile-detail { margin-top: 8px; }

.profile-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.ability-summary {
  background: linear-gradient(135deg, var(--color-primary-bg), rgba(167,139,250,0.05));
  border-radius: var(--radius-md);
  padding: 16px 20px;
  color: var(--color-primary);
  font-size: 14px;
  line-height: 1.7;
  margin-bottom: 24px;
  border: 1px solid var(--color-primary-border);
}

.quiz-summary {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 20px 24px;
  margin-bottom: 24px;
}

.quiz-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.quiz-head h3 { margin: 0; font-size: 16px; }
.quiz-meta { display: flex; gap: 16px; color: var(--text-secondary); font-size: 12px; margin-bottom: 10px; }
.quiz-analysis { margin: 0; color: var(--text-regular); font-size: 14px; line-height: 1.8; }

.radar-section { margin-bottom: 28px; }

.courses-section { margin-bottom: 28px; }
.courses-section h3 { margin-bottom: 16px; }

.course-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}

.course-card {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
  padding: 18px;
  cursor: pointer;
  transition: all var(--transition-base);
}
.course-card:hover { box-shadow: var(--shadow-md); transform: translateY(-2px); }
.course-card.active { border-color: var(--color-primary); background: var(--color-primary-bg); }

.cc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.cc-name { font-weight: 600; color: var(--text-primary); font-size: 15px; }
.cc-points { color: var(--text-regular); font-size: 13px; line-height: 1.5; margin-bottom: 10px; }
.cc-tags { display: flex; gap: 6px; flex-wrap: wrap; }

.course-detail {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
  padding: 24px;
  margin-top: 12px;
}
.course-detail h3 { margin-bottom: 16px; }

.cd-grid { display: grid; grid-template-columns: 360px 1fr; gap: 24px; }

.cd-block { margin-bottom: 18px; }
.cd-label { display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; font-weight: 500; }
.cd-block p { color: var(--text-primary); font-size: 14px; line-height: 1.6; margin: 0; }
.cd-tags { display: flex; gap: 6px; flex-wrap: wrap; }

.course-path-section {
  margin-top: 28px;
  padding-top: 24px;
  border-top: 1px solid var(--border-light);
}

.cp-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}
.cp-title { font-weight: 600; font-size: 16px; }

.cp-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}
.cp-progress-text { font-size: 13px; color: var(--text-regular); white-space: nowrap; }

.cp-steps { margin-top: 4px; }

.cp-step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 0;
  border-bottom: 1px solid var(--border-light);
}
.cp-step:last-child { border-bottom: none; }
.cp-step-body { flex: 1; min-width: 0; }
.cp-step-title { font-weight: 600; color: var(--text-primary); font-size: 14px; margin-bottom: 4px; }
.cp-step-desc { color: var(--text-regular); font-size: 13px; line-height: 1.6; margin-bottom: 6px; }
.cp-step-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cp-step-duration {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-overlay);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}
.cp-resources { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
.cp-res-label { font-size: 12px; color: var(--text-secondary); }
.cp-res-btn { font-size: 12px; }
.cp-checkpoint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--color-success-bg);
  border-radius: var(--radius-sm);
  color: var(--color-success);
  font-size: 12px;
  line-height: 1.5;
}
.cp-empty { padding: 16px 0; }
.cp-empty p { color: var(--text-secondary); font-size: 13px; margin: 0 0 10px; }

.rebuild-hint { color: var(--text-regular); font-size: 14px; line-height: 1.8; margin-bottom: 12px; }
.rebuild-sources { padding-left: 20px; margin: 0 0 16px; font-size: 14px; list-style: none; }
.rebuild-sources li { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; color: var(--color-primary); }
.rebuild-warn { display: flex; align-items: center; gap: 6px; color: var(--color-warning); font-size: 13px; padding: 10px 12px; background: var(--color-warning-bg); border-radius: var(--radius-sm); }

.completeness-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
  padding: 12px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
}
.completeness-label { font-size: 13px; color: var(--text-secondary); white-space: nowrap; font-weight: 500; }
.completeness-hint { font-size: 12px; color: var(--text-placeholder); white-space: nowrap; }

.dim-tooltips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; padding: 0 20px 4px; }
.dim-tag { cursor: help; }

.chat-update-box {
  background: var(--bg-card);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  padding: 16px 20px;
  margin-bottom: 24px;
}
.chat-update-title { font-size: 13px; font-weight: 600; color: var(--color-primary); margin-bottom: 10px; }
.chat-update-row { display: flex; gap: 10px; }
.chat-update-result { margin-top: 8px; font-size: 12px; color: var(--color-success); }

.guide-card {
  background: var(--color-warning-bg);
  border: 1px solid rgba(230,162,60,0.4);
  border-radius: var(--radius-md);
  padding: 12px 16px;
  margin-bottom: 18px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.guide-title { font-size: 12px; font-weight: 600; color: var(--color-warning); white-space: nowrap; padding-top: 2px; }
.guide-list { margin: 0; padding-left: 16px; font-size: 12px; color: var(--text-regular); line-height: 1.8; }

.section-title { font-size: 15px; font-weight: 600; margin: 0 0 14px; color: var(--text-primary); }

.history-section { margin-bottom: 28px; }
.history-chart { width: 100%; height: 240px; }
.history-triggers { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.trigger-dot { cursor: default; }

.kg-section { margin-bottom: 28px; }
</style>







