<template>
<div class="dashboard">
    <!-- 顶部状态栏 -->
    <div class="dashboard-header">
      <div class="header-left">
        <h1 class="page-title">
          {{ getDashboardTitle() }}
        </h1>
        <span class="role-badge" :class="roleClass">{{ getRoleLabel() }}</span>
        <span class="last-update">{{ $t('dashboard.lastUpdate') }}: {{ lastUpdateTime }}</span>
        <!-- 构建戳：便于确认线上是否已部署含「关闭短信总览」的前端包；强刷或禁用 CDN 缓存 index.html 后应对更新 -->
        <span v-if="isStaff && !showStaffSmsOverview" class="build-stamp">{{ appBuildStamp }}</span>
      </div>
      <div class="header-right">
        <button class="refresh-btn" @click="refreshData" :disabled="loading">
          <svg :class="{ spinning: loading }" width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M14 8C14 11.3137 11.3137 14 8 14C4.68629 14 2 11.3137 2 8C2 4.68629 4.68629 2 8 2C10.5 2 12.5 3.5 13.5 5.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M11 5.5H14V2.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          {{ $t('dashboard.refreshData') }}
        </button>
      </div>
    </div>

    <!-- ========== 管理员/员工视图 ========== -->
<!-- 核心指标卡片 - 客户 -->
      <div class="metrics-grid metrics-4">
        <!-- 今日发送 -->
        <div class="metric-card soft-card soft-card-hover animate-scale" style="animation-delay: 0.1s">
          <div class="metric-header">
            <div class="metric-icon sent">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M18 2L9 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                <path d="M18 2L12 18L9 11L2 8L18 2Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
              </svg>
            </div>
            <span class="metric-label">{{ $t('dashboard.todaySent') }}</span>
          </div>
          <div class="metric-body">
            <span class="metric-value">{{ formatNumber(todaySent) }}</span>
            <span class="metric-unit">{{ $t('dashboard.items') }}</span>
          </div>
        </div>

        <!-- 本周发送 -->
        <div class="metric-card soft-card soft-card-hover animate-scale" style="animation-delay: 0.2s">
          <div class="metric-header">
            <div class="metric-icon success">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5"/>
                <path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
            <span class="metric-label">{{ $t('dashboard.weekSent') }}</span>
          </div>
          <div class="metric-body">
            <span class="metric-value">{{ formatNumber(weekSent) }}</span>
            <span class="metric-unit">{{ $t('dashboard.items') }}</span>
          </div>
        </div>

        <!-- 本月发送 -->
        <div class="metric-card soft-card soft-card-hover animate-scale" style="animation-delay: 0.3s">
          <div class="metric-header">
            <div class="metric-icon failed">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5"/>
                <path d="M8 8L12 12M12 8L8 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
            </div>
            <span class="metric-label">{{ $t('dashboard.monthSent') }}</span>
          </div>
          <div class="metric-body">
            <span class="metric-value">{{ formatNumber(monthSent) }}</span>
            <span class="metric-unit">{{ $t('dashboard.items') }}</span>
          </div>
        </div>

        <!-- 账户余额 -->
        <div class="metric-card clickable soft-card soft-card-hover animate-scale" @click="$router.push('/account/balance')" style="animation-delay: 0.4s">
          <div class="metric-header">
            <div class="metric-icon balance">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <rect x="2" y="4" width="16" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>
                <path d="M2 8H18" stroke="currentColor" stroke-width="1.5"/>
              </svg>
            </div>
            <span class="metric-label">{{ $t('dashboard.accountBalance') }}</span>
          </div>
          <div class="metric-body">
            <span class="metric-currency">$</span>
            <span class="metric-value">{{ formatNumber(balance) }}</span>
          </div>
          <div class="metric-footer">
            <span class="metric-link">{{ $t('common.view') }} →</span>
          </div>
        </div>
      </div>

      <!-- 主内容区 - 客户 -->
      <div class="content-grid customer-grid">
        <!-- 左侧 -->
        <div class="content-left">
          <!-- 快速操作 -->
          <div class="card actions-card">
            <div class="card-header">
              <h2 class="card-title">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <rect x="2" y="2" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
                  <rect x="10" y="2" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
                  <rect x="2" y="10" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
                  <rect x="10" y="10" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
                </svg>
                {{ $t('dashboard.quickActions') }}
              </h2>
            </div>
            <div class="actions-grid">
              <div class="action-btn primary soft-button" @click="$router.push('/sms/send')">
                <div class="action-icon">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M22 2L11 13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
                  </svg>
                </div>
                <span class="action-label">{{ $t('menu.sendSms') }}</span>
              </div>
              <div class="action-btn success soft-button" @click="$router.push('/sms/tasks')">
                <div class="action-icon">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <rect x="4" y="3" width="16" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
                    <path d="M9 7H15M9 11H15M9 15H12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>
                </div>
                <span class="action-label">{{ $t('menu.sendTasks') }}</span>
              </div>
              <div class="action-btn warning soft-button" @click="$router.push('/sms/records')">
                <div class="action-icon">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M14 2H6C5.44772 2 5 2.44772 5 3V21C5 21.5523 5.44772 22 6 22H18C18.5523 22 19 21.5523 19 21V7L14 2Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
                    <path d="M14 2V7H19" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
                    <path d="M9 13H15M9 17H12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>
                </div>
                <span class="action-label">{{ $t('menu.sendRecords') }}</span>
              </div>
              <div class="action-btn stats soft-button" @click="$router.push('/sms/send-stats')">
                <div class="action-icon">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M4 20V12M12 20V4M20 20V8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>
                </div>
                <span class="action-label">{{ $t('menu.sendStats') }}</span>
              </div>
              <div class="action-btn info soft-button" @click="$router.push('/sms/approvals')">
                <div class="action-icon">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M9 12L11 14L15 10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M9 5H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <path d="M12 3v6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>
                </div>
                <span class="action-label">{{ $t('menu.smsAudit') }}</span>
              </div>
              <div class="action-btn store soft-button" @click="$router.push('/data/store')">
                <div class="action-icon">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M3 9L12 2L21 9V20C21 20.5523 20.5523 21 20 21H4C3.44772 21 3 20.5523 3 20V9Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
                    <path d="M9 21V12H15V21" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
                  </svg>
                </div>
                <span class="action-label">{{ $t('menu.dataStore') }}</span>
              </div>
            </div>
          </div>

          <!-- 最近发送记录 -->
          <div class="card records-card">
            <div class="card-header">
              <h2 class="card-title">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <rect x="3" y="2" width="12" height="14" rx="2" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M6 6H12M6 9H12M6 12H9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
                {{ $t('dashboard.recentSent') }}
              </h2>
              <button class="view-all-btn" @click="$router.push('/sms/records')">
                {{ $t('dashboard.viewAll') }}
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M5 3L9 7L5 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
            </div>
            <div class="records-list">
              <div v-if="recentRecords.length === 0" class="empty-state">
                <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
                  <rect x="8" y="6" width="24" height="28" rx="3" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M14 14H26M14 20H26M14 26H20" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
                <span>{{ $t('smsRecords.noRecords') }}</span>
              </div>
              <div 
                v-else
                v-for="record in recentRecords" 
                :key="record.id" 
                class="record-item"
              >
                <div class="record-phone">
                  <span class="phone-flag">{{ getCountryFlag(record.country_code) }}</span>
                  <span class="phone-number">{{ record.phone_number }}</span>
                </div>
                <div class="record-message">{{ truncateMessage(record.message) }}</div>
                <div class="record-meta">
                  <span :class="['record-status', record.status]">
                    {{ getStatusText(record.status) }}
                  </span>
                  <span class="record-time">{{ formatTime(record.submit_time) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 右侧 -->
        <div class="content-right">
          <!-- 账户信息 -->
          <div class="card account-card">
            <div class="card-header">
              <h2 class="card-title">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <circle cx="9" cy="6" r="3" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M3 16C3 13.2386 5.68629 11 9 11C12.3137 11 15 13.2386 15 16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
                {{ $t('dashboard.accountInfo') }}
              </h2>
            </div>
            <div class="account-details account-details-customer">
              <div class="account-row">
                <span class="account-label">{{ $t('dashboard.clientName') }}</span>
                <span class="account-value">{{ customerDisplayName }}</span>
              </div>
              <div class="account-row">
                <span class="account-label">{{ $t('dashboard.tgAccount') }}</span>
                <span class="account-value">{{ formatTgHandle(customerAccountInfo?.tg_username) }}</span>
              </div>
              <div class="account-row">
                <span class="account-label">{{ $t('dashboard.country') }}</span>
                <span class="account-value">{{ countryDisplay(customerAccountInfo?.country_code) }}</span>
              </div>
              <div class="account-row">
                <span class="account-label">{{ $t('dashboard.unitPrice') }}</span>
                <span class="account-value">
                  <template v-if="customerAccountInfo?.unit_price != null && customerAccountInfo.unit_price > 0">
                    {{ customerAccountInfo.currency }} {{ formatUnitPrice(customerAccountInfo.unit_price) }} / {{ $t('dashboard.perSms') }}
                  </template>
                  <template v-else>—</template>
                </span>
              </div>
              <div class="account-row">
                <span class="account-label">{{ $t('dashboard.balance') }}</span>
                <span class="account-value">{{ customerAccountInfo ? `${customerAccountInfo.currency} ${formatNumber(customerAccountInfo.balance)}` : '—' }}</span>
              </div>
              <div class="account-row">
                <span class="account-label">{{ $t('dashboard.remainingSms') }}</span>
                <span class="account-value">
                  {{ customerAccountInfo?.remaining_sms_estimate != null ? formatNumber(customerAccountInfo.remaining_sms_estimate) : '—' }}
                </span>
              </div>
              <div class="account-row">
                <span class="account-label">{{ $t('dashboard.salesContactTg') }}</span>
                <span class="account-value">{{ formatTgHandle(customerAccountInfo?.sales_tg_username) }}</span>
              </div>
              <div class="account-row">
                <span class="account-label">{{ $t('dashboard.accountName') }}</span>
                <span class="account-value">{{ accountName }}</span>
              </div>
              <div class="account-row">
                <span class="account-label">{{ $t('dashboard.accountStatus') }}</span>
                <span :class="['status-badge', customerAccountStatusClass]">
                  <span class="status-dot"></span>
                  {{ customerAccountStatusLabel }}
                </span>
              </div>
              <div class="account-row">
                <span class="account-label">{{ $t('dashboard.apiKey') }}</span>
                <div class="api-key-wrapper">
                  <code class="api-key">{{ maskedApiKey }}</code>
                  <button class="copy-btn" @click="copyApiKey">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <rect x="4" y="4" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
                      <path d="M10 4V2.5C10 2 9.5 1.5 9 1.5H2.5C2 1.5 1.5 2 1.5 2.5V9C1.5 9.5 2 10 2.5 10H4" stroke="currentColor" stroke-width="1.5"/>
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
</template>

<script setup lang='ts'>

import { ref, onMounted, computed, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getAccountInfo, type AccountInfo } from '@/api/account'
import { getChannels } from '@/api/channel'
import { getStatistics } from '@/api/reports'
import { getAdminDashboard, type AdminServerMetrics, type AdminServiceStatusItem } from '@/api/admin'
import { getSMSRecords } from '@/api/sms'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

/**
 * 员工视图：是否展示短信运营总览（顶部 KPI、日环比、7 日趋势、客户 TOP、批次与通道统计）。
 * 固定为 false；若需恢复展示，改为 true 后重新构建并部署前端。
 */
const showStaffSmsOverview = false

/** 与 vite.config define 一致，用于页头展示以核对部署版本 */
const appBuildStamp = typeof __APP_BUILD_STAMP__ !== 'undefined' ? __APP_BUILD_STAMP__ : ''

const loading = ref(false)
const balance = ref<number>(0)
const todaySent = ref<number>(0)
/** 客户仪表盘：本周 / 本月发送条数 */
const weekSent = ref<number>(0)
const monthSent = ref<number>(0)
const customerAccountInfo = ref<AccountInfo | null>(null)
const todayDelivered = ref<number>(0)
const todayFailed = ref<number>(0)
const successRate = ref<number>(0)
const failRate = ref<number>(0)
const todayCost = ref<number>(0)
const todayRevenue = ref<number>(0)
const todayProfit = ref<number>(0)
const availableChannels = ref<number>(0)
const totalChannels = ref<number>(0)
const activeAccounts = ref<number>(0)
const totalBalance = ref<number>(0)
const accountId = ref('')
const isStaff = ref(false)
const isSales = ref(false)
const adminRole = ref('')
const lastUpdateTime = ref('')
const channels = ref<any[]>([])
const recentRecords = ref<any[]>([])
const recentCustomers = ref<any[]>([])
const permissions = ref({
  view_global: false,
  view_finance: false,
  view_channels: false,
  view_customers: false,
  view_system_monitor: false
})

const serverMetrics = ref<AdminServerMetrics | null>(null)
const serviceStatus = ref<AdminServiceStatusItem[]>([])

const yesterdayStats = ref<{ sent: number; delivered: number; failed: number; revenue: number }>({ sent: 0, delivered: 0, failed: 0, revenue: 0 })
const dailyTrend = ref<{ date: string; sent: number; delivered: number; revenue: number }[]>([])
const topCustomers = ref<{ account_name: string; sent: number; delivered: number; revenue: number }[]>([])
const batchOverview = ref<{ total: number; processing: number; completed: number; failed: number }>({ total: 0, processing: 0, completed: 0, failed: 0 })
const channelStats = ref<{ channel_name: string; sent: number; delivered: number; rate: number }[]>([])

/** 是否展示服务器监控区（与权限同步，供模板使用） */
const showSystemMonitor = computed(() => permissions.value.view_system_monitor)

/** 员工仪表盘加载中（用于监控卡片内占位，避免误判为「无数据」） */
const dashboardLoading = computed(() => loading.value && isStaff.value)

const accountName = ref(localStorage.getItem('account_name') || 'User')
const apiKey = ref(localStorage.getItem('api_key') || '')

const maskedApiKey = computed(() => {
  if (!apiKey.value) return '-'
  return apiKey.value.substring(0, 8) + '••••' + apiKey.value.substring(apiKey.value.length - 4)
})

const customerDisplayName = computed(() => {
  const c = customerAccountInfo.value
  if (!c) return accountName.value
  const name = (c.client_name || c.company_name || c.account_name || '').trim()
  return name || accountName.value
})

const customerAccountStatusLabel = computed(() => {
  const s = customerAccountInfo.value?.status || ''
  if (s === 'active') return t('common.active')
  if (s === 'suspended') return t('dashboard.accountSuspended')
  if (s === 'closed') return t('dashboard.accountClosed')
  return s || '—'
})

const customerAccountStatusClass = computed(() => {
  const s = customerAccountInfo.value?.status || ''
  if (s === 'active') return 'active'
  if (s === 'suspended') return 'warning'
  if (s === 'closed') return 'inactive'
  return 'inactive'
})

/** Telegram 展示为 @username */
function formatTgHandle(raw?: string | null): string {
  if (raw == null || String(raw).trim() === '') return '—'
  const u = String(raw).trim().replace(/^@+/, '')
  return u ? `@${u}` : '—'
}

/** 国家代码展示（可后续接完整国家库） */
function countryDisplay(code?: string | null): string {
  if (code == null || String(code).trim() === '') return '—'
  const c = String(code).trim().toUpperCase()
  const map: Record<string, string> = {
    CN: '中国',
    US: '美国',
    GB: '英国',
    BR: '巴西',
    BD: '孟加拉国',
    IN: '印度',
    ID: '印度尼西亚',
    MX: '墨西哥',
    PH: '菲律宾',
    VN: '越南',
    TH: '泰国',
    MY: '马来西亚',
    JP: '日本',
    KR: '韩国',
  }
  return map[c] || code
}

const roleClass = computed(() => {
  if (adminRole.value === 'super_admin' || adminRole.value === 'admin') return 'admin'
  if (adminRole.value === 'sales') return 'sales'
  if (adminRole.value === 'finance') return 'finance'
  if (adminRole.value === 'tech') return 'tech'
  return 'customer'
})

const getDashboardTitle = () => {
  if (adminRole.value === 'super_admin' || adminRole.value === 'admin') return t('dashboard.adminConsole')
  if (adminRole.value === 'sales') return t('dashboard.salesWorkbench')
  if (adminRole.value === 'finance') return t('dashboard.financeCenter')
  if (adminRole.value === 'tech') return t('dashboard.techMonitor')
  return t('dashboard.myConsole')
}

const getRoleLabel = () => {
  const roles: Record<string, string> = {
    'super_admin': t('roles.superAdmin'),
    'admin': t('roles.admin'),
    'sales': t('roles.sales'),
    'finance': t('roles.finance'),
    'tech': t('roles.tech'),
  }
  return roles[adminRole.value] || t('roles.customer')
}

const calcChange = (today: number, yesterday: number): { pct: string; dir: 'up' | 'down' | 'flat' } => {
  if (yesterday === 0 && today === 0) return { pct: '0', dir: 'flat' }
  if (yesterday === 0) return { pct: '+∞', dir: 'up' }
  const pct = ((today - yesterday) / yesterday * 100).toFixed(1)
  if (today > yesterday) return { pct: `+${pct}`, dir: 'up' }
  if (today < yesterday) return { pct: pct, dir: 'down' }
  return { pct: '0', dir: 'flat' }
}

const sentChange = computed(() => calcChange(todaySent.value, yesterdayStats.value.sent))
const deliveredChange = computed(() => calcChange(todayDelivered.value, yesterdayStats.value.delivered))
const revenueChange = computed(() => calcChange(todayRevenue.value, yesterdayStats.value.revenue))

const trendMaxSent = computed(() => Math.max(...dailyTrend.value.map(d => d.sent), 1))

const formatNumber = (num: number) => {
  const n = Number(num) || 0
  return n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

/** 短信单价：与账户设置页 AccountOverviewPanel.fmtNum 一致，最多 4 位小数，避免仪表盘误显示为 0.01 */
const formatUnitPrice = (num: number) => {
  const n = Number(num) || 0
  return n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 4 })
}

const formatRate = (rate: number) => {
  const r = Number(rate) || 0
  return r.toFixed(1)
}

/** 依赖服务展示名称 */
const serviceLabel = (id: string) => {
  const keys: Record<string, string> = {
    mysql: 'dashboard.serviceMysql',
    redis: 'dashboard.serviceRedis',
    rabbitmq: 'dashboard.serviceRabbitmq'
  }
  const k = keys[id]
  return k ? t(k) : id
}

const getCountryFlag = (code: string) => {
  const flags: Record<string, string> = {
    '86': '🇨🇳', '1': '🇺🇸', '44': '🇬🇧', '81': '🇯🇵', '82': '🇰🇷',
    '63': '🇵🇭', '84': '🇻🇳', '66': '🇹🇭', '62': '🇮🇩', '60': '🇲🇾',
    '52': '🇲🇽', '55': '🇧🇷', '91': '🇮🇳', '49': '🇩🇪', '33': '🇫🇷',
  }
  return flags[code] || '🌍'
}

const getStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    'pending': 'pending', 'sent': 'sent', 'delivered': 'delivered', 'failed': 'failed',
  }
  const key = statusMap[status] || status
  return t(`smsStatus.${key}`)
}

const getChannelStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    'active': t('channelStatus.active'),
    'inactive': t('channelStatus.inactive'),
    'maintenance': t('channelStatus.maintenance'),
  }
  return statusMap[status] || status
}

const truncateMessage = (msg: string) => {
  if (!msg) return '-'
  return msg.length > 25 ? msg.substring(0, 25) + '...' : msg
}

const formatTime = (time: string) => {
  if (!time) return '-'
  const date = new Date(time)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  if (diff < 60000) return t('time.justNow')
  if (diff < 3600000) return t('time.minutesAgo', { n: Math.floor(diff / 60000) })
  if (diff < 86400000) return t('time.hoursAgo', { n: Math.floor(diff / 3600000) })
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const updateLastTime = () => {
  lastUpdateTime.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

/** 统一仪表盘监控字段（兼容 snake_case / camelCase） */
function normalizeServerMetrics(raw: unknown): AdminServerMetrics | null {
  if (raw == null || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  if (typeof o.error === 'string') return { error: o.error }
  const arr = o.load_avg ?? o.loadAvg
  return {
    hostname: typeof o.hostname === 'string' ? o.hostname : undefined,
    cpu_percent: Number(o.cpu_percent ?? o.cpuPercent) || 0,
    memory_percent: Number(o.memory_percent ?? o.memoryPercent) || 0,
    memory_used_gb: Number(o.memory_used_gb ?? o.memoryUsedGb) || 0,
    memory_total_gb: Number(o.memory_total_gb ?? o.memoryTotalGb) || 0,
    disk_percent: Number(o.disk_percent ?? o.diskPercent) || 0,
    disk_free_gb: Number(o.disk_free_gb ?? o.diskFreeGb) || 0,
    disk_total_gb: Number(o.disk_total_gb ?? o.diskTotalGb) || 0,
    load_avg: Array.isArray(arr) ? (arr as number[]) : null
  }
}

function normalizeServiceStatus(raw: unknown): AdminServiceStatusItem[] {
  if (!Array.isArray(raw)) return []
  return raw.map((item) => {
    const o = item as Record<string, unknown>
    return {
      id: String(o.id ?? ''),
      status: o.status === 'ok' ? 'ok' : 'error',
      message: typeof o.message === 'string' ? o.message : undefined
    }
  })
}

const loadStaffData = async () => {
  try {
    const res = await getAdminDashboard()
    if (res.success) {
      accountName.value = res.admin_name
      adminRole.value = res.admin_role
      isSales.value = res.admin_role === 'sales'
      
      todaySent.value = Number(res.statistics.today_sent) || 0
      todayDelivered.value = Number(res.statistics.today_delivered) || 0
      todayFailed.value = Number(res.statistics.today_failed) || 0
      successRate.value = Number(res.statistics.today_success_rate) || 0
      failRate.value = todaySent.value > 0 ? (todayFailed.value / todaySent.value * 100) : 0
      todayCost.value = Number(res.statistics.today_cost) || 0
      todayRevenue.value = Number(res.statistics.today_revenue) || 0
      todayProfit.value = Number(res.statistics.today_profit) || 0
      availableChannels.value = Number(res.statistics.active_channels) || 0
      activeAccounts.value = Number(res.statistics.active_accounts) || 0
      totalBalance.value = Number(res.statistics.total_balance) || 0
      
      const perm = (res.permissions || {}) as Record<string, unknown>
      const roleMonitors = ['super_admin', 'admin', 'tech'].includes(res.admin_role || '')
      let viewSystemMonitor: boolean
      if (typeof perm.view_system_monitor === 'boolean') {
        viewSystemMonitor = perm.view_system_monitor
      } else if (typeof perm.viewSystemMonitor === 'boolean') {
        viewSystemMonitor = perm.viewSystemMonitor
      } else {
        // 旧版后端未返回该字段时，超级管理员 / 管理员 / 运维仍展示监控区（数据可能为空，见文案提示）
        viewSystemMonitor = roleMonitors
      }
      permissions.value = {
        view_global: false,
        view_finance: false,
        view_channels: false,
        view_customers: false,
        ...(res.permissions || {}),
        view_system_monitor: viewSystemMonitor,
      }
      yesterdayStats.value = res.yesterday_stats || { sent: 0, delivered: 0, failed: 0, revenue: 0 }
      dailyTrend.value = res.daily_trend || []
      topCustomers.value = res.top_customers || []
      batchOverview.value = res.batch_overview || { total: 0, processing: 0, completed: 0, failed: 0 }
      channelStats.value = res.channel_stats || []
      recentCustomers.value = res.recent_customers || []
      if (viewSystemMonitor) {
        const r = res as Record<string, unknown>
        serverMetrics.value = normalizeServerMetrics(r.server_metrics ?? r.serverMetrics)
        serviceStatus.value = normalizeServiceStatus(r.service_status ?? r.serviceStatus)
      } else {
        serverMetrics.value = null
        serviceStatus.value = []
      }
      
      // 加载通道
      if (permissions.value.view_channels) {
        try {
          const channelsRes = await getChannels()
          channels.value = channelsRes.channels || []
        } catch {
          channels.value = []
        }
      }
    }
  } catch (error) {
    console.error('Failed to load staff data:', error)
  }
}

const loadCustomerData = async () => {
  try {
    const infoRes = await getAccountInfo()
    customerAccountInfo.value = infoRes
    balance.value = Number(infoRes.balance) || 0
    accountId.value = String(infoRes.id)
    if (infoRes.account_name) {
      accountName.value = infoRes.account_name
      try {
        localStorage.setItem('account_name', infoRes.account_name)
      } catch {
        /* ignore */
      }
    }

    const todayStr = new Date().toISOString().split('T')[0]
    try {
      const statsRes = await getStatistics(todayStr, todayStr)
      todaySent.value = Number(statsRes.total_sent) || 0
    } catch {
      todaySent.value = 0
    }

    const now = new Date()
    const dow = now.getDay()
    const diffToMonday = dow === 0 ? -6 : 1 - dow
    const weekStart = new Date(now)
    weekStart.setDate(now.getDate() + diffToMonday)
    weekStart.setHours(0, 0, 0, 0)
    const weekStartStr = weekStart.toISOString().split('T')[0]
    try {
      const weekStats = await getStatistics(weekStartStr, todayStr)
      weekSent.value = Number(weekStats.total_sent) || 0
    } catch {
      weekSent.value = 0
    }

    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1)
    const monthStartStr = monthStart.toISOString().split('T')[0]
    try {
      const monthStats = await getStatistics(monthStartStr, todayStr)
      monthSent.value = Number(monthStats.total_sent) || 0
    } catch {
      monthSent.value = 0
    }

    todayDelivered.value = 0
    todayFailed.value = 0
    successRate.value = 0
    failRate.value = 0

    try {
      const recordsRes = await getSMSRecords({ page: 1, page_size: 5 })
      recentRecords.value = recordsRes.records || []
    } catch {
      recentRecords.value = []
    }
  } catch (error) {
    console.error('Failed to load customer data:', error)
  }
}

const loadData = async () => {
  loading.value = true
  try {
    const isImpersonateMode = sessionStorage.getItem('impersonate_mode') === '1'
    const adminToken = localStorage.getItem('admin_token')
    
    if (!isImpersonateMode && adminToken) {
      isStaff.value = true
      await loadStaffData()
    } else {
      isStaff.value = false
      adminRole.value = ''
      await loadCustomerData()
    }
    updateLastTime()
  } finally {
    loading.value = false
  }
}

const refreshData = () => {
  loadData()
  ElMessage.success(t('dashboard.dataRefreshed'))
}

const copyApiKey = async () => {
  if (!apiKey.value) return
  try {
    await navigator.clipboard.writeText(apiKey.value)
    ElMessage.success(t('common.copied'))
  } catch {
    ElMessage.error(t('common.error'))
  }
}

let refreshInterval: number

onMounted(() => {
  loadData()
  refreshInterval = window.setInterval(() => loadData(), 60000)
})

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval)
})

