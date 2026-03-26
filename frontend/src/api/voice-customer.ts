/** 客户控制台语音 API（使用账户 API Key，路径 /api/v1/voice/*） */
import request from './index'

export function getVoiceMe() {
  return request.get('/voice/me')
}

export function getVoiceCallerIdsCustomer() {
  return request.get('/voice/caller-ids')
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
