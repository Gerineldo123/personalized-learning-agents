import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface SausageSkinDef {
  id: string
  name: string
  unlockMinutes: number
  fill: string
  stroke: string
  accent: string
  dots?: { cx: number; cy: number; r: number; fill: string }[]
  lines?: { d: string; stroke: string; width: number }[]
  encouragement: string
  unlockText: string
}

export const SAUSAGE_SKINS: SausageSkinDef[] = [
  {
    id: 'original',
    name: '原味淀粉肠',
    unlockMinutes: 0,
    fill: '#F9B89A',
    stroke: '#E8A07A',
    accent: '#DBA878',
    encouragement: '经典原味，百吃不腻！',
    unlockText: '获得基础皮肤：原味淀粉肠',
  },
  {
    id: 'spicy',
    name: '麻辣淀粉肠',
    unlockMinutes: 5,
    fill: '#E87461',
    stroke: '#D1553F',
    accent: '#C0392B',
    dots: [
      { cx: 30, cy: 28, r: 1.5, fill: '#A93226' },
      { cx: 48, cy: 34, r: 1.2, fill: '#A93226' },
      { cx: 38, cy: 46, r: 1.8, fill: '#A93226' },
      { cx: 52, cy: 48, r: 1.4, fill: '#A93226' },
      { cx: 28, cy: 42, r: 1, fill: '#A93226' },
    ],
    encouragement: '够辣够劲，学习就要这么燃！',
    unlockText: '解锁麻辣淀粉肠！火辣口感，刺激你的学习欲望',
  },
  {
    id: 'cumin',
    name: '孜然淀粉肠',
    unlockMinutes: 10,
    fill: '#E8C89A',
    stroke: '#D4A86A',
    accent: '#B8864A',
    dots: [
      { cx: 34, cy: 26, r: 1, fill: '#8B6914' },
      { cx: 46, cy: 30, r: 0.8, fill: '#8B6914' },
      { cx: 28, cy: 38, r: 1.2, fill: '#8B6914' },
      { cx: 50, cy: 44, r: 0.9, fill: '#8B6914' },
      { cx: 40, cy: 50, r: 1.1, fill: '#8B6914' },
      { cx: 54, cy: 38, r: 0.7, fill: '#8B6914' },
    ],
    encouragement: '孜然飘香，越学越有味！',
    unlockText: '解锁孜然淀粉肠！香气扑鼻，充满异域风情',
  },
  {
    id: 'five-spice',
    name: '五香淀粉肠',
    unlockMinutes: 30,
    fill: '#C9A882',
    stroke: '#B08A5E',
    accent: '#8B6F45',
    dots: [
      { cx: 32, cy: 30, r: 1.5, fill: '#6B4F2E' },
      { cx: 46, cy: 28, r: 1, fill: '#6B4F2E' },
      { cx: 38, cy: 40, r: 1.3, fill: '#6B4F2E' },
      { cx: 52, cy: 42, r: 0.8, fill: '#6B4F2E' },
      { cx: 30, cy: 48, r: 1.1, fill: '#6B4F2E' },
      { cx: 50, cy: 34, r: 0.9, fill: '#6B4F2E' },
      { cx: 42, cy: 52, r: 1.2, fill: '#6B4F2E' },
    ],
    encouragement: '五香俱全，知识全面！',
    unlockText: '解锁五香淀粉肠！五种香料，品味学习的丰富多彩',
  },
  {
    id: 'black-pepper',
    name: '黑椒淀粉肠',
    unlockMinutes: 60,
    fill: '#B89A8A',
    stroke: '#7A5A4A',
    accent: '#5A3A2A',
    dots: [
      { cx: 30, cy: 26, r: 2, fill: '#1A1A1A' },
      { cx: 48, cy: 30, r: 1.5, fill: '#1A1A1A' },
      { cx: 36, cy: 38, r: 1.8, fill: '#1A1A1A' },
      { cx: 52, cy: 40, r: 1.3, fill: '#1A1A1A' },
      { cx: 28, cy: 44, r: 1.6, fill: '#1A1A1A' },
      { cx: 44, cy: 50, r: 1.4, fill: '#1A1A1A' },
      { cx: 54, cy: 48, r: 1, fill: '#1A1A1A' },
      { cx: 34, cy: 52, r: 1.2, fill: '#1A1A1A' },
    ],
    encouragement: '黑椒浓郁，知识厚重！',
    unlockText: '解锁黑椒淀粉肠！浓郁黑椒，品味学习的醇厚滋味',
  },
  {
    id: 'crispy',
    name: '脆皮淀粉肠',
    unlockMinutes: 180,
    fill: '#F0C878',
    stroke: '#D4A84A',
    accent: '#B89030',
    lines: [
      { d: 'M28 22 Q34 18 40 20', stroke: '#D4A84A', width: 1.2 },
      { d: 'M44 22 Q50 20 54 24', stroke: '#D4A84A', width: 1.2 },
      { d: 'M24 32 Q28 28 34 30', stroke: '#D4A84A', width: 1 },
      { d: 'M48 30 Q52 28 56 32', stroke: '#D4A84A', width: 1 },
      { d: 'M22 44 Q28 40 34 42', stroke: '#D4A84A', width: 1 },
      { d: 'M46 42 Q52 40 56 44', stroke: '#D4A84A', width: 1 },
    ],
    encouragement: '金黄酥脆，学霸专属！',
    unlockText: '解锁脆皮淀粉肠！金黄酥脆，学习达人就是你',
  },
]