</script>

<style scoped>

.dashboard {
  width: 100%;
  min-height: 100%;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* 头部 */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.role-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.role-badge.admin {
  background: linear-gradient(135deg, rgba(255, 77, 79, 0.15), rgba(255, 120, 117, 0.1));
  color: #ff4d4f;
}

.role-badge.sales {
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.15), rgba(118, 75, 162, 0.1));
  color: var(--primary);
}

.role-badge.finance {
  background: linear-gradient(135deg, rgba(255, 210, 0, 0.15), rgba(247, 151, 30, 0.1));
  color: var(--warning);
}

.role-badge.tech {
  background: linear-gradient(135deg, rgba(79, 172, 254, 0.15), rgba(0, 242, 254, 0.1));
  color: var(--info);
}

.role-badge.customer {
  background: linear-gradient(135deg, rgba(56, 239, 125, 0.15), rgba(17, 153, 142, 0.1));
  color: var(--success);
}

.last-update {
  font-size: 12px;
  color: var(--text-quaternary);
  margin-left: 8px;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: rgba(102, 126, 234, 0.1);
  border: 1px solid rgba(102, 126, 234, 0.2);
  border-radius: 10px;
  color: var(--primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover:not(:disabled) {
  background: rgba(102, 126, 234, 0.15);
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.refresh-btn svg.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 核心指标 */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
  margin-bottom: 32px;
}

.metrics-grid.metrics-4 {
  grid-template-columns: repeat(4, 1fr);
}

.metrics-grid.metrics-6 {
  grid-template-columns: repeat(6, 1fr);
}

/* 服务器性能与服务状态 */
.system-monitor-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 32px;
}

.server-health-card,
.service-health-card {
  height: auto;
}

.server-health-body,
.service-health-body {
  padding: 16px 20px 20px;
}

.host-line {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0 0 16px;
}

.host-label {
  opacity: 0.85;
}

.host-value {
  color: var(--text-primary);
  font-weight: 500;
}

.perf-row {
  margin-bottom: 14px;
}

.perf-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.perf-pct {
  font-weight: 600;
  color: var(--text-primary);
}

.perf-bar-track {
  height: 6px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 4px;
  overflow: hidden;
}

.perf-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.35s ease;
}

