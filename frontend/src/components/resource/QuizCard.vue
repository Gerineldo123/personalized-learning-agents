<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import api from '../../api'
import { ElMessage } from 'element-plus'

interface QuizQuestion {
  id: number
  type: string
  question: string
  options: string[]
  answer: string
  explanation: string
}

const props = defineProps<{ content: { title?: string; questions?: QuizQuestion[] }; resourceId?: number; userId?: string }>()

const answers = ref<Record<number, string>>({})
const showExplanation = ref<Record<number, boolean>>({})
const submitted = ref(false)
const submitting = ref(false)
const loadingLatest = ref(false)
const latestScore = ref<number | null>(null)
const latestSubmittedAt = ref<string>('')
const markedSet = ref<Record<number, boolean>>({})

const storageKey = computed(() => {
  if (!props.userId || !props.resourceId) return ''
  return `quiz_progress_${props.userId}_${props.resourceId}`
})

function loadProgress() {
  if (!storageKey.value) return
  try {
    const raw = localStorage.getItem(storageKey.value)
    if (!raw) return
    const saved = JSON.parse(raw)
    answers.value = saved.answers || {}
    showExplanation.value = saved.showExplanation || {}
    submitted.value = Boolean(saved.submitted)
    latestScore.value = typeof saved.latestScore === 'number' ? saved.latestScore : latestScore.value
    latestSubmittedAt.value = saved.latestSubmittedAt || latestSubmittedAt.value
    markedSet.value = saved.markedSet || {}
  } catch {
    answers.value = {}
    showExplanation.value = {}
    submitted.value = false
    markedSet.value = {}
  }
}

function saveProgress() {
  if (!storageKey.value) return
  const payload = {
    answers: answers.value,
    showExplanation: showExplanation.value,
    submitted: submitted.value,
    latestScore: latestScore.value,
    latestSubmittedAt: latestSubmittedAt.value,
    markedSet: markedSet.value,
  }
  localStorage.setItem(storageKey.value, JSON.stringify(payload))
}

async function loadLatestRecord() {
  if (!props.userId || !props.resourceId) return
  loadingLatest.value = true
  try {
    const r = await api.get('/quiz/latest', {
      params: { user_id: props.userId, resource_id: props.resourceId },
    })
    if (r.data?.found && r.data?.record) {
      const rec = r.data.record
      answers.value = rec.answers || {}
      showExplanation.value = Object.keys(rec.answers || {}).reduce((acc: Record<number, boolean>, k: string) => {
        acc[Number(k)] = true
        return acc
      }, {})
      submitted.value = true
      latestScore.value = typeof rec.score === 'number' ? rec.score : null
      latestSubmittedAt.value = rec.created_at || ''
    }
  } catch {
    // keep local cache fallback
  } finally {
    loadingLatest.value = false
  }
}

onMounted(async () => {
  loadProgress()
  await loadLatestRecord()
})

watch(storageKey, async () => {
  answers.value = {}
  showExplanation.value = {}
  submitted.value = false
  latestScore.value = null
  latestSubmittedAt.value = ''
  markedSet.value = {}
  loadProgress()
  await loadLatestRecord()
})

watch([answers, showExplanation, submitted, latestScore, latestSubmittedAt, markedSet], () => {
  saveProgress()
}, { deep: true })

function selectAnswer(qId: number, option: string) {
  answers.value[qId] = option
  showExplanation.value[qId] = true
}

function restartQuiz() {
  submitted.value = false
  answers.value = {}
  showExplanation.value = {}
}

function isCorrect(qId: number): boolean | null {
  if (!answers.value[qId]) return null
  const q = props.content.questions?.find((x) => x.id === qId)
  return q?.answer === answers.value[qId]
}

const correctCount = computed(() => {
  let count = 0
  for (const q of props.content.questions || []) {
    if (answers.value[q.id] === q.answer) count++
  }
  return count
})

const totalCount = computed(() => props.content.questions?.length || 0)
const latestScorePct = computed(() => latestScore.value == null ? null : Math.round(latestScore.value * 100))

