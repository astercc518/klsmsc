import type { RouteRecordRaw } from 'vue-router'

/** 管理后台路由 */
export const adminRoutes: RouteRecordRaw[] = [
  {
    path: '/admin/accounts',
    name: 'AdminAccounts',
    component: () => import('@/views/admin/Accounts.vue'),
    meta: { titleKey: 'menu.customers', icon: 'User' },
  },
  {
    path: '/admin/sms-accounts',
    name: 'SmsAccounts',
    component: () => import('@/views/admin/Accounts.vue'),
    props: { defaultBusinessType: 'sms' },
    meta: { titleKey: 'menu.smsAccounts', icon: 'Message' },
  },
  {
    path: '/admin/staff',
    name: 'AdminStaff',
    component: () => import('@/views/admin/Staff.vue'),
    meta: { titleKey: 'menu.staff', icon: 'UserFilled' },
  },
  {
    path: '/admin/account-templates',
    name: 'AccountTemplates',
    component: () => import('@/views/admin/AccountTemplates.vue'),
    meta: { titleKey: 'menu.accountTemplates', icon: 'Document' },
  },
  {
    path: '/admin/bot/config',
    name: 'BotConfig',
    component: () => import('@/views/bot/Config.vue'),
    meta: { titleKey: 'menu.botConfig', icon: 'Setting' },
  },
  {
    path: '/admin/bot/messages',
    name: 'BotMessages',
    component: () => import('@/views/bot/Messages.vue'),
    meta: { titleKey: 'menu.botMessages', icon: 'ChatDotRound' },
  },
  {
    path: '/admin/bot/invites',
    name: 'BotInvites',
    component: () => import('@/views/bot/Invites.vue'),
    meta: { titleKey: 'menu.botInvites', icon: 'Ticket' },
  },
  {
    path: '/admin/bot/templates',
    name: 'BotTemplates',
    component: () => import('@/views/bot/Templates.vue'),
    meta: { titleKey: 'menu.whitelist', icon: 'Check' },
  },
  {
    path: '/admin/business-knowledge',
    name: 'BusinessKnowledge',
    component: () => import('@/views/admin/BusinessKnowledge.vue'),
    meta: { titleKey: 'menu.businessKnowledge', icon: 'Document' },
  },
  {
    path: '/admin/profile',
    name: 'AdminProfile',
    component: () => import('@/views/admin/Profile.vue'),
    meta: { titleKey: 'menu.accountManage', icon: 'User' },
  },
  {
    path: '/admin/system/config',
    name: 'SystemConfig',
    component: () => import('@/views/system/Index.vue'),
    meta: { titleKey: 'menu.systemConfig', icon: 'Setting' },
  },
  {
    path: '/admin/pricing',
    redirect: '/channels',
  },
  {
    path: '/admin/suppliers',
    name: 'Suppliers',
    component: () => import('@/views/admin/Suppliers.vue'),
    meta: { titleKey: 'menu.suppliers', icon: 'Shop' },
  },
  {
    path: '/admin/tickets',
    name: 'AdminTickets',
    component: () => import('@/views/admin/Tickets.vue'),
    meta: { titleKey: 'menu.tickets', icon: 'Tickets' },
  },
  {
    path: '/admin/settlements',
    name: 'Settlements',
    component: () => import('@/views/admin/Settlements.vue'),
    meta: { titleKey: 'menu.settlements', icon: 'Money' },
  },
  {
    path: '/admin/data/accounts',
    name: 'DataAccounts',
    component: () => import('@/views/admin/data/Accounts.vue'),
    meta: { titleKey: 'menu.dataAccounts', icon: 'User' },
  },
  {
    path: '/admin/data/upload',
    name: 'DataUpload',
    component: () => import('@/views/admin/data/Numbers.vue'),
    meta: { titleKey: 'menu.dataUpload', icon: 'Upload' },
  },
  {
    path: '/admin/data/products',
    name: 'DataProducts',
    component: () => import('@/views/admin/data/Products.vue'),
    meta: { titleKey: 'menu.dataProducts', icon: 'Goods' },
  },
  {
    path: '/admin/data/orders',
    name: 'DataOrders',
    component: () => import('@/views/admin/data/Orders.vue'),
    meta: { titleKey: 'menu.dataOrders', icon: 'ShoppingCart' },
  },
  {
    path: '/admin/data/pricing',
    name: 'DataPricing',
    component: () => import('@/views/admin/data/Pricing.vue'),
    meta: { titleKey: 'menu.dataPricing', icon: 'PriceTag' },
  },
]
