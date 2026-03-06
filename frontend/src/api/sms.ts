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

// 批量发送短信
export const sendBatchSMS = (data: {
  phone_numbers: string[]
  message: string
  sender_id?: string
  callback_url?: string
}) => {
  return request.post('/sms/batch', data)
}

// 获取发送记录
export const getSMSRecords = (params?: any) => {
  return request.get('/sms/records', { params })
}

// 导出发送记录 CSV
export const exportSMSRecords = (params?: any) => {
  return request.get('/sms/records/export', { params, responseType: 'blob' })
}

