<template>
  <div class="login-page" :class="{ 'is-light': !isDark }">
    <!-- 背景 -->
    <div class="bg">
      <div class="bg-grain"></div>
      <div class="bg-glow glow-a"></div>
      <div class="bg-glow glow-b"></div>
      <div class="bg-glow glow-c"></div>
    </div>

    <!-- 顶部工具栏 -->
    <header class="topbar">
      <button class="topbar-pill" @click="toggleTheme" :title="isDark ? 'Light' : 'Dark'">
        <transition name="icon-flip" mode="out-in">
          <svg v-if="isDark" key="sun" width="16" height="16" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="3.2" stroke="currentColor" stroke-width="1.4"/>
            <path d="M8 1.5v1.8M8 12.7v1.8M1.5 8h1.8M12.7 8h1.8M3.4 3.4l1.3 1.3M11.3 11.3l1.3 1.3M3.4 12.6l1.3-1.3M11.3 4.7l1.3-1.3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
          </svg>
          <svg v-else key="moon" width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M13.6 9.8A6 6 0 0 1 6.2 2.4a6 6 0 1 0 7.4 7.4Z" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </transition>
      </button>
      <button class="topbar-pill lang-pill" @click="toggleLang">
        {{ currentLang === 'zh-CN' ? 'EN' : '中文' }}
      </button>
    </header>

    <!-- 主体 -->
    <main class="main">
      <div class="hero" :class="{ show: mounted }">
        <div class="logo-mark">
          <div class="logo-ring">
            <svg width="52" height="52" viewBox="0 0 48 48" fill="none">
              <defs>
                <linearGradient id="lg" x1="4" y1="4" x2="44" y2="44">
                  <stop stop-color="#6366F1"/><stop offset="1" stop-color="#A855F7"/>
                </linearGradient>
                <filter id="glow"><feGaussianBlur stdDeviation="1.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
              </defs>
              <circle cx="24" cy="24" r="20" stroke="url(#lg)" stroke-width="0.8" opacity="0.2"/>
              <circle cx="24" cy="24" r="14" stroke="url(#lg)" stroke-width="0.5" opacity="0.1" stroke-dasharray="2 3"/>
              <path d="M24 6 L27.5 20 L42 24 L27.5 28 L24 42 L20.5 28 L6 24 L20.5 20 Z" fill="url(#lg)" opacity="0.9"/>
              <circle cx="24" cy="24" r="3.5" fill="#fff" opacity="0.9" filter="url(#glow)"/>
              <g fill="url(#lg)" opacity="0.75">
                <circle cx="24" cy="4" r="1.6"/><circle cx="44" cy="24" r="1.6"/>
                <circle cx="24" cy="44" r="1.6"/><circle cx="4" cy="24" r="1.6"/>
              </g>
              <g stroke="url(#lg)" stroke-width="0.5" opacity="0.15">
                <line x1="24" y1="4" x2="44" y2="24"/><line x1="44" y1="24" x2="24" y2="44"/>
                <line x1="24" y1="44" x2="4" y2="24"/><line x1="4" y1="24" x2="24" y2="4"/>
              </g>
            </svg>
          </div>
        </div>
        <h1 class="hero-title">{{ $t('brand.name') }}</h1>
        <p class="hero-sub">{{ $t('login.subtitle') }}</p>
      </div>

      <div class="card" :class="{ show: mounted }">
        <!-- Tabs -->
        <nav class="tabs">
          <button v-for="tab in tabs" :key="tab.key"
            :class="['tab', { active: loginType === tab.key }]"
            @click="loginType = tab.key"
          >{{ tab.label }}</button>
          <div class="tab-indicator" :style="indicatorStyle"></div>
        </nav>

        <!-- TG 登录 -->
        <div v-if="loginType === 'telegram'" class="form-area">
          <div class="field">
            <label>{{ $t('login.username') }}</label>
            <div class="input-wrap">
              <input type="text" v-model="tgForm.username" :placeholder="$t('login.enterStaffUsername')" autocomplete="username" />
            </div>
          </div>

          <template v-if="!tgCodeSent">
            <button class="btn-primary" :disabled="tgSending || !tgForm.username" @click="handleSendTgCode">
              <span v-if="!tgSending">{{ $t('login.tgSendCode') }}</span>
              <span v-else class="btn-loading"><i class="dot-spinner"></i>{{ $t('login.tgSending') }}</span>
            </button>
          </template>
          <template v-else>
            <div class="field">
              <label>{{ $t('login.tgVerifyCode') }}</label>
              <div class="input-wrap">
                <input type="text" v-model="tgForm.code" :placeholder="$t('login.tgEnterCode')" maxlength="6" autocomplete="one-time-code" />
              </div>
            </div>
            <button class="btn-primary" :disabled="loading || !tgForm.code" @click="handleTgVerify">
              <span v-if="!loading">{{ $t('login.tgVerifyLogin') }}</span>
              <span v-else class="btn-loading"><i class="dot-spinner"></i>{{ $t('login.loggingIn') }}</span>
            </button>
            <p class="resend-row">
              <span v-if="tgCooldown > 0" class="muted">{{ $t('login.tgResendIn', { n: tgCooldown }) }}</span>
              <button v-else class="link-btn" @click="handleSendTgCode">{{ $t('login.tgResendCode') }}</button>
            </p>
          </template>
        </div>

        <!-- 密码登录 -->
        <el-form v-else :model="form" :rules="rules" ref="formRef" @submit.prevent="handleLogin" class="form-area">
          <div class="field">
            <label>{{ loginType === 'customer' ? $t('login.email') : $t('login.username') }}</label>
            <div class="input-wrap">
              <input
                type="text"
                v-model="form.username"
                :placeholder="loginType === 'customer' ? $t('login.enterEmail') : $t('login.enterStaffUsername')"
                autocomplete="username"
              />
            </div>
          </div>
          <div class="field">
            <label>{{ $t('login.password') }}</label>
            <div class="input-wrap has-toggle">
              <input
                :type="showPwd ? 'text' : 'password'"
                v-model="form.password"
                :placeholder="$t('login.enterPassword')"
                autocomplete="current-password"
              />
              <button type="button" class="pwd-toggle" @click="showPwd = !showPwd" tabindex="-1">
                <svg v-if="showPwd" width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M1.5 9s3-5.5 7.5-5.5S16.5 9 16.5 9s-3 5.5-7.5 5.5S1.5 9 1.5 9Z" stroke="currentColor" stroke-width="1.3"/><circle cx="9" cy="9" r="2.5" stroke="currentColor" stroke-width="1.3"/></svg>
                <svg v-else width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M1.5 9s3-5.5 7.5-5.5S16.5 9 16.5 9s-3 5.5-7.5 5.5S1.5 9 1.5 9Z" stroke="currentColor" stroke-width="1.3"/><circle cx="9" cy="9" r="2.5" stroke="currentColor" stroke-width="1.3"/><path d="M3 15L15 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
              </button>
            </div>
          </div>

          <div class="captcha-row">
            <SliderCaptcha ref="captchaRef" v-model="captchaVerified" />
          </div>

          <button type="submit" class="btn-primary" :disabled="loading" @click.prevent="handleLogin">
            <span v-if="!loading">
              {{ loginType === 'customer' ? $t('login.customerLoginBtn') : $t('login.staffLoginBtn') }}
            </span>
            <span v-else class="btn-loading"><i class="dot-spinner"></i>{{ $t('login.loggingIn') }}</span>
          </button>
        </el-form>

        <!-- 底部信息 -->
        <p v-if="loginType === 'staff'" class="card-hint">
          {{ $t('login.roleHint') }}
        </p>
        <div class="card-footer">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M6.5 1L2 3.2v2.8c0 2.8 1.9 5.3 4.5 6 2.6-.7 4.5-3.2 4.5-6V3.2L6.5 1Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M4.5 6.5l1.3 1.3L8.5 5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <span>{{ $t('login.securityNote') }}</span>
        </div>
      </div>

      <p class="copyright" :class="{ show: mounted }">© 2024 {{ $t('brand.name') }}. All rights reserved.</p>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { adminLogin, sendTelegramLoginCode, verifyTelegramLoginCode } from '@/api/admin'
