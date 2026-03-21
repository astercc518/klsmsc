import { createRouter, createWebHistory } from 'vue-router'
import { routes } from './routes'

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  // 代客登录模式
  if (to.path === '/login' && to.query.impersonate === '1' && to.query.api_key) {
    sessionStorage.setItem('impersonate_mode', '1')
    sessionStorage.setItem('impersonate_api_key', to.query.api_key as string)
    if (to.query.account_id) sessionStorage.setItem('impersonate_account_id', to.query.account_id as string)
    if (to.query.account_name) sessionStorage.setItem('impersonate_account_name', to.query.account_name as string)
    let redirect = (to.query.redirect as string) || '/sms/send'
    if (!redirect.startsWith('/') || redirect.startsWith('//')) redirect = '/sms/send'
    next(redirect)
    return
  }

  // 公开页面无需登录
  if (to.name === 'Landing' || to.path === '/login') {
    next()
    return
  }

  const isImpersonateMode = sessionStorage.getItem('impersonate_mode') === '1'
  const apiKey = localStorage.getItem('api_key')
  const adminToken = localStorage.getItem('admin_token')
  const isLoggedIn = !!(isImpersonateMode || apiKey || adminToken)

  const isAdminRoute = to.path.startsWith('/admin')
  if (isAdminRoute && !adminToken) {
    next('/dashboard')
    return
  }

  if (to.path !== '/login' && !isLoggedIn) {
    next('/login')
  } else if (to.path === '/login' && isLoggedIn) {
    next('/dashboard')
  } else {
    next()
  }
})

export default router
