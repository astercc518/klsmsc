<template>
  <div class="agent-layout">
    <header class="app-header">
      <div class="header-left">
        <div class="logo">
          <span class="logo-text">SMSC Agent Workspace</span>
        </div>
      </div>
      
      <div class="header-right">
        <!-- 软电话快捷呼出 -->
        <div class="softphone-trigger" :class="{ 'is-active': phoneStore.isVisible }" @click="toggleSoftPhone" title="软电话">
          <el-icon><Microphone /></el-icon>
        </div>

        <!-- 语言切换 -->
        <el-dropdown trigger="click" @command="handleLanguageChange" class="lang-dropdown">
          <span class="el-dropdown-link">
            <el-icon><Location /></el-icon>
            {{ currentLang === 'zh-CN' ? '中文' : 'English' }}
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="zh-CN" :disabled="currentLang === 'zh-CN'">中文</el-dropdown-item>
              <el-dropdown-item command="en-US" :disabled="currentLang === 'en-US'">English</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <el-divider direction="vertical" style="margin: 0 16px" />

        <!-- 用户名与状态切换 -->
        <el-dropdown trigger="click" @command="handleStatusChange" class="user-dropdown">
          <span class="el-dropdown-link user-info">
            <span class="status-dot" :class="agentState"></span>
            {{ extensionNumber }}
            <el-icon class="el-icon--right"><arrow-down /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <div class="dropdown-header">
                {{ $t('voice.agentStateLabel') }}: 
                <span :class="['state-text', agentState]">{{ $t(`voice.agentState.${agentState}`) }}</span>
              </div>
              <el-divider style="margin: 4px 0" />
              <el-dropdown-item command="idle" :disabled="agentState === 'idle'">
                <span class="status-dot idle"></span> {{ $t('voice.agentState.idle') }}
              </el-dropdown-item>
              <el-dropdown-item command="on_break" :disabled="agentState === 'on_break'">
                <span class="status-dot on_break"></span> {{ $t('voice.agentState.on_break') }}
              </el-dropdown-item>
              <el-dropdown-item command="offline" :disabled="agentState === 'offline'">
                <span class="status-dot offline"></span> {{ $t('voice.agentState.offline') }}
              </el-dropdown-item>
              <el-divider style="margin: 4px 0" />
              <el-dropdown-item command="logout">{{ $t('common.logout') }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <main class="app-main">
      <router-view v-slot="{ Component }">
        <transition name="fade-transform" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- 悬浮的 WebRTC 软电话组件 -->
    <SoftPhone />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Microphone, Location, ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import SoftPhone from '@/components/voice/SoftPhone.vue'
import { useVoicePhoneStore } from '@/stores/voice-phone'
import request from '@/api/index'

const router = useRouter()
const { t, locale } = useI18n()
const phoneStore = useVoicePhoneStore()

const currentLang = computed(() => locale.value)
const extensionNumber = ref('Agent')
const agentState = ref('offline')
const extensionRef = ref<any>(null)
let statusPoll: any = null

function handleLanguageChange(lang: string) {
  locale.value = lang
  localStorage.setItem('language', lang)
}

function toggleSoftPhone() {
  phoneStore.toggleVisibility()
}

async function loadAgentProfile() {
  try {
    const res: any = await request.get('/api/v1/agent/voice/me')
    if (res.success && res.extension) {
      extensionNumber.value = res.extension.extension_number
      agentState.value = res.extension.agent_state
      extensionRef.value = res.extension
      
      // Auto connect SIP if idle or break
      phoneStore.setVisible(true)
    }
  } catch (e: any) {
    if (e?.response?.status === 401) {
      handleLogout()
    }
  }
}

async function handleStatusChange(command: string) {
  if (command === 'logout') {
    handleLogout()
    return
  }
  try {
    const res: any = await request.post('/api/v1/agent/voice/status', { state: command })
    if (res.success) {
      agentState.value = res.agent_state
      ElMessage.success(t('voice.updateSuccess'))
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || e.message || t('common.failed'))
  }
}

function handleLogout() {
  localStorage.removeItem('agent_token')
  phoneStore.hangup()
  setTimeout(() => {
    router.replace('/agent/login')
  }, 300)
}

function startPolling() {
  statusPoll = setInterval(loadAgentProfile, 10000)
}

onMounted(() => {
  if (!localStorage.getItem('agent_token')) {
    router.replace('/agent/login')
    return
  }
  loadAgentProfile()
  startPolling()
})

onUnmounted(() => {
  if (statusPoll) clearInterval(statusPoll)
})
</script>

<style scoped>
.agent-layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--el-bg-color-page);
}

.app-header {
  height: 60px;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-light);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
}

.logo {
  display: flex;
  align-items: center;
}

.logo-text {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-color-primary);
  letter-spacing: 0.5px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.softphone-trigger {
  width: 36px;
  height: 36px;
  display: flex;
  justify-content: center;
  align-items: center;
  border-radius: 50%;
  background-color: var(--el-fill-color-light);
  cursor: pointer;
  transition: all 0.3s ease;
  color: var(--el-text-color-secondary);
}

.softphone-trigger:hover {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.softphone-trigger.is-active {
  background-color: var(--el-color-primary);
  color: white;
  box-shadow: 0 2px 8px rgba(var(--el-color-primary-rgb), 0.4);
}

.el-dropdown-link {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--el-text-color-regular);
  font-size: 14px;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.el-dropdown-link:hover {
  background-color: var(--el-fill-color-light);
}

.user-info {
  font-weight: 500;
}

.status-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background-color: #909399; /* offline */
}
.status-dot.idle { background-color: #67C23A; } /* green */
.status-dot.on_break { background-color: #E6A23C; } /* yellow */
.status-dot.dialing, .status-dot.in_call { background-color: #F56C6C; } /* red */
.status-dot.wrap_up { background-color: #409EFF; } /* blue */

.state-text {
  font-weight: 600;
}
.state-text.idle { color: #67C23A; }
.state-text.on_break { color: #E6A23C; }
.state-text.offline { color: #909399; }
.state-text.dialing, .state-text.in_call { color: #F56C6C; }

.dropdown-header {
  padding: 8px 16px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  background-color: var(--el-fill-color-light);
}

.app-main {
  flex: 1;
  overflow: auto;
  position: relative;
}

/* 渐变动画 */
.fade-transform-leave-active,
.fade-transform-enter-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.fade-transform-enter-from {
  opacity: 0;
  transform: translateY(10px);
}
.fade-transform-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
