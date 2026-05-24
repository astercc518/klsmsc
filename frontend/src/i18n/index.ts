import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import enUS from './locales/en-US'

export type LocaleType = 'zh-CN' | 'en-US'

/**
 * 自定义 messageCompiler：完全用纯 JS 拼字符串，**不调 new Function**，
 * 让站点能在不放开 CSP 'unsafe-eval' 的前提下用 vue-i18n。
 *
 * 项目里 messages 的语法只用到两种：
 *   1. 命名插值：`{name}`
 *   2. 字面量转义：`{'@'}` → 输出原始 `@`
 * 没有 linked (`@:key`)、plural pipes (`a | b | c`)、datetime/number。如果以后
 * 引入这些特性，这个 compiler 也要相应扩展。
 */
type CompiledFn = (ctx: { values?: Record<string, unknown> }) => string

function compileMessageNoEval(message: string): CompiledFn {
  type Tok = { kind: 'text'; v: string } | { kind: 'var'; name: string } | { kind: 'literal'; v: string }
  const tokens: Tok[] = []
  let i = 0
  const n = message.length
  while (i < n) {
    const open = message.indexOf('{', i)
    if (open < 0) {
      tokens.push({ kind: 'text', v: message.slice(i) })
      break
    }
    if (open > i) tokens.push({ kind: 'text', v: message.slice(i, open) })
    const close = message.indexOf('}', open)
    if (close < 0) {
      tokens.push({ kind: 'text', v: message.slice(open) })
      break
    }
    const inner = message.slice(open + 1, close).trim()
    // 字面量转义 `{'xxx'}` → 输出 xxx
    if (inner.length >= 2 && inner.startsWith("'") && inner.endsWith("'")) {
      tokens.push({ kind: 'literal', v: inner.slice(1, -1) })
    } else if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(inner)) {
      tokens.push({ kind: 'var', name: inner })
    } else {
      // 不认识的占位符 → 原样保留（防止把含 { 的文案吃掉）
      tokens.push({ kind: 'text', v: message.slice(open, close + 1) })
    }
    i = close + 1
  }

  return (ctx) => {
    const values = ctx?.values || {}
    let out = ''
    for (const t of tokens) {
      if (t.kind === 'text' || t.kind === 'literal') out += t.v
      else {
        const v = values[t.name]
        out += v === undefined || v === null ? `{${t.name}}` : String(v)
      }
    }
    return out
  }
}

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
  // 关键：替换默认 compiler 避免 new Function（违反 CSP unsafe-eval）
  messageCompiler: (message: unknown) => {
    if (typeof message === 'function') return message as CompiledFn
    if (typeof message !== 'string') return () => String(message ?? '')
    return compileMessageNoEval(message)
  },
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
