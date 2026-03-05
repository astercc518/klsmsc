/**
 * 报表统计API
 */
import { request } from './index';

export interface StatisticsResponse {
  total_sent: number;
  total_delivered: number;
  total_failed: number;
  success_rate: number;
  total_cost: number;
  currency: string;
}

export interface SuccessRateResponse {
  overall_rate: number;
  by_channel: Array<{
    channel_id: number;
    channel_code: string;
    channel_name: string;
    total: number;
    delivered: number;
    success_rate: number;
  }>;
  by_country: Array<{
    country_code: string;
    total: number;
    delivered: number;
    success_rate: number;
  }>;
}

export interface DailyStatsResponse {
  success: boolean;
  days: number;
  statistics: Array<{
    date: string;
    total_sent: number;
    total_delivered: number;
    success_rate: number;
    total_cost: number;
  }>;
}

/**
 * 获取发送统计
 * 管理员使用 /admin/statistics，用户使用 /reports/statistics
 */
export async function getStatistics(
  startDate?: string,
  endDate?: string
): Promise<StatisticsResponse> {
  const params: any = {};
  if (startDate) params.start_date = startDate;
  if (endDate) params.end_date = endDate;

  const isImpersonateMode = sessionStorage.getItem('impersonate_mode') === '1';
  const adminToken = localStorage.getItem('admin_token');
  if (!isImpersonateMode && adminToken) {
    return request.get<StatisticsResponse>('/admin/statistics', { params });
  }

  return request.get<StatisticsResponse>('/reports/statistics', { params });
}

/**
 * 获取成功率分析
 * 管理员模式下返回空数据（暂未实现管理员版本）
 */
export async function getSuccessRate(
  startDate?: string,
  endDate?: string
): Promise<SuccessRateResponse> {
  const isImpersonateMode = sessionStorage.getItem('impersonate_mode') === '1';
  const adminToken = localStorage.getItem('admin_token');
  if (!isImpersonateMode && adminToken) {
    return {
      overall_rate: 0,
      by_channel: [],
      by_country: []
    };
  }

  const params: any = {};
  if (startDate) params.start_date = startDate;
  if (endDate) params.end_date = endDate;

  return request.get<SuccessRateResponse>('/reports/success-rate', { params });
}

/**
 * 获取每日统计
 * 管理员模式下返回空数据（暂未实现管理员版本）
 */
export async function getDailyStats(days: number = 7): Promise<DailyStatsResponse> {
  const isImpersonateMode = sessionStorage.getItem('impersonate_mode') === '1';
  const adminToken = localStorage.getItem('admin_token');
  if (!isImpersonateMode && adminToken) {
    return {
      success: true,
      days: days,
      statistics: []
    };
  }

  return request.get<DailyStatsResponse>('/reports/daily-stats', { params: { days } });
}
