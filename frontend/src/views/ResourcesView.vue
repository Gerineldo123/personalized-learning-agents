<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import { useUserStore } from '../stores/user'
import { useEventStore } from '../stores/event'
import MindMapViewer from '../components/resource/MindMapViewer.vue'
import QuizCard from '../components/resource/QuizCard.vue'
import PptViewer from '../components/resource/PptViewer.vue'
import { ElMessage } from 'element-plus'
import { renderMarkdownEnhanced as renderMdCommon, codeBlockStore } from '../utils/markdown'
import SausageIcon from '../components/SausageIcon.vue'
import LoadingSausage from '../components/LoadingSausage.vue'

const userStore = useUserStore()
const eventStore = useEventStore()
const route = useRoute()

const resources = ref<any[]>([])
const totalResources = ref(0)
const page = ref(1)
const pageSize = ref(12)
const profile = ref<any>(null)
const recommendedSeeds = ref<any[]>([])
const weakPoints = ref<string[]>([])
const typeFilter = ref('')
const loading = ref(false)
const selected = ref<any>(null)
const showGenDialog = ref(false)
const genTopic = ref('')
const genTypes = ref<string[]>(['article'])
const genQuestionCount = ref(5)
const genDifficulty = ref('中等')
const genQuestionTypes = ref<string[]>(['single_choice'])
const genCodeLanguage = ref('python')
const genLoading = ref(false)
const starterLoading = ref(false)
const orchestrateLoading = ref(false)
const recommendItems = ref<any[]>([])
const manageMode = ref(false)
const selectedIds = ref<number[]>([])

function markdownSource(content: any): string {
  if (typeof content === 'string') return content
  if (content && typeof content === 'object') {
    if (typeof content.text === 'string') return content.text
    if (typeof content.markdown === 'string') return content.markdown
    if (typeof content.code === 'string') {
      const lang = content.language || 'python'
      return '```' + lang + '\n' + content.code + '\n```'
    }
  }
  return JSON.stringify(content, null, 2)
}

function renderMarkdown(content: any): string {
  return renderMdCommon(markdownSource(content))
}

function handleDetailClick(e: MouseEvent) {
  const copyBtn = (e.target as HTMLElement).closest('.code-copy-btn') as HTMLElement | null
  if (copyBtn) {
    const id = copyBtn.dataset.codeId
    if (id && codeBlockStore[id]) {
      navigator.clipboard.writeText(codeBlockStore[id]).then(() => {
        copyBtn.textContent = '已复制'
        setTimeout(() => { copyBtn.textContent = '复制' }, 1500)
      }).catch(() => {})
    }
  }
}

const resourceTypes = ['', 'article', 'quiz', 'code', 'mindmap', 'ppt', 'video', 'evaluation']
const genTypeOptions = [
  { value: 'article', label: '文章' },
  { value: 'quiz', label: '题库' },
  { value: 'code', label: '代码' },
  { value: 'mindmap', label: '思维导图' },
  { value: 'ppt', label: 'PPT课件' },
  { value: 'video', label: '视频推荐' },
  { value: 'evaluation', label: '学习评估' },
]
const difficultyOptions = ['简单', '中等', '较难', '挑战']
const codeLangOptions = [
  { value: 'python', label: 'Python' },
  { value: 'cpp', label: 'C++' },
  { value: 'java', label: 'Java' },
  { value: 'javascript', label: 'JavaScript' },
  { value: 'c', label: 'C' },
]

onMounted(() => {
  if (route.query.type) typeFilter.value = route.query.type as string
  if (userStore.userId) { loadResources(); loadRecommend() }
  eventStore.connect(userStore.userId || 'user_default')
  loadProfileAndSeeds()
})

watch(() => eventStore.lastEvent, (evt) => {
  if (evt?.event === 'resource.created') loadResources()
})

watch(() => userStore.userId, (newId) => {
  if (newId) { loadResources(); loadProfileAndSeeds(); loadRecommend() }
})

watch(() => route.query.type, (newType) => {
  typeFilter.value = (newType as string) || ''
  page.value = 1
  loadResources()
})

