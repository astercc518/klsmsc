import type { RouteRecordRaw } from 'vue-router'

/** 账户相关路由 */
export const accountRoutes: RouteRecordRaw[] = [
  {
    path: '/account/info',
    redirect: '/account/settings',
  },
  {
    path: '/account/manage',
    redirect: '/account/settings',
  },
  {
    path: '/account/api-keys',
    name: 'AccountApiKeys',
    component: () => import('@/views/account/ApiKeys.vue'),
    meta: { titleKey: 'menu.apiKeys', icon: 'Key' },
  },
  {
    path: '/account/settings',
    name: 'AccountSettings',
    component: () => import('@/views/account/Settings.vue'),
    meta: { titleKey: 'menu.accountManagement', icon: 'Setting' },
  },
  {
    path: '/account/sub-accounts',
    name: 'SubAccounts',
    component: () => import('@/views/account/SubAccounts.vue'),
    meta: { titleKey: 'menu.subAccounts', icon: 'UserFilled' },
  },
  {
    path: '/account/packages',
    name: 'Packages',
    component: () => import('@/views/account/Packages.vue'),
    meta: { titleKey: 'menu.packages', icon: 'Box' },
  },
  {
    path: '/account/notifications',
    name: 'Notifications',
    component: () => import('@/views/account/Notifications.vue'),
    meta: { titleKey: 'menu.notifications', icon: 'Bell' },
  },
  {
    path: '/account/security',
    name: 'Security',
    component: () => import('@/views/account/Security.vue'),
    meta: { titleKey: 'menu.security', icon: 'Lock' },
  },
  {
    path: '/account/balance',
    name: 'AccountBalance',
    component: () => import('@/views/account/Balance.vue'),
    meta: { titleKey: 'menu.balance', icon: 'Wallet' },
  },
  {
    path: '/account/tickets',
    name: 'MyTickets',
    component: () => import('@/views/account/Tickets.vue'),
    meta: { titleKey: 'menu.myTickets', icon: 'Tickets' },
  },
]
