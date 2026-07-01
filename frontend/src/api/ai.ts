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

export interface TranslateRequest {
  texts: string[]
  target?: string
  source?: string
}

export interface TranslateResponse {
  success: boolean
  translations: string[]
}

export function translateTexts(data: TranslateRequest): Promise<TranslateResponse> {
  return request({ url: '/ai/translate', method: 'post', data })
}

export interface ParaphraseRequest {
  text: string
  lang?: string
  count?: number
}

export interface ParaphraseResponse {
  success: boolean
  variants: string[]
  source: string
}

export function paraphraseText(data: ParaphraseRequest): Promise<ParaphraseResponse> {
  return request({ url: '/ai/paraphrase', method: 'post', data })
}
