import { request } from './index'

export interface BrandTheme {
  id: number
  name: string
  primary_color: string
  logo?: string | null
  favicon?: string | null
  is_active: boolean
  created_at?: string | null
  updated_at?: string | null
}

/** 公开：当前激活品牌（登录前即可读，用于全站皮肤） */
export function getActiveBrand(): Promise<{ success: boolean; brand: BrandTheme | null }> {
  return request.get('/brand/active')
}

/** 管理：品牌列表 */
export function listBrands(): Promise<{ success: boolean; items: BrandTheme[] }> {
  return request.get('/admin/brands')
}

/** 管理：新增品牌（super_admin） */
export function createBrand(data: Partial<BrandTheme>): Promise<{ success: boolean; id: number }> {
  return request.post('/admin/brands', data)
}

/** 管理：编辑品牌（super_admin）。logo/favicon 传 undefined=不改、空串=清空 */
export function updateBrand(id: number, data: Partial<BrandTheme>): Promise<{ success: boolean }> {
  return request.put(`/admin/brands/${id}`, data)
}

/** 管理：设为激活（super_admin，全实例唯一） */
export function activateBrand(id: number): Promise<{ success: boolean }> {
  return request.post(`/admin/brands/${id}/activate`)
}

/** 管理：删除品牌（super_admin，不能删激活中的） */
export function deleteBrand(id: number): Promise<{ success: boolean }> {
  return request.delete(`/admin/brands/${id}`)
}
