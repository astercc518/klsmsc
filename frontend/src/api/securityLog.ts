import { request } from './index'

// 安全日志相关API
export const securityLogApi = {
  // 查询安全日志列表
  list(params: {
    page?: number
    page_size?: number
    event_type?: string
    level?: string
    start_date?: string
    end_date?: string
  }) {
    return request.get('/security-logs', { params })
  },

  // 获取安全统计
  getStats() {
    return request.get('/security-logs/stats')
  },

  // 查询登录记录
  getLoginAttempts(params: {
    page?: number
    page_size?: number
    success?: boolean
  }) {
    return request.get('/login-attempts', { params })
  }
}
