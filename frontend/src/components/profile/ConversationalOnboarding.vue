<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import api from '../../api'
import { useUserStore } from '../../stores/user'
import { ElMessage } from 'element-plus'

const userStore = useUserStore()

const emit = defineEmits<{
  done: [profile: any]
  cancel: []
}>()

const loading = ref(false)
const generatingQuiz = ref(false)
const finishing = ref(false)
const active = ref(0)
const status = ref('')
const sessionId = ref('')
const message = ref('')
const availableCourses = ref<any[]>([])
const selectedCourseNames = ref<string[]>([])
const diagnosticCourses = ref<any[]>([])
const microQuiz = ref<{ questions: any[]; meta?: any }>({ questions: [] })
const answers = ref<Record<string, string>>({})
const diagnosis = ref<any>(null)
const interviewQuestion = ref('')
const interviewAnswer = ref('')
const interviewCount = ref(0)
const knowledgeGraphs = ref<Record<string, any>>({})
const graphMarks = ref<Record<string, string>>({})
const finishResult = ref<any>(null)
let pollTimer: ReturnType<typeof setTimeout> | null = null

const canStart = computed(() => selectedCourseNames.value.length > 0)
const blocked = computed(() => !loading.value && status.value === 'blocked')

function clearPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

function applySessionPayload(data: any) {
  sessionId.value = data.session_id || sessionId.value
  status.value = data.status || ''
  message.value = data.message || ''
  availableCourses.value = data.available_courses || availableCourses.value || []
  diagnosticCourses.value = data.diagnostic_courses || []
  if (diagnosticCourses.value.length) {
    selectedCourseNames.value = diagnosticCourses.value.map((c: any) => c.course_name)
  }
  microQuiz.value = data.micro_quiz || { questions: [] }
  knowledgeGraphs.value = data.knowledge_graphs || {}
  interviewQuestion.value = data.interview_question || ''
}

async function prepare() {
  if (!userStore.userId) return
  loading.value = true
  try {
    const r = await api.post('/profile/onboarding/prepare', {
      user_id: userStore.userId,
      course_names: [],
      mode: 'first_build',
    })
    status.value = r.data.status || ''
    message.value = r.data.message || ''
    availableCourses.value = r.data.available_courses || []
    selectedCourseNames.value = availableCourses.value.slice(0, 3).map((c: any) => c.course_name)
    answers.value = {}
    diagnosis.value = null
    graphMarks.value = {}
    finishResult.value = null
    active.value = 0
  } catch (e: any) {
    status.value = 'blocked'
    microQuiz.value = { questions: [] }
    ElMessage.error(e?.response?.data?.detail || '建档课程加载失败')
  } finally {
    loading.value = false
  }
}

async function pollSession() {
  if (!sessionId.value) return
  try {
    const r = await api.get(`/profile/onboarding/${sessionId.value}`)
    applySessionPayload(r.data)
    if (r.data.status === 'started' && r.data.micro_quiz?.questions?.length) {
      generatingQuiz.value = false
      active.value = 1
      clearPoll()
      return
    }
    if (r.data.status === 'blocked') {
      generatingQuiz.value = false
      active.value = 0
      clearPoll()
      ElMessage.error(r.data.message || '未生成合格诊断题，请稍后重试')
      return
    }
    pollTimer = setTimeout(pollSession, 1200)
  } catch (e: any) {
    generatingQuiz.value = false
    clearPoll()
    ElMessage.error(e?.response?.data?.detail || '获取微测验状态失败')
  }
}

async function start(courseNames?: string[]) {
  if (!userStore.userId) return
  clearPoll()
  loading.value = true
  generatingQuiz.value = false
  try {
    const r = await api.post('/profile/onboarding/start', {
      user_id: userStore.userId,
      course_names: courseNames || [],
      mode: 'first_build',
    })
    applySessionPayload(r.data)
    answers.value = {}
    diagnosis.value = null
    graphMarks.value = {}
    finishResult.value = null
    active.value = r.data.status === 'blocked' ? 0 : 1
    if (r.data.status === 'generating') {
      generatingQuiz.value = true
      pollTimer = setTimeout(pollSession, 800)
    }
  } catch (e: any) {
    status.value = 'blocked'
    microQuiz.value = { questions: [] }
    ElMessage.error(e?.response?.data?.detail || '建档流程启动失败')
  } finally {
    loading.value = false
  }
}

async function restartWithSelection() {
  if (!canStart.value) { ElMessage.warning('请选择至少一门可诊断课程'); return }
  await start(selectedCourseNames.value)
  if (blocked.value || generatingQuiz.value || !microQuiz.value.questions?.length) return
  active.value = 1
}

function backToCourseSelection() {
  clearPoll()
  generatingQuiz.value = false
  active.value = 0
}

