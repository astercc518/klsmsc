import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type UserRole = 'admin' | 'user' | 'impersonate'

export const useAuthStore = defineStore('auth', () => {
  const adminToken = ref(localStorage.getItem('admin_token') || '')
  const apiKey = ref(localStorage.getItem('api_key') || '')
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
    localStorage.setItem('api_key', key)
    if (name) localStorage.setItem('account_name', name)
  }

  function logout() {
    adminToken.value = ''
    apiKey.value = ''
    adminId.value = ''
    accountName.value = ''
    localStorage.removeItem('admin_token')
    localStorage.removeItem('admin_id')
    localStorage.removeItem('api_key')
    localStorage.removeItem('account_name')
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
