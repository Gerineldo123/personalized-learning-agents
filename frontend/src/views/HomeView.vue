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
        <div class="stat-card action-card" @click="router.push('/agent')">
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
            @click="router.push({ path: '/agent' })"
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
            <el-tag :type="r.resource_type === 'quiz' ? 'warning' : ''" size="small">{{ typeLabel(r.resource_type) }}</el-tag>
            <span class="res-title">{{ r.title }}</span>
          </div>
        </div>
      </div>

      <!-- 快捷操作 -->
      <div class="section">
        <h3>快捷操作</h3>
        <div class="quick-actions">
          <el-button @click="router.push('/agent')">📚 针对薄弱点学习</el-button>
          <el-button @click="router.push('/agent')">🔁 复习错题</el-button>
          <el-button @click="router.push('/mistakes')">📋 查看错题本</el-button>
          <el-button @click="router.push('/path')">🌭 专注淀粉肠</el-button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.dashboard { max-width: 960px; }
.page-title { margin-bottom: 28px; }

.no-profile-card {
  background: linear-gradient(135deg, var(--color-primary-bg), rgba(167, 139, 250, 0.06));
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-lg);
  padding: 24px;
  margin-bottom: 24px;
}
.no-profile-body { display: flex; justify-content: space-between; align-items: center; }
.no-profile-body p { margin: 0; color: var(--color-primary); font-size: 14px; font-weight: 500; }

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 28px;
}

.stat-card {
  cursor: default;
}
.action-card {
  cursor: pointer;
  background: linear-gradient(135deg, var(--color-primary-bg), rgba(167, 139, 250, 0.04));
  border-color: var(--color-primary-border);
}
.action-card:hover {
  box-shadow: var(--shadow-lg);
  border-color: var(--color-primary);
  transform: translateY(-2px);
}

.section {
  margin-bottom: 28px;
}

.weak-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.weak-tag { cursor: pointer; }
.weak-tag:hover { opacity: 0.85; transform: scale(1.03); }

.course-row { display: flex; gap: 12px; flex-wrap: wrap; }
.course-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 10px 16px;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.course-chip:hover {
  border-color: var(--color-danger);
  box-shadow: var(--shadow-sm);
}
.cc-name {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}

.resource-row { display: flex; flex-direction: column; gap: 8px; }
.res-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 12px 16px;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.res-chip:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-sm);
  transform: translateX(4px);
}
.res-title {
  font-size: 14px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quick-actions { display: flex; gap: 10px; flex-wrap: wrap; }
</style>
