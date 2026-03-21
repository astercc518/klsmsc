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
      <a href="/" class="topbar-logo" aria-label="考拉出海">
        <img src="/favicon.svg" alt="" class="topbar-logo-icon" width="28" height="28" />
        <span class="topbar-logo-text">Kao<em>lach</em></span>
      </a>
      <nav class="topbar-nav" aria-label="官网导航">
        <a href="/" class="topbar-nav-item">{{ $t('landing.nav.home') }}</a>
        <a href="/#products" class="topbar-nav-item">{{ $t('landing.nav.smsProducts') }}</a>
        <a href="/#solutions" class="topbar-nav-item">{{ $t('landing.nav.solutions') }}</a>
        <a href="/#pricing" class="topbar-nav-item">{{ $t('landing.nav.pricing') }}</a>
        <a href="/#faq" class="topbar-nav-item">{{ $t('landing.nav.support') }}</a>
        <a href="/#about" class="topbar-nav-item">{{ $t('landing.nav.about') }}</a>
      </nav>
      <div class="topbar-right">
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
        {{ currentLang === 'zh-CN' ? $t('language.shortEn') : $t('language.zh') }}
      </button>
      </div>
    </header>

    <!-- 主体 -->
    <main class="main">
      <div class="hero" :class="{ show: mounted }">
        <div class="logo-mark">
          <img src="/favicon.svg" alt="考拉出海" class="logo-mark-img" width="64" height="64" />
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
            <label>{{ $t('login.tgIdentifier') }}</label>
            <div class="input-wrap">
              <input type="text" v-model="tgForm.username" :placeholder="$t('login.tgIdentifierPlaceholder')" autocomplete="username" />
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
                <input
                ref="tgCodeInputRef"
                type="text"
                v-model="tgForm.code"
                :placeholder="$t('login.tgEnterCode')"
                maxlength="6"
                inputmode="numeric"
                pattern="[0-9]*"
                autocomplete="one-time-code"
                @input="tgForm.code = tgForm.code.replace(/\D/g, '').slice(0, 6)"
              />
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
            <label>{{ $t('login.email') }}</label>
            <div class="input-wrap">
              <input
                type="text"
                v-model="form.username"
                :placeholder="$t('login.enterEmail')"
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
              {{ $t('login.customerLoginBtn') }}
            </span>
            <span v-else class="btn-loading"><i class="dot-spinner"></i>{{ $t('login.loggingIn') }}</span>
          </button>
        </el-form>

        <!-- 底部信息 -->
        <div class="card-footer">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M6.5 1L2 3.2v2.8c0 2.8 1.9 5.3 4.5 6 2.6-.7 4.5-3.2 4.5-6V3.2L6.5 1Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M4.5 6.5l1.3 1.3L8.5 5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <span>{{ $t('login.securityNote') }}</span>
        </div>
        <a href="/" class="card-website-link">{{ $t('login.backToWebsite') }}</a>
      </div>

      <p class="copyright" :class="{ show: mounted }">© 2024 {{ $t('brand.name') }}. All rights reserved.</p>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { adminLogin, sendTelegramLoginCode, verifyTelegramLoginCode } from '@/api/admin'
import { sendAccountTelegramCode, verifyAccountTelegramCode, getAccountInfo, login as accountLogin } from '@/api/account'
import SliderCaptcha from '@/components/SliderCaptcha.vue'

const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()
const formRef = ref<FormInstance>()
const loading = ref(false)
const captchaVerified = ref(false)
const captchaRef = ref<InstanceType<typeof SliderCaptcha>>()
const loginType = ref<'customer' | 'telegram'>('customer')
const showPwd = ref(false)
const mounted = ref(false)

const isDark = ref(true)
const currentLang = ref(locale.value)