import { login as accountLogin, getAccountInfo } from '@/api/account'
import SliderCaptcha from '@/components/SliderCaptcha.vue'

const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()
const formRef = ref<FormInstance>()
const loading = ref(false)
const captchaVerified = ref(false)
const captchaRef = ref<InstanceType<typeof SliderCaptcha>>()
const loginType = ref<'customer' | 'staff' | 'telegram'>('customer')
const showPwd = ref(false)
const mounted = ref(false)

const isDark = ref(true)
const currentLang = ref(locale.value)

const tabs = computed(() => [
  { key: 'customer' as const, label: t('login.customerLogin') },
  { key: 'staff' as const, label: t('login.staffLogin') },
  { key: 'telegram' as const, label: t('login.tgLogin') },
])

const indicatorStyle = computed(() => {
  const idx = tabs.value.findIndex(tb => tb.key === loginType.value)
  const w = 100 / tabs.value.length
  return { left: `${idx * w}%`, width: `${w}%` }
})

const toggleTheme = () => {
  isDark.value = !isDark.value
  const theme = isDark.value ? 'dark' : 'light'
  document.documentElement.setAttribute('data-theme', theme)
  document.documentElement.classList.toggle('dark', isDark.value)
  localStorage.setItem('theme', theme)
}

const toggleLang = () => {
  const newLang = currentLang.value === 'zh-CN' ? 'en-US' : 'zh-CN'
  currentLang.value = newLang
  locale.value = newLang
  localStorage.setItem('language', newLang)
}

