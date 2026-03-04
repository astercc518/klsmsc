import request from './index'

// ============ 工单类型定义 ============

export interface Ticket {
  id: number
  ticket_no: string
  ticket_type: string
  priority: string
  category?: string
  title: string
  description?: string
  attachments?: string[]
  status: string
  account_id?: number
  account_name?: string
  assigned_to?: number
  assignee_name?: string
  resolution?: string
  satisfaction_rating?: number
  created_at?: string
  updated_at?: string
  resolved_at?: string
  closed_at?: string
}

export interface TicketReply {
  id: number
  reply_by_type: string
  reply_by_name: string
  content: string
  attachments?: string[]
  is_internal?: boolean
  is_solution?: boolean
  source?: string
  created_at?: string
}

export interface TicketDetail extends Ticket {
  replies: TicketReply[]
  extra_data?: any
  tg_user_id?: string
  account_email?: string
  satisfaction_comment?: string
  assigned_at?: string
}

// ============ 客户端工单接口 ============

// 获取我的工单列表
export function getMyTickets(params?: {
  page?: number
  page_size?: number
  status?: string
  ticket_type?: string
}) {
  return request.get('/tickets', { params })
}

// 创建工单
export function createTicket(data: {
  ticket_type?: string
  priority?: string
  category?: string
  title: string
  description?: string
  attachments?: string[]
  extra_data?: any
}) {
  return request.post('/tickets', data)
}

// 获取工单详情
export function getTicketDetail(ticketId: number) {
  return request.get(`/tickets/${ticketId}`)
}

// 回复工单
export function replyTicket(ticketId: number, data: {
  content: string
  attachments?: string[]
}) {
  return request.post(`/tickets/${ticketId}/reply`, data)
}

// 评价工单
export function rateTicket(ticketId: number, rating: number, comment?: string) {
  return request.post(`/tickets/${ticketId}/rate`, null, {
    params: { rating, comment }
  })
}

// ============ 管理员工单接口 ============

// 获取所有工单列表
export function getAdminTickets(params?: {
  page?: number
  page_size?: number
  status?: string
  ticket_type?: string
  priority?: string
  assigned_to?: number
  keyword?: string
}) {
  return request.get('/admin/tickets', { params })
}

// 获取工单仪表板
export function getTicketsDashboard() {
  return request.get('/admin/tickets/dashboard')
}

// 获取工单详情（管理员）
export function getAdminTicketDetail(ticketId: number) {
  return request.get(`/admin/tickets/${ticketId}`)
}

// 分配工单
export function assignTicket(ticketId: number, adminId: number) {
  return request.post(`/admin/tickets/${ticketId}/assign`, { admin_id: adminId })
}

// 管理员回复工单
export function adminReplyTicket(ticketId: number, data: {
  content: string
  attachments?: string[]
  is_internal?: boolean
}) {
  return request.post(`/admin/tickets/${ticketId}/reply`, data)
}

// 解决工单
export function resolveTicket(ticketId: number, resolution: string) {
  return request.post(`/admin/tickets/${ticketId}/resolve`, { resolution })
}

// 关闭工单
export function closeTicket(ticketId: number, reason?: string) {
  return request.post(`/admin/tickets/${ticketId}/close`, null, {
    params: { reason }
  })
}

// 更新工单状态
export function updateTicketStatus(ticketId: number, status: string) {
  return request.put(`/admin/tickets/${ticketId}/status`, null, {
    params: { status }
  })
}

// 更新工单
export function updateTicket(ticketId: number, data: {
  priority?: string
  category?: string
  title?: string
  status?: string
}) {
  return request.put(`/admin/tickets/${ticketId}`, data)
}

// 获取快捷回复模板
export function getTicketTemplates(templateType?: string) {
  return request.get('/admin/tickets/templates', {
    params: { template_type: templateType }
  })
}
