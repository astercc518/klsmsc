import axios from 'axios'
import type { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

const apiBaseURL = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api/v1`
  : '/api/v1'

export const request: AxiosInstance = axios.create({
  baseURL: apiBaseURL,
  timeout: 120000,
})

// 防止 401 时重复弹窗
let isRedirecting = false

// ---------- access token 自动刷新 ----------
// 拦截器在第一次 401 时调 /admin/auth/refresh 换新 token；
// 队列其他并发请求等待刷新完成后用新 token 重发，全部失败再跳登录。
let isRefreshing = false
let refreshWaiters: Array<(t: string | null) => void> = []

async function tryRefreshAdminToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem('admin_refresh_token')
  if (!refreshToken) return null
  try {
    const resp = await axios.post(`${apiBaseURL}/admin/auth/refresh`, {
      refresh_token: refreshToken,
    }, { timeout: 15000 })
    const data = resp.data || {}
    if (data.success && data.token) {
      localStorage.setItem('admin_token', data.token)
      if (data.refresh_token) {
        localStorage.setItem('admin_refresh_token', data.refresh_token)
      }
      return data.token
    }
    return null
  } catch {
    return null
  }
}

/**
 * 客户控制台走「账户 API Key」鉴权的接口（后端 Depends(get_current_account)）。
 * 管理员若同时存在 admin_token 与本地 api_key，原先只发 Bearer 会导致 /batches 等 401，
 * 表现成「列表/统计偶发异常、详情加载失败」等。
 */
/** 鉴权入口路径：登录/注册/找回密码/Telegram 验证。这些请求绝不能带历史 token，
 *  否则浏览器 localStorage 残留的旧 api_key 会被后端中间件拿去查 → 当账户已被删除/禁用时，
 *  直接拒掉登录请求本身（即 TG15066V01 报"权限不足"现象）。
 */
export function isAuthEntryPath(url: string | undefined): boolean {
  if (!url) return false
  const path = url.split('?')[0]
  return (
    path.startsWith('/account/login') ||
    path.startsWith('/account/register') ||
    path.startsWith('/account/forgot-password') ||
    path.startsWith('/account/reset-password') ||
    path.startsWith('/account/telegram/') ||
    path.startsWith('/admin/login') ||
    path.startsWith('/admin/auth/refresh')
  )
}

function shouldAttachCustomerApiKey(url: string | undefined): boolean {
  if (!url) return false
  const path = url.split('?')[0]
  if (path.startsWith('/admin/')) return false
  if (isAuthEntryPath(url)) return false
  const prefixes = [
    '/batches',
    '/templates',
    '/sms/',
    '/account/',
    '/channels/list',
    '/packages',
    '/my-packages',
    '/api-keys',
    '/sub-accounts',
    '/scheduled-tasks',
    '/notifications',
    '/security-logs',
    '/login-attempts',
    '/tickets',
    '/data/',
    '/reports/',
  ]
  return prefixes.some((p) => path === p || path.startsWith(`${p}/`) || path.startsWith(`${p}?`))
}

// ---------- 请求拦截器 ----------
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // 鉴权入口（登录/注册/刷新等）任何情况下都不带历史 token；显式 strip 避免 axios 默认头泄漏
    if (isAuthEntryPath(config.url)) {
      if (config.headers) {
        delete (config.headers as any)['X-API-Key']
        delete (config.headers as any)['Authorization']
      }
      return config
    }

    const isImpersonateMode = sessionStorage.getItem('impersonate_mode') === '1'

    if (isImpersonateMode) {
      const impersonateApiKey = sessionStorage.getItem('impersonate_api_key')
      const fallbackApiKey = localStorage.getItem('api_key')
      const apiKeyToUse = impersonateApiKey || fallbackApiKey
      if (apiKeyToUse) config.headers['X-API-Key'] = apiKeyToUse
    } else {
      const adminToken = localStorage.getItem('admin_token')
      const apiKey = localStorage.getItem('api_key')
      if (apiKey && adminToken && shouldAttachCustomerApiKey(config.url)) {
        config.headers['X-API-Key'] = apiKey
        config.headers['Authorization'] = `Bearer ${adminToken}`
      } else if (adminToken) {
        config.headers['Authorization'] = `Bearer ${adminToken}`
      } else if (apiKey) {
        config.headers['X-API-Key'] = apiKey
      }
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// ---------- 响应拦截器 ----------
request.interceptors.response.use(
  (response: AxiosResponse) => {
    return response.data
  },
  async (error) => {
    if (error.response) {
      const { status, data, config: reqConfig } = error.response
      const requestUrl = reqConfig?.url || ''

      switch (status) {
        case 401: {
          // 先尝试 refresh token 自动续期（仅 admin 路径 + 非 refresh 端点本身）
          const isAdminCall = requestUrl.startsWith('/admin/') && !requestUrl.startsWith('/admin/auth/refresh')
          const hasRefresh = !!localStorage.getItem('admin_refresh_token')
          const alreadyRetried = (reqConfig as any)._retried
          if (isAdminCall && hasRefresh && !alreadyRetried) {
            // 标记防递归
            ;(reqConfig as any)._retried = true
            // 多个并发 401 共用一次刷新
            if (isRefreshing) {
              return new Promise((resolve, reject) => {
                refreshWaiters.push((newToken) => {
                  if (newToken) {
                    reqConfig.headers = reqConfig.headers || {}
                    reqConfig.headers['Authorization'] = `Bearer ${newToken}`
                    resolve(request(reqConfig))
                  } else {
                    reject(error)
                  }
                })
              })
            }
            isRefreshing = true
            const newToken = await tryRefreshAdminToken()
            isRefreshing = false
            const waiters = refreshWaiters
            refreshWaiters = []
            waiters.forEach((cb) => cb(newToken))
            if (newToken) {
              reqConfig.headers = reqConfig.headers || {}
              reqConfig.headers['Authorization'] = `Bearer ${newToken}`
              return request(reqConfig)
            }
            // refresh 失败 → 走下面的强制登出流程
          }

          if (!isRedirecting) {
            isRedirecting = true
            // 后端 ACCOUNT_INVALID = api_key 对应账户被删/禁用 → 给出明确提示，
            // 顺带清掉所有残留 token，避免下次进登录页又被同样的脏 token 拦
            const isAccountInvalid = data?.error?.code === 'ACCOUNT_INVALID'
            ElMessage.error(isAccountInvalid ? '账户已禁用或被删除，请重新登录' : '认证失败，请重新登录')
            localStorage.removeItem('api_key')
            localStorage.removeItem('admin_token')
            localStorage.removeItem('admin_refresh_token')
            localStorage.removeItem('admin_id')
            localStorage.removeItem('admin_role')
            sessionStorage.removeItem('admin_role_verified')
            sessionStorage.removeItem('impersonate_mode')
            sessionStorage.removeItem('impersonate_api_key')
            window.location.href = '/login'
          }
          break
        }
        case 403:
          ElMessage.error('权限不足')
          break
        case 404:
          ElMessage.error('请求的资源不存在')
          break
        case 422:
          // 422 验证错误由调用方自行处理
          break
        case 429:
          ElMessage.warning('请求过于频繁，请稍后重试')
          break
        default:
          if (status >= 500) {
            ElMessage.error('服务器错误，请稍后重试')
          } else {
            ElMessage.error(data?.error?.message || data?.detail || '请求失败')
          }
      }
    } else if (error.code === 'ECONNABORTED') {
      ElMessage.error('请求超时，请检查网络连接')
    } else {
      ElMessage.error('网络错误，请检查网络连接')
    }

    return Promise.reject(error)
  }
)

export default request

