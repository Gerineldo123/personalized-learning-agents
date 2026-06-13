import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('./views/HomeView.vue') },
    { path: '/chat', redirect: '/agent' },
    { path: '/profile', name: 'profile', component: () => import('./views/ProfileView.vue') },
    { path: '/resources', name: 'resources', component: () => import('./views/ResourcesView.vue') },
    { path: '/mistakes', name: 'mistakes', component: () => import('./views/MistakeView.vue') },
    { path: '/path', name: 'path', component: () => import('./views/PathView.vue') },
    { path: '/learning-path', name: 'learning-path', component: () => import('./views/LearningPathView.vue') },
    { path: '/config', name: 'config', component: () => import('./views/ConfigView.vue') },
    { path: '/auth', name: 'auth', component: () => import('./views/AuthView.vue') },
    { path: '/agent', name: 'agent', component: () => import('./views/AgentPanelView.vue'), meta: { fullscreen: true } },
  ],
})

export default router
