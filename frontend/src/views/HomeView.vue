<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import api from '../api'
import { useUserStore } from '../stores/user'
import { useSausageSkinStore, SAUSAGE_SKINS } from '../stores/sausageSkin'
import SausageIcon from '../components/SausageIcon.vue'
import SkinUnlockPopup from '../components/SkinUnlockPopup.vue'

const router = useRouter()
const userStore = useUserStore()
const skinStore = useSausageSkinStore()
const previewSkin = ref<{ id: string; locked: boolean } | null>(null)

function showSkinPreview(id: string) {
  previewSkin.value = { id, locked: !skinStore.unlockedSkins.includes(id) }
}

function closeSkinPreview() {
  previewSkin.value = null
}

const hasFocusSessions = computed(() => {
  try {
    const raw = localStorage.getItem('focus-sessions')
    if (!raw) return false
    const sessions = JSON.parse(raw)
    return Array.isArray(sessions) && sessions.length > 0
  } catch {
    return false
  }
})

const barChartRef = ref<HTMLDivElement>()
const radarChartRef = ref<HTMLDivElement>()
const homeQuery = ref('')
const insightsRowRef = ref<HTMLDivElement>()
const insightsVisible = ref(false)
const weeklyUsage = ref({
  days: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
  morning: [0, 0, 0, 0, 0, 0, 0],
  afternoon: [0, 0, 0, 0, 0, 0, 0],
  evening: [0, 0, 0, 0, 0, 0, 0],
})
const hasWeeklyUsageData = computed(() => {
  const all = [
    ...weeklyUsage.value.morning,
    ...weeklyUsage.value.afternoon,
    ...weeklyUsage.value.evening,
  ]
  return all.some((x) => Number(x) > 0)
})
let barChart: echarts.ECharts | null = null
let radarChart: echarts.ECharts | null = null
let insightsObserver: IntersectionObserver | null = null

const profile = ref<any>(null)
const abilityDims = ['知识记忆', '逻辑推理', '应用实践', '信息整合', '应试能力']
const courseColors = ['#E35749', '#49BBC8', '#F3B86B']
const hasRadarData = computed(() => {
  return !!(profile.value?.weak_courses?.length)
})

const suggestedQuestions = ref<string[]>([])

async function loadSuggestedQuestions() {
  if (!userStore.userId) return
  try {
    const r = await api.get('/resources', { params: { user_id: userStore.userId, limit: 20 } })
    const items: Array<{ title?: string }> = r.data.items || []
    const questions: string[] = []
    for (const item of items) {
      const title = item.title
      if (!title || title.length < 2) continue
      if (title.length <= 20) {
        questions.push(`讲解一下"${title}"的核心概念`)
        questions.push(`"${title}"的重点是什么？`)
      } else {
        questions.push(`请帮我理解"${title}"`)
      }
      if (questions.length >= 16) break
    }
    suggestedQuestions.value = questions
  } catch { suggestedQuestions.value = [] }
}

function suggestOpenChat(q: string) {
  router.push({
    path: '/agent',
    query: { from: 'home', t: String(Date.now()), q },
  })
}

const kColors = ['#f8d5a4', '#ee9b8f', '#95d7da']
const knowledgeAreas = ref([
  { name: 'article', type: 'article', icon: '📄', count: 0, color: kColors[0] },
  { name: 'quiz', type: 'quiz', icon: '❓', count: 0, color: kColors[1] },
  { name: 'code', type: 'code', icon: '💻', count: 0, color: kColors[2] },
  { name: 'mindmap', type: 'mindmap', icon: '🧠', count: 0, color: kColors[0] },
  { name: 'ppt', type: 'ppt', icon: '📊', count: 0, color: kColors[1] },
  { name: 'all resources', type: '', icon: '📦', count: 0, color: kColors[2] },
])

const defaultCounts = { article: 0, quiz: 0, code: 0, mindmap: 0, ppt: 0, all: 0 }