export const useSausageSkinStore = defineStore('sausageSkin', () => {
  const unlockedSkins = ref<string[]>(['original'])
  const selectedSkin = ref('original')
  const newUnlockQueue = ref<string[]>([])

  const totalFocusMinutes = computed(() => {
    try {
      const raw = localStorage.getItem('focus-sessions')
      if (!raw) return 0
      const sessions = JSON.parse(raw)
      return sessions.reduce((sum: number, s: any) => sum + (s.minutes || 0), 0)
    } catch {
      return 0
    }
  })

  const currentSkin = computed(() => {
    return SAUSAGE_SKINS.find(s => s.id === selectedSkin.value) || SAUSAGE_SKINS[0]
  })

  function loadFromStorage() {
    const saved = localStorage.getItem('sausage-unlocked-skins')
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length > 0) {
          unlockedSkins.value = parsed
        }
      } catch {}
    }
    const selected = localStorage.getItem('sausage-selected-skin')
    if (selected && unlockedSkins.value.includes(selected)) {
      selectedSkin.value = selected
    }
  }

  function saveToStorage() {
    localStorage.setItem('sausage-unlocked-skins', JSON.stringify(unlockedSkins.value))
    localStorage.setItem('sausage-selected-skin', selectedSkin.value)
  }

  function selectSkin(id: string) {
    if (unlockedSkins.value.includes(id)) {
      selectedSkin.value = id
      saveToStorage()
    }
  }

  function checkUnlocks(): string[] {
    const total = totalFocusMinutes.value
    const newlyUnlocked: string[] = []
    for (const skin of SAUSAGE_SKINS) {
      if (skin.unlockMinutes > 0 && total >= skin.unlockMinutes && !unlockedSkins.value.includes(skin.id)) {
        unlockedSkins.value.push(skin.id)
        newlyUnlocked.push(skin.id)
      }
    }
    if (newlyUnlocked.length > 0) {
      saveToStorage()
      newUnlockQueue.value = [...newlyUnlocked]
    }
    return newlyUnlocked
  }

  function popUnlockQueue(): string[] {
    const queue = [...newUnlockQueue.value]
    newUnlockQueue.value = []
    return queue
  }

  function clearNewUnlocks() {
    newUnlockQueue.value = []
  }

  loadFromStorage()

  return {
    unlockedSkins,
    selectedSkin,
    newUnlockQueue,
    totalFocusMinutes,
    currentSkin,
    loadFromStorage,
    saveToStorage,
    selectSkin,
    checkUnlocks,
    popUnlockQueue,
    clearNewUnlocks,
  }
})
