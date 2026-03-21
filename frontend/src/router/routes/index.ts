import type { RouteRecordRaw } from 'vue-router'
import { authRoutes } from './auth'
import { smsRoutes } from './sms'
import { accountRoutes } from './account'
import { dataRoutes } from './data'
import { adminRoutes } from './admin'

/** 主布局下的子路由 */
const layoutChildren: RouteRecordRaw[] = [
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { titleKey: 'menu.dashboard', icon: 'DataAnalysis' },
  },
  ...smsRoutes,
  ...accountRoutes,
  ...dataRoutes,
  {
    path: '/channels',
    name: 'Channels',
    component: () => import('@/views/Channels.vue'),
    meta: { titleKey: 'menu.channels', icon: 'Connection' },
  },
  {
    path: '/reports',
    name: 'Reports',
    component: () => import('@/views/Reports.vue'),
    meta: { titleKey: 'menu.reports', icon: 'TrendCharts' },
  },
  ...adminRoutes,
  {
    path: '/sales/data',
    name: 'SalesDataOverview',
    component: () => import('@/views/sales/DataOverview.vue'),
    meta: { titleKey: 'menu.salesData', icon: 'TrendCharts' },
  },
]

/** 完整路由配置 */
export const routes: RouteRecordRaw[] = [
  ...authRoutes,
  {
    path: '/_',
    component: () => import('@/layouts/MainLayout.vue'),
    children: layoutChildren,
  },
]
