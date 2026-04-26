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

// --- 分组 / 批量 / 审计 / 导入导出 ---

export interface GroupedConfigItem extends SystemConfig {
  category: string
  updated_by_name?: string
}

export interface GroupedConfigsResponse {
  categories: Array<{ key: string; label: string; label_en: string }>
  groups: Record<string, GroupedConfigItem[]>
}

export function getConfigsGrouped(): Promise<GroupedConfigsResponse> {
  return request({ url: '/admin/configs/grouped', method: 'get' })
}

export function batchUpdateConfigs(items: Record<string, string>): Promise<{ success: boolean; updated: number }> {
  return request({ url: '/admin/configs', method: 'put', data: { items } })
}

export interface AuditLogItem {
  id: number
  config_key: string
  action: 'create' | 'update' | 'delete'
  old_value: string | null
  new_value: string | null
  admin_id: number | null
  admin_name: string
  created_at: string
}

export function getConfigAuditLogs(params?: {
  config_key?: string
  page?: number
  limit?: number
}): Promise<{ total: number; items: AuditLogItem[] }> {
  return request({ url: '/admin/configs-audit', method: 'get', params })
}

export function exportConfigs(): Promise<{ configs: any[]; total: number }> {
  return request({ url: '/admin/configs-export', method: 'get' })
}

export function importConfigs(items: any[], overwrite = true): Promise<{ success: boolean; created: number; updated: number; skipped: number }> {
  return request({ url: '/admin/configs-import', method: 'post', data: { items, overwrite } })
}

// --- 系统日志 ---

export interface AdminLogItem {
  id: number
  admin_id: number | null
  admin_name: string
  module: string
  module_label: string
  action: string
  target_type: string | null
  target_id: string | null
  title: string
  detail: string | null
  ip_address: string | null
  status: 'success' | 'failed'
  error_message: string | null
  created_at: string
}

export function getSystemLogs(params?: {
  page?: number
  page_size?: number
  module?: string
  action?: string
  keyword?: string
  admin_name?: string
  start_date?: string
  end_date?: string
}): Promise<{ total: number; items: AdminLogItem[]; page: number; page_size: number }> {
  return request({ url: '/admin/system/logs', method: 'get', params })
}

export function getSystemLogModules(): Promise<{ modules: Record<string, string> }> {
  return request({ url: '/admin/system/logs/modules', method: 'get' })
}

export function getSystemLogStats(): Promise<{ total: number; today: number; by_module: Record<string, { count: number; label: string }> }> {
  return request({ url: '/admin/system/logs/stats', method: 'get' })
}

export interface RiskyOpItem {
  id: number
  admin_name: string
  module: string
  module_label: string
  action: string
  status: 'success' | 'failed'
  title: string
  created_at: string
}

export interface SecurityStatsResponse {
  today_success: number
  today_failed: number
  unique_ips_today: number
  daily_trend: Array<{ day: string; success: number; failed: number }>
  top_failed_ips: Array<{ ip: string; total: number; failed: number; last_time: string | null }>
  recent_events: Array<{
    id: number
    admin_name: string
    action: string
    status: 'success' | 'failed'
    ip_address: string | null
    title: string
    created_at: string
  }>
  recent_risky_ops: RiskyOpItem[]
}

export function getSecurityStats(): Promise<SecurityStatsResponse> {
  return request({ url: '/admin/system/security-stats', method: 'get' })
}

export function exportSystemLogs(params?: {
  module?: string
  action?: string
  keyword?: string
  admin_name?: string
  start_date?: string
  end_date?: string
}): Promise<AdminLogItem[]> {
  return request({ url: '/admin/system/logs/export', method: 'get', params })
}

// --- 服务管理 ---
export interface ContainerInfo {
  name: string
  state: string
  status: string
  cpu_pct: number | null
  mem_usage_mb: number | null
  mem_limit_mb: number | null
  mem_pct: number | null
  net_rx_mb: number | null
  net_tx_mb: number | null
}

export interface ServicesStatusResponse {
  containers: ContainerInfo[]
  services: Record<string, { name: string; status: string; message: string }>
}

export function getServicesStatus(): Promise<ServicesStatusResponse> {
  return request({ url: '/admin/system/services', method: 'get' })
}