// TG 验证登录
const tgForm = reactive({ username: '', code: '' })
const tgCodeSent = ref(false)
const tgSending = ref(false)
const tgCooldown = ref(0)
let tgTimer: ReturnType<typeof setInterval> | null = null

const handleSendTgCode = async () => {
  if (!tgForm.username) { ElMessage.warning(t('login.enterUsername')); return }
  tgSending.value = true
  try {
    const res: any = await sendTelegramLoginCode(tgForm.username)
    if (res?.success) {
      tgCodeSent.value = true
      tgCooldown.value = 60
      tgTimer = setInterval(() => {
        tgCooldown.value--
        if (tgCooldown.value <= 0 && tgTimer) { clearInterval(tgTimer); tgTimer = null }
      }, 1000)
      ElMessage.success(t('login.tgCodeSentSuccess'))
    } else {
      ElMessage.error(mapLoginError(res?.error || 'send_failed'))
    }
  } catch (e: any) {
    ElMessage.error(e.message || t('login.tgSendFailed'))
  } finally { tgSending.value = false }
}

const handleTgVerify = async () => {
  if (!tgForm.code) return
  loading.value = true
  try {
    const res = await verifyTelegramLoginCode(tgForm.username, tgForm.code)
    if (res.success && res.token) {
      localStorage.removeItem('api_key'); localStorage.removeItem('account_id'); localStorage.removeItem('account_name')
      sessionStorage.removeItem('impersonate_mode')
      localStorage.setItem('admin_token', res.token)
      localStorage.setItem('admin_id', String(res.admin_id || ''))
      localStorage.setItem('admin_role', res.role || '')
      localStorage.setItem('account_name', res.username || tgForm.username)
      ElMessage.success(`${t('login.welcomeBack')}, ${res.username || tgForm.username}`)
      router.push('/dashboard')
    } else { ElMessage.error(mapLoginError(res.error || '')) }
  } catch (e: any) { ElMessage.error(e.message || t('common.error')) }
  finally { loading.value = false }
}

onUnmounted(() => { if (tgTimer) clearInterval(tgTimer) })

