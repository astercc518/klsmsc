import { request } from './index'

const BASE = '/admin/water'

// ========== 代理管理 ==========
export const getProxies = (params?: any) =>
  request.get(`${BASE}/proxies`, { params })

export const createProxy = (data: any) =>
  request.post(`${BASE}/proxies`, data)

export const updateProxy = (id: number, data: any) =>
  request.put(`${BASE}/proxies/${id}`, data)

export const deleteProxy = (id: number) =>
  request.delete(`${BASE}/proxies/${id}`)

export const testProxy = (id: number, testCountry?: string) =>
  request.post(`${BASE}/proxies/${id}/test${testCountry ? `?test_country=${testCountry}` : ''}`)

// ========== 客户账户（供注水任务选择） ==========
export const getWaterAccounts = () =>
  request.get(`${BASE}/accounts`)

// ========== 注水任务 ==========
export const getTasks = (params?: any) =>
  request.get(`${BASE}/tasks`, { params })

export const getTaskStats = () =>
  request.get(`${BASE}/tasks/stats`)

/** 注水队列 web_automation 待执行任务数 */
export const getWaterQueueStats = () =>
  request.get(`${BASE}/queue/web-automation`)

/** 清空队列（须传确认口令，与后端 WATER_QUEUE_PURGE_CONFIRM_PHRASE 一致） */
export const purgeWaterQueue = (confirm_phrase: string) =>
  request.post(`${BASE}/queue/web-automation/purge`, { confirm_phrase })

/** 某账户已追踪的待执行注水任务数（未开始执行） */
export const getAccountPendingTracked = (accountId: number) =>
  request.get(`${BASE}/tasks/account/${accountId}/pending-tracked`)

/** 仅撤销该账户已追踪的排队任务，不影响其他账户 */
export const revokeAccountWaterPending = (accountId: number, confirm_phrase: string) =>
  request.post(`${BASE}/tasks/account/${accountId}/revoke-pending`, { confirm_phrase })

export const createTask = (data: any) =>
  request.post(`${BASE}/tasks`, data)

export const updateTask = (id: number, data: any) =>
  request.put(`${BASE}/tasks/${id}`, data)

export const toggleTask = (id: number) =>
  request.put(`${BASE}/tasks/${id}/toggle`)

export const deleteTask = (id: number) =>
  request.delete(`${BASE}/tasks/${id}`)

/** 某注水配置下，按发送批次维度的注水进度 */
export const getTaskBatchProgress = (taskConfigId: number, params?: { page?: number; page_size?: number }) =>
  request.get(`${BASE}/tasks/${taskConfigId}/batch-progress`, { params })

// ========== 注水记录 ==========
export const getLogs = (params?: any) =>
  request.get(`${BASE}/logs`, { params })

export const getLogScreenshot = (id: number) =>
  `${request.defaults.baseURL}${BASE}/logs/${id}/screenshot`

// ========== 注册脚本 ==========
export const getScripts = (params?: any) =>
  request.get(`${BASE}/scripts`, { params })

export const createScript = (data: any) =>
  request.post(`${BASE}/scripts`, data)

export const updateScript = (id: number, data: any) =>
  request.put(`${BASE}/scripts/${id}`, data)

export const deleteScript = (id: number) =>
  request.delete(`${BASE}/scripts/${id}`)

export const testScript = (id: number) =>
  request.post(`${BASE}/scripts/${id}/test`)
