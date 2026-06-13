<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import api from '../../api'
import { ElMessage } from 'element-plus'
import { renderMathInline } from '../../utils/markdown'

interface TestCase { input: string; expected: string }
interface QuizQuestion {
  id: number
  type: string
  question: string
  // single_choice
  options?: string[]
  // fill_blank / single_choice
  answer: string
  explanation: string
  // coding
  function_signature?: string
  test_cases?: TestCase[]
  code_lang?: string
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

// coding: per-question judge results & running state
const judgeResults = ref<Record<number, any>>({})
const judging = ref<Record<number, boolean>>({})
// coding: editable code per question (initialized from function_signature)
const codeAnswers = ref<Record<number, string>>({})

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
    codeAnswers.value = saved.codeAnswers || {}
    judgeResults.value = saved.judgeResults || {}
  } catch {
    answers.value = {}
    showExplanation.value = {}
    submitted.value = false
    markedSet.value = {}
  }
}

function saveProgress() {
  if (!storageKey.value) return
  localStorage.setItem(storageKey.value, JSON.stringify({
    answers: answers.value,
    showExplanation: showExplanation.value,
    submitted: submitted.value,
    latestScore: latestScore.value,
    latestSubmittedAt: latestSubmittedAt.value,
    markedSet: markedSet.value,
    codeAnswers: codeAnswers.value,
    judgeResults: judgeResults.value,
  }))
}

async function loadLatestRecord() {
  if (!props.userId || !props.resourceId) return
  loadingLatest.value = true
  try {
    const r = await api.get('/quiz/latest', { params: { user_id: props.userId, resource_id: props.resourceId } })
    if (r.data?.found && r.data?.record) {
      const rec = r.data.record
      answers.value = rec.answers || {}
      showExplanation.value = Object.keys(rec.answers || {}).reduce((acc: Record<number, boolean>, k: string) => {
        acc[Number(k)] = true; return acc
      }, {})
      submitted.value = true
      latestScore.value = typeof rec.score === 'number' ? rec.score : null
      latestSubmittedAt.value = rec.created_at || ''
    }
  } catch { /* keep local cache */ } finally { loadingLatest.value = false }
}

onMounted(async () => {
  loadProgress()
  initCodeAnswers()
  await loadLatestRecord()
})

function initCodeAnswers() {
  for (const q of props.content.questions || []) {
    if (q.type === 'coding' && !codeAnswers.value[q.id]) {
      codeAnswers.value[q.id] = q.function_signature ? q.function_signature + '\n    pass' : ''
    }
  }
}

watch(storageKey, async () => {
  answers.value = {}; showExplanation.value = {}; submitted.value = false
  latestScore.value = null; latestSubmittedAt.value = ''
  markedSet.value = {}; codeAnswers.value = {}; judgeResults.value = {}
  loadProgress(); initCodeAnswers(); await loadLatestRecord()
})

watch([answers, showExplanation, submitted, latestScore, latestSubmittedAt, markedSet, codeAnswers, judgeResults], () => {
  saveProgress()
}, { deep: true })

function selectAnswer(qId: number, option: string) {
  answers.value[qId] = option
  showExplanation.value[qId] = true
}

function confirmFillBlank(q: QuizQuestion) {
  if (!answers.value[q.id]?.trim()) return
  showExplanation.value[q.id] = true
}

async function runCode(q: QuizQuestion) {
  const code = codeAnswers.value[q.id]
  if (!code?.trim()) return
  judging.value[q.id] = true
  try {
      const r = await api.post('/quiz/judge', {
        question_id: q.id,
        code: code,
        test_cases: q.test_cases || [],
        code_lang: (q as any).code_lang || 'python',
      })
    judgeResults.value[q.id] = r.data
    // store score ratio as answer
    answers.value[q.id] = String(r.data.score ?? 0)
    showExplanation.value[q.id] = true
  } catch {
    ElMessage.error('判题失败')
  } finally {
    judging.value[q.id] = false
  }
}