async function submitQuiz() {
  const unanswered = microQuiz.value.questions.filter((q) => !answers.value[q.id])
  if (unanswered.length) { ElMessage.warning('请完成全部微测验题目'); return }
  loading.value = true
  try {
    const r = await api.post('/profile/onboarding/answer', {
      session_id: sessionId.value,
      step: 'micro_quiz',
      payload: { answers: answers.value },
    })
    diagnosis.value = r.data.diagnosis
    interviewQuestion.value = r.data.next_question || interviewQuestion.value
    active.value = 2
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '微测验提交失败')
  } finally {
    loading.value = false
  }
}

async function submitInterviewAnswer() {
  if (!interviewAnswer.value.trim()) { ElMessage.warning('请先回答当前问题'); return }
  loading.value = true
  try {
    const r = await api.post('/profile/onboarding/answer', {
      session_id: sessionId.value,
      step: 'interview',
      payload: {
        question: interviewQuestion.value,
        answer: interviewAnswer.value.trim(),
      },
    })
    interviewCount.value += 1
    interviewAnswer.value = ''
    if (r.data.next_step === 'knowledge_graph') {
      active.value = 3
    } else {
      interviewQuestion.value = r.data.next_question || ''
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '面试回答提交失败')
  } finally {
    loading.value = false
  }
}

async function submitGraphMarks() {
  loading.value = true
  try {
    await api.post('/profile/onboarding/answer', {
      session_id: sessionId.value,
      step: 'knowledge_graph',
      payload: { marks: graphMarks.value },
    })
    active.value = 4
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '知识图谱标记提交失败')
  } finally {
    loading.value = false
  }
}

async function finishOnboarding() {
  finishing.value = true
  try {
    const r = await api.post('/profile/onboarding/finish', {
      session_id: sessionId.value,
    })
    finishResult.value = r.data
    ElMessage.success('对话式画像建档完成')
    emit('done', r.data.profile)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '画像合成失败')
  } finally {
    finishing.value = false
  }
}

function markKp(kp: string, mark: string) {
  graphMarks.value = { ...graphMarks.value, [kp]: graphMarks.value[kp] === mark ? '' : mark }
}

function markType(kp: string) {
  const mark = graphMarks.value[kp]
  if (mark === 'familiar') return 'success'
  if (mark === 'unfamiliar') return 'danger'
  if (mark === 'focus') return 'warning'
  return 'info'
}

onMounted(() => prepare())
onBeforeUnmount(() => clearPoll())
</script>

