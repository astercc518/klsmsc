<template>
  <div class="soft-phone-container" v-show="phoneStore.isVisible">
    <div class="phone-header">
      <div class="header-status">
        <span class="status-dot" :class="{ online: phoneStore.isRegistered }"></span>
        <span class="status-text">{{ phoneStore.isRegistered ? '已就绪' : '离线' }}</span>
      </div>
      <div class="header-actions">
        <el-icon class="close-icon" @click="phoneStore.setVisible(false)"><Close /></el-icon>
      </div>
    </div>

    <!-- 拨号展示区 -->
    <div class="phone-display">
      <div class="call-info" v-if="phoneStore.callStatus !== 'idle'">
        <div class="call-number">{{ phoneStore.currentNumber }}</div>
        <div class="call-timer">{{ formatDuration(phoneStore.duration) }}</div>
        <div class="call-state">{{ t(`voice.softphone.status.${phoneStore.callStatus}`) }}</div>
      </div>
      <el-input
        v-else
        v-model="phoneStore.currentNumber"
        placeholder="输入号码"
        class="number-input"
        clearable
      >
        <template #prefix>
          <el-icon><Phone /></el-icon>
        </template>
      </el-input>
    </div>

    <!-- 拨号盘 -->
    <div class="dial-pad" v-if="phoneStore.callStatus === 'idle'">
      <div v-for="key in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '*', '0', '#']" 
           :key="key" 
           class="dial-key" 
           @click="appendKey(key)">
        {{ key }}
      </div>
    </div>

    <!-- 通话控制按钮 -->
    <div class="phone-actions">
      <template v-if="phoneStore.callStatus === 'idle'">
        <el-button type="success" size="large" circle @click="handleCall" class="call-btn">
          <el-icon size="24"><PhoneFilled /></el-icon>
        </el-button>
      </template>
      <template v-else-if="phoneStore.callStatus === 'ringing'">
        <div class="active-actions">
          <el-button type="success" size="large" circle @click="handleAnswer">
            <el-icon size="24"><PhoneFilled /></el-icon>
          </el-button>
          <el-button type="danger" size="large" circle @click="handleHangup" class="hangup-btn">
            <el-icon size="24"><PhoneFilled style="transform: rotate(135deg)" /></el-icon>
          </el-button>
        </div>
      </template>
      <template v-else>
        <div class="active-actions">
          <el-button circle size="large" :type="phoneStore.isMuted ? 'warning' : 'info'" @click="toggleMute">
            <el-icon><Mute v-if="phoneStore.isMuted" /><Microphone v-else /></el-icon>
          </el-button>
          <el-button type="danger" size="large" circle @click="handleHangup" class="hangup-btn">
            <el-icon size="24"><PhoneFilled style="transform: rotate(135deg)" /></el-icon>
          </el-button>
          <el-button circle size="large" type="info" @click="toggleHold">
            <el-icon><VideoPause /></el-icon>
          </el-button>
        </div>
      </template>
    </div>

    <!-- 隐藏的音频元素用于播放远程音频 -->
    <audio ref="remoteAudio" autoplay></audio>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Close, Phone, PhoneFilled, Microphone, Mute, VideoPause } from '@element-plus/icons-vue'
import { useVoicePhoneStore } from '@/stores/voice-phone'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const phoneStore = useVoicePhoneStore()

const remoteAudio = ref<HTMLAudioElement | null>(null)

watch(remoteAudio, (newVal) => {
  if (newVal) {
    phoneStore.setRemoteAudio(newVal)
  }
})

function appendKey(key: string) {
  phoneStore.currentNumber += key
}

function handleCall() {
  if (!phoneStore.currentNumber) return
  phoneStore.startCall(phoneStore.currentNumber)
}

function handleAnswer() {
  phoneStore.answer()
}

function handleHangup() {
  phoneStore.hangup()
}

function toggleMute() {
  phoneStore.isMuted = !phoneStore.isMuted
}

function toggleHold() {
  // 保持/取回逻辑
}

function formatDuration(sec: number) {
  const m = Math.floor(sec / 60).toString().padStart(2, '0')
  const s = (sec % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}
</script>

<style scoped>
.soft-phone-container {
  position: fixed;
  right: 20px;
  bottom: 80px;
  width: 280px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.15);
  z-index: 2000;
  overflow: hidden;
  user-select: none;
}

.phone-header {
  height: 40px;
  background: var(--el-fill-color-light);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.header-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #909399;
}
.status-dot.online {
  background: #67c23a;
  box-shadow: 0 0 4px #67c23a;
}

.close-icon {
  cursor: pointer;
  color: var(--el-text-color-secondary);
}
.close-icon:hover {
  color: var(--el-text-color-primary);
}

.phone-display {
  padding: 20px;
  text-align: center;
}

.call-info {
  margin-bottom: 10px;
}
.call-number {
  font-size: 24px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.call-timer {
  font-size: 18px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
}
.call-state {
  font-size: 12px;
  margin-top: 5px;
  color: var(--el-color-primary);
}

.dial-pad {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 0 24px 20px;
}

.dial-key {
  height: 50px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  font-size: 20px;
  cursor: pointer;
  transition: all 0.2s;
}
.dial-key:hover {
  background: var(--el-fill-color-light);
  border-color: var(--el-color-primary-light-5);
}
.dial-key:active {
  background: var(--el-fill-color);
}

.phone-actions {
  padding: 0 20px 24px;
  text-align: center;
}

.active-actions {
  display: flex;
  justify-content: space-around;
  align-items: center;
}

.call-btn {
  width: 60px;
  height: 60px;
}
.hangup-btn {
  width: 60px;
  height: 60px;
}
</style>
