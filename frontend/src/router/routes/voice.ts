import type { RouteRecordRaw } from 'vue-router'

/** 客户侧语音（非管理端） */
export const voiceRoutes: RouteRecordRaw[] = [
  {
    path: '/voice/call',
    name: 'VoiceCall',
    component: () => import('@/views/voice/VoiceCall.vue'),
    meta: { titleKey: 'menu.makeCall', icon: 'Phone' },
  },
  {
    path: '/voice/records',
    name: 'VoiceRecords',
    component: () => import('@/views/voice/VoiceRecords.vue'),
    meta: { titleKey: 'menu.callRecords', icon: 'Document' },
  },
  {
    path: '/voice/caller-ids',
    name: 'VoiceCallerIdsCustomer',
    component: () => import('@/views/voice/VoiceCallerIdsCustomer.vue'),
    meta: { titleKey: 'menu.voiceCallerIdsCustomer', icon: 'Iphone' },
  },
]
