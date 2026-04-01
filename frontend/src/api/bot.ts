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

// 2. Templates
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

// 3. Recharges
export function getRecharges(params?: {
  status?: string
  page?: number
  limit?: number
}) {
  return request({
    url: '/admin/bot/recharges',
    method: 'get',
    params
  })
}

export function auditRecharge(oid: number, data: { action: 'approve' | 'reject'; reason?: string }) {
  return request({
    url: `/admin/bot/recharges/${oid}/audit`,
    method: 'post',
    data
  })
}

// 4. Batches
export function getBotBatches(params?: {
  status?: string
  page?: number
  limit?: number
}) {
  return request({
    url: '/admin/bot/batches',
    method: 'get',
    params
  })
}

export function auditBatch(bid: string, data: { action: 'approve' | 'reject'; reason?: string }) {
  return request({
    url: `/admin/bot/batches/${bid}/audit`,
    method: 'post',
    data
  })
}

// 5. Config
export function getBotConfig() {
  return request({
    url: '/admin/bot/config',
    method: 'get'
  })
}

export function saveBotConfig(data: any) {
  return request({
    url: '/admin/bot/config',
    method: 'post',
    data
  })
}

export function restartBot() {
  return request({
    url: '/admin/bot/restart',
    method: 'post'
  })
}
