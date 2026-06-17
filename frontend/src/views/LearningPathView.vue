<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'
import api from '../api'
import { ElMessage } from 'element-plus'

const userStore = useUserStore()
const router = useRouter()

interface PathStep {
  order: number
  title: string
  description: string
  duration_estimate: string
  checkpoint: string
  status: 'pending' | 'done'
  completed_at?: string | null
  resource_ids?: number[]
  resources?: Array<{ id: number; title: string; type: string }>
}

interface CoursePath {
  id: number
  course_name: string
  steps: PathStep[]
  total_steps: number
  done_steps: number
  progress: number
  status: 'active' | 'completed'
  created_at: string | null
}

const paths = ref<CoursePath[]>([])
const selectedPath = ref<CoursePath | null>(null)
const loading = ref(false)
const generatingResources = ref(false)

// 快速生成路径
const quickCourseName = ref('')
const quickGenerating = ref(false)

// 下一步：第一个 pending 的步骤
const nextStepOrder = computed(() => {
  if (!selectedPath.value) return -1
  const pending = selectedPath.value.steps.find(s => s.status !== 'done')
  return pending ? pending.order : -1
})

async function loadPaths() {
  loading.value = true
  try {
    const r = await api.get('/path/course/list', { params: { user_id: userStore.userId } })
    paths.value = r.data.items || []
    if (paths.value.length > 0 && !selectedPath.value) {
      selectedPath.value = paths.value[0]
    }
  } catch {
    ElMessage.error('加载路径失败')
  } finally {
    loading.value = false
  }
}

async function quickGenerate() {
  if (!quickCourseName.value.trim()) return
  quickGenerating.value = true
  try {
    const r = await api.post('/path/course/generate', null, {
      params: { user_id: userStore.userId, course_name: quickCourseName.value.trim() },
      timeout: 120000,
    })
    await loadPaths()
    selectedPath.value = paths.value.find(p => p.id === r.data.id) || paths.value[0]
    quickCourseName.value = ''
    ElMessage.success(`已生成「${r.data.course_name}」学习路径`)
  } catch {
    ElMessage.error('生成失败，请重试')
  } finally {
    quickGenerating.value = false
  }
}

async function toggleStep(step: PathStep) {
  if (!selectedPath.value) return
  const done = step.status !== 'done'
  try {
    const r = await api.patch(`/path/course/${selectedPath.value.id}/step/${step.order}`, null, {
      params: { done }
    })
    step.status = done ? 'done' : 'pending'
    step.completed_at = done ? new Date().toISOString() : null
    selectedPath.value.done_steps = r.data.done_steps
    selectedPath.value.progress = r.data.progress
    selectedPath.value.status = r.data.status
    const p = paths.value.find(p => p.id === selectedPath.value!.id)
    if (p) { p.done_steps = r.data.done_steps; p.progress = r.data.progress; p.status = r.data.status }
  } catch {
    ElMessage.error('更新失败')
  }
}

async function generateResources() {
  if (!selectedPath.value) return
  generatingResources.value = true
  try {
    const r = await api.post(`/path/course/${selectedPath.value.id}/generate-resources`, null, {
      params: { user_id: userStore.userId }
    })
    selectedPath.value.steps = r.data.steps
    ElMessage.success('资源生成完成')
  } catch {
    ElMessage.error('资源生成失败')
  } finally {
    generatingResources.value = false
  }
}

function progressColor(p: number) {
  if (p >= 1) return '#67c23a'
  if (p >= 0.5) return '#e6a23c'
  return '#DBA878'
}

onMounted(loadPaths)
</script>

