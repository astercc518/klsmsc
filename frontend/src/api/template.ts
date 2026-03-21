import { request } from './index'

export interface Template {
  id: number
  account_id: number
  name: string
  category: 'verification' | 'notification' | 'marketing'
  content: string
  variables: string[] | null
  status: 'pending' | 'approved' | 'rejected' | 'disabled'
  reject_reason: string | null
  usage_count: number
  approved_by: number | null
  approved_at: string | null
  created_at: string
  updated_at: string
}

export interface TemplateCreate {
  name: string
  category: 'verification' | 'notification' | 'marketing'
  content: string
  variables?: string[]
}

export interface TemplateUpdate {
  name?: string
  category?: 'verification' | 'notification' | 'marketing'
  content?: string
  variables?: string[]
}

export interface TemplateListParams {
  page?: number
  page_size?: number
  category?: string
  status?: string
  keyword?: string
}

// 获取模板列表
export const getTemplates = (params?: TemplateListParams) => {
  return request.get('/templates', { params })
}

// 获取模板详情
export const getTemplate = (id: number) => {
  return request.get(`/templates/${id}`)
}

// 创建模板
export const createTemplate = (data: TemplateCreate) => {
  return request.post('/templates', data)
}

// 更新模板
export const updateTemplate = (id: number, data: TemplateUpdate) => {
  return request.put(`/templates/${id}`, data)
}

// 删除模板
export const deleteTemplate = (id: number) => {
  return request.delete(`/templates/${id}`)
}

// 管理员 - 获取所有模板
export const adminGetTemplates = (params?: TemplateListParams & { account_id?: number }) => {
  return request.get('/admin/templates', { params })
}

// 管理员 - 审核模板
export const approveTemplate = (id: number, data: { status: string; reject_reason?: string }) => {
  return request.post(`/admin/templates/${id}/approve`, data)
}
