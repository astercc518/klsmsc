<template>
  <div class="login-page" :class="{ 'is-light': !isDark }">
    <!-- 背景 - kaolach 双径向渐变 -->
    <div class="bg-mesh" aria-hidden="true"></div>

    <!-- 顶部工具栏 -->
    <header class="topbar">
      <a href="/" class="topbar-logo" aria-label="kaolach">
        <img src="/kaolach-wordmark.svg?v=koala2" alt="kaolach" class="topbar-wordmark" />
      </a>
      <div class="topbar-badges">
        <span class="trust-pill">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M17 8V6a5 5 0 00-10 0v2H5v14h14V8h-2zm-8 0V6a3 3 0 116 0v2H9z"/></svg>
          {{ $t('login.badge.encrypted') }}
        </span>
        <span class="trust-pill">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z"/></svg>
          {{ $t('login.badge.global') }}
        </span>
        <span class="trust-pill">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M13 2L3 14h7v8l11-14h-8z"/></svg>
          {{ $t('login.badge.fast') }}
        </span>
      </div>
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

    <!-- 主体：左右两栏 -->
    <main class="main">
      <div class="grid">
        <!-- 左：价值主张 -->
        <section class="hero-card" :class="{ show: mounted }" aria-label="平台介绍">
          <h1 class="hero-title">{{ $t('login.hero.title') }}</h1>
          <p class="hero-sub">{{ $t('login.hero.subtitle') }}</p>

          <div class="hero-checks">
            <div class="hero-check">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="#22c55e"><path d="M9 16.2L4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"/></svg>
              {{ $t('login.hero.check1') }}
            </div>
            <div class="hero-check">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="#22c55e"><path d="M9 16.2L4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"/></svg>
              {{ $t('login.hero.check2') }}
            </div>
            <div class="hero-check">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="#22c55e"><path d="M9 16.2L4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"/></svg>
              {{ $t('login.hero.check3') }}
            </div>
          </div>

          <div class="chip-strip">
            <span class="chip">{{ $t('login.chips.intl') }}</span>
            <span class="chip">{{ $t('login.chips.verify') }}</span>
            <span class="chip">{{ $t('login.chips.marketing') }}</span>
            <span class="chip">{{ $t('login.chips.api') }}</span>
            <span class="chip">{{ $t('login.chips.did') }}</span>
            <span class="chip">{{ $t('login.chips.realtime') }}</span>
          </div>

          <div class="feature-grid">
            <div class="feature-tile">
              <h4>{{ $t('login.features.routing.title') }}</h4>
              <p>{{ $t('login.features.routing.desc') }}</p>
            </div>
            <div class="feature-tile">
              <h4>{{ $t('login.features.scale.title') }}</h4>
              <p>{{ $t('login.features.scale.desc') }}</p>
            </div>
            <div class="feature-tile">
              <h4>{{ $t('login.features.pricing.title') }}</h4>
              <p>{{ $t('login.features.pricing.desc') }}</p>
            </div>
            <div class="feature-tile">
              <h4>{{ $t('login.features.support.title') }}</h4>
              <p>{{ $t('login.features.support.desc') }}</p>
            </div>
          </div>

          <div class="hero-stats">
            <div class="stat"><b>190+</b><span>{{ $t('login.stats.countries') }}</span></div>
            <div class="stat"><b>99.9%</b><span>{{ $t('login.stats.uptime') }}</span></div>
            <div class="stat"><b>&lt; 3s</b><span>{{ $t('login.stats.latency') }}</span></div>
          </div>
        </section>

        <!-- 右：登录卡片 -->
        <section class="card" :class="{ show: mounted }" aria-label="登录表单">
          <h3 class="card-title">{{ $t('login.cardTitle') }}</h3>
          <p class="card-micro">{{ $t('login.cardMicro') }}</p>

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
                <svg class="field-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>
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
                  <svg class="field-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
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
                <svg class="field-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><path d="M22 6l-10 7L2 6"/></svg>
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
                <svg class="field-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
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

          <div class="card-divider"></div>

          <div class="card-footer">
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M6.5 1L2 3.2v2.8c0 2.8 1.9 5.3 4.5 6 2.6-.7 4.5-3.2 4.5-6V3.2L6.5 1Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M4.5 6.5l1.3 1.3L8.5 5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <span>{{ $t('login.securityNote') }}</span>
          </div>
          <a href="/" class="card-website-link">{{ $t('login.backToWebsite') }} →</a>
        </section>
      </div>

      <p class="copyright" :class="{ show: mounted }">© 2024 {{ $t('brand.name') }} · All rights reserved</p>
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
          lastError = toLoginErrorString(adminResp?.error) || 'invalid_credentials'
        } catch (e: unknown) {
          lastError = pickAxiosLoginError(e) || lastError || 'invalid_credentials'
        }
      }
      // 尝试客户登录
      try {
        const accountResp: any = await accountLogin({ email: form.username, password: form.password })
        if (accountResp?.success && accountResp?.token) {
          await doCustomerSuccess(accountResp)
          return
        }
        lastError = toLoginErrorString(accountResp?.error) || lastError
      } catch (e: unknown) {
        lastError = pickAxiosLoginError(e) || lastError
      }
      // 若先试了管理员，此处不再重试；否则再试管理员
      if (isEmailLike) {
        try {
          const adminResp = await adminLogin({ username: form.username, password: form.password })
          if (adminResp?.success && adminResp?.token) {
            doAdminSuccess(adminResp)
            return
          }
          lastError = toLoginErrorString(adminResp?.error) || lastError
        } catch (e: unknown) {
          lastError = pickAxiosLoginError(e) || lastError
        }
      }
      const errMsg = mapLoginError(lastError)
      if (errMsg) ElMessage.error(errMsg)
      resetCaptcha()
    } finally {
      loading.value = false
    }
  })
}

