/**
 * 管理员API
 */
import { request } from './index';

export interface AdminLoginRequest {
  username: string;
  password: string;
}

export interface AdminLoginResponse {
  success: boolean;
  token?: string;
  admin_id?: number;
  username?: string;
  role?: string;
  error?: string;
}

// Telegram 验证登录
export function sendTelegramLoginCode(username: string) {
  return request.post('/admin/telegram-login/send-code', { username })
}

export function verifyTelegramLoginCode(username: string, code: string): Promise<AdminLoginResponse> {
  return request.post('/admin/telegram-login/verify', { username, code })
}

export interface ChannelCreateRequest {
  channel_code: string;
  channel_name: string;
  protocol: string;
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  api_url?: string;
  api_key?: string;
  status?: string;
  max_tps?: number;
  concurrency?: number;
  rate_control_window?: number;
  priority?: number;
  weight?: number;
  default_sender_id?: string;
  description?: string;
  supplier_id?: number;  // 关联供应商
}

export interface ChannelUpdateRequest {
  channel_name?: string;
  max_tps?: number;
  concurrency?: number;
  rate_control_window?: number;
  priority?: number;
  weight?: number;
  status?: string;
  description?: string;
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  api_url?: string;
  api_key?: string;
  default_sender_id?: string;
  supplier_id?: number;  // 关联供应商
}

export interface PricingCreateRequest {
  channel_id: number;
  country_code: string;
  country_name: string;
  price_per_sms: number;
  currency?: string;
  mnc?: string;
  operator_name?: string;
  effective_date?: string;
}

/**
 * 管理员登录
 */
export async function adminLogin(data: AdminLoginRequest): Promise<AdminLoginResponse> {
  const response = await request.post<AdminLoginResponse>('/admin/login', data);
  return response;
}

/** 管理员个人资料 */
export interface AdminProfile {
  id: number
  username: string
  real_name?: string
  email?: string
  phone?: string
  role: string
  tg_id?: number
  tg_username?: string
  last_login_at?: string
  created_at?: string
}

/** 获取管理员个人资料 */
export async function getAdminProfile(): Promise<{ success: boolean; profile: AdminProfile }> {
  return request.get('/admin/profile')
}

/** 修改管理员密码 */
export async function changeAdminPassword(data: { old_password: string; new_password: string }): Promise<{ success: boolean; error?: string }> {
  return request.post('/admin/profile/change-password', data)
}

/** 生成 Telegram 绑定码 */
export async function generateTgBindCode(): Promise<{ success: boolean; code?: string; expires_in?: number }> {
  return request.post('/admin/profile/telegram-bind-code')
}

/** 解绑 Telegram */
export async function unbindTelegram(): Promise<{ success: boolean; error?: string }> {
  return request.post('/admin/profile/telegram-unbind')
}

/**
 * 获取通道列表（管理员）
 */
export async function getChannelsAdmin(): Promise<any> {
  return request.get('/admin/channels');
}

/**
 * 获取通道详情（管理员）
 */
export async function getChannelAdmin(channelId: number): Promise<any> {
  return request.get(`/admin/channels/${channelId}`);
}

/**
 * 创建通道
 */
export async function createChannel(data: ChannelCreateRequest): Promise<any> {
  return request.post('/admin/channels', data);
}

/**
 * 更新通道
 */
export async function updateChannel(
  channelId: number,
  data: ChannelUpdateRequest
): Promise<any> {
  return request.put(`/admin/channels/${channelId}`, data);
}

/**
 * 删除通道
 */
export async function deleteChannel(channelId: number): Promise<any> {
  return request.delete(`/admin/channels/${channelId}`);
}

/**
 * 通道测试发送
 */
export async function channelTestSend(
  channelId: number,
  data: { phone: string; content: string; sender_id?: string }
): Promise<any> {
  return request.post(`/admin/channels/${channelId}/test-send`, data);
}

/**
 * 通道状态检查（单个）
 */
export async function channelCheckStatus(channelId: number): Promise<any> {
  return request.post(`/admin/channels/${channelId}/check-status`);
}

/**
 * 一键检测所有通道连接状态
 */
export async function channelCheckAllStatus(): Promise<any> {
  return request.post('/admin/channels/check-all-status');
}

/**
 * 获取路由规则列表（管理员）
 */
export async function getRoutingRules(channelId?: number, countryCode?: string): Promise<any> {
  const params: any = {};
  if (channelId) params.channel_id = channelId;
  if (countryCode) params.country_code = countryCode;
  return request.get('/admin/routing-rules', { params });
}

/**
 * 创建路由规则（管理员）
 */
export async function createRoutingRule(data: {
  channel_id: number;
  country_code: string;
  priority?: number;
  is_active?: boolean;
}): Promise<any> {
  return request.post('/admin/routing-rules', data);
}

/**
 * 更新路由规则（管理员）
 */
