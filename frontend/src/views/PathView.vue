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

/* Focusing page */
.focusing-page { padding: 40px 0; text-align: center; }
.focusing-timer {
  font-size: 56px;
  font-weight: 200;
  font-family: 'Menlo', 'Consolas', monospace;
  color: #303133;
  margin-bottom: 16px;
}
.focusing-progress {
  width: 260px;
  height: 6px;
  background: #e4e7ed;
  border-radius: 3px;
  margin: 0 auto 24px;
  overflow: hidden;
}
.fp-bar {
  height: 100%;
  background: #67c23a;
  border-radius: 3px;
  transition: width 0.3s linear;
}
.focusing-hint { font-size: 16px; color: #303133; margin-bottom: 8px; }
.focusing-sub { font-size: 13px; color: #e6a23c; }

/* Completed */
.done-area { padding: 40px 0; }
.done-icon { font-size: 60px; margin-bottom: 12px; }
.done-title { font-size: 24px; color: #303133; font-weight: 700; margin-bottom: 16px; }
.done-reward { font-size: 18px; color: #606266; margin-bottom: 8px; }
.reward-sausage { color: #e6a23c; font-weight: 700; }
.done-total { font-size: 14px; color: #909399; margin-bottom: 24px; }
</style>
