import { request } from './index'

// 套餐相关API
export const packageApi = {
  // 查询套餐列表（公开接口）
  list(params?: {
    page?: number
    page_size?: number
    status?: string
    is_featured?: boolean
  }) {
    return request.get('/packages', { params })
  },

  // 获取套餐详情
  get(id: number) {
    return request.get(`/packages/${id}`)
  },

  // 购买套餐
  purchase(packageId: number, data: {
    payment_method?: string
  }) {
    return request.post(`/packages/${packageId}/purchase`, data)
  },

  // 查询我的套餐
  getMyPackages(params?: { is_active?: boolean }) {
    return request.get('/my-packages', { params })
  }
}