export async function updateRoutingRule(
  ruleId: number,
  data: { priority?: number; is_active?: boolean }
): Promise<any> {
  return request.put(`/admin/routing-rules/${ruleId}`, data);
}

/**
 * 删除路由规则（管理员）
 */
export async function deleteRoutingRule(ruleId: number): Promise<any> {
  return request.delete(`/admin/routing-rules/${ruleId}`);
}

/**
 * 获取费率列表
 */
export async function getPricingList(
  channelId?: number,
  countryCode?: string
): Promise<any> {
  const params: any = {};
  if (channelId) params.channel_id = channelId;
  if (countryCode) params.country_code = countryCode;

  const response = await request.get('/admin/pricing', { params });
  return response;
}

/**
 * 创建费率规则
 */
export async function createPricing(data: PricingCreateRequest): Promise<any> {
  return request.post('/admin/pricing', data);
}

/**
 * 更新费率规则
 */
export async function updatePricing(
  pricingId: number,
  pricePerSms?: number,
  currency?: string
): Promise<any> {
  const data: any = {};
  if (pricePerSms !== undefined) data.price_per_sms = pricePerSms;
  if (currency) data.currency = currency;

  const response = await request.put(`/admin/pricing/${pricingId}`, data);
  return response;
}

/**
 * 删除费率规则
 */
export async function deletePricing(pricingId: number): Promise<any> {
  return request.delete(`/admin/pricing/${pricingId}`);
}

/**
 * 管理员仪表板数据
 */
/** 仪表盘主机性能（API 进程所在机器） */
export interface AdminServerMetrics {
  hostname?: string;
  cpu_percent?: number;
  memory_percent?: number;
  memory_used_gb?: number;
  memory_total_gb?: number;
  disk_percent?: number;
  disk_free_gb?: number;
  disk_total_gb?: number;
  load_avg?: number[] | null;
  error?: string;
}

export interface AdminServiceStatusItem {
  id: string;
  status: 'ok' | 'error';
  message?: string;
}

export interface AdminDashboardResponse {
  success: boolean;
  admin_name: string;
  admin_role: string;
  statistics: {
    today_sent: number;
    today_delivered: number;
    today_success_rate: number;
    today_cost: number;
    active_channels: number;
    active_accounts: number;
    total_balance: number;
  };
  permissions?: {
    view_global?: boolean;
    view_finance?: boolean;
    view_channels?: boolean;
    view_customers?: boolean;
    view_system_monitor?: boolean;
  };
  server_metrics?: AdminServerMetrics | null;
  service_status?: AdminServiceStatusItem[] | null;
}

export async function getAdminDashboard(): Promise<AdminDashboardResponse> {
  return request.get('/admin/dashboard');
}

/**
 * 管理员系统统计
 */
export async function getAdminStatistics(startDate?: string, endDate?: string): Promise<any> {
  const params: any = {};
  if (startDate) params.start_date = startDate;
  if (endDate) params.end_date = endDate;
  return request.get('/admin/statistics', { params });
}

/**
 * 获取发送方ID列表
 */
export async function getSenderIDs(status?: string, channelId?: number): Promise<any> {
  const params: any = {};
  if (status) params.status = status;
  if (channelId) params.channel_id = channelId;
  return request.get('/admin/sender-ids', { params });
}

/**
 * 审核发送方ID
 */
export async function auditSenderID(sidId: number, status: string, rejectionReason?: string): Promise<any> {
  return request.put(`/admin/sender-ids/${sidId}/audit`, {
    status,
    rejection_reason: rejectionReason
  });
}

// --- Accounts (Admin) ---

