<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { useUserStore } from '../stores/user'

const router = useRouter()
const userStore = useUserStore()

const homeQuery = ref('')
const insightsRowRef = ref<HTMLDivElement>()
const insightsVisible = ref(false)
let insightsObserver: IntersectionObserver | null = null

const profile = ref<any>(null)
const suggestedQuestions = ref<string[]>([])
const kColors = ['#f8d5a4', '#ee9b8f', '#95d7da']

const knowledgeAreas = ref([
  { name: '文章', type: 'article', icon: '📄', count: 0, color: kColors[0] },
  { name: '题库', type: 'quiz', icon: '❓', count: 0, color: kColors[1] },
  { name: '代码', type: 'code', icon: '💻', count: 0, color: kColors[2] },
  { name: '思维导图', type: 'mindmap', icon: '🧠', count: 0, color: kColors[0] },
  { name: 'PPT课件', type: 'ppt', icon: '📊', count: 0, color: kColors[1] },
  { name: '全部资源', type: '', icon: '📦', count: 0, color: kColors[2] },
])

const defaultCounts = { article: 0, quiz: 0, code: 0, mindmap: 0, ppt: 0, all: 0 }

async function goAgent(query?: string) {
  const q = (query ?? homeQuery.value).trim()
  await router.push({
    path: '/agent',
    query: q ? { from: 'home', t: String(Date.now()), q, auto_submit: '1' } : {},
  })
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

async function loadKnowledgeAreaCounts() {
  const userId = userStore.userId
  const counts = { ...defaultCounts }
  if (userId) {
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
    } catch { /* ignore */ }
  }
  knowledgeAreas.value = [
    { name: '文章', type: 'article', icon: '📄', count: counts.article, color: kColors[0] },
    { name: '题库', type: 'quiz', icon: '❓', count: counts.quiz, color: kColors[1] },
    { name: '代码', type: 'code', icon: '💻', count: counts.code, color: kColors[2] },
    { name: '思维导图', type: 'mindmap', icon: '🧠', count: counts.mindmap, color: kColors[0] },
    { name: 'PPT课件', type: 'ppt', icon: '📊', count: counts.ppt, color: kColors[1] },
    { name: '全部资源', type: '', icon: '📦', count: counts.all, color: kColors[2] },
  ]
}

