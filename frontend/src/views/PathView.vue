<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import SausageIcon from '../components/SausageIcon.vue'
import SkinUnlockPopup from '../components/SkinUnlockPopup.vue'
import { useSausageSkinStore, SAUSAGE_SKINS } from '../stores/sausageSkin'
import { useFocusStore } from '../stores/focus'

const skinStore = useSausageSkinStore()
const focusStore = useFocusStore()

const completedNewSkins = ref<string[]>([])
const showCompletedUnlocks = ref(false)
const previewSkin = ref<{ id: string; locked: boolean } | null>(null)

const sortedSkins = computed(() => {
  const unlocked = SAUSAGE_SKINS.filter(s => skinStore.unlockedSkins.includes(s.id))
  const locked = SAUSAGE_SKINS.filter(s => !skinStore.unlockedSkins.includes(s.id))
  return [...unlocked, ...locked]
})

const totalMinutes = computed(() => {
  return focusStore.focusSessions.reduce((sum, s) => sum + s.minutes, 0)
})

onMounted(() => {
  focusStore.init()
  skinStore.loadFromStorage()
  const newly = skinStore.checkUnlocks()
  if (newly.length > 0) completedNewSkins.value = newly
})

watch(() => focusStore.state, (s) => {
  if (s === 'completed') {
    const newly = skinStore.checkUnlocks()
    if (newly.length > 0) {
      completedNewSkins.value = newly
      showCompletedUnlocks.value = true
    }
  }
})

function showSkinPreview(id: string) {
  previewSkin.value = { id, locked: !skinStore.unlockedSkins.includes(id) }
}

function closeSkinPreview() {
  previewSkin.value = null
}

function onUnlockDone() {
  showCompletedUnlocks.value = false
  completedNewSkins.value = []
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  const m = d.getMonth() + 1
  const day = d.getDate()
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${m}/${day} ${hh}:${mm}`
}

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes}分钟`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m > 0 ? `${h}小时${m}分钟` : `${h}小时`
}

function formatTotalTime(minutes: number): string {
  if (minutes < 60) return `${Math.floor(minutes)}分钟`
  const h = Math.floor(minutes / 60)
  const m = Math.floor(minutes % 60)
  return m > 0 ? `${h}小时${m}分钟` : `${h}小时`
}

function nextUnlockSkin(): string | null {
  for (const skin of SAUSAGE_SKINS) {
    if (skin.unlockMinutes > 0 && !skinStore.unlockedSkins.includes(skin.id)) return skin.name
  }
  return null
}

function nextUnlockMinutes(): number | null {
  for (const skin of SAUSAGE_SKINS) {
    if (skin.unlockMinutes > 0 && !skinStore.unlockedSkins.includes(skin.id)) return skin.unlockMinutes
  }
  return null
}
</script>

