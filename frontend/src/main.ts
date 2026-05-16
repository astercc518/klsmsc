import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import en from 'element-plus/es/locale/lang/en'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css' // 引入 Element Plus 暗黑变量
import './styles/dark-theme.css' // 引入我们的自定义暗黑高级主题
import './styles/admin-mobile.css' // 管理员后台全局移动端微调
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import router from './router'
import i18n, { getLocale } from './i18n'
import App from './App.vue'

const app = createApp(App)

// 注册Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// Element Plus 语言配置
const elementLocale = getLocale().startsWith('zh') ? zhCn : en

app.use(createPinia())
app.use(router)
app.use(i18n)
app.use(ElementPlus, { locale: elementLocale })

app.mount('#app')

// 注册 PWA service worker（仅生产环境 + 安全上下文）
if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').then((reg) => {
      // 发现新版本时自动跳过等待，下次导航即生效
      reg.addEventListener('updatefound', () => {
        const sw = reg.installing
        if (!sw) return
        sw.addEventListener('statechange', () => {
          if (sw.state === 'installed' && navigator.serviceWorker.controller) {
            sw.postMessage({ type: 'SKIP_WAITING' })
          }
        })
      })
    }).catch(() => { /* 失败静默：PWA 仅渐进增强 */ })
  })
}

