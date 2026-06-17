<script setup lang="ts">
import { ref, watch } from 'vue'
import { SAUSAGE_SKINS, useSausageSkinStore } from '../stores/sausageSkin'
import SausageIcon from './SausageIcon.vue'

const skinStore = useSausageSkinStore()

const props = defineProps<{
  skinIds?: string[]
  previewSkin?: { id: string; locked: boolean } | null
}>()

const emit = defineEmits<{
  done: []
  close: []
}>()

const currentIndex = ref(0)
const visible = ref(false)
const leaving = ref(false)

watch(() => props.skinIds, (ids) => {
  if (ids && ids.length > 0) {
    currentIndex.value = 0
    visible.value = true
    leaving.value = false
  }
}, { immediate: true })

watch(() => props.previewSkin, (skin) => {
  if (skin) {
    visible.value = true
    leaving.value = false
  } else {
    visible.value = false
  }
})

function currentSkin() {
  const preview = props.previewSkin
  if (preview) {
    return SAUSAGE_SKINS.find(s => s.id === preview.id) || SAUSAGE_SKINS[0]
  }
  const ids = props.skinIds
  if (ids && ids.length > 0) {
    return SAUSAGE_SKINS.find(s => s.id === ids[currentIndex.value]) || SAUSAGE_SKINS[0]
  }
  return SAUSAGE_SKINS[0]
}

function isPreviewMode(): boolean {
  return !!props.previewSkin
}

function isLockedPreview(): boolean {
  return props.previewSkin?.locked === true
}

function switchSkin() {
  const skin = currentSkin()
  skinStore.selectSkin(skin.id)
  close()
}

function next() {
  if (props.skinIds && currentIndex.value < props.skinIds.length - 1) {
    currentIndex.value++
  } else {
    close()
  }
}

function close() {
  leaving.value = true
  setTimeout(() => {
    visible.value = false
    leaving.value = false
    emit('close')
    emit('done')
  }, 500)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="skin-unlock-overlay" :class="{ 'skin-unlock-leave': leaving }" @click.self="close">
      <div class="skin-unlock-card" :class="{ 'skin-unlock-card-leave': leaving, 'skin-preview-card': isPreviewMode() }" :key="currentIndex + (previewSkin?.id || '')">
        <button class="skin-close-btn" @click="close">✕</button>

        <!-- New unlock mode -->
        <template v-if="!isPreviewMode()">
          <div class="skin-unlock-sparkle">✦</div>
          <div class="skin-unlock-icon">
            <SausageIcon :size="100" :skin="currentSkin().id" />
          </div>
          <div class="skin-unlock-title">解锁新皮肤！</div>
          <div class="skin-unlock-name">{{ currentSkin().name }}</div>
          <div class="skin-unlock-text">{{ currentSkin().unlockText }}</div>
          <div class="skin-unlock-encourage">{{ currentSkin().encouragement }}</div>
          <div class="skin-unlock-actions">
            <el-button
              class="skin-switch-btn"
              size="large"
              @click="switchSkin"
            >
              更换成该皮肤
            </el-button>
            <el-button
              type="primary"
              size="large"
              class="skin-next-btn"
              @click="next"
            >
              {{ skinIds && currentIndex < skinIds.length - 1 ? '下一个 >>' : '太棒了！' }}
            </el-button>
          </div>
        </template>

        <!-- Preview unlocked mode -->
        <template v-else-if="!isLockedPreview()">
          <div class="skin-unlock-sparkle">✦</div>
          <div class="skin-unlock-icon">
            <SausageIcon :size="100" :skin="currentSkin().id" />
          </div>
          <div class="skin-unlock-title">已解锁皮肤</div>
          <div class="skin-unlock-name">{{ currentSkin().name }}</div>
          <div class="skin-unlock-encourage" style="margin-bottom:24px">{{ currentSkin().encouragement }}</div>
          <el-button
            class="skin-switch-btn skin-switch-btn-full"
            size="large"
            @click="switchSkin"
          >
            {{ skinStore.selectedSkin === currentSkin().id ? '当前使用中' : '更换成该皮肤' }}
          </el-button>
        </template>

        <!-- Preview locked mode -->
        <template v-else>
          <div class="skin-unlock-icon">
            <SausageIcon :size="100" :skin="currentSkin().id" outline />
          </div>
          <div class="skin-unlock-name" style="color:#948A80">{{ currentSkin().name }}</div>
          <div class="skin-unlock-title" style="font-size:18px;margin-bottom:12px">尚未解锁</div>
          <div class="skin-unlock-text">继续专注 {{ currentSkin().unlockMinutes }} 分钟即可解锁该皮肤</div>
          <div class="skin-unlock-encourage">{{ currentSkin().encouragement }}</div>
          <el-button
            type="primary"
            size="large"
            class="skin-next-btn"
            @click="close"
          >
            知道了
          </el-button>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.skin-unlock-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: unlockFadeIn 0.3s ease;
}

