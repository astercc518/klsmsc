import { request } from './index'

export interface SmsBatch {
  id: number
  account_id: number
  batch_name: string
  template_id: number | null
  file_path: string | null
  file_size: number | null
  total_count: number
  success_count: number
  /** 回执终态：已送达（SMSLog delivered） */
  delivered_count?: number
  /** 通道已接受但仍为 sent：终态回执未到或解析失败（与上游门户可能暂时不一致） */
  sent_awaiting_receipt_count?: number
  failed_count: number
  processing_count: number
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'
  error_message: string | null
  sender_id: string | null
  progress: number
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

// 上传批量发送文件
export const uploadBatchFile = (data: FormData) => {
  return request.post('/batches/upload', data, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

// 获取批次列表
export const getBatches = (params?: { page?: number; page_size?: number; status?: string }) => {
  return request.get('/batches', { params })
}

// 获取批次统计
export const getBatchStats = () => {
  return request.get('/batches/stats')
}

// 获取批次详情
export const getBatchDetail = (id: number) => {
  return request.get(`/batches/${id}`)
}

// 取消批次
export const cancelBatch = (id: number) => {
  return request.delete(`/batches/${id}`)
}

/**
 * 失败记录重新计费并入队。
 *
 * partial=true 表示余额仅够重发前 N 条，已扣的不退；其余条目仍为 failed，
 * 行级 error_message 已写明「余额不足，未能重发」。前端应以 warning 提示。
 */
export const retryBatchFailed = (id: number, opts: { timeout?: number } = {}) => {
  // 新流程：生成新批次重发，正常计费正常路由，source_batch_id 溯源链
  return request.post<{
    success: boolean
    source_batch_id: number
    new_batch_id: number
    retried: number
    enqueued: number
    skipped: number
    out_of_balance: boolean
    charged_amount: number
    errors: string[]
    message: string
  }>(`/batches/${id}/retry-as-new-batch`, undefined, opts.timeout ? { timeout: opts.timeout } : undefined)
}

/** 补发未发送：处理 CSV 中尚未写入 sms_logs 的剩余号码（仅 CSV 上传批次可用） */
export const resendUnsentBatch = (id: number) => {
  return request.post<{ triggered: boolean; unsent_count: number; message: string }>(
    `/batches/${id}/resend-unsent`
  )
}

/**
 * 重新投递「排队中」记录到 Celery（不重复扣费）。
 * 适用于 Worker 异常导致 RabbitMQ 消息丢失、sms_log 卡 queued 的恢复。
 */
export const requeueBatchQueued = (id: number) => {
  return request.post<{
    retried: number
    skipped: number
    errors: string[]
    message: string
  }>(`/batches/${id}/requeue-queued`)
}

/** 导出批次明细 CSV（后端手机号脱敏） */
export const exportBatchRecordsCsv = (id: number) => {
  return request.get(`/batches/${id}/export`, { responseType: 'blob' })
}
