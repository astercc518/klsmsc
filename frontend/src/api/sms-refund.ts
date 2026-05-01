import { request } from './index'

export interface RefundCandidate {
  sms_log_id: number
  message_id: string
  account_id: number
  channel_id?: number | null
  batch_id?: number | null
  phone_number: string
  country_code?: string | null
  cost_price: number
  selling_price: number
  currency?: string
  status: string
  error_message?: string | null
  submit_time?: string | null
  upstream_message_id?: string | null
  category: string
}

export interface ListRefundableParams {
  account_id?: number
  batch_id?: number
  channel_id?: number
  keyword?: string
  page?: number
  page_size?: number
}

export const listRefundable = (params: ListRefundableParams = {}) =>
  request.get<{ success: boolean; total: number; page: number; page_size: number; items: RefundCandidate[] }>(
    '/admin/sms/refundable',
    { params }
  )

export const previewRefund = (smsLogId: number) =>
  request.get<{
    success: boolean
    eligible: boolean
    reason: string
    sms_log_id: number
    message_id: string
    account_id: number
    amount_to_refund: number
    currency?: string
    error_message?: string | null
    upstream_message_id?: string | null
    refunded_at?: string | null
  }>(`/admin/sms/${smsLogId}/refund/preview`)

export const executeRefund = (smsLogId: number, note?: string) =>
  request.post<{
    success: boolean
    reason?: string
    amount?: number
    balance_after?: number
    message_id?: string
    account_id?: number
    category?: string
  }>(`/admin/sms/${smsLogId}/refund`, { note })

export const executeRefundBatch = (sms_log_ids: number[], note?: string) =>
  request.post<{
    success: boolean
    error?: string
    ok?: number
    failed?: number
    total_amount?: number
    failures?: { sms_log_id: number; reason: string }[]
  }>('/admin/sms/refund-batch', { sms_log_ids, note })
