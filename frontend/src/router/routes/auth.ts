import type { RouteRecordRaw } from 'vue-router'

/** 公开路由：无需登录 */
export const authRoutes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { titleKey: 'login.title' },
  },
  {
    path: '/',
    name: 'Landing',
    component: () => import('@/views/Landing.vue'),
    meta: { titleKey: 'landing.title', public: true },
  },
]
