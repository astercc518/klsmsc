import type { RouteRecordRaw } from 'vue-router'

/** 数据业务路由 */
export const dataRoutes: RouteRecordRaw[] = [
  {
    path: '/data/store',
    name: 'DataStore',
    component: () => import('@/views/data/DataStore.vue'),
    meta: { titleKey: 'menu.dataStore', icon: 'Shop' },
  },
  {
    path: '/data/my-numbers',
    name: 'MyNumbers',
    component: () => import('@/views/data/MyNumbers.vue'),
    meta: { titleKey: 'menu.myNumbers', icon: 'Box' },
  },
  {
    path: '/data/orders',
    name: 'CustomerDataOrders',
    component: () => import('@/views/data/MyOrders.vue'),
    meta: { titleKey: 'menu.myOrders', icon: 'ShoppingCart' },
  },
]