.perf-bar-fill.cpu {
  background: linear-gradient(90deg, #667eea, #764ba2);
}

.perf-bar-fill.memory {
  background: linear-gradient(90deg, #4facfe, #00f2fe);
}

.perf-bar-fill.disk {
  background: linear-gradient(90deg, #56ab2f, #a8e063);
}

.perf-sub {
  font-size: 11px;
  color: var(--text-quaternary);
  margin: 6px 0 0;
}

.load-line {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 12px 0 0;
}

.metrics-error {
  font-size: 13px;
  color: var(--error);
  line-height: 1.5;
}

.service-row {
  padding: 12px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.service-row:last-child {
  border-bottom: none;
}

.service-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  display: block;
}

.service-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  margin-top: 8px;
}

.service-badge.ok {
  color: var(--success);
}

.service-badge.err {
  color: var(--error);
}

.service-badge .status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.service-msg {
  font-size: 11px;
  color: var(--text-quaternary);
  margin: 6px 0 0;
  word-break: break-all;
}

.empty-state.subtle {
  text-align: left;
  color: var(--text-quaternary);
  font-size: 13px;
}

@media (max-width: 960px) {
  .system-monitor-row {
    grid-template-columns: 1fr;
  }
}

.metric-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  padding: 18px;
  transition: all 0.2s;
}

.metric-card.clickable {
  cursor: pointer;
}


.metric-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.metric-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.metric-icon.sent { background: linear-gradient(135deg, rgba(102, 126, 234, 0.2), rgba(118, 75, 162, 0.15)); color: var(--primary); }
.metric-icon.success { background: linear-gradient(135deg, rgba(56, 239, 125, 0.2), rgba(17, 153, 142, 0.15)); color: var(--success); }
.metric-icon.failed { background: linear-gradient(135deg, rgba(255, 77, 79, 0.2), rgba(255, 120, 117, 0.15)); color: var(--error); }
.metric-icon.balance { background: linear-gradient(135deg, rgba(255, 210, 0, 0.2), rgba(247, 151, 30, 0.15)); color: var(--warning); }
.metric-icon.customers { background: linear-gradient(135deg, rgba(79, 172, 254, 0.2), rgba(0, 242, 254, 0.15)); color: var(--info); }
.metric-icon.revenue { background: linear-gradient(135deg, rgba(56, 239, 125, 0.2), rgba(17, 153, 142, 0.15)); color: var(--success); }
.metric-icon.profit { background: linear-gradient(135deg, rgba(240, 147, 251, 0.2), rgba(245, 87, 108, 0.15)); color: #F093FB; }

.metric-label {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.metric-body {
  display: flex;
  align-items: baseline;
  gap: 2px;
  margin-bottom: 6px;
}

.metric-currency {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-secondary);
}

.metric-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.metric-value.positive {
  color: var(--success);
}

.metric-unit {
  font-size: 13px;
  color: var(--text-quaternary);
  margin-left: 2px;
}

.metric-footer {
  display: flex;
  align-items: center;
  gap: 6px;
}

.metric-rate {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
}

.metric-rate.success { background: rgba(56, 239, 125, 0.1); color: var(--success); }
.metric-rate.failed { background: rgba(255, 77, 79, 0.1); color: var(--error); }

.metric-compare {
  font-size: 11px;
  color: var(--text-quaternary);
}

.metric-link {
  font-size: 12px;
  color: var(--primary);
  font-weight: 500;
}

/* 内容网格 */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.content-grid.admin-grid {
  grid-template-columns: 1.2fr 1fr;
}

.content-grid.customer-grid {
  grid-template-columns: 1.5fr 1fr;
}

.content-left, .content-right {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 卡片通用 */
.card {
  border-radius: var(--radius-xl);
  overflow: hidden;
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-title svg {
  color: var(--text-tertiary);
}

/* 快速操作 */
.actions-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  padding: 16px;
}

.actions-grid.admin-actions {
  grid-template-columns: repeat(4, 1fr);
}

.action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 18px 14px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  transform: translateY(-2px);
}

.action-btn.primary { background: linear-gradient(135deg, rgba(102, 126, 234, 0.15), rgba(118, 75, 162, 0.1)); }
.action-btn.primary .action-icon { color: var(--primary); }
.action-btn.success { background: linear-gradient(135deg, rgba(56, 239, 125, 0.15), rgba(17, 153, 142, 0.1)); }
.action-btn.success .action-icon { color: var(--success); }
.action-btn.warning { background: linear-gradient(135deg, rgba(255, 210, 0, 0.15), rgba(247, 151, 30, 0.1)); }
.action-btn.warning .action-icon { color: var(--warning); }
.action-btn.info { background: linear-gradient(135deg, rgba(79, 172, 254, 0.15), rgba(0, 242, 254, 0.1)); }
.action-btn.info .action-icon { color: var(--info); }
.action-btn.stats { background: linear-gradient(135deg, rgba(167, 139, 250, 0.18), rgba(139, 92, 246, 0.1)); }
.action-btn.stats .action-icon { color: #a78bfa; }

.action-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
}

/* 列表通用样式 */
.view-all-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: var(--text-tertiary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.view-all-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 30px 20px;
  color: var(--text-quaternary);
  font-size: 13px;
}

/* 通道状态 */
.channel-count {
  font-size: 12px;
  color: var(--success);
  font-weight: 500;
}

.channels-list {
  padding: 8px 16px 16px;
}

.channel-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.channel-item:last-child {
  border-bottom: none;
}

.channel-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.channel-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.channel-protocol {
  font-size: 10px;
  padding: 2px 6px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 4px;
  color: var(--text-quaternary);
}

.channel-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
}

.channel-status .status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  animation: status-pulse 2s infinite ease-in-out;
}

