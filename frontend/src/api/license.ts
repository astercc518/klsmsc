import request from './index'

export interface LicenseStatus {
  state: string            // valid|grace|expired|invalid|wrong_machine|missing
  valid_for_send: boolean
  edition: string | null   // saas|private|oem
  customer: string | null
  expires_at: string | null
  days_left: number | null
  brand: { name?: string; logo?: string } | null
  message: string
  fingerprint?: string
}

export function getLicenseStatus() {
  return request.get('/admin/license/status')
}

export function getLicenseFingerprint() {
  return request.get('/admin/license/fingerprint')
}

export function uploadLicense(blob: string) {
  return request.post('/admin/license/upload', { blob })
}

// 公开:有效 OEM 品牌(供白标)
export function getBrand() {
  return request.get('/license/brand')
}

export function setBrand(payload: { name?: string; logo?: string }) {
  return request.put('/admin/license/brand', payload)
}
