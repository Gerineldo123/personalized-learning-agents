<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useFocusStore } from '../stores/focus'

const focusStore = useFocusStore()

const totalMinutes = computed(() =>
  focusStore.focusSessions.reduce((sum, session) => sum + session.minutes, 0),
)
const completedSessions = computed(() =>
  focusStore.focusSessions.filter(session => session.completed).length,
)
const interruptedSessions = computed(() =>
  focusStore.focusSessions.filter(session => !session.completed).length,
)
const todayMinutes = computed(() => {
  const today = new Date().toDateString()
  return focusStore.focusSessions
    .filter(session => new Date(session.date).toDateString() === today)
    .reduce((sum, session) => sum + session.minutes, 0)
})
const completionRate = computed(() => {
  const total = focusStore.focusSessions.length
  if (!total) return 0
  return Math.round((completedSessions.value / total) * 100)
})

onMounted(() => {
  focusStore.init()
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
  if (minutes < 60) return `${Math.round(minutes)} 分钟`
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return m > 0 ? `${h} 小时 ${m} 分钟` : `${h} 小时`
}

function formatTotalTime(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)} 分钟`
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return m > 0 ? `${h} 小时 ${m} 分钟` : `${h} 小时`
}

function selectedDurationText() {
  const h = Math.floor(focusStore.focusMinutes / 60)
  const m = focusStore.focusMinutes % 60
  if (h && m) return `${h} 小时 ${m} 分钟`
  if (h) return `${h} 小时`
  return `${m} 分钟`
}
</script>

<template>
  <div class="focus-view">
    <section class="focus-hero">
      <div>
        <p class="eyebrow">Focus Growth</p>
        <h1>专注成长</h1>
        <p class="hero-desc">记录学习专注时长、完成率和中断情况，用行为数据支撑学习效果评估。</p>
      </div>
      <el-button type="primary" size="large" @click="focusStore.openTimePicker">
        开始专注
      </el-button>
    </section>

    <section class="stats-grid">
      <div class="stat-card">
        <span class="stat-label">累计专注</span>
        <strong>{{ formatTotalTime(totalMinutes) }}</strong>
      </div>
      <div class="stat-card">
        <span class="stat-label">今日专注</span>
        <strong>{{ formatTotalTime(todayMinutes) }}</strong>
      </div>
      <div class="stat-card">
        <span class="stat-label">完成次数</span>
        <strong>{{ completedSessions }}</strong>
      </div>
      <div class="stat-card">
        <span class="stat-label">完成率</span>
        <strong>{{ completionRate }}%</strong>
      </div>
    </section>

    <section v-if="focusStore.state === 'idle'" class="panel">
      <div class="panel-head">
        <h2>专注记录</h2>
        <span>中断 {{ interruptedSessions }} 次</span>
      </div>
      <div v-if="focusStore.focusSessions.length" class="history-list">
        <div v-for="(session, index) in focusStore.focusSessions" :key="index" class="history-item">
          <div>
            <strong>{{ formatDuration(session.minutes) }}</strong>
            <span>{{ formatDate(session.date) }}</span>
          </div>
          <el-tag :type="session.completed ? 'success' : 'warning'" size="small">
            {{ session.completed ? '已完成' : '已中断' }}
          </el-tag>
        </div>
      </div>
      <el-empty v-else description="暂无专注记录" />
    </section>

    <section v-if="focusStore.state === 'selecting'" class="panel picker-panel">
      <h2>选择专注时长</h2>
      <div class="duration-presets">
        <button
          v-for="minutes in [15, 25, 45, 60, 90, 120]"
          :key="minutes"
          :class="{ active: focusStore.focusMinutes === minutes }"
          @click="focusStore.focusMinutes = minutes; focusStore.focusSeconds = 0"
        >
          {{ minutes < 60 ? `${minutes} 分钟` : `${minutes / 60} 小时` }}
        </button>
      </div>
      <p class="selected-duration">已选择：{{ selectedDurationText() }}</p>
      <div class="picker-actions">
        <el-button @click="focusStore.backToIdle">取消</el-button>
        <el-button type="primary" @click="focusStore.startFocus">开始专注</el-button>
      </div>
    </section>

    <section v-if="focusStore.state === 'focusing'" class="panel focusing-panel">
      <p class="focus-state">专注中</p>
      <div class="timer">
        {{ String(focusStore.displayMinutes).padStart(2, '0') }}:{{ String(focusStore.displaySeconds).padStart(2, '0') }}
      </div>
      <el-progress :percentage="Math.round(focusStore.focusProgress)" />
      <p class="focus-tip">请保持当前页面与全屏状态。离开页面会记录为一次中断。</p>
    </section>

    <section v-if="focusStore.state === 'completed'" class="panel completed-panel">
      <div class="done-icon">✓</div>
      <h2>本次专注已完成</h2>
      <p>累计专注 {{ formatTotalTime(totalMinutes) }}，继续保持稳定的学习节奏。</p>
      <el-button type="primary" size="large" @click="focusStore.backToIdle">返回统计</el-button>
    </section>
  </div>
</template>

<style scoped>
.focus-view {
  max-width: 1120px;
  margin: 0 auto;
  padding: 8px 20px 34px;
}

.focus-hero {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: center;
  padding: 28px;
  border: 1px solid #EFE6DC;
  border-radius: 18px;
  background: linear-gradient(135deg, #FFFBF5 0%, #FFF3E4 100%);
  box-shadow: 0 10px 28px rgba(58, 51, 46, 0.08);
}

.eyebrow {
  margin: 0 0 6px;
  color: #DBA878;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.focus-hero h1 {
  margin: 0;
  color: #3A332E;
  font-size: 28px;
}

.hero-desc {
  margin: 8px 0 0;
  color: #6B635C;
  line-height: 1.7;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin: 18px 0;
}

.stat-card {
  padding: 18px;
  border: 1px solid #EFE6DC;
  border-radius: 14px;
  background: #FFFBF5;
}

.stat-label {
  display: block;
  margin-bottom: 8px;
  color: #948A80;
  font-size: 13px;
}

.stat-card strong {
  color: #3A332E;
  font-size: 22px;
}

.panel {
  padding: 22px;
  border: 1px solid #EFE6DC;
  border-radius: 16px;
  background: #FFFBF5;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.panel h2 {
  margin: 0;
  color: #3A332E;
  font-size: 18px;
}

.panel-head span {
  color: #948A80;
  font-size: 13px;
}

.history-list {
  display: grid;
  gap: 10px;
}

.history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid #F1E3D6;
  border-radius: 12px;
  background: #FFFFFF;
}

.history-item strong {
  display: block;
  color: #3A332E;
}

.history-item span {
  color: #948A80;
  font-size: 12px;
}

.picker-panel {
  text-align: center;
}

.duration-presets {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin: 20px 0;
}

.duration-presets button {
  min-width: 96px;
  padding: 10px 14px;
  border: 1px solid #EFE6DC;
  border-radius: 12px;
  background: #FFFFFF;
  color: #6B635C;
  cursor: pointer;
}

.duration-presets button.active {
  border-color: #DBA878;
  background: rgba(249, 217, 184, 0.45);
  color: #3A332E;
  font-weight: 700;
}

.selected-duration {
  color: #6B635C;
}

.picker-actions {
  display: flex;
  justify-content: center;
  gap: 10px;
}

.focusing-panel,
.completed-panel {
  text-align: center;
}

.focus-state {
  color: #DBA878;
  font-weight: 700;
}

.timer {
  margin: 12px 0 18px;
  color: #3A332E;
  font-size: 56px;
  font-weight: 800;
  letter-spacing: 0.06em;
}

.focus-tip,
.completed-panel p {
  color: #6B635C;
}

.done-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 12px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(103, 194, 58, 0.12);
  color: #67C23A;
  font-size: 36px;
  font-weight: 800;
}

@media (max-width: 900px) {
  .focus-hero {
    align-items: flex-start;
    flex-direction: column;
  }
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
