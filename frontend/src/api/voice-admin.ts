import request from './index'

export interface VoiceRoute {
  id: number
  country_code: string
  provider_id?: number | null
  priority: number
  cost_per_minute: number
  trunk_profile?: string | null
  dial_prefix?: string | null
  /** generic=通用 FS/Trunk；vos=对接 VOS（如 VOS3000） */
  gateway_type?: string
  vos_gateway_name?: string | null
  notes?: string | null
  created_at?: string | null
}

export interface VoiceCall {
  id: number
  call_id: string
  account_id: number
  caller?: string | null
  callee?: string | null
  outbound_campaign_id?: number | null
  outbound_campaign_name?: string | null
  voice_route_id?: number | null
  start_time?: string | null
  end_time?: string | null
  duration?: number | null
  status?: string | null
  cost?: number | null
  created_at?: string | null
}

/** 管理端语音账户列表项（与 GET /admin/voice/accounts 对齐） */
export interface VoiceAccountListItem {
  id: number
  account_id: number
  account?: { account_name: string }
  sales_id?: number | null
  sales?: { id: number; username: string; real_name?: string | null } | null
  okcc_account?: string | null
  sip_username?: string | null
  sip_login_hint?: string | null
  external_id?: string | null
  default_caller_id_id?: number | null
  default_caller_number?: string | null
  country_code: string
  balance: number
  max_concurrent_calls?: number
  daily_outbound_limit?: number
  total_calls: number
  total_minutes: number
  status: string
  sync_error?: string | null
  last_sync_at?: string | null
  created_at?: string | null
}

export function getVoiceAccounts(params?: {
  country_code?: string
  status?: string
  account_id?: number
  account_name?: string
  sales_id?: number
  page?: number
  page_size?: number
}) {
  return request.get('/admin/voice/accounts', { params })
}

export function updateVoiceAccount(
  voiceAccountId: number,
  data: {
    status?: string
    max_concurrent_calls?: number
    daily_outbound_limit?: number
    sip_username?: string | null
    sales_id?: number | null
  }
) {
  return request.put(`/admin/voice/accounts/${voiceAccountId}`, data)
}

/** 为已有业务账户开通语音子账户（POST /admin/voice/accounts） */
export function createVoiceAccount(data: {
  account_id: number
  country_code: string
  template_id?: number | null
  assign_mode?: 'inherit' | 'none' | 'explicit'
  sales_id?: number
}) {
  return request.post<{
    success: boolean
    voice_account_id: number
    account_id: number
    okcc_account?: string | null
    sip_username?: string | null
    sip_password?: string | null
    external_id?: string | null
    message?: string
  }>('/admin/voice/accounts', data)
}

export function getVoiceRoutes(params?: { country_code?: string }) {
  return request.get('/admin/voice/routes', { params })
}

export function createVoiceRoute(data: {
  country_code: string
  provider_id?: number | null
  priority?: number
  cost_per_minute?: number
  trunk_profile?: string | null
  dial_prefix?: string | null
  notes?: string | null
  gateway_type?: string
  vos_gateway_name?: string | null
}) {
  return request.post('/admin/voice/routes', data)
}

/** VOS 管理 HTTP 是否配置及可选连通性探测 */
export function getVoiceVosStatus() {
  return request.get<{
    success: boolean
    vos_http_base_configured: boolean
    vos_http_username_set: boolean
    reachable: boolean | null
    detail: string
  }>('/admin/voice/vos/status')
}

export function updateVoiceRoute(routeId: number, data: any) {
  return request.put(`/admin/voice/routes/${routeId}`, data)
}

export function deleteVoiceRoute(routeId: number) {
  return request.delete(`/admin/voice/routes/${routeId}`)
}

export function getVoiceCalls(params?: {
  account_id?: number
  status?: string
  outbound_campaign_id?: number
  start_date?: string
  end_date?: string
  /** created_at | start_time */
  date_basis?: string
  page?: number
  page_size?: number
}) {
  return request.get('/admin/voice/calls', { params })
}

export function getVoiceCallerIds(params?: { account_id?: number }) {
  return request.get('/admin/voice/caller-ids', { params })
}

export function createVoiceCallerId(data: {
  account_id: number
  number_e164: string
  label?: string | null
  trunk_ref?: string | null
  voice_route_id?: number | null
}) {
  return request.post('/admin/voice/caller-ids', data)
}

export function updateVoiceCallerId(
  callerId: number,
  data: {
    label?: string | null
    trunk_ref?: string | null
    status?: 'active' | 'disabled'
    voice_route_id?: number | null
  }
) {
  return request.put(`/admin/voice/caller-ids/${callerId}`, data)
}

export function deleteVoiceCallerId(callerId: number) {
  return request.delete(`/admin/voice/caller-ids/${callerId}`)
}

export function getVoiceCampaigns(params?: { account_id?: number }) {
  return request.get('/admin/voice/campaigns', { params })
}

export function createVoiceCampaign(data: Record<string, unknown>) {
  return request.post('/admin/voice/campaigns', data)
}

export function setVoiceCampaignStatus(campaignId: number, status: string) {
  return request.post(`/admin/voice/campaigns/${campaignId}/status`, { status })
}

export function importVoiceCampaignContacts(campaignId: number, phones: string[]) {
  return request.post(`/admin/voice/campaigns/${campaignId}/contacts`, { phones })
}

export function getVoiceHangupSmsRules(params?: { account_id?: number }) {
  return request.get('/admin/voice/hangup-sms-rules', { params })
}

export function createVoiceHangupSmsRule(data: Record<string, unknown>) {
  return request.post('/admin/voice/hangup-sms-rules', data)
}

export function getVoiceDnc(params?: { account_id?: number }) {
  return request.get('/admin/voice/dnc', { params })
}

export function createVoiceDnc(data: { account_id: number; phone_e164: string; source?: string }) {
  return request.post('/admin/voice/dnc', data)
}

export function deleteVoiceDnc(dncId: number) {
  return request.delete(`/admin/voice/dnc/${dncId}`)
}

/** 重置 SIP 密码，响应中含一次性明文 sip_password */
export function resetVoiceAccountSipPassword(voiceAccountId: number) {
  return request.post(`/admin/voice/accounts/${voiceAccountId}/reset-sip-password`)
}

export function exportVoiceCallsCsv(params?: {
  account_id?: number
  status?: string
  outbound_campaign_id?: number
  start_date?: string
  end_date?: string
  date_basis?: string
}) {
  return request.get('/admin/voice/calls/export', {
    params,
    responseType: 'blob',
  })
}

/** 与后端 GET /admin/voice/ops-metrics 一致 */
export interface VoiceOpsMetrics {
  success: boolean
  window_hours: number
  cdr_webhook_processed: number
  cdr_webhook_failed: number
  campaigns_running: number
  voice_calls_total_24h: number
  voice_calls_connected_24h: number
  voice_answer_rate_24h: number | null
  outbound_contacts_pending: number
}

export function getVoiceOpsMetrics() {
  return request.get<VoiceOpsMetrics>('/admin/voice/ops-metrics')
}
