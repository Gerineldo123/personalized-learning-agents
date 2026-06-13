<script setup lang="ts">
import { ref, onMounted } from 'vue'
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
    // 同步列表中的进度
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
  return '#409eff'
}

onMounted(loadPaths)
</script>

<template>
  <div class="path-page">
    <h2 class="page-title">学习路径</h2>

    <div v-if="loading" v-loading="true" class="loading-box" />

    <div v-else-if="paths.length === 0" class="empty-state">
      <div class="empty-icon">🗺️</div>
      <p>暂无学习路径，可在 AI 智能助手中进行「学习评估」自动生成路径</p>
      <el-button type="primary" @click="router.push('/agent')">前往 AI 智能助手</el-button>
    </div>

    <div v-else class="path-layout">
      <!-- 左侧课程列表 -->
      <aside class="course-list">
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
            :class="['step-node', { done: step.status === 'done' }]"
          >
            <!-- 连接线 -->
            <div class="step-line" v-if="step.order < selectedPath.steps.length" />

            <div class="step-circle" @click="toggleStep(step)">
              <span v-if="step.status === 'done'">✓</span>
              <span v-else>{{ step.order }}</span>
            </div>

            <div class="step-card">
              <div class="step-card-header">
                <span class="step-title">{{ step.title }}</span>
                <span class="step-duration">⏱ {{ step.duration_estimate }}</span>
              </div>
              <p class="step-desc">{{ step.description }}</p>
              <div class="step-checkpoint">
                <span class="checkpoint-label">验收：</span>{{ step.checkpoint }}
              </div>
              <!-- 关联资源 -->
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
.page-title { margin-bottom: 20px; color: #303133; }
.loading-box { height: 200px; }

.empty-state { text-align: center; padding: 80px 0; color: #909399; }
.empty-icon { font-size: 60px; margin-bottom: 16px; }
.empty-state p { margin-bottom: 20px; font-size: 15px; }

.path-layout { display: flex; gap: 20px; align-items: flex-start; }

/* 左侧 */
.course-list { width: 220px; min-width: 220px; display: flex; flex-direction: column; gap: 8px; }
.course-item { background: #fff; border: 1px solid #e4e7ed; border-radius: 10px; padding: 12px 14px; cursor: pointer; transition: all 0.15s; }
.course-item:hover { border-color: #409eff; }
.course-item.active { border-color: #409eff; background: #ecf5ff; }
.course-name { font-size: 14px; font-weight: 600; color: #303133; margin-bottom: 8px; }
.course-progress-bar { margin-bottom: 6px; }
.course-meta { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #909399; }

/* 右侧 */
.path-detail { flex: 1; background: #fff; border-radius: 12px; border: 1px solid #e4e7ed; padding: 20px 24px; }
.detail-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.detail-header h3 { margin: 0 0 4px; font-size: 18px; color: #303133; }
.progress-text { font-size: 13px; color: #909399; }
.overall-progress { margin-bottom: 24px; }

/* 步骤时间线 */
.steps-timeline { display: flex; flex-direction: column; gap: 0; }
.step-node { display: flex; gap: 16px; position: relative; }
.step-line {
  position: absolute;
  left: 19px;
  top: 40px;
  width: 2px;
  height: calc(100% - 8px);
  background: #e4e7ed;
  z-index: 0;
}
.step-node.done .step-line { background: #67c23a; }

.step-circle {
  width: 40px;
  height: 40px;
  min-width: 40px;
  border-radius: 50%;
  background: #f5f7fa;
  border: 2px solid #dcdfe6;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: #909399;
  cursor: pointer;
  z-index: 1;
  transition: all 0.2s;
  margin-top: 0;
}
.step-node.done .step-circle { background: #67c23a; border-color: #67c23a; color: #fff; }
.step-circle:hover { border-color: #409eff; color: #409eff; }
.step-node.done .step-circle:hover { background: #85ce61; border-color: #85ce61; color: #fff; }

.step-card { flex: 1; background: #fafafa; border: 1px solid #ebeef5; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; }
.step-node.done .step-card { background: #f0f9eb; border-color: #b3e19d; }
.step-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.step-title { font-weight: 600; font-size: 14px; color: #303133; }
.step-duration { font-size: 12px; color: #909399; }
.step-desc { font-size: 13px; color: #606266; margin: 0 0 8px; line-height: 1.5; }
.step-checkpoint { font-size: 12px; color: #909399; }
.checkpoint-label { font-weight: 600; color: #e6a23c; }

.step-resources { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.res-tag { font-size: 12px; color: #409eff; background: #ecf5ff; border: 1px solid #b3d8ff; border-radius: 4px; padding: 2px 8px; cursor: pointer; }
.res-tag:hover { background: #409eff; color: #fff; }
</style>
