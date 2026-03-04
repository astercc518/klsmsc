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
