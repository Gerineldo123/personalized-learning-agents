<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { useUserStore } from '../stores/user'

type ResourceCount = {
  article: number
  quiz: number
  code: number
  anime: number
  mindmap: number
  ppt: number
  video: number
  all: number
}

const router = useRouter()
const userStore = useUserStore()

const homeQuery = ref('')
const insightsRowRef = ref<HTMLDivElement>()
const insightsVisible = ref(false)
let insightsObserver: IntersectionObserver | null = null

const profile = ref<any>(null)
const suggestedQuestions = ref<string[]>([])
const resourceCounts = ref<ResourceCount>({
  article: 0,
  quiz: 0,
  code: 0,
  anime: 0,
  mindmap: 0,
  ppt: 0,
  video: 0,
  all: 0,
})

const knowledgeBase = computed<Record<string, number>>(() => profile.value?.knowledge_base || {})
const measuredKnowledgeCount = computed(() => Object.keys(knowledgeBase.value).length)
const masteredKnowledgeCount = computed(() => Object.values(knowledgeBase.value).filter(score => Number(score || 0) >= 0.8).length)
const weakPoints = computed<string[]>(() => (profile.value?.weak_points || []).filter(Boolean))
const weakPointsPreview = computed(() => weakPoints.value.slice(0, 8))
const hasProfileEvidence = computed(() => {
  const evidence = profile.value?.profile_evidence || {}
  return Boolean(
    profile.value?.learning_goal
    || profile.value?.cognitive_style
    || profile.value?.preferred_format
    || Object.keys(evidence).length
    || measuredKnowledgeCount.value
    || weakPoints.value.length
  )
})

const knowledgeAreas = computed(() => [
  { name: '文章', type: 'article', icon: '📄', count: resourceCounts.value.article, color: '#F8D5A4' },
  { name: '题库', type: 'quiz', icon: '❓', count: resourceCounts.value.quiz, color: '#EE9B8F' },
  { name: '动画', type: 'anime', icon: '🎬', count: resourceCounts.value.anime, color: '#95D7DA' },
  { name: '思维导图', type: 'mindmap', icon: '🧠', count: resourceCounts.value.mindmap, color: '#F8D5A4' },
  { name: 'PPT课件', type: 'ppt', icon: '📊', count: resourceCounts.value.ppt, color: '#EE9B8F' },
  { name: '全部资源', type: '', icon: '📦', count: resourceCounts.value.all, color: '#95D7DA' },
])

const guideSteps = computed(() => [
  {
    order: 1,
    title: '完成学习画像建档',
    desc: '通过微测验和 AI 面试建立画像，系统才能判断目标、偏好和薄弱点。',
    done: hasProfileEvidence.value,
    action: '开始建档',
    path: '/profile',
    query: { onboarding: '1' },
  },
  {
    order: 2,
    title: '查看专业知识图谱',
    desc: '确认当前专业课程关系，点击课程查看先修、后继和课内知识点。',
    done: Boolean(profile.value?.major),
    action: '查看图谱',
    path: '/profile',
    query: {},
  },
  {
    order: 3,
    title: '生成第一个学习资源包',
    desc: '从课程或薄弱知识点出发，生成文章、题库、动画、视频等学习资源。',
    done: resourceCounts.value.all > 0,
    action: '生成资源',
    path: '/resources',
    query: {},
  },
])