function restartQuiz() {
  submitted.value = false
  answers.value = {}
  showExplanation.value = {}
  judgeResults.value = {}
  initCodeAnswers()
}

function isCorrect(q: QuizQuestion): boolean | null {
  if (!answers.value[q.id]) return null
  if (q.type === 'single_choice') return q.answer === answers.value[q.id]
  if (q.type === 'fill_blank') return answers.value[q.id].trim().toLowerCase() === q.answer.trim().toLowerCase()
  if (q.type === 'coding') return (judgeResults.value[q.id]?.score ?? 0) >= 1.0
  return null
}

const correctCount = computed(() => {
  let count = 0
  for (const q of props.content.questions || []) {
    if (q.type === 'coding') {
      const r = judgeResults.value[q.id]
      if (r && r.score >= 1.0) count++
    } else if (q.type === 'fill_blank') {
      if ((answers.value[q.id] || '').trim().toLowerCase() === q.answer.trim().toLowerCase()) count++
    } else {
      if (answers.value[q.id] === q.answer) count++
    }
  }
  return count
})

const totalCount = computed(() => props.content.questions?.length || 0)
const latestScorePct = computed(() => latestScore.value == null ? null : Math.round(latestScore.value * 100))

async function markToMistake(q: QuizQuestion) {
  if (!props.userId || !props.resourceId) return
  const qid = Number(q.id)
  const userAns = String(answers.value[qid] || '')
  try {
    await api.post('/mistakes/add', null, {
      params: {
        user_id: props.userId, resource_id: props.resourceId, question_id: qid,
        reason: 'auto_wrong', question: JSON.stringify(q),
        user_answer: userAns, correct_answer: String(q.answer || ''),
      },
    })
    markedSet.value[qid] = true
    ElMessage.success('已加入错题本')
  } catch { ElMessage.error('加入错题本失败') }
}

async function submitQuiz() {
  if (!props.userId || !props.resourceId) return
  const answered = Object.keys(answers.value).length
  if (answered < (props.content.questions?.length || 0)) {
    ElMessage.warning('请完成所有题目后再提交'); return
  }
  submitting.value = true
  try {
    const total = totalCount.value
    const score = total > 0 ? correctCount.value / total : 0
    await api.post('/quiz/submit', {
      user_id: props.userId, resource_id: props.resourceId,
      answers: answers.value, score, time_spent: 0,
    })
    submitted.value = true
    latestScore.value = score
    latestSubmittedAt.value = new Date().toISOString()
    ElMessage.success(`正确率 ${Math.round(score * 100)}%`)
  } catch { ElMessage.error('提交失败') } finally { submitting.value = false }
}
</script>