async function loadKnowledgeAreaCounts() {
  const userId = userStore.userId
  if (!userId) {
    knowledgeAreas.value = [
      { name: 'article', type: 'article', icon: '📄', count: 0, color: kColors[0] },
      { name: 'quiz', type: 'quiz', icon: '❓', count: 0, color: kColors[1] },
      { name: 'code', type: 'code', icon: '💻', count: 0, color: kColors[2] },
      { name: 'mindmap', type: 'mindmap', icon: '🧠', count: 0, color: kColors[0] },
      { name: 'ppt', type: 'ppt', icon: '📊', count: 0, color: kColors[1] },
      { name: 'all resources', type: '', icon: '📦', count: 0, color: kColors[2] },
    ]
    return
  }
  const counts = { ...defaultCounts }
  try {
    const res = await api.get('/resources', { params: { user_id: userId } })
    const items: Array<{ resource_type?: string }> = res.data.items || []
    for (const item of items) {
      const type = item.resource_type || ''
      counts.all += 1
      if (type === 'article') counts.article += 1
      else if (type === 'quiz') counts.quiz += 1
      else if (type === 'code') counts.code += 1
      else if (type === 'mindmap') counts.mindmap += 1
      else if (type === 'ppt') counts.ppt += 1
    }
  } catch {}
  knowledgeAreas.value = [
    { name: 'article', type: 'article', icon: '📄', count: counts.article, color: kColors[0] },
    { name: 'quiz', type: 'quiz', icon: '❓', count: counts.quiz, color: kColors[1] },
    { name: 'code', type: 'code', icon: '💻', count: counts.code, color: kColors[2] },
    { name: 'mindmap', type: 'mindmap', icon: '🧠', count: counts.mindmap, color: kColors[0] },
    { name: 'ppt', type: 'ppt', icon: '📊', count: counts.ppt, color: kColors[1] },
    { name: 'all resources', type: '', icon: '📦', count: counts.all, color: kColors[2] },
  ]
}

function openResourcesByType(type: string) {
  router.push({ path: '/resources', query: type ? { type } : {} })
}

function initBarChart() {
  if (!barChartRef.value) return
  if (!hasWeeklyUsageData.value) { barChart?.dispose(); barChart = null; return }
  const maxPerDay = weeklyUsage.value.days.map((_, i) => {
    return Number(weeklyUsage.value.morning[i] || 0) + Number(weeklyUsage.value.afternoon[i] || 0) + Number(weeklyUsage.value.evening[i] || 0)
  })
  const yMax = Math.max(1, Math.ceil(Math.max(...maxPerDay)))
  barChart = echarts.init(barChartRef.value)
  barChart.setOption({
    tooltip: { trigger: 'axis', backgroundColor: '#FFFBF5', borderColor: '#EFE6DC', borderRadius: 8, textStyle: { color: '#3A332E', fontSize: 12 } },
    legend: { data: ['上午', '下午', '晚间'], bottom: 0, textStyle: { color: '#7C5C3C', fontSize: 11, fontWeight: 500 }, itemWidth: 10, itemHeight: 10, itemGap: 16 },
    grid: { left: 40, right: 12, top: 32, bottom: 36 },
    xAxis: { type: 'category', data: weeklyUsage.value.days, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#948A80', fontSize: 10 } },
    yAxis: { type: 'value', min: 0, max: yMax, interval: 1, splitLine: { lineStyle: { color: '#EFE6DC' } }, axisLabel: { color: '#948A80', fontSize: 10 }, axisLine: { show: false }, axisTick: { show: false } },
    series: [
      { name: '上午', type: 'bar', stack: 'total', barWidth: 24, data: weeklyUsage.value.morning, itemStyle: { color: '#AECDD0', borderRadius: [4, 4, 0, 0] } },
      { name: '下午', type: 'bar', stack: 'total', barWidth: 24, data: weeklyUsage.value.afternoon, itemStyle: { color: '#F3B86B' } },
      { name: '晚间', type: 'bar', stack: 'total', barWidth: 24, data: weeklyUsage.value.evening, itemStyle: { color: '#FCDDDA', borderRadius: [0, 0, 4, 4] } },
    ],
  })
}

async function loadWeeklyUsage() {
  if (!userStore.userId) return
  try {
    const r = await api.get('/conversations/weekly-usage', { params: { user_id: userStore.userId } })
    weeklyUsage.value = {
      days: r.data.days || weeklyUsage.value.days,
      morning: r.data.morning || weeklyUsage.value.morning,
      afternoon: r.data.afternoon || weeklyUsage.value.afternoon,
      evening: r.data.evening || weeklyUsage.value.evening,
    }
  } catch {}
}

async function loadProfile() {
  if (!userStore.userId) return
  try {
    const r = await api.get('/profile', { params: { user_id: userStore.userId } })
    if (r.data.found) profile.value = r.data.profile
    else profile.value = null
  } catch { profile.value = null }
}

function initRadarChart() {
  if (!radarChartRef.value) return
  const weakCourses = profile.value?.weak_courses || []
  const seriesData: any[] = []
  const legendData: string[] = []
  weakCourses.slice(0, 3).forEach((course: any, i: number) => {
    const scores = course.course_ability_scores || {}
    const values = abilityDims.map(d => scores[d] || 0)
    const color = courseColors[i]
    seriesData.push({ value: values, name: course.name || `课程${i + 1}`, lineStyle: { color }, itemStyle: { color }, areaStyle: { color } })
    legendData.push(course.name || `课程${i + 1}`)
  })
  radarChart = echarts.init(radarChartRef.value)
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
    legend: { data: legendData, bottom: 0, textStyle: { color: '#7C5C3C', fontSize: 11 }, itemWidth: 10, itemHeight: 10 },
  })
}

