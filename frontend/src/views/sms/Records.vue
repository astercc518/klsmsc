<template>
  <div class="records-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">{{ $t('smsRecords.title') }}</h1>
        <p class="page-desc">{{ $t('smsRecords.pageDesc') }}</p>
        <p class="status-explain">{{ $t('smsRecords.statusExplain') }}</p>
      </div>
      <div class="header-actions">
        <button class="action-btn refresh" @click="loadRecords">
          <el-icon><Refresh /></el-icon>
          {{ $t('common.refresh') }}
        </button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-chip">
        <span class="stat-chip-label">{{ $t('smsRecords.totalRecords') }}</span>
        <span class="stat-chip-value">{{ pagination.total }}</span>
      </div>
      <div class="stat-chip sent">
        <span class="stat-chip-dot"></span>
        <span class="stat-chip-label">{{ $t('smsRecords.sent') }}</span>
        <span class="stat-chip-value">{{ statusCounts.sent }}</span>
      </div>
      <div class="stat-chip delivered">
        <span class="stat-chip-dot"></span>
        <span class="stat-chip-label">{{ $t('smsRecords.delivered') }}</span>
        <span class="stat-chip-value">{{ statusCounts.delivered }}</span>
      </div>
      <div class="stat-chip failed">
        <span class="stat-chip-dot"></span>
        <span class="stat-chip-label">{{ $t('smsRecords.failed') }}</span>
        <span class="stat-chip-value">{{ statusCounts.failed }}</span>
      </div>
      <div class="stat-chip expired">
        <span class="stat-chip-dot"></span>
        <span class="stat-chip-label">{{ $t('smsRecords.expired') }}</span>
        <span class="stat-chip-value">{{ statusCounts.expired }}</span>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-card">
      <div class="filter-content">
        <div class="filter-item" v-if="isAdmin">
          <label class="filter-label">{{ $t('smsRecords.customerAccount') }}</label>
          <el-select v-model="searchForm.account_id" :placeholder="$t('smsRecords.allAccounts')" clearable size="large" class="filter-select">
            <el-option v-for="acc in accounts" :key="acc.id" :label="`${acc.account_name} (${acc.id})`" :value="acc.id" />
          </el-select>
        </div>

        <div class="filter-item">
          <label class="filter-label">手机号码</label>
          <el-input v-model="searchForm.phone_number" placeholder="搜索号码" clearable size="large" class="filter-input" @keyup.enter="handleSearch" />
        </div>

        <div class="filter-item">
          <label class="filter-label">{{ $t('smsRecords.messageId') }}</label>
          <el-input
            v-model="searchForm.message_id"
            :placeholder="$t('smsRecords.messageIdPlaceholder')"
            clearable
            size="large"
            class="filter-input"
            @keyup.enter="handleSearch"
          />
        </div>

        <div class="filter-item">
          <label class="filter-label">{{ $t('smsRecords.statusFilter') }}</label>
          <el-select v-model="searchForm.status" :placeholder="$t('smsRecords.allStatus')" clearable size="large" class="filter-select">
            <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value">
              <div class="status-option"><span class="status-dot" :class="s.value"></span>{{ s.label }}</div>
            </el-option>
          </el-select>
        </div>

        <div class="filter-item" v-if="isAdmin">
          <label class="filter-label">通道</label>
          <el-select v-model="searchForm.channel_id" placeholder="全部通道" clearable size="large" class="filter-select">
            <el-option v-for="ch in channels" :key="ch.id" :label="ch.channel_code" :value="ch.id" />
          </el-select>
        </div>

        <div class="filter-item">
          <label class="filter-label">国家</label>
          <el-select v-model="searchForm.country_code" :placeholder="$t('smsRecords.allCountries')" clearable size="large" class="filter-select">
            <el-option v-for="c in countryOptions" :key="c.dial" :label="c.name" :value="c.dial" />
          </el-select>
        </div>

        <div class="filter-item" v-if="searchForm.batch_id">
          <label class="filter-label">任务ID</label>
          <el-input-number
            v-model="searchForm.batch_id"
            :min="1"
            placeholder="任务ID"
            size="large"
            class="filter-input"
            controls-position="right"
            style="width: 130px"
          />
        </div>

        <div class="filter-item">
          <label class="filter-label">日期范围</label>
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="~"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            size="large"
            class="filter-date"
            :shortcuts="dateShortcuts"
          />
        </div>

        <div class="filter-actions">
          <button class="filter-btn search" @click="handleSearch">
            <el-icon><Search /></el-icon>
            {{ $t('smsRecords.query') }}
          </button>
          <button class="filter-btn reset" @click="handleReset">{{ $t('common.reset') }}</button>
        </div>
      </div>
    </div>

    <!-- 数据表格 -->
    <div class="table-card">
      <div class="table-wrapper" v-loading="loading">
        <el-table :data="records" class="records-table" :row-class-name="tableRowClassName" @row-click="handleViewDetail" empty-text="暂无记录" stripe>
          <el-table-column v-if="isAdmin" prop="account_name" label="客户" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="account-cell">
                <span class="account-name-text">{{ row.account_name || '-' }}</span>
                <span v-if="row.sales_name" class="sales-tag">{{ row.sales_name }}</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column prop="message_id" :label="$t('smsRecords.messageId')" width="140">
            <template #default="{ row }">
              <el-tooltip :content="row.message_id" placement="top">
                <span class="mono-text clickable">{{ row.message_id?.substring(0, 12) }}...</span>
              </el-tooltip>
            </template>
          </el-table-column>

          <el-table-column prop="phone_number" label="手机号码" width="150">
            <template #default="{ row }">
              <span class="phone-text">{{ row.phone_number }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="country_code" :label="$t('smsRecords.country')" width="90" align="center">
            <template #default="{ row }">
              <span>{{ countryDisplay(row.country_code) }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="isAdmin" prop="channel_code" label="通道" width="140">
            <template #default="{ row }">
              <el-tag v-if="row.channel_code" size="small" :type="row.channel_code?.includes('SMPP') ? 'primary' : 'success'" effect="plain">
                {{ row.channel_code }}
              </el-tag>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>

          <el-table-column prop="message" label="内容" min-width="200">
            <template #default="{ row }">
              <el-tooltip :content="row.message" placement="top" :show-after="500">
                <span class="message-preview">{{ truncate(row.message, 40) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>

          <el-table-column prop="status" label="状态" width="100" align="center">
            <template #default="{ row }">
              <span class="status-badge" :class="row.status">{{ getStatusText(row.status) }}</span>
            </template>
          </el-table-column>

          <el-table-column
            prop="error_message"
            :label="$t('smsRecords.errorMsg')"
            min-width="160"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <template v-if="shouldShowErrorMessage(row)">
                <span v-if="friendlyError(row.error_message)" class="error-preview-friendly">
                  {{ friendlyError(row.error_message)!.title }}
                </span>
                <span v-else class="error-preview">{{ row.error_message }}</span>
              </template>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>

          <el-table-column v-if="isAdmin" label="费用" width="160">
            <template #default="{ row }">
              <div class="cost-cell">
                <span class="cost-selling">{{ row.selling_price?.toFixed(4) }}</span>
                <span class="cost-detail" v-if="row.cost_price">成本 {{ row.cost_price?.toFixed(4) }}</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column v-if="!isAdmin" prop="selling_price" label="费用" width="100" align="right">
            <template #default="{ row }">
              <span class="cost-selling">{{ row.selling_price?.toFixed(4) }} {{ row.currency }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="submit_time" label="提交时间" width="170">
            <template #default="{ row }">
              <span class="time-text">{{ formatTime(row.submit_time) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="delivery_time" :label="$t('smsRecords.deliveryTime')" width="170">
            <template #default="{ row }">
              <span class="time-text">{{ formatTime(row.delivery_time) || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="" width="50" align="center" fixed="right">
            <template #default="{ row }">
              <el-icon class="detail-icon" @click.stop="handleViewDetail(row)"><View /></el-icon>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 分页 -->
      <div class="pagination-wrapper" v-if="pagination.total > 0">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[20, 50, 100, 200]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="loadRecords"
          @current-change="loadRecords"
        />
      </div>
    </div>

    <!-- 详情对话框 -->
    <el-dialog v-model="detailVisible" title="短信详情" width="640px" class="detail-dialog" destroy-on-close>
      <div class="detail-content" v-if="currentRecord">
        <!-- 状态横幅 -->
        <div class="status-banner" :class="currentRecord.status">
          <span class="status-badge lg" :class="currentRecord.status">{{ getStatusText(currentRecord.status) }}</span>
          <span class="status-time" v-if="currentRecord.sent_time">{{ formatTime(currentRecord.sent_time) }}</span>
        </div>

        <!-- 客户信息（仅管理员可见） -->
        <div class="detail-grid-3" v-if="isAdmin && (currentRecord.account_name || currentRecord.account_id)">
          <div class="detail-card">
            <span class="dc-label">客户账号</span>
            <span class="dc-value">{{ currentRecord.account_name || '-' }}</span>
          </div>
          <div class="detail-card">
            <span class="dc-label">客户ID</span>
            <span class="dc-value mono">{{ currentRecord.account_id }}</span>
          </div>
          <div class="detail-card" v-if="currentRecord.sales_name">
            <span class="dc-label">归属员工</span>
            <span class="dc-value">{{ currentRecord.sales_name }}</span>
          </div>
        </div>

        <div class="detail-grid-3">
          <div class="detail-card">
            <span class="dc-label">{{ $t('smsRecords.messageId') }}</span>
            <span class="dc-value mono">{{ currentRecord.message_id }}</span>
          </div>
          <div class="detail-card" v-if="currentRecord.upstream_message_id">
            <span class="dc-label">上游消息ID</span>
            <span class="dc-value mono">{{ currentRecord.upstream_message_id }}</span>
          </div>
          <div class="detail-card">
            <span class="dc-label">手机号码</span>
            <span class="dc-value">{{ currentRecord.phone_number }}</span>
          </div>
          <div class="detail-card">
            <span class="dc-label">{{ $t('smsRecords.country') }}</span>
            <span class="dc-value">{{ countryDisplay(currentRecord.country_code) }}</span>
          </div>
          <div class="detail-card" v-if="isAdmin && currentRecord.channel_code">
            <span class="dc-label">发送通道</span>
            <el-tag size="small" effect="plain">{{ currentRecord.channel_code }}</el-tag>
          </div>
          <div class="detail-card">
            <span class="dc-label">{{ $t('smsRecords.upstreamHandoffLabel') }}</span>
            <el-tooltip v-if="currentRecord.status === 'delivered'" placement="top" :content="$t('smsRecords.upstreamHandoffTipDelivered')">
              <el-tag size="small" type="success" effect="plain">{{ $t('smsStatus.delivered') }}</el-tag>
            </el-tooltip>
            <el-tooltip v-else-if="currentRecord.status === 'failed'" placement="top" :content="$t('smsRecords.upstreamHandoffTipFailed')">
              <el-tag size="small" type="danger" effect="plain">{{ $t('smsStatus.failed') }}</el-tag>
            </el-tooltip>
            <el-tooltip
              v-else-if="currentRecord.upstream_message_id"
              placement="top"
              :content="$t('smsRecords.upstreamHandoffTipAccepted')"
            >
              <el-tag size="small" type="info" effect="plain">{{ $t('smsRecords.upstreamAcceptedShort') }}</el-tag>
            </el-tooltip>
            <span v-else class="text-muted">-</span>
          </div>
          <div class="detail-card">
            <span class="dc-label">短信条数</span>
            <span class="dc-value">{{ currentRecord.message_count || 1 }}</span>
          </div>
        </div>

        <div class="detail-section">
          <h4 class="section-title">短信内容</h4>
          <div class="message-box">{{ currentRecord.message }}</div>
        </div>

        <div class="detail-section" v-if="isAdmin">
          <h4 class="section-title">费用信息</h4>
          <div class="detail-grid-3">
            <div class="detail-card">
              <span class="dc-label">售价</span>
              <span class="dc-value highlight">{{ currentRecord.selling_price?.toFixed(4) }} {{ currentRecord.currency }}</span>
            </div>
            <div class="detail-card">
              <span class="dc-label">成本</span>
              <span class="dc-value">{{ currentRecord.cost_price?.toFixed(4) }} {{ currentRecord.currency }}</span>
            </div>
            <div class="detail-card">
              <span class="dc-label">利润</span>
              <span class="dc-value" :class="currentRecord.profit >= 0 ? 'profit-positive' : 'profit-negative'">
                {{ currentRecord.profit?.toFixed(4) }} {{ currentRecord.currency }}
              </span>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <h4 class="section-title">时间线</h4>
          <div class="timeline">
            <div class="timeline-item active">
              <div class="tl-dot"></div>
              <div class="tl-content">
                <span class="tl-label">提交</span>
                <span class="tl-time">{{ formatTime(currentRecord.submit_time) }}</span>
              </div>
            </div>
            <div class="timeline-item" :class="{ active: currentRecord.sent_time }">
              <div class="tl-dot"></div>
              <div class="tl-content">
                <span class="tl-label">发送</span>
                <span class="tl-time">{{ formatTime(currentRecord.sent_time) || $t('common.waiting') }}</span>
              </div>
            </div>
            <div class="timeline-item" :class="{ active: currentRecord.delivery_time }">
              <div class="tl-dot"></div>
              <div class="tl-content">
                <span class="tl-label">送达</span>
                <span class="tl-time">{{ formatTime(currentRecord.delivery_time) || $t('common.waiting') }}</span>
              </div>
            </div>
          </div>
          <p v-if="showDlrExplainHint" class="dlr-explain-hint">{{ $t('smsRecords.dlrTerminalHint') }}</p>
        </div>

        <div class="detail-section" v-if="currentRecord.error_message && shouldShowErrorMessage(currentRecord)">
          <h4 class="section-title error-title">{{ $t('smsRecords.errorMsg') }}</h4>
          <div v-if="friendlyError(currentRecord.error_message)" class="error-explain">
            <el-alert :type="friendlyError(currentRecord.error_message).type" :closable="false" show-icon>
              <template #title>{{ friendlyError(currentRecord.error_message).title }}</template>
              <template #default>{{ friendlyError(currentRecord.error_message).desc }}</template>
            </el-alert>
          </div>
          <div class="error-box">{{ currentRecord.error_message }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, Search, View } from '@element-plus/icons-vue'
import { getSMSRecords } from '@/api/sms'
import { getAccountsAdmin, getChannelsAdmin } from '@/api/admin'
import { COUNTRY_LIST, findCountryByDial, findCountryByIso } from '@/constants/countries'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

/** 国家列/详情：支持电话国码(如 880)或 ISO(如 BD)，与后台 country_code 存储一致 */
function countryDisplay(code: string | null | undefined): string {
  if (!code) return '-'
  const raw = String(code).trim()
  const byDial = findCountryByDial(raw)
  if (byDial) return byDial.name
  const iso = raw.length <= 3 ? raw.toUpperCase() : raw
  const byIso = findCountryByIso(iso)
  if (byIso) return byIso.name
  return raw
}

// 国家筛选选项（按中文名排序）
const countryOptions = [...COUNTRY_LIST].sort((a, b) => a.name.localeCompare(b.name))
const loading = ref(false)
const detailVisible = ref(false)
const currentRecord = ref<any>(null)

const isAdmin = computed(() => {
  if (sessionStorage.getItem('impersonate_mode') === '1') return false
  return !!localStorage.getItem('admin_token')
})

const accounts = ref<any[]>([])
const channels = ref<any[]>([])
const dateRange = ref<string[] | null>(null)

const searchForm = ref({
  phone_number: '',
  message_id: '',
  status: '',
  account_id: null as number | null,
  channel_id: null as number | null,
  country_code: '' as string,
  batch_id: null as number | null,
})

const pagination = ref({ page: 1, pageSize: 20, total: 0 })
const records = ref<any[]>([])

const statusCounts = computed(() => {
  const map: Record<string, number> = { sent: 0, delivered: 0, failed: 0, pending: 0, queued: 0, expired: 0 }
  records.value.forEach(r => { if (map[r.status] !== undefined) map[r.status]++ })
  return map
})

const statusOptions = computed(() => [
  { value: 'pending', label: t('smsStatus.pending') },
  { value: 'queued', label: t('smsStatus.queued') },
  { value: 'sent', label: t('smsStatus.sent') },
  { value: 'delivered', label: t('smsStatus.delivered') },
  { value: 'failed', label: t('smsStatus.failed') },
  { value: 'expired', label: t('smsStatus.expired') },
])

const dateShortcuts = [
  { text: '今天', value: () => { const d = new Date(); return [d, d] } },
  { text: '近7天', value: () => { const e = new Date(); const s = new Date(); s.setDate(s.getDate() - 6); return [s, e] } },
  { text: '近30天', value: () => { const e = new Date(); const s = new Date(); s.setDate(s.getDate() - 29); return [s, e] } },
]

const truncate = (s: string | null, n: number) => {
  if (!s) return '-'
  return s.length > n ? s.substring(0, n) + '...' : s
}

/** 已提交上游但尚无终端送达时间时，提示 DLR 与界面含义 */
const showDlrExplainHint = computed(() => {
  const r = currentRecord.value
  if (!r) return false
  return (
    (r.status === 'sent' || r.status === 'pending' || r.status === 'queued') &&
    !!r.sent_time &&
    !r.delivery_time
  )
})

const formatTime = (iso: string | null) => {
  if (!iso) return ''
  return iso.replace('T', ' ').substring(0, 19)
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    pending: t('smsStatus.pending'),
    queued: t('smsStatus.queued'),
    sent: t('smsStatus.sent'),
    delivered: t('smsStatus.delivered'),
    failed: t('smsStatus.failed'),
    expired: t('smsStatus.expired'),
  }
  return map[status] || status
}

const tableRowClassName = ({ row }: { row: any }) => {
  if (row.status === 'failed') return 'row-failed'
  if (row.status === 'expired') return 'row-expired'
  return ''
}

const buildParams = () => {
  const params: any = { page: pagination.value.page, page_size: pagination.value.pageSize }
  if (searchForm.value.status) params.status = searchForm.value.status
  if (searchForm.value.phone_number) params.phone_number = searchForm.value.phone_number
  if (searchForm.value.message_id) params.message_id = searchForm.value.message_id
  if (isAdmin.value && searchForm.value.account_id) params.account_id = searchForm.value.account_id
  if (isAdmin.value && searchForm.value.channel_id) params.channel_id = searchForm.value.channel_id
  if (searchForm.value.country_code) params.country_code = searchForm.value.country_code
  if (searchForm.value.batch_id) params.batch_id = searchForm.value.batch_id
  if (dateRange.value && dateRange.value.length === 2) {
    params.start_date = dateRange.value[0]
    params.end_date = dateRange.value[1]
  }
  return params
}

const loadRecords = async () => {
  loading.value = true
  try {
    const res: any = await getSMSRecords(buildParams())
    if (res?.success) {
      records.value = res.records || []
      pagination.value.total = res.total || 0
    }
  } catch (error: any) {
    ElMessage.error('加载记录失败')
    records.value = []
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.value.page = 1
  loadRecords()
}

const handleReset = () => {
  searchForm.value = { phone_number: '', message_id: '', status: '', account_id: null, channel_id: null, country_code: '', batch_id: null }
  dateRange.value = null
  if (route.query.batch_id) {
    router.replace({ query: { ...route.query, batch_id: undefined } })
  }
  handleSearch()
}

const handleViewDetail = (row: any) => {
  currentRecord.value = row
  detailVisible.value = true
}

/** 已送达却仍带历史「批次兜底/Worker」脏文案时不在界面展示，避免与成功状态矛盾（库中可能未清空 error_message） */
const STALE_SUCCESS_ERROR_PATTERNS = [
  /worker restart/i,
  /simulated task lost/i,
  /待发任务未完成调度/,
  /后台\s*worker\s*重启/,
]

const shouldShowErrorMessage = (row: { status?: string; error_message?: string | null }) => {
  const msg = (row.error_message || '').trim()
  if (!msg) return false
  if (row.status === 'delivered' && STALE_SUCCESS_ERROR_PATTERNS.some((re) => re.test(msg))) {
    return false
  }
  return true
}

const friendlyError = (msg: string | null | undefined): { title: string; desc: string; type: 'warning' | 'error' | 'info' } | null => {
  if (!msg) return null
  if (msg.includes('UNDELIV')) {
    return {
      type: 'warning',
      title: '运营商拒绝投递（UNDELIVERABLE）',
      desc: '短信已提交至运营商，但被目标运营商拒绝投递。常见原因：号码关机/停机、运营商内容过滤拦截、号码加入了免打扰名单(DND)、号码不存在或已注销。',
    }
  }
  if (msg.includes('REJECTD') || msg.includes('REJECTED')) {
    return {
      type: 'error',
      title: '运营商拒绝（REJECTED）',
      desc: '短信被运营商直接拒绝，未尝试投递。可能原因：发送内容违规、发送号码被列入黑名单、目标运营商策略限制。',
    }
  }
  if (msg.includes('EXPIRED')) {
    return {
      type: 'warning',
      title: '短信过期（EXPIRED）',
      desc: '短信在运营商网络中等待投递超时。通常因为接收方设备长时间不在线（关机/无信号）。',
    }
  }
  if (msg.includes('different loop')) {
    return {
      type: 'error',
      title: '系统内部错误',
      desc: '发送过程中出现系统内部异常，该条短信未被发出。可联系管理员安排重发。',
    }
  }
  if (msg.includes('No available channel')) {
    return {
      type: 'error',
      title: '无可用通道',
      desc: '当前没有匹配该目标国家的可用发送通道，请联系管理员检查通道配置。',
    }
  }
  if (/SMPP.*提交被拒.*129/.test(msg)) {
    return {
      type: 'error',
      title: '无效目标号码',
      desc: '目标手机号码格式错误或不存在，请检查号码是否正确（含国家码）。',
    }
  }
  if (msg.includes('connection failed') || msg.includes('Connection') || msg.includes('timeout')) {
    return {
      type: 'error',
      title: '通道连接异常',
      desc: '与上游通道的网络连接失败或超时，系统会自动重试。若持续出现请联系管理员。',
    }
  }
  return null
}

const loadAccounts = async () => {
  if (!isAdmin.value) return
  try {
    const res: any = await getAccountsAdmin({ page: 1, page_size: 200 })
    accounts.value = res?.accounts || []
  } catch { /* ignore */ }
}

const loadChannels = async () => {
  if (!isAdmin.value) return
  try {
    const res: any = await getChannelsAdmin()
    channels.value = (res?.channels || []).filter((c: any) => c.status === 'active')
  } catch { /* ignore */ }
}

onMounted(() => {
  const qBatchId = route.query.batch_id
  if (qBatchId) {
    const bid = Number(qBatchId)
    if (Number.isFinite(bid) && bid > 0) searchForm.value.batch_id = bid
  }
  loadAccounts()
  loadChannels()
  loadRecords()
})
</script>

<style scoped>
.records-page {
  width: 100%;
  animation: fadeIn 0.4s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 头部 */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
}
.header-content {
  flex: 1;
  min-width: 0;
}
.page-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 6px;
}
.page-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}
.status-explain {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.55;
  margin: 10px 0 0;
  max-width: 920px;
  opacity: 0.92;
}
.header-actions {
  display: flex;
  gap: 10px;
}
.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid var(--border-default);
  background: var(--bg-input);
  color: var(--text-secondary);
}
.action-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 统计行 */
.stats-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.stat-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  font-size: 13px;
}
.stat-chip-label { color: var(--text-tertiary); }
.stat-chip-value { font-weight: 600; color: var(--text-primary); }
.stat-chip-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.stat-chip.sent .stat-chip-dot { background: var(--primary); }
.stat-chip.delivered .stat-chip-dot { background: var(--success); }
.stat-chip.failed .stat-chip-dot { background: var(--danger); }
.stat-chip.expired .stat-chip-dot { background: #909399; }

/* 筛选 */
.filter-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  padding: 18px 20px;
  margin-bottom: 16px;
}
.filter-content {
  display: flex;
  gap: 16px;
  align-items: flex-end;
  flex-wrap: wrap;
}
.filter-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 160px;
}
.filter-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-quaternary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
:deep(.filter-select .el-input__wrapper),
:deep(.filter-input .el-input__wrapper) {
  border-radius: 10px !important;
}
:deep(.filter-date) {
  --el-date-editor-width: 260px;
}
.status-option {
  display: flex;
  align-items: center;
  gap: 8px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.status-dot.pending { background: var(--info); }
.status-dot.queued { background: var(--warning); }
.status-dot.sent { background: var(--primary); }
.status-dot.delivered { background: var(--success); }
.status-dot.failed { background: var(--danger); }
.status-dot.expired { background: #909399; }
.filter-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}
.filter-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}
.filter-btn.search {
  background: linear-gradient(135deg, #2997FF 0%, #0071E3 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(41, 151, 255, 0.3);
}
.filter-btn.search:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(41, 151, 255, 0.4);
}
.filter-btn.reset {
  background: var(--bg-input);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

/* 表格 */
.table-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  overflow: hidden;
}
.table-wrapper {
  min-height: 300px;
}
:deep(.records-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: var(--bg-input);
  --el-table-border-color: var(--border-subtle);
}
:deep(.records-table .el-table__header th) {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-quaternary);
}
:deep(.records-table .el-table__row) {
  cursor: pointer;
  transition: background 0.15s;
}
:deep(.records-table .el-table__row:hover > td) {
  background: rgba(41, 151, 255, 0.04) !important;
}
:deep(.records-table .row-failed > td) {
  background: rgba(255, 69, 58, 0.03) !important;
}
.mono-text {
  font-family: 'SF Mono', Monaco, monospace;
  font-size: 12px;
  color: var(--text-tertiary);
}
.clickable { cursor: pointer; }
.phone-text { font-weight: 500; color: var(--text-primary); }
.account-cell { display: flex; flex-direction: column; gap: 2px; line-height: 1.3; }
.account-name-text { font-size: 13px; font-weight: 500; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sales-tag { font-size: 11px; color: var(--text-quaternary); }
.text-muted { color: var(--text-quaternary); font-size: 12px; }
.error-preview {
  color: var(--el-color-danger);
  font-size: 12px;
}
.error-preview-friendly {
  color: var(--el-color-warning-dark-2);
  font-size: 12px;
  font-weight: 500;
}
.message-preview {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-tertiary);
  font-size: 13px;
  max-width: 300px;
}
.status-badge {
  display: inline-flex;
  padding: 3px 10px;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 500;
}
.status-badge.pending { background: rgba(100, 210, 255, 0.15); color: var(--info); }
.status-badge.queued { background: rgba(255, 159, 10, 0.15); color: var(--warning); }
.status-badge.sent { background: rgba(41, 151, 255, 0.15); color: var(--primary); }
.status-badge.delivered { background: rgba(50, 215, 75, 0.15); color: var(--success); }
.status-badge.failed { background: rgba(255, 69, 58, 0.15); color: var(--danger); }
.status-badge.expired { background: rgba(144, 147, 153, 0.15); color: #909399; }
.status-badge.lg { font-size: 14px; padding: 6px 16px; }
.cost-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cost-selling { font-weight: 500; color: var(--text-primary); font-size: 13px; }
.cost-detail { font-size: 11px; color: var(--text-quaternary); }
.time-text { font-size: 13px; color: var(--text-tertiary); }
.detail-icon {
  cursor: pointer;
  color: var(--text-quaternary);
  font-size: 18px;
  transition: color 0.2s;
}
.detail-icon:hover { color: var(--primary); }

/* 分页 */
.pagination-wrapper {
  padding: 16px 20px;
  border-top: 1px solid var(--border-subtle);
  display: flex;
  justify-content: flex-end;
}

/* 详情弹窗 */
.detail-content { padding: 0 4px; }
.status-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-radius: 12px;
  margin-bottom: 20px;
}
.status-banner.sent { background: rgba(41, 151, 255, 0.08); }
.status-banner.delivered { background: rgba(50, 215, 75, 0.08); }
.status-banner.failed { background: rgba(255, 69, 58, 0.08); }
.status-banner.pending { background: rgba(100, 210, 255, 0.08); }
.status-banner.queued { background: rgba(255, 159, 10, 0.08); }
.status-banner.expired { background: rgba(144, 147, 153, 0.08); }
.status-time { font-size: 13px; color: var(--text-tertiary); }

.detail-grid-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}
.detail-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: var(--bg-input);
  border-radius: 10px;
}
.dc-label { font-size: 11px; color: var(--text-quaternary); text-transform: uppercase; letter-spacing: 0.04em; }
.dc-value { font-size: 14px; font-weight: 500; color: var(--text-primary); word-break: break-all; }
.dc-value.mono { font-family: 'SF Mono', Monaco, monospace; font-size: 11px; }
.dc-value.highlight { color: var(--primary); font-weight: 600; }
.profit-positive { color: var(--success) !important; }
.profit-negative { color: var(--danger) !important; }

.detail-section { margin-bottom: 20px; }
.section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 12px;
}
.error-title { color: var(--danger); }
.message-box {
  background: var(--bg-input);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 14px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
}
.error-explain {
  margin-bottom: 10px;
}
.error-explain :deep(.el-alert__description) {
  font-size: 12px;
  line-height: 1.6;
  margin-top: 4px;
}
.error-box {
  background: rgba(255, 69, 58, 0.08);
  border: 1px solid rgba(255, 69, 58, 0.2);
  border-radius: 10px;
  padding: 14px;
  font-size: 12px;
  color: var(--danger);
  font-family: 'SF Mono', 'Fira Code', monospace;
  word-break: break-all;
}

