/**
 * 短信分段与编码判断（与 backend/app/core/pricing.py 中
 * PricingEngine._is_gsm7 / _count_sms_parts 保持一致，供前端预估条数）
 */

/** 与 pricing._is_gsm7 字符集一致 */
const GSM7_CHARSET =
  '@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?' +
  '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà'

const GSM7_SET = new Set(GSM7_CHARSET)

/** GSM-7 扩展表（escape）字符：仍是 GSM-7，但每个占 2 个 septet。
 *  与 backend sms_segment._GSM7_EXT_CHARS 一致。 */
const GSM7_EXT_SET = new Set('\f^{}\\[~]|€')

/** 返回 GSM-7 编码所需 septet 数；含非 GSM-7 字符返回 null。
 *  基本表 1 septet/字符，扩展表 2 septet/字符。 */
function gsm7SeptetCount(norm: string): number | null {
  let total = 0
  for (const c of norm) {
    if (GSM7_SET.has(c)) total += 1
    else if (GSM7_EXT_SET.has(c)) total += 2
    else return null
  }
  return total
}

/**
 * 与 backend app.utils.sms_segment.normalize_for_sms_segment_count 一致：
 * 仅做白名单字符替换（NBSP/零宽/弯引号/长破折/省略号），不做整段 NFKC ——
 * NFKC 会把 Thai SARA AM (ำ U+0E33→U+0E4D+U+0E32) 等单 UCS-2 码点拆开，
 * 造成 70 char 误判 71 多算 1 条；实际 SMS UCS-2 传输各占 1 个 16-bit 单元。
 */
export function normalizeForSmsSegmentCount(message: string): string {
  if (!message) return message
  let out = ''
  for (const c of message) {
    if (c === ' ') out += ' '
    else if ('​‌‍﻿'.includes(c)) continue
    else if (c === '‘' || c === '’') out += "'"
    else if (c === '“' || c === '”') out += '"'
    else if (c === '–') out += '-'
    else if (c === '—') out += '-'
    else if (c === '…') out += '...'
    else out += c
  }
  return out
}

/** 与 Python len(str) 一致：按 Unicode 码点计数；自动识别 {{TRACK_URL=...}} 占位符 */
export function smsCodePointLength(message: string): number {
  const effective = (message && message.indexOf('{{TRACK_URL') !== -1)
    ? substituteTrackUrlForCount(message)
    : message
  return [...(effective || '')].length
}

/**
 * 返回与「单段上限」同口径的长度：GSM-7 按 septet（扩展字符算 2），UCS-2 按码点。
 * 用于判断正文是否超出单段（GSM-7 比 160 / UCS-2 比 70），避免含 [ ] 等扩展字符时
 * 用码点数误判。自动识别 {{TRACK_URL=...}} 占位符。
 */
export function smsSegmentUnitLength(message: string): number {
  const effective = (message && message.indexOf('{{TRACK_URL') !== -1)
    ? substituteTrackUrlForCount(message)
    : message
  const norm = normalizeForSmsSegmentCount(effective || '')
  const septets = gsm7SeptetCount(norm)
  return septets !== null ? septets : [...norm].length
}

export function isGsm7Message(message: string): boolean {
  if (!message) return true
  const effective = (message.indexOf('{{TRACK_URL') !== -1)
    ? substituteTrackUrlForCount(message)
    : message
  const norm = normalizeForSmsSegmentCount(effective)
  return gsm7SeptetCount(norm) !== null
}

// 短链占位符识别：{{TRACK_URL}} / {{TRACK_URL=target}} / {{TRACK_URL=target|base}}
const TRACK_URL_RE = /\{\{TRACK_URL(?:=([^}]*))?\}\}/g

/**
 * 把 {{TRACK_URL=target|base}} 替换为「实际发送形态」字符串，仅用于字符数/分段计数。
 * - 有 base：替换为 `${base}/Ab3Xz7q`（base 取占位符内的真实值）
 * - 无 base：用兜底 'klsms.com' 估算
 *
 * 与 backend app.utils.sms_segment.substitute_track_url_for_count 行为一致。
 */
export function substituteTrackUrlForCount(message: string): string {
  if (!message || message.indexOf('{{TRACK_URL') === -1) return message
  return message.replace(TRACK_URL_RE, (_full, inner) => {
    let base = 'klsms.com'
    if (inner) {
      const parts = String(inner).split('|')
      if (parts.length >= 2 && parts[1].trim()) base = parts[1].trim()
    }
    return `${base.replace(/\/+$/, '')}/Ab3Xz7q`
  })
}

/** 与 app.utils.sms_segment.count_sms_parts 一致；自动识别 {{TRACK_URL=...}} 占位符 */
export function countSmsParts(message: string): number {
  const effective = (message && message.indexOf('{{TRACK_URL') !== -1)
    ? substituteTrackUrlForCount(message)
    : message
  const norm = normalizeForSmsSegmentCount(effective)
  const len = [...norm].length
  if (len === 0) return 0
  const septets = gsm7SeptetCount(norm)
  if (septets !== null) {
    // GSM-7：单段 160 septet，拼接每段 153
    if (septets <= 160) return 1
    return Math.floor((septets + 152) / 153)
  }
  // UCS-2：单段 70 码点，拼接每段 67
  if (len <= 70) return 1
  return Math.floor((len + 66) / 67)
}
