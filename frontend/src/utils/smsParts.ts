/**
 * 短信分段与编码判断（与 backend/app/core/pricing.py 中
 * PricingEngine._is_gsm7 / _count_sms_parts 保持一致，供前端预估条数）
 */

/** 与 pricing._is_gsm7 字符集一致 */
const GSM7_CHARSET =
  '@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?' +
  '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà'

const GSM7_SET = new Set(GSM7_CHARSET)

/**
 * 与 backend app.utils.sms_segment.normalize_for_sms_segment_count 一致：
 * 分段前去掉零宽、NBSP→空格、弯引号→ASCII，避免误判 UCS-2。
 */
export function normalizeForSmsSegmentCount(message: string): string {
  if (!message) return message
  const t = message.normalize('NFKC')
  let out = ''
  for (const c of t) {
    if (c === '\u00a0') out += ' '
    else if ('\u200b\u200c\u200d\ufeff'.includes(c)) continue
    else if (c === '\u2018' || c === '\u2019') out += "'"
    else if (c === '\u201c' || c === '\u201d') out += '"'
    else if (c === '\u2013') out += '-'
    else if (c === '\u2014') out += '-'
    else if (c === '\u2026') out += '...'
    else out += c
  }
  return out
}

/** 与 Python len(str) 一致：按 Unicode 码点计数 */
export function smsCodePointLength(message: string): number {
  return [...message].length
}

export function isGsm7Message(message: string): boolean {
  if (!message) return true
  const norm = normalizeForSmsSegmentCount(message)
  return [...norm].every((ch) => GSM7_SET.has(ch))
}

/** 与 app.utils.sms_segment.count_sms_parts 一致 */
export function countSmsParts(message: string): number {
  const norm = normalizeForSmsSegmentCount(message)
  const len = [...norm].length
  if (len === 0) return 0
  if ([...norm].every((ch) => GSM7_SET.has(ch))) {
    if (len <= 160) return 1
    return Math.floor((len + 152) / 153)
  }
  if (len <= 70) return 1
  return Math.floor((len + 66) / 67)
}