onMounted(async () => {
  const savedTheme = localStorage.getItem('theme') || 'dark'
  isDark.value = savedTheme === 'dark'
  document.documentElement.setAttribute('data-theme', savedTheme)
  document.documentElement.classList.toggle('dark', isDark.value)
  const savedLang = localStorage.getItem('language')
  if (savedLang) { currentLang.value = savedLang; locale.value = savedLang }
  if (route.query.type === 'staff') loginType.value = 'staff'

  const impersonate = route.query.impersonate
  const apiKey = route.query.api_key as string
  const accountId = route.query.account_id as string
  const accountName = route.query.account_name as string
  if (impersonate === '1' && apiKey) {
    sessionStorage.setItem('impersonate_mode', '1')
    localStorage.setItem('api_key', apiKey)
    if (accountId) localStorage.setItem('account_id', accountId)
    if (accountName) localStorage.setItem('account_name', accountName)
    ElMessage.success(t('staff.switchedTo') + ': ' + (accountName || t('roles.customer')))
    router.replace('/sms/send')
  }

  await nextTick()
  requestAnimationFrame(() => { mounted.value = true })
})

const form = reactive({ username: '', password: '' })

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
    if (!captchaVerified.value) { ElMessage.warning(t('login.sliderVerify')); return }
    loading.value = true
    try {
      if (loginType.value === 'staff') await handleStaffLogin()
      else await handleCustomerLogin()
    } catch (error: any) { ElMessage.error(error.message || t('common.error')); resetCaptcha() }
    finally { loading.value = false }
  })
}

const mapLoginError = (error: string): string => {
  if (!error) return t('login.invalidCredentials')
  if (error.startsWith('invalid_credentials')) {
    const parts = error.split(':')
    return parts[1] ? t('login.invalidCredentialsRemaining', { n: parts[1] }) : t('login.invalidCredentials')
  }
  const m: Record<string, string> = {
    account_locked: t('login.accountLocked'), account_disabled: t('login.accountDisabled'),
    tg_not_bound: t('login.tgNotBound'), code_expired: t('login.tgCodeExpired'),
    code_invalid: t('login.tgCodeInvalid'), send_failed: t('login.tgSendFailed'),
    account_not_bound: t('login.tgNotBound'), cooldown: t('login.tgCooldown'),
  }
  return m[error] || error
}

const handleStaffLogin = async () => {
  const response = await adminLogin({ username: form.username, password: form.password })
  if (response.success && response.token) {
    localStorage.removeItem('api_key'); localStorage.removeItem('account_id'); localStorage.removeItem('account_name')
    sessionStorage.removeItem('impersonate_mode')
    localStorage.setItem('admin_token', response.token)
    localStorage.setItem('admin_id', String(response.admin_id || ''))
    localStorage.setItem('admin_role', response.role || '')
    localStorage.setItem('account_name', response.username || form.username)
    const roleNames: Record<string, string> = { super_admin: t('roles.superAdmin'), admin: t('roles.admin'), sales: t('roles.sales'), finance: t('roles.finance'), tech: t('roles.tech') }
    const roleName = roleNames[response.role || ''] || t('roles.staff')
    ElMessage.success(`${t('login.welcomeBack')}, ${roleName} ${response.username || form.username}`)
    router.push('/dashboard')
  } else { ElMessage.error(mapLoginError(response.error)); resetCaptcha() }
}

const handleCustomerLogin = async () => {
  const accountResp: any = await accountLogin({ email: form.username, password: form.password })
  if (accountResp?.success && accountResp?.token) {
    localStorage.removeItem('admin_token'); localStorage.removeItem('admin_id'); localStorage.removeItem('admin_role')
    sessionStorage.removeItem('impersonate_mode')
    localStorage.setItem('api_key', accountResp.token)
    localStorage.setItem('account_id', String(accountResp.account_id || ''))
    try { const info: any = await getAccountInfo(); if (info?.account_name) localStorage.setItem('account_name', info.account_name) } catch {}
    ElMessage.success(t('login.loginSuccess'))
    router.push('/dashboard')
  } else { ElMessage.error(mapLoginError(accountResp?.error)); resetCaptcha() }
}

const resetCaptcha = () => { captchaRef.value?.reset(); captchaVerified.value = false }
</script>