const moduleGuides = [
  {
    title: '学习画像',
    desc: '记录专业、目标、薄弱点和资源偏好，是推荐资源和路径的依据。',
    path: '/profile',
    action: '建档/更新',
  },
  {
    title: '学习资源',
    desc: '统一管理文章、题库、动画、视频、PPT，可按课程和知识点筛选。',
    path: '/resources',
    action: '查看资源',
  },
  {
    title: '学习路径',
    desc: '用于整门课程或阶段学习，按知识图谱组织步骤和验收题。',
    path: '/learning-path',
    action: '规划课程',
  },
  {
    title: 'AI 智能助手',
    desc: '对话模式用于答疑，任务模式用于生成动画、题库、视频和课件。',
    path: '/agent',
    action: '去提问',
  },
  {
    title: '错题本',
    desc: '沉淀错题并定位薄弱知识点，可继续生成针对性补弱资源。',
    path: '/mistakes',
    action: '复盘错题',
  },
  {
    title: '专注成长',
    desc: '记录学习时长和专注行为，为后续学习建议提供行为证据。',
    path: '/focus',
    action: '开始专注',
  },
]

const loopStats = computed(() => [
  { label: '学习资源', value: resourceCounts.value.all, unit: '个', hint: '文章、题库、导图、课件等资源总量', path: '/resources' },
  { label: '题库资源', value: resourceCounts.value.quiz, unit: '套', hint: '提交题目后自动更新掌握度', path: '/resources', query: { type: 'quiz' } },
  { label: '已测知识点', value: measuredKnowledgeCount.value, unit: '个', hint: `已掌握 ${masteredKnowledgeCount.value} 个`, path: '/profile' },
  { label: '薄弱知识点', value: weakPoints.value.length, unit: '个', hint: '来自微测验、题库和错题记录', path: '/profile' },
])

const nextActions = computed(() => {
  if (!hasProfileEvidence.value) {
    return [{
      title: '先完成学习画像建档',
      desc: '建档后系统才能生成个性化资源、路径和补弱建议。',
      path: '/profile',
      query: { onboarding: '1' },
    }]
  }
  return [
    {
      title: weakPoints.value.length ? '优先处理薄弱知识点' : '完成一次诊断测验',
      desc: weakPoints.value.length ? `当前有 ${weakPoints.value.length} 个薄弱知识点，建议生成专项练习。` : '题目提交后才会形成可信掌握度和薄弱点。',
      path: weakPoints.value.length ? '/resources' : '/profile',
      query: weakPoints.value.length ? {} : { onboarding: '1' },
    },
    {
      title: resourceCounts.value.quiz ? '继续做题更新掌握度' : '先生成题库资源',
      desc: resourceCounts.value.quiz ? '提交题目后会直接刷新画像和知识图谱掌握度。' : '从课程或知识点生成专项题库，开始形成学习证据。',
      path: '/resources',
      query: resourceCounts.value.quiz ? { type: 'quiz' } : {},
    },
    {
      title: '让 AI 助手解释一个卡点',
      desc: '适合概念解释、公式推导、学习建议；生成资源请切换到任务模式。',
      path: '/agent',
      query: {},
    },
  ]
})

async function goAgent(query?: string) {
  const q = (query ?? homeQuery.value).trim()
  await router.push({
    path: '/agent',
    query: q ? { from: 'home', t: String(Date.now()), q, auto_submit: '1' } : {},
  })
}

function openResourcesByType(type: string) {
  router.push({ path: '/resources', query: type ? { type } : {} })
}

function goPath(path: string, query: Record<string, any> = {}) {
  router.push({ path, query })
}

async function loadSuggestedQuestions() {
  if (!userStore.userId) return
  try {
    const r = await api.get('/resources', { params: { user_id: userStore.userId, limit: 20 } })
    const items: Array<{ title?: string }> = r.data.items || []
    const questions: string[] = []
    for (const item of items) {
      const title = (item.title || '').trim()
      if (!title || title.length < 2) continue
      questions.push(title.length <= 20 ? `讲解一下“${title}”的核心概念` : `请帮我理解“${title}”`)
      if (questions.length >= 8) break
    }
    suggestedQuestions.value = questions
  } catch {
    suggestedQuestions.value = []
  }
}

