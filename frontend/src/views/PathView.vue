<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

const focusState = ref<'idle' | 'selecting' | 'focusing' | 'completed'>('idle')
const focusMinutes = ref(25)
const focusSeconds = ref(0)
const focusRemaining = ref(0)
const focusTotal = ref(0)
const timerView = ref<'hourglass' | 'digital'>('hourglass')
let focusTimer: ReturnType<typeof setInterval> | null = null

const starchSausages = ref(0)
const focusSessions = ref<{ date: string; minutes: number; completed: boolean }[]>([])

onMounted(() => {
  const saved = localStorage.getItem('starch-sausages')
  if (saved) starchSausages.value = parseInt(saved) || 0
  const sessions = localStorage.getItem('focus-sessions')
  if (sessions) focusSessions.value = JSON.parse(sessions)
})

const displayMinutes = computed(() => Math.floor(focusRemaining.value / 60))
const displaySeconds = computed(() => focusRemaining.value % 60)
const focusProgress = computed(() => focusTotal.value > 0 ? (focusTotal.value - focusRemaining.value) / focusTotal.value * 100 : 0)

function openTimePicker() {
  focusState.value = 'selecting'
}

function startFocus() {
  focusTotal.value = focusMinutes.value * 60 + focusSeconds.value
  focusRemaining.value = focusTotal.value
  focusState.value = 'focusing'
  focusTimer = setInterval(() => {
    focusRemaining.value--
    if (focusRemaining.value <= 0) {
      completeFocus()
    }
  }, 1000)
}

function completeFocus() {
  if (focusTimer) { clearInterval(focusTimer); focusTimer = null }
  focusState.value = 'completed'
  starchSausages.value++
  localStorage.setItem('starch-sausages', String(starchSausages.value))
  const session = {
    date: new Date().toISOString(),
    minutes: focusTotal.value / 60,
    completed: true,
  }
  focusSessions.value.unshift(session)
  if (focusSessions.value.length > 50) focusSessions.value = focusSessions.value.slice(0, 50)
  localStorage.setItem('focus-sessions', JSON.stringify(focusSessions.value))
}

function unlockFocus() {
  if (focusTimer) { clearInterval(focusTimer); focusTimer = null }
  const session = {
    date: new Date().toISOString(),
    minutes: Math.ceil((focusTotal.value - focusRemaining.value) / 60),
    completed: false,
  }
  focusSessions.value.unshift(session)
  if (focusSessions.value.length > 50) focusSessions.value = focusSessions.value.slice(0, 50)
  localStorage.setItem('focus-sessions', JSON.stringify(focusSessions.value))
  focusState.value = 'idle'
}

