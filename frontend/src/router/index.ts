import { createRouter, createWebHistory } from 'vue-router'
import { routes } from './routes'
import { request } from '@/api'

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/**
 * 校验 admin 角色：localStorage.admin_role 可被篡改，必须从后端 /admin/profile 拉真实角色。
 * 通过 sessionStorage 缓存避免每次跳路由都打 API。退出登录会清掉 sessionStorage（在 stores/auth.ts）。
 */
async function ensureAdminRoleVerified(): Promise<string | null> {
  const cached = sessionStorage.getItem('admin_role_verified')
  if (cached) return cached
  try {
    const profile = await request.get<any>('/admin/profile')
    const role = (profile && (profile.role || profile.data?.role)) || ''
    if (role) {
      sessionStorage.setItem('admin_role_verified', role)
      // 把可信角色同步回 localStorage（被读的多处一起更新）
      localStorage.setItem('admin_role', role)
    }
    return role || null
  } catch (err) {
    return null
  }
}

router.beforeEach(async (to, from, next) => {
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

  // admin 路由：用后端 /admin/profile 校验真实角色
  // 防止用户篡改 localStorage.admin_role 让前端菜单显示更多入口
  if (isAdminRoute && adminToken) {
    const role = await ensureAdminRoleVerified()
    if (!role) {
      // token 失效或后端拒绝 → 强制重新登录
      localStorage.removeItem('admin_token')
      localStorage.removeItem('admin_role')
      sessionStorage.removeItem('admin_role_verified')
      next('/login')
      return
    }
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
