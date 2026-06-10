<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import { weakPointApi } from '../api/weakPoint'
import { useUserStore } from '../stores/user'
import { useEventStore } from '../stores/event'
import MindMapViewer from '../components/resource/MindMapViewer.vue'
import QuizCard from '../components/resource/QuizCard.vue'
import PptViewer from '../components/resource/PptViewer.vue'
import WeakPointDashboard from '../components/WeakPointDashboard.vue'
import { ElMessage } from 'element-plus'
import { renderMarkdownEnhanced as renderMdCommon, codeBlockStore } from '../utils/markdown'

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
const weakPointRecs = ref<any[]>([])
const showWeakDashboard = ref(false)
const typeFilter = ref('')
const searchKeyword = ref('')
const loading = ref(false)
const selected = ref<any>(null)
const showGenDialog = ref(false)
const genTopic = ref('')
const genTypes = ref<string[]>(['article'])
const genQuestionCount = ref(5)
const genDifficulty = ref('中等')
const genLoading = ref(false)
const starterLoading = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null
const manageMode = ref(false)
const selectedIds = ref<number[]>([])
function markdownSource(content: any): string {
  if (typeof content === 'string') return content
  if (content && typeof content === 'object') {
    if (typeof content.text === 'string') return content.text
    if (typeof content.markdown === 'string') return content.markdown
    if (typeof content.code === 'string') return '```python\n' + content.code + '\n```'
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
]
const difficultyOptions = ['简单', '中等', '较难', '挑战']

function startPoll() {
  loadResources()
  pollTimer = setInterval(loadResources, 30000)
}

onMounted(() => {
  if (userStore.userId) startPoll()
  eventStore.connect(userStore.userId || 'user_default')
  loadProfileAndSeeds()
  loadWeakPointRecs()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

watch(() => eventStore.lastEvent, (evt) => {
  if (evt?.event === 'resource.created') loadResources()
})

watch(() => searchKeyword.value, () => { page.value = 1; loadResources() })
watch(() => userStore.userId, (newId) => {
  if (newId) {
    startPoll()
    loadProfileAndSeeds()
    loadWeakPointRecs()
  } else if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
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

async function loadWeakPointRecs() {
  if (!userStore.userId) return
  try {
    const r = await weakPointApi.getRecommendations(userStore.userId, 10)
    weakPointRecs.value = r.data
  } catch {
    weakPointRecs.value = []
  }
}

async function archiveWeakPoint(wp: any) {
  await weakPointApi.updateStatus(wp.id, 'archived', userStore.userId!)
  await loadWeakPointRecs()
}

async function loadResources() {
  if (!userStore.userId) return
  loading.value = true
  try {
    const offset = (page.value - 1) * pageSize.value
    const params: any = { user_id: userStore.userId, limit: pageSize.value, offset }
    if (typeFilter.value) params.resource_type = typeFilter.value
    if (searchKeyword.value.trim()) params.keyword = searchKeyword.value.trim()
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
      }
    })
    ElMessage.success('资源生成完成')
    showGenDialog.value = false
    genTopic.value = ''
    genTypes.value = ['article']
    genQuestionCount.value = 5
    genDifficulty.value = '中等'
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

function viewResource(r: any) {
  if (manageMode.value) {
    toggleSelect(r.id)
    return
  }
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
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先选择资源')
    return
  }
  try {
    await api.post('/resources/batch_pin', null, {
      params: {
        user_id: userStore.userId,
        ids: selectedIds.value.join(','),
        pinned,
      },
    })
    ElMessage.success(pinned ? '已批量置顶' : '已取消置顶')
    await loadResources()
  } catch {
    ElMessage.error('操作失败')
  }
}

async function batchDelete() {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先选择资源')
    return
  }
  try {
    await api.post('/resources/batch_delete', null, {
      params: {
        user_id: userStore.userId,
        ids: selectedIds.value.join(','),
      },
    })
    ElMessage.success('已批量删除')
    selectedIds.value = []
    await loadResources()
  } catch {
    ElMessage.error('删除失败')
  }
}

function typeLabel(t: string) {
  const map: Record<string, string> = { article: '文章', quiz: '题库', code: '代码', mindmap: '思维导图', ppt: '课件', video: '视频', evaluation: '评估' }
  return map[t] || t
}

function typeTag(t: string) {
  const map: Record<string, string> = { article: 'primary', quiz: 'warning', code: 'success', mindmap: 'info', ppt: 'danger', video: 'info', evaluation: 'info' }
  return map[t] || 'info'
}
</script>

<template>
  <div class="resources-view">
    <h2 class="page-title">学习资源</h2>

    <div class="toolbar">
      <el-select v-model="typeFilter" placeholder="全部类型" @change="page = 1; loadResources()" style="width: 160px">
        <el-option v-for="t in resourceTypes" :key="t" :label="t || '全部'" :value="t" />
      </el-select>
      <el-input
        v-model="searchKeyword"
        placeholder="搜索资源标题..."
        clearable
        style="width: 220px; margin-left: 8px"
        @clear="loadResources()"
        @keyup.enter="loadResources()"
      />
      <el-button @click="loadResources" style="margin-left: 8px">刷新</el-button>
      <el-button style="margin-left: 8px" @click="toggleManageMode">{{ manageMode ? '完成管理' : '管理资源' }}</el-button>
      <el-button v-if="manageMode" style="margin-left: 8px" @click="batchPin(1)">批量置顶</el-button>
      <el-button v-if="manageMode" style="margin-left: 8px" @click="batchPin(0)">取消置顶</el-button>
      <el-button v-if="manageMode" style="margin-left: 8px" type="danger" @click="batchDelete">批量删除</el-button>
      <el-button type="primary" @click="showGenDialog = true" style="margin-left: auto">+ 手动生成</el-button>
    </div>

    <!-- 薄弱知识点专项推荐（新：基于 SM-2 推荐引擎） -->
    <div v-if="weakPointRecs.length > 0 && !selected" class="weak-banner">
      <div class="weak-banner-head">
        <span class="weak-banner-title">薄弱知识点专项推荐</span>
        <span class="weak-banner-hint">{{ weakPointRecs.length }} 个待攻克 · 按复习优先级排序</span>
        <el-button link size="small" style="margin-left: auto" @click="showWeakDashboard = true">管理全部</el-button>
      </div>
      <div class="weak-tags">
        <div v-for="wp in weakPointRecs.slice(0, 8)" :key="wp.id" class="weak-tag-item">
          <el-tag
            :type="wp.status === 'reviewing' ? 'success' : 'warning'"
            size="small"
            class="weak-tag"
            @click="generateQuick({ course: wp.name, topic: wp.name }, 'article')"
          >{{ wp.name }} → 生成讲解</el-tag>
          <span class="tag-close" @click.stop="archiveWeakPoint(wp)">×</span>
        </div>
      </div>
    </div>

    <WeakPointDashboard
      v-model:visible="showWeakDashboard"
      :userId="userStore.userId || ''"
    />

    <div v-if="(!loading && resources.length === 0)" class="starter-panel">
      <div class="starter-head">
        <h3>根据你的学习画像推荐</h3>
        <el-button type="success" :loading="starterLoading" @click="generateStarterPack">
          一键生成入门资源包
        </el-button>
      </div>
      <p class="starter-desc">系统会优先根据你的薄弱课程，自动生成「文章 + 题库」组合资源，帮助你快速开始学习。</p>

      <div v-if="recommendedSeeds.length > 0" class="seed-grid">
        <div v-for="s in recommendedSeeds" :key="s.course + s.topic" class="seed-card">
          <div class="seed-title">{{ s.course }}</div>
          <div class="seed-topic">{{ s.topic }}</div>
          <div class="seed-actions">
            <el-button size="small" @click="generateQuick(s, 'article')">生成文章</el-button>
            <el-button size="small" type="warning" @click="generateQuick(s, 'quiz')">生成题库</el-button>
          </div>
        </div>
      </div>

      <el-empty v-else description="尚未检测到可推荐的薄弱课程，可先去学习画像完成问卷" />
    </div>

    <div v-if="loading" v-loading="loading" class="loading-box" />

    <div v-else-if="selected" class="detail-view">
      <el-button @click="selected = null" style="margin-bottom: 16px">返回列表</el-button>
      <QuizCard v-if="selected.resource_type === 'quiz'" :content="selected.content" :resourceId="selected.id" :userId="userStore.userId" />
      <MindMapViewer v-else-if="selected.resource_type === 'mindmap'" :markdown="selected.content?.markdown || ''" />
      <PptViewer v-else-if="selected.resource_type === 'ppt'" :content="selected.content" :resourceId="selected.id" :userId="userStore.userId" />
      <div v-else class="text-content markdown-body" v-html="renderMarkdown(selected.content)" @click="handleDetailClick"></div>
    </div>

    <div v-else-if="resources.length > 0" class="resource-list">
      <div v-for="r in resources" :key="r.id" class="resource-card" @click="viewResource(r)">
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
      </div>
    </div>

    <div v-else class="empty-box">
      <el-empty description="暂无资源" />
    </div>

    <div v-if="!selected && !loading && totalResources > pageSize" class="pagination-box">
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
          <el-input v-model="genTopic" placeholder="例如：Python装饰器" />
        </el-form-item>
        <el-form-item label="资源类型">
          <el-checkbox-group v-model="genTypes">
            <el-checkbox v-for="o in genTypeOptions" :key="o.value" :value="o.value">{{ o.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <template v-if="genTypes.includes('quiz')">
          <el-form-item label="题目数量">
            <el-input-number v-model="genQuestionCount" :min="3" :max="30" :step="1" />
            <span style="margin-left:8px;color:#909399;font-size:12px">建议 5~15 题</span>
          </el-form-item>
          <el-form-item label="题库难度">
            <el-radio-group v-model="genDifficulty">
              <el-radio v-for="d in difficultyOptions" :key="d" :value="d">{{ d }}</el-radio>
            </el-radio-group>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showGenDialog = false">取消</el-button>
        <el-button type="primary" :loading="genLoading" @click="startGenerate">生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.resources-view { max-width: 1000px; }
.page-title { margin-bottom: 24px; color: #303133; }
.toolbar { display: flex; align-items: center; margin-bottom: 20px; }
.loading-box { height: 200px; }

.starter-panel {
  background: linear-gradient(140deg, #f5f9ff 0%, #f8fff5 100%);
  border: 1px solid #dfe8ff;
  border-radius: 10px;
  padding: 18px;
  margin-bottom: 20px;
}

.starter-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.starter-head h3 { margin: 0; color: #303133; font-size: 18px; }
.starter-desc { margin: 0 0 14px; color: #606266; font-size: 13px; line-height: 1.7; }

.seed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.seed-card {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px;
}

.seed-title { font-weight: 600; color: #303133; margin-bottom: 4px; }
.seed-topic { color: #606266; font-size: 13px; min-height: 40px; line-height: 1.5; }
.seed-actions { display: flex; gap: 8px; margin-top: 10px; }

.resource-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }

.resource-card {
  background: #fff; border-radius: 8px; border: 1px solid #e4e7ed; padding: 16px;
  cursor: pointer; transition: box-shadow 0.2s;
}
.resource-card:hover { box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08); }

.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.card-date { font-size: 12px; color: #c0c4cc; }
.card-title { margin: 0; color: #303133; font-size: 15px; line-height: 1.5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.pagination-box { display: flex; justify-content: center; margin-top: 24px; }

.weak-banner {
  background: #fffbf0;
  border: 1px solid #ffe58f;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
}
.weak-banner-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.weak-banner-title { font-weight: 600; color: #d48806; font-size: 14px; }
.weak-banner-hint { font-size: 12px; color: #ad8b00; }
.weak-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.weak-tag-item { display: flex; align-items: center; gap: 2px; }
.weak-tag { cursor: pointer; }
.weak-tag:hover { opacity: 0.8; }
.tag-close { cursor: pointer; color: #aaa; font-size: 14px; padding: 0 2px; line-height: 1; }
.tag-close:hover { color: #f56c6c; }

.text-content { background: #fff; border-radius: 8px; border: 1px solid #e4e7ed; padding: 20px; }
.text-content :deep(h1),
.text-content :deep(h2),
.text-content :deep(h3) {
  margin: 12px 0 8px;
  font-weight: 600;
}
.text-content :deep(h1) { font-size: 22px; }
.text-content :deep(h2) { font-size: 18px; }
.text-content :deep(h3) { font-size: 16px; }
.text-content :deep(p) { margin: 8px 0; }
.text-content :deep(ul),
.text-content :deep(ol) { margin: 8px 0; padding-left: 20px; }
.text-content :deep(li) { margin: 4px 0; }
.text-content :deep(code) {
  background: rgba(0,0,0,0.06);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}
.text-content :deep(pre) {
  background: #1f2430;
  color: #d8dee9;
  padding: 14px 16px;
  border-radius: 0 0 8px 8px;
  overflow-x: auto;
  margin: 0;
}
.text-content :deep(pre code) {
  background: transparent;
  padding: 0;
  color: inherit;
  font-size: 13px;
  white-space: pre;
  tab-size: 4;
  -moz-tab-size: 4;
}
.text-content :deep(.code-block-wrapper) {
  margin: 12px 0;
  border-radius: 8px;
  overflow: hidden;
}
.text-content :deep(.code-header) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #21252b;
  padding: 6px 14px;
  border-radius: 8px 8px 0 0;
}
.text-content :deep(.code-lang) {
  font-size: 11px;
  color: #abb2bf;
  text-transform: uppercase;
}
.text-content :deep(.code-copy-btn) {
  font-size: 11px;
  color: #abb2bf;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 3px;
  transition: all 0.15s;
  user-select: none;
}
.text-content :deep(.code-copy-btn:hover) {
  color: #fff;
  background: rgba(255, 255, 255, 0.1);
}
.text-content :deep(blockquote) {
  border-left: 3px solid #409eff;
  margin: 10px 0;
  padding: 6px 12px;
  color: #606266;
  background: #f5f9ff;
}
</style>