async function loadResourceCounts() {
  const counts: ResourceCount = {
    article: 0,
    quiz: 0,
    code: 0,
    anime: 0,
    mindmap: 0,
    ppt: 0,
    video: 0,
    all: 0,
  }
  if (userStore.userId) {
    try {
      const res = await api.get('/resources', { params: { user_id: userStore.userId } })
      const items: Array<{ resource_type?: string }> = res.data.items || []
      for (const item of items) {
        const type = item.resource_type || ''
        counts.all += 1
        if (type in counts) counts[type as keyof ResourceCount] += 1
      }
    } catch { /* ignore */ }
  }
  resourceCounts.value = counts
}

async function loadProfile() {
  if (!userStore.userId) return
  try {
    const r = await api.get('/profile', { params: { user_id: userStore.userId } })
    profile.value = r.data.found ? r.data.profile : null
  } catch {
    profile.value = null
  }
}

async function refreshHome() {
  await Promise.all([loadProfile(), loadResourceCounts(), loadSuggestedQuestions()])
}

function handleSearchKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    goAgent()
  }
}

onMounted(async () => {
  await refreshHome()
  if (insightsRowRef.value) {
    insightsObserver = new IntersectionObserver((entries) => {
      if (entries.some(entry => entry.isIntersecting)) {
        insightsVisible.value = true
        insightsObserver?.disconnect()
        insightsObserver = null
      }
    }, { threshold: 0.2 })
    insightsObserver.observe(insightsRowRef.value)
  }
})

onBeforeUnmount(() => {
  if (insightsObserver) insightsObserver.disconnect()
})

watch(() => userStore.userId, refreshHome)
</script>

