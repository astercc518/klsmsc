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

// ---------- 请求拦截器 ----------
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const isImpersonateMode = sessionStorage.getItem('impersonate_mode') === '1'

    if (isImpersonateMode) {
      const impersonateApiKey = sessionStorage.getItem('impersonate_api_key')
      if (impersonateApiKey) {
        config.headers['X-API-Key'] = impersonateApiKey
      }
    } else {
      const adminToken = localStorage.getItem('admin_token')
      if (adminToken) {
        config.headers['Authorization'] = `Bearer ${adminToken}`
      } else {
        const apiKey = localStorage.getItem('api_key')
        if (apiKey) {
          config.headers['X-API-Key'] = apiKey
        }
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
  (error) => {
    if (error.response) {
      const { status, data, config: reqConfig } = error.response
      const requestUrl = reqConfig?.url || ''

      switch (status) {
        case 401: {
          if (!isRedirecting) {
            isRedirecting = true
            ElMessage.error('认证失败，请重新登录')
            localStorage.removeItem('api_key')
            localStorage.removeItem('admin_token')
            localStorage.removeItem('admin_id')
            localStorage.removeItem('admin_role')
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

