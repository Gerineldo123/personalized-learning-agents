<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import api from '../../api'
import { ElMessage } from 'element-plus'
import { renderMathInline } from '../../utils/markdown'

function formatExplanation(text: string): string {
  if (!text) return ''
  return text
    .replace(/([A-D])[.、]/g, '\n$1. ')
    .replace(/选项([A-D])/g, '\n选项$1')
}

interface QuizQuestion {
  id: number
  type: string
  question: string
  options: string[]
  answer: string
  explanation: string
  option_explanations?: Record<string, string>
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

    for (const q of props.content.questions || []) {
      const qid = Number(q.id)
      if (answers.value[qid] !== q.answer && !markedSet.value[qid]) {
        try {
          await api.post('/mistakes/add', null, {
            params: {
              user_id: props.userId,
              resource_id: props.resourceId,
              question_id: qid,
              reason: 'auto_wrong',
              question: JSON.stringify(q),
              user_answer: String(answers.value[qid] || ''),
              correct_answer: String(q.answer || ''),
            },
          })
          markedSet.value[qid] = true
        } catch { /* skip */ }
      }
    }

    ElMessage.success(`正确率 ${Math.round(score * 100)}%`)
  } catch {
    ElMessage.error('提交失败')
  } finally {
    submitting.value = false
  }
}

defineExpose({ submitted, submitting, submitQuiz, restartQuiz })
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
      <template v-if="latestSubmittedAt">（{{ latestSubmittedAt.slice(0, 10) }}）</template>
    </div>

    <div v-for="q in content.questions" :key="q.id" class="quiz-question">
      <div class="question-text" v-html="renderMathInline(`${q.id}. ${q.question}`)" />

      <el-radio-group
        v-model="answers[q.id]"
        :disabled="showExplanation[q.id]"
        @change="(val: string) => selectAnswer(q.id, val)"
      >
        <el-radio v-for="opt in q.options" :key="opt" :value="opt.charAt(0)">
          <span v-html="renderMathInline(opt)" />
        </el-radio>
      </el-radio-group>

      <div v-if="showExplanation[q.id]" class="quiz-result">
        <el-button class="mistake-btn" size="small" text :disabled="markedSet[q.id]" @click="markToMistake(q)">
          {{ markedSet[q.id] ? '已加错题本' : '+ 错题本' }}
        </el-button>
        <el-tag :type="isCorrect(q.id) ? 'success' : 'danger'" size="small">
          {{ isCorrect(q.id) ? '正确' : '错误' }}
        </el-tag>
        <p class="explanation" v-html="renderMathInline(formatExplanation(q.explanation))" />
        <div v-if="q.option_explanations" class="opt-explanations">
          <div v-for="(exp, letter) in q.option_explanations" :key="letter" class="opt-exp-item">
            <b :class="{ 'c-green': letter === q.answer, 'c-red': letter === answers[q.id] && letter !== q.answer }">{{ letter }}</b>
            <span v-html="renderMathInline(exp)" />
          </div>
        </div>
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
  text-align: left;
}

.quiz-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid #ebeef5;
}

.quiz-header h3 { margin: 0; color: #303133; text-align: center; flex: 1; }

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
  word-break: break-word;
  overflow-wrap: break-word;
}

.quiz-question :deep(.el-radio) {
  display: flex;
  white-space: normal;
  word-break: break-word;
  height: auto;
  align-items: flex-start;
  padding: 4px 0;
  margin-right: 0;
}

.quiz-question :deep(.el-radio__label) {
  white-space: normal;
  word-break: break-word;
  line-height: 1.6;
}

.quiz-result {
  position: relative;
  margin-top: 12px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 4px;
  text-align: center;
}

.mistake-btn {
  position: absolute;
  top: 8px;
  right: 10px;
  color: #409eff !important;
  font-weight: 700;
  font-size: 12px;
}

.explanation {
  margin: 8px 0 0;
  color: #606266;
  font-size: 13px;
  text-align: left;
  white-space: pre-line;
}

.opt-explanations {
  margin: 12px 0 0;
  padding: 10px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}

.opt-exp-item {
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
  text-align: left;
}

.opt-exp-item b {
  display: inline-block;
  width: 20px;
  font-weight: 700;
}

.c-green { color: #67c23a; }
.c-red { color: #f56c6c; }
</style>
