import request from './index'

// 注册账户
export const registerAccount = (data: {
  account_name: string
  email: string
  password: string
  company_name?: string
  contact_person?: string
  contact_phone?: string
}) => {
  return request.post('/account/register', data)
}

// 登录
export const login = (data: { email: string; password: string }) => {
  return request.post('/account/login', data)
}

// 查询余额
// 管理员模式下返回模拟数据，impersonate 模式调用真实 API
export const getBalance = () => {
  const isImpersonate = sessionStorage.getItem('impersonate_mode') === '1'
  if (isImpersonate) {
    return request.get('/account/balance')
  }
  const adminToken = localStorage.getItem('admin_token');
  if (adminToken) {
    return Promise.resolve({
      account_id: 'admin',
      balance: 0,
      currency: 'USD',
      low_balance_threshold: null
    });
  }
  return request.get('/account/balance')
}

/** 客户账户信息（/account/info） */
export interface AccountInfo {
  id: number
  account_name: string
  email?: string | null
  balance: number
  currency: string
  status: string
  services?: string
  company_name?: string | null
  contact_person?: string | null
  rate_limit?: number | null
  tg_id?: number | null
  tg_username?: string | null
  unit_price?: number | null
  created_at: string
  client_name?: string | null
  country_code?: string | null
  remaining_sms_estimate?: number | null
  sales_tg_username?: string | null
}

// 查询账户信息
// 管理员模式下返回模拟数据，impersonate 模式调用真实 API
export const getAccountInfo = (): Promise<AccountInfo> => {
  const isImpersonate = sessionStorage.getItem('impersonate_mode') === '1'
  if (isImpersonate) {
    return request.get('/account/info')
  }
  const adminToken = localStorage.getItem('admin_token');
  if (adminToken) {
    return Promise.resolve({
      id: 0,
      account_name: 'Admin',
      email: 'admin@system.local',
      balance: 0,
      currency: 'USD',
      status: 'active',
      company_name: 'System Administrator',
      contact_person: 'Admin',
      rate_limit: 0,
      created_at: new Date().toISOString()
    });
  }
  return request.get('/account/info')
}

// 生成客户 TG 绑定码
export const generateAccountTgBindCode = () => {
  return request.post('/account/telegram-bind-code')
}

// 解绑客户 TG
export const unbindAccountTelegram = () => {
  return request.post('/account/telegram-unbind')
}

// 客户 TG 验证登录
export const sendAccountTelegramCode = (identifier: string) => {
  return request.post('/account/telegram-login/send-code', { identifier })
}

export const verifyAccountTelegramCode = (identifier: string, code: string) => {
  return request.post('/account/telegram-login/verify', { identifier, code })
}

