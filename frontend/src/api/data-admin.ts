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

export function importNumbers(formData: FormData, params: { source: string; purpose: string; data_date?: string; default_tags?: string; pricing_template_id?: number }) {
  return request({
    url: '/admin/data/numbers/import',
    method: 'post',
    data: formData,
    params,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
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