@keyframes status-pulse {
  0% { transform: scale(1); opacity: 1; box-shadow: 0 0 0px currentColor; }
  50% { transform: scale(1.2); opacity: 0.8; box-shadow: 0 0 12px currentColor; }
  100% { transform: scale(1); opacity: 1; box-shadow: 0 0 0px currentColor; }
}

.channel-status.active { color: var(--success); }
.channel-activity { display: flex; align-items: flex-end; gap: 2px; margin-right: 8px; height: 20px; }
.activity-bar { width: 2px; background: var(--success); border-radius: 1px; animation: activity-pulse 1.2s infinite ease-in-out; opacity: 0.6; }
@keyframes activity-pulse {
  0%, 100% { transform: scaleY(1); opacity: 0.4; }
  50% { transform: scaleY(1.5); opacity: 1; }
}
.channel-status.active .status-dot { background: var(--success); }
.channel-status.inactive { color: var(--text-quaternary); }
.channel-status.inactive .status-dot { background: var(--text-quaternary); }
.channel-status.maintenance { color: var(--warning); }
.channel-status.maintenance .status-dot { background: var(--warning); }

/* 客户列表 (销售专属) */
.customers-list {
  padding: 8px 16px 16px;
}

.customer-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.customer-item:last-child {
  border-bottom: none;
}

