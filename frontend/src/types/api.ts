/**
 * API 通用类型定义
 */

/** 分页请求参数 */
export interface PaginationParams {
  page?: number
  page_size?: number
}

/** 分页响应结构 */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/** 通用 API 错误 */
export interface ApiError {
  message?: string
  detail?: string | Record<string, unknown>
  error?: { message?: string }
}

/** 列表查询通用参数 */
export interface ListQueryParams extends PaginationParams {
  search?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}