function backToIdle() {
  focusState.value = 'idle'
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

onUnmounted(() => {
  if (focusTimer) clearInterval(focusTimer)
})
</script>

<template>
  <div class="focus-view">
    <h2 class="page-title">专注淀粉肠</h2>

    <!-- Idle State -->
    <div v-if="focusState === 'idle'" class="idle-area">
      <div class="sausage-counter">
        <span class="sausage-icon">🌭</span>
        <span class="sausage-count">× {{ starchSausages }}</span>
      </div>
      <p class="idle-hint">集中注意力，开启专注学习模式吧！给自己一些独立思考的时间，来活跃你的大脑吧！</p>
      <el-button type="primary" size="large" class="start-btn" @click="openTimePicker">开始专注</el-button>

      <div v-if="focusSessions.length > 0" class="history">
        <div class="history-title">专注记录</div>
        <div v-for="(s, i) in focusSessions" :key="i" class="history-item">
          <span class="h-date">{{ formatDate(s.date) }}</span>
          <span class="h-duration">{{ formatDuration(s.minutes) }}</span>
          <span :class="s.completed ? 'h-done' : 'h-fail'">{{ s.completed ? '✓ 完成' : '✗ 中断' }}</span>
        </div>
      </div>
    </div>

    <!-- Time Picker -->
    <div v-if="focusState === 'selecting'" class="picker-area">
      <p class="picker-label">选择专注时长</p>
      <div class="picker-row">
        <div class="picker-col">
          <div class="picker-title">小时</div>
          <div class="picker-scroll">
            <div
              v-for="h in 4"
              :key="h"
              :class="['picker-item', { active: focusMinutes === h * 60 }]"
              @click="focusMinutes = h * 60; focusSeconds = 0"
            >
              {{ h }}
            </div>
          </div>
        </div>
        <div class="picker-col">
          <div class="picker-title">分钟</div>
          <div class="picker-scroll">
            <div
              v-for="m in [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]"
              :key="m"
              :class="['picker-item', { active: focusMinutes % 60 === m && focusMinutes > 0 }]"
              @click="focusMinutes = Math.floor(focusMinutes / 60) * 60 + m"
            >
              {{ m }}
            </div>
          </div>
        </div>
      </div>
      <p class="picker-result">已选：{{ Math.floor(focusMinutes / 60) > 0 ? Math.floor(focusMinutes / 60) + '小时' : '' }}{{ focusMinutes % 60 > 0 ? focusMinutes % 60 + '分钟' : '' }}</p>
      <div class="picker-actions">
        <el-button @click="backToIdle">取消</el-button>
        <el-button type="primary" @click="startFocus">开始专注</el-button>
      </div>
    </div>

    <!-- Focusing / Locked Overlay -->
    <Teleport to="body">
      <div v-if="focusState === 'focusing'" class="focus-overlay">
        <div class="focus-lock">
          <template v-if="timerView === 'hourglass'">
            <div class="hourglass">
              <div class="hg-glass-top"></div>
              <div class="hg-glass-bottom"></div>
              <div class="hg-sand-top" :style="{ height: (100 - focusProgress) + '%' }">
                <div class="hg-sand-particles"></div>
              </div>
              <div class="hg-sand-stream">
                <div class="hg-stream-line" v-for="i in 3" :key="i" :style="{ animationDelay: i * 0.15 + 's' }"></div>
              </div>
              <div class="hg-sand-bottom" :style="{ height: focusProgress + '%' }">
                <div class="hg-sand-pile"></div>
              </div>
            </div>
            <div class="lock-progress">
              <div class="lock-progress-bar" :style="{ width: focusProgress + '%' }"></div>
            </div>
          </template>
          <template v-else>
            <div class="lock-timer-big">
              <span class="timer-min">{{ String(displayMinutes).padStart(2, '0') }}</span>
              <span class="timer-sep-big">:</span>
              <span class="timer-sec">{{ String(displaySeconds).padStart(2, '0') }}</span>
            </div>
            <div class="lock-progress">
              <div class="lock-progress-bar" :style="{ width: focusProgress + '%' }"></div>
            </div>
          </template>

          <p class="lock-hint">放下手机，回归书本，专注学习</p>

          <div class="lock-actions">
            <button class="lock-toggle" @click="timerView = timerView === 'hourglass' ? 'digital' : 'hourglass'" title="切换显示">
              {{ timerView === 'hourglass' ? '🕐' : '⏳' }}
            </button>
            <el-button type="danger" plain class="unlock-btn" @click="unlockFocus">解除锁定</el-button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Completed -->
    <div v-if="focusState === 'completed'" class="done-area">
      <div class="done-icon">🎉</div>
      <div class="done-title">太棒了！</div>
      <div class="done-reward">
        <span>你获得了</span>
        <span class="reward-sausage">🌭 一根淀粉肠</span>
      </div>
      <div class="done-total">
        共计 <b>{{ starchSausages }}</b> 根淀粉肠
      </div>
      <el-button type="primary" size="large" @click="backToIdle">继续专注</el-button>
    </div>
  </div>
</template>

<style scoped>
.focus-view { max-width: 700px; text-align: center; }
.page-title { margin-bottom: 24px; color: #303133; }

/* Idle */
.idle-area { padding: 40px 0; }
.sausage-counter { font-size: 32px; margin-bottom: 16px; }
.sausage-icon { font-size: 40px; }
.sausage-count { color: #e6a23c; font-weight: 700; }
.idle-hint { color: #909399; margin-bottom: 24px; font-size: 15px; }
.start-btn { width: 200px; height: 48px; font-size: 18px; border-radius: 24px; }

.history { margin-top: 40px; text-align: left; }
.history-title { font-size: 14px; font-weight: 600; color: #303133; margin-bottom: 12px; }
.history-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 6px;
  margin-bottom: 6px;
  font-size: 13px;
}
.h-date { flex: 1; color: #606266; }
.h-duration { margin-right: 12px; color: #909399; }
.h-done { color: #67c23a; font-weight: 500; }
.h-fail { color: #f56c6c; }

/* Time Picker */
.picker-area { padding: 30px 0; }
.picker-label { font-size: 16px; color: #303133; margin-bottom: 24px; }
.picker-row { display: flex; justify-content: center; gap: 40px; margin-bottom: 20px; }
.picker-col { }
.picker-title { font-size: 13px; color: #909399; margin-bottom: 8px; }
.picker-scroll { max-height: 240px; overflow-y: auto; border: 1px solid #e4e7ed; border-radius: 8px; }
.picker-item {
  padding: 10px 28px;
  cursor: pointer;
  font-size: 15px;
  color: #606266;
  transition: all 0.15s;
  user-select: none;
}
.picker-item:hover { background: #f5f7fa; }
.picker-item.active { background: #ecf5ff; color: #409eff; font-weight: 600; }
.picker-result { font-size: 15px; color: #409eff; font-weight: 600; margin-bottom: 20px; }
.picker-actions { display: flex; justify-content: center; gap: 12px; }

/* Completed */
.done-area { padding: 40px 0; }
.done-icon { font-size: 60px; margin-bottom: 12px; }
.done-title { font-size: 24px; color: #303133; font-weight: 700; margin-bottom: 16px; }
.done-reward { font-size: 18px; color: #606266; margin-bottom: 8px; }
.reward-sausage { color: #e6a23c; font-weight: 700; }
.done-total { font-size: 14px; color: #909399; margin-bottom: 24px; }
</style>

<style>
.focus-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

.focus-lock {
  text-align: center;
  color: #fff;
}

.lock-icon { font-size: 60px; margin-bottom: 16px; }
.lock-title { font-size: 22px; font-weight: 600; margin-bottom: 24px; }

.lock-timer { font-size: 64px; font-weight: 300; font-family: 'Menlo', 'Consolas', monospace; margin-bottom: 20px; }
.timer-sep { animation: blink 1s infinite; }

.lock-icon-only { font-size: 48px; margin-bottom: 8px; }

.hourglass {
  position: relative;
  width: 80px;
  height: 140px;
  margin: 0 auto 20px;
}

.hg-glass-top {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 50%;
  border-left: 6px solid rgba(255,255,255,0.25);
  border-right: 6px solid rgba(255,255,255,0.25);
  border-top: 6px solid rgba(255,255,255,0.35);
  border-bottom: none;
  border-radius: 6px 6px 0 0;
  overflow: hidden;
}

.hg-glass-bottom {
  position: absolute;
  top: 50%; left: 0; right: 0; bottom: 0;
  border-left: 6px solid rgba(255,255,255,0.25);
  border-right: 6px solid rgba(255,255,255,0.25);
  border-bottom: 6px solid rgba(255,255,255,0.35);
  border-top: none;
  border-radius: 0 0 6px 6px;
  overflow: hidden;
}

.hg-sand-top {
  position: absolute;
  top: 6px; left: 6px; right: 6px;
  bottom: 50%;
  background: linear-gradient(180deg, rgba(240,192,96,0.6) 0%, #e6a23c 90%);
  transition: height 0.8s ease;
  overflow: hidden;
  border-radius: 3px 3px 0 0;
}

.hg-sand-particles {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background:
    radial-gradient(1px 1px at 20% 30%, rgba(255,255,255,0.4) 50%, transparent 50%),
    radial-gradient(1px 1px at 60% 50%, rgba(255,255,255,0.3) 50%, transparent 50%),
    radial-gradient(1px 1px at 40% 70%, rgba(255,255,255,0.35) 50%, transparent 50%),
    radial-gradient(1px 1px at 80% 20%, rgba(255,255,255,0.25) 50%, transparent 50%);
  animation: particles 2s linear infinite;
}

.hg-sand-stream {
  position: absolute;
  top: calc(50% - 16px);
  left: 50%;
  transform: translateX(-50%);
  width: 8px;
  height: 32px;
  overflow: hidden;
}

.hg-stream-line {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: linear-gradient(180deg, transparent 0%, #e6a23c 30%, #e6a23c 70%, transparent 100%);
  animation: streamDown 0.5s linear infinite;
  opacity: 0.8;
}

.hg-sand-bottom {
  position: absolute;
  bottom: 6px; left: 6px; right: 6px;
  height: 0;
  background: linear-gradient(180deg, #c8852a 0%, #e6a23c 60%, rgba(240,192,96,0.6) 100%);
  transition: height 0.8s ease;
  border-radius: 0 0 3px 3px;
  overflow: hidden;
}

.hg-sand-pile {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 10px;
  background: #f0c060;
  border-radius: 50%;
  transform: translateY(-60%);
  animation: pileSettle 1.5s ease-in-out infinite;
}

@keyframes particles {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

@keyframes streamDown {
  0% { transform: translateY(-100%); }
  100% { transform: translateY(100%); }
}

@keyframes pileSettle {
  0%, 100% { transform: translateY(-60%) scaleX(1); }
  50% { transform: translateY(-50%) scaleX(1.05); }
}

.lock-timer-big {
  font-size: 72px;
  font-weight: 200;
  font-family: 'Menlo', 'Consolas', monospace;
  color: #fff;
  margin-bottom: 20px;
  letter-spacing: 4px;
}

.timer-sep-big { animation: blink 1s infinite; }

.lock-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 28px;
}

.lock-toggle {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  border: 1px solid rgba(255,255,255,0.3);
  background: rgba(255,255,255,0.08);
  color: #fff;
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.lock-toggle:hover {
  background: rgba(255,255,255,0.15);
  border-color: rgba(255,255,255,0.5);
}

.lock-progress {
  width: 260px;
  height: 4px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
  margin: 0 auto 20px;
  overflow: hidden;
}

.lock-progress-bar {
  height: 100%;
  background: #67c23a;
  border-radius: 2px;
  transition: width 0.3s linear;
}

.lock-hint { color: rgba(255, 255, 255, 0.6); font-size: 14px; margin-bottom: 0; }
.unlock-btn { width: 160px; }

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}
</style>