async function markToMistake(q: QuizQuestion) {
  if (!props.userId || !props.resourceId) return
  const qid = Number(q.id)
  const userAns = String(answers.value[qid] || '')
  const correctAns = String(q.answer || '')
  try {
    await api.post('/mistakes/add', null, {
      params: {
        user_id: props.userId,
        resource_id: props.resourceId,
        question_id: qid,
        reason: userAns && userAns === correctAns ? 'manual_mark' : 'auto_wrong',
        question: JSON.stringify(q),
        user_answer: userAns,
        correct_answer: correctAns,
      },
    })
    markedSet.value[qid] = true
    ElMessage.success('已加入错题本')
  } catch {
    ElMessage.error('加入错题本失败')
  }
}

async function submitQuiz() {
  if (!props.userId || !props.resourceId) return
  const answered = Object.keys(answers.value).length
  if (answered < (props.content.questions?.length || 0)) {
    ElMessage.warning('请完成所有题目后再提交')
    return
  }
  submitting.value = true
  try {
    const total = totalCount.value
    const score = total > 0 ? correctCount.value / total : 0
    await api.post('/quiz/submit', {
        user_id: props.userId,
        resource_id: props.resourceId,
        answers: answers.value,
        score,
        time_spent: 0,
      })
    submitted.value = true
    latestScore.value = score
    latestSubmittedAt.value = new Date().toISOString()
    ElMessage.success(`正确率 ${Math.round(score * 100)}%`)
  } catch {
    ElMessage.error('提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="quiz-card">
    <div class="quiz-header">
      <h3>{{ content.title || '练习题' }}</h3>
      <span class="score">{{ correctCount }} / {{ totalCount }}</span>
      <div class="actions">
        <el-button v-if="submitted" size="small" type="warning" plain @click="restartQuiz">
          重新作答
        </el-button>
        <el-button type="primary" size="small" :loading="submitting || loadingLatest" :disabled="submitted" @click="submitQuiz">
          {{ submitted ? '已提交' : '提交' }}
        </el-button>
      </div>
    </div>

    <div v-if="submitted && latestScorePct !== null" class="latest-meta">
      上次作答：正确率 {{ latestScorePct }}%
      <template v-if="latestSubmittedAt">（{{ latestSubmittedAt.replace('T', ' ').slice(0, 19) }}）</template>
    </div>

    <div v-for="q in content.questions" :key="q.id" class="quiz-question">
      <div class="question-text">
        <span class="q-num">{{ q.id }}.</span> {{ q.question }}
      </div>

      <el-radio-group
        v-model="answers[q.id]"
        :disabled="showExplanation[q.id]"
        @change="(val: string) => selectAnswer(q.id, val)"
      >
        <el-radio v-for="opt in q.options" :key="opt" :value="opt.charAt(0)">
          {{ opt }}
        </el-radio>
      </el-radio-group>

      <div v-if="showExplanation[q.id]" class="quiz-result">
        <el-tag :type="isCorrect(q.id) ? 'success' : 'danger'" size="small">
          {{ isCorrect(q.id) ? '正确' : '错误' }}
        </el-tag>
        <p class="explanation">{{ q.explanation }}</p>
        <el-button size="small" type="danger" text :disabled="markedSet[q.id]" @click="markToMistake(q)">
          {{ markedSet[q.id] ? '已加入错题本' : '加入错题本' }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.quiz-card {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  padding: 20px;
}

.quiz-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid #ebeef5;
}

.quiz-header h3 { margin: 0; color: #303133; }

.score {
  font-size: 18px;
  font-weight: 700;
  color: #409eff;
}

.actions {
  display: flex;
  gap: 8px;
}

.latest-meta {
  margin-bottom: 12px;
  color: #909399;
  font-size: 12px;
}

.quiz-question {
  margin-bottom: 24px;
}

.question-text {
  margin-bottom: 12px;
  color: #303133;
  line-height: 1.6;
}

.q-num {
  font-weight: 700;
  color: #409eff;
}

.quiz-result {
  margin-top: 12px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 4px;
}

.explanation {
  margin: 8px 0 0;
  color: #606266;
  font-size: 13px;
}
</style>
