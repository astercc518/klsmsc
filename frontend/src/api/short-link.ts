/**
 * 短链：域名管理 + 客户端列表 + 批次点击统计
 */
import { request } from './index'

export interface ShortLinkDomain {
  id: number
  domain: string
  base_path: string
  scheme: string
  omit_scheme: boolean
  remark?: string | null
  status: 'active' | 'disabled'
  sort_order: number
  base_url: string
  // with_stats=true 时附带，否则为 undefined
  link_count?: number
  total_clicks?: number
  last_used_at?: string | null
}

export interface DomainPayload {
  domain: string
  base_path?: string
  scheme?: string
  omit_scheme?: boolean
  remark?: string | null
  status?: 'active' | 'disabled'
  sort_order?: number
}

// ---------- 客户端：仅 active 域名 ----------
export const listActiveShortLinkDomains = () =>
  request.get<{ data: ShortLinkDomain[] }>('/short-link-domains')

// ---------- 管理员：CRUD ----------
export const adminListShortLinkDomains = (
  params: { keyword?: string; status?: string; with_stats?: boolean } = {},
) =>
  request.get<{ data: ShortLinkDomain[] }>('/admin/short-link-domains', { params })

export const adminCreateShortLinkDomain = (payload: DomainPayload) =>
  request.post<{ data: ShortLinkDomain }>('/admin/short-link-domains', payload)

export const adminUpdateShortLinkDomain = (id: number, payload: Partial<DomainPayload>) =>
  request.put<{ data: ShortLinkDomain }>(`/admin/short-link-domains/${id}`, payload)

export const adminDeleteShortLinkDomain = (id: number) =>
  request.delete(`/admin/short-link-domains/${id}`)

// ---------- 短链 SSL 证书 ----------
export interface CertInfo {
  configured: boolean
  reason?: string
  path?: string
  key_path?: string
  sans?: string[]
  issuer?: string
  not_before?: string
  not_after?: string
  days_until_expiry?: number
  expired?: boolean
  fingerprint_sha256?: string
}

export const adminGetShortLinkCert = () =>
  request.get<{ data: CertInfo }>('/admin/short-link-domains/cert/info')

export const adminUploadShortLinkCert = (cert_pem: string, key_pem: string) =>
  request.post<{ data: { cert: CertInfo; reload: { success: boolean; method: string; error?: string } } }>(
    '/admin/short-link-domains/cert/upload',
    { cert_pem, key_pem },
  )

export const adminReloadShortLinkNginx = () =>
  request.post<{ data: { success: boolean; method: string; error?: string } }>(
    '/admin/short-link-domains/cert/reload',
  )

// ---------- 一域名一证书 ----------
export interface DomainCertInfo {
  configured: boolean
  domain_id: number
  reason?: string
  path?: string
  sans?: string[]
  issuer?: string
  not_before?: string
  not_after?: string
  days_until_expiry?: number
  expired?: boolean
  fingerprint_sha256?: string
}

export const adminGetDomainCert = (domainId: number) =>
  request.get<{ data: DomainCertInfo }>(`/admin/short-link-domains/${domainId}/cert/info`)

export const adminUploadDomainCert = (domainId: number, cert_pem: string, key_pem: string) =>
  request.post<{ data: { domain: string; cert: DomainCertInfo; reload: { success: boolean; error?: string } } }>(
    `/admin/short-link-domains/${domainId}/cert/upload`,
    { cert_pem, key_pem },
  )

export const adminDeleteDomainCert = (domainId: number) =>
  request.delete<{ data: { removed: string[]; reload: any } }>(
    `/admin/short-link-domains/${domainId}/cert`,
  )

// ---------- 批次点击统计（默认仅真人，机器扫描自动过滤） ----------
export interface ClickStats {
  batch_id: number
  total_links: number
  /** 真人点击过的短链数 */
  clicked_links: number
  /** 真人点击次数 */
  total_clicks: number
  /** 已自动过滤的机器扫描次数（仅展示用） */
  bot_clicks?: number
  /** 没有明细行的旧点击数（按真人计入；用于 UI 提示口径） */
  legacy_clicks?: number
}

export interface ClickedPhoneRow {
  phone_number: string
  /** 真人点击次数 */
  click_count: number
  human_clicks?: number
  last_click_at: string | null
  original_url: string
  token: string
}

export interface ClickDetailRow {
  clicked_at: string | null
  client_ip: string | null
  user_agent: string | null
  is_bot: boolean
  bot_reason: string | null
}

export interface TokenClicksResp {
  token: string
  /** 该 token 已被自动过滤的机器扫描次数 */
  filtered_bot_count: number
  items: ClickDetailRow[]
}

export const getBatchClickStats = (batchId: number) =>
  request.get<{ data: ClickStats }>(`/sms/batches/${batchId}/click-stats`)

export const listBatchClickedPhones = (
  batchId: number,
  page = 1,
  pageSize = 50,
) =>
  request.get<{
    data: { total: number; page: number; page_size: number; items: ClickedPhoneRow[] }
  }>(`/sms/batches/${batchId}/clicked-phones`, { params: { page, page_size: pageSize } })

/** 拉取单个 token 的最近真人点击明细（含 IP/UA）。include_bots=true 才含机器行，仅排查用。 */
export const listTokenClickDetails = (
  token: string,
  limit = 100,
  includeBots = false,
) =>
  request.get<{ data: TokenClicksResp }>(`/short-links/${token}/clicks`, {
    params: { limit, include_bots: includeBots },
  })

/** 触发 CSV 下载（浏览器原生流） */
export const downloadBatchClickedPhonesCsvUrl = (batchId: number): string => {
  const baseUrl = (import.meta as any).env?.VITE_API_BASE_URL
    ? `${(import.meta as any).env.VITE_API_BASE_URL}/api/v1`
    : '/api/v1'
  return `${baseUrl}/sms/batches/${batchId}/clicked-phones.csv`
}

// ---------- 短链域名：导出已点击号码（按国家筛选） ----------

export interface ClickedCountryItem {
  country_code: string
  count: number
}

/** 该域名下出现过的国家列表（仅含 click_count>=1 的号码） */
export const listClickedCountries = (domainId: number) =>
  request.get<{ success: boolean; items: ClickedCountryItem[] }>(
    `/admin/short-link-domains/${domainId}/clicked-countries`,
  )

/** 下载该域名已点击号码：fmt=txt（去重号码，每行一个，去 + 前缀）/ csv（含多维度） */
export const exportShortLinkClickedPhones = (
  domainId: number,
  opts: { country_code?: string; fmt: 'txt' | 'csv' },
): Promise<Blob> =>
  request.get(`/admin/short-link-domains/${domainId}/clicked-phones`, {
    params: { country_code: opts.country_code || undefined, fmt: opts.fmt },
    responseType: 'blob',
  }) as unknown as Promise<Blob>

// ---------- 占位符工具：在文案中插入/替换 URL ----------
export interface BuildPlaceholderArgs {
  targetUrl: string
  baseUrl?: string
}

/** 生成 {{TRACK_URL=...}} 占位符（带可选 |base_url） */
export function buildTrackUrlPlaceholder({ targetUrl, baseUrl }: BuildPlaceholderArgs): string {
  const t = (targetUrl || '').trim()
  const b = (baseUrl || '').trim()
  if (!t) return '{{TRACK_URL}}'
  if (!b) return `{{TRACK_URL=${t}}}`
  return `{{TRACK_URL=${t}|${b}}}`
}