.skin-unlock-leave {
  animation: unlockFadeOut 0.5s ease forwards;
}

.skin-unlock-card {
  background: linear-gradient(180deg, #FFF5EB 0%, #FFFBF5 100%);
  border: 2px solid #F9D9B8;
  border-radius: 24px;
  padding: 40px 36px 32px;
  text-align: center;
  max-width: 360px;
  width: 90%;
  position: relative;
  animation: unlockPopIn 0.5s cubic-bezier(0.2, 0.75, 0.22, 1);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.skin-preview-card {
  padding: 32px 36px 28px;
}

.skin-unlock-card-leave {
  animation: unlockPopOut 0.5s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}

.skin-close-btn {
  position: absolute;
  top: 12px;
  right: 14px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: none;
  background: rgba(0,0,0,0.06);
  color: #948A80;
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
  line-height: 1;
}

.skin-close-btn:hover {
  background: rgba(0,0,0,0.12);
  color: #6B635C;
}

.skin-unlock-sparkle {
  font-size: 36px;
  color: #F9D9B8;
  margin-bottom: 8px;
  animation: sparkleSpin 1.5s ease-in-out infinite;
}

.skin-unlock-icon {
  margin-bottom: 16px;
}

.skin-unlock-title {
  font-size: 13px;
  color: #948A80;
  margin-bottom: 6px;
  letter-spacing: 2px;
}

.skin-unlock-name {
  font-size: 22px;
  font-weight: 700;
  color: #3A332E;
  margin-bottom: 12px;
}

.skin-unlock-text {
  font-size: 14px;
  color: #6B635C;
  line-height: 1.6;
  margin-bottom: 8px;
}

.skin-unlock-encourage {
  font-size: 15px;
  color: #DBA878;
  font-weight: 500;
  margin-bottom: 24px;
}

.skin-unlock-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skin-switch-btn {
  background: transparent;
  color: #DBA878;
  border: 1.5px solid #F9D9B8;
  border-radius: 8px;
  font-weight: 600;
  width: 100%;
}

.skin-switch-btn:hover {
  background: rgba(249,217,184,0.1);
  color: #DBA878;
  border-color: #DBA878;
}

.skin-switch-btn-full {
  width: 100%;
}

.skin-next-btn {
  background: #F9D9B8;
  color: #3A332E;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  width: 100%;
}

.skin-next-btn:hover {
  background: #F0C8A0;
  color: #3A332E;
}

@keyframes unlockFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes unlockFadeOut {
  from { opacity: 1; }
  to { opacity: 0; }
}

@keyframes unlockPopIn {
  from { opacity: 0; transform: scale(0.5) translateY(30px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

@keyframes unlockPopOut {
  from { opacity: 1; transform: scale(1) translateY(0); }
  to { opacity: 0; transform: scale(0.8) translateY(-20px); }
}

@keyframes sparkleSpin {
  0%, 100% { transform: rotate(0deg) scale(1); }
  50% { transform: rotate(180deg) scale(1.2); }
}
</style>
