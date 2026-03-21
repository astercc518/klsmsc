import { request } from './index'

// 子账户相关API
export const subAccountApi = {
  // 查询子账户列表
  list(params: {
    page?: number
    page_size?: number
    role?: string
    status?: string
  }) {
    return request.get('/sub-accounts', { params })
  },

  // 获取子账户统计
  getStats() {
    return request.get('/sub-accounts/stats')
  },

  // 创建子账户
  create(data: {
    username: string
    email?: string
    password: string
    role: 'viewer' | 'operator' | 'manager'
    permissions?: any
    rate_limit?: number
    daily_limit?: number
    ip_whitelist?: string[]
    description?: string
  }) {
    return request.post('/sub-accounts', data)
  },

  // 更新子账户
  update(id: number, data: any) {
    return request.put(`/sub-accounts/${id}`, data)
  },

  // 删除子账户
  delete(id: number) {
    return request.delete(`/sub-accounts/${id}`)
  },

  // 重置密码
  resetPassword(id: number, newPassword: string) {
    return request.post(`/sub-accounts/${id}/reset-password`, null, {
      params: { new_password: newPassword }
    })
  }
}