<style scoped>
/* ═══════════════════════════════════════
   Apple-Inspired Login — 极简通透质感
   ═══════════════════════════════════════ */

/* ---------- 页面容器 ---------- */
.login-page {
  --accent: #6366F1;
  --accent-hover: #4F46E5;
  --accent-glow: rgba(99, 102, 241, 0.35);
  --card-bg: rgba(28, 28, 34, 0.55);
  --card-border: rgba(255, 255, 255, 0.08);
  --card-shadow: 0 8px 64px rgba(0, 0, 0, 0.35), 0 2px 8px rgba(0, 0, 0, 0.2);
  --input-bg: rgba(255, 255, 255, 0.06);
  --input-border: rgba(255, 255, 255, 0.1);
  --input-focus: rgba(255, 255, 255, 0.12);
  --text-1: #F5F5F7;
  --text-2: rgba(245, 245, 247, 0.72);
  --text-3: rgba(245, 245, 247, 0.48);
  --text-4: rgba(245, 245, 247, 0.28);
  --page-bg: #0B0D13;

  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--page-bg);
  color: var(--text-1);
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  overflow: hidden;
  position: relative;
}

.login-page.is-light {
  --accent: #0071E3;
  --accent-hover: #0077ED;
  --accent-glow: rgba(0, 113, 227, 0.18);
  --card-bg: rgba(255, 255, 255, 0.72);
  --card-border: rgba(0, 0, 0, 0.06);
  --card-shadow: 0 4px 48px rgba(0, 0, 0, 0.08), 0 1px 4px rgba(0, 0, 0, 0.04);
  --input-bg: rgba(0, 0, 0, 0.04);
  --input-border: rgba(0, 0, 0, 0.08);
  --input-focus: rgba(0, 0, 0, 0.06);
  --text-1: #1D1D1F;
  --text-2: rgba(29, 29, 31, 0.72);
  --text-3: rgba(29, 29, 31, 0.42);
  --text-4: rgba(29, 29, 31, 0.22);
  --page-bg: #F5F5F7;
}

/* ---------- 背景 ---------- */
.bg {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.bg-grain {
  position: absolute;
  inset: 0;
  opacity: 0.025;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  background-size: 128px;
}

.is-light .bg-grain { opacity: 0.02; }

.bg-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(120px);
  will-change: transform;
  animation: float 20s ease-in-out infinite;
}

.glow-a {
  width: 600px; height: 600px;
  background: radial-gradient(circle, rgba(99, 102, 241, 0.18), transparent 70%);
  top: -20%; left: -10%;
  animation-delay: 0s;
}
.glow-b {
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(168, 85, 247, 0.14), transparent 70%);
  bottom: -15%; right: -8%;
  animation-delay: -7s;
}
.glow-c {
  width: 350px; height: 350px;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.1), transparent 70%);
  top: 40%; left: 55%;
  animation-delay: -14s;
}

.is-light .glow-a { background: radial-gradient(circle, rgba(0, 113, 227, 0.08), transparent 70%); }
.is-light .glow-b { background: radial-gradient(circle, rgba(168, 85, 247, 0.06), transparent 70%); }
.is-light .glow-c { background: radial-gradient(circle, rgba(52, 199, 89, 0.05), transparent 70%); }

@keyframes float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -20px) scale(1.05); }
  66% { transform: translate(-20px, 15px) scale(0.97); }
}

/* ---------- 顶部工具栏 ---------- */
.topbar {
  position: fixed;
  top: 0; left: 0; right: 0;
  z-index: 100;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 6px;
  padding: 16px 24px;
}

.topbar-pill {
  height: 34px;
  min-width: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 10px;
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 20px;
  color: var(--text-2);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.is-light .topbar-pill {
  background: rgba(0, 0, 0, 0.04);
  border-color: rgba(0, 0, 0, 0.06);
}

.topbar-pill:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-1);
  transform: scale(1.04);
}
.is-light .topbar-pill:hover { background: rgba(0, 0, 0, 0.07); }

