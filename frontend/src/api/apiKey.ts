import { request } from './index'

export interface ApiKey {
  id: number
  account_id: number
  key_name: string
  api_key: string
  permission: 'read_only' | 'read_write' | 'full'
  ip_whitelist: string[] | null
  rate_limit: number
  status: 'active' | 'disabled' | 'expired'
  usage_count: number
  last_used_at: string | null
  last_used_ip: string | null
  expires_at: string | null
  description: string | null
  created_at: string
  updated_at: string
}

export interface ApiKeyCreate {
  key_name: string
  permission?: 'read_only' | 'read_write' | 'full'
  ip_whitelist?: string[]
  rate_limit?: number
  expires_days?: number
  description?: string
}

export interface ApiKeyCreateResponse extends ApiKey {
  api_secret: string  // 仅创建时返回一次
}

// 获取密钥列表
export const getApiKeys = (params?: { page?: number; page_size?: number; status?: string }) => {
  return request.get('/api-keys', { params })
}

// 获取统计
export const getApiKeyStats = () => {
  return request.get('/api-keys/stats')
}

// 创建密钥
export const createApiKey = (data: ApiKeyCreate) => {
  return request.post<ApiKeyCreateResponse>('/api-keys', data)
}

// 更新密钥
export const updateApiKey = (id: number, data: Partial<ApiKeyCreate>) => {
  return request.put(`/api-keys/${id}`, data)
}

// 重新生成密钥
export const regenerateApiKey = (id: number) => {
  return request.post<ApiKeyCreateResponse>(`/api-keys/${id}/regenerate`)
}

// 删除密钥
export const deleteApiKey = (id: number) => {
  return request.delete(`/api-keys/${id}`)
}
