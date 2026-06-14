<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from './stores/user'
import { useAuthStore } from './stores/auth'
import { useFocusStore } from './stores/focus'

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
  { path: '/path', label: '专注淀粉肠', icon: 'Food' },
  { path: '/config', label: 'API 配置', icon: 'Setting' },
]

const isAuthPage = computed(() => route.path === '/auth')
const isFullscreen = computed(() => !!route.meta?.fullscreen)

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
</script>

<template>
  <router-view v-if="isAuthPage" />

  <el-container v-else class="app-container">
    <el-aside width="230px" class="app-sidebar">
      <div class="logo-area">
        <div class="logo-icon">
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <rect width="28" height="28" rx="8" fill="url(#logo-grad)" />
            <path d="M8 18l4-8 4 8M14 14l2-4 4 8" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            <defs>
              <linearGradient id="logo-grad" x1="0" y1="0" x2="28" y2="28">
                <stop offset="0%" stop-color="#5b7fff" />
                <stop offset="100%" stop-color="#a78bfa" />
              </linearGradient>
            </defs>
          </svg>
        </div>
        <span class="logo-title">个性化学习</span>
        <span class="logo-subtitle">AI Agent</span>
      </div>

      <nav class="sidebar-nav">
        <div
          v-for="item in menuItems"
          :key="item.path"
          :class="['nav-item', { active: route.path === item.path }]"
          @click="navigate(item.path)"
        >
          <span class="nav-icon">
            <el-icon><component :is="item.icon" /></el-icon>
          </span>
          <span class="nav-label">{{ item.label }}</span>
          <span v-if="route.path === item.path" class="nav-indicator" />
        </div>
      </nav>

      <div class="sidebar-footer">
        <div v-if="userStore.userId" class="user-card">
          <div class="user-avatar">
            {{ userStore.userId.slice(-2).toUpperCase() }}
          </div>
          <div class="user-meta">
            <span class="user-name">{{ userStore.userId }}</span>
            <span class="user-status">在线</span>
          </div>
          <button class="logout-btn" @click="logout" title="退出登录">
            <el-icon><component :is="'SwitchButton'" /></el-icon>
          </button>
        </div>
      </div>
    </el-aside>

    <el-main class="app-main" :class="{ 'app-main--fullscreen': isFullscreen }">
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
  overflow: hidden;
}

.app-sidebar {
  background: var(--sidebar-bg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid var(--sidebar-border);
}

.logo-area {
  padding: 20px 18px 16px;
  border-bottom: 1px solid var(--sidebar-border);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  flex-shrink: 0;
}
.logo-icon {
  margin-bottom: 4px;
}
.logo-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--sidebar-text-active);
  line-height: 1.2;
}
.logo-subtitle {
  font-size: 11px;
  color: var(--sidebar-text);
  letter-spacing: 1px;
  text-transform: uppercase;
}

.sidebar-nav {
  flex: 1;
  padding: 10px 10px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  position: relative;
  color: var(--sidebar-text);
  font-size: 13px;
  user-select: none;
}
.nav-item:hover {
  background: var(--sidebar-hover);
  color: var(--sidebar-text-active);
}
.nav-item.active {
  background: var(--sidebar-active);
  color: var(--sidebar-text-active);
  font-weight: 600;
}
.nav-icon {
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  flex-shrink: 0;
}
.nav-label {
  flex: 1;
}
.nav-indicator {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  background: var(--color-primary);
  border-radius: 0 3px 3px 0;
}

.sidebar-footer {
  border-top: 1px solid var(--sidebar-border);
  padding: 12px 14px;
  flex-shrink: 0;
}

.user-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-md);
  background: var(--sidebar-hover);
}
.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  background: linear-gradient(135deg, var(--color-primary), #a78bfa);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.user-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.user-name {
  font-size: 12px;
  color: var(--sidebar-text-active);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.user-status {
  font-size: 10px;
  color: var(--color-success);
}
.logout-btn {
  width: 30px;
  height: 30px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--sidebar-text);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}
.logout-btn:hover {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.app-main {
  background: var(--bg-page);
  padding: 28px 32px;
  overflow-y: auto;
}
.app-main--fullscreen {
  padding: 0;
  overflow: hidden;
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
  background: var(--sidebar-bg);
  border: 1px solid var(--sidebar-border);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  box-shadow: var(--shadow-xl);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  min-width: 200px;
  user-select: none;
  backdrop-filter: blur(12px);
}

.ff-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.ff-title {
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: 600;
}

.ff-toggle {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.05);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}
.ff-toggle:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.3);
}

.ff-timer {
  font-size: 32px;
  font-weight: 300;
  font-family: var(--font-mono);
  color: #fff;
  letter-spacing: 3px;
  font-variant-numeric: tabular-nums;
}

.ff-bar {
  width: 100%;
  height: 4px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.ff-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary), var(--color-success));
  border-radius: var(--radius-full);
  transition: width 0.3s linear;
}

.ff-unlock {
  width: 100%;
  font-size: 12px;
}
</style>