<template>
  <div class="focus-view">
    <h2 class="page-title animate-up animate-delay-1">专注淀粉肠</h2>

    <!-- Idle State -->
    <div v-if="focusStore.state === 'idle'" class="idle-area animate-up animate-delay-2">
      <div class="sausage-counter">
        <SausageIcon :size="56" />
        <span class="sausage-count">{{ formatTotalTime(totalMinutes) }}</span>
      </div>
      <p class="idle-hint">集中注意力，开启专注学习模式吧！给自己一些独立思考的时间，来活跃你的大脑吧！</p>
      <el-button type="primary" size="large" class="start-btn" @click="focusStore.openTimePicker">开始专注</el-button>

      <!-- Skin Selector -->
      <div class="skin-selector animate-up animate-delay-1">
        <div class="skin-selector-title">更换皮肤</div>
        <div class="skin-grid">
          <div
            v-for="skin in sortedSkins"
            :key="skin.id"
            :class="['skin-item', {
              'skin-unlocked': skinStore.unlockedSkins.includes(skin.id),
              'skin-active': skinStore.selectedSkin === skin.id,
              'skin-locked': !skinStore.unlockedSkins.includes(skin.id),
            }]"
            @click="showSkinPreview(skin.id)"
          >
            <SausageIcon :size="48" :skin="skin.id" :outline="!skinStore.unlockedSkins.includes(skin.id)" />
            <div class="skin-item-name">{{ skin.name }}</div>
            <div v-if="!skinStore.unlockedSkins.includes(skin.id)" class="skin-item-lock">
              <span class="skin-lock-icon">🔒</span>
              <span class="skin-lock-text">{{ skin.unlockMinutes }}分钟解锁</span>
            </div>
            <div v-else-if="skinStore.selectedSkin === skin.id" class="skin-item-check">✓</div>
          </div>
        </div>
      </div>

      <div v-if="focusStore.focusSessions.length > 0" class="history">
        <div class="history-title">专注记录</div>
        <div v-for="(s, i) in focusStore.focusSessions" :key="i" class="history-item">
          <span class="h-date">{{ formatDate(s.date) }}</span>
          <span class="h-duration">{{ formatDuration(s.minutes) }}</span>
          <span :class="s.completed ? 'h-done' : 'h-fail'">{{ s.completed ? '✓ 完成' : '✗ 中断' }}</span>
        </div>
        <div class="history-footer-deco">
          <SausageIcon :size="28" muted />
        </div>
      </div>
    </div>

    <!-- Time Picker -->
    <div v-if="focusStore.state === 'selecting'" class="picker-area">
      <p class="picker-label">选择专注时长</p>
      <div class="picker-row">
        <div class="picker-col">
          <div class="picker-title">小时</div>
          <div class="picker-scroll">
            <div
              v-for="h in 4"
              :key="h"
              :class="['picker-item', { active: focusStore.focusMinutes === h * 60 }]"
              @click="focusStore.focusMinutes = h * 60; focusStore.focusSeconds = 0"
            >{{ h }}</div>
          </div>
        </div>
        <div class="picker-col">
          <div class="picker-title">分钟</div>
          <div class="picker-scroll">
            <div
              v-for="m in [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]"
              :key="m"
              :class="['picker-item', { active: focusStore.focusMinutes % 60 === m && focusStore.focusMinutes > 0 }]"
              @click="focusStore.focusMinutes = Math.floor(focusStore.focusMinutes / 60) * 60 + m"
            >{{ m }}</div>
          </div>
        </div>
      </div>
      <p class="picker-result">已选：{{ Math.floor(focusStore.focusMinutes / 60) > 0 ? Math.floor(focusStore.focusMinutes / 60) + '小时' : '' }}{{ focusStore.focusMinutes % 60 > 0 ? focusStore.focusMinutes % 60 + '分钟' : '' }}</p>
      <div class="picker-actions">
        <el-button @click="focusStore.backToIdle">取消</el-button>
        <el-button type="primary" @click="focusStore.startFocus">开始专注</el-button>
      </div>
    </div>

    <!-- Focusing: overlay handled in App.vue, show page content -->
    <div v-if="focusStore.state === 'focusing'" class="focusing-page">
      <div class="focusing-timer">
        {{ String(focusStore.displayMinutes).padStart(2, '0') }}:{{ String(focusStore.displaySeconds).padStart(2, '0') }}
      </div>
      <div class="focusing-progress">
        <div class="fp-bar" :style="{ width: focusStore.focusProgress + '%' }"></div>
      </div>
      <p class="focusing-hint">专注模式已开启，悬浮窗口显示计时器。</p>
    </div>

    <!-- Completed -->
    <div v-if="focusStore.state === 'completed'" class="done-area">
      <div class="done-icon">🎉</div>
      <div class="done-title">太棒了！</div>
      <div class="done-reward">
        <span>共计专注</span>
        <span class="reward-sausage">{{ formatTotalTime(totalMinutes) }}</span>
      </div>
      <div v-if="nextUnlockSkin()" class="done-total">
        再专注 {{ (nextUnlockMinutes() ?? 0) - totalMinutes }} 分钟可解锁「{{ nextUnlockSkin() }}」
      </div>
      <div v-else class="done-total">已解锁全部皮肤！</div>
      <el-button type="primary" size="large" @click="focusStore.backToIdle">继续专注</el-button>
    </div>
  </div>

  <SkinUnlockPopup v-if="showCompletedUnlocks" :skin-ids="completedNewSkins" @done="onUnlockDone" @close="onUnlockDone" />
  <SkinUnlockPopup :preview-skin="previewSkin" @close="closeSkinPreview" @done="closeSkinPreview" />
</template>