/** 从 axios 错误体解析可映射的文案（兼容 500 时 error 为 { code, message } 对象） */
const pickAxiosLoginError = (e: unknown): string => {
  const ex = e as { response?: { data?: { error?: unknown; detail?: unknown } }; message?: unknown }
  const data = ex?.response?.data
  if (data?.error !== undefined) {
    const er = data.error
    if (typeof er === 'string') return er
    if (er && typeof er === 'object') {
      const o = er as { message?: unknown; code?: unknown }
      if (typeof o.message === 'string') return o.message
      if (typeof o.code === 'string') return o.code
    }
  }
  if (typeof data?.detail === 'string') return data.detail
  if (typeof ex?.message === 'string') return ex.message
  return ''
}

/** 将任意 API/axios 错误统一为字符串，避免对非字符串调用 startsWith */
const toLoginErrorString = (input: unknown): string => {
  if (input == null) return ''
  if (typeof input === 'string') return input
  if (typeof input === 'number' || typeof input === 'boolean') return String(input)
  if (typeof input === 'object') {
    const o = input as Record<string, unknown>
    if (typeof o.message === 'string') return o.message
    if (typeof o.code === 'string') return o.code
    if (typeof o.error === 'string') return o.error
    if (o.error && typeof o.error === 'object') {
      const inner = o.error as Record<string, unknown>
      if (typeof inner.message === 'string') return inner.message
      if (typeof inner.code === 'string') return inner.code
    }
  }
  return pickAxiosLoginError(input)
}

const mapLoginError = (error: unknown): string => {
  const raw = toLoginErrorString(error).trim()
  if (!raw) return t('login.invalidCredentials')
  // 全局 500 响应已在 axios 拦截器提示，此处不再重复弹窗
  if (raw === 'Internal server error' || raw === 'INTERNAL_SERVER_ERROR') return ''
  if (raw.startsWith('invalid_credentials')) {
    const parts = raw.split(':')
    return parts[1] ? t('login.invalidCredentialsRemaining', { n: parts[1] }) : t('login.invalidCredentials')
  }
  const m: Record<string, string> = {
    account_locked: t('login.accountLocked'), account_disabled: t('login.accountDisabled'),
    tg_not_bound: t('login.tgNotBound'), code_expired: t('login.tgCodeExpired'),
    code_invalid: t('login.tgCodeInvalid'), send_failed: t('login.tgSendFailed'),
    account_not_bound: t('login.tgNotBound'), cooldown: t('login.tgCooldown'),
    too_many_attempts: t('login.tgTooManyAttempts'), invalid_username: t('login.enterUsername'),
  }
  return m[raw] || raw
}

const resetCaptcha = () => { captchaRef.value?.reset(); captchaVerified.value = false }
</script>


<style scoped>
/* ═══════════════════════════════════════
   kaolach-style Login — 国际大厂质感
   ═══════════════════════════════════════ */
.login-page {
  min-height: 100vh;
  position: relative;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  color: var(--text-primary);
  overflow-x: hidden;
}