.customer-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.customer-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.customer-status {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
}

.customer-status.active {
  background: rgba(56, 239, 125, 0.1);
  color: var(--success);
}

.customer-balance {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

/* 系统概览 */
.overview-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  padding: 16px;
}

.overview-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 10px;
}

.overview-label {
  font-size: 11px;
  color: var(--text-quaternary);
}

.overview-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

/* 发送记录 */
.records-list {
  padding: 8px;
  max-height: 260px;
  overflow-y: auto;
}

.record-item {
  display: grid;
  grid-template-columns: 130px 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 10px;
  border-radius: 10px;
  transition: background 0.15s;
}

.record-item:hover {
  background: rgba(255, 255, 255, 0.03);
}

.record-phone {
  display: flex;
  align-items: center;
  gap: 6px;
}

.phone-flag {
  font-size: 14px;
}

.phone-number {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  font-family: 'SF Mono', Monaco, monospace;
}

.record-message {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.record-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.record-status {
  font-size: 10px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 4px;
}

.record-status.delivered { background: rgba(56, 239, 125, 0.1); color: var(--success); }
.record-status.sent { background: rgba(102, 126, 234, 0.1); color: var(--primary); }
.record-status.pending { background: rgba(255, 210, 0, 0.1); color: var(--warning); }
.record-status.failed { background: rgba(255, 77, 79, 0.1); color: var(--error); }

.record-time {
  font-size: 10px;
  color: var(--text-quaternary);
  white-space: nowrap;
}

/* 账户信息 */
.account-details {
  padding: 12px 16px 16px;
}

.account-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.account-row:last-child {
  border-bottom: none;
}

.account-label {
  font-size: 13px;
  color: var(--text-tertiary);
}

.account-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.role-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 6px;
}

