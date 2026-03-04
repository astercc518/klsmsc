import request from './index'

export function getSalesProducts(params?: { page?: number; page_size?: number; product_type?: string }) {
  return request({ url: '/sales/data/products', method: 'get', params })
}

export function getSalesOrders(params?: {
  page?: number; page_size?: number; status?: string; account_id?: number
}) {
  return request({ url: '/sales/data/orders', method: 'get', params })
}

export function getSalesCustomers(params?: { page?: number; page_size?: number }) {
  return request({ url: '/sales/data/customers', method: 'get', params })
}