onMounted(async () => {
  await Promise.all([loadWeeklyUsage(), loadProfile()])
  await nextTick()
  initBarChart()
  initRadarChart()
  window.addEventListener('resize', () => { barChart?.resize(); radarChart?.resize() })
  skinStore.loadFromStorage()
  skinStore.checkUnlocks()
  loadKnowledgeAreaCounts()
  loadSuggestedQuestions()

  if (insightsRowRef.value) {
    insightsObserver = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            insightsVisible.value = true
            insightsObserver?.disconnect()
            insightsObserver = null
            break
          }
        }
      },
      { threshold: 0.2 }
    )
    insightsObserver.observe(insightsRowRef.value)
  }
})

onBeforeUnmount(() => {
  if (insightsObserver) { insightsObserver.disconnect(); insightsObserver = null }
})

watch(() => userStore.userId, async () => {
  loadKnowledgeAreaCounts()
  await Promise.all([loadWeeklyUsage(), loadProfile()])
  await nextTick()
  initBarChart()
  initRadarChart()
})

function openAiChat() {
  const q = homeQuery.value.trim()
  router.push({
    path: '/agent',
    query: { from: 'home', t: String(Date.now()), ...(q ? { q } : {}) },
  })
}

function handleSearchKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') { e.preventDefault(); openAiChat() }
}
</script>

