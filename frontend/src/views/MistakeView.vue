<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import api from '../api'
import { useUserStore } from '../stores/user'
import { ElMessage } from 'element-plus'
import katex from 'katex'
import 'katex/dist/katex.min.css'

const userStore = useUserStore()
const loading = ref(false)
const items = ref<any[]>([])
const expandedId = ref<number | null>(null)
const analyzing = ref(false)
const analyses = ref<Record<number, any>>({})
const pendingRemove = ref<{ id: number; item: any } | null>(null)
const similarLoading = ref(false)
const similarProblems = ref<Record<number, any[]>>({})
const similarAnswers = ref<Record<string, string>>({})
const similarWrongCount = ref<Record<string, number>>({})
const similarAnalyses = ref<Record<string, any>>({})
const reviewProblems = ref<Record<number, any[]>>({})
const pendingReview = ref<Record<number, any[]>>({})
const reviewAnswers = ref<Record<string, string>>({})
const reviewCorrectCount = ref<Record<string, number>>({})
const reviewAttempts = ref<Record<string, number>>({})
const reviewAnalyses = ref<Record<string, any>>({})
const pendingReviewRemove = ref<{ mistakeId: number; ri: number; item: any } | null>(null)
let reviewRemoveTimer: ReturnType<typeof setTimeout> | null = null
let undoTimer: ReturnType<typeof setTimeout> | null = null

function loadReviewFromStorage() {
  try {
    const raw = localStorage.getItem(`mistake-review-${userStore.userId}`)
    if (raw) reviewProblems.value = JSON.parse(raw)
  } catch {}
}

function saveReviewToStorage() {
  localStorage.setItem(`mistake-review-${userStore.userId}`, JSON.stringify(reviewProblems.value))
}

function flushPendingReview(mistakeId: number | null) {
  if (!mistakeId) return
  const pending = pendingReview.value[mistakeId]
  if (!pending || pending.length === 0) return
  const existing = reviewProblems.value[mistakeId] || []
  for (const p of pending) {
    const dup = existing.find((r: any) => r.question === p.question)
    if (!dup) {
      if (!reviewProblems.value[mistakeId]) reviewProblems.value[mistakeId] = []
      reviewProblems.value[mistakeId].push(p)
    } else {
      dup.wrongCount = (dup.wrongCount || 1) + 1
      dup.lastWrong = new Date().toISOString()
    }
  }
  pendingReview.value[mistakeId] = []
  saveReviewToStorage()
}

function goBackToList() {
  if (expandedId.value != null) {
    flushPendingReview(expandedId.value)
  }
  expandedId.value = null
}

interface Group {
  label: string
  dateKey: string
  items: any[]
}

const groupedItems = computed<Group[]>(() => {
  const map = new Map<string, any[]>()
  for (const m of items.value) {
    const key = getDateKey(m.created_at)
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(m)
  }
  return Array.from(map.entries()).map(([key, list]) => ({
    label: formatDateLabel(key),
    dateKey: key,
    items: list,
  }))
})

function getDateKey(iso: string | null): string {
  if (!iso) return '未知'
  return iso.slice(0, 10)
}

function formatDateLabel(key: string): string {
  if (key === '未知') return '未知日期'
  const d = new Date(key + 'T00:00:00')
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const thatDay = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const diff = Math.floor((today.getTime() - thatDay.getTime()) / 86400000)
  if (diff === 0) return '今天'
  if (diff === 1) return '昨天'
  const m = d.getMonth() + 1
  const day = d.getDate()
  return `${m}/${day}`
}