.role-tag.super_admin, .role-tag.admin {
  background: rgba(255, 77, 79, 0.1);
  color: #ff4d4f;
}

.role-tag.sales {
  background: rgba(102, 126, 234, 0.1);
  color: var(--primary);
}

.role-tag.finance {
  background: rgba(255, 210, 0, 0.1);
  color: var(--warning);
}

.role-tag.tech {
  background: rgba(79, 172, 254, 0.1);
  color: var(--info);
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 6px;
}

.status-badge.active {
  background: rgba(56, 239, 125, 0.1);
  color: var(--success);
}

.status-badge.warning {
  background: rgba(255, 193, 7, 0.12);
  color: var(--warning);
}

.status-badge.inactive {
  background: rgba(148, 163, 184, 0.15);
  color: var(--text-tertiary);
}

.account-details-customer .account-row {
  align-items: flex-start;
}

.account-details-customer .account-value {
  text-align: right;
  word-break: break-all;
}

.status-badge .status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 8px currentColor;
  animation: status-pulse 2s infinite ease-in-out;
}

@keyframes status-pulse {
  0% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.3); opacity: 0.7; }
  100% { transform: scale(1); opacity: 1; }
}

.api-key-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.api-key {
  font-family: 'SF Mono', Monaco, monospace;
  font-size: 11px;
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.04);
  padding: 4px 10px;
  border-radius: 6px;
}

.copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: var(--text-quaternary);
  cursor: pointer;
  transition: all 0.15s;
}

.copy-btn:hover {
  background: rgba(102, 126, 234, 0.1);
  border-color: var(--primary);
  color: var(--primary);
}

