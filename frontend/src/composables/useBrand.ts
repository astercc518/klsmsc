/**
 * 多品牌皮肤：拉取「当前激活品牌」并运行时套用——主色(及 Element Plus 衍生色阶)、
 * favicon、浏览器标题、品牌名/Logo。模块级响应式状态,MainLayout/Login/Landing 共享。
 *
 * 主色色阶按现有 dark-theme.css 的手算比例复刻(light-i 混白 (i-1)/10:3→20% 5→40%
 * 7→60% 8→70% 9→80%;dark-2 混黑 20%),并以 inline !important 压过样式表的 !important。
 * 拉取失败静默:保留 dark-theme.css 内置默认(考拉绿),不影响使用。
 */
import { ref } from 'vue'
import { getActiveBrand } from '@/api/brand'

const DEFAULT_NAME = '考拉出海'
const DEFAULT_COLOR = '#2a9d8f'

export const brandName = ref<string>('')
export const brandLogo = ref<string>('')
export const brandColor = ref<string>(DEFAULT_COLOR)
export const brandLoaded = ref(false)

function hexToRgb(hex: string): [number, number, number] | null {
  const m = /^#?([0-9a-fA-F]{6})$/.exec((hex || '').trim())
  if (!m) return null
  const n = parseInt(m[1], 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function toHex(n: number): string {
  const v = Math.round(Math.min(255, Math.max(0, n)))
  return v.toString(16).padStart(2, '0')
}

/** 把基色按 weight 比例混入 mixColor(weight=混入色占比 0~1) */
function mix(base: [number, number, number], mixC: [number, number, number], weight: number): string {
  const r = base[0] * (1 - weight) + mixC[0] * weight
  const g = base[1] * (1 - weight) + mixC[1] * weight
  const b = base[2] * (1 - weight) + mixC[2] * weight
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`
}

const WHITE: [number, number, number] = [255, 255, 255]
const BLACK: [number, number, number] = [0, 0, 0]
// light-i 的混白比例(复刻现有 dark-theme.css)
const LIGHT_WEIGHTS: Record<number, number> = { 3: 0.2, 5: 0.4, 7: 0.6, 8: 0.7, 9: 0.8 }

function applyPrimaryColor(hex: string) {
  const base = hexToRgb(hex)
  if (!base) return
  const root = document.documentElement
  // inline + important，压过 dark-theme.css 里的 !important
  root.style.setProperty('--el-color-primary', hex, 'important')
  for (const i of [3, 5, 7, 8, 9]) {
    root.style.setProperty(`--el-color-primary-light-${i}`, mix(base, WHITE, LIGHT_WEIGHTS[i]), 'important')
  }
  root.style.setProperty('--el-color-primary-dark-2', mix(base, BLACK, 0.2), 'important')
}

function applyFavicon(dataUrl?: string | null) {
  if (!dataUrl) return
  let link = document.querySelector("link[rel~='icon']") as HTMLLinkElement | null
  if (!link) {
    link = document.createElement('link')
    link.rel = 'icon'
    document.head.appendChild(link)
  }
  link.href = dataUrl
}

function applyTitle(name?: string | null) {
  if (name) document.title = name
}

/** 拉取并套用当前激活品牌。app 启动时调用一次即可。 */
export async function loadBrand(): Promise<void> {
  try {
    const r = await getActiveBrand()
    const b = r?.brand
    if (b) {
      brandName.value = b.name || ''
      brandLogo.value = b.logo || ''
      brandColor.value = b.primary_color || DEFAULT_COLOR
      applyPrimaryColor(brandColor.value)
      applyFavicon(b.favicon)
      applyTitle(b.name)
    }
  } catch {
    /* 公开接口失败静默：保留 dark-theme.css 默认皮肤 */
  } finally {
    brandLoaded.value = true
  }
}

export function useBrand() {
  return { brandName, brandLogo, brandColor, brandLoaded, loadBrand, DEFAULT_NAME, DEFAULT_COLOR }
}
