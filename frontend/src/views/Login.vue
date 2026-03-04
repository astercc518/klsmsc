<template>
  <div class="login-page">
    <!-- 背景 -->
    <div class="background">
      <div class="gradient-orb orb-1"></div>
      <div class="gradient-orb orb-2"></div>
      <div class="grid-pattern"></div>
    </div>
    
    <!-- 登录容器 -->
    <div class="login-wrapper">
      <!-- 品牌 -->
      <div class="brand">
        <div class="logo">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <path d="M24 4L44 14V34L24 44L4 34V14L24 4Z" stroke="url(#logo-gradient)" stroke-width="2.5" fill="none"/>
            <circle cx="24" cy="24" r="8" fill="url(#logo-gradient)"/>
            <defs>
              <linearGradient id="logo-gradient" x1="4" y1="4" x2="44" y2="44">
                <stop offset="0%" stop-color="#667EEA"/>
                <stop offset="100%" stop-color="#764BA2"/>
              </linearGradient>
            </defs>
          </svg>
        </div>
        <h1 class="brand-name">SMSPro</h1>
        <p class="brand-desc">{{ $t('login.subtitle') }}</p>
      </div>
      
      <!-- 登录卡片 -->
      <div class="login-card">
        <!-- 登录类型切换 -->
        <div class="login-tabs">
          <button 
            :class="['tab-btn', { active: loginType === 'customer' }]"
            @click="loginType = 'customer'"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="5" r="3" stroke="currentColor" stroke-width="1.5"/>
              <path d="M2 14C2 11.5 4.5 10 8 10C11.5 10 14 11.5 14 14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            {{ $t('login.customerLogin') }}
          </button>
          <button 
            :class="['tab-btn', { active: loginType === 'staff' }]"
            @click="loginType = 'staff'"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="2" y="1" width="12" height="14" rx="2" stroke="currentColor" stroke-width="1.5"/>
              <circle cx="8" cy="5.5" r="2" stroke="currentColor" stroke-width="1.2"/>
              <path d="M5 10.5C5 9.5 6.5 8.5 8 8.5C9.5 8.5 11 9.5 11 10.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
              <path d="M5 13H11" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
            </svg>
            {{ $t('login.staffLogin') }}
          </button>
        </div>

        <el-form 
          :model="form" 
          :rules="rules" 
          ref="formRef" 
          @submit.prevent="handleLogin"
          class="login-form"
        >
          <div class="form-group">
            <label class="form-label">
              {{ loginType === 'customer' ? $t('login.email') : $t('login.username') }}
            </label>
            <el-input
              v-model="form.username"
              :placeholder="loginType === 'customer' ? $t('login.enterEmail') : $t('login.enterStaffUsername')"
              size="large"
              class="form-input"
            >
              <template #prefix>
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <circle cx="9" cy="6" r="4" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M2 16C2 13 5 11 9 11C13 11 16 13 16 16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
              </template>
            </el-input>
          </div>
          
          <div class="form-group">
            <label class="form-label">{{ $t('login.password') }}</label>
            <el-input
              v-model="form.password"
              type="password"
              :placeholder="$t('login.enterPassword')"
              size="large"
              show-password
              class="form-input"
            >
              <template #prefix>
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <rect x="3" y="7" width="12" height="9" rx="2" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M6 7V5C6 3.34 7.34 2 9 2C10.66 2 12 3.34 12 5V7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  <circle cx="9" cy="11.5" r="1.5" fill="currentColor"/>
                </svg>
              </template>
            </el-input>
          </div>
          
          <div class="form-group">
            <SliderCaptcha ref="captchaRef" v-model="captchaVerified" />
          </div>
          
          <button 
            type="submit" 
            class="login-button"
            :disabled="loading"
            @click.prevent="handleLogin"
          >
            <span v-if="!loading">
              {{ loginType === 'customer' ? $t('login.customerLoginBtn') : $t('login.staffLoginBtn') }}
            </span>
            <span v-else class="loading-state">
              <svg class="spinner" width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="7" stroke="currentColor" stroke-width="2" stroke-dasharray="35" stroke-dashoffset="10" stroke-linecap="round"/>
              </svg>
              {{ $t('login.loggingIn') }}
            </span>
          </button>
        </el-form>

        <!-- 角色提示 -->
        <div class="role-hint" v-if="loginType === 'staff'">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <circle cx="7" cy="7" r="6" stroke="currentColor" stroke-width="1.2"/>
            <path d="M7 4V7.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
            <circle cx="7" cy="10" r="0.8" fill="currentColor"/>
          </svg>
          <span>{{ $t('login.roleHint') }}</span>
        </div>
        
        <div class="security-note">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 1L2 3.5V6.5C2 9.5 4 12 7 13C10 12 12 9.5 12 6.5V3.5L7 1Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
            <path d="M5 7L6.5 8.5L9 5.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>{{ $t('login.securityNote') }}</span>
        </div>
      </div>
      
      <!-- 版权 -->
      <p class="copyright">© 2024 SMSPro. All rights reserved.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { adminLogin } from '@/api/admin'