<template>
  <div class="canva-page">
    <div class="canva-bg">
      <div class="hero-section animate-up animate-delay-1">
        <div class="hero-heading">今天想学点什么？</div>
        <button class="hero-search animate-up animate-delay-2" type="button" @click="openAiChat">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="7" stroke="#948A80" stroke-width="2"/><path d="M20 20l-3.5-3.5" stroke="#948A80" stroke-width="2" stroke-linecap="round"/></svg>
          <input
            v-model="homeQuery"
            class="hero-search-input"
            placeholder="查找你需要的知识点，回车即可和 AI 对话"
            @keydown="handleSearchKeydown"
            @click.stop
          />
        </button>
        <div v-if="suggestedQuestions.length > 0" class="hero-suggest">
          <div class="hero-suggest-track">
            <button v-for="(q, i) in suggestedQuestions" :key="'hs-' + i" class="hero-suggest-btn" @click="suggestOpenChat(q)">{{ q }}</button>
            <button v-for="(q, i) in suggestedQuestions" :key="'hs-dup-' + i" class="hero-suggest-btn" @click="suggestOpenChat(q)">{{ q }}</button>
          </div>
        </div>
      </div>

      <div class="card-main animate-up animate-delay-3">
        <div class="card-main-section card-main-left">
          <div class="card-main-title">知识领域</div>
          <div class="knowledge-grid">
            <button v-for="area in knowledgeAreas" :key="area.name" class="k-card" :style="{ '--kc': area.color }" @click="openResourcesByType(area.type)">
              <span class="k-icon">{{ area.icon }}</span>
              <span class="k-name">{{ area.name }}</span>
              <span class="k-count">{{ area.count }} 个</span>
            </button>
          </div>
        </div>

        <div class="card-main-section card-main-right">
          <div class="card-main-title">快捷入口</div>
          <div class="quick-actions">
            <button class="qa-btn" @click="router.push('/agent')">
              <span class="qa-dot" style="background:#E35749"></span>
              <div><div class="qa-label">AI 智能助手</div><div class="qa-sub">智能问答助手</div></div>
            </button>
            <button class="qa-btn" @click="router.push('/profile')">
              <span class="qa-dot" style="background:#49BBC8"></span>
              <div><div class="qa-label">学习画像</div><div class="qa-sub">个性化诊断</div></div>
            </button>
            <button class="qa-btn" @click="router.push('/mistakes')">
              <span class="qa-dot" style="background:#F3B86B"></span>
              <div><div class="qa-label">错题本</div><div class="qa-sub">查漏补缺提升</div></div>
            </button>
            <button class="qa-btn" @click="router.push('/resources')">
              <span class="qa-dot" style="background:#AECDD0"></span>
              <div><div class="qa-label">学习资源</div><div class="qa-sub">丰富学习材料</div></div>
            </button>
          </div>
        </div>
      </div>

      <div ref="insightsRowRef" class="insights-row" :class="{ 'in-view': insightsVisible }">
        <div class="card-stats" @click="router.push('/path')">
          <div class="card-stats-title">专注淀粉肠</div>
          <div v-if="hasWeeklyUsageData" class="card-stats-chart" ref="barChartRef"></div>
          <div v-if="!hasFocusSessions" class="card-stats-empty">本周尚无专注记录，继续加油！</div>
          <div v-if="hasFocusSessions" class="home-skin-strip">
            <div
              v-for="skin in SAUSAGE_SKINS.filter(s => skinStore.unlockedSkins.includes(s.id))"
              :key="skin.id"
              :class="['home-skin-item', { 'home-skin-active': skinStore.selectedSkin === skin.id }]"
              @click.stop="showSkinPreview(skin.id)"
            >
              <SausageIcon :size="96" :skin="skin.id" />
              <div class="home-skin-name">{{ skin.name }}</div>
            </div>
          </div>
        </div>

        <div class="card-radar clickable-card" @click="router.push('/profile')">
          <div class="card-radar-title">能力对比</div>
          <div v-if="hasRadarData" class="card-radar-chart" ref="radarChartRef"></div>
          <div v-else class="card-stats-empty">暂无学习画像数据</div>
        </div>
      </div>

      <div class="indicator-row">
        <span class="indicator-dot active"></span>
        <span class="indicator-dot"></span>
        <span class="indicator-dot"></span>
        <span class="indicator-dot"></span>
        <span class="indicator-dot"></span>
      </div>
    </div>
  </div>
  <SkinUnlockPopup :preview-skin="previewSkin" @close="closeSkinPreview" @done="closeSkinPreview" />
</template>

