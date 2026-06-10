<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { useUserStore } from '../stores/user'

const userStore = useUserStore()
const router = useRouter()

const profile = ref<any>(null)
const quizStats = ref({ total: 0, avg_score_percent: 0, latest_score_percent: null as number | null })
const resourceCount = ref(0)
const recentResources = ref<any[]>([])
const loading = ref(false)

async function loadDashboard() {
  if (!userStore.userId) return
  loading.value = true
  try {
    const [pr, qr, rr] = await Promise.all([
      api.get('/profile', { params: { user_id: userStore.userId } }),
      api.get('/quiz/stats', { params: { user_id: userStore.userId } }),
      api.get('/resources', { params: { user_id: userStore.userId, limit: 4 } }),
    ])
    profile.value = pr.data?.found ? pr.data.profile : null
    quizStats.value = {
      total: qr.data.total || 0,
      avg_score_percent: qr.data.avg_score_percent || 0,
      latest_score_percent: qr.data.latest_score_percent ?? null,
    }
    resourceCount.value = rr.data.total || 0
    recentResources.value = (rr.data.items || []).slice(0, 4)
  } catch {}
  finally { loading.value = false }
}

const weakPoints = computed(() => (profile.value?.weak_points || []).slice(0, 6))
const weakCourses = computed(() => (profile.value?.weak_courses || []).slice(0, 3))

const scoreColor = computed(() => {
  const s = quizStats.value.avg_score_percent
  if (s >= 80) return '#67c23a'
  if (s >= 60) return '#e6a23c'
  return '#f56c6c'
})

function typeLabel(t: string) {
  const map: Record<string, string> = { article: '文章', quiz: '题库', code: '代码', mindmap: '思维导图', ppt: '课件' }
  return map[t] || t
}

watch(() => userStore.userId, (id) => { if (id) loadDashboard() }, { immediate: true })
</script>

<template>
  <div class="dashboard">
    <h2 class="page-title">学习仪表盘</h2>

    <div v-if="loading" v-loading="loading" class="loading-box" />

    <template v-else>
      <!-- 无画像提示 -->
      <div v-if="!profile" class="no-profile-card">
        <div class="no-profile-body">
          <p>尚未构建学习画像，系统无法个性化推荐内容。</p>
          <el-button type="primary" @click="router.push('/profile')">立即构建画像</el-button>
        </div>
      </div>

      <!-- 数据概览 -->
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-label">平均正确率</div>
          <div class="stat-value" :style="{ color: scoreColor }">
            {{ quizStats.avg_score_percent.toFixed(1) }}%
          </div>
          <div class="stat-sub">共 {{ quizStats.total }} 次答题</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">学习资源</div>
          <div class="stat-value">{{ resourceCount }}</div>
          <div class="stat-sub">篇文章 / 题库 / 课件</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">薄弱知识点</div>
          <div class="stat-value" style="color: #f56c6c">{{ weakPoints.length }}</div>
          <div class="stat-sub">{{ weakCourses.length }} 门薄弱课程</div>
        </div>
        <div class="stat-card action-card" @click="router.push('/chat')">
          <div class="stat-label">开始学习</div>
          <div class="stat-value" style="font-size: 32px">💬</div>
          <div class="stat-sub">与 AI 对话，生成专属内容</div>
        </div>
      </div>

      <!-- 薄弱点快速入口 -->
      <div v-if="weakPoints.length > 0" class="section">
        <div class="section-head">
          <h3>薄弱知识点</h3>
          <el-button text size="small" @click="router.push('/resources')">一键生成专项资源 →</el-button>
        </div>
        <div class="weak-tags">
          <el-tag
            v-for="pt in weakPoints"
            :key="pt"
            type="warning"
            class="weak-tag"
            @click="router.push({ path: '/chat' })"
          >{{ pt }}</el-tag>
        </div>
      </div>

      <!-- 薄弱课程 -->
      <div v-if="weakCourses.length > 0" class="section">
        <div class="section-head">
          <h3>需要提升的课程</h3>
          <el-button text size="small" @click="router.push('/profile')">查看详情 →</el-button>
        </div>
        <div class="course-row">
          <div v-for="c in weakCourses" :key="c.name" class="course-chip" @click="router.push('/profile')">
            <span class="cc-name">{{ c.name }}</span>
            <el-tag size="small" type="danger">{{ c.goal || '待提升' }}</el-tag>
          </div>
        </div>
      </div>

      <!-- 最近资源 -->
      <div v-if="recentResources.length > 0" class="section">
        <div class="section-head">
          <h3>最近生成的资源</h3>
          <el-button text size="small" @click="router.push('/resources')">查看全部 →</el-button>
        </div>
        <div class="resource-row">
          <div
            v-for="r in recentResources" :key="r.id"
            class="res-chip"
            @click="router.push({ path: '/resources', query: { open: String(r.id) } })"
          >
            <el-tag :type="r.resource_type === 'quiz' ? 'warning' : 'info'" size="small">{{ typeLabel(r.resource_type) }}</el-tag>
            <span class="res-title">{{ r.title }}</span>
          </div>
        </div>
      </div>

      <!-- 快捷操作 -->
      <div class="section">
        <h3>快捷操作</h3>
        <div class="quick-actions">
          <el-button @click="router.push({ path: '/chat', query: { prompt: '我想学习今天的薄弱知识点' } })">📚 针对薄弱点学习</el-button>
          <el-button @click="router.push({ path: '/chat', query: { prompt: '帮我复习错题' } })">🔁 复习错题</el-button>
          <el-button @click="router.push('/mistakes')">📋 查看错题本</el-button>
          <el-button @click="router.push('/path')">🌭 专注淀粉肠</el-button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.dashboard { max-width: 960px; }
.page-title { margin-bottom: 24px; color: #303133; }
.loading-box { height: 200px; }

.no-profile-card {
  background: #ecf5ff;
  border: 1px solid #b3d8ff;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}
.no-profile-body { display: flex; justify-content: space-between; align-items: center; }
.no-profile-body p { margin: 0; color: #409eff; font-size: 14px; }

.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }

.stat-card {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  padding: 18px;
  text-align: center;
}
.action-card { cursor: pointer; transition: box-shadow 0.2s; }
.action-card:hover { box-shadow: 0 4px 14px rgba(64, 158, 255, 0.15); border-color: #409eff; }

.stat-label { font-size: 12px; color: #909399; margin-bottom: 8px; }
.stat-value { font-size: 28px; font-weight: 700; color: #303133; margin-bottom: 4px; }
.stat-sub { font-size: 12px; color: #c0c4cc; }

.section { margin-bottom: 24px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-head h3 { margin: 0; font-size: 16px; color: #303133; }

.weak-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.weak-tag { cursor: pointer; }
.weak-tag:hover { opacity: 0.8; }

.course-row { display: flex; gap: 12px; flex-wrap: wrap; }
.course-chip {
  display: flex; align-items: center; gap: 8px;
  background: #fff; border: 1px solid #e4e7ed; border-radius: 6px;
  padding: 8px 12px; cursor: pointer;
}
.course-chip:hover { border-color: #f56c6c; }
.cc-name { font-size: 14px; color: #303133; }

.resource-row { display: flex; flex-direction: column; gap: 8px; }
.res-chip {
  display: flex; align-items: center; gap: 10px;
  background: #fff; border: 1px solid #e4e7ed; border-radius: 6px;
  padding: 10px 14px; cursor: pointer;
}
.res-chip:hover { border-color: #409eff; }
.res-title { font-size: 14px; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.quick-actions { display: flex; gap: 10px; flex-wrap: wrap; }
</style>