import { login as accountLogin, getAccountInfo } from '@/api/account'
import SliderCaptcha from '@/components/SliderCaptcha.vue'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const formRef = ref<FormInstance>()
const loading = ref(false)
const captchaVerified = ref(false)
const captchaRef = ref<InstanceType<typeof SliderCaptcha>>()
const loginType = ref<'customer' | 'staff'>('customer')

// 初始化主题 & 处理模拟登录
onMounted(() => {
  const savedTheme = localStorage.getItem('theme') || 'dark'
  document.documentElement.setAttribute('data-theme', savedTheme)
  
  // 检查URL参数决定默认登录类型
  if (route.query.type === 'staff') {
    loginType.value = 'staff'
  }
  
  // 检查是否是模拟登录
  const impersonate = route.query.impersonate
  const apiKey = route.query.api_key as string
  const accountId = route.query.account_id as string
  const accountName = route.query.account_name as string
  
  if (impersonate === '1' && apiKey) {
    // 标记为模拟登录模式
    sessionStorage.setItem('impersonate_mode', '1')
    localStorage.setItem('api_key', apiKey)
    if (accountId) localStorage.setItem('account_id', accountId)
    if (accountName) localStorage.setItem('account_name', accountName)
    
    ElMessage.success(t('staff.switchedTo') + ': ' + (accountName || t('roles.customer')))
    router.replace('/sms/send')
  }
})

const form = reactive({
  username: '',
  password: '',
})

const rules: FormRules = {
  username: [
    { required: true, message: () => t('login.enterUsername'), trigger: 'blur' },
    { min: 3, message: () => t('validation.minLength', { n: 3 }), trigger: 'blur' },
  ],
  password: [
    { required: true, message: () => t('login.enterPassword'), trigger: 'blur' },
    { min: 6, message: () => t('validation.minLength', { n: 6 }), trigger: 'blur' },
  ],
}

const handleLogin = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    
    if (!captchaVerified.value) {
      ElMessage.warning(t('login.sliderVerify'))
      return
    }
    
    loading.value = true
    try {
      if (loginType.value === 'staff') {
        // 员工登录
        await handleStaffLogin()
      } else {
        // 客户登录
        await handleCustomerLogin()
      }
    } catch (error: any) {
      ElMessage.error(error.message || t('common.error'))
      resetCaptcha()
    } finally {
      loading.value = false
    }
  })
}