/* 时间线 */
.timeline { display: flex; flex-direction: column; gap: 0; }
.timeline-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 0;
  position: relative;
}
.timeline-item::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 26px;
  bottom: -10px;
  width: 2px;
  background: var(--border-default);
}
.timeline-item:last-child::before { display: none; }
.tl-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--border-default);
  flex-shrink: 0;
  margin-top: 2px;
}
.timeline-item.active .tl-dot { background: var(--primary); box-shadow: 0 0 0 4px rgba(41, 151, 255, 0.15); }
.timeline-item.active::before { background: var(--primary); opacity: 0.3; }
.tl-content { display: flex; justify-content: space-between; flex: 1; }
.tl-label { font-size: 14px; font-weight: 500; color: var(--text-secondary); }
.tl-time { font-size: 13px; color: var(--text-tertiary); }
.timeline-item:not(.active) .tl-label { color: var(--text-quaternary); }
.timeline-item:not(.active) .tl-time { color: var(--text-quaternary); font-style: italic; }

.dlr-explain-hint {
  margin: 12px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-tertiary);
}

@media (max-width: 1024px) {
  .filter-content { flex-direction: column; align-items: stretch; }
  .filter-item { min-width: auto; }
  .filter-actions { margin-left: 0; }
  .detail-grid-3 { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 640px) {
  .page-header { flex-direction: column; gap: 12px; align-items: flex-start; }
  .stats-row { flex-direction: column; }
  .detail-grid-3 { grid-template-columns: 1fr; }
}
</style>
