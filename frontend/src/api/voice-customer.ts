/** 客户控制台语音 API（使用账户 API Key，路径 /api/v1/voice/*） */
import request from './index'

export function getVoiceMe() {
  return request.get('/voice/me')
}

export function getVoiceCallerIdsCustomer() {
  return request.get('/voice/caller-ids')
}

/** 当前账户外呼任务列表 */
export function getVoiceOutboundCampaignsCustomer() {
  return request.get<{
    success: boolean
    items: Array<{
      id: number
      name: string
      status: string
      timezone?: string | null
      window_start?: string | null
      window_end?: string | null
      ai_mode?: string
      max_concurrent?: number
      caller_id_mode?: string
      fixed_caller_id_id?: number | null
    }>
  }>('/voice/outbound-campaigns')
}

export function getVoiceOutboundCampaignCustomer(campaignId: number) {
  return request.get<{ success: boolean; item: Record<string, unknown> }>(
    `/voice/outbound-campaigns/${campaignId}`
  )
}

export function createVoiceOutboundCampaignCustomer(data: Record<string, unknown>) {
  return request.post<{ success: boolean; id: number }>('/voice/outbound-campaigns', data)
}

export function updateVoiceOutboundCampaignCustomer(
  campaignId: number,
  data: Record<string, unknown>
) {
  return request.put(`/voice/outbound-campaigns/${campaignId}`, data)
}

export function setVoiceOutboundCampaignStatusCustomer(campaignId: number, status: string) {
  return request.post(`/voice/outbound-campaigns/${campaignId}/status`, { status })
}

export function importVoiceCampaignContactsCustomer(campaignId: number, phones: string[]) {
  return request.post<{ success: boolean; imported: number }>(
    `/voice/outbound-campaigns/${campaignId}/contacts`,
    { phones }
  )
}

export function importVoiceCampaignContactsCsvCustomer(campaignId: number, file: File) {
  const form = new FormData()
  form.append('file', file)
  return request.post<{ success: boolean; imported: number }>(
    `/voice/outbound-campaigns/${campaignId}/contacts/csv`,
    form
  )
}

export function getVoiceCampaignContactsCustomer(
  campaignId: number,
  params?: { status?: string; page?: number; page_size?: number }
) {
  return request.get<{
    success: boolean
    total: number
    page: number
    page_size: number
    items: Array<Record<string, unknown>>
  }>(`/voice/outbound-campaigns/${campaignId}/contacts`, { params })
}

export function getVoiceCallsCustomer(params?: {
  page?: number
  page_size?: number
  start_date?: string
  end_date?: string
  date_basis?: string
  /** initiated | ringing | answered | busy | failed | completed */
  status?: string
  /** inbound | outbound */
  direction?: string
  /** 须为本账户外呼任务 */
  outbound_campaign_id?: number
}) {
  return request.get('/voice/calls', { params })
}

export function exportVoiceCallsCustomerCsv(params?: {
  start_date?: string
  end_date?: string
  date_basis?: string
  status?: string
  direction?: string
  outbound_campaign_id?: number
}) {
  return request.get('/voice/calls/export', {
    params,
    responseType: 'blob',
  })
}
