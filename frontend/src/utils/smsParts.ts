/**
 * 短信分段与编码判断（与 backend/app/core/pricing.py 中
 * PricingEngine._is_gsm7 / _count_sms_parts 保持一致，供前端预估条数）
 */

/** 与 pricing._is_gsm7 字符集一致 */
const GSM7_CHARSET =
  '@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?' +
  '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà'

const GSM7_SET = new Set(GSM7_CHARSET)

/** 与 Python len(str) 一致：按 Unicode 码点计数 */
export function smsCodePointLength(message: string): number {
  return [...message].length
}

export function isGsm7Message(message: string): boolean {
  if (!message) return true
  return [...message].every((ch) => GSM7_SET.has(ch))
}

/** 与 PricingEngine._count_sms_parts 一致 */
export function countSmsParts(message: string): number {
  const len = smsCodePointLength(message)
  if (len === 0) return 0
  if (isGsm7Message(message)) {
    if (len <= 160) return 1
    return Math.floor((len + 152) / 153)
  }
  if (len <= 70) return 1
  return Math.floor((len + 66) / 67)
}