const tabs = computed(() => [
  { key: 'customer' as const, label: t('login.customerLogin') },
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
  localStorage.setItem('locale', newLang)
}

// TG 验证登录（支持客户账户和员工，先尝试客户）
const tgForm = reactive({ username: '', code: '' })
const tgUserType = ref<'account' | 'admin'>('account')  // 发送成功后记录类型
const tgCodeSent = ref(false)
const tgSending = ref(false)
const tgCooldown = ref(0)
const tgCodeInputRef = ref<HTMLInputElement>()
let tgTimer: ReturnType<typeof setInterval> | null = null

watch(tgCodeSent, (sent) => {
  if (sent) nextTick(() => tgCodeInputRef.value?.focus())
})

const handleSendTgCode = async () => {
  const identifier = tgForm.username?.trim()
  if (!identifier) { ElMessage.warning(t('login.enterUsername')); return }
  tgSending.value = true
  try {
    let res: any = await sendAccountTelegramCode(identifier)
    if (res?.success) {
      tgForm.username = identifier
      tgUserType.value = 'account'
      tgCodeSent.value = true
      tgCooldown.value = res.remaining ?? 60
      tgTimer = setInterval(() => {
        tgCooldown.value--
        if (tgCooldown.value <= 0 && tgTimer) { clearInterval(tgTimer); tgTimer = null }
      }, 1000)
      ElMessage.success(t('login.tgCodeSentSuccess'))
    } else if (res?.error === 'account_not_bound') {
      res = await sendTelegramLoginCode(identifier)
      if (res?.success) {
        tgForm.username = identifier
        tgUserType.value = 'admin'
        tgCodeSent.value = true
        tgCooldown.value = res.remaining ?? 60
        tgTimer = setInterval(() => {
          tgCooldown.value--
          if (tgCooldown.value <= 0 && tgTimer) { clearInterval(tgTimer); tgTimer = null }
        }, 1000)
        ElMessage.success(t('login.tgCodeSentSuccess'))
      } else {
        if (res?.error === 'cooldown' && res?.remaining) {
          tgForm.username = identifier
          tgUserType.value = 'admin'
          tgCodeSent.value = true
          tgCooldown.value = res.remaining
          tgTimer = setInterval(() => {
            tgCooldown.value--
            if (tgCooldown.value <= 0 && tgTimer) { clearInterval(tgTimer); tgTimer = null }
          }, 1000)
        }
        ElMessage.error(mapLoginError(res?.error || 'send_failed'))
      }
    } else {
      if (res?.error === 'cooldown' && res?.remaining) {
        tgForm.username = identifier
        tgUserType.value = 'account'
        tgCodeSent.value = true
        tgCooldown.value = res.remaining
        tgTimer = setInterval(() => {
          tgCooldown.value--
          if (tgCooldown.value <= 0 && tgTimer) { clearInterval(tgTimer); tgTimer = null }
        }, 1000)
      }
      ElMessage.error(mapLoginError(res?.error || 'send_failed'))
    }
  } catch (e: any) {
    ElMessage.error(e.message || t('login.tgSendFailed'))
  } finally { tgSending.value = false }
}

const handleTgVerify = async () => {
  const code = tgForm.code?.replace(/\D/g, '')
  if (!code || code.length !== 6) {
    ElMessage.warning(t('login.tgEnterCode'))
    return
  }
  loading.value = true
  try {
    if (tgUserType.value === 'account') {
      const res: any = await verifyAccountTelegramCode(tgForm.username.trim(), code)
      if (res?.success && res?.token) {
        localStorage.removeItem('admin_token'); localStorage.removeItem('admin_id'); localStorage.removeItem('admin_role')
        sessionStorage.removeItem('impersonate_mode')
        localStorage.setItem('api_key', res.token)
        localStorage.setItem('account_id', String(res.account_id || ''))
        try { const info: any = await getAccountInfo(); if (info?.account_name) localStorage.setItem('account_name', info.account_name) } catch {}
        ElMessage.success(t('login.loginSuccess'))
        router.push('/dashboard')
      } else { ElMessage.error(mapLoginError(res?.error || '')) }
    } else {
      const res = await verifyTelegramLoginCode(tgForm.username.trim(), code)
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
    }
  } catch (e: any) { ElMessage.error(e.message || t('common.error')) }
  finally { loading.value = false }
}

onUnmounted(() => { if (tgTimer) clearInterval(tgTimer) })

onMounted(async () => {
  const savedTheme = localStorage.getItem('theme') || 'dark'
  isDark.value = savedTheme === 'dark'
  document.documentElement.setAttribute('data-theme', savedTheme)
  document.documentElement.classList.toggle('dark', isDark.value)
  const savedLang = localStorage.getItem('locale')
  if (savedLang) { currentLang.value = savedLang; locale.value = savedLang }

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

// 管理员登录成功后的处理
const doAdminSuccess = (adminResp: { token?: string; admin_id?: number; role?: string; username?: string }) => {
  localStorage.removeItem('api_key'); localStorage.removeItem('account_id'); localStorage.removeItem('account_name')
  sessionStorage.removeItem('impersonate_mode')
  localStorage.setItem('admin_token', adminResp.token!)
  localStorage.setItem('admin_id', String(adminResp.admin_id || ''))
  localStorage.setItem('admin_role', adminResp.role || '')
  localStorage.setItem('account_name', adminResp.username || form.username)
  const roleNames: Record<string, string> = { super_admin: t('roles.superAdmin'), admin: t('roles.admin'), sales: t('roles.sales'), finance: t('roles.finance'), tech: t('roles.tech') }
  const roleName = roleNames[adminResp.role || ''] || t('roles.staff')
  ElMessage.success(`${t('login.welcomeBack')}, ${roleName} ${adminResp.username || form.username}`)
  router.push('/dashboard')
}
// 客户登录成功后的处理
const doCustomerSuccess = async (accountResp: { token?: string; account_id?: number }) => {
  localStorage.removeItem('admin_token'); localStorage.removeItem('admin_id'); localStorage.removeItem('admin_role')
  sessionStorage.removeItem('impersonate_mode')
  localStorage.setItem('api_key', accountResp.token!)
  localStorage.setItem('account_id', String(accountResp.account_id || ''))
  try { const info: any = await getAccountInfo(); if (info?.account_name) localStorage.setItem('account_name', info.account_name) } catch {}
  ElMessage.success(t('login.loginSuccess'))
  router.push('/dashboard')
}

const handleLogin = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    if (!captchaVerified.value) { ElMessage.warning(t('login.sliderVerify')); return }
    loading.value = true
    let lastError = ''
    const isEmailLike = form.username.includes('@')
    try {
      // 输入不含 @ 时优先管理员登录
      if (!isEmailLike) {
        try {
          const adminResp = await adminLogin({ username: form.username, password: form.password })
          if (adminResp?.success && adminResp?.token) {
            doAdminSuccess(adminResp)
            return
          }
          lastError = adminResp?.error || 'invalid_credentials'
        } catch (e: any) {
          lastError = e?.response?.data?.error || e?.message || 'invalid_credentials'
        }
      }
      // 尝试客户登录
      try {
        const accountResp: any = await accountLogin({ email: form.username, password: form.password })
        if (accountResp?.success && accountResp?.token) {
          await doCustomerSuccess(accountResp)
          return
        }
        lastError = accountResp?.error || lastError
      } catch (e: any) {
        lastError = e?.response?.data?.error || e?.message || lastError
      }
      // 若先试了管理员，此处不再重试；否则再试管理员
      if (isEmailLike) {
        try {
          const adminResp = await adminLogin({ username: form.username, password: form.password })
          if (adminResp?.success && adminResp?.token) {
            doAdminSuccess(adminResp)
            return
          }
          lastError = adminResp?.error || lastError
        } catch (e: any) {
          lastError = e?.response?.data?.error || e?.message || lastError
        }
      }
      ElMessage.error(mapLoginError(lastError))
      resetCaptcha()
    } finally {
      loading.value = false
    }
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
    too_many_attempts: t('login.tgTooManyAttempts'), invalid_username: t('login.enterUsername'),
  }
  return m[error] || error
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

.topbar {
  position: fixed;
  top: 0; left: 0; right: 0;
  z-index: 100;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 24px;
  gap: 24px;
  background: rgba(11, 13, 19, 0.6);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.is-light .topbar {
  background: rgba(255, 255, 255, 0.7);
  border-bottom-color: rgba(0, 0, 0, 0.06);
}

.topbar-logo {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  font-size: 1.25rem;
  font-weight: 800;
  color: var(--text-1);
  letter-spacing: -0.02em;
  transition: opacity 0.2s;
}
.topbar-logo-icon { border-radius: 6px; }

.topbar-logo:hover { opacity: 0.9; }

.topbar-logo-text em {
  font-style: normal;
  color: var(--accent);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.topbar-nav {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-wrap: wrap;
}

.topbar-nav-item {
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-2);
  text-decoration: none;
  border-radius: 10px;
  transition: color 0.2s, background 0.2s;
}

.topbar-nav-item:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.08);
}

.is-light .topbar-nav-item {
  color: rgba(29, 29, 31, 0.72);
}

.is-light .topbar-nav-item:hover {
  color: var(--text-1);
  background: rgba(0, 0, 0, 0.05);
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

/* 卡片下方官网链接，醒目可见 */
.card-website-link {
  display: block;
  text-align: center;
  margin-top: 12px;
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 500;
  color: var(--accent);
  text-decoration: none;
  border: 1px solid rgba(99, 102, 241, 0.4);
  border-radius: 10px;
  background: rgba(99, 102, 241, 0.1);
  transition: background 0.2s, border-color 0.2s;
}

.card-website-link:hover {
  background: rgba(99, 102, 241, 0.18);
  border-color: var(--accent);
}

.is-light .card-website-link {
  color: var(--accent);
  border-color: rgba(0, 113, 227, 0.4);
  background: rgba(0, 113, 227, 0.08);
}

.is-light .card-website-link:hover {
  background: rgba(0, 113, 227, 0.15);
}

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
.logo-mark-img { border-radius: 14px; box-shadow: 0 8px 24px rgba(59,130,246,.3); }

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
  .topbar { padding: 12px 16px; gap: 12px; }
  .topbar-logo { font-size: 1.1rem; }
  .topbar-nav { gap: 0; }
  .topbar-nav-item { padding: 6px 10px; font-size: 12px; }
  .card { padding: 24px 22px 22px; border-radius: 18px; }
  .hero-title { font-size: 26px; }
  .tab { font-size: 12px; padding: 8px 0; }
}

@media (min-height: 900px) {
  .main { padding-top: 0; }
}
</style>
