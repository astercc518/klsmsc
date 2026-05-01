import { request } from './index'

export interface AdminBatchItem {
  id: number
  account_id: number
  account_name?: string
  batch_name: string
  total_count: number
  success_count: number
  delivered_count: number
  failed_count: number
  processing_count: number
  status: 'pending' | 'processing' | 'paused' | 'completed' | 'failed' | 'cancelled'
  progress: number
  error_message?: string | null
  created_at?: string | null
  updated_at?: string | null
  started_at?: string | null
  completed_at?: string | null
}

export interface AdminBatchDetail extends AdminBatchItem {
  status_counts: Record<string, number>
  current_channel?: {
    id: number
    channel_code: string
    channel_name: string
    protocol: string
    status: string
    connection_status?: string | null
  } | null
  refundable_count: number
}

export interface PreviewSwitchResult {
  success: boolean
  reason?: string
  batch_id?: number
  new_channel_id?: number
  new_channel_code?: string
  unsent_count?: number
  total_diff?: number
  balance_before?: number
  balance_after_estimate?: number
  balance_sufficient?: boolean
}

export interface ListBatchesParams {
  account_id?: number
  channel_id?: number
  status?: string
  keyword?: string
  start_date?: string
  end_date?: string
  page?: number
  page_size?: number
}

export const listAdminBatches = (params: ListBatchesParams = {}) =>
  request.get<{ success: boolean; total: number; page: number; page_size: number; items: AdminBatchItem[] }>(
    '/admin/batches',
    { params }
  )

export const getAdminBatch = (id: number) =>
  request.get<{ success: boolean; batch: AdminBatchDetail; error?: string }>(`/admin/batches/${id}`)

export const pauseBatch = (id: number) =>
  request.post<{ success: boolean; reason?: string; unsent_count?: number; warning?: string }>(
    `/admin/batches/${id}/pause`
  )

export const resumeBatch = (id: number, body: { new_channel_id?: number } = {}) =>
  request.post<{ success: boolean; reason?: string; unsent_count?: number; requeued_ok?: number; switch_channel?: any }>(
    `/admin/batches/${id}/resume`,
    body
  )

export const clearBatchQueue = (id: number) =>
  request.post<{ success: boolean; reason?: string; cancelled_logs?: number }>(
    `/admin/batches/${id}/clear-queue`
  )

export const previewSwitchChannel = (id: number, new_channel_id: number) =>
  request.post<PreviewSwitchResult>(`/admin/batches/${id}/preview-switch-channel`, { new_channel_id })