<template>
  <div class="path-page">
    <h2 class="page-title">学习路径</h2>

    <div v-if="loading" v-loading="true" class="loading-box" />

    <div v-else-if="paths.length === 0" class="empty-state">
      <div class="empty-icon">🗺️</div>
      <p class="empty-desc">还没有学习路径，输入课程名称快速生成</p>
      <div class="quick-gen-row">
        <el-input
          v-model="quickCourseName"
          placeholder="例如：数据结构、机器学习、操作系统"
          style="width: 320px"
          @keydown.enter="quickGenerate"
        />
        <el-button type="primary" :loading="quickGenerating" @click="quickGenerate">生成路径</el-button>
      </div>
      <el-divider>或</el-divider>
      <el-button plain @click="router.push('/agent')">前往 AI 智能助手自动生成</el-button>
    </div>

    <div v-else class="path-layout">
      <!-- 左侧课程列表 -->
      <aside class="course-list">
        <div class="course-list-header">
          <span class="course-list-title">我的路径</span>
          <el-popover trigger="click" width="260" placement="bottom-start">
            <template #reference>
              <el-button size="small" type="primary" plain>+ 新建</el-button>
            </template>
            <div class="popover-gen">
              <p style="font-size:13px;margin:0 0 10px;color:var(--text-regular)">输入课程名称生成路径</p>
              <el-input v-model="quickCourseName" placeholder="课程名称" size="small" @keydown.enter="quickGenerate" />
              <el-button type="primary" size="small" style="margin-top:8px;width:100%" :loading="quickGenerating" @click="quickGenerate">生成</el-button>
            </div>
          </el-popover>
        </div>

        <div
          v-for="p in paths" :key="p.id"
          :class="['course-item', { active: selectedPath?.id === p.id }]"
          @click="selectedPath = p"
        >
          <div class="course-name">{{ p.course_name }}</div>
          <el-progress
            :percentage="Math.round(p.progress * 100)"
            :stroke-width="4"
            :color="progressColor(p.progress)"
            :show-text="false"
            class="course-progress-bar"
          />
          <div class="course-meta">
            <span>{{ p.done_steps }}/{{ p.total_steps }} 步</span>
            <el-tag v-if="p.status === 'completed'" type="success" size="small">已完成</el-tag>
            <el-tag v-else type="primary" size="small">进行中</el-tag>
          </div>
        </div>
      </aside>

      <!-- 右侧路径详情 -->
      <main v-if="selectedPath" class="path-detail">
        <div class="detail-header">
          <div>
            <h3>{{ selectedPath.course_name }}</h3>
            <span class="progress-text">{{ selectedPath.done_steps }}/{{ selectedPath.total_steps }} 步完成 · {{ Math.round(selectedPath.progress * 100) }}%</span>
          </div>
          <el-button
            size="small" type="primary" plain
            :loading="generatingResources"
            @click="generateResources"
          >✨ 生成步骤资源</el-button>
        </div>

        <el-progress
          :percentage="Math.round(selectedPath.progress * 100)"
          :color="progressColor(selectedPath.progress)"
          :stroke-width="8"
          class="overall-progress"
        />

        <!-- 步骤时间线 -->
        <div class="steps-timeline">
          <div
            v-for="step in selectedPath.steps" :key="step.order"
            :class="['step-node', { done: step.status === 'done', current: step.order === nextStepOrder }]"
          >
            <div class="step-line" v-if="step.order < selectedPath.steps.length" />

            <div class="step-circle" @click="toggleStep(step)">
              <span v-if="step.status === 'done'">✓</span>
              <span v-else-if="step.order === nextStepOrder">▶</span>
              <span v-else>{{ step.order }}</span>
            </div>

            <div class="step-card">
              <div class="step-card-header">
                <div style="display:flex;align-items:center;gap:8px">
                  <span class="step-title">{{ step.title }}</span>
                  <el-tag v-if="step.order === nextStepOrder" size="small" type="warning">当前步骤</el-tag>
                </div>
                <span class="step-duration">⏱ {{ step.duration_estimate }}</span>
              </div>
              <p class="step-desc">{{ step.description }}</p>
              <div class="step-checkpoint">
                <span class="checkpoint-label">验收：</span>{{ step.checkpoint }}
              </div>
              <div v-if="step.resources?.length" class="step-resources">
                <span
                  v-for="res in step.resources" :key="res.id"
                  class="res-tag"
                  @click="router.push({ path: '/resources', query: { open: String(res.id) } })"
                >{{ res.type === 'quiz' ? '📝' : '📄' }} {{ res.title }}</span>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.path-page { max-width: 1100px; }
