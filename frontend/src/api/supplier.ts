import request from './index'

// ============ 供应商管理 ============

export interface Supplier {
  id: number
  supplier_code: string
  supplier_name: string
  supplier_group?: string
  supplier_type: string
  business_type?: string
  country?: string
  resource_type?: string
  cost_price?: number
  cost_currency?: string
  contact_person?: string
  contact_email?: string
  contact_phone?: string
  protocol: string
  status: string
  priority: number
  settlement_currency: string
  settlement_period: string
  payment_method: string
  credit_limit: number
  current_balance: number
  notes?: string
  created_at?: string
}

export interface SupplierCreate {
  supplier_code: string
  supplier_name: string
  supplier_type?: string
  contact_person?: string
  contact_email?: string
  contact_phone?: string
  contact_address?: string
  api_endpoint?: string
  api_key?: string
  api_secret?: string
  protocol?: string
  status?: string
  priority?: number
  settlement_currency?: string
  settlement_period?: string
  settlement_day?: number
  payment_method?: string
  credit_limit?: number
  notes?: string
}

export interface SupplierRate {
  id: number
  country_code: string
  mcc?: string
  mnc?: string
  operator_name?: string
  cost_price: number
  currency: string
  effective_date?: string
  expire_date?: string
  status: string
}

export interface RateDeck {
  id: number
  deck_code: string
  deck_name: string
  deck_type: string
  markup_type: string
  markup_value: number
  is_default: boolean
  status: string
  description?: string
  created_at?: string
}

// 获取供应商列表
export function getSuppliers(params?: {
  page?: number
  page_size?: number
  status?: string
  keyword?: string
}) {
  return request.get('/admin/suppliers', { params })
}

// 获取供应商详情
export function getSupplier(supplierId: number) {
  return request.get(`/admin/suppliers/${supplierId}`)
}

// 创建供应商
export function createSupplier(data: SupplierCreate) {
  return request.post('/admin/suppliers', data)
}

// 更新供应商
export function updateSupplier(supplierId: number, data: Partial<SupplierCreate>) {
  return request.put(`/admin/suppliers/${supplierId}`, data)
}

// 删除供应商
export function deleteSupplier(supplierId: number) {
  return request.delete(`/admin/suppliers/${supplierId}`)
}

// 获取供应商费率列表
export function getSupplierRates(supplierId: number, params?: {
  page?: number
  page_size?: number
  country_code?: string
}) {
  return request.get(`/admin/suppliers/${supplierId}/rates`, { params })
}

// 创建供应商费率
export function createSupplierRate(supplierId: number, data: {
  country_code: string
  cost_price: number
  mcc?: string
  mnc?: string
  operator_name?: string
  currency?: string
}) {
  return request.post(`/admin/suppliers/${supplierId}/rates`, data)
}

// 批量导入供应商费率
export function batchImportSupplierRates(supplierId: number, rates: any[]) {
  return request.post(`/admin/suppliers/${supplierId}/rates/batch`, { rates })
}

// 更新供应商费率
export function updateSupplierRate(supplierId: number, rateId: number, data: {
  country_code?: string
  cost_price?: number
  mcc?: string
  mnc?: string
  operator_name?: string
  currency?: string
  effective_date?: string
}) {
  return request.put(`/admin/suppliers/${supplierId}/rates/${rateId}`, data)
}

// 删除供应商费率
export function deleteSupplierRate(supplierId: number, rateId: number) {
  return request.delete(`/admin/suppliers/${supplierId}/rates/${rateId}`)
}

// 获取供应商关联通道
export function getSupplierChannels(supplierId: number) {
  return request.get(`/admin/suppliers/${supplierId}/channels`)
}

// 关联供应商通道
export function linkSupplierChannel(supplierId: number, channelId: number, supplierChannelCode?: string) {
  return request.post(`/admin/suppliers/${supplierId}/channels`, null, {
    params: { channel_id: channelId, supplier_channel_code: supplierChannelCode }
  })
}

// 解绑供应商通道
export function unlinkSupplierChannel(supplierId: number, channelId: number) {
  return request.delete(`/admin/suppliers/${supplierId}/channels/${channelId}`)
}

// 获取供应商统计
export function getSupplierStatistics(supplierId: number, params?: {
  start_date?: string
  end_date?: string
}) {
  return request.get(`/admin/suppliers/${supplierId}/statistics`, { params })
}

// ============ 费率表管理 ============

// 获取费率表列表
export function getRateDecks(params?: {
  page?: number
  page_size?: number
  status?: string
}) {
  return request.get('/admin/suppliers/rate-decks', { params })
}

// 创建费率表
export function createRateDeck(data: {
  deck_name: string
  deck_code: string
  description?: string
  deck_type?: string
  markup_type?: string
  markup_value?: number
  is_default?: boolean
}) {
  return request.post('/admin/suppliers/rate-decks', data)
}

// 获取费率表的销售费率
export function getRateDeckRates(deckId: number, params?: {
  page?: number
  page_size?: number
  country_code?: string
}) {
  return request.get(`/admin/suppliers/rate-decks/${deckId}/rates`, { params })
}

// 创建销售费率
export function createSellRate(deckId: number, data: {
  country_code: string
  sell_price: number
  mcc?: string
  mnc?: string
  operator_name?: string
  currency?: string
}) {
  return request.post(`/admin/suppliers/rate-decks/${deckId}/rates`, data)
}