<template>
  <div class="home-page">
    <div class="home-shell">
      <section class="hero-section animate-up animate-delay-1">
        <div class="hero-eyebrow">智途 · 个性化学习智能体系统</div>
        <h1 class="hero-heading">今天想学点什么？</h1>
        <button class="hero-search animate-up animate-delay-2" type="button" @click="goAgent()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="7" stroke="#948A80" stroke-width="2"/><path d="M20 20l-3.5-3.5" stroke="#948A80" stroke-width="2" stroke-linecap="round"/></svg>
          <input v-model="homeQuery" class="hero-search-input" placeholder="输入知识点、问题或学习目标，回车即可和 AI 对话" @keydown="handleSearchKeydown" @click.stop />
        </button>
        <div v-if="suggestedQuestions.length > 0" class="hero-suggest">
          <div class="hero-suggest-track">
            <button v-for="(q, i) in suggestedQuestions" :key="'hs-' + i" class="hero-suggest-btn" @click="goAgent(q)">{{ q }}</button>
            <button v-for="(q, i) in suggestedQuestions" :key="'hs-dup-' + i" class="hero-suggest-btn" @click="goAgent(q)">{{ q }}</button>
          </div>
        </div>
      </section>

      <section class="onboarding-card animate-up animate-delay-3">
        <div class="section-head">
          <div>
            <div class="section-kicker">新手引导</div>
            <h2>先完成这 3 步，系统才会真正个性化</h2>
          </div>
          <button class="plain-link" @click="goPath('/profile', { onboarding: '1' })">重新建档</button>
        </div>
        <div class="guide-grid">
          <button v-for="step in guideSteps" :key="step.order" class="guide-step" :class="{ done: step.done }" @click="goPath(step.path, step.query)">
            <span class="guide-order">{{ step.done ? '✓' : step.order }}</span>
            <span class="guide-body">
              <strong>{{ step.title }}</strong>
              <em>{{ step.desc }}</em>
              <b>{{ step.done ? '已完成' : step.action }}</b>
            </span>
          </button>
        </div>
      </section>

      <section class="card-main animate-up animate-delay-3">
        <div class="card-main-section card-main-left">
          <div class="card-main-title">学习资源概览</div>
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
            <button class="qa-btn" @click="goAgent()"><span class="qa-dot red"></span><div><div class="qa-label">AI 智能助手</div><div class="qa-sub">答疑、解释、任务生成</div></div></button>
            <button class="qa-btn" @click="goPath('/profile')"><span class="qa-dot cyan"></span><div><div class="qa-label">学习画像</div><div class="qa-sub">画像建档与知识图谱</div></div></button>
            <button class="qa-btn" @click="goPath('/mistakes')"><span class="qa-dot yellow"></span><div><div class="qa-label">错题本</div><div class="qa-sub">错题复盘与补弱</div></div></button>
            <button class="qa-btn" @click="goPath('/resources')"><span class="qa-dot teal"></span><div><div class="qa-label">学习资源</div><div class="qa-sub">文章、题库、动画、PPT</div></div></button>
          </div>
        </div>
      </section>

      <section class="module-guide-card">
        <div class="section-head">
          <div>
            <div class="section-kicker">模块说明</div>
            <h2>每个模块是干什么的？</h2>
          </div>
        </div>
        <div class="module-grid">
          <button v-for="module in moduleGuides" :key="module.title" class="module-card" @click="goPath(module.path)">
            <strong>{{ module.title }}</strong>
            <span>{{ module.desc }}</span>
            <em>{{ module.action }} →</em>
          </button>
        </div>
      </section>

      <div ref="insightsRowRef" class="insights-row" :class="{ 'in-view': insightsVisible }">
        <div class="card-stats">
          <div class="card-stats-title">学习闭环概览</div>
          <div class="loop-grid">
            <button v-for="item in loopStats" :key="item.label" class="loop-card" @click="router.push({ path: item.path, query: item.query || {} })">
              <span class="loop-label">{{ item.label }}</span>
              <strong>{{ item.value }}<em>{{ item.unit }}</em></strong>
              <span class="loop-hint">{{ item.hint }}</span>
            </button>
          </div>
          <div class="loop-note">掌握度只会在提交题目后自动变化；资源学习和路径学习只记录学习行为。</div>
        </div>

        <div class="card-radar">
          <div class="card-radar-title">下一步建议</div>
          <div v-if="weakPointsPreview.length" class="weak-chip-list">
            <span v-for="point in weakPointsPreview" :key="point" class="weak-chip">{{ point }}</span>
          </div>
          <div v-else class="next-empty">暂无明确薄弱点。完成建档、微测验或题库后，这里会显示优先补强的知识点。</div>
          <div class="next-action-list">
            <button v-for="action in nextActions" :key="action.title" class="next-action" @click="goPath(action.path, action.query || {})">
              <strong>{{ action.title }}</strong>
              <span>{{ action.desc }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home-page {
  min-height: 100%;
  background: linear-gradient(180deg, #F9D9B8 0%, #FFF5EB 45%, #FFFBF5 100%);
  padding: 28px 20px 40px;
  box-sizing: border-box;
  margin: -28px -32px;
  width: calc(100% + 64px);
}

.home-shell {
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
}

.hero-section {
  padding-top: 34px;
  margin-bottom: 18px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.hero-eyebrow {
  color: #9A6A3F;
  font-size: 13px;
  margin-bottom: 8px;
}

.hero-heading {
  font-size: 36px;
  font-weight: 700;
  color: #3A332E;
  letter-spacing: -1px;
  line-height: 1.15;
  margin: 0 0 24px;
  text-align: center;
}

.hero-search {
  display: flex;
  align-items: center;
  gap: 10px;
  width: min(560px, 92%);
  padding: 10px 20px;
  background: #FFFBF5;
  border: 1.5px solid #EFE6DC;
  border-radius: 12px;
  color: #3A332E;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
  text-align: left;
}
.hero-search:hover {
  border-color: #E8C29C;
  box-shadow: 0 8px 24px rgba(58, 51, 46, 0.08);
}

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
.hero-suggest-btn {
  flex-shrink: 0;
  padding: 8px 20px;
  border: 1.5px solid #EFE6DC;
  border-radius: 22px;
  background: #FFFBF5;
  color: #7A6A5C;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}
.hero-suggest-btn:hover {
  border-color: #E8C29C;
  background: #FFF5EB;
  transform: translateY(-1px);
}

@keyframes scrollLtr {
  0% { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}

@keyframes floatUpIn {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-up { opacity: 0; animation: floatUpIn 0.55s cubic-bezier(0.2, 0.75, 0.22, 1) forwards; }
.animate-delay-1 { animation-delay: 0.08s; }
.animate-delay-2 { animation-delay: 0.16s; }
.animate-delay-3 { animation-delay: 0.24s; }

.onboarding-card,
.module-guide-card,
.card-main,
.card-stats,
.card-radar {
  background: #FFFBF5;
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(58, 51, 46, 0.08);
  border: 1px solid rgba(239, 230, 220, 0.8);
}

.onboarding-card,
.module-guide-card {
  padding: 24px;
  margin-bottom: 24px;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.section-head h2 {
  margin: 2px 0 0;
  font-size: 20px;
  color: #3A332E;
}
.section-kicker {
  color: #D9891B;
  font-size: 13px;
  font-weight: 700;
}
.plain-link {
  border: none;
  background: #FFF5EB;
  color: #9A6A3F;
  border-radius: 10px;
  padding: 8px 12px;
  cursor: pointer;
}

.guide-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
.guide-step {
  display: flex;
  gap: 12px;
  text-align: left;
  border: 1.5px solid #EFE6DC;
  border-radius: 14px;
  background: #FFFBF5;
  padding: 16px;
  cursor: pointer;
  transition: transform 0.2s, border-color 0.2s, background 0.2s;
}
.guide-step:hover {
  transform: translateY(-2px);
  border-color: #E8C29C;
  background: #FFF5EB;
}
.guide-step.done {
  border-color: rgba(82, 196, 26, 0.35);
  background: rgba(82, 196, 26, 0.06);
}
.guide-order {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: #F9D9B8;
  color: #3A332E;
  display: grid;
  place-items: center;
  font-weight: 700;
  flex-shrink: 0;
}
.guide-step.done .guide-order {
  background: #DFF3D8;
  color: #3A7A22;
}
.guide-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.guide-body strong { color: #3A332E; font-size: 15px; }
.guide-body em { color: #7A6A5C; font-size: 12px; line-height: 1.6; font-style: normal; }
.guide-body b { color: #D9891B; font-size: 12px; }

.card-main {
  display: flex;
  gap: 20px;
  padding: 24px;
  margin-bottom: 24px;
}
.card-main-left { flex: 1; }
.card-main-right { width: 320px; flex-shrink: 0; }
.card-main-title,
.card-stats-title,
.card-radar-title {
  font-size: 18px;
  font-weight: 700;
  color: #3A332E;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-main-title::before,
.card-stats-title::before,
.card-radar-title::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #F9D9B8;
}

.knowledge-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.k-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 124px;
  padding: 20px 10px;
  border: 1.5px solid #EFE6DC;
  border-radius: 14px;
  background: #FFFBF5;
  cursor: pointer;
  transition: all 0.2s;
}
.k-card:hover {
  border-color: var(--kc);
  background: #FFF5EB;
  transform: translateY(-2px);
}
.k-icon { font-size: 26px; }
.k-name { font-size: 14px; font-weight: 700; color: #3A332E; }
.k-count { font-size: 12px; color: #948A80; padding: 2px 8px; background: #FFF5EB; border-radius: 8px; }

.quick-actions { display: flex; flex-direction: column; gap: 10px; }
.qa-btn {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 68px;
  padding: 14px 16px;
  border: 1.5px solid #EFE6DC;
  border-radius: 14px;
  background: #FFFBF5;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}
.qa-btn:hover {
  border-color: #E8C29C;
  background: #FFF5EB;
}
.qa-dot { width: 36px; height: 36px; border-radius: 50%; flex-shrink: 0; }
.qa-dot.red { background: #E35749; }
.qa-dot.cyan { background: #49BBC8; }
.qa-dot.yellow { background: #F3B86B; }
.qa-dot.teal { background: #AECDD0; }
.qa-label { font-size: 14px; font-weight: 700; color: #3A332E; }
.qa-sub { font-size: 12px; color: #948A80; margin-top: 2px; }

.module-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.module-card {
  min-height: 132px;
  padding: 16px;
  border: 1.5px solid #EFE6DC;
  border-radius: 14px;
  background: linear-gradient(135deg, #FFFBF5, #FFF5EB);
  text-align: left;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: transform 0.2s, border-color 0.2s;
}
.module-card:hover {
  transform: translateY(-2px);
  border-color: #E8C29C;
}
.module-card strong { color: #3A332E; font-size: 15px; }
.module-card span { color: #7A6A5C; font-size: 12px; line-height: 1.6; flex: 1; }
.module-card em { color: #D9891B; font-size: 12px; font-style: normal; }

.insights-row {
  display: flex;
  gap: 24px;
  align-items: stretch;
  margin-bottom: 24px;
  opacity: 0;
  transform: translateY(14px);
  transition: opacity 0.55s cubic-bezier(0.2, 0.75, 0.22, 1), transform 0.55s cubic-bezier(0.2, 0.75, 0.22, 1);
}
.insights-row.in-view { opacity: 1; transform: translateY(0); }
.card-stats { flex: 1.2; padding: 28px; }
.card-radar { flex: 1; padding: 28px; }
.loop-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.loop-card {
  min-height: 96px;
  padding: 14px;
  border: 1.5px solid #EFE6DC;
  border-radius: 14px;
  background: linear-gradient(135deg, #FFFBF5, #FFF5EB);
  text-align: left;
  cursor: pointer;
}
.loop-label { display: block; color: #7A6A5C; font-size: 12px; margin-bottom: 8px; }
.loop-card strong { display: block; color: #3A332E; font-size: 28px; line-height: 1; }
.loop-card em { margin-left: 4px; color: #948A80; font-size: 12px; font-style: normal; }
.loop-hint { display: block; margin-top: 9px; color: #948A80; font-size: 12px; line-height: 1.45; }
.loop-note {
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(73, 187, 200, 0.09);
  color: #6B635C;
  font-size: 12px;
  line-height: 1.6;
}

.weak-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}
.weak-chip {
  max-width: 100%;
  padding: 6px 10px;
  border: 1px solid #F6D5A7;
  border-radius: 999px;
  background: #FFF8ED;
  color: #D9891B;
  font-size: 12px;
}
.next-empty {
  min-height: 48px;
  padding: 12px;
  border-radius: 12px;
  background: #FFF5EB;
  color: #948A80;
  font-size: 12px;
  line-height: 1.6;
  margin-bottom: 14px;
}
.next-action-list { display: flex; flex-direction: column; gap: 10px; }
.next-action {
  padding: 12px 14px;
  border: 1.5px solid #EFE6DC;
  border-radius: 12px;
  background: #FFFBF5;
  text-align: left;
  cursor: pointer;
}
.next-action:hover { border-color: #E8C29C; background: #FFF5EB; }
.next-action strong { display: block; color: #3A332E; font-size: 14px; margin-bottom: 4px; }
.next-action span { color: #948A80; font-size: 12px; line-height: 1.5; }

@media (max-width: 1024px) {
  .card-main,
  .insights-row { flex-direction: column; }
  .card-main-right { width: 100%; }
  .guide-grid,
  .module-grid { grid-template-columns: 1fr; }
}

@media (max-width: 640px) {
  .home-page { padding: 24px 16px 60px; margin: -28px -32px; width: calc(100% + 64px); }
  .hero-heading { font-size: 30px; }
  .knowledge-grid,
  .loop-grid { grid-template-columns: repeat(2, 1fr); }
  .hero-search { width: 92%; }
}
</style>