function openResourcesByType(type: string) {
  router.push({ path: '/resources', query: type ? { type } : {} })
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

const totalResourceCount = computed(() => knowledgeAreas.value.find(area => area.type === '')?.count || 0)
const quizResourceCount = computed(() => knowledgeAreas.value.find(area => area.type === 'quiz')?.count || 0)
const articleResourceCount = computed(() => knowledgeAreas.value.find(area => area.type === 'article')?.count || 0)
const knowledgeBase = computed<Record<string, number>>(() => profile.value?.knowledge_base || {})
const measuredKnowledgeCount = computed(() => Object.keys(knowledgeBase.value).length)
const masteredKnowledgeCount = computed(() => Object.values(knowledgeBase.value).filter(score => Number(score || 0) >= 0.8).length)
const weakPoints = computed<string[]>(() => (profile.value?.weak_points || []).filter(Boolean))
const weakPointsPreview = computed(() => weakPoints.value.slice(0, 8))

const loopStats = computed(() => [
  { label: '学习资源', value: totalResourceCount.value, unit: '个', hint: '文章、题库、导图、课件等资源总量', path: '/resources' },
  { label: '题库资源', value: quizResourceCount.value, unit: '套', hint: '掌握度只由题目提交自动更新', path: '/resources', query: { type: 'quiz' } },
  { label: '已测知识点', value: measuredKnowledgeCount.value, unit: '个', hint: `已掌握 ${masteredKnowledgeCount.value} 个`, path: '/profile' },
  { label: '薄弱知识点', value: weakPoints.value.length, unit: '个', hint: '来自错题和微测验诊断', path: '/profile' },
])

const nextActions = computed(() => [
  {
    title: weakPoints.value.length ? '优先处理薄弱知识点' : '先完成一次诊断测验',
    desc: weakPoints.value.length ? `当前有 ${weakPoints.value.length} 个薄弱知识点，建议生成专项练习。` : '画像中的薄弱点还不充分，建议先做微测验或题库。',
    path: weakPoints.value.length ? '/resources' : '/profile',
  },
  {
    title: quizResourceCount.value ? '继续做题更新掌握度' : '先生成题库资源',
    desc: quizResourceCount.value ? '提交题目后会直接刷新画像和知识图谱掌握度。' : '题库较少，建议从课程或知识点生成专项题库。',
    path: '/resources',
    query: quizResourceCount.value ? { type: 'quiz' } : {},
  },
  {
    title: articleResourceCount.value ? '从资源进入复习闭环' : '补齐讲解资源',
    desc: articleResourceCount.value ? '可从文章生成测试题，形成“学—测—更新掌握度”闭环。' : '文章资源较少，建议先生成课程总览或知识点讲解。',
    path: '/resources',
    query: articleResourceCount.value ? { type: 'article' } : {},
  },
])

onMounted(async () => {
  await Promise.all([loadProfile(), loadKnowledgeAreaCounts(), loadSuggestedQuestions()])
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

watch(() => userStore.userId, async () => {
  await Promise.all([loadProfile(), loadKnowledgeAreaCounts(), loadSuggestedQuestions()])
})

function handleSearchKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    goAgent()
  }
}
</script>

<template>
  <div class="canva-page">
    <div class="canva-bg">
      <div class="hero-section animate-up animate-delay-1">
        <div class="hero-heading">今天想学点什么？</div>
        <button class="hero-search animate-up animate-delay-2" type="button" @click="goAgent()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="7" stroke="#948A80" stroke-width="2"/><path d="M20 20l-3.5-3.5" stroke="#948A80" stroke-width="2" stroke-linecap="round"/></svg>
          <input v-model="homeQuery" class="hero-search-input" placeholder="查找你需要的知识点，回车即可和 AI 对话" @keydown="handleSearchKeydown" @click.stop />
        </button>
        <div v-if="suggestedQuestions.length > 0" class="hero-suggest">
          <div class="hero-suggest-track">
            <button v-for="(q, i) in suggestedQuestions" :key="'hs-' + i" class="hero-suggest-btn" @click="goAgent(q)">{{ q }}</button>
            <button v-for="(q, i) in suggestedQuestions" :key="'hs-dup-' + i" class="hero-suggest-btn" @click="goAgent(q)">{{ q }}</button>
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
            <button class="qa-btn" @click="goAgent()"><span class="qa-dot" style="background:#E35749"></span><div><div class="qa-label">AI 智能助手</div><div class="qa-sub">智能问答助手</div></div></button>
            <button class="qa-btn" @click="router.push('/profile')"><span class="qa-dot" style="background:#49BBC8"></span><div><div class="qa-label">学习画像</div><div class="qa-sub">个性化诊断</div></div></button>
            <button class="qa-btn" @click="router.push('/mistakes')"><span class="qa-dot" style="background:#F3B86B"></span><div><div class="qa-label">错题本</div><div class="qa-sub">查漏补缺提升</div></div></button>
            <button class="qa-btn" @click="router.push('/resources')"><span class="qa-dot" style="background:#AECDD0"></span><div><div class="qa-label">学习资源</div><div class="qa-sub">丰富学习材料</div></div></button>
          </div>
        </div>
      </div>

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
          <div class="loop-note">掌握度只会在提交题目后自动变化，资源学习和路径学习只记录学习行为。</div>
        </div>

        <div class="card-radar clickable-card" @click="router.push('/profile')">
          <div class="card-radar-title">下一步建议</div>
          <div v-if="weakPointsPreview.length" class="weak-chip-list">
            <span v-for="point in weakPointsPreview" :key="point" class="weak-chip">{{ point }}</span>
          </div>
          <div v-else class="next-empty">暂无明确薄弱点。完成微测验或题库后，这里会显示优先补强的知识点。</div>
          <div class="next-action-list">
            <button v-for="action in nextActions" :key="action.title" class="next-action" @click.stop="router.push({ path: action.path, query: action.query || {} })">
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
  transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
}
.loop-card:hover {
  transform: translateY(-2px);
  border-color: #E8C29C;
  box-shadow: 0 6px 18px rgba(58, 51, 46, 0.08);
}
.loop-label {
  display: block;
  color: #7A6A5C;
  font-size: 12px;
  margin-bottom: 8px;
}
.loop-card strong {
  display: block;
  color: #3A332E;
  font-size: 28px;
  line-height: 1;
}
.loop-card em {
  margin-left: 4px;
  color: #948A80;
  font-size: 12px;
  font-style: normal;
  font-weight: 500;
}
.loop-hint {
  display: block;
  margin-top: 9px;
  color: #948A80;
  font-size: 12px;
  line-height: 1.45;
}
.loop-note {
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(73, 187, 200, 0.09);
  color: #6B635C;
  font-size: 12px;
  line-height: 1.6;
}

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
  cursor: default;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
.next-action-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.next-action {
  padding: 12px 14px;
  border: 1.5px solid #EFE6DC;
  border-radius: 12px;
  background: #FFFBF5;
  text-align: left;
  cursor: pointer;
  transition: transform 0.2s, border-color 0.2s, background 0.2s;
}
.next-action:hover {
  transform: translateY(-1px);
  border-color: #E8C29C;
  background: #FFF5EB;
}
.next-action strong {
  display: block;
  color: #3A332E;
  font-size: 14px;
  margin-bottom: 4px;
}
.next-action span {
  color: #948A80;
  font-size: 12px;
  line-height: 1.5;
}

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
  .hero-search { width: 90%; }
}
</style>