/* ========== 日环比对比行 ========== */
.compare-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.compare-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
}
.compare-chip.up { background: rgba(16, 185, 129, 0.08); border-color: rgba(16, 185, 129, 0.2); }
.compare-chip.down { background: rgba(239, 68, 68, 0.08); border-color: rgba(239, 68, 68, 0.2); }
.compare-label { color: var(--text-tertiary); }
.compare-val { font-weight: 700; }
.compare-chip.up .compare-val { color: #10b981; }
.compare-chip.down .compare-val { color: #ef4444; }
.compare-chip.flat .compare-val { color: var(--text-secondary); }
.compare-hint { color: var(--text-quaternary); font-size: 11px; }

.metric-change {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
}
.metric-change.up { color: #10b981; background: rgba(16, 185, 129, 0.1); }
.metric-change.down { color: #ef4444; background: rgba(239, 68, 68, 0.1); }
.metric-change.flat { color: var(--text-tertiary); }

/* ========== 可视化行 ========== */
.viz-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 20px;
}

/* 7日趋势 */
.trend-chart {
  padding: 16px;
}
.trend-bars {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  height: 140px;
  padding-bottom: 4px;
}
.trend-bar-group {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  height: 100%;
}
.trend-bar-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  align-items: center;
  width: 100%;
  position: relative;
}
.trend-bar {
  width: 60%;
  min-height: 4px;
  border-radius: 4px 4px 0 0;
  position: relative;
  transition: height 0.5s ease;
}
.sent-bar { background: linear-gradient(180deg, rgba(102, 126, 234, 0.8), rgba(102, 126, 234, 0.4)); }
.delivered-bar {
  background: linear-gradient(180deg, rgba(16, 185, 129, 0.8), rgba(16, 185, 129, 0.4));
  width: 40%;
  position: absolute;
  bottom: 0;
  border-radius: 4px 4px 0 0;
}
.trend-bar-tooltip {
  display: none;
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.8);
  color: #fff;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  white-space: nowrap;
}
.trend-bar-group:hover .trend-bar-tooltip { display: block; }
.trend-date { font-size: 11px; color: var(--text-quaternary); }
.trend-legend {
  display: flex;
  gap: 16px;
  justify-content: center;
  margin-top: 10px;
  font-size: 12px;
  color: var(--text-tertiary);
}
.legend-item { display: flex; align-items: center; gap: 4px; }
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.legend-dot.sent { background: rgba(102, 126, 234, 0.8); }
.legend-dot.delivered { background: rgba(16, 185, 129, 0.8); }

/* 客户TOP */
.top-list { padding: 8px 16px; }
.top-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  font-size: 13px;
}
.top-item:last-child { border-bottom: none; }
.top-rank {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-weight: 700;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-tertiary);
}
.top-rank.gold { background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; }
.top-rank.silver { background: linear-gradient(135deg, #94a3b8, #64748b); color: #fff; }
.top-rank.bronze { background: linear-gradient(135deg, #c2884e, #a0693c); color: #fff; }
.top-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); }
.top-sent { font-weight: 700; color: var(--primary); min-width: 60px; text-align: right; }
.top-rate { color: #10b981; font-weight: 600; min-width: 52px; text-align: right; }
.top-revenue { color: var(--text-secondary); min-width: 60px; text-align: right; }

/* 批次概览 */
.batch-stats {
  display: flex;
  gap: 16px;
  padding: 20px 16px;
  justify-content: center;
}
.batch-stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 20px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
}
.batch-stat-item.total { border-left: 3px solid var(--primary); }
.batch-stat-item.processing { border-left: 3px solid #3b82f6; }
.batch-stat-item.completed { border-left: 3px solid #10b981; }
.batch-stat-item.failed { border-left: 3px solid #ef4444; }
.batch-num { font-size: 24px; font-weight: 800; color: var(--text-primary); }
.batch-label { font-size: 12px; color: var(--text-tertiary); }

/* 通道统计 */
.ch-stats-list { padding: 8px 16px; }
.ch-stat-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  font-size: 13px;
}
.ch-stat-row:last-child { border-bottom: none; }
.ch-stat-name { width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); }
.ch-stat-bar-wrap {
  flex: 1;
  height: 6px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 3px;
  overflow: hidden;
}
.ch-stat-bar { height: 100%; border-radius: 3px; transition: width 0.6s ease; }
.ch-stat-bar.good { background: linear-gradient(90deg, #10b981, #34d399); }
.ch-stat-bar.warn { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
.ch-stat-bar.bad { background: linear-gradient(90deg, #ef4444, #f87171); }
.ch-stat-pct { font-weight: 700; min-width: 44px; text-align: right; }
.ch-stat-row .ch-stat-pct { color: var(--text-secondary); }
.ch-stat-cnt { color: var(--text-quaternary); min-width: 70px; text-align: right; }

/* 响应式 */
@media (max-width: 1400px) {
  .metrics-grid.metrics-6 {
    grid-template-columns: repeat(3, 1fr);
  }
  
  .actions-grid.admin-actions {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 1024px) {
  .metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .content-grid {
    grid-template-columns: 1fr;
  }
  
  .viz-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .dashboard-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  
  .header-left {
    flex-wrap: wrap;
  }
  
  .metrics-grid {
    grid-template-columns: 1fr;
  }
  
  .record-item {
    grid-template-columns: 1fr;
    gap: 6px;
  }
}

/* 亮色主题 */
[data-theme="light"] .metric-card,
[data-theme="light"] .card {
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(20px);
  border: 0.5px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

[data-theme="light"] .card-header {
  border-bottom-color: rgba(0, 0, 0, 0.05);
}

[data-theme="light"] .channel-item,
[data-theme="light"] .customer-item,
[data-theme="light"] .account-row {
  border-bottom-color: rgba(0, 0, 0, 0.05);
}

[data-theme="light"] .channel-protocol {
  background: rgba(0, 0, 0, 0.04);
}

[data-theme="light"] .overview-item {
  background: rgba(0, 0, 0, 0.02);
}

[data-theme="light"] .api-key {
  background: rgba(0, 0, 0, 0.04);
}

[data-theme="light"] .record-item:hover {
  background: rgba(0, 0, 0, 0.02);
}

[data-theme="light"] .compare-chip {
  background: rgba(0, 0, 0, 0.03);
  border-color: rgba(0, 0, 0, 0.06);
}

[data-theme="light"] .top-item,
[data-theme="light"] .ch-stat-row {
  border-bottom-color: rgba(0, 0, 0, 0.05);
}

[data-theme="light"] .batch-stat-item {
  background: rgba(0, 0, 0, 0.02);
}

[data-theme="light"] .ch-stat-bar-wrap {
  background: rgba(0, 0, 0, 0.06);
}

[data-theme="light"] .top-rank {
  background: rgba(0, 0, 0, 0.05);
}

</style>