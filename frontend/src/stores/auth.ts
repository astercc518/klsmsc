import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type UserRole = 'admin' | 'user' | 'impersonate'

/**
 * 客户 api_key 的存储后端：sessionStorage 优先（关浏览器即失效，限缩 XSS 后果），
 * 兼容已登录用户的 localStorage 残留——读取时如 session 缺失则从 local 拉一次并迁移。
 */
function readApiKey(): string {
  const fromSession = sessionStorage.getItem('api_key')
  if (fromSession) return fromSession
  const fromLocal = localStorage.getItem('api_key')
  if (fromLocal) {
    // 平滑迁移：把残留的 localStorage 值搬进 sessionStorage，并删除 localStorage 副本
    sessionStorage.setItem('api_key', fromLocal)
    localStorage.removeItem('api_key')
    return fromLocal
  }
  return ''
}

function writeApiKey(key: string): void {
  sessionStorage.setItem('api_key', key)
  // 一并清掉历史 localStorage 副本，杜绝两处都有值的分裂
  localStorage.removeItem('api_key')
}

function clearApiKey(): void {
  sessionStorage.removeItem('api_key')
  localStorage.removeItem('api_key')
}

export const useAuthStore = defineStore('auth', () => {
  const adminToken = ref(localStorage.getItem('admin_token') || '')
  const apiKey = ref(readApiKey())
  const adminId = ref(localStorage.getItem('admin_id') || '')
  const accountName = ref(localStorage.getItem('account_name') || '')

  const isImpersonateMode = computed(
    () => sessionStorage.getItem('impersonate_mode') === '1'
  )

  const isLoggedIn = computed(
    () => !!(isImpersonateMode.value || apiKey.value || adminToken.value)
  )

  const isAdmin = computed(() => !!adminToken.value && !isImpersonateMode.value)

  const role = computed<UserRole>(() => {
    if (isImpersonateMode.value) return 'impersonate'
    if (adminToken.value) return 'admin'
    return 'user'
  })

  function setAdminAuth(token: string, id: string) {
    adminToken.value = token
    adminId.value = id
    localStorage.setItem('admin_token', token)
    localStorage.setItem('admin_id', id)
  }

  function setUserAuth(key: string, name?: string) {
    apiKey.value = key
    accountName.value = name || ''
    writeApiKey(key)
    if (name) localStorage.setItem('account_name', name)
  }

  function logout() {
    adminToken.value = ''
    apiKey.value = ''
    adminId.value = ''
    accountName.value = ''
    localStorage.removeItem('admin_token')
    localStorage.removeItem('admin_refresh_token')
    localStorage.removeItem('admin_id')
    localStorage.removeItem('admin_role')
    clearApiKey()
    localStorage.removeItem('account_name')
    sessionStorage.removeItem('admin_role_verified')
    sessionStorage.removeItem('impersonate_mode')
    sessionStorage.removeItem('impersonate_api_key')
    sessionStorage.removeItem('impersonate_account_id')
    sessionStorage.removeItem('impersonate_account_name')
  }

  return {
    adminToken,
    apiKey,
    adminId,
    accountName,
    isImpersonateMode,
    isLoggedIn,
    isAdmin,
    role,
    setAdminAuth,
    setUserAuth,
    logout,
  }
})
