import request from './index'

// 发送短信
export const sendSMS = (data: {
  phone_number: string
  message: string
  sender_id?: string
  channel_id?: number
  callback_url?: string
  http_username?: string
  http_password?: string
}) => {
  return request.post('/sms/send', data)
}

// 查询短信状态
export const getSMSStatus = (messageId: string) => {
  return request.get(`/sms/status/${messageId}`)
}

// 批量发送短信（会创建发送任务 batch，可在「发送任务」页查看进度）
export const sendBatchSMS = (data: {
  phone_numbers?: string[]
  private_library_filters?: {
    country_code?: string
    source?: string
    purpose?: string
    /** 与私库卡片批次一致，避免多批次同维度时 use_count 更新错位 */
    batch_id?: string
    carrier?: string
    limit?: number
    unused_only?: boolean
  }
  message: string
  messages?: string[]
  sender_id?: string
  channel_id?: number | null
  callback_url?: string
  batch_name?: string
}) => {
  return request.post('/sms/batch', data)
}

// 获取发送记录
export const getSMSRecords = (params?: any) => {
  return request.get('/sms/records', { params })
}

// ========== 短信审核（与 Bot 同步） ==========

// 提交短信审核（仅需文案；可选号码）
export const submitSmsApproval = (data: { message: string; phone_number?: string }) => {
  return request.post('/sms/approval', data)
}

// 删除未发送的审核记录
export const deleteSmsApproval = (approvalId: number) => {
  return request.delete(`/sms/approval/${approvalId}`)
}

// 获取短信审核列表
export const getSmsApprovals = (params?: {
  status?: string
  search?: string
  limit?: number
  offset?: number
  account_id?: number
}) => {
  return request.get('/sms/approvals', { params })
}

// 单条审核详情（完整 content，用于跳转发送页预填）
export const getSmsApprovalDetail = (approvalId: number) => {
  return request.get(`/sms/approvals/${approvalId}`)
}

// 执行审核通过的短信发送（审核无号码时需 body.phone_number）
export const executeApprovedSms = (approvalId: number, data?: { phone_number?: string }) => {
  return request.post(`/sms/approval/${approvalId}/execute`, data ?? {})
}

export const getChannelBannedWords = (channelId: number): Promise<any> => {
  return request.get(`/sms/channels/${channelId}/banned-words`)
}

export const getCustomerSendStatistics = (params?: {
  start_date?: string
  end_date?: string
}): Promise<any> => {
  return request.get('/sms/send-statistics', { params })
}

export const getCustomerDailyStats = (params?: {
  days?: number
  start_date?: string
  end_date?: string
}): Promise<any> => {
  return request.get('/sms/daily-stats', { params })
}

export const getCustomerFailAnalysis = (params?: {
  start_date?: string
  end_date?: string
}): Promise<any> => {
  return request.get('/sms/fail-analysis', { params })
}

