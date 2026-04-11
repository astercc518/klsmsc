import request from './index'

export interface DataProduct {
  id: number
  product_code: string
  product_name: string
  description: string
  price_per_number: string
  currency: string
  stock_count: number
  min_purchase: number
  max_purchase: number
  filter_criteria: any
  product_type: 'data_only' | 'combo' | 'data_and_send'
  sms_quota: number | null
  sms_unit_price: string | null
  bundle_price: string | null
  bundle_discount: string | null
  status: string
  total_sold: number
  created_at: string
}

/** 私库号码来源：manual=手工上传分表；purchased=公海购入绑定；mixed=同维度分组内两者兼有 */
export type LibraryOrigin = 'manual' | 'purchased' | 'mixed'

export interface DataNumber {
  id: number
  phone_number: string
  country_code: string
  carrier: string
  tags: string[]
  status: string
  source: string
  source_label: string
  purpose: string
  purpose_label: string
  data_date: string | null
  freshness: string
  freshness_label: string
  use_count: number
  last_used_at: string | null
  created_at: string | null
  /** 分页列表 / 导出 CSV 等接口返回 */
  library_origin?: LibraryOrigin
}

export interface DataOrder {
  id: number
  order_no: string
  account_id: number
  product_id: number
  product_name: string
  quantity: number
  unit_price: string
  total_price: string
  order_type: 'data_only' | 'combo' | 'data_and_send'
  status: string
  executed_count: number
  cancel_reason: string | null
  refund_amount: string | null
  created_at: string
  executed_at: string | null
  refunded_at: string | null
}

// ============ 商品 ============

export const getDataProducts = (params: {
  page?: number
  page_size?: number
  product_type?: string
  source?: string
  purpose?: string
  freshness?: string
  carrier?: string
  country?: string
  tag?: string
}) => {
  return request({ url: '/data/products', method: 'get', params })
}

export function getCarriers(params?: { country_code?: string }) {
  return request({ url: '/data/carriers', method: 'get', params })
}

// ============ 预览 ============

export function previewDataSelection(data: any) {
  return request({ url: '/data/preview', method: 'post', data })
}

// ============ 购买 ============

export function buyToStock(data: { product_id?: number; filter_criteria?: any; quantity: number }) {
  return request({ url: '/data/buy-to-stock', method: 'post', data })
}

export function buyCombo(data: { product_id: number; quantity: number }) {
  return request({ url: '/data/buy-combo', method: 'post', data })
}

export function buyAndSend(data: { product_id?: number; filter_criteria?: any; quantity: number; message: string; messages?: string[]; carrier?: string }) {
  return request({ url: '/data/buy-and-send', method: 'post', data, timeout: 300000 })
}

// ============ 订单 ============

export function createDataOrder(data: { product_id?: number; filter_criteria?: any; quantity: number }) {
  return request({ url: '/data/orders', method: 'post', data })
}

export function getMyOrders(params?: { page?: number; page_size?: number; status?: string }) {
  return request({ url: '/data/orders', method: 'get', params })
}

export function getOrderDetail(orderId: number) {
  return request({ url: `/data/orders/${orderId}`, method: 'get' })
}

export function cancelOrder(orderId: number, data?: { reason?: string }) {
  return request({ url: `/data/orders/${orderId}/cancel`, method: 'post', data })
}

// ============ 评分 ============

export function rateProduct(productId: number, params: { rating: number; order_id?: number; comment?: string }) {
  return request({ url: `/data/products/${productId}/rate`, method: 'post', params })
}

export function getProductRatings(productId: number) {
  return request({ url: `/data/products/${productId}/ratings`, method: 'get' })
}

// ============ 私库 ============

/** max_batches: 0 = 全量（较慢，短信发送页私库分组）；省略则后端默认仅最近若干批次卡片 */
export function getMyNumbersSummary(params?: { max_batches?: number }) {
  // 与全局 axios 超时一致：大账户首次汇总可能超过 60s，避免误报「网络超时」
  const timeout = 180000
  return request({
    url: '/data/my-numbers/summary',
    method: 'get',
    params,
    timeout,
  })
}

export function getMyNumbers(params?: { page?: number; page_size?: number; country?: string; tag?: string }) {
  return request({ url: '/data/my-numbers', method: 'get', params })
}

export function exportMyNumbers(params?: { fmt?: string; country?: string; source?: string; purpose?: string; batch_id?: string }) {
  return request({
    url: '/data/my-numbers/export',
    method: 'get',
    params,
    responseType: 'blob',
  })
}

export function uploadMyNumbers(data: FormData) {
  return request({
    url: '/data/my-numbers/upload',
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 私库异步上传任务（大文件），用于轮询进度 */
export interface PrivateLibraryUploadTaskDTO {
  task_id: string
  status: string
  stage: string
  progress_percent: number
  total_unique: number
  inserted: number
  updated: number
  original_filename?: string | null
  country_code?: string | null
  detect_carrier?: boolean
  result_batch_id?: string | null
  error_message?: string | null
  created_at?: string | null
  completed_at?: string | null
}

/** 创建异步上传任务（建议大文件使用，需 Worker 消费 data_tasks 队列） */
export function createMyNumbersUploadTask(data: FormData) {
  return request({
    url: '/data/my-numbers/upload-tasks',
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 600000,
  }) as Promise<{ success?: boolean; task_id?: string; message?: string }>
}

export function getMyNumbersUploadTask(taskId: string) {
  return request({
    url: `/data/my-numbers/upload-tasks/${encodeURIComponent(taskId)}`,
    method: 'get',
  }) as Promise<{ success?: boolean; task?: PrivateLibraryUploadTaskDTO }>
}

export function listMyNumbersUploadTasks(params?: { page?: number; page_size?: number }) {
  return request({
    url: '/data/my-numbers/upload-tasks',
    method: 'get',
    params,
  }) as Promise<{
    success?: boolean
    items?: PrivateLibraryUploadTaskDTO[]
    total?: number
    page?: number
    page_size?: number
  }>
}

/** 放弃排队中的上传任务（使用 JSON Body，避免部分网关对「…/id/abandon」路径返回 404） */
export function abandonMyNumbersUploadTask(taskId: string) {
  return request({
    url: '/data/my-numbers/upload-tasks/abandon',
    method: 'post',
    data: { task_id: taskId },
  }) as Promise<{ success?: boolean; message?: string }>
}

export function deleteMyNumbers(params: {
  country?: string
  source?: string
  purpose?: string
  carrier?: string
  batch_id?: string
  remarks?: string
}) {
  // POST + JSON：避免 DELETE 查询串编码/长度问题；与后端 TRIM+小写 维度匹配一致
  return request({
    url: '/data/my-numbers/delete-batch',
    method: 'post',
    data: {
      country_code: params.country ?? '',
      source: params.source ?? '',
      purpose: params.purpose ?? '',
      batch_id: params.batch_id ?? '',
      remarks: params.remarks,
      carrier: params.carrier,
    },
  }) as Promise<{
    success?: boolean
    message?: string
    deleted?: number
  }>
}
