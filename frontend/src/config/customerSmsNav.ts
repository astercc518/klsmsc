/**
 * 客户端「短信业务」侧栏菜单顺序与路由（单一配置，避免漏加菜单项）
 */
export type CustomerSmsNavIcon = 'plane' | 'tasks' | 'records' | 'stats' | 'approvals'

export interface CustomerSmsNavItem {
  path: string
  titleKey: string
  icon: CustomerSmsNavIcon
}

export const CUSTOMER_SMS_NAV: CustomerSmsNavItem[] = [
  { path: '/sms/send', titleKey: 'menu.sendSms', icon: 'plane' },
  { path: '/sms/tasks', titleKey: 'menu.sendTasks', icon: 'tasks' },
  { path: '/sms/records', titleKey: 'menu.sendRecords', icon: 'records' },
  { path: '/sms/send-stats', titleKey: 'menu.sendStats', icon: 'stats' },
  { path: '/sms/approvals', titleKey: 'menu.smsApprovals', icon: 'approvals' },
]
