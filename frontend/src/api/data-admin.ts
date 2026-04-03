import request from './index'

export interface DataNumber {
  id: number
  phone_number: string
  country_code: string
  tags: string[]
  carrier: string
  status: string
  source: string
  source_label: string
  purpose: string
  purpose_label: string
  data_date: string | null
  freshness: string
  freshness_label: string
  batch_id: string
  use_count: number
  account_id: number | null
  last_used_at: string | null
  created_at: string | null
}

export interface DataProduct {
  id: number
  product_code: string
  product_name: string
  description: string
  filter_criteria: any
  price_per_number: string
  currency: string
  stock_count: number
  min_purchase: number
  max_purchase: number
  product_type: 'data_only' | 'combo' | 'data_and_send'
  sms_quota: number | null
  sms_unit_price: string | null
  bundle_price: string | null
  bundle_discount: string | null
  status: string
  total_sold: number
  created_at: string
}

export interface DataOrder {
  id: number
  order_no: string
  account_id: number
  account_name: string
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
  refunded_at: string | null
  created_at: string
  executed_at: string | null
}

export interface CreateProductData {
  product_code: string
  product_name: string
  description?: string
  filter_criteria: any
  price_per_number: string
  min_purchase: number
  max_purchase: number
  product_type?: string
  sms_quota?: number
  sms_unit_price?: string
  bundle_price?: string
  bundle_discount?: string
}

// ============ 号码管理 ============

export function getNumbers(params?: {
  page?: number; page_size?: number; country?: string;
  status?: string; source?: string; purpose?: string;
  tag?: string; batch_id?: string; account_id?: number
}) {
  return request({ url: '/admin/data/numbers', method: 'get', params })
}

export function getNumberStats() {
  return request({ url: '/admin/data/numbers/stats', method: 'get' })
}

export function importNumbers(formData: FormData, params: { source: string; purpose: string; data_date?: string; default_tags?: string; freshness?: string; country_code?: string; force_country?: boolean; pricing_template_id?: number }) {
  return request({
    url: '/admin/data/numbers/import',
    method: 'post',
    data: formData,
    params,
    timeout: 600000,
  })
}

/** 分块原始上传：多段短请求，避免经 CDN 的 HTTP/2 长传出现 net::ERR_HTTP2_PING_FAILED */
export async function importNumbersRaw(file: File, params: { source: string; purpose: string; data_date?: string; default_tags?: string; country_code?: string; force_country?: boolean; pricing_template_id?: number }) {
  const baseURL = import.meta.env.VITE_API_BASE_URL ? `${import.meta.env.VITE_API_BASE_URL}/api/v1` : '/api/v1'
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const isImpersonate = sessionStorage.getItem('impersonate_mode') === '1'
  if (isImpersonate) {
    const apiKey = sessionStorage.getItem('impersonate_api_key')
    if (apiKey) headers['X-API-Key'] = apiKey
  } else {
    const adminToken = localStorage.getItem('admin_token')
    if (adminToken) headers['Authorization'] = `Bearer ${adminToken}`
  }

  const sessionBody = {
    source: params.source,
    purpose: params.purpose,
    filename: file.name,
    country_code: params.country_code,
    force_country: !!params.force_country,
    data_date: params.data_date,
    pricing_template_id: params.pricing_template_id,
    default_tags: params.default_tags,
  }

  const r0 = await fetch(`${baseURL}/admin/data/numbers/import-raw/session`, {
    method: 'POST',
    headers,
    body: JSON.stringify(sessionBody),
  })
  const sessionJson = await r0.json().catch(() => ({}))
  if (!r0.ok) throw new Error(sessionJson.detail || r0.statusText || '创建上传会话失败')

  const sessionId = sessionJson.session_id as string
  const chunkSize = (sessionJson.chunk_size as number) || 4 * 1024 * 1024

  const plainHeaders: Record<string, string> = {}
  if (isImpersonate) {
    const apiKey = sessionStorage.getItem('impersonate_api_key')
    if (apiKey) plainHeaders['X-API-Key'] = apiKey
  } else {
    const adminToken = localStorage.getItem('admin_token')
    if (adminToken) plainHeaders['Authorization'] = `Bearer ${adminToken}`
  }

  let index = 0
  for (let offset = 0; offset < file.size; offset += chunkSize) {
    const slice = file.slice(offset, Math.min(offset + chunkSize, file.size))
    const rChunk = await fetch(
      `${baseURL}/admin/data/numbers/import-raw/session/${sessionId}/chunk?index=${index}`,
      {
        method: 'PUT',
        body: slice,
        headers: plainHeaders,
      },
    )
    if (!rChunk.ok) {
      const errJson = await rChunk.json().catch(() => ({}))
      throw new Error(errJson.detail || rChunk.statusText || `分块 ${index} 上传失败`)
    }
    index++
  }

  const rDone = await fetch(`${baseURL}/admin/data/numbers/import-raw/session/${sessionId}/complete`, {
    method: 'POST',
    headers: plainHeaders,
  })
  const data = await rDone.json().catch(() => ({}))
  if (!rDone.ok) throw new Error(data.detail || rDone.statusText || '完成上传失败')
  return data
}