const handleStaffLogin = async () => {
  const response = await adminLogin({
    username: form.username,
    password: form.password,
  })
  
  if (response.success && response.token) {
    // 清除所有旧凭证
    localStorage.removeItem('api_key')
    localStorage.removeItem('account_id')
    localStorage.removeItem('account_name')
    sessionStorage.removeItem('impersonate_mode')
    
    // 保存员工凭证
    localStorage.setItem('admin_token', response.token)
    localStorage.setItem('admin_id', String(response.admin_id || ''))
    localStorage.setItem('admin_role', response.role || '')
    localStorage.setItem('account_name', response.username || form.username)
    
    // 根据角色显示欢迎消息
    const roleNames: Record<string, string> = {
      'super_admin': t('roles.superAdmin'),
      'admin': t('roles.admin'),
      'sales': t('roles.sales'),
      'finance': t('roles.finance'),
      'tech': t('roles.tech'),
    }
    const roleName = roleNames[response.role || ''] || t('roles.staff')
    ElMessage.success(`${t('login.welcomeBack')}, ${roleName} ${response.username || form.username}`)
    
    router.push('/dashboard')
  } else {
    ElMessage.error(response.error || t('login.invalidCredentials'))
    resetCaptcha()
  }
}

const handleCustomerLogin = async () => {
  const accountResp: any = await accountLogin({
    email: form.username,
    password: form.password,
  })

  if (accountResp?.success && accountResp?.token) {
    // 清除所有旧凭证
    localStorage.removeItem('admin_token')
    localStorage.removeItem('admin_id')
    localStorage.removeItem('admin_role')
    sessionStorage.removeItem('impersonate_mode')
    
    // 保存客户凭证
    localStorage.setItem('api_key', accountResp.token)
    localStorage.setItem('account_id', String(accountResp.account_id || ''))

    try {
      const info: any = await getAccountInfo()
      if (info?.account_name) {
        localStorage.setItem('account_name', info.account_name)
      }
    } catch {}

    ElMessage.success(t('login.loginSuccess'))
    router.push('/dashboard')
  } else {
    ElMessage.error(accountResp?.error || t('login.invalidCredentials'))
    resetCaptcha()
  }
}

const resetCaptcha = () => {
  captchaRef.value?.reset()
  captchaVerified.value = false
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
  position: relative;
  overflow: hidden;
}

/* 背景 */
.background {
  position: absolute;
  inset: 0;
  pointer-events: none;
  transition: opacity 0.3s ease;
}

.gradient-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
  transition: background 0.3s ease;
}

.orb-1 {
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, rgba(102, 126, 234, 0.25) 0%, transparent 70%);
  top: -150px;
  left: -100px;
}

.orb-2 {
  width: 400px;
  height: 400px;
  background: radial-gradient(circle, rgba(118, 75, 162, 0.2) 0%, transparent 70%);
  bottom: -100px;
  right: -50px;
}

[data-theme="light"] .orb-1 {
  background: radial-gradient(circle, rgba(88, 86, 214, 0.12) 0%, transparent 70%);
}

[data-theme="light"] .orb-2 {
  background: radial-gradient(circle, rgba(175, 82, 222, 0.1) 0%, transparent 70%);
}

.grid-pattern {
  position: absolute;
  inset: 0;
  background-image: 
    linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
  background-size: 60px 60px;
  mask-image: radial-gradient(ellipse at center, black 30%, transparent 70%);
}

[data-theme="light"] .grid-pattern {
  background-image: 
    linear-gradient(rgba(0, 0, 0, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 0, 0, 0.03) 1px, transparent 1px);
}

/* 登录容器 */
.login-wrapper {
  position: relative;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
  width: 100%;
  max-width: 420px;
}

/* 品牌 */
.brand {
  text-align: center;
  margin-bottom: 32px;
}

.logo {
  margin-bottom: 20px;
}

.brand-name {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
  letter-spacing: -0.02em;
}

.brand-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

