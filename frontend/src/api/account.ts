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
  hide_price?: boolean  // 客户门户隐藏价格(单价/剩余条数估算)
  hide_tg?: boolean     // 客户门户隐藏TG(自绑TG卡片+归属商务联系TG)
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

/** 余额变动流水（仅资金事件：充值/退款/调整等，不含逐条 SMS 扣费） */
export interface BalanceTransaction {
  id: number
  type: string
  amount: number
  balance_after: number
  description: string
  created_at: string | null
}

// 近期交易（/account/transactions）
// 管理员非 impersonate 模式无真实账户上下文，返回空列表
export const getTransactions = (limit = 20): Promise<{ items: BalanceTransaction[] }> => {
  const isImpersonate = sessionStorage.getItem('impersonate_mode') === '1'
  if (!isImpersonate && localStorage.getItem('admin_token')) {
    return Promise.resolve({ items: [] })
  }
  return request.get('/account/transactions', { params: { limit } })
}

// 修改客户登录密码
export const changeAccountPassword = (data: { old_password: string; new_password: string }) => {
  return request.post('/account/change-password', data)
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

