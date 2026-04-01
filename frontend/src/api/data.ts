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
  return request({ url: '/data/buy-and-send', method: 'post', data })
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

export function getMyNumbersSummary() {
  return request({ url: '/data/my-numbers/summary', method: 'get' })
}

export function getMyNumbers(params?: { page?: number; page_size?: number; country?: string; tag?: string }) {
  return request({ url: '/data/my-numbers', method: 'get', params })
}

export function exportMyNumbers(params?: { fmt?: string; country?: string; source?: string; purpose?: string }) {
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

export function deleteMyNumbers(params: { country?: string; source?: string; purpose?: string; carrier?: string }) {
  return request({ url: '/data/my-numbers', method: 'delete', params })
}
