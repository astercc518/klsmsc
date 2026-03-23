import request from './index'

// 获取通道列表
export const getChannels = async () => {
  // 检查是否为模拟登录模式
  const isImpersonateMode = sessionStorage.getItem('impersonate_mode') === '1'
  
  // 模拟登录模式：使用客户 API 接口
  if (isImpersonateMode) {
    const res: any = await request.get('/channels/list')
    return {
      success: res?.success ?? true,
      total: res?.total ?? (res?.channels?.length ?? 0),
      bound: res?.bound ?? false,
      channels: (res?.channels || []).map((ch: any) => ({
        id: ch.id,
        code: ch.code,
        name: ch.name,
        protocol: ch.protocol,
        status: ch.status,
      })),
    }
  }
  
  // 若已登录（用户名+密码登录会得到 admin_token），优先走管理员接口
  const adminToken = localStorage.getItem('admin_token')
  if (adminToken) {
    const res: any = await request.get('/admin/channels')
    return {
      success: res?.success ?? true,
      total: res?.total ?? (res?.channels?.length ?? 0),
      channels: (res?.channels || []).map((ch: any) => ({
        id: ch.id,
        code: ch.channel_code ?? ch.code,
        name: ch.channel_name ?? ch.name,
        protocol: ch.protocol,
        status: ch.status,
        connection_status: ch.connection_status ?? 'unknown',
        connection_checked_at: ch.connection_checked_at ?? null,
        priority: ch.priority ?? 0,
        weight: ch.weight ?? 0,
        max_tps: ch.max_tps ?? 100,
        concurrency: ch.concurrency ?? 1,
        rate_control_window: ch.rate_control_window ?? 1000,
        host: ch.host ?? null,
        port: ch.port ?? null,
        username: ch.username ?? null,
        api_url: ch.api_url ?? null,
        default_sender_id: ch.default_sender_id ?? null,
        supplier: ch.supplier ?? null,
        created_at: ch.created_at ?? null,
        updated_at: ch.updated_at ?? null,
      })),
    }
  }
  
  // 客户账户使用 API Key 访问通道列表
  const apiKey = localStorage.getItem('api_key')
  if (apiKey) {
    const res: any = await request.get('/channels/list')
    return {
      success: res?.success ?? true,
      total: res?.total ?? (res?.channels?.length ?? 0),
      bound: res?.bound ?? false,
      channels: (res?.channels || []).map((ch: any) => ({
        id: ch.id,
        code: ch.code,
        name: ch.name,
        protocol: ch.protocol,
        status: ch.status,
      })),
    }
  }
  
  // 未登录返回空
  return { success: false, total: 0, channels: [] }
}

// 获取通道详情
export const getChannelInfo = (channelId: number) => {
  return request.get(`/channels/${channelId}`)
}

// 获取管理员通道列表
export const getChannelsAdmin = () => {
  return request.get('/admin/channels')
}