.lang-pill { padding: 0 14px; }

/* ---------- 主体布局 ---------- */
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px 40px;
  position: relative;
  z-index: 1;
}

/* ---------- Hero ---------- */
.hero {
  text-align: center;
  margin-bottom: 36px;
  opacity: 0;
  transform: translateY(18px);
  transition: all 0.8s cubic-bezier(0.16, 1, 0.3, 1);
}
.hero.show { opacity: 1; transform: translateY(0); }

.logo-mark { margin-bottom: 20px; display: flex; justify-content: center; }

.logo-ring {
  width: 72px; height: 72px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: radial-gradient(circle at 40% 40%, rgba(99, 102, 241, 0.12), rgba(168, 85, 247, 0.06));
  border: 1px solid rgba(99, 102, 241, 0.1);
  box-shadow: 0 0 40px rgba(99, 102, 241, 0.12), inset 0 0 20px rgba(99, 102, 241, 0.05);
  transition: transform 0.6s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.4s ease;
}
.is-light .logo-ring {
  background: radial-gradient(circle at 40% 40%, rgba(99, 102, 241, 0.08), rgba(168, 85, 247, 0.03));
  border-color: rgba(99, 102, 241, 0.08);
  box-shadow: 0 0 30px rgba(99, 102, 241, 0.06);
}
.logo-ring:hover {
  transform: scale(1.08);
  box-shadow: 0 0 60px rgba(99, 102, 241, 0.2), inset 0 0 20px rgba(99, 102, 241, 0.08);
}