/* 登录卡片 */
.login-card {
  width: 100%;
  background: var(--bg-card);
  backdrop-filter: blur(20px);
  border: 1px solid var(--border-default);
  border-radius: 24px;
  padding: 28px 32px 32px;
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

[data-theme="light"] .login-card {
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 0.5px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
}

/* 登录类型切换 */
.login-tabs {
  display: flex;
  gap: 8px;
  padding: 4px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 12px;
  margin-bottom: 28px;
}

[data-theme="light"] .login-tabs {
  background: rgba(0, 0, 0, 0.04);
}

.tab-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 16px;
  background: transparent;
  border: none;
  border-radius: 10px;
  color: var(--text-tertiary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover:not(.active) {
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.04);
}

[data-theme="light"] .tab-btn:hover:not(.active) {
  background: rgba(0, 0, 0, 0.04);
}

.tab-btn.active {
  background: var(--gradient-primary);
  color: white;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.tab-btn svg {
  opacity: 0.8;
}

.tab-btn.active svg {
  opacity: 1;
}

.login-form {
  width: 100%;
}

.form-group {
  margin-bottom: 20px;
}

.form-group:last-of-type {
  margin-bottom: 24px;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

:deep(.form-input .el-input__wrapper) {
  height: 50px;
  background: var(--bg-input) !important;
  border: 1px solid var(--border-default) !important;
  border-radius: 12px !important;
  box-shadow: none !important;
  padding: 0 16px !important;
  transition: all 0.2s ease !important;
}

:deep(.form-input .el-input__wrapper:hover) {
  background: var(--bg-input-hover) !important;
  border-color: var(--border-hover) !important;
}

:deep(.form-input .el-input__wrapper.is-focus) {
  background: var(--bg-input-hover) !important;
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.15) !important;
}

[data-theme="light"] :deep(.form-input .el-input__wrapper) {
  background: rgba(0, 0, 0, 0.03) !important;
  border: 0.5px solid rgba(0, 0, 0, 0.1) !important;
  box-shadow: inset 0 0 0 0.5px rgba(0, 0, 0, 0.1) !important;
}

[data-theme="light"] :deep(.form-input .el-input__wrapper:hover) {
  background: rgba(0, 0, 0, 0.05) !important;
  border-color: rgba(0, 0, 0, 0.15) !important;
}

[data-theme="light"] :deep(.form-input .el-input__wrapper.is-focus) {
  background: rgba(0, 0, 0, 0.05) !important;
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 4px rgba(0, 122, 255, 0.15), inset 0 0 0 1px var(--primary) !important;
}

:deep(.form-input .el-input__prefix) {
  color: var(--text-quaternary);
  margin-right: 8px;
}

:deep(.form-input .el-input__inner) {
  color: var(--text-primary);
  font-size: 15px;
}

:deep(.form-input .el-input__inner::placeholder) {
  color: var(--text-quaternary);
}

/* 登录按钮 */
.login-button {
  width: 100%;
  height: 50px;
  background: var(--gradient-primary);
  border: none;
  border-radius: 12px;
  color: white;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
  overflow: hidden;
}

.login-button::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(255,255,255,0.15) 0%, transparent 50%);
}

.login-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.4);
}

.login-button:active:not(:disabled) {
  transform: translateY(0);
}

.login-button:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 角色提示 */
.role-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 16px;
  padding: 10px 14px;
  background: rgba(102, 126, 234, 0.08);
  border: 1px solid rgba(102, 126, 234, 0.15);
  border-radius: 10px;
  color: var(--primary);
  font-size: 12px;
}

.role-hint svg {
  flex-shrink: 0;
  opacity: 0.7;
}

/* 安全提示 */
.security-note {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  color: var(--text-quaternary);
  font-size: 12px;
}

[data-theme="light"] .security-note {
  border-top-color: rgba(0, 0, 0, 0.06);
}

.security-note svg {
  color: var(--success);
}

/* 版权 */
.copyright {
  margin-top: 32px;
  font-size: 12px;
  color: var(--text-quaternary);
}

/* 响应式 */
@media (max-width: 480px) {
  .login-wrapper {
    padding: 24px 16px;
  }
  
  .login-card {
    padding: 24px 20px;
  }
  
  .brand-name {
    font-size: 24px;
  }
  
  .tab-btn {
    padding: 10px 12px;
    font-size: 13px;
  }
  
  .tab-btn svg {
    width: 14px;
    height: 14px;
  }
}
</style>
