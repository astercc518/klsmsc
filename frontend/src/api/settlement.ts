import request from './index'

// ============ 结算类型定义 ============

export interface Settlement {
  id: number
  settlement_no: string
  supplier_id: number
  supplier_name?: string
  period_start: string
  period_end: string
  total_sms_count: number
  total_success_count?: number
  total_failed_count?: number
  total_cost: number
  adjustment_amount: number
  final_amount: number
  currency: string
  status: string
  payment_method?: string
  payment_reference?: string
  payment_proof?: string
  paid_at?: string
  notes?: string
  created_at?: string
}

export interface SettlementDetail {
  id: number
  channel_id?: number
  country_code: string
  country_name?: string
  sms_count: number
  success_count: number
  failed_count: number
  unit_cost: number
  total_cost: number
}

export interface SettlementLog {
  id: number
  action: string
  old_status?: string
  new_status?: string
  operator_name?: string
  description?: string
  created_at?: string
}

export interface CustomerBill {
  id: number
  bill_no: string
  account_id: number
  account_name?: string
  period_start: string
  period_end: string
  total_sms_count: number
  total_amount: number
  paid_amount: number
  outstanding_amount: number
  status: string
  due_date?: string
  created_at?: string
}

// ============ 供应商结算接口 ============

// 获取结算单列表
export function getSettlements(params?: {
  page?: number
  page_size?: number
  supplier_id?: number
  status?: string
  start_date?: string
  end_date?: string
}) {
  return request.get('/admin/settlements', { params })
}

// 生成结算单
export function generateSettlement(data: {
  supplier_id: number
  period_start: string
  period_end: string
  notes?: string
}) {
  return request.post('/admin/settlements/generate', data)
}

// 获取结算单详情
export function getSettlementDetail(settlementId: number) {
  return request.get(`/admin/settlements/${settlementId}`)
}

// 确认结算单
export function confirmSettlement(settlementId: number) {
  return request.post(`/admin/settlements/${settlementId}/confirm`)
}

// 调整结算金额
export function adjustSettlement(settlementId: number, data: {
  adjustment_amount: number
  reason: string
}) {
  return request.post(`/admin/settlements/${settlementId}/adjust`, data)
}

// 支付结算单
export function paySettlement(settlementId: number, data: {
  payment_method: string
  payment_reference?: string
  payment_proof?: string
  notes?: string
}) {
  return request.post(`/admin/settlements/${settlementId}/pay`, data)
}

// 取消结算单
export function cancelSettlement(settlementId: number, reason: string) {
  return request.post(`/admin/settlements/${settlementId}/cancel`, null, {
    params: { reason }
  })
}

// ============ 利润报表接口 ============

// 获取利润报表
export function getProfitReport(params: {
  start_date: string
  end_date: string
  group_by?: 'day' | 'supplier' | 'country' | 'channel'
  supplier_id?: number
}) {
  return request.get('/admin/settlements/reports/profit', { params })
}

// ============ 客户账单接口 ============

// 获取客户账单列表
export function getCustomerBills(params?: {
  page?: number
  page_size?: number
  account_id?: number
  status?: string
}) {
  return request.get('/admin/bills', { params })
}

// 生成客户账单
export function generateCustomerBill(data: {
  account_id: number
  period_start: string
  period_end: string
}) {
  return request.post('/admin/bills/generate', null, { params: data })
}
