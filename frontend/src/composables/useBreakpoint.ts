import { ref, onMounted, onUnmounted, readonly } from 'vue'

/**
 * 响应式断点 hook
 *
 * 断点对齐 Element Plus / 项目里既有的 768 / 1024 媒体查询。
 * 使用 matchMedia 而非 resize 监听，避免高频回流。
 */
const MOBILE_QUERY = '(max-width: 768px)'
const TABLET_QUERY = '(max-width: 1024px)'

const isMobile = ref(false)
const isTablet = ref(false)

let initialized = false
let mqMobile: MediaQueryList | null = null
let mqTablet: MediaQueryList | null = null

function syncMobile(e: MediaQueryList | MediaQueryListEvent) {
  isMobile.value = e.matches
}
function syncTablet(e: MediaQueryList | MediaQueryListEvent) {
  isTablet.value = e.matches
}

function ensureInit() {
  if (initialized || typeof window === 'undefined') return
  initialized = true
  mqMobile = window.matchMedia(MOBILE_QUERY)
  mqTablet = window.matchMedia(TABLET_QUERY)
  syncMobile(mqMobile)
  syncTablet(mqTablet)
  // addEventListener('change') 在 Safari ≥ 14 与所有现代浏览器支持
  mqMobile.addEventListener('change', syncMobile)
  mqTablet.addEventListener('change', syncTablet)
}

export function useBreakpoint() {
  onMounted(ensureInit)
  // 全局单例，无需 onUnmounted 销毁；进程结束时浏览器自动回收
  onUnmounted(() => { /* keep singleton listeners */ })
  return {
    isMobile: readonly(isMobile),
    isTablet: readonly(isTablet),
  }
}
