import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const sidebarCollapsed = ref(false)
  const theme = ref<'light' | 'dark'>(
    (localStorage.getItem('theme') as 'light' | 'dark') || 'dark'
  )
  const locale = ref(localStorage.getItem('locale') || 'zh-CN')

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function setTheme(value: 'light' | 'dark') {
    theme.value = value
    localStorage.setItem('theme', value)
    document.documentElement.setAttribute('data-theme', value)
  }

  function setLocale(value: string) {
    locale.value = value
    localStorage.setItem('locale', value)
  }

  return {
    sidebarCollapsed,
    theme,
    locale,
    toggleSidebar,
    setTheme,
    setLocale,
  }
})
