import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import enUS from './locales/en-US'

export type LocaleType = 'zh-CN' | 'en-US'

// 获取默认语言（从 localStorage 读取）
export const getDefaultLocale = (): LocaleType => {
  try {
    const saved = localStorage.getItem('locale')
    if (saved === 'zh-CN' || saved === 'en-US') {
      return saved
    }
  } catch (e) {
    console.warn('无法读取 localStorage', e)
  }
  
  // 根据浏览器语言自动选择
  const browserLang = navigator.language
  if (browserLang.startsWith('zh')) return 'zh-CN'
  return 'en-US'
}

const i18n = createI18n({
  legacy: false, // 使用 Composition API 模式
  locale: getDefaultLocale(),
  fallbackLocale: 'en-US',
  globalInjection: true, // 全局注入 $t
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})

// 切换语言
export const setLocale = (locale: LocaleType) => {
  i18n.global.locale.value = locale
  try {
    localStorage.setItem('locale', locale)
  } catch (e) {
    console.warn('无法写入 localStorage', e)
  }
  document.documentElement.setAttribute('lang', locale)
}

// 获取当前语言（从 localStorage 读取，确保一致性）
export const getLocale = (): LocaleType => {
  try {
    const saved = localStorage.getItem('locale')
    if (saved === 'zh-CN' || saved === 'en-US') {
      return saved
    }
  } catch (e) {
    // ignore
  }
  return i18n.global.locale.value as LocaleType
}

export default i18n