<style scoped>
.canva-page {
  width: 100%;
  min-height: 100%;
  background: linear-gradient(180deg, #F9D9B8 0%, #FFF5EB 45%, #FFFBF5 100%);
  padding: 28px 20px 34px;
  box-sizing: border-box;
  margin: -28px -32px;
  width: calc(100% + 64px);
}

.canva-bg {
  position: relative;
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
}

.hero-section {
  position: relative;
  z-index: 2;
  margin-bottom: 18px;
  padding-top: 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.hero-heading {
  font-size: 35.5px;
  font-weight: 600;
  color: #3A332E;
  letter-spacing: -2px;
  line-height: 1.15;
  margin-bottom: 24px;
  text-align: center;
}

.hero-search {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 33.3333%;
  padding: 10px 20px;
  background: #FFFBF5;
  border: 1.5px solid #EFE6DC;
  border-radius: 10px;
  font-size: 15px;
  color: #3A332E;
  cursor: pointer;
  transition: border-color 0.2s;
  text-align: left;
}
.hero-search:hover { border-color: #E8C29C; }

.hero-search-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  color: #3A332E;
  font-size: 15px;
  min-width: 0;
}
.hero-search-input::placeholder { color: #948A80; }

.hero-suggest {
  margin-top: 18px;
  overflow: hidden;
  width: 100%;
}
.hero-suggest:hover .hero-suggest-track { animation-play-state: paused; }

.hero-suggest-track {
  display: flex;
  gap: 10px;
  width: max-content;
  animation: scrollLtr 120s linear infinite;
}

@keyframes scrollLtr {
  0% { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}

.hero-suggest-btn {
  flex-shrink: 0;
  padding: 8px 20px;
  border: 1.5px solid #EFE6DC;
  border-radius: 22px;
  background: #FFFBF5;
  color: #948A80;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}
.hero-suggest-btn:hover {
  border-color: #E8C29C;
  background: #FFF5EB;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(58, 51, 46, 0.08);
}

@keyframes floatUpIn {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-up { opacity: 0; animation: floatUpIn 0.55s cubic-bezier(0.2, 0.75, 0.22, 1) forwards; }
.animate-delay-1 { animation-delay: 0.08s; }
.animate-delay-2 { animation-delay: 0.16s; }
.animate-delay-3 { animation-delay: 0.24s; }

.card-main {
  position: relative;
  z-index: 2;
  display: flex;
  gap: 20px;
  background: #FFFBF5;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 4px 24px rgba(58, 51, 46, 0.08);
  margin-bottom: 28px;
  width: min(100%, 1280px);
  margin-left: auto;
  margin-right: auto;
  box-sizing: border-box;
}
.card-main-left { flex: 1; }
.card-main-right { width: 320px; flex-shrink: 0; }

.card-main-title {
  font-size: 20px;
  font-weight: 500;
  color: #3A332E;
  margin-bottom: 18px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-main-title::before {
  content: '';
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #F9D9B8;
}
.card-main-right .card-main-title::before { background: #49BBC8; }

.knowledge-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  gap: 12px;
}

.k-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  min-height: 124px;
  padding: 20px 10px;
  border: 1.5px solid #EFE6DC;
  border-radius: 12px;
  background: #FFFBF5;
  cursor: pointer;
  transition: all 0.2s;
}
.k-card:hover {
  border-color: var(--kc);
  background: linear-gradient(135deg, #FFFBF5, color-mix(in srgb, var(--kc) 8%, #FFFBF5));
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(58, 51, 46, 0.08);
}
.k-icon { font-size: 26px; }
.k-name { font-size: 14px; font-weight: 500; color: #3A332E; text-align: center; line-height: 1.35; }
.k-count { font-size: 12px; color: #948A80; padding: 2px 8px; background: #FFF5EB; border-radius: 8px; }

.quick-actions { display: flex; flex-direction: column; gap: 10px; }

.qa-btn {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 68px;
  padding: 14px 16px;
  border: 1.5px solid #EFE6DC;
  border-radius: 12px;
  background: #FFFBF5;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}
.qa-btn:hover {
  border-color: #E8C29C;
  background: #FFF5EB;
  box-shadow: 0 2px 10px rgba(58, 51, 46, 0.08);
}
.qa-dot { width: 36px; height: 36px; border-radius: 50%; flex-shrink: 0; }
.qa-label { font-size: 14px; font-weight: 500; color: #3A332E; }
.qa-sub { font-size: 12px; color: #948A80; margin-top: 2px; }

.insights-row {
  position: relative;
  z-index: 2;
  display: flex;
  gap: 24px;
  align-items: stretch;
  width: min(100%, 1280px);
  margin-left: auto;
  margin-right: auto;
  margin-bottom: 24px;
  box-sizing: border-box;
  opacity: 0;
  transform: translateY(14px);
  transition: opacity 0.55s cubic-bezier(0.2, 0.75, 0.22, 1), transform 0.55s cubic-bezier(0.2, 0.75, 0.22, 1);
}
.insights-row.in-view { opacity: 1; transform: translateY(0); }

.card-stats {
  flex: 1.2;
  background: #FFFBF5;
  border-radius: 12px;
  padding: 28px;
  box-shadow: 0 4px 24px rgba(58, 51, 46, 0.08);
  cursor: pointer;
}

.card-stats-title {
  font-size: 16px;
  font-weight: 500;
  color: #3A332E;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-stats-title::before { content: ''; width: 8px; height: 8px; border-radius: 50%; background: #F3B86B; }

.card-stats-chart { width: 100%; height: 260px; }
.card-stats-empty { width: 100%; height: 260px; display: flex; align-items: center; justify-content: center; color: #948A80; font-size: 12px; }

.home-skin-strip {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 24px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #EFE6DC;
  flex-wrap: wrap;
}

.home-skin-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 16px 24px;
  border-radius: 14px;
  border: 2px solid transparent;
  transition: all 0.2s;
  min-width: 140px;
}
.home-skin-item:hover { border-color: #EFE6DC; background: rgba(249,217,184,0.08); }
.home-skin-active { border-color: #F9D9B8; background: rgba(249,217,184,0.12); }
.home-skin-name { font-size: 15px; color: #3A332E; font-weight: 500; white-space: nowrap; }

.card-radar {
  flex: 1;
  background: #FFFBF5;
  border-radius: 12px;
  padding: 28px;
  box-shadow: 0 4px 24px rgba(58, 51, 46, 0.08);
}
.clickable-card { cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; }
.clickable-card:hover { transform: translateY(-2px); box-shadow: 0 8px 28px rgba(58, 51, 46, 0.12); }

.card-radar-title {
  font-size: 16px;
  font-weight: 500;
  color: #3A332E;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-radar-title::before { content: ''; width: 8px; height: 8px; border-radius: 50%; background: #E35749; }
.card-radar-chart { width: 100%; height: 260px; }

.indicator-row {
  position: absolute;
  right: 80px;
  bottom: 100px;
  z-index: 3;
  display: flex;
  gap: 10px;
}
.indicator-dot { width: 10px; height: 10px; border-radius: 50%; background: #DBA878; opacity: 0.3; }
.indicator-dot.active { opacity: 1; box-shadow: 0 0 6px rgba(219, 168, 120, 0.4); }

@media (max-width: 1024px) {
  .canva-page { margin: -28px -32px; width: calc(100% + 64px); }
  .card-main { flex-direction: column; width: 100%; }
  .card-main-right { width: 100%; }
  .card-stats { flex: 1; }
  .insights-row { flex-direction: column; width: 100%; }
  .card-radar { width: 100%; }
  .knowledge-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 640px) {
  .canva-page { padding: 24px 16px 60px; margin: -28px -32px; width: calc(100% + 64px); }
  .hero-heading { font-size: 32px; }
  .hero-section { margin-bottom: 40px; }
  .knowledge-grid { grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .indicator-row { display: none; }
  .hero-search { width: 90%; }
}
</style>
