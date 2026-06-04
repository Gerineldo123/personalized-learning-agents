<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import ProfileRadar from '../components/profile/ProfileRadar.vue'
import ProfileQuestionnaire from '../components/profile/ProfileQuestionnaire.vue'
import { useUserStore } from '../stores/user'
import { useEventStore } from '../stores/event'
import { ElMessage } from 'element-plus'

const userStore = useUserStore()
const eventStore = useEventStore()
const router = useRouter()

const profile = ref<any>(null)
const loading = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null
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

function startPoll() {
  loadProfile()
  pollTimer = setInterval(loadProfile, 30000)
}

onMounted(() => {
  if (userStore.userId) startPoll()
  eventStore.connect(userStore.userId || 'user_default')
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

watch(() => eventStore.lastEvent, (evt) => {
  if (evt?.event === 'profile.updated') loadProfile()
  if (evt?.event === 'quiz.submitted') loadProfile()
})

watch(() => userStore.userId, (newId) => {
  if (newId) startPoll()
  else if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
})

async function loadProfile() {
  if (!userStore.userId) return
  loading.value = true
  try {
    const r = await api.get('/profile', { params: { user_id: userStore.userId } })
    if (r.data.found) profile.value = r.data.profile
    else profile.value = null

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
.page-title { margin-bottom: 24px; color: #303133; }
.loading-box { height: 200px; }
.empty-box { margin-top: 40px; }

.profile-detail { margin-top: 8px; }

.profile-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.ability-summary {
  background: #ecf5ff;
  border-radius: 8px;
  padding: 14px 18px;
  color: #409eff;
  font-size: 14px;
  line-height: 1.7;
  margin-bottom: 20px;
}

.quiz-summary {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px 18px;
  margin-bottom: 20px;
}

.quiz-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.quiz-head h3 {
  margin: 0;
  color: #303133;
  font-size: 16px;
}

.quiz-meta {
  display: flex;
  gap: 16px;
  color: #909399;
  font-size: 12px;
  margin-bottom: 8px;
}

.quiz-analysis {
  margin: 0;
  color: #606266;
  font-size: 14px;
  line-height: 1.8;
}

.radar-section { margin-bottom: 28px; }

.courses-section { margin-bottom: 28px; }
.courses-section h3 { color: #303133; margin-bottom: 16px; }

.course-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}

.course-card {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  padding: 16px;
  cursor: pointer;
  transition: 0.2s;
}
.course-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
.course-card.active { border-color: #409eff; background: #ecf5ff; }

.cc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.cc-name { font-weight: 600; color: #303133; font-size: 15px; }
.cc-points { color: #606266; font-size: 13px; line-height: 1.5; margin-bottom: 10px; }
.cc-tags { display: flex; gap: 6px; flex-wrap: wrap; }

.course-detail {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  padding: 20px;
  margin-top: 8px;
}
.course-detail h3 { color: #303133; margin-bottom: 16px; }

.cd-grid { display: grid; grid-template-columns: 360px 1fr; gap: 24px; }

.cd-block { margin-bottom: 18px; }
.cd-label { display: block; font-size: 12px; color: #909399; margin-bottom: 6px; }
.cd-block p { color: #303133; font-size: 14px; line-height: 1.6; margin: 0; }
.cd-tags { display: flex; gap: 6px; flex-wrap: wrap; }

.course-path-section {
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid #ebeef5;
}

.cp-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.cp-title {
  font-weight: 600;
  color: #303133;
  font-size: 15px;
}

.cp-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
}

.cp-progress-text {
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
}

.cp-steps { margin-top: 4px; }

.cp-step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 0;
  border-bottom: 1px solid #f0f0f0;
}

.cp-step:last-child { border-bottom: none; }

.cp-step-body { flex: 1; min-width: 0; }

.cp-step-title {
  font-weight: 600;
  color: #303133;
  font-size: 14px;
  margin-bottom: 4px;
}

.cp-step-desc {
  color: #606266;
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
  color: #909399;
  background: #f5f7fa;
  padding: 2px 8px;
  border-radius: 3px;
}

.cp-resources { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
.cp-res-label { font-size: 12px; color: #909399; }
.cp-res-btn { font-size: 12px; }
.cp-checkpoint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 12px;
  background: #f0f9eb;
  border-radius: 4px;
  color: #67c23a;
  font-size: 12px;
  line-height: 1.5;
}

.cp-empty { padding: 16px 0; }
.cp-empty p { color: #909399; font-size: 13px; margin: 0 0 10px; }

.rebuild-hint { color: #606266; font-size: 14px; line-height: 1.8; margin-bottom: 12px; }
.rebuild-sources { padding-left: 20px; margin: 0 0 16px; color: #303133; font-size: 14px; list-style: none; }
.rebuild-sources li { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; color: #409eff; }
.rebuild-warn { display: flex; align-items: center; gap: 6px; color: #e6a23c; font-size: 13px; padding: 10px 12px; background: #fdf6ec; border-radius: 4px; }
</style>