<template>
  <div class="quiz-card">
    <div class="quiz-header">
      <h3>{{ content.title || '练习题' }}</h3>
      <span class="score">{{ correctCount }} / {{ totalCount }}</span>
      <div class="actions">
        <el-button v-if="submitted" size="small" type="warning" plain @click="restartQuiz">重新作答</el-button>
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
      <div class="question-meta">
        <el-tag size="small" :type="q.type === 'coding' ? 'success' : q.type === 'fill_blank' ? 'warning' : ''">
          {{ q.type === 'coding' ? '编程题' : q.type === 'fill_blank' ? '填空题' : '选择题' }}
        </el-tag>
      </div>
      <div class="question-text" v-html="renderMathInline(`${q.id}. ${q.question}`)" />

      <!-- 单选题 -->
      <template v-if="q.type === 'single_choice'">
        <el-radio-group v-model="answers[q.id]" :disabled="showExplanation[q.id]"
          @change="(val: string) => selectAnswer(q.id, val)">
          <el-radio v-for="opt in q.options" :key="opt" :value="opt.charAt(0)">
            <span v-html="renderMathInline(opt)" />
          </el-radio>
        </el-radio-group>
      </template>

      <!-- 填空题 -->
      <template v-else-if="q.type === 'fill_blank'">
        <div class="fill-blank-row">
          <el-input v-model="answers[q.id]" :disabled="showExplanation[q.id]" placeholder="输入答案..." style="width:320px" @keyup.enter="confirmFillBlank(q)" />
          <el-button v-if="!showExplanation[q.id]" size="small" type="primary" @click="confirmFillBlank(q)">确认</el-button>
        </div>
      </template>

      <!-- 编程题 -->
      <template v-else-if="q.type === 'coding'">
        <div class="coding-block">
          <el-input
            v-model="codeAnswers[q.id]"
            type="textarea"
            :rows="8"
            :disabled="submitted"
            :placeholder="`在此输入你的 ${(q as any).code_lang || 'Python'} 代码...`"
            class="code-editor"
          />
          <div class="coding-actions">
            <el-button
              size="small" type="success"
              :loading="judging[q.id]"
              :disabled="submitted || !codeAnswers[q.id]"
              @click="runCode(q)"
            >运行测试</el-button>
          </div>
          <!-- 测试用例结果 -->
          <div v-if="judgeResults[q.id]" class="judge-results">
            <div v-for="(tc, i) in judgeResults[q.id].results" :key="i" class="tc-row">
              <el-tag :type="tc.passed ? 'success' : 'danger'" size="small">{{ tc.passed ? '通过' : '失败' }}</el-tag>
              <code>输入: {{ tc.input }}</code>
              <code>期望: {{ tc.expected }}</code>
              <code v-if="!tc.passed">实际: {{ tc.actual || tc.error }}</code>
            </div>
            <div class="judge-summary">
              通过 {{ judgeResults[q.id].passed }} / {{ judgeResults[q.id].total }} 个测试用例
            </div>
          </div>
        </div>
      </template>

      <!-- 解析区 -->
      <div v-if="showExplanation[q.id]" class="quiz-result">
        <el-tag :type="isCorrect(q) ? 'success' : 'danger'" size="small">
          {{ isCorrect(q) ? '正确' : (q.type === 'coding' ? `通过率 ${Math.round((judgeResults[q.id]?.score ?? 0) * 100)}%` : '错误') }}
        </el-tag>
        <p v-if="q.type !== 'coding'" class="explanation">
          正确答案：<strong>{{ q.answer }}</strong>
        </p>
        <p class="explanation" v-html="renderMathInline(q.explanation)" />
        <el-button size="small" type="danger" text :disabled="markedSet[q.id]" @click="markToMistake(q)">
          {{ markedSet[q.id] ? '已加入错题本' : '加入错题本' }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.quiz-card { background: #fff; border-radius: 8px; border: 1px solid #e4e7ed; padding: 20px; }
.quiz-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid #ebeef5; }
.quiz-header h3 { margin: 0; color: #303133; }
.score { font-size: 18px; font-weight: 700; color: #409eff; }
.actions { display: flex; gap: 8px; }
.latest-meta { margin-bottom: 12px; color: #909399; font-size: 12px; }
.quiz-question { margin-bottom: 24px; }
.question-meta { margin-bottom: 6px; }
.question-text { margin-bottom: 12px; color: #303133; line-height: 1.6; }
.fill-blank-row { display: flex; gap: 8px; align-items: center; }
.coding-block { display: flex; flex-direction: column; gap: 8px; }
.code-editor :deep(textarea) { font-family: 'Courier New', monospace; font-size: 13px; }
.coding-actions { display: flex; gap: 8px; }
.judge-results { background: #f5f7fa; border-radius: 4px; padding: 10px; display: flex; flex-direction: column; gap: 6px; }
.tc-row { display: flex; gap: 10px; align-items: center; font-size: 12px; flex-wrap: wrap; }
.tc-row code { background: #e8eaed; padding: 1px 6px; border-radius: 3px; }
.judge-summary { font-size: 12px; color: #606266; font-weight: 600; margin-top: 4px; }
.quiz-result { margin-top: 12px; padding: 12px; background: #f5f7fa; border-radius: 4px; }
.explanation { margin: 8px 0 0; color: #606266; font-size: 13px; }
</style>