async function loadProfileAndSeeds() {
  if (!userStore.userId) return
  try {
    const r = await api.get('/profile', { params: { user_id: userStore.userId } })
    profile.value = r.data?.found ? r.data.profile : null
    const weak = profile.value?.weak_courses || []
    recommendedSeeds.value = weak.slice(0, 6).map((c: any) => ({
      course: c.name || '未命名课程',
      topic: c.knowledge_points || c.name || '核心概念',
      goal: c.goal || '扎实基础',
    }))
    weakPoints.value = profile.value?.weak_points || []
  } catch {
    profile.value = null
    recommendedSeeds.value = []
    weakPoints.value = []
  }
}

async function loadResources() {
  if (!userStore.userId) return
  loading.value = true
  try {
    const offset = (page.value - 1) * pageSize.value
    const params: any = { user_id: userStore.userId, limit: pageSize.value, offset }
    if (typeFilter.value) params.resource_type = typeFilter.value
    const r = await api.get('/resources', { params })
    resources.value = r.data.items || []
    totalResources.value = r.data.total || 0

    const openId = Number(route.query.open || 0)
    if (openId > 0) {
      const target = resources.value.find((x: any) => x.id === openId)
      if (target) selected.value = target
    }
  } catch { resources.value = [] }
  finally { loading.value = false }
}

function onPageChange(p: number) {
  page.value = p
  loadResources()
}

async function startGenerate() {
  if (!genTopic.value.trim()) { ElMessage.warning('请输入主题'); return }
  if (genTypes.value.length === 0) { ElMessage.warning('请选择类型'); return }
  genLoading.value = true
  try {
    await api.post('/resources/generate', null, {
      params: {
        user_id: userStore.userId,
        topic: genTopic.value.trim(),
        resource_types: genTypes.value.join(','),
        question_count: genQuestionCount.value,
        difficulty: genDifficulty.value,
        question_types: genQuestionTypes.value.join(','),
        code_language: genCodeLanguage.value,
      }
    })
    ElMessage.success('资源生成完成')
    showGenDialog.value = false
    genTopic.value = ''
    genTypes.value = ['article']
    genQuestionCount.value = 5
    genDifficulty.value = '中等'
    genQuestionTypes.value = ['single_choice']
    genCodeLanguage.value = 'python'
    page.value = 1
    loadResources()
  } catch { ElMessage.error('生成失败') }
  finally { genLoading.value = false }
}

async function generateQuick(seed: any, type: 'article' | 'quiz') {
  try {
    await api.post('/resources/generate', null, {
      params: {
        user_id: userStore.userId,
        topic: `${seed.course}：${seed.topic}`,
        resource_types: type,
      },
    })
    ElMessage.success(`已生成${type === 'article' ? '文章' : '题库'}：${seed.course}`)
    page.value = 1
    loadResources()
  } catch {
    ElMessage.error('快速生成失败')
  }
}

async function generateStarterPack() {
  starterLoading.value = true
  try {
    const r = await api.post('/resources/generate/starter', null, {
      params: { user_id: userStore.userId, max_courses: 3 },
      timeout: 180000,
    })
    ElMessage.success(`已生成 ${r.data.generated || 0} 个资源`)
    page.value = 1
    await loadResources()
  } catch {
    ElMessage.error('入门资源包生成失败')
  } finally {
    starterLoading.value = false
  }
}

async function generateOrchestrated(topic: string) {
  orchestrateLoading.value = true
  try {
    await api.post('/resources/generate/orchestrate', null, {
      params: { user_id: userStore.userId, topic },
      timeout: 300000,
    })
    ElMessage.success('多智能体协同生成完成（文章+思维导图+题库+视频）')
    page.value = 1
    await loadResources()
  } catch {
    ElMessage.error('协同生成失败')
  } finally {
    orchestrateLoading.value = false
  }
}

async function loadRecommend() {
  if (!userStore.userId) return
  try {
    const r = await api.get('/resources/recommend', { params: { user_id: userStore.userId, top_k: 8 } })
    recommendItems.value = r.data.items || []
  } catch {
    recommendItems.value = []
  }
}

