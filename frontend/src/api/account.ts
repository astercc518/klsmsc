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

// 查询账户信息
// 管理员模式下返回模拟数据，impersonate 模式调用真实 API
export const getAccountInfo = () => {
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

