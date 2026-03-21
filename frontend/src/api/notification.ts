import { request } from './index'

// 通知相关API
export const notificationApi = {
  // 查询通知列表
  list(params: {
    page?: number
    page_size?: number
    is_read?: boolean
    notification_type?: string
  }) {
    return request.get('/notifications', { params })
  },

  // 获取通知统计
  getStats() {
    return request.get('/notifications/stats')
  },

  // 标记为已读
  markRead(id: number) {
    return request.put(`/notifications/${id}/read`)
  },

  // 全部标记为已读
  markAllRead() {
    return request.post('/notifications/mark-all-read')
  },

  // 删除通知
  delete(id: number) {
    return request.delete(`/notifications/${id}`)
  }
}