export function getImportProgress(batchId: string) {
  return request({ url: `/admin/data/numbers/import-progress/${batchId}`, method: 'get' })
}

export function retryImport(batchId: string) {
  return request({ url: `/admin/data/numbers/import-retry/${batchId}`, method: 'post' })
}

export function supplementProductForBatch(batchId: string) {
  return request({ url: `/admin/data/numbers/import-supplement-product/${batchId}`, method: 'post' })
}

export function getImportBatches(params?: { page?: number; page_size?: number }) {
  return request({ url: '/admin/data/import-batches', method: 'get', params })
}

export function deleteImportBatch(batchId: string) {
  return request({ url: `/admin/data/import-batches/${batchId}`, method: 'delete' })
}

export function clearAllData() {
  return request({ url: '/admin/data/clear-all', method: 'post', params: { confirm: 'RESET_ALL' } })
}

export function batchTag(data: { number_ids: number[]; tags: string[]; mode?: string }) {
  return request({ url: '/admin/data/numbers/batch-tag', method: 'post', data })
}

export function batchStatus(data: { number_ids: number[]; status: string }) {
  return request({ url: '/admin/data/numbers/batch-status', method: 'post', data })
}

export function exportNumbers(params?: { country?: string; status?: string; tag?: string; batch_id?: string }) {
  return request({
    url: '/admin/data/numbers/export',
    method: 'get',
    params,
    responseType: 'blob',
  })
}

export function deleteNumbersByCountry(countryCode: string, params?: { source?: string; purpose?: string }) {
  return request({ url: `/admin/data/numbers/by-country/${countryCode}`, method: 'delete', params })
}

export function deleteNumbersByBatch(batchId: string) {
  return request({ url: `/admin/data/numbers/by-batch/${batchId}`, method: 'delete' })
}

export function dedupNumbers() {
  return request({ url: '/admin/data/numbers/clean/dedup', method: 'post' })
}

export function uploadBlacklist(formData: FormData) {
  return request({
    url: '/admin/data/numbers/clean/blacklist',
    method: 'post',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function recycleNumbers(days?: number) {
  return request({ url: '/admin/data/numbers/clean/recycle', method: 'post', params: { days } })
}

// ============ 商品管理 ============

export function getProducts(params?: { page?: number; page_size?: number; status?: string; product_type?: string }) {
  return request({ url: '/admin/data/products', method: 'get', params })
}

export function createProduct(data: CreateProductData) {
  return request({ url: '/admin/data/products', method: 'post', data })
}

export function updateProduct(id: number, data: Partial<CreateProductData & { status: string }>) {
  return request({ url: `/admin/data/products/${id}`, method: 'put', data })
}

export function deleteProduct(id: number) {
  return request({ url: `/admin/data/products/${id}`, method: 'delete' })
}

export function refreshProductStock(id: number) {
  return request({ url: `/admin/data/products/${id}/refresh-stock`, method: 'post' })
}

export function assignPoolNumbersToProduct(id: number) {
  return request({ url: `/admin/data/products/${id}/assign-pool-numbers`, method: 'post' })
}

export function syncProductsFromPool(countryCode?: string) {
  return request({ url: '/admin/data/products/sync-from-pool', method: 'post', params: countryCode ? { country_code: countryCode } : {} })
}

// ============ 评分管理 ============

export function getProductRatings(productId: number, params?: { page?: number; page_size?: number }) {
  return request({ url: `/admin/data/products/${productId}/ratings`, method: 'get', params })
}

export function updateRating(ratingId: number, params: { rating: number; comment?: string }) {
  return request({ url: `/admin/data/products/ratings/${ratingId}`, method: 'put', params })
}

export function deleteRating(ratingId: number) {
  return request({ url: `/admin/data/products/ratings/${ratingId}`, method: 'delete' })
}

// ============ 客户私库管理 ============

export function getAdminPrivateLibraryNumbers(params?: {
  page?: number;
  page_size?: number;
  account_id?: number;
  is_deleted?: boolean;
  country_code?: string;
  batch_id?: string;
  phone?: string;
}) {
  // 使用 main.py 显式挂载的短路径，与 /admin/data/private-library-numbers 等价
  return request({ url: '/admin/private-library-numbers', method: 'get', params })
}

/** 管理端私库卡片汇总（与客户「我的私有库」卡片结构一致，含 account_id/account_name） */
export function getAdminPrivateLibrarySummary(params?: {
  max_batches?: number;
  account_id?: number;
  /** 单国码（兼容旧参数） */
  country_code?: string;
  /** 逗号分隔多国码，通常由前端从国家名称解析得到 */
  country_codes?: string;
  batch_id?: string;
  min_card_count?: number;
  max_card_count?: number;
}) {
  return request({ url: '/admin/private-library-summary', method: 'get', params })
}

export function exportAdminPrivateLibraryNumbersUrl(params?: any) {
  const query = new URLSearchParams()
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') {
        query.append(k, String(v))
      }
    })
  }
  return `/admin/private-library-numbers/export?${query.toString()}`
}

