import type { RouteRecordRaw } from 'vue-router'

/** 短信业务路由 */
export const smsRoutes: RouteRecordRaw[] = [
  {
    path: '/sms/send',
    name: 'SmsSend',
    component: () => import('@/views/sms/Send.vue'),
    meta: { titleKey: 'menu.sendSms', icon: 'Position' },
  },
  {
    path: '/sms/templates',
    name: 'SmsTemplates',
    component: () => import('@/views/sms/Templates.vue'),
    meta: { titleKey: 'menu.smsTemplates', icon: 'Document' },
  },
  {
    path: '/sms/tasks',
    name: 'SmsTasks',
    component: () => import('@/views/sms/BatchSend.vue'),
    meta: { titleKey: 'menu.sendTasks', icon: 'Upload' },
  },
  {
    path: '/sms/scheduled',
    name: 'SmsScheduled',
    component: () => import('@/views/sms/ScheduledTasks.vue'),
    meta: { titleKey: 'menu.scheduledTasks', icon: 'Timer' },
  },
  {
    path: '/sms/records',
    name: 'SmsRecords',
    component: () => import('@/views/sms/Records.vue'),
    meta: { titleKey: 'menu.sendRecords', icon: 'List' },
  },
  {
    path: '/sms/approvals',
    name: 'SmsApprovals',
    component: () => import('@/views/sms/Approvals.vue'),
    meta: { titleKey: 'menu.smsApprovals', icon: 'DocumentChecked' },
  },
  {
    path: '/sms/recharge-records',
    name: 'SmsRechargeRecords',
    component: () => import('@/views/sms/RechargeRecords.vue'),
    meta: { titleKey: 'menu.rechargeRecords', icon: 'List' },
  },
  {
    path: '/sms/send-stats',
    name: 'SmsSendStats',
    component: () => import('@/views/sms/SendStats.vue'),
    meta: { titleKey: 'menu.sendStats', icon: 'TrendCharts' },
  },
  {
    path: '/sms/data-send',
    name: 'DataSend',
    component: () => import('@/views/sms/DataSend.vue'),
    meta: { titleKey: 'menu.dataSms', icon: 'DataLine' },
  },
]