function viewResource(r: any) {
  if (manageMode.value) { toggleSelect(r.id); return }
  selected.value = r
}

function toggleManageMode() {
  manageMode.value = !manageMode.value
  if (!manageMode.value) selectedIds.value = []
}

function toggleSelect(id: number) {
  if (!manageMode.value) return
  if (selectedIds.value.includes(id)) {
    selectedIds.value = selectedIds.value.filter((x) => x !== id)
  } else {
    selectedIds.value.push(id)
  }
}

async function batchPin(pinned: 0 | 1) {
  if (selectedIds.value.length === 0) { ElMessage.warning('请先选择资源'); return }
  try {
    await api.post('/resources/batch_pin', null, {
      params: { user_id: userStore.userId, ids: selectedIds.value.join(','), pinned },
    })
    ElMessage.success(pinned ? '已批量置顶' : '已取消置顶')
    await loadResources()
  } catch { ElMessage.error('操作失败') }
}

async function batchDelete() {
  if (selectedIds.value.length === 0) { ElMessage.warning('请先选择资源'); return }
  try {
    await api.post('/resources/batch_delete', null, {
      params: { user_id: userStore.userId, ids: selectedIds.value.join(',') },
    })
    ElMessage.success('已批量删除')
    selectedIds.value = []
    await loadResources()
  } catch { ElMessage.error('删除失败') }
}

function typeLabel(t: string) {
  const map: Record<string, string> = { article: '文章', quiz: '题库', code: '代码', mindmap: '思维导图', ppt: '课件', video: '视频', evaluation: '评估' }
  return map[t] || t
}

function typeTag(t: string) {
  const map: Record<string, string> = { article: '', quiz: 'warning', code: 'success', mindmap: 'info', ppt: 'danger', video: '', evaluation: 'info' }
  return map[t] || ''
}

function bvidFromUrl(url: string): string {
  if (!url) return ''
  const bv = url.match(/\/video\/(BV\w+)/)
  return bv ? bv[1] : ''
}

function avidFromUrl(url: string): string {
  if (!url) return ''
  const av = url.match(/\/video\/av(\d+)/)
  return av ? av[1] : ''
}
</script>

