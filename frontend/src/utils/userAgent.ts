/**
 * User-Agent 解析（仅用于前端展示，不参与 bot 判定）。
 *
 * 解析口径要和后端 utils/bot_ua.py + utils/bot_ip.py 保持精神一致：先识别
 * 已知 bot 关键词，再识别真人设备/浏览器；都识别不出就标 "未识别"。
 *
 * 注：bot 判定的最终结果以后端的 is_bot/bot_reason 为准；本工具只为把
 * 长长一串 UA 字符串翻译成一眼能读懂的设备/浏览器标签。
 */

export type UAKind = 'mobile' | 'desktop' | 'bot' | 'unknown'

export interface UAInfo {
  label: string                            // "iPhone Safari" / "Bot · IM 预览"
  device: string                           // "iPhone" / "Android" / "Windows" / "Bot"
  browser: string                          // "Safari" / "Chrome" / ""
  kind: UAKind
  tagType: '' | 'success' | 'warning' | 'danger' | 'info'
}

const UNKNOWN: UAInfo = {
  label: '未识别', device: 'Unknown', browser: '', kind: 'unknown', tagType: 'info',
}

export function parseUserAgent(ua?: string | null): UAInfo {
  if (!ua || ua.trim().length < 5) {
    return { label: '空 UA', device: 'Bot', browser: '', kind: 'bot', tagType: 'danger' }
  }
  const s = ua.toLowerCase()

  // ---- 已知 bot：按特异性排序 ----
  if (/googlebot|bingbot|yandex|duckduckbot|applebot|baiduspider/.test(s)) {
    return { label: '搜索引擎爬虫', device: 'Bot', browser: 'search', kind: 'bot', tagType: 'danger' }
  }
  // IM 链接预览 bot：必须用预览特异签名，避免误杀 LINE/Viber/微信 真人 App 内置浏览器。
  if (/facebookexternalhit|facebot|whatsapp|telegrambot|slackbot|linkedinbot|twitterbot|discordbot|skypeuripreview|linebotwebhook|line-bot|linepreview|viberurldownloader|viber-url-|viber url crawler|viberbot|wechat-bot|wechatlink-|kakaotalk-scrap|embedly|iframely/.test(s)) {
    return { label: 'IM 链接预览', device: 'Bot', browser: 'preview', kind: 'bot', tagType: 'warning' }
  }
  if (/antispam|safebrowsing|google-safety|trustwave|sophos|symantec|proofpoint|forcepoint|bluecoat|mimecast|barracuda|messagelabs|fortinet|kaspersky|avast|mcafee|linkpreview|urlchecker|phish|scanner|scanurl|fetcher/.test(s)) {
    return { label: '安全扫描器', device: 'Bot', browser: 'scanner', kind: 'bot', tagType: 'danger' }
  }
  if (/curl\/|wget\/|python-(requests|urllib)|httpx\/|go-http-client|java\/|okhttp|apache-httpclient|node-fetch|axios\/|guzzlehttp|aiohttp|winhttp|libwww-perl/.test(s)) {
    return { label: '编程客户端', device: 'Bot', browser: 'http-client', kind: 'bot', tagType: 'danger' }
  }
  if (/headlesschrome|phantomjs|puppeteer|playwright/.test(s)) {
    return { label: '无头浏览器', device: 'Bot', browser: 'headless', kind: 'bot', tagType: 'danger' }
  }
  if (/\bbot\b|spider|crawler|monitor/.test(s)) {
    return { label: 'Bot', device: 'Bot', browser: 'bot', kind: 'bot', tagType: 'danger' }
  }

  // ---- 设备 ----
  let device = 'Unknown'
  if (s.includes('iphone')) device = 'iPhone'
  else if (s.includes('ipad')) device = 'iPad'
  else if (s.includes('ipod')) device = 'iPod'
  else if (s.includes('openharmony') || s.includes('harmonyos')) device = 'HarmonyOS'
  else if (s.includes('android')) device = 'Android'
  else if (s.includes('windows nt') || s.includes('windows phone')) device = 'Windows'
  else if (s.includes('macintosh') || s.includes('mac os x')) device = 'Mac'
  else if (s.includes('cros')) device = 'ChromeOS'
  else if (s.includes('x11; linux') || s.includes('linux')) device = 'Linux'

  // ---- 浏览器（按特异性顺序，避免 chrome 提前命中盖住 edge/opera） ----
  let browser = ''
  if (s.includes('edg/') || s.includes('edga/') || s.includes('edgios/')) browser = 'Edge'
  else if (s.includes('opr/') || s.includes('opera')) browser = 'Opera'
  else if (s.includes('samsungbrowser')) browser = 'Samsung'
  else if (s.includes('miuibrowser')) browser = 'MIUI'
  else if (s.includes('huaweibrowser')) browser = 'Huawei'
  else if (s.includes('ucbrowser')) browser = 'UC'
  else if (s.includes('quark/')) browser = 'Quark'
  else if (s.includes('micromessenger')) browser = 'WeChat'
  else if (s.includes('qqbrowser')) browser = 'QQ'
  else if (/\bline\/[\d.]+/.test(s)) browser = 'LINE'        // 真人 LINE App 内置浏览器
  else if (/\bviber\/[\d.]+/.test(s)) browser = 'Viber'      // 真人 Viber App 内置浏览器
  else if (s.includes('kakaotalk') && !s.includes('scrap')) browser = 'KakaoTalk'
  else if (s.includes('crios/')) browser = 'Chrome'
  else if (s.includes('fxios/') || s.includes('firefox')) browser = 'Firefox'
  else if (s.includes('chrome/')) browser = 'Chrome'
  else if (s.includes('safari/')) browser = 'Safari'

  const isMobile = ['iPhone', 'iPad', 'iPod', 'Android', 'HarmonyOS'].includes(device)
  const isDesktop = ['Windows', 'Mac', 'Linux', 'ChromeOS'].includes(device)

  if (!isMobile && !isDesktop) return UNKNOWN

  const label = browser ? `${device} ${browser}` : device
  return {
    label,
    device,
    browser,
    kind: isMobile ? 'mobile' : 'desktop',
    tagType: isMobile ? 'success' : '',
  }
}

/** bot_reason → 中文标签 */
const BOT_REASON_MAP: Record<string, string> = {
  empty_ua: '空 UA',
  http_client: '编程客户端',
  preview_bot: 'IM 链接预览',
  security_scanner: '安全扫描器',
  generic_bot: '通用 Bot',
  google_scanner: 'Google 扫描器',
  microsoft_scanner: 'Microsoft 扫描器',
  ip_fanout: 'IP 扇出',
}

export function formatBotReason(reason?: string | null): string {
  if (!reason) return '—'
  return BOT_REASON_MAP[reason] || reason
}
