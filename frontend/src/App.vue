<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from './stores/user'
import { useAuthStore } from './stores/auth'
import { useFocusStore } from './stores/focus'
import api from './api'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const authStore = useAuthStore()
const focusStore = useFocusStore()

const menuItems = [
  { path: '/', label: '首页', icon: 'HomeFilled' },
  { path: '/agent', label: 'AI 智能助手', icon: 'ChatDotRound' },
  { path: '/profile', label: '学习画像', icon: 'UserFilled' },
  { path: '/resources', label: '学习资源', icon: 'Document' },
  { path: '/mistakes', label: '错题本', icon: 'CollectionTag' },
  { path: '/learning-path', label: '学习路径', icon: 'Promotion' },
  { path: '/path', label: '专注成长', icon: 'Timer' },
  { path: '/config', label: 'API 配置', icon: 'Setting' },
]

const isAuthPage = computed(() => route.path === '/auth')

watch(
  () => route.path,
  (p) => {
    if (!authStore.isLoggedIn && p !== '/auth') {
      router.replace('/auth')
    }
    if (authStore.isLoggedIn && p === '/auth') {
      router.replace('/')
    }
  },
  { immediate: true },
)

function navigate(path: string) {
  router.push(path)
}

function logout() {
  authStore.clearAuth()
  userStore.clearUserId()
  router.push('/auth')
}

async function deleteAccount() {
  try {
    await ElMessageBox.confirm(
      '注销后将删除当前账号的画像、学习资源、错题、会话、学习路径、PPT 会话和专注记录，且不可恢复。',
      '确认注销账号',
      {
        confirmButtonText: '确认注销',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      },
    )
    await api.delete('/auth/account')
    authStore.clearAuth()
    userStore.clearUserId()
    localStorage.removeItem('focus-sessions')
    localStorage.removeItem('focus-completed-count')
    ElMessage.success('账号已注销')
    router.push('/auth')
  } catch (e: any) {
    if (e === 'cancel' || e === 'close') return
    const message = e?.response?.data?.detail || '账号注销失败'
    ElMessage.error(message)
  }
}
</script>

<template>
  <router-view v-if="isAuthPage" />

  <el-container v-else class="app-container">
    <el-header class="app-header" height="60px">
      <div class="header-left">
        <span class="logo-text">个性化学习</span>
      </div>
      <nav class="header-nav">
        <div
          v-for="item in menuItems"
          :key="item.path"
          class="nav-item"
          :class="{ active: route.path === item.path }"
          @click="navigate(item.path)"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </div>
      </nav>
      <div v-if="userStore.userId" class="header-right">
        <span class="user-tag">{{ userStore.userId }}</span>
        <el-button size="small" @click="logout" style="color:var(--text-secondary);border-color:var(--border)">
          <el-icon style="margin-right:4px"><component :is="'SwitchButton'" /></el-icon>
          退出登录
        </el-button>
        <el-button size="small" type="danger" plain @click="deleteAccount">
          注销账号
        </el-button>
      </div>
    </el-header>

    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>

  <Teleport to="body">
    <div v-if="focusStore.state === 'focusing'" class="focus-float">
      <div class="ff-inner">
        <div class="ff-header">
          <span class="ff-title">专注模式</span>
          <button
            class="ff-toggle"
            @click="focusStore.timerView = focusStore.timerView === 'hourglass' ? 'digital' : 'hourglass'"
            :title="focusStore.timerView === 'hourglass' ? '切换数字' : '切换沙漏'"
          >
            {{ focusStore.timerView === 'hourglass' ? '🕐' : '⏳' }}
          </button>
        </div>
        <span class="ff-timer">
          {{ String(focusStore.displayMinutes).padStart(2, '0') }}:{{ String(focusStore.displaySeconds).padStart(2, '0') }}
        </span>
        <div class="ff-bar">
          <div class="ff-bar-fill" :style="{ width: focusStore.focusProgress + '%' }"></div>
        </div>
        <el-button class="ff-unlock" type="danger" plain size="small" @click="focusStore.unlockFocus">
          解除专注
        </el-button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.app-container {
  height: 100vh;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.app-header {
  background-color: var(--page-white);
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 0 24px;
  width: 100%;
  height: 60px;
  box-sizing: border-box;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border);
}

.header-left {
  display: flex;
  align-items: center;
}

.logo-text {
  color: var(--text-body);
  font-size: 20px;
  font-weight: 600;
  white-space: nowrap;
}

.header-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
}

.nav-item {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 12px;
  height: 36px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  white-space: nowrap;
}

.nav-item:hover {
  background-color: rgba(249, 217, 184, 0.2);
  color: var(--link);
}

.nav-item.active {
  background-color: var(--brand);
  color: var(--text-body);
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  white-space: nowrap;
}

.user-tag {
  color: var(--text-aux);
  font-size: 13px;
}

.app-main {
  background: var(--brand-bg);
  overflow-y: auto;
  flex: 1;
  padding: 28px 32px;
}
</style>

<style>
.focus-float {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9998;
  pointer-events: auto;
}

.ff-inner {
  background: #3A2E26;
  border: 1px solid #4A3E36;
  border-radius: var(--radius-xl);
  padding: 16px 20px;
  box-shadow: var(--shadow-xl);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  min-width: 200px;
  user-select: none;
}

.ff-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.ff-title {
  font-size: 11px;
  color: #B8A898;
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: 600;
}

.ff-toggle {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid rgba(249, 217, 184, 0.2);
  background: rgba(249, 217, 184, 0.08);
  color: var(--brand);
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}
.ff-toggle:hover {
  background: rgba(249, 217, 184, 0.15);
  border-color: rgba(249, 217, 184, 0.4);
}

.ff-timer {
  font-size: 32px;
  font-weight: 300;
  font-family: var(--font-mono);
  color: var(--brand);
  letter-spacing: 3px;
  font-variant-numeric: tabular-nums;
}

.ff-bar {
  width: 100%;
  height: 4px;
  background: rgba(249, 217, 184, 0.15);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.ff-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--brand), var(--color-success));
  border-radius: var(--radius-full);
  transition: width 0.3s linear;
}

.ff-unlock {
  width: 100%;
  font-size: 12px;
}
</style>