async function loadMistakes() {
  if (!userStore.userId) return
  loadReviewFromStorage()
  loading.value = true
  try {
    const r = await api.get('/mistakes', { params: { user_id: userStore.userId } })
    items.value = r.data.items || []
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

async function toggleCard(m: any) {
  if (expandedId.value === m.id) {
    goBackToList()
    return
  }
  if (expandedId.value != null) {
    flushPendingReview(expandedId.value)
  }
  expandedId.value = m.id
  similarProblems.value[m.id] = undefined as any
  similarAnswers.value = {}
  similarWrongCount.value = {}
  similarAnalyses.value = {}
  pendingReview.value = {}
  reviewAnswers.value = {}
  reviewAnalyses.value = {}

  if (!analyses.value[m.id]) {
    analyzing.value = true
    try {
      const r = await api.post(`/mistakes/${m.id}/analyze`, null, {
        params: { user_id: userStore.userId },
      })
      analyses.value[m.id] = r.data.analysis || {}
    } catch {
      analyses.value[m.id] = { error_analysis: '分析失败，请重试' }
    } finally {
      analyzing.value = false
    }
  }
}

async function loadSimilar(m: any) {
  similarLoading.value = true
  similarProblems.value[m.id] = null as any
  similarAnswers.value = {}
  similarWrongCount.value = {}
  similarAnalyses.value = {}

  const excludeQuestions = (reviewProblems.value[m.id] || []).map((r: any) => r.question)

  try {
    const r = await api.post(`/mistakes/${m.id}/similar`, null, {
      params: { user_id: userStore.userId },
    })
    let problems = r.data.problems || []
    if (excludeQuestions.length > 0) {
      problems = problems.filter((p: any) => !excludeQuestions.includes(p.question))
    }
    similarProblems.value[m.id] = problems
  } catch {
    similarProblems.value[m.id] = []
  } finally {
    similarLoading.value = false
  }
}

async function selectSimilarOption(mistakeId: number, pi: number, option: string, problem: any) {
  const key = `${mistakeId}-${pi}`
  if (similarAnswers.value[key]) return

  similarAnswers.value[key] = option
  if (option !== problem.correct) {
    const cnt = (similarWrongCount.value[key] || 0) + 1
    similarWrongCount.value[key] = cnt

    if (!pendingReview.value[mistakeId]) pendingReview.value[mistakeId] = []
    const existing = pendingReview.value[mistakeId].find((r: any) => r.question === problem.question)
    if (!existing) {
      pendingReview.value[mistakeId].push({ ...problem, wrongCount: 1, lastWrong: new Date().toISOString() })
    } else {
      existing.wrongCount = (existing.wrongCount || 1) + 1
      existing.lastWrong = new Date().toISOString()
    }

    try {
      const r = await api.post('/mistakes/analyze-similar', {
        user_id: userStore.userId,
        question: problem.question,
        correct_answer: problem.correct,
        user_answer: option,
      })
      similarAnalyses.value[key] = r.data.analysis || {}
    } catch {
      similarAnalyses.value[key] = { error_analysis: '分析失败' }
    }
  }
}

function removeReviewProblem(mistakeId: number, ri: number) {
  if (!reviewProblems.value[mistakeId]) return
  const item = reviewProblems.value[mistakeId][ri]
  reviewProblems.value[mistakeId].splice(ri, 1)
  if (reviewProblems.value[mistakeId].length === 0) {
    delete reviewProblems.value[mistakeId]
  }
  saveReviewToStorage()
  pendingReviewRemove.value = { mistakeId, ri, item }

  if (reviewRemoveTimer) clearTimeout(reviewRemoveTimer)
  reviewRemoveTimer = setTimeout(() => {
    pendingReviewRemove.value = null
    reviewRemoveTimer = null
  }, 5000)
}

function undoReviewRemove() {
  if (!pendingReviewRemove.value) return
  if (reviewRemoveTimer) { clearTimeout(reviewRemoveTimer); reviewRemoveTimer = null }
  const { mistakeId, item } = pendingReviewRemove.value
  if (!reviewProblems.value[mistakeId]) reviewProblems.value[mistakeId] = []
  reviewProblems.value[mistakeId].push(item)
  saveReviewToStorage()
  pendingReviewRemove.value = null
}

async function selectReviewOption(mistakeId: number, ri: number, option: string, problem: any) {
  const key = `${mistakeId}-r${ri}`
  if (reviewAnswers.value[key]) return

  reviewAnswers.value[key] = option
  const attempts = (reviewAttempts.value[key] || 0) + 1
  reviewAttempts.value[key] = attempts
  const isCorrect = option === problem.correct
  if (isCorrect) {
    reviewCorrectCount.value[key] = (reviewCorrectCount.value[key] || 0) + 1
  }

  try {
    const r = await api.post('/mistakes/analyze-similar', {
      user_id: userStore.userId,
      question: problem.question,
      correct_answer: problem.correct,
      user_answer: option,
    })
    reviewAnalyses.value[key] = r.data.analysis || {}
  } catch {
    reviewAnalyses.value[key] = { error_analysis: '分析失败' }
  }
}

function reviewMastery(key: string): boolean {
  const correct = reviewCorrectCount.value[key] || 0
  const attempts = reviewAttempts.value[key] || 0
  if (attempts === 0) return false
  return correct >= 3 && correct / attempts >= 0.8
}

async function removeItem(id: number) {
  const target = items.value.find(i => i.id === id)
  if (!target) return
  if (expandedId.value === id) {
    goBackToList()
  }

  items.value = items.value.filter(i => i.id !== id)
  pendingRemove.value = { id, item: target }

  if (undoTimer) clearTimeout(undoTimer)
  undoTimer = setTimeout(async () => {
    try {
      await api.delete(`/mistakes/${pendingRemove.value?.id}`, { params: { user_id: userStore.userId } })
    } catch {}
    pendingRemove.value = null
    undoTimer = null
  }, 5000)
}

function undoRemove() {
  if (!pendingRemove.value) return
  if (undoTimer) { clearTimeout(undoTimer); undoTimer = null }
  items.value.push(pendingRemove.value.item)
  items.value.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
  pendingRemove.value = null
}

async function clearAll() {
  try {
    await api.delete('/mistakes', { params: { user_id: userStore.userId } })
    ElMessage.success('错题本已清空')
    expandedId.value = null
    loadMistakes()
  } catch {
    ElMessage.error('清空失败')
  }
}

onMounted(() => {
  loadMistakes()
})

watch(() => userStore.userId, () => {
  loadMistakes()
})

function isWrong(m: any): boolean {
  return m.user_answer !== m.correct_answer
}

function getOptionText(q: any, letter: string): string {
  if (!q || !letter) return letter || '-'
  if (letter.includes('. ')) return letter
  const options = q.options
  if (!options) return letter
  if (Array.isArray(options)) {
    const idx = letter.toUpperCase().charCodeAt(0) - 65
    const opt = options[idx]
    if (!opt) return letter
    return opt.startsWith(letter + '. ') ? opt : `${letter}. ${opt}`
  }
  if (typeof options === 'object') {
    const opt = options[letter]
    if (!opt) return letter
    return opt.startsWith(letter + '. ') ? opt : `${letter}. ${opt}`
  }
  return letter
}

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function renderMath(text: string): string {
  if (!text) return ''
  const mathBlocks: Array<{ formula: string; display: boolean }> = []

  let processed = text
    .replace(/\$\$([\s\S]*?)\$\$/g, (_m: string, formula: string) => {
      const idx = mathBlocks.length
      mathBlocks.push({ formula: formula.trim(), display: true })
      return `\uFFF0MB${idx}\uFFF1`
    })
    .replace(/\\\[([\s\S]*?)\\\]/g, (_m: string, formula: string) => {
      const idx = mathBlocks.length
      mathBlocks.push({ formula: formula.trim(), display: true })
      return `\uFFF0MB${idx}\uFFF1`
    })
    .replace(/\$([^$\n]+?)\$/g, (_m: string, formula: string) => {
      const idx = mathBlocks.length
      mathBlocks.push({ formula: formula.trim(), display: false })
      return `\uFFF0MB${idx}\uFFF1`
    })
    .replace(/\\\(([\s\S]*?)\\\)/g, (_m: string, formula: string) => {
      const idx = mathBlocks.length
      mathBlocks.push({ formula: formula.trim(), display: false })
      return `\uFFF0MB${idx}\uFFF1`
    })

  processed = escapeHtml(processed)

  processed = processed.replace(/\uFFF0MB(\d+)\uFFF1/g, (_m, idxStr) => {
    const idx = +idxStr
    const { formula, display } = mathBlocks[idx]
    try {
      const rendered = katex.renderToString(formula, { displayMode: display, throwOnError: false })
      return display
        ? `<div class="math-block">${rendered}</div>`
        : `<span class="math-inline">${rendered}</span>`
    } catch {
      return display
        ? `<div class="math-block">${escapeHtml(formula)}</div>`
        : `<span class="math-inline">${escapeHtml(formula)}</span>`
    }
  })

  return processed
}
</script>

<template>
  <div class="mistake-view">
    <div class="header">
      <h2>错题本</h2>
      <div class="ops">
        <el-button @click="loadMistakes">刷新</el-button>
        <el-button type="danger" plain @click="clearAll">清空</el-button>
      </div>
    </div>

    <div v-if="expandedId" class="m-back" @click="goBackToList">← 返回列表</div>

    <div v-if="pendingRemove" class="undo-bar">
      <span>已移除，5秒后永久删除</span>
      <el-button size="small" type="primary" text @click="undoRemove">撤回</el-button>
    </div>
    <div v-if="pendingReviewRemove" class="undo-bar">
      <span>错题回顾已移除，5秒后永久删除</span>
      <el-button size="small" type="primary" text @click="undoReviewRemove">撤回</el-button>
    </div>

    <div v-loading="loading">
      <el-empty v-if="items.length === 0 && !expandedId" description="暂无错题" />

      <template v-if="expandedId">
        <div v-for="m in items.filter(i => i.id === expandedId)" :key="m.id" class="m-card expanded">
          <div class="m-head">
            <el-tag size="small" :type="isWrong(m) ? 'danger' : 'warning'">
              {{ isWrong(m) ? '答错' : '手动加入' }}
            </el-tag>
            <span class="m-q-text" v-html="renderMath(m.question?.question || '题干缺失')"></span>
            <el-button size="small" text type="danger" @click="removeItem(m.id)">移除</el-button>
          </div>

          <div class="m-expand">
            <div v-if="analyzing && !analyses[m.id]" class="m-loading">分析中...</div>
            <template v-else-if="analyses[m.id]">
              <div class="m-section" v-if="isWrong(m)">
                <div class="m-label">错误分析</div>
                <div class="m-text" v-html="renderMath(analyses[m.id].error_analysis || '无')"></div>
              </div>
              <div class="m-section">
                <div class="m-label">你的选择</div>
                <div class="m-answer wrong" v-html="renderMath(getOptionText(m.question, m.user_answer))"></div>
              </div>
              <div class="m-section">
                <div class="m-label">正确答案</div>
                <div class="m-answer correct" v-html="renderMath(getOptionText(m.question, m.correct_answer))"></div>
              </div>
              <div class="m-section" v-if="m.question?.explanation">
                <div class="m-label">解析</div>
                <div class="m-text" v-html="renderMath(m.question.explanation)"></div>
              </div>
              <div class="m-section" v-if="analyses[m.id].confused_points?.length">
                <div class="m-label">混淆知识点</div>
                <div class="m-tags">
                  <el-tag v-for="pt in analyses[m.id].confused_points" :key="pt" size="small" type="warning">{{ pt }}</el-tag>
                </div>
              </div>
              <div class="m-section" v-if="analyses[m.id].weak_points?.length">
                <div class="m-label">薄弱知识点</div>
                <div class="m-tags">
                  <el-tag v-for="pt in analyses[m.id].weak_points" :key="pt" size="small" type="danger">{{ pt }}</el-tag>
                </div>
              </div>
              <div class="m-section" v-if="analyses[m.id].key_concepts?.length">
                <div class="m-label">核心知识点</div>
                <div class="m-tags">
                  <el-tag v-for="pt in analyses[m.id].key_concepts" :key="pt" size="small">{{ pt }}</el-tag>
                </div>
              </div>
            </template>

            <div v-if="reviewProblems[m.id]?.length" class="m-review">
              <div class="m-review-header">错题回顾</div>
              <div
                v-for="(r, ri) in reviewProblems[m.id]"
                :key="ri"
                class="m-review-item"
              >
                <div class="m-review-item-head">
                  <span class="m-q-text" v-html="renderMath(`${ri + 1}. ${r.question}`)"></span>
                  <el-button
                    v-if="reviewMastery(`${m.id}-r${ri}`)"
                    size="small"
                    type="danger"
                    text
                    class="m-review-remove-btn"
                    @click.stop="removeReviewProblem(m.id, ri)"
                  >移除</el-button>
                </div>
                <div class="m-options">
                  <span
                    v-for="opt in r.options"
                    :key="opt"
                    :class="['m-opt-btn', {
                      selected: reviewAnswers[`${m.id}-r${ri}`] === opt.charAt(0),
                      correct: reviewAnswers[`${m.id}-r${ri}`] && opt.charAt(0) === r.correct,
                      wrong: reviewAnswers[`${m.id}-r${ri}`] === opt.charAt(0) && opt.charAt(0) !== r.correct,
                    }]"
                    @click.stop="selectReviewOption(m.id, ri, opt.charAt(0), r)"
                  >
                    <span v-html="renderMath(opt)"></span>
                  </span>
                </div>

                <div v-if="reviewAnswers[`${m.id}-r${ri}`]" class="m-similar-result">
                  <div class="m-similar-answer">
                    <span class="m-similar-label">正确答案：</span><b>{{ r.correct }}</b>
                  </div>
                  <div class="m-text" v-if="r.explanation" v-html="renderMath(r.explanation)"></div>

                  <div class="m-opt-explanations" v-if="r.option_explanations">
                    <div v-for="(exp, letter) in r.option_explanations" :key="letter" class="m-opt-exp-item">
                      <b :class="{ 'c-green': letter === r.correct, 'c-red': letter === reviewAnswers[`${m.id}-r${ri}`] && letter !== r.correct }">{{ letter }}</b>：<span v-html="renderMath(exp)"></span>
                    </div>
                  </div>

                  <template v-if="reviewAnswers[`${m.id}-r${ri}`] !== r.correct && reviewAnalyses[`${m.id}-r${ri}`]">
                    <div class="m-text" v-if="reviewAnalyses[`${m.id}-r${ri}`].error_analysis && reviewAnalyses[`${m.id}-r${ri}`].error_analysis !== '无'">
                      <span class="m-label">错误分析：</span><span v-html="renderMath(reviewAnalyses[`${m.id}-r${ri}`].error_analysis)"></span>
                    </div>
                    <div class="m-tags" v-if="reviewAnalyses[`${m.id}-r${ri}`].confused_points?.length">
                      <span class="m-tag-label">混淆：</span>
                      <el-tag v-for="pt in reviewAnalyses[`${m.id}-r${ri}`].confused_points" :key="pt" size="small" type="warning">{{ pt }}</el-tag>
                    </div>
                    <div class="m-tags" v-if="reviewAnalyses[`${m.id}-r${ri}`].weak_points?.length">
                      <span class="m-tag-label">薄弱：</span>
                      <el-tag v-for="pt in reviewAnalyses[`${m.id}-r${ri}`].weak_points" :key="pt" size="small" type="danger">{{ pt }}</el-tag>
                    </div>
                  </template>

                  <div class="m-review-meta">
                    <span>正确 {{ reviewCorrectCount[`${m.id}-r${ri}`] || 0 }}/{{ reviewAttempts[`${m.id}-r${ri}`] || 0 }}</span>
                  </div>
                  <div v-if="reviewMastery(`${m.id}-r${ri}`)" class="m-mastery-hint">
                    您已掌握该题目，可从错题回顾中移除
                  </div>
                </div>
              </div>
            </div>

            <div class="m-similar-bar">
              <el-button
                type="primary"
                size="small"
                :loading="similarLoading"
                @click.stop="loadSimilar(m)"
              >
                举一反三
              </el-button>
            </div>

            <div v-if="similarProblems[m.id]?.length" class="m-similar">
              <div
                v-for="(p, pi) in similarProblems[m.id]"
                :key="pi"
                class="m-similar-card"
              >
                <div class="m-q-text" v-html="renderMath(`${pi + 1}. ${p.question}`)"></div>
                <div class="m-options">
                  <span
                    v-for="opt in p.options"
                    :key="opt"
                    :class="['m-opt-btn', {
                      selected: similarAnswers[`${m.id}-${pi}`] === opt.charAt(0),
                      correct: similarAnswers[`${m.id}-${pi}`] && opt.charAt(0) === p.correct,
                      wrong: similarAnswers[`${m.id}-${pi}`] === opt.charAt(0) && opt.charAt(0) !== p.correct,
                    }]"
                    @click.stop="selectSimilarOption(m.id, pi, opt.charAt(0), p)"
                  >
                    <span v-html="renderMath(opt)"></span>
                  </span>
                </div>
                <div v-if="similarAnswers[`${m.id}-${pi}`]" class="m-similar-result">
                  <div class="m-similar-answer">
                    <span class="m-similar-label">正确答案：</span><b>{{ p.correct }}</b>
                  </div>
                  <div class="m-text" v-if="p.explanation" v-html="renderMath(p.explanation)"></div>

                  <div class="m-opt-explanations" v-if="p.option_explanations">
                    <div v-for="(exp, letter) in p.option_explanations" :key="letter" class="m-opt-exp-item">
                      <b :class="{ 'c-green': letter === p.correct, 'c-red': letter === similarAnswers[`${m.id}-${pi}`] && letter !== p.correct }">{{ letter }}</b>：<span v-html="renderMath(exp)"></span>
                    </div>
                  </div>

                  <template v-if="similarAnalyses[`${m.id}-${pi}`]">
                    <div class="m-text" v-if="similarAnalyses[`${m.id}-${pi}`].error_analysis && similarAnalyses[`${m.id}-${pi}`].error_analysis !== '无'">
                      <span class="m-label">错误分析：</span><span v-html="renderMath(similarAnalyses[`${m.id}-${pi}`].error_analysis)"></span>
                    </div>
                    <div class="m-tags" v-if="similarAnalyses[`${m.id}-${pi}`].confused_points?.length">
                      <span class="m-tag-label">混淆：</span>
                      <el-tag v-for="pt in similarAnalyses[`${m.id}-${pi}`].confused_points" :key="pt" size="small" type="warning">{{ pt }}</el-tag>
                    </div>
                    <div class="m-tags" v-if="similarAnalyses[`${m.id}-${pi}`].weak_points?.length">
                      <span class="m-tag-label">薄弱：</span>
                      <el-tag v-for="pt in similarAnalyses[`${m.id}-${pi}`].weak_points" :key="pt" size="small" type="danger">{{ pt }}</el-tag>
                    </div>
                  </template>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <div v-for="group in groupedItems" :key="group.dateKey" class="m-group">
          <div class="m-group-header">{{ group.label }}</div>
          <div
            v-for="m in group.items"
            :key="m.id"
            class="m-card"
            @click="toggleCard(m)"
          >
            <div class="m-head">
              <el-tag size="small" :type="isWrong(m) ? 'danger' : 'warning'">
                {{ isWrong(m) ? '答错' : '手动加入' }}
              </el-tag>
            <span class="m-q-text" v-html="renderMath(m.question?.question || '题干缺失')"></span>
              <el-button size="small" text type="danger" @click.stop="removeItem(m.id)">移除</el-button>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.mistake-view { max-width: 900px; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.header h2 { margin: 0; color: #303133; }
.ops { display: flex; gap: 8px; }
.m-group { margin-bottom: 20px; }

.undo-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fdf6ec;
  border: 1px solid #faecd8;
  border-radius: 6px;
  padding: 8px 14px;
  margin-bottom: 14px;
  font-size: 13px;
  color: #e6a23c;
  position: fixed;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 900px;
  max-width: calc(100vw - 260px);
  z-index: 100;
}

.m-back {
  font-size: 14px;
  color: #409eff;
  cursor: pointer;
  padding: 8px 0;
  margin-bottom: 12px;
  display: block;
  text-align: left;
  user-select: none;
}
.m-back:hover { color: #337ecc; }

.m-group-header {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  padding: 6px 0;
  margin-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
}

.m-card {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 10px;
  cursor: pointer;
  transition: box-shadow 0.15s;
}

.m-card:hover { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06); }

.m-head { display: flex; align-items: center; gap: 10px; }
.m-q-text { flex: 1; color: #303133; font-size: 14px; line-height: 1.5; }

.m-expand { margin-top: 14px; padding-top: 14px; border-top: 1px solid #f0f0f0; }

.m-section { margin-bottom: 12px; text-align: left; }
.m-label { font-size: 12px; color: #909399; margin-bottom: 4px; font-weight: 500; text-align: left; }
.m-text { font-size: 13px; color: #606266; line-height: 1.6; text-align: left; }
.m-answer { font-size: 14px; font-weight: 600; padding: 4px 10px; border-radius: 4px; display: block; text-align: left; }
.m-answer.wrong { background: #fef0f0; color: #f56c6c; }
.m-answer.correct { background: #f0f9eb; color: #67c23a; }
.m-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.m-loading { color: #909399; font-size: 13px; padding: 8px 0; }

.m-similar-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}

.m-review { margin-top: 14px; padding-top: 12px; border-top: 1px solid #f0f0f0; }
.m-review-header { font-size: 14px; font-weight: 600; color: #303133; margin-bottom: 10px; }

.m-review-item {
  background: #fdf6ec;
  border: 1px solid #faecd8;
  border-radius: 6px;
  padding: 12px 14px;
  margin-bottom: 10px;
}

.m-review-item-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.m-review-remove-btn {
  flex-shrink: 0;
  margin-left: 8px;
}

.m-review-meta {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  margin-top: 8px;
  font-size: 12px;
  gap: 12px;
}

.m-mastery-hint { color: #67c23a; font-weight: 500; text-align: center; padding-top: 6px; }

.m-review-correct { color: #67c23a; font-weight: 500; }

.m-opt-static { font-size: 13px; color: #606266; padding: 2px 8px; }

.m-similar { margin-top: 14px; }

.m-similar-card {
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px 14px;
  margin-bottom: 10px;
}

.m-options { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
.m-opt-btn {
  font-size: 13px;
  color: #606266;
  padding: 4px 14px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}
.m-opt-btn:hover { border-color: #409eff; color: #409eff; }
.m-opt-btn.selected.correct { background: #f0f9eb; border-color: #67c23a; color: #67c23a; }
.m-opt-btn.selected.wrong { background: #fef0f0; border-color: #f56c6c; color: #f56c6c; }

.m-similar-result { margin-top: 10px; padding-top: 10px; border-top: 1px solid #f0f0f0; }

.m-similar-answer { font-size: 13px; color: #67c23a; margin: 6px 0; text-align: left; }
.m-similar-label { color: #909399; font-weight: 400; }

.m-wrong-count { font-size: 12px; color: #f56c6c; margin-top: 6px; text-align: right; }

.m-opt-explanations { margin: 10px 0; }
.m-opt-exp-item { font-size: 12px; color: #606266; line-height: 1.7; text-align: left; }
.m-opt-exp-item b { margin-right: 4px; }
.c-green { color: #67c23a; }
.c-red { color: #f56c6c; }

.m-tag-label { font-size: 12px; color: #909399; vertical-align: middle; margin-right: 4px; }

.m-similar-card .m-text { text-align: left; }
.m-similar-card .m-q-text { text-align: left; }
.m-q-text { flex: 1; color: #303133; font-size: 14px; line-height: 1.5; text-align: left; }
.m-q-text :deep(.math-block) { display: block; text-align: center; margin: 10px 0; overflow-x: auto; }
.m-q-text :deep(.math-inline) { padding: 0 2px; }
.m-text :deep(.math-block) { display: block; text-align: center; margin: 10px 0; overflow-x: auto; }
.m-text :deep(.math-inline) { padding: 0 2px; }
.m-answer :deep(.math-block) { display: block; text-align: center; margin: 6px 0; overflow-x: auto; }
.m-answer :deep(.math-inline) { padding: 0 2px; }
.m-opt-btn :deep(.math-inline) { padding: 0 2px; }
.m-opt-exp-item :deep(.math-inline) { padding: 0 2px; }
.m-opt-exp-item :deep(.math-block) { display: block; text-align: center; margin: 6px 0; overflow-x: auto; }
</style>