.page-title { margin-bottom: 24px; }
.loading-box { height: 200px; }

.empty-state { text-align: center; padding: 60px 20px; }
.empty-icon { font-size: 48px; margin-bottom: 16px; }
.empty-desc { color: var(--text-secondary); margin-bottom: 16px; }
.quick-gen-row { display: flex; justify-content: center; gap: 10px; margin-bottom: 16px; }

.path-layout { display: flex; gap: 20px; align-items: flex-start; }

.course-list { width: 220px; min-width: 220px; display: flex; flex-direction: column; gap: 8px; }
.course-list-header { display: flex; justify-content: space-between; align-items: center; padding: 0 2px 6px; }
.course-list-title { font-size: 13px; font-weight: 600; color: var(--text-secondary); }
.popover-gen { padding: 4px; }

.course-item {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.course-item:hover { border-color: var(--color-primary-border); }
.course-item.active { border-color: var(--color-primary); background: var(--color-primary-bg); }
.course-name { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.course-progress-bar { margin-bottom: 6px; }
.course-meta { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--text-secondary); }

.path-detail { flex: 1; background: var(--bg-card); border-radius: var(--radius-lg); border: 1px solid var(--border-light); padding: 24px 28px; }
.detail-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.detail-header h3 { margin: 0 0 4px; font-size: 18px; }
.progress-text { font-size: 13px; color: var(--text-secondary); }
.overall-progress { margin-bottom: 28px; }

.steps-timeline { display: flex; flex-direction: column; gap: 0; }
.step-node { display: flex; gap: 16px; position: relative; }
.step-line {
  position: absolute;
  left: 19px;
  top: 40px;
  width: 2px;
  height: calc(100% - 8px);
  background: var(--border-light);
  z-index: 0;
}
.step-node.done .step-line { background: var(--color-success); }
.step-node.current .step-line { background: var(--color-warning); }

.step-circle {
  width: 40px;
  height: 40px;
  min-width: 40px;
  border-radius: 50%;
  background: var(--bg-overlay);
  border: 2px solid var(--border-base);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-secondary);
  cursor: pointer;
  z-index: 1;
  transition: all var(--transition-base);
  margin-top: 0;
}
.step-node.done .step-circle { background: var(--color-success); border-color: var(--color-success); color: #fff; }
.step-node.current .step-circle { background: var(--color-warning); border-color: var(--color-warning); color: #fff; box-shadow: 0 0 0 4px rgba(230,162,60,0.2); }
.step-circle:hover { border-color: var(--color-primary); color: var(--color-primary); transform: scale(1.1); }
.step-node.done .step-circle:hover { background: var(--color-success); border-color: var(--color-success); color: #fff; }

.step-card {
  flex: 1;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 14px 18px;
  margin-bottom: 16px;
  transition: all var(--transition-fast);
}
.step-node.done .step-card { background: var(--color-success-bg); border-color: rgba(82,196,26,0.25); }
.step-node.current .step-card { border-color: var(--color-warning); background: var(--color-warning-bg); }
.step-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.step-title { font-weight: 600; font-size: 14px; }
.step-duration { font-size: 12px; color: var(--text-secondary); }
.step-desc { font-size: 13px; color: var(--text-regular); margin: 0 0 8px; line-height: 1.5; }
.step-checkpoint { font-size: 12px; color: var(--text-secondary); }
.checkpoint-label { font-weight: 600; color: var(--color-warning); }
.step-resources { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.res-tag {
  font-size: 12px;
  color: var(--color-primary);
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-sm);
  padding: 3px 10px;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.res-tag:hover { background: var(--color-primary); color: #fff; }
</style>