<style scoped>
.focus-view { max-width: 1280px; text-align: center; padding: 8px 20px 34px; margin: 0 auto; box-sizing: border-box; }
.page-title { margin-bottom: 24px; color: #3A332E; font-size: 24px; font-weight: 600; }

.idle-area { padding: 40px 0; }
.sausage-counter { display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 16px; user-select: none; transition: opacity 0.15s; }
.sausage-counter:hover { opacity: 0.8; }
.sausage-count { color: #DBA878; font-weight: 700; font-size: 20px; }
.idle-hint { color: #948A80; margin-bottom: 24px; font-size: 14px; }
.start-btn { width: 200px; height: 48px; font-size: 18px; border-radius: 8px; background: #F9D9B8; color: #3A332E; border: none; }

.skin-selector {
  background: #FFFBF5;
  border: 1.5px solid #EFE6DC;
  border-radius: 12px;
  padding: 16px;
  margin: 16px auto;
  max-width: 800px;
}
.skin-selector-title { font-size: 14px; font-weight: 600; color: #3A332E; margin-bottom: 12px; }
.skin-grid { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.skin-item {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 10px 12px; border-radius: 10px; border: 2px solid transparent;
  cursor: pointer; transition: all 0.2s; min-width: 80px; position: relative;
}
.skin-item:hover { border-color: #EFE6DC; }
.skin-unlocked.skin-active { border-color: #F9D9B8; background: rgba(249,217,184,0.12); }
.skin-locked { cursor: default; }
.skin-locked .skin-item-name { color: #C4B8AC; }
.skin-item-name { font-size: 11px; color: #3A332E; font-weight: 500; white-space: nowrap; }
.skin-item-check {
  position: absolute; top: 4px; right: 4px;
  width: 18px; height: 18px; border-radius: 50%;
  background: #98C9B3; color: #fff; font-size: 11px;
  display: flex; align-items: center; justify-content: center; font-weight: 700;
}
.skin-item-lock { display: flex; flex-direction: column; align-items: center; gap: 1px; }
.skin-lock-icon { font-size: 14px; }
.skin-lock-text { font-size: 10px; color: #948A80; white-space: nowrap; }

.history { margin-top: 40px; text-align: left; }
.history-title { font-size: 14px; font-weight: 500; color: #3A332E; margin-bottom: 12px; }
.history-item {
  display: flex; align-items: center; padding: 8px 12px;
  background: #FFFBF5; border: 1px solid #EFE6DC; border-radius: 8px;
  margin-bottom: 6px; font-size: 13px;
}
.h-date { flex: 1; color: #6B635C; }
.h-duration { margin-right: 12px; color: #948A80; }
.h-done { color: #98C9B3; font-weight: 500; }
.h-fail { color: #F2B8A2; }
.history-footer-deco { display: flex; justify-content: center; margin-top: 16px; opacity: 0.4; }

.picker-area { padding: 30px 0; }
.picker-label { font-size: 16px; color: #3A332E; font-weight: 500; margin-bottom: 24px; }
.picker-row { display: flex; justify-content: center; gap: 40px; margin-bottom: 20px; }
.picker-title { font-size: 12px; color: #948A80; margin-bottom: 8px; }
.picker-scroll { max-height: 240px; overflow-y: auto; border: 1.5px solid #EFE6DC; border-radius: 8px; }
.picker-item { padding: 10px 28px; cursor: pointer; font-size: 14px; color: #6B635C; transition: all 0.15s; user-select: none; }
.picker-item:hover { background: #FFF5EB; }
.picker-item.active { background: rgba(249,217,184,0.2); color: #3A332E; font-weight: 600; }
.picker-result { font-size: 14px; color: #DBA878; font-weight: 500; margin-bottom: 20px; }
.picker-actions { display: flex; justify-content: center; gap: 12px; }

.focusing-page { padding: 40px 0; }
.focusing-timer { font-size: 64px; font-weight: 200; font-family: var(--font-mono); margin-bottom: 20px; color: #3A332E; font-variant-numeric: tabular-nums; }
.focusing-progress { width: 260px; height: 4px; background: #EFE6DC; border-radius: var(--radius-full); margin: 0 auto 20px; overflow: hidden; }
.fp-bar { height: 100%; background: linear-gradient(90deg, #F9D9B8, #98C9B3); border-radius: var(--radius-full); transition: width 0.3s linear; }
.focusing-hint { font-size: 14px; color: #948A80; }

.done-area { padding: 40px 0; }
.done-icon { font-size: 60px; margin-bottom: 12px; }
.done-title { font-size: 24px; color: #3A332E; font-weight: 600; margin-bottom: 16px; }
.done-reward { font-size: 16px; color: #6B635C; margin-bottom: 8px; }
.reward-sausage { color: #DBA878; font-weight: 700; }
.done-total { font-size: 14px; color: #948A80; margin-bottom: 24px; }

@keyframes floatUpIn {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-up { opacity: 0; animation: floatUpIn 0.55s cubic-bezier(0.2, 0.75, 0.22, 1) forwards; }
.animate-delay-1 { animation-delay: 0.08s; }
.animate-delay-2 { animation-delay: 0.16s; }
</style>
