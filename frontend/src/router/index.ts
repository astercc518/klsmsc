import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { titleKey: 'login.title' },
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { titleKey: 'menu.dashboard', icon: 'DataAnalysis' },
      },
      {
        path: 'sms/send',
        name: 'SmsSend',
        component: () => import('@/views/sms/Send.vue'),
        meta: { titleKey: 'menu.sendSms', icon: 'Position' },
      },
      {
        path: 'sms/templates',
        name: 'SmsTemplates',
        component: () => import('@/views/sms/Templates.vue'),
        meta: { titleKey: 'menu.smsTemplates', icon: 'Document' },
      },
      {
        path: 'sms/tasks',
        name: 'SmsTasks',
        component: () => import('@/views/sms/BatchSend.vue'),
        meta: { titleKey: 'menu.sendTasks', icon: 'Upload' },
      },
      {
        path: 'sms/scheduled',
        name: 'SmsScheduled',
        component: () => import('@/views/sms/ScheduledTasks.vue'),
        meta: { titleKey: 'menu.scheduledTasks', icon: 'Timer' },
      },
      {
        path: 'sms/records',
        name: 'SmsRecords',
        component: () => import('@/views/sms/Records.vue'),
        meta: { titleKey: 'menu.sendRecords', icon: 'List' },
      },
      {
        path: 'account/info',
        name: 'AccountInfo',
        component: () => import('@/views/account/Info.vue'),
        meta: { titleKey: 'menu.accountInfo', icon: 'User' },
      },
      {
        path: 'account/api-keys',
        name: 'AccountApiKeys',
        component: () => import('@/views/account/ApiKeys.vue'),
        meta: { titleKey: 'menu.apiKeys', icon: 'Key' },
      },
      {
        path: 'account/settings',
        name: 'AccountSettings',
        component: () => import('@/views/account/Settings.vue'),
        meta: { titleKey: 'menu.accountSettings', icon: 'Setting' },
      },
      {
        path: 'account/sub-accounts',
        name: 'SubAccounts',
        component: () => import('@/views/account/SubAccounts.vue'),
        meta: { titleKey: 'menu.subAccounts', icon: 'UserFilled' },
      },
      {
        path: 'account/packages',
        name: 'Packages',
        component: () => import('@/views/account/Packages.vue'),
        meta: { titleKey: 'menu.packages', icon: 'Box' },
      },
      {
        path: 'account/notifications',
        name: 'Notifications',
        component: () => import('@/views/account/Notifications.vue'),
        meta: { titleKey: 'menu.notifications', icon: 'Bell' },
      },
      {
        path: 'account/security',
        name: 'Security',
        component: () => import('@/views/account/Security.vue'),
        meta: { titleKey: 'menu.security', icon: 'Lock' },
      },
      {
        path: 'account/balance',
        name: 'AccountBalance',
        component: () => import('@/views/account/Balance.vue'),
        meta: { titleKey: 'menu.balance', icon: 'Wallet' },
      },
      {
        path: 'data/store',
        name: 'DataStore',
        component: () => import('@/views/data/DataStore.vue'),
        meta: { titleKey: 'menu.dataStore', icon: 'Shop' },
      },
      {
        path: 'data/my-numbers',
        name: 'MyNumbers',
        component: () => import('@/views/data/MyNumbers.vue'),
        meta: { titleKey: 'menu.myNumbers', icon: 'Box' }
      },
      {
        path: 'data/orders',
        name: 'CustomerDataOrders',
        component: () => import('@/views/data/MyOrders.vue'),
        meta: { titleKey: 'menu.myOrders', icon: 'ShoppingCart' }
      },
      {
        path: 'channels',
        name: 'Channels',
        component: () => import('@/views/Channels.vue'),
        meta: { titleKey: 'menu.channels', icon: 'Connection' },
      },
      {
        path: 'reports',
        name: 'Reports',
        component: () => import('@/views/Reports.vue'),
        meta: { titleKey: 'menu.reports', icon: 'TrendCharts' },
      },
      {
        path: 'admin/accounts',
        name: 'AdminAccounts',
        component: () => import('@/views/admin/Accounts.vue'),
        meta: { titleKey: 'menu.customers', icon: 'User' },
      },
      {
        path: 'admin/sms-accounts',
        name: 'SmsAccounts',
        component: () => import('@/views/admin/Accounts.vue'),
        props: { defaultBusinessType: 'sms' },
        meta: { titleKey: 'menu.smsAccounts', icon: 'Message' },
      },
      {
        path: 'admin/staff',
        name: 'AdminStaff',
        component: () => import('@/views/admin/Staff.vue'),
        meta: { titleKey: 'menu.staff', icon: 'UserFilled' },
      },
      {
        path: 'admin/account-templates',
        name: 'AccountTemplates',
        component: () => import('@/views/admin/AccountTemplates.vue'),
        meta: { titleKey: 'menu.accountTemplates', icon: 'Document' },
      },
      // TG助手管理
      {
        path: 'admin/bot/config',
        name: 'BotConfig',
        component: () => import('@/views/bot/Config.vue'),
        meta: { titleKey: 'menu.botConfig', icon: 'Setting' },
      },
      {
        path: 'admin/bot/messages',
        name: 'BotMessages',
        component: () => import('@/views/bot/Messages.vue'),
        meta: { titleKey: 'menu.botMessages', icon: 'ChatDotRound' },
      },
      {
        path: 'admin/bot/invites',
        name: 'BotInvites',
        component: () => import('@/views/bot/Invites.vue'),
        meta: { titleKey: 'menu.botInvites', icon: 'Ticket' },
      },
      {
        path: 'admin/bot/recharge',
        name: 'BotRecharge',
        component: () => import('@/views/bot/RechargeAudit.vue'),
        meta: { titleKey: 'menu.rechargeAudit', icon: 'Money' },
      },
      {
        path: 'admin/bot/batches',
        name: 'BotBatches',
        component: () => import('@/views/bot/BatchAudit.vue'),
        meta: { titleKey: 'menu.batchAudit', icon: 'Files' },
      },
      {
        path: 'admin/bot/templates',
        name: 'BotTemplates',
        component: () => import('@/views/bot/Templates.vue'),
        meta: { titleKey: 'menu.whitelist', icon: 'Check' },
      },
      {
        path: 'admin/system/config',
        name: 'SystemConfig',
        component: () => import('@/views/system/Config.vue'),
        meta: { titleKey: 'menu.systemConfig', icon: 'Setting' },
      },
      {
        // 已将费率管理集成到通道配置中，保留旧路径跳转以避免空白页
        path: 'admin/pricing',
        redirect: '/channels',
      },
      // 供应商管理
      {
        path: 'admin/suppliers',
        name: 'Suppliers',
        component: () => import('@/views/admin/Suppliers.vue'),
        meta: { titleKey: 'menu.suppliers', icon: 'Shop' },
      },
      // 工单管理
      {
        path: 'admin/tickets',
        name: 'AdminTickets',
        component: () => import('@/views/admin/Tickets.vue'),
        meta: { titleKey: 'menu.tickets', icon: 'Tickets' },
      },
      {
        path: 'account/tickets',
        name: 'MyTickets',
        component: () => import('@/views/account/Tickets.vue'),
        meta: { titleKey: 'menu.myTickets', icon: 'Tickets' },
      },
      // 结算管理
      {
        path: 'admin/settlements',
        name: 'Settlements',
        component: () => import('@/views/admin/Settlements.vue'),
        meta: { titleKey: 'menu.settlements', icon: 'Money' },
      },
      // 语音业务管理
      {
        path: 'admin/voice/accounts',
        name: 'VoiceAccounts',
        component: () => import('@/views/admin/voice/Accounts.vue'),
        meta: { titleKey: 'menu.voiceAccounts', icon: 'User' },
      },
      {
        path: 'admin/voice/routes',
        name: 'VoiceRoutes',
        component: () => import('@/views/admin/voice/Routes.vue'),
        meta: { titleKey: 'menu.voiceRoutes', icon: 'Link' },
      },
      {
        path: 'admin/voice/calls',
        name: 'VoiceCalls',
        component: () => import('@/views/admin/voice/Calls.vue'),
        meta: { titleKey: 'menu.callRecords', icon: 'Phone' },
      },
      // 数据业务管理
      {
        path: 'admin/data/accounts',
        name: 'DataAccounts',
        component: () => import('@/views/admin/data/Accounts.vue'),
        meta: { titleKey: 'menu.dataAccounts', icon: 'User' },
      },
      {
        path: 'admin/data/upload',
        name: 'DataUpload',
        component: () => import('@/views/admin/data/Numbers.vue'),
        meta: { titleKey: 'menu.dataUpload', icon: 'Upload' },
      },
      {
        path: 'admin/data/products',
        name: 'DataProducts',
        component: () => import('@/views/admin/data/Products.vue'),
        meta: { titleKey: 'menu.dataProducts', icon: 'Goods' },
      },
      {
        path: 'admin/data/orders',
        name: 'DataOrders',
        component: () => import('@/views/admin/data/Orders.vue'),
        meta: { titleKey: 'menu.dataOrders', icon: 'ShoppingCart' },
      },
      {
        path: 'admin/data/pricing',
        name: 'DataPricing',
        component: () => import('@/views/admin/data/Pricing.vue'),
        meta: { titleKey: 'menu.dataPricing', icon: 'PriceTag' },
      },
      // 客户数据发送
      {
        path: 'sms/data-send',
        name: 'DataSend',
        component: () => import('@/views/sms/DataSend.vue'),
        meta: { titleKey: 'menu.dataSms', icon: 'DataLine' },
      },
      // 销售数据概览
      {
        path: 'sales/data',
        name: 'SalesDataOverview',
        component: () => import('@/views/sales/DataOverview.vue'),
        meta: { titleKey: 'menu.salesData', icon: 'TrendCharts' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to, from, next) => {
  // 页面标题在 MainLayout 中通过 i18n 动态设置

  // 处理管理员模拟登录（使用 sessionStorage，不影响其他窗口）
  if (to.path === '/login' && to.query.impersonate === '1' && to.query.api_key) {
    // 使用 sessionStorage 存储客户凭证（仅当前窗口有效）
    sessionStorage.setItem('impersonate_mode', '1')
    sessionStorage.setItem('impersonate_api_key', to.query.api_key as string)
    if (to.query.account_id) sessionStorage.setItem('impersonate_account_id', to.query.account_id as string)
    if (to.query.account_name) sessionStorage.setItem('impersonate_account_name', to.query.account_name as string)
    let redirect = (to.query.redirect as string) || '/sms/send'
    if (!redirect.startsWith('/') || redirect.startsWith('//')) redirect = '/sms/send'
    next(redirect)
    return
  }

  // 检查登录状态（支持用户、管理员和模拟登录）
  const isImpersonateMode = sessionStorage.getItem('impersonate_mode') === '1'
  const apiKey = localStorage.getItem('api_key')
  const adminToken = localStorage.getItem('admin_token')
  const isLoggedIn = !!(isImpersonateMode || apiKey || adminToken)

  // P1-FIX: /admin/* 路径必须有 admin_token
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

