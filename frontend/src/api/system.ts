import request from './index'

// --- Types ---

export interface SystemConfig {
  id: number
  config_key: string
  config_value: string
  config_type: 'string' | 'number' | 'boolean' | 'json'
  description?: string
  is_public: boolean
  updated_at?: string
  updated_by?: number
}

export interface CreateConfigRequest {
  config_key: string
  config_value: string
  config_type?: string
  description?: string
  is_public?: boolean
}

export interface UpdateConfigRequest {
  config_value: string
  description?: string
  is_public?: boolean
}

// --- API ---

export function getConfigs(params?: {
  is_public?: boolean
  search?: string
}): Promise<SystemConfig[]> {
  return request({
    url: '/admin/configs',
    method: 'get',
    params
  })
}

export function getConfig(key: string): Promise<SystemConfig> {
  return request({
    url: `/admin/configs/${key}`,
    method: 'get'
  })
}

export function createConfig(data: CreateConfigRequest) {
  return request({
    url: '/admin/configs',
    method: 'post',
    data
  })
}

export function updateConfig(key: string, data: UpdateConfigRequest) {
  return request({
    url: `/admin/configs/${key}`,
    method: 'put',
    data
  })
}

export function deleteConfig(key: string) {
  return request({
    url: `/admin/configs/${key}`,
    method: 'delete'
  })
}