/* 背景径向渐变 - kaolach 双色 mesh */
.bg-mesh {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(900px 480px at -8% -10%, rgba(42, 157, 143, 0.18), transparent 55%),
    radial-gradient(900px 480px at 110% 10%, rgba(0, 255, 213, 0.12), transparent 55%),
    radial-gradient(700px 400px at 50% 110%, rgba(253, 181, 42, 0.08), transparent 60%);
  z-index: 0;
}
.is-light .bg-mesh {
  background:
    radial-gradient(900px 480px at -8% -10%, rgba(42, 157, 143, 0.14), transparent 55%),
    radial-gradient(900px 480px at 110% 10%, rgba(24, 99, 220, 0.10), transparent 55%),
    radial-gradient(700px 400px at 50% 110%, rgba(253, 181, 42, 0.06), transparent 60%);
}

/* ---------- Topbar ---------- */
.topbar {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 32px;
  max-width: 1280px;
  width: 100%;
  margin: 0 auto;
}
.topbar-logo {
  display: inline-flex; align-items: center;
  text-decoration: none;
  color: var(--text-primary);
  flex-shrink: 0;
  height: 40px;
}
.topbar-wordmark { height: 36px; width: auto; display: block; }
.topbar-logo:hover { opacity: 0.85; }

.topbar-badges {
  display: flex; gap: 10px; flex-wrap: wrap;
  margin-left: 24px;
}
.trust-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  box-shadow: 0 2px 8px rgba(10, 20, 37, 0.04);
}
.trust-pill svg { color: var(--primary); }

.topbar-right {
  margin-left: auto;
  display: flex; align-items: center; gap: 8px;
}
.topbar-pill {
  display: inline-flex; align-items: center; justify-content: center;
  height: 36px; min-width: 36px; padding: 0 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 0.82rem;
  font-weight: 600;
  transition: all 0.2s;
}
.topbar-pill:hover {
  border-color: var(--primary);
  color: var(--primary);
  transform: translateY(-1px);
}
.lang-pill { font-family: 'Plus Jakarta Sans', sans-serif; }

/* ---------- Main grid ---------- */
.main {
  position: relative;
  z-index: 5;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 28px 32px 64px;
}
.grid {
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  gap: 28px;
  max-width: 1280px;
  width: 100%;
  align-items: start;
}
@media (max-width: 992px) {
  .grid { grid-template-columns: 1fr; }
  .topbar-badges { display: none; }
}
@media (max-width: 600px) {
  .topbar { padding: 14px 18px; }
  .main { padding: 16px 18px 40px; }
}

/* ---------- 左：Hero card ---------- */
.hero-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  padding: 36px 32px;
  box-shadow: 0 12px 32px rgba(10, 20, 37, 0.06);
  opacity: 0;
  transform: translateY(16px);
  transition: opacity 0.6s ease, transform 0.6s ease;
}
.hero-card.show { opacity: 1; transform: translateY(0); }

.hero-title {
  font-size: clamp(28px, 2.8vw, 40px);
  line-height: 1.15;
  font-weight: 800;
  margin: 0 0 12px;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}
.hero-sub {
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 1.6;
  margin: 0 0 22px;
}

.hero-checks {
  display: flex; flex-direction: column; gap: 10px;
  margin-bottom: 18px;
}
.hero-check {
  display: flex; align-items: center; gap: 10px;
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}
.hero-check svg { flex-shrink: 0; }

.chip-strip {
  display: flex; gap: 8px; flex-wrap: wrap;
  margin-bottom: 22px;
}
.chip {
  padding: 7px 12px;
  border-radius: 10px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
}

.feature-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 22px;
}
@media (max-width: 600px) {
  .feature-grid { grid-template-columns: 1fr; }
}
.feature-tile {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 14px 16px;
  box-shadow: 0 2px 6px rgba(10, 20, 37, 0.03);
  transition: transform 0.18s, box-shadow 0.18s, border-color 0.18s;
}
.feature-tile:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 18px rgba(42, 157, 143, 0.10);
  border-color: var(--primary);
}
.feature-tile h4 {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}
.feature-tile p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-tertiary);
}

.hero-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  padding: 18px 0 4px;
  border-top: 1px solid var(--border-subtle);
}
.stat { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; }
.stat b {
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--primary);
  font-feature-settings: 'tnum';
}
.stat span {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}

/* ---------- 右：登录卡 ---------- */
.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  padding: 32px 28px;
  box-shadow: 0 16px 48px rgba(10, 20, 37, 0.08);
  position: sticky;
  top: 24px;
  opacity: 0;
  transform: translateY(16px);
  transition: opacity 0.6s ease 0.15s, transform 0.6s ease 0.15s;
}
.card.show { opacity: 1; transform: translateY(0); }

