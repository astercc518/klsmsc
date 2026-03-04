import request from './index'

// --- Types ---

export interface InviteCode {
  code: string
  sales_id: number
  sales_name?: string
  config: any
  status: 'unused' | 'used' | 'expired'
  used_by_account_id?: number
  created_at: string
  expires_at?: string
  used_at?: string
}

export interface InviteListResponse {
  items: InviteCode[]
  total: number
  page: number
  limit: number
}

export interface CreateInviteRequest {
  country: string
  price: number
  business_type: string
  valid_hours: number
}

export interface RechargeOrder {
  id: number
  order_no: string
  account_id: number
  account_name?: string
  amount: number
  currency: string
  proof: string
  status: string
  created_at: string
  finance_audit_by?: number
  finance_audit_at?: string
  reject_reason?: string
}

export interface RechargeListResponse {
  items: RechargeOrder[]
  total: number
  page: number
  limit: number
}

export interface SMSBatch {
  id: string
  account_id: number
  account_name?: string
  content: string
  content_preview?: string
  total_count: number
  valid_count: number
  total_cost: number
  status: string
  created_at: string
  audit_by?: number
  audit_at?: string
}

export interface BatchListResponse {
  items: SMSBatch[]
  total: number
  page: number
  limit: number
}

export interface SMSTemplate {
  id: number
  account_id: number
  account_name?: string
  hash: string
  text: string
  status: string
  created_at: string
}

export interface TemplateListResponse {
  items: SMSTemplate[]
  total: number
  page: number
  limit: number
}

// --- API ---

// 1. Invites
export function getInvites(params: {
  page?: number
  limit?: number
  status?: string
  sales_id?: number
}): Promise<InviteListResponse> {
  return request({
    url: '/admin/bot/invites',
    method: 'get',
    params
  })
}

export function createInvite(data: CreateInviteRequest) {
  return request({
    url: '/admin/bot/invites',
    method: 'post',
    data
  })
}

export function getInviteDetail(code: string) {
  return request({
    url: `/admin/bot/invites/${code}`,
    method: 'get'
  })
}

export function getInviteStats(params?: {
  sales_id?: number
  start_date?: string
  end_date?: string
}) {
  return request({
    url: '/admin/bot/invites/stats/summary',
    method: 'get',
    params
  })
}

// 2. Recharges
export function getRecharges(params: {
  status?: string
  page?: number
  limit?: number
}): Promise<RechargeListResponse> {
  return request({
    url: '/admin/bot/recharges',
    method: 'get',
    params
  })
}

export function getRechargeDetail(id: number) {
  return request({
    url: `/admin/bot/recharges/${id}`,
    method: 'get'
  })
}

export function auditRecharge(id: number, action: 'approve' | 'reject', reason?: string) {
  return request({
    url: `/admin/bot/recharges/${id}/audit`,
    method: 'post',
    data: { action, reason }
  })
}

// 3. Batches
export function getBatches(params: {
  status?: string
  page?: number
  limit?: number
}): Promise<BatchListResponse> {
  return request({
    url: '/admin/bot/batches',
    method: 'get',
    params
  })
}

export function getBatchDetail(id: string) {
  return request({
    url: `/admin/bot/batches/${id}`,
    method: 'get'
  })
}

export function auditBatch(id: string, action: 'approve' | 'reject', reason?: string) {
  return request({
    url: `/admin/bot/batches/${id}/audit`,
    method: 'post',
    data: { action, reason }
  })
}

// 4. Templates
export interface CreateTemplateRequest {
  account_id: number
  content_text: string
}

export interface UpdateTemplateRequest {
  status: 'approved' | 'rejected'
}

export function getTemplates(params?: {
  account_id?: number
  search?: string
  page?: number
  limit?: number
}): Promise<TemplateListResponse> {
  return request({
    url: '/admin/bot/templates',
    method: 'get',
    params
  })
}

export function createTemplate(data: CreateTemplateRequest) {
  return request({
    url: '/admin/bot/templates',
    method: 'post',
    data
  })
}

export function updateTemplate(id: number, data: UpdateTemplateRequest) {
  return request({
    url: `/admin/bot/templates/${id}`,
    method: 'put',
    data
  })
}

export function deleteTemplate(id: number) {
  return request({
    url: `/admin/bot/templates/${id}`,
    method: 'delete'
  })
}
