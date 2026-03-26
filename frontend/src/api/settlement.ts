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
  /** 后端列表扩展 */
  settlement_month?: string
  channel_count?: number
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

// 获取结算单汇总
export function getSettlementsSummary(params?: {
  supplier_id?: number
  status?: string
  start_date?: string
  end_date?: string
  settlement_month?: string
  supplier_keyword?: string
}) {
  return request.get('/admin/settlements/summary', { params })
}

// 获取结算单列表
export function getSettlements(params?: {
  page?: number
  page_size?: number
  supplier_id?: number
  status?: string
  start_date?: string
  end_date?: string
  /** 结算月 YYYY-MM */
  settlement_month?: string
  /** 供应商名称模糊搜索 */
  supplier_keyword?: string
  sort_by?: 'created_at' | 'total_sms_count' | 'final_amount'
  sort_order?: 'asc' | 'desc'
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

/** 批量生成指定月份：全部供应商结算、销售佣金、活跃客户账单（已存在或无数据则跳过） */
export function autoGenerateMonthSettlements(params?: {
  year?: number
  month?: number
  include_suppliers?: boolean
  include_employees?: boolean
  include_customers?: boolean
  due_days?: number
}) {
  return request.post('/admin/settlements/auto-generate-month', {}, { params })
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

// 删除结算单（仅草稿/待确认/已取消）
export function deleteSettlement(settlementId: number) {
  return request.delete(`/admin/settlements/${settlementId}`)
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
  settlement_month?: string
  account_keyword?: string
  sort_by?: 'created_at' | 'total_sms_count' | 'total_amount'
  sort_order?: 'asc' | 'desc'
}) {
  return request.get('/admin/bills', { params })
}

// 获取客户账单详情
export function getCustomerBillDetail(billId: number) {
  return request.get(`/admin/bills/${billId}`)
}

// 客户账单收款
export function payCustomerBill(billId: number, data: {
  amount: number
  payment_method?: string
  payment_reference?: string
  notes?: string
}) {
  return request.post(`/admin/bills/${billId}/pay`, data)
}

// 生成客户账单
export function generateCustomerBill(data: {
  account_id: number
  period_start: string
  period_end: string
  due_days?: number
}) {
  return request.post('/admin/bills/generate', data)
}

// ============ 销售佣金结算接口 ============

export interface CommissionSettlement {
  id: number
  settlement_no: string
  sales_id: number
  sales_name?: string
  period_start: string
  period_end: string
  total_sms_count: number
  total_revenue: number
  /** 该员工名下客户在本周期内的短信成本汇总 */
  total_cost?: number
  commission_rate: number
  commission_amount: number
  currency: string
  status: string
  paid_at?: string
  created_at?: string
}

// 获取销售佣金汇总
export function getCommissionSummary(params?: {
  sales_id?: number
  status?: string
  start_date?: string
  end_date?: string
  settlement_month?: string
  sales_keyword?: string
}) {
  return request.get('/admin/sales-commission/summary', { params })
}

// 获取销售佣金结算单列表
export function getCommissionSettlements(params?: {
  page?: number
  page_size?: number
  sales_id?: number
  status?: string
  start_date?: string
  end_date?: string
  settlement_month?: string
  sales_keyword?: string
  sort_by?: 'created_at' | 'total_sms_count' | 'commission_amount' | 'total_cost'
  sort_order?: 'asc' | 'desc'
}) {
  return request.get('/admin/sales-commission', { params })
}

// 生成销售佣金结算单
export function generateCommissionSettlement(params: {
  sales_id: number
  year: number
  month: number
}) {
  return request.post('/admin/sales-commission/generate', null, { params })
}

// 获取销售佣金结算单详情
export function getCommissionSettlementDetail(settlementId: number) {
  return request.get(`/admin/sales-commission/${settlementId}`)
}

// 确认销售佣金结算单
export function confirmCommissionSettlement(settlementId: number) {
  return request.post(`/admin/sales-commission/${settlementId}/confirm`)
}

// 支付销售佣金结算单
export function payCommissionSettlement(settlementId: number, data: {
  payment_method: string
  payment_reference?: string
  notes?: string
}) {
  return request.post(`/admin/sales-commission/${settlementId}/pay`, data)
}

// 取消销售佣金结算单
export function cancelCommissionSettlement(settlementId: number, reason: string) {
  return request.post(`/admin/sales-commission/${settlementId}/cancel`, null, {
    params: { reason }
  })
}
