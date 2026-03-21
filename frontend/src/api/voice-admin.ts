import request from './index'

export interface VoiceRoute {
  id: number
  country_code: string
  provider_id?: number | null
  priority: number
  cost_per_minute: number
  created_at?: string | null
}

export interface VoiceCall {
  id: number
  call_id: string
  account_id: number
  caller?: string | null
  callee?: string | null
  start_time?: string | null
  end_time?: string | null
  duration?: number | null
  status?: string | null
  cost?: number | null
  created_at?: string | null
}

export function getVoiceRoutes(params?: { country_code?: string }) {
  return request.get('/admin/voice/routes', { params })
}

export function createVoiceRoute(data: {
  country_code: string
  provider_id?: number | null
  priority?: number
  cost_per_minute?: number
}) {
  return request.post('/admin/voice/routes', data)
}

export function updateVoiceRoute(routeId: number, data: any) {
  return request.put(`/admin/voice/routes/${routeId}`, data)
}

export function deleteVoiceRoute(routeId: number) {
  return request.delete(`/admin/voice/routes/${routeId}`)
}

export function getVoiceCalls(params?: {
  account_id?: number
  status?: string
  page?: number
  page_size?: number
}) {
  return request.get('/admin/voice/calls', { params })
}
