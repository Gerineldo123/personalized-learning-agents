<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from './stores/user'
import { useAuthStore } from './stores/auth'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const authStore = useAuthStore()

const menuItems = [
  { path: '/', label: '首页', icon: 'HomeFilled' },
  { path: '/chat', label: 'AI 对话', icon: 'ChatDotRound' },
  { path: '/profile', label: '学习画像', icon: 'UserFilled' },
  { path: '/resources', label: '学习资源', icon: 'Document' },
  { path: '/mistakes', label: '错题本', icon: 'CollectionTag' },
  { path: '/path', label: '专注淀粉肠', icon: 'Food' },
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
</script>

<template>
  <router-view v-if="isAuthPage" />

  <el-container v-else class="app-container">
    <el-aside width="220px" class="app-sidebar">
      <div class="logo">
        <span class="logo-text">个性化学习</span>
      </div>
      <el-menu
        :default-active="route.path"
        background-color="#1d1e2c"
        text-color="#a0a4b8"
        active-text-color="#409eff"
        @select="navigate"
      >
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-footer">
        <div v-if="userStore.userId" class="user-info">
          <span class="user-tag">{{ userStore.userId }}</span>
          <el-button type="danger" size="small" plain @click="logout" style="padding: 5px 12px">
            <el-icon style="margin-right:4px"><component :is="'SwitchButton'" /></el-icon>
            退出登录
          </el-button>
        </div>
      </div>
    </el-aside>

    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.app-container {
  height: 100vh;
  margin: 0;
  padding: 0;
}

.app-sidebar {
  background-color: #1d1e2c;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid #2a2b3d;
  flex-shrink: 0;
}

.logo-text {
  color: #fff;
  font-size: 18px;
  font-weight: 600;
}

.el-menu {
  flex: 1;
  border-right: none;
}

.sidebar-footer {
  border-top: 1px solid #2a2b3d;
  padding: 12px 16px;
  flex-shrink: 0;
}

.user-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.user-tag {
  color: #a0a4b8;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 140px;
}

.app-main {
  background-color: #f5f7fa;
  padding: 24px;
  overflow-y: auto;
}
</style>

