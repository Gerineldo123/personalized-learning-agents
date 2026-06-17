<script setup lang="ts">
import { computed } from 'vue'
import { SAUSAGE_SKINS, useSausageSkinStore } from '../stores/sausageSkin'
import type { SausageSkinDef } from '../stores/sausageSkin'

const props = withDefaults(defineProps<{
  size?: number
  animate?: boolean
  muted?: boolean
  outline?: boolean
  skin?: string
}>(), { size: 80, animate: false, muted: false, outline: false })

const skinStore = useSausageSkinStore()

const resolvedSkin = computed<SausageSkinDef>(() => {
  if (props.skin) {
    return SAUSAGE_SKINS.find(s => s.id === props.skin) || SAUSAGE_SKINS[0]
  }
  return skinStore.currentSkin
})
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 80 80"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    :class="{ 'sa-bounce': animate }"
  >
    <path
      d="M18 54 C16 46, 22 30, 32 24 C42 18, 56 18, 62 26 C68 34, 64 46, 58 52 C52 58, 40 62, 32 60 C24 58, 20 62, 18 54Z"
      :fill="outline ? 'transparent' : (muted ? '#F5EDE2' : resolvedSkin.fill)"
      :stroke="outline ? '#D9CBB8' : (muted ? '#D9CBB8' : resolvedSkin.stroke)"
      stroke-width="2.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
    <circle
      v-for="(dot, i) in resolvedSkin.dots || []"
      :key="'dot-' + i"
      :cx="dot.cx"
      :cy="dot.cy"
      :r="dot.r"
      :fill="outline ? 'transparent' : (muted ? '#D9CBB8' : dot.fill)"
    />
    <path
      v-for="(line, i) in resolvedSkin.lines || []"
      :key="'line-' + i"
      :d="line.d"
      :stroke="outline ? '#D9CBB8' : (muted ? '#D9CBB8' : line.stroke)"
      :stroke-width="line.width"
      stroke-linecap="round"
      fill="none"
    />
    <path
      d="M22 48 Q26 46 30 40"
      :stroke="outline ? '#D9CBB8' : (muted ? '#D9CBB8' : resolvedSkin.accent)"
      stroke-width="2"
      stroke-linecap="round"
      fill="none"
    />
    <path
      d="M40 32 Q50 30 55 28"
      :stroke="outline ? '#D9CBB8' : (muted ? '#D9CBB8' : resolvedSkin.accent)"
      stroke-width="1.5"
      stroke-linecap="round"
      fill="none"
    />
    <path
      d="M18 54 C16 50 18 44 22 40"
      :stroke="outline ? '#D9CBB8' : (muted ? '#D9CBB8' : resolvedSkin.stroke)"
      stroke-width="2"
      stroke-linecap="round"
      fill="none"
    />
    <path
      d="M58 52 C60 48 62 44 60 38"
      :stroke="outline ? '#D9CBB8' : (muted ? '#D9CBB8' : resolvedSkin.stroke)"
      stroke-width="2"
      stroke-linecap="round"
      fill="none"
    />
  </svg>
</template>

<style scoped>
.sa-bounce {
  animation: saFloat 3s ease-in-out infinite;
}

@keyframes saFloat {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  25% { transform: translateY(-4px) rotate(-2deg); }
  50% { transform: translateY(-2px) rotate(1deg); }
  75% { transform: translateY(-4px) rotate(-1deg); }
}
</style>
