<script setup lang="ts">
import { ref } from 'vue'

interface Slide {
  title: string
  content: string[]
  notes?: string
}

const props = defineProps<{ content: { title?: string; slides?: Slide[] } }>()
const currentSlide = ref(0)

function prev() {
  if (currentSlide.value > 0) currentSlide.value--
}

function next() {
  if (currentSlide.value < (props.content.slides?.length || 1) - 1) currentSlide.value++
}

const totalSlides = () => props.content.slides?.length || 0
const slide = () => props.content.slides?.[currentSlide.value]
</script>

<template>
  <div class="ppt-viewer">
    <div class="ppt-header">
      <h3>{{ content.title || '课件' }}</h3>
      <span class="slide-count">{{ currentSlide + 1 }} / {{ totalSlides() }}</span>
    </div>

    <div class="slide-area">
      <div class="slide-content" v-if="slide()">
        <h4 class="slide-title">{{ slide()!.title }}</h4>
        <ul class="slide-points">
          <li v-for="(point, i) in slide()!.content" :key="i">{{ point }}</li>
        </ul>
        <div v-if="slide()!.notes" class="slide-notes">
          <el-icon><InfoFilled /></el-icon> {{ slide()!.notes }}
        </div>
      </div>
    </div>

    <div class="ppt-controls">
      <el-button :disabled="currentSlide === 0" @click="prev">上一页</el-button>
      <el-button type="primary" :disabled="currentSlide >= totalSlides() - 1" @click="next">下一页</el-button>
    </div>
  </div>
</template>

<style scoped>
.ppt-viewer {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  overflow: hidden;
}

.ppt-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: #f5f7fa;
  border-bottom: 1px solid #ebeef5;
}

.ppt-header h3 { margin: 0; color: #303133; }

.slide-count {
  font-size: 14px;
  color: #909399;
}

.slide-area {
  min-height: 300px;
  padding: 32px 40px;
}

.slide-title {
  font-size: 20px;
  color: #303133;
  margin-bottom: 24px;
}

.slide-points {
  padding-left: 20px;
}

.slide-points li {
  margin-bottom: 12px;
  line-height: 1.8;
  color: #606266;
}

.slide-notes {
  margin-top: 24px;
  padding: 12px 16px;
  background: #ecf5ff;
  border-left: 3px solid #409eff;
  color: #606266;
  font-size: 13px;
}

.ppt-controls {
  display: flex;
  justify-content: center;
  gap: 16px;
  padding: 16px;
  border-top: 1px solid #ebeef5;
}
</style>