<template>
  <div class="resources-view">
    <div class="toolbar animate-up animate-delay-1">
      <el-select v-model="typeFilter" placeholder="全部类型" @change="page = 1; loadResources()" style="width: 160px">
        <el-option v-for="t in resourceTypes" :key="t" :label="t || '全部'" :value="t" />
      </el-select>
      <el-button @click="loadResources" style="margin-left: 8px">刷新</el-button>
      <el-button style="margin-left: 8px" @click="toggleManageMode">{{ manageMode ? '完成管理' : '管理资源' }}</el-button>
      <el-button v-if="manageMode" style="margin-left: 8px" @click="batchPin(1)">批量置顶</el-button>
      <el-button v-if="manageMode" style="margin-left: 8px" @click="batchPin(0)">取消置顶</el-button>
      <el-button v-if="manageMode" style="margin-left: 8px" type="danger" @click="batchDelete">批量删除</el-button>
      <el-button type="primary" @click="showGenDialog = true" style="margin-left: auto">+ 手动生成</el-button>
    </div>

    <!-- 为你推荐区 -->
    <div v-if="recommendItems.length > 0 && !selected" class="recommend-banner animate-up animate-delay-2">
      <div class="recommend-head">
        <span class="recommend-title">为你推荐</span>
        <span class="recommend-hint">基于画像智能匹配</span>
        <el-button size="small" text @click="loadRecommend" style="margin-left:auto">刷新</el-button>
      </div>
      <div class="recommend-list">
        <div v-for="r in recommendItems" :key="r.id" class="recommend-item" @click="selected = r">
          <el-tag :type="typeTag(r.resource_type)" size="small">{{ typeLabel(r.resource_type) }}</el-tag>
          <span class="recommend-item-title">{{ r.title }}</span>
        </div>
      </div>
    </div>

    <!-- 薄弱知识点专项推荐 -->
    <div v-if="weakPoints.length > 0 && !selected" class="weak-banner animate-up animate-delay-2">
      <div class="weak-banner-head">
        <span class="weak-banner-title">薄弱知识点专项推荐</span>
        <span class="weak-banner-hint">基于你的学习画像和答题记录自动生成</span>
      </div>
      <div class="weak-tags">
        <el-tag
          v-for="pt in weakPoints.slice(0, 8)"
          :key="pt"
          type="warning"
          size="small"
          class="weak-tag"
          @click="generateQuick({ course: pt, topic: pt }, 'article')"
        >{{ pt }} → 生成讲解</el-tag>
        <el-tag
          v-for="pt in weakPoints.slice(0, 4)"
          :key="'q_' + pt"
          type="danger"
          size="small"
          class="weak-tag"
          @click="generateQuick({ course: pt, topic: pt }, 'quiz')"
        >{{ pt }} → 生成题库</el-tag>
      </div>
    </div>

    <div v-if="(!loading && resources.length === 0)" class="starter-panel animate-up animate-delay-2">
      <div class="starter-head">
        <h3>根据你的学习画像推荐</h3>
        <div style="display:flex;gap:8px">
          <el-button type="success" :loading="starterLoading" @click="generateStarterPack">
            一键生成入门资源包
          </el-button>
        </div>
      </div>
      <p class="starter-desc">系统会优先根据你的薄弱课程，自动生成「文章 + 题库」组合资源，帮助你快速开始学习。</p>

      <div v-if="recommendedSeeds.length > 0" class="seed-grid">
        <div v-for="s in recommendedSeeds" :key="s.course + s.topic" class="seed-card">
          <div class="seed-title">{{ s.course }}</div>
          <div class="seed-topic">{{ s.topic }}</div>
          <div class="seed-actions">
            <el-button size="small" @click="generateQuick(s, 'article')">生成文章</el-button>
            <el-button size="small" type="warning" @click="generateQuick(s, 'quiz')">生成题库</el-button>
            <el-button size="small" type="primary" :loading="orchestrateLoading" @click="generateOrchestrated(`${s.course}：${s.topic}`)">协同生成</el-button>
          </div>
        </div>
      </div>

      <div v-else class="sa-empty">
        <SausageIcon :size="64" animate />
        <p class="sa-empty-text">尚未检测到可推荐的薄弱课程<br/>可先去学习画像完成问卷</p>
      </div>
    </div>

    <div v-if="loading" class="loading-box"><LoadingSausage text="加载资源..." /></div>

    <div v-else-if="selected" class="detail-view animate-up animate-delay-2">
      <el-button @click="selected = null" style="margin-bottom: 16px">返回列表</el-button>
      <QuizCard v-if="selected.resource_type === 'quiz'" :content="selected.content" :resourceId="selected.id" :userId="userStore.userId" />
      <MindMapViewer v-else-if="selected.resource_type === 'mindmap'" :markdown="selected.content?.markdown || ''" />
      <PptViewer v-else-if="selected.resource_type === 'ppt'" :content="selected.content" />
      <div v-else-if="selected.resource_type === 'video'" class="video-viewer">
        <div v-if="bvidFromUrl(selected.content?.url) || avidFromUrl(selected.content?.url)" class="video-embed-wrap">
          <iframe
            :src="bvidFromUrl(selected.content?.url)
              ? `//player.bilibili.com/player.html?bvid=${bvidFromUrl(selected.content?.url)}&autoplay=0&danmaku=0`
              : `//player.bilibili.com/player.html?aid=${avidFromUrl(selected.content?.url)}&autoplay=0&danmaku=0`"
            scrolling="no" border="0" frameborder="no" framespacing="0" allowfullscreen="true"
            class="bili-iframe"
          />
        </div>
        <div v-else class="video-fallback">
          <p>{{ selected.content?.reason }}</p>
          <a :href="selected.content?.url" target="_blank" rel="noopener">在 B 站打开</a>
        </div>
        <div class="video-meta">
          <span class="video-source">{{ selected.content?.source }}</span>
          <p class="video-reason">{{ selected.content?.reason }}</p>
        </div>
      </div>
      <div v-else class="text-content markdown-body" v-html="renderMarkdown(selected.content)" @click="handleDetailClick"></div>
    </div>

    <div v-else-if="resources.length > 0" class="resource-list animate-up animate-delay-2">
      <div v-for="r in resources" :key="r.id" class="resource-card animate-up" @click="viewResource(r)">
        <div class="card-header">
          <el-checkbox
            v-if="manageMode"
            :model-value="selectedIds.includes(r.id)"
            @change="() => toggleSelect(r.id)"
            @click.stop
          />
          <el-tag v-if="r.pinned" type="danger" size="small">置顶</el-tag>
          <el-tag :type="typeTag(r.resource_type)" size="small">{{ typeLabel(r.resource_type) }}</el-tag>
          <span class="card-date">{{ r.created_at?.slice(0, 10) }}</span>
        </div>
        <h4 class="card-title">{{ r.title }}</h4>
        <div class="card-deco"><SausageIcon :size="20" muted /></div>
      </div>
    </div>

    <div v-else class="empty-box animate-up animate-delay-2">
      <div class="sa-empty">
        <SausageIcon :size="72" animate />
        <p class="sa-empty-text">还没有学习资源<br/>尝试生成或刷新看看吧</p>
      </div>
    </div>

    <div v-if="!selected && !loading && totalResources > pageSize" class="pagination-box animate-up animate-delay-3">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="totalResources"
        layout="prev, pager, next, total"
        @current-change="onPageChange"
      />
    </div>

    <el-dialog v-model="showGenDialog" title="生成学习资源" width="480px">
      <el-form label-width="80px">
        <el-form-item label="主题">
          <el-input v-model="genTopic" placeholder="例如：排序算法" />
        </el-form-item>
        <el-form-item label="资源类型">
          <el-checkbox-group v-model="genTypes">
            <el-checkbox v-for="o in genTypeOptions" :key="o.value" :value="o.value">{{ o.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item v-if="genTypes.includes('code') || genTypes.includes('quiz')" label="编程语言">
          <el-select v-model="genCodeLanguage" placeholder="选择语言" style="width: 160px">
            <el-option v-for="l in codeLangOptions" :key="l.value" :label="l.label" :value="l.value" />
          </el-select>
        </el-form-item>
        <template v-if="genTypes.includes('quiz')">
          <el-form-item label="题目数量">
            <el-input-number v-model="genQuestionCount" :min="3" :max="30" :step="1" />
            <span style="margin-left:8px;color:#948A80;font-size:12px">建议 5~15 题</span>
          </el-form-item>
          <el-form-item label="题库难度">
            <el-radio-group v-model="genDifficulty">
              <el-radio v-for="d in difficultyOptions" :key="d" :value="d">{{ d }}</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="题目类型">
            <el-checkbox-group v-model="genQuestionTypes">
              <el-checkbox value="single_choice">选择题</el-checkbox>
              <el-checkbox value="fill_blank">填空题</el-checkbox>
              <el-checkbox value="coding">编程题</el-checkbox>
            </el-checkbox-group>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showGenDialog = false">取消</el-button>
        <el-button type="success" :loading="orchestrateLoading" @click="() => { if (!genTopic.trim()) { ElMessage.warning('请输入主题'); return } showGenDialog = false; generateOrchestrated(genTopic.trim()) }">多智能体协同生成</el-button>
        <el-button type="primary" :loading="genLoading" @click="startGenerate">生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.resources-view { max-width: 1280px; padding: 28px 20px 34px; margin: 0 auto; box-sizing: border-box; background: linear-gradient(180deg, #F9D9B8 0%, #FFF5EB 45%, #FFFBF5 100%); }
.toolbar { display: flex; align-items: center; margin-bottom: 20px; padding-top: 4px; flex-wrap: wrap; gap: 4px; }
.loading-box { height: 200px; }

.starter-panel {
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 12px;
  padding: 18px;
  margin-bottom: 20px;
}
.starter-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.starter-head h3 { margin: 0; color: #3A332E; font-size: 20px; font-weight: 500; }
.starter-desc { margin: 0 0 14px; color: #6B635C; font-size: 13px; line-height: 1.7; }

.seed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.seed-card {
  background: #FFFBF5;
  border: 1.5px solid #EFE6DC;
  border-radius: 12px;
  padding: 12px;
}
.seed-title { font-weight: 500; color: #3A332E; margin-bottom: 4px; }
.seed-topic { color: #6B635C; font-size: 13px; min-height: 40px; line-height: 1.5; }
.seed-actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }

.weak-banner {
  background: rgba(253, 246, 236, 0.9);
  border: 1px solid rgba(235, 177, 95, 0.4);
  border-radius: 12px;
  padding: 14px 18px;
  margin-bottom: 18px;
}
.weak-banner-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.weak-banner-title { font-weight: 500; color: #DBA878; font-size: 14px; }
.weak-banner-hint { font-size: 12px; color: #948A80; }
.weak-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.weak-tag { cursor: pointer; }
.weak-tag:hover { opacity: 0.85; transform: scale(1.03); }

.recommend-banner {
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 12px;
  padding: 12px 16px;
  margin-bottom: 18px;
}
.recommend-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.recommend-title { font-weight: 500; color: #3A332E; font-size: 14px; }
.recommend-hint { font-size: 12px; color: #948A80; }
.recommend-list { display: flex; flex-wrap: wrap; gap: 8px; }
.recommend-item {
  display: flex; align-items: center; gap: 6px;
  background: #FFF5EB; border: 1px solid #EFE6DC;
  border-radius: 8px; padding: 4px 10px;
  cursor: pointer; font-size: 13px; transition: all 0.2s;
}
.recommend-item:hover { border-color: #E8C29C; box-shadow: 0 2px 8px rgba(58,51,46,0.08); }
.recommend-item-title { color: #3A332E; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.resource-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }

.resource-card {
  display: flex; flex-direction: column; gap: 8px;
  min-height: 83px;
  padding: 14px 14px;
  border: 1.5px solid #EFE6DC;
  border-radius: 12px;
  background: #FFFBF5;
  cursor: pointer;
  transition: all 0.2s;
}
.resource-card:hover {
  border-color: #E8C29C;
  background: linear-gradient(135deg, #FFFBF5, color-mix(in srgb, #E8C29C 8%, #FFFBF5));
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(58,51,46,0.08);
}

.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-date { font-size: 11px; color: #948A80; }
.card-title { margin: 0; color: #3A332E; font-size: 14px; font-weight: 500; line-height: 1.5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.pagination-box { display: flex; justify-content: center; margin-top: 24px; }

.text-content {
  background: #FFF5EB;
  color: #3A332E;
  border-radius: 4px 12px 12px 12px;
  border: 1px solid #EFE6DC;
  padding: 12px 16px;
  line-height: 1.6;
  word-break: break-word;
  font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 14px;
  font-weight: normal;
}
.text-content :deep(h1),
.text-content :deep(h2),
.text-content :deep(h3) { margin: 12px 0 8px; font-weight: normal; color: #3A332E; font-family: inherit; font-size: inherit; }
.text-content :deep(p) { margin: 10px 0; color: #3A332E; font-family: inherit; }
.text-content :deep(ul),
.text-content :deep(ol) { padding-left: 20px; margin: 10px 0; color: #3A332E; font-family: inherit; }
.text-content :deep(li) { margin: 6px 0; line-height: 1.7; color: #3A332E; font-family: inherit; }
.text-content :deep(code) { background: #f5ebdf; padding: 2px 6px; border-radius: 3px; font-size: inherit; font-family: inherit; color: #3A332E; }
.text-content :deep(strong),
.text-content :deep(em),
.text-content :deep(small),
.text-content :deep(td),
.text-content :deep(th) { color: #3A332E; font-family: inherit; font-weight: normal; }
.text-content :deep(pre) { background: #2f3541; color: #f0f4f9; padding: 14px 18px; border-radius: 0 0 6px 6px; overflow-x: auto; margin: 0; }
.text-content :deep(pre code) { background: none; padding: 0; color: inherit; font-size: 13px; white-space: pre; tab-size: 4; -moz-tab-size: 4; }
.text-content :deep(.code-block-wrapper) { margin: 12px 0; border-radius: 6px; overflow: hidden; }
.text-content :deep(.code-header) { display: flex; justify-content: space-between; align-items: center; background: #21252b; padding: 6px 14px; border-radius: 6px 6px 0 0; }
.text-content :deep(.code-lang) { font-size: 11px; color: #3A332E; text-transform: uppercase; }
.text-content :deep(.code-copy-btn) { font-size: 11px; color: #3A332E; cursor: pointer; padding: 2px 8px; border-radius: 3px; transition: all 0.15s; user-select: none; }
.text-content :deep(.code-copy-btn:hover) { color: #fff; background: rgba(255,255,255,0.1); }
.text-content :deep(blockquote) { border-left: 3px solid #e35749; padding: 4px 12px; margin: 8px 0; color: #3A332E; background: rgba(227,87,73,0.08); }
.text-content :deep(table) { border-collapse: collapse; margin: 8px 0; width: 100%; }
.text-content :deep(th),
.text-content :deep(td) { border: 1px solid #EFE6DC; padding: 6px 10px; text-align: left; }
.text-content :deep(th) { background: #FFF5EB; font-weight: 600; }
.text-content :deep(strong) { font-weight: 700; }
.text-content :deep(a) { color: #3A332E; text-decoration: none; }
.text-content :deep(a:hover) { text-decoration: underline; }
.text-content :deep(.math-block) { display: block; text-align: center; margin: 14px 0; overflow-x: auto; }
.text-content :deep(.math-inline) { padding: 0 2px; }

.video-viewer {
  background: #FFFBF5;
  border-radius: 12px;
  border: 1px solid #EFE6DC;
  overflow: hidden;
}
.video-embed-wrap { position: relative; width: 100%; padding-top: 56.25%; background: #000; }
.bili-iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none; }
.video-fallback { padding: 32px; text-align: center; }
.video-fallback a { color: #DBA878; text-decoration: none; font-size: 15px; }
.video-meta { padding: 14px 18px; }
.video-source { font-size: 12px; color: #948A80; }
.video-reason { margin: 6px 0 0; color: #3A332E; font-size: 14px; line-height: 1.6; }

@keyframes floatUpIn {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-up {
  opacity: 0;
  animation: floatUpIn 0.55s cubic-bezier(0.2, 0.75, 0.22, 1) forwards;
}
.animate-delay-1 { animation-delay: 0.08s; }
.animate-delay-2 { animation-delay: 0.16s; }
.animate-delay-3 { animation-delay: 0.28s; }
.animate-delay-4 { animation-delay: 0.40s; }

.resource-card.animate-up { animation-duration: 0.4s; }
.resource-card:nth-child(1) { animation-delay: 0.10s; }
.resource-card:nth-child(2) { animation-delay: 0.14s; }
.resource-card:nth-child(3) { animation-delay: 0.18s; }
.resource-card:nth-child(4) { animation-delay: 0.22s; }
.resource-card:nth-child(5) { animation-delay: 0.26s; }
.resource-card:nth-child(6) { animation-delay: 0.30s; }
.resource-card:nth-child(7) { animation-delay: 0.34s; }
.resource-card:nth-child(8) { animation-delay: 0.38s; }
.resource-card:nth-child(9) { animation-delay: 0.42s; }
.resource-card:nth-child(10) { animation-delay: 0.46s; }
.resource-card:nth-child(11) { animation-delay: 0.50s; }
.resource-card:nth-child(12) { animation-delay: 0.54s; }

@media (max-width: 1024px) {
  .resource-list { grid-template-columns: repeat(2, 1fr); gap: 12px; }
}
@media (max-width: 640px) {
  .resource-list { grid-template-columns: 1fr; gap: 12px; }
}

.sa-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 40px 20px;
}
.sa-empty-text {
  margin: 0;
  font-size: 14px;
  color: #948A80;
  text-align: center;
  line-height: 1.8;
}
.card-deco {
  display: flex;
  justify-content: flex-end;
  opacity: 0.25;
  margin-top: auto;
}
</style>
