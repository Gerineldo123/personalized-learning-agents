<script setup lang="ts">
import { onMounted } from 'vue'
import { useFocusStore } from '../stores/focus'

const store = useFocusStore()

onMounted(() => {
  store.init()
})

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
</script>

<template>
  <div class="focus-view">
    <h2 class="page-title">专注淀粉肠</h2>

    <!-- Idle -->
    <div v-if="store.state === 'idle'" class="idle-area">
      <div class="sausage-counter">
        <span class="sausage-icon">🌭</span>
        <span class="sausage-count">× {{ store.starchSausages }}</span>
      </div>
      <p class="idle-hint">集中注意力，开启专注学习模式吧！给自己一些独立思考的时间，来活跃你的大脑吧！</p>
      <el-button type="primary" size="large" class="start-btn" @click="store.openTimePicker">开始专注</el-button>

      <div v-if="store.focusSessions.length > 0" class="history">
        <div class="history-title">专注记录</div>
        <div v-for="(s, i) in store.focusSessions" :key="i" class="history-item">
          <span class="h-date">{{ formatDate(s.date) }}</span>
          <span class="h-duration">{{ formatDuration(s.minutes) }}</span>
          <span :class="s.completed ? 'h-done' : 'h-fail'">{{ s.completed ? '✓ 完成' : '✗ 中断' }}</span>
        </div>
      </div>
    </div>

    <!-- Time Picker -->
    <div v-if="store.state === 'selecting'" class="picker-area">
      <p class="picker-label">选择专注时长</p>
      <div class="picker-row">
        <div class="picker-col">
          <div class="picker-title">小时</div>
          <div class="picker-scroll">
            <div
              v-for="h in 4"
              :key="h"
              :class="['picker-item', { active: store.focusMinutes === h * 60 }]"
              @click="store.focusMinutes = h * 60; store.focusSeconds = 0"
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
              :class="['picker-item', { active: store.focusMinutes % 60 === m && store.focusMinutes > 0 }]"
              @click="store.focusMinutes = Math.floor(store.focusMinutes / 60) * 60 + m"
            >
              {{ m }}
            </div>
          </div>
        </div>
      </div>
      <p class="picker-result">已选：{{ Math.floor(store.focusMinutes / 60) > 0 ? Math.floor(store.focusMinutes / 60) + '小时' : '' }}{{ store.focusMinutes % 60 > 0 ? store.focusMinutes % 60 + '分钟' : '' }}</p>
      <div class="picker-actions">
        <el-button @click="store.backToIdle">取消</el-button>
        <el-button type="primary" @click="store.startFocus">开始专注</el-button>
      </div>
    </div>

    <!-- Focusing: page content (floating widget is rendered in App.vue) -->
    <div v-if="store.state === 'focusing'" class="focusing-page">
      <div class="focusing-timer">
        {{ String(store.displayMinutes).padStart(2, '0') }}:{{ String(store.displaySeconds).padStart(2, '0') }}
      </div>
      <div class="focusing-progress">
        <div class="fp-bar" :style="{ width: store.focusProgress + '%' }"></div>
      </div>
      <p class="focusing-hint">专注模式已开启，你可以继续使用学习系统的其他功能。</p>
      <p class="focusing-sub">⚠️ 请勿退出全屏、切换标签页或最小化窗口，否则会话将自动中断。</p>
    </div>

    <!-- Completed -->
    <div v-if="store.state === 'completed'" class="done-area">
      <div class="done-icon">🎉</div>
      <div class="done-title">太棒了！</div>
      <div class="done-reward">
        <span>你获得了</span>
        <span class="reward-sausage">🌭 一根淀粉肠</span>
      </div>
      <div class="done-total">
        共计 <b>{{ store.starchSausages }}</b> 根淀粉肠
      </div>
      <el-button type="primary" size="large" @click="store.backToIdle">继续专注</el-button>
    </div>
  </div>
</template>

<style scoped>
.focus-view { max-width: 700px; text-align: center; }
.page-title { margin-bottom: 28px; }

.idle-area { padding: 40px 0; }
.sausage-counter { font-size: 32px; margin-bottom: 20px; display: flex; align-items: center; justify-content: center; gap: 10px; }
.sausage-icon { font-size: 44px; }
.sausage-count { color: var(--color-warning); font-weight: 800; }
.idle-hint { color: var(--text-secondary); margin-bottom: 28px; font-size: 15px; max-width: 420px; margin-left: auto; margin-right: auto; line-height: 1.7; }
.start-btn { width: 200px; height: 48px; font-size: 17px; border-radius: var(--radius-full); font-weight: 600; }

.history { margin-top: 48px; text-align: left; }
.history-title { font-size: 15px; font-weight: 600; margin-bottom: 14px; }
.history-item {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  margin-bottom: 6px;
  font-size: 13px;
  transition: all var(--transition-fast);
}
.history-item:hover { box-shadow: var(--shadow-sm); }
.h-date { flex: 1; color: var(--text-regular); }
.h-duration { margin-right: 14px; color: var(--text-secondary); }
.h-done { color: var(--color-success); font-weight: 500; }
.h-fail { color: var(--color-danger); }

.picker-area { padding: 30px 0; }
.picker-label { font-size: 16px; color: var(--text-primary); margin-bottom: 24px; font-weight: 500; }
.picker-row { display: flex; justify-content: center; gap: 40px; margin-bottom: 20px; }
.picker-title { font-size: 13px; color: var(--text-secondary); margin-bottom: 10px; font-weight: 500; }
.picker-scroll { max-height: 240px; overflow-y: auto; border: 1px solid var(--border-light); border-radius: var(--radius-md); background: var(--bg-card); }
.picker-item {
  padding: 10px 28px;
  cursor: pointer;
  font-size: 15px;
  color: var(--text-regular);
  transition: all var(--transition-fast);
  user-select: none;
}
.picker-item:hover { background: var(--bg-card-hover); }
.picker-item.active { background: var(--color-primary-bg); color: var(--color-primary); font-weight: 600; }
.picker-result { font-size: 15px; color: var(--color-primary); font-weight: 600; margin-bottom: 24px; }
.picker-actions { display: flex; justify-content: center; gap: 12px; }

.focusing-page { padding: 40px 0; text-align: center; }
.focusing-timer {
  font-size: 64px;
  font-weight: 200;
  font-family: var(--font-mono);
  margin-bottom: 20px;
  font-variant-numeric: tabular-nums;
}
.focusing-progress {
  width: 260px;
  height: 6px;
  background: var(--border-light);
  border-radius: var(--radius-full);
  margin: 0 auto 28px;
  overflow: hidden;
}
.fp-bar { height: 100%; background: linear-gradient(90deg, var(--color-primary), var(--color-success)); border-radius: var(--radius-full); transition: width 0.3s linear; }
.focusing-hint { font-size: 16px; color: var(--text-primary); margin-bottom: 8px; }
.focusing-sub { font-size: 13px; color: var(--color-warning); }

.done-area { padding: 40px 0; animation: fadeIn 0.5s ease; }
.done-icon { font-size: 64px; margin-bottom: 16px; }
.done-title { font-size: 28px; color: var(--text-primary); font-weight: 700; margin-bottom: 16px; }
.done-reward { font-size: 18px; color: var(--text-regular); margin-bottom: 12px; }
.reward-sausage { color: var(--color-warning); font-weight: 700; }
.done-total { font-size: 14px; color: var(--text-secondary); margin-bottom: 28px; }
</style>
