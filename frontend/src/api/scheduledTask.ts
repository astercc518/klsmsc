import { request } from './index'

// 定时任务相关API
export const scheduledTaskApi = {
  // 查询定时任务列表
  list(params: {
    page?: number
    page_size?: number
    status?: string
    frequency?: string
  }) {
    return request.get('/scheduled-tasks', { params })
  },

  // 获取任务统计
  getStats() {
    return request.get('/scheduled-tasks/stats')
  },

  // 创建定时任务
  create(data: {
    task_name: string
    template_id?: number
    phone_numbers: string[]
    content?: string
    sender_id?: string
    frequency: 'once' | 'daily' | 'weekly' | 'monthly'
    scheduled_time: string
    repeat_config?: any
  }) {
    return request.post('/scheduled-tasks', data)
  },

  // 获取任务详情
  get(id: number) {
    return request.get(`/scheduled-tasks/${id}`)
  },

  // 更新任务
  update(id: number, data: any) {
    return request.put(`/scheduled-tasks/${id}`, data)
  },

  // 删除任务
  delete(id: number) {
    return request.delete(`/scheduled-tasks/${id}`)
  },

  // 立即执行任务
  execute(id: number) {
    return request.post(`/scheduled-tasks/${id}/execute`)
  }
}