export interface AdminAccount {
  id: number;
  account_name: string;
  email: string;
  status: string;
  balance: number;
  currency: string;
  low_balance_threshold?: number | null;
  rate_limit?: number;
  ip_whitelist?: string[];
  api_key?: string | null;
  company_name?: string | null;
  contact_person?: string | null;
  contact_phone?: string | null;
  sales?: {
    id?: number | null;
    username?: string | null;
    real_name?: string | null;
    email?: string | null;
  } | null;
  channels?: { id: number; channel_code: string }[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AdminAccountListResponse {
  success: boolean;
  total: number;
  accounts: AdminAccount[];
}

export async function getAccountsAdmin(params?: {
  keyword?: string;
  status?: string;
  business_type?: string;
  sales_id?: number;
  tg_username?: string;
  country_codes?: string;
  channel_keyword?: string;
  limit?: number;
  offset?: number;
}): Promise<AdminAccountListResponse> {
  return request.get('/admin/accounts', { params });
}

export async function getAccountAdminDetail(accountId: number): Promise<any> {
  return request.get(`/admin/accounts/${accountId}`);
}

export async function createAccountAdmin(data: {
  account_name: string;
  email: string;
  password: string;
  tg_username?: string;
  business_type?: string;
  currency?: string;
  rate_limit?: number;
  ip_whitelist?: string[];
  low_balance_threshold?: number;
  company_name?: string;
  contact_person?: string;
  contact_phone?: string;
  sales_id?: number;
  channel_ids?: number[];
}): Promise<any> {
  return request.post('/admin/accounts', data);
}

export async function updateAccountAdmin(
  accountId: number,
  data: {
    account_name?: string;
    tg_username?: string;
    business_type?: string;
    status?: string;
    currency?: string;
    rate_limit?: number;
    ip_whitelist?: string[];
    low_balance_threshold?: number;
    company_name?: string;
    contact_person?: string;
    contact_phone?: string;
    sales_id?: number;
    channel_ids?: number[];
  }
): Promise<any> {
  return request.put(`/admin/accounts/${accountId}`, data);
}

export async function resetAccountApiKey(accountId: number): Promise<any> {
  return request.post(`/admin/accounts/${accountId}/reset-api-key`);
}

export async function resetAccountPassword(accountId: number, password: string): Promise<any> {
  return request.post(`/admin/accounts/${accountId}/reset-password`, { password });
}

export async function adjustAccountBalance(
  accountId: number,
  data: {
    amount: number;
    change_type?: string;
    description?: string;
    transaction_id?: string;
  }
): Promise<any> {
  return request.post(`/admin/accounts/${accountId}/balance/adjust`, data);
}

export async function getAccountBalanceLogs(
  accountId: number,
  params?: { limit?: number; offset?: number }
): Promise<any> {
  return request.get(`/admin/accounts/${accountId}/balance-logs`, { params });
}

// 充值记录查询（含退补充值）
export async function getRechargeLogs(params?: {
  account_id?: number
  sales_id?: number
  change_type?: string
  start_date?: string
  end_date?: string
  page?: number
  page_size?: number
}): Promise<any> {
  return request.get('/admin/recharge-logs', { params });
}

// 发送统计查询（按员工/通道/客户）
export async function getSendStatistics(params?: {
  account_id?: number
  sales_id?: number
  channel_id?: number
  report_type?: string
  start_date?: string
  end_date?: string
  page?: number
  page_size?: number
}): Promise<any> {
  return request.get('/admin/send-statistics', { params });
}

// --- Business Accounts (业务账户：语音/数据) ---

export interface BusinessAccount {
  id: number
  account_name: string
  business_type: string
  country_code: string
  status: string
  unit_price: number
  balance: number
  supplier_url: string | null
  supplier_credentials: Record<string, any> | null
  company_name: string | null
  contact_person: string | null
  contact_phone: string | null
  sales_id: number | null
  sales_name: string | null
  created_at: string | null
  updated_at: string | null
}

export async function getBusinessAccounts(params?: {
  business_type?: string
  country_code?: string
  status?: string
  keyword?: string
  sales_id?: number
  page?: number
  page_size?: number
}): Promise<{ success: boolean; total: number; items: BusinessAccount[] }> {
  return request.get('/admin/business-accounts', { params })
}

export async function getBusinessAccountDetail(accountId: number): Promise<{ success: boolean; account: BusinessAccount }> {
  return request.get(`/admin/business-accounts/${accountId}`)
}

export async function updateBusinessAccount(accountId: number, data: {
  account_name?: string
  status?: string
  company_name?: string
  contact_person?: string
  contact_phone?: string
  unit_price?: number
  supplier_url?: string
  supplier_credentials?: Record<string, any>
}): Promise<{ success: boolean }> {
  return request.put(`/admin/business-accounts/${accountId}`, data)
}

export async function deleteBusinessAccount(accountId: number): Promise<{ success: boolean }> {
  return request.delete(`/admin/business-accounts/${accountId}`)
}

export async function syncOkccBalances(): Promise<any> {
  return request.post('/admin/okcc/sync')
}

export async function getOkccCustomers(server?: string): Promise<any> {
  return request.get('/admin/okcc/customers', { params: server ? { server } : {} })
}

// --- Suppliers (供应商管理) ---

export async function getSuppliers(params?: {
  page?: number;
  page_size?: number;
  status?: string;
  keyword?: string;
}): Promise<any> {
  return request.get('/admin/suppliers', { params });
}

export async function getSupplier(supplierId: number): Promise<any> {
  return request.get(`/admin/suppliers/${supplierId}`);
}

export async function getSupplierChannels(supplierId: number): Promise<any> {
  return request.get(`/admin/suppliers/${supplierId}/channels`);
}

export async function linkSupplierChannel(
  supplierId: number,
  channelId: number,
  supplierChannelCode?: string
): Promise<any> {
  return request.post(`/admin/suppliers/${supplierId}/channels`, null, {
    params: { channel_id: channelId, supplier_channel_code: supplierChannelCode }
  });
}

export async function unlinkSupplierChannel(
  supplierId: number,
  channelId: number
): Promise<any> {
  return request.delete(`/admin/suppliers/${supplierId}/channels/${channelId}`);
}
