<template>
  <div class="slider-captcha">
    <div class="slider-track" ref="trackRef" :class="{ verified: isVerified }">
      <div class="slider-fill" :style="{ width: sliderValue + '%' }"></div>
      <div class="slider-text">
        <span v-if="isVerified">✓ 验证成功</span>
        <span v-else>滑动完成验证</span>
      </div>
      <div 
        class="slider-handle" 
        :class="{ verified: isVerified, dragging: isDragging }"
        :style="{ left: `calc(${sliderValue}% - ${sliderValue * 0.36}px)` }"
        @mousedown="handleMouseDown"
        @touchstart="handleTouchStart"
      >
        <svg v-if="isVerified" width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M4 8L7 11L12 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <svg v-else width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M6 4L10 8L6 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue'

const props = defineProps<{
  modelValue?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const trackRef = ref<HTMLElement>()
const sliderValue = ref(0)
const isDragging = ref(false)
const isVerified = ref(false)

let startX = 0
let startLeft = 0

const handleMouseDown = (e: MouseEvent) => {
  if (isVerified.value) return
  isDragging.value = true
  startX = e.clientX
  startLeft = sliderValue.value
  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', handleMouseUp)
  e.preventDefault()
}

const handleMouseMove = (e: MouseEvent) => {
  if (!isDragging.value) return
  const deltaX = e.clientX - startX
  const trackWidth = trackRef.value?.offsetWidth || 260
  const newValue = Math.max(0, Math.min(100, (startLeft * trackWidth / 100 + deltaX) / trackWidth * 100))
  sliderValue.value = newValue
  
  if (newValue >= 95 && !isVerified.value) {
    sliderValue.value = 100
    isVerified.value = true
    emit('update:modelValue', true)
    handleMouseUp()
  }
}

const handleMouseUp = () => {
  isDragging.value = false
  document.removeEventListener('mousemove', handleMouseMove)
  document.removeEventListener('mouseup', handleMouseUp)
  
  if (!isVerified.value) {
    const animateReset = () => {
      if (sliderValue.value > 0) {
        sliderValue.value = Math.max(0, sliderValue.value - 10)
        requestAnimationFrame(animateReset)
      }
    }
    animateReset()
  }
}

const handleTouchStart = (e: TouchEvent) => {
  if (isVerified.value) return
  isDragging.value = true
  startX = e.touches[0].clientX
  startLeft = sliderValue.value
  document.addEventListener('touchmove', handleTouchMove, { passive: false })
  document.addEventListener('touchend', handleTouchEnd)
  e.preventDefault()
}

const handleTouchMove = (e: TouchEvent) => {
  if (!isDragging.value) return
  e.preventDefault()
  const deltaX = e.touches[0].clientX - startX
  const trackWidth = trackRef.value?.offsetWidth || 260
  const newValue = Math.max(0, Math.min(100, (startLeft * trackWidth / 100 + deltaX) / trackWidth * 100))
  sliderValue.value = newValue
  
  if (newValue >= 95 && !isVerified.value) {
    sliderValue.value = 100
    isVerified.value = true
    emit('update:modelValue', true)
    handleTouchEnd()
  }
}

const handleTouchEnd = () => {
  isDragging.value = false
  document.removeEventListener('touchmove', handleTouchMove)
  document.removeEventListener('touchend', handleTouchEnd)
  
  if (!isVerified.value) {
    sliderValue.value = 0
  }
}

const reset = () => {
  sliderValue.value = 0
  isVerified.value = false
  isDragging.value = false
  emit('update:modelValue', false)
}

defineExpose({
  reset
})

onUnmounted(() => {
  document.removeEventListener('mousemove', handleMouseMove)
  document.removeEventListener('mouseup', handleMouseUp)
  document.removeEventListener('touchmove', handleTouchMove)
  document.removeEventListener('touchend', handleTouchEnd)
})
</script>

<style scoped>
.slider-captcha {
  width: 100%;
  user-select: none;
}

.slider-track {
  position: relative;
  width: 100%;
  height: 50px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.slider-track.verified {
  background: rgba(56, 239, 125, 0.08);
  border-color: rgba(56, 239, 125, 0.25);
}

.slider-fill {
  position: absolute;
  left: 0;
  top: 0;
  height: 100%;
  background: rgba(102, 126, 234, 0.1);
  transition: none;
  z-index: 1;
}

.slider-track.verified .slider-fill {
  background: rgba(56, 239, 125, 0.1);
}

.slider-text {
  position: relative;
  z-index: 2;
  font-size: 13px;
  color: var(--text-quaternary);
  transition: color 0.2s;
}

.slider-track.verified .slider-text {
  color: var(--success);
  font-weight: 500;
}

.slider-handle {
  position: absolute;
  top: 6px;
  left: 0;
  width: 38px;
  height: 38px;
  background: var(--gradient-primary);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  cursor: grab;
  z-index: 3;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.4);
  transition: transform 0.1s, box-shadow 0.1s, background 0.2s;
}

.slider-handle:hover {
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.5);
}

.slider-handle.dragging {
  cursor: grabbing;
  transform: scale(0.95);
}

.slider-handle.verified {
  background: var(--gradient-emerald);
  box-shadow: 0 2px 8px rgba(56, 239, 125, 0.4);
  cursor: default;
}
</style>