// ============ 订单管理 ============

export function getOrders(params?: {
  page?: number; page_size?: number; status?: string; account_id?: number; order_type?: string
}) {
  return request({ url: '/admin/data/orders', method: 'get', params })
}

export function getOrderStats(period?: string) {
  return request({ url: '/admin/data/orders/stats', method: 'get', params: { period } })
}

export function getOrderDetail(orderId: number) {
  return request({ url: `/admin/data/orders/${orderId}`, method: 'get' })
}

export function cancelOrder(orderId: number, data?: { reason?: string }) {
  return request({ url: `/admin/data/orders/${orderId}/cancel`, method: 'post', data })
}

export function refundOrder(orderId: number, data?: { reason?: string; refund_amount?: string }) {
  return request({ url: `/admin/data/orders/${orderId}/refund`, method: 'post', data })
}

// ============ 数据账户 ============

export function getAccounts(params?: { country_code?: string; status?: string; search?: string; page?: number; page_size?: number }) {
  return request({ url: '/admin/data/accounts', method: 'get', params })
}

export function getAccountStats() {
  return request({ url: '/admin/data/accounts/stats', method: 'get' })
}

export function getAvailableAccounts(search?: string) {
  return request({ url: '/admin/data/accounts/available-accounts', method: 'get', params: { search } })
}

export function createDataAccount(data: { account_id: number; country_code?: string; balance?: number; remarks?: string }) {
  return request({ url: '/admin/data/accounts', method: 'post', data })
}

export function updateDataAccount(accountId: number, data: { country_code?: string; status?: string; remarks?: string }) {
  return request({ url: `/admin/data/accounts/${accountId}`, method: 'put', data })
}

export function deleteDataAccount(accountId: number, force: boolean = false) {
  return request({ url: `/admin/data/accounts/${accountId}`, method: 'delete', params: { force } })
}

export function rechargeDataAccount(accountId: number, data: { amount: number; remarks?: string }) {
  return request({ url: `/admin/data/accounts/${accountId}/recharge`, method: 'post', data })
}

export function syncAccount(accountId: number) {
  return request({ url: `/admin/data/accounts/${accountId}/sync`, method: 'post' })
}

export function getAccountLogs(accountId: number, params?: { page?: number; page_size?: number }) {
  return request({ url: `/admin/data/accounts/${accountId}/logs`, method: 'get', params })
}

export function impersonateAccount(accountId: number) {
  return request({ url: `/admin/accounts/${accountId}/impersonate`, method: 'post' })
}

// ============ 定价模板 ============

export interface PricingTemplate {
  id: number
  name: string
  country_code: string
  source: string
  source_label: string
  purpose: string
  purpose_label: string
  freshness: string
  freshness_label: string
  price_per_number: string
  cost_per_number: string
  currency: string
  remarks: string | null
  status: string
  created_at: string
  updated_at: string
}

export function getPricingTemplates(params?: { page?: number; page_size?: number; source?: string; purpose?: string; freshness?: string; country_code?: string; status?: string }) {
  return request({ url: '/admin/data/pricing-templates', method: 'get', params })
}

export function createPricingTemplate(data: { source: string; purpose: string; freshness: string; country_code?: string; price_per_number: string; cost_per_number?: string; remarks?: string; currency?: string; name?: string }) {
  return request({ url: '/admin/data/pricing-templates', method: 'post', data })
}

export function batchCreatePricingTemplates(data: { items: Array<{ source: string; purpose: string; freshness: string; country_code?: string; price_per_number: string }> }) {
  return request({ url: '/admin/data/pricing-templates/batch', method: 'post', data })
}

export function updatePricingTemplate(id: number, data: { price_per_number?: string; cost_per_number?: string; remarks?: string; status?: string; name?: string }) {
  return request({ url: `/admin/data/pricing-templates/${id}`, method: 'put', data })
}

export function deletePricingTemplate(id: number) {
  return request({ url: `/admin/data/pricing-templates/${id}`, method: 'delete' })
}

export function matchPricingTemplate(params: { country_code: string; source: string; purpose: string; freshness: string }) {
  return request({ url: '/admin/data/pricing-templates/match', method: 'get', params })
}

export function getPricingMatrix(country_code?: string) {
  return request({ url: '/admin/data/pricing-matrix', method: 'get', params: { country_code: country_code || '*' } })
}
