<script setup lang="ts">
import { ref, watch } from 'vue'
import api from '../api'
import { useUserStore } from '../stores/user'

const userStore = useUserStore()

const stats = ref({
  profile: false,
  resources: 0,
  evaluations: 0,
})

const userInputId = ref(userStore.userId || 'test_user_1')

async function loadStats() {
  if (!userStore.userId) return
  try {
    const pr = await api.get('/profile', { params: { user_id: userStore.userId } })
    stats.value.profile = pr.data.found

    const rr = await api.get('/resources', { params: { user_id: userStore.userId } })
    stats.value.resources = rr.data.total || rr.data.items?.length || 0

    const er = await api.get('/evaluation', { params: { user_id: userStore.userId } })
    stats.value.evaluations = er.data.total || er.data.items?.length || 0
  } catch {}
}

function login() {
  userStore.setUserId(userInputId.value)
}

watch(() => userStore.userId, (newId) => {
  if (newId) loadStats()
}, { immediate: true })
</script>

<template>
  <div class="home">
    <h2 class="page-title">学习仪表盘</h2>

    <div v-if="!userStore.userId" class="login-card">
      <el-card>
        <template #header>输入用户标识</template>
        <el-input v-model="userInputId" placeholder="输入 user_id" style="width: 300px" />
        <el-button type="primary" style="margin-left: 12px" @click="login">进入</el-button>
      </el-card>
    </div>

    <div v-else class="stats-grid">
      <el-card class="stat-card">
        <template #header>学习画像</template>
        <el-tag :type="stats.profile ? 'success' : 'info'">
          {{ stats.profile ? '已构建' : '未构建' }}
        </el-tag>
      </el-card>

      <el-card class="stat-card">
        <template #header>学习资源</template>
        <div class="stat-number">{{ stats.resources }}</div>
      </el-card>

      <el-card class="stat-card">
        <template #header>评估报告</template>
        <div class="stat-number">{{ stats.evaluations }}</div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.home { max-width: 800px; }
.page-title { margin-bottom: 24px; color: #303133; }
.login-card { max-width: 500px; }
.stats-grid { display: flex; gap: 20px; flex-wrap: wrap; }
.stat-card { flex: 1; min-width: 200px; }
.stat-number { font-size: 36px; font-weight: 700; color: #409eff; }
</style>
