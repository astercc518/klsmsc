import request from './index'

export interface AiConfig {
  ai_enabled: boolean
  model: string | null
}

export interface GenerateSmsRequest {
  prompt: string
  count?: number
  language?: string
  max_length?: number
}

export interface GenerateSmsResponse {
  success: boolean
  messages: string[]
  source: string
}

export function getAiConfig(): Promise<AiConfig> {
  return request({ url: '/ai/config', method: 'get' })
}

export function generateSmsContent(data: GenerateSmsRequest): Promise<GenerateSmsResponse> {
  return request({ url: '/ai/generate-sms', method: 'post', data })
}
