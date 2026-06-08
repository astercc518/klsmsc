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
    // 后端返回 {success, profile: {role, ...}}；axios 拦截器已 unwrap 到 .data
    const role = (profile && (profile.profile?.role || profile.role || profile.data?.role)) || ''
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
  // 代客登录（新链路）：使用一次性 token 直换 api_key，避免先渲染登录页再跳转
  if (to.path === '/login' && to.query.impersonate === '1' && to.query.token) {
    try {
      const impToken = String(to.query.token)
      const base = import.meta.env.VITE_API_BASE_URL ? `${import.meta.env.VITE_API_BASE_URL}/api/v1` : '/api/v1'
      const res = await fetch(`${base}/admin/auth/impersonate-exchange/${encodeURIComponent(impToken)}`)
      if (!res.ok) throw new Error('token 无效或已过期')
      const data = await res.json()
      // 代客登录仅写 sessionStorage（标签页隔离），避免污染同浏览器管理员主标签页的 account_name
      sessionStorage.setItem('impersonate_mode', '1')
      sessionStorage.setItem('impersonate_api_key', data.api_key)
      if (data.account_id) sessionStorage.setItem('impersonate_account_id', String(data.account_id))
      if (data.account_name) sessionStorage.setItem('impersonate_account_name', data.account_name)
      next('/sms/send')
      return
    } catch (e) {
      // token 失效时回到普通登录页
      next('/login')
      return
    }
  }

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
  const apiKey = sessionStorage.getItem('api_key') || localStorage.getItem('api_key')
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

// 跨部署自愈：发版后 chunk 哈希变化，旧标签页仍引用已删除的旧 chunk，动态 import 会
// 失败(浏览器报 "Failed to fetch dynamically imported module" / MIME text/html)。
// 此时整页重载一次即可拿到 no-cache 的新 index.html → 加载新 chunk。用 sessionStorage
// 限一次,避免新 chunk 真不存在时无限刷新。导航成功后清标记,使后续发版仍可自愈。
const CHUNK_RELOAD_KEY = 'chunk-reload-once'
function isChunkLoadError(err: any): boolean {
  const msg = String(err?.message || err || '')
  return /dynamically imported module|Failed to fetch dynamically|Importing a module script failed|Loading chunk \d|error loading dynamically imported module|Failed to load module script/i.test(msg)
}
function reloadOnceForChunk() {
  if (!sessionStorage.getItem(CHUNK_RELOAD_KEY)) {
    sessionStorage.setItem(CHUNK_RELOAD_KEY, '1')
    window.location.reload()
  }
}
router.onError((error) => {
  if (isChunkLoadError(error)) reloadOnceForChunk()
})
router.afterEach(() => {
  // 成功完成一次导航说明 chunk 体系正常，清掉一次性标记
  sessionStorage.removeItem(CHUNK_RELOAD_KEY)
})
// Vite 预加载失败(modulepreload / 路由预取)也走自愈
window.addEventListener('vite:preloadError', (e: any) => {
  try { e?.preventDefault?.() } catch {}
  reloadOnceForChunk()
})

export default router