.card-title {
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.01em;
  margin: 0 0 4px;
  color: var(--text-primary);
}
.card-micro {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 20px;
}

/* Tabs */
.tabs {
  position: relative;
  display: flex;
  background: var(--bg-tertiary);
  border-radius: 10px;
  padding: 4px;
  margin-bottom: 22px;
}
.tab {
  flex: 1;
  position: relative; z-index: 2;
  padding: 9px 12px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  border-radius: 8px;
  transition: color 0.2s;
  font-family: inherit;
}
.tab.active { color: var(--primary); }
.tab:not(.active):hover { color: var(--text-secondary); }
.tab-indicator {
  position: absolute;
  top: 4px; bottom: 4px;
  background: var(--bg-secondary);
  border-radius: 8px;
  box-shadow: 0 2px 6px rgba(10, 20, 37, 0.08);
  transition: left 0.25s cubic-bezier(0.4, 0, 0.2, 1), width 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 1;
}

/* Form */
.form-area { display: flex; flex-direction: column; gap: 14px; }

.field { position: relative; }
.field label {
  display: block;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
  letter-spacing: 0.01em;
}
.input-wrap {
  position: relative;
  display: flex; align-items: center;
}
.field-ico {
  position: absolute;
  left: 14px; top: 50%;
  transform: translateY(-50%);
  color: var(--text-tertiary);
  pointer-events: none;
  z-index: 2;
}
.input-wrap input {
  width: 100%;
  height: 48px;
  padding: 0 16px 0 44px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
  transition: border-color 0.18s, box-shadow 0.18s;
  font-family: inherit;
}
.input-wrap.has-toggle input { padding-right: 44px; }
.input-wrap input::placeholder { color: var(--text-quaternary); }
.input-wrap input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 4px rgba(42, 157, 143, 0.18);
}
.input-wrap input:hover:not(:focus) {
  border-color: var(--border-hover);
}

.pwd-toggle {
  position: absolute;
  right: 8px; top: 50%;
  transform: translateY(-50%);
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.15s, color 0.15s;
}
.pwd-toggle:hover { background: var(--bg-tertiary); color: var(--text-primary); }

.captcha-row { padding: 4px 0; }

.btn-primary {
  display: inline-flex; align-items: center; justify-content: center;
  width: 100%; height: 48px;
  padding: 0 18px;
  background: linear-gradient(135deg, var(--primary), var(--primary-hover));
  color: #ffffff;
  font-size: 14.5px;
  font-weight: 700;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  letter-spacing: 0.01em;
  box-shadow: 0 8px 20px rgba(42, 157, 143, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.2);
  transition: transform 0.15s, box-shadow 0.15s, filter 0.15s;
  font-family: inherit;
  margin-top: 4px;
}
.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.06);
  box-shadow: 0 12px 28px rgba(42, 157, 143, 0.36), inset 0 1px 0 rgba(255, 255, 255, 0.2);
}
.btn-primary:active:not(:disabled) { transform: translateY(0); }
.btn-primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
  box-shadow: none;
}

.btn-loading { display: inline-flex; align-items: center; gap: 8px; }
.dot-spinner {
  width: 14px; height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }

.resend-row {
  margin: 8px 0 0;
  text-align: center;
  font-size: 13px;
}
.resend-row .muted { color: var(--text-tertiary); }
.link-btn {
  background: none; border: none; padding: 0;
  color: var(--primary);
  font-weight: 600;
  cursor: pointer;
  font-size: 13px;
}
.link-btn:hover { text-decoration: underline; }

/* Card footer */
.card-divider {
  height: 1px;
  background: var(--border-subtle);
  margin: 22px 0 14px;
}
.card-footer {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px;
  color: var(--text-tertiary);
}
.card-footer svg { color: var(--success); }
.card-website-link {
  display: block;
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--primary);
  text-decoration: none;
  font-weight: 600;
}
.card-website-link:hover { text-decoration: underline; }

/* Copyright */
.copyright {
  margin-top: 32px;
  font-size: 12px;
  color: var(--text-quaternary);
  text-align: center;
  opacity: 0;
  transition: opacity 0.6s ease 0.3s;
}
.copyright.show { opacity: 1; }

/* Theme icon transition */
.icon-flip-enter-active, .icon-flip-leave-active {
  transition: transform 0.3s, opacity 0.3s;
}
.icon-flip-enter-from { transform: rotate(-90deg); opacity: 0; }
.icon-flip-leave-to { transform: rotate(90deg); opacity: 0; }
</style>