.hero-title {
  font-size: 34px;
  font-weight: 800;
  letter-spacing: 0.12em;
  margin: 0 0 8px;
  background: linear-gradient(135deg, #6366F1 0%, #A855F7 50%, #6366F1 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  background-size: 200% 100%;
  animation: shimmer 6s ease-in-out infinite;
}
.is-light .hero-title {
  background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 50%, #4F46E5 100%);
  -webkit-background-clip: text;
  background-clip: text;
  background-size: 200% 100%;
  animation: shimmer 6s ease-in-out infinite;
}
@keyframes shimmer {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

.hero-sub {
  font-size: 13px;
  color: var(--text-3);
  margin: 0;
  font-weight: 500;
  letter-spacing: 0.35em;
  text-transform: uppercase;
}

/* ---------- 卡片 ---------- */
.card {
  width: 100%;
  max-width: 400px;
  background: var(--card-bg);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid var(--card-border);
  border-radius: 20px;
  padding: 32px 32px 28px;
  box-shadow: var(--card-shadow);
  opacity: 0;
  transform: translateY(24px);
  transition: all 0.8s cubic-bezier(0.16, 1, 0.3, 1) 0.1s;
}
.card.show { opacity: 1; transform: translateY(0); }

/* ---------- Tabs ---------- */
.tabs {
  display: flex;
  position: relative;
  background: var(--input-bg);
  border-radius: 10px;
  padding: 3px;
  margin-bottom: 28px;
}

.tab {
  flex: 1;
  position: relative;
  z-index: 1;
  padding: 9px 0;
  background: none;
  border: none;
  color: var(--text-3);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.3s ease;
  letter-spacing: 0.01em;
}
.tab:hover { color: var(--text-2); }
.tab.active { color: var(--text-1); }

.tab-indicator {
  position: absolute;
  top: 3px;
  bottom: 3px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  transition: left 0.35s cubic-bezier(0.16, 1, 0.3, 1), width 0.35s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
}

.is-light .tab-indicator {
  background: rgba(255, 255, 255, 0.85);
  box-shadow: 0 0.5px 2px rgba(0, 0, 0, 0.08), 0 0 0 0.5px rgba(0, 0, 0, 0.04);
}

/* ---------- 表单区 ---------- */
.form-area {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.field {
  margin-bottom: 18px;
}

.field label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-2);
  margin-bottom: 7px;
  letter-spacing: 0.01em;
}

.input-wrap {
  position: relative;
}

.input-wrap input {
  width: 100%;
  height: 48px;
  padding: 0 16px;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 12px;
  color: var(--text-1);
  font-size: 15px;
  font-family: inherit;
  outline: none;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  box-sizing: border-box;
}

.input-wrap input::placeholder {
  color: var(--text-4);
}

.input-wrap input:hover {
  border-color: rgba(255, 255, 255, 0.15);
  background: var(--input-focus);
}
.is-light .input-wrap input:hover {
  border-color: rgba(0, 0, 0, 0.12);
}

.input-wrap input:focus {
  border-color: var(--accent);
  background: var(--input-focus);
  box-shadow: 0 0 0 3px var(--accent-glow);
}

.has-toggle input { padding-right: 46px; }

.pwd-toggle {
  position: absolute;
  right: 4px; top: 50%;
  transform: translateY(-50%);
  width: 38px; height: 38px;
  display: flex; align-items: center; justify-content: center;
  background: none;
  border: none;
  color: var(--text-4);
  cursor: pointer;
  border-radius: 8px;
  transition: color 0.2s, background 0.2s;
}
.pwd-toggle:hover { color: var(--text-2); background: rgba(255, 255, 255, 0.06); }
.is-light .pwd-toggle:hover { background: rgba(0, 0, 0, 0.04); }

/* ---------- 滑块验证 ---------- */
.captcha-row {
  margin-bottom: 22px;
}

/* ---------- 主按钮 ---------- */
.btn-primary {
  width: 100%;
  height: 48px;
  background: var(--accent);
  border: none;
  border-radius: 12px;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  font-family: inherit;
  letter-spacing: 0.01em;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
  transform: scale(1.01);
  box-shadow: 0 4px 20px var(--accent-glow);
}

.btn-primary:active:not(:disabled) {
  transform: scale(0.98);
  box-shadow: none;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-loading {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.dot-spinner {
  display: inline-block;
  width: 16px; height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* ---------- 卡片底部 ---------- */
.card-hint {
  margin: 16px 0 0;
  padding: 10px 14px;
  background: var(--input-bg);
  border-radius: 10px;
  font-size: 12px;
  color: var(--text-3);
  text-align: center;
  line-height: 1.5;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid var(--card-border);
  color: var(--text-4);
  font-size: 12px;
}

.card-footer svg { color: #34C759; flex-shrink: 0; }
.is-light .card-footer svg { color: #30D158; }

/* ---------- 重发 ---------- */
.resend-row {
  text-align: center;
  margin-top: 14px;
  font-size: 13px;
}
.muted { color: var(--text-4); }

.link-btn {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  padding: 0;
}
.link-btn:hover { text-decoration: underline; }

/* ---------- 版权 ---------- */
.copyright {
  margin-top: 36px;
  font-size: 12px;
  color: var(--text-4);
  opacity: 0;
  transform: translateY(10px);
  transition: all 0.8s cubic-bezier(0.16, 1, 0.3, 1) 0.2s;
}
.copyright.show { opacity: 1; transform: translateY(0); }

/* ---------- 图标切换动画 ---------- */
.icon-flip-enter-active,
.icon-flip-leave-active {
  transition: all 0.2s ease;
}
.icon-flip-enter-from { opacity: 0; transform: rotate(-90deg) scale(0.6); }
.icon-flip-leave-to { opacity: 0; transform: rotate(90deg) scale(0.6); }

/* ---------- 覆盖 el-form 默认样式 ---------- */
:deep(.el-form-item) { margin-bottom: 0; }
:deep(.el-form-item__error) {
  font-size: 12px;
  padding-top: 4px;
  color: #FF453A;
}
.is-light :deep(.el-form-item__error) { color: #FF3B30; }

/* ---------- 响应式 ---------- */
@media (max-width: 480px) {
  .main { padding: 70px 16px 32px; }
  .card { padding: 24px 22px 22px; border-radius: 18px; }
  .hero-title { font-size: 26px; }
  .tab { font-size: 12px; padding: 8px 0; }
}

@media (min-height: 900px) {
  .main { padding-top: 0; }
}
</style>
