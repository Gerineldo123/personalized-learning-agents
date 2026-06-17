<script setup lang="ts">
import { computed } from 'vue'
import { SAUSAGE_SKINS, useSausageSkinStore } from '../stores/sausageSkin'
import type { SausageSkinDef } from '../stores/sausageSkin'

const props = withDefaults(defineProps<{
  text?: string
  size?: number
  skin?: string
  outline?: boolean
}>(), { text: '加载中...', size: 48, outline: false })

const skinStore = useSausageSkinStore()

const resolvedSkin = computed<SausageSkinDef>(() => {
  if (props.skin) {
    return SAUSAGE_SKINS.find(s => s.id === props.skin) || SAUSAGE_SKINS[0]
  }
  return skinStore.currentSkin
})
</script>

<template>
  <div class="loading-sausage">
    <svg
      :width="size" :height="size"
      viewBox="0 0 48 48" fill="none"
      xmlns="http://www.w3.org/2000/svg"
      class="sa-spin"
    >
      <path
        d="M10 34 C8 28, 12 18, 20 13 C28 8, 40 10, 42 18 C44 26, 36 34, 28 36 C20 38, 12 40, 10 34Z"
        :fill="props.outline ? 'transparent' : resolvedSkin.fill"
        :stroke="props.outline ? '#D9CBB8' : resolvedSkin.stroke"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <circle
        v-for="(dot, i) in resolvedSkin.dots || []"
        :key="'dot-' + i"
        :cx="dot.cx * 0.6 + 4"
        :cy="dot.cy * 0.6 + 2"
        :r="dot.r * 0.6"
        :fill="props.outline ? 'transparent' : dot.fill"
      />
      <path
        v-for="(line, i) in resolvedSkin.lines || []"
        :key="'line-' + i"
        :d="line.d"
        :stroke="props.outline ? '#D9CBB8' : line.stroke"
        :stroke-width="line.width"
        stroke-linecap="round"
        fill="none"
      />
      <path
        d="M13 30 Q15 28 18 24"
        :stroke="props.outline ? '#D9CBB8' : resolvedSkin.accent"
        stroke-width="1.5"
        stroke-linecap="round"
        fill="none"
      />
    </svg>
    <span v-if="text" class="sa-text">{{ text }}</span>
  </div>
</template>

<style scoped>
.loading-sausage {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
}

.sa-spin {
  animation: saSpin 1.8s ease-in-out infinite;
}

@keyframes saSpin {
  0% { transform: rotate(0deg) scale(1); }
  25% { transform: rotate(10deg) scale(1.05); }
  50% { transform: rotate(0deg) scale(1); }
  75% { transform: rotate(-10deg) scale(1.05); }
  100% { transform: rotate(0deg) scale(1); }
}

.sa-text {
  font-size: 13px;
  color: #948A80;
  animation: saPulse 1.8s ease-in-out infinite;
}

@keyframes saPulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}
</style>
