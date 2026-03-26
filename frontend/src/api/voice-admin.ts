import request from './index'

export interface VoiceRoute {
  id: number
  country_code: string
  provider_id?: number | null
  priority: number
  cost_per_minute: number
  trunk_profile?: string | null
  dial_prefix?: string | null
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
}) {
  return request.post('/admin/voice/routes', data)
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