<template>
  <el-dialog
    :model-value="true"
    width="760px"
    :close-on-click-modal="false"
    :show-close="false"
  >
    <template #header>
      <div class="onboard-header">
        <span>对话式学习画像建档</span>
        <el-steps :active="active" finish-status="success" align-center class="onboard-steps">
          <el-step title="课程确认" />
          <el-step title="微测验" />
          <el-step title="AI面试" />
          <el-step title="图谱标记" />
          <el-step title="画像确认" />
        </el-steps>
      </div>
    </template>

    <div v-loading="loading" class="onboard-body">
      <el-alert
        v-if="blocked"
        :title="message"
        type="warning"
        :closable="false"
        show-icon
      />

      <div v-if="active === 0" class="onboard-step">
        <h3>选择用于建档诊断的课程</h3>
        <p class="muted">系统只展示你培养方案中已配置课程知识点图谱的课程，不使用固定默认课程。</p>
        <el-checkbox-group v-model="selectedCourseNames">
          <div class="course-grid">
            <label v-for="course in availableCourses" :key="course.course_name" class="course-card">
              <el-checkbox :value="course.course_name">
                {{ course.course_name }}
              </el-checkbox>
              <div class="course-meta">第 {{ course.semester }} 学期 · {{ course.kp_count }} 个知识点</div>
            </label>
          </div>
        </el-checkbox-group>
        <div class="actions">
          <el-button @click="emit('cancel')">取消</el-button>
          <el-button type="primary" :disabled="!canStart" @click="restartWithSelection">进入微测验</el-button>
        </div>
      </div>

      <div v-else-if="active === 1" class="onboard-step">
        <h3>多课程微测验</h3>
        <p class="muted">题目覆盖所选课程的核心知识点，用于生成初始知识掌握画像。</p>
        <el-alert
          v-if="generatingQuiz || status === 'generating'"
          :title="message || '正在生成多课程微测验'"
          description="系统正在调用大模型围绕所选课程知识图谱出题。你可以停留在此页面等待，生成完成后会自动显示题目。"
          type="info"
          :closable="false"
          show-icon
        />
        <el-skeleton v-if="generatingQuiz || status === 'generating'" :rows="4" animated />
        <el-empty
          v-else-if="!microQuiz.questions?.length"
          description="暂无可作答的微测验题目，请返回重新选择课程或稍后重试。"
        />
        <div v-for="q in microQuiz.questions" :key="q.id" class="question-card">
          <div class="q-meta">{{ q.course_name }} · {{ q.knowledge_point }} · {{ q.difficulty }}</div>
          <div class="q-title">{{ q.question }}</div>
          <el-radio-group v-model="answers[q.id]" class="option-list">
            <el-radio v-for="opt in q.options || []" :key="opt.key" :value="opt.key">
              {{ opt.key }}. {{ opt.text }}
            </el-radio>
          </el-radio-group>
        </div>
        <div class="actions">
          <el-button @click="backToCourseSelection">返回选课</el-button>
          <el-button type="primary" :disabled="generatingQuiz || !microQuiz.questions?.length" @click="submitQuiz">提交微测验</el-button>
        </div>
      </div>

      <div v-else-if="active === 2" class="onboard-step">
        <h3>AI学习面试官</h3>
        <p class="muted">第 {{ Math.min(interviewCount + 1, 6) }} / 6 轮。用于采集学习目标、资源偏好和困难类型。</p>
        <div v-if="diagnosis" class="diagnosis-box">
          初步薄弱点：
          <el-tag v-for="kp in diagnosis.weak_points || []" :key="kp" size="small" type="warning">{{ kp }}</el-tag>
          <span v-if="!(diagnosis.weak_points || []).length">暂未发现明显薄弱点</span>
        </div>
        <div class="interview-question">{{ interviewQuestion }}</div>
        <el-input
          v-model="interviewAnswer"
          type="textarea"
          :rows="5"
          placeholder="用自然语言回答即可，例如：我想补基础，做题经常没思路，更喜欢图解和代码案例。"
        />
        <div class="actions">
          <el-button type="primary" @click="submitInterviewAnswer">提交回答</el-button>
        </div>
      </div>

      <div v-else-if="active === 3" class="onboard-step">
        <h3>多课程知识图谱标记</h3>
        <p class="muted">标记你对知识点的自评。测验结果优先，自评作为辅助证据。</p>
        <el-tabs>
          <el-tab-pane v-for="course in diagnosticCourses" :key="course.course_name" :label="course.course_name">
            <div class="kp-grid">
              <div
                v-for="node in (knowledgeGraphs[course.course_name]?.nodes || [])"
                :key="node.id"
                class="kp-card"
              >
                <div class="kp-name">{{ node.id }}</div>
                <div class="kp-actions">
                  <el-button size="small" :type="markType(node.id) === 'success' ? 'success' : ''" @click="markKp(node.id, 'familiar')">熟悉</el-button>
                  <el-button size="small" :type="markType(node.id) === 'danger' ? 'danger' : ''" @click="markKp(node.id, 'unfamiliar')">陌生</el-button>
                  <el-button size="small" :type="markType(node.id) === 'warning' ? 'warning' : ''" @click="markKp(node.id, 'focus')">重点学</el-button>
                </div>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
        <div class="actions">
          <el-button type="primary" @click="submitGraphMarks">提交图谱标记</el-button>
        </div>
      </div>

      <div v-else class="onboard-step">
        <h3>合成学习画像</h3>
        <p class="muted">系统将合并微测验、AI面试和知识图谱标记，生成多维学习画像。</p>
        <el-button type="primary" :loading="finishing" @click="finishOnboarding">生成画像</el-button>
        <div v-if="finishResult" class="diagnosis-box">
          已生成画像，推荐优先关注：
          <el-tag v-for="r in finishResult.next_recommendations || []" :key="r.course_name" type="warning" size="small">
            {{ r.course_name }}：{{ r.knowledge_points }}
          </el-tag>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.onboard-header { display: flex; align-items: center; gap: 20px; }
.onboard-header > span { font-size: 18px; font-weight: 700; color: #3A332E; white-space: nowrap; }
.onboard-steps { flex: 1; }
.onboard-body { min-height: 420px; }
.onboard-step { display: flex; flex-direction: column; gap: 14px; }
.onboard-step h3 { margin: 0; color: #3A332E; }
.muted { margin: 0; color: #7A6A5C; font-size: 13px; line-height: 1.7; }
.course-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.course-card { border: 1px solid #EFE6DC; border-radius: 10px; padding: 12px; background: #FFFBF5; cursor: pointer; }
.course-meta, .q-meta { margin-top: 6px; color: #948A80; font-size: 12px; }
.question-card { border: 1px solid #EFE6DC; border-radius: 10px; padding: 12px; background: #FFFBF5; }
.q-title { margin: 8px 0; font-weight: 600; color: #3A332E; }
.option-list { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.diagnosis-box { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; background: #FFF8EC; border: 1px solid #F3D6A1; border-radius: 10px; padding: 10px; color: #6B5344; font-size: 13px; }
.interview-question { background: #F7EFE6; border-radius: 10px; padding: 14px; color: #3A332E; font-weight: 600; }
.kp-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.kp-card { border: 1px solid #EFE6DC; border-radius: 10px; padding: 10px; background: #FFFBF5; }
.kp-name { font-weight: 600; color: #3A332E; margin-bottom: 8px; }
.kp-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
@media (max-width: 720px) {
  .course-grid, .kp-grid { grid-template-columns: 1fr; }
}
</style>
