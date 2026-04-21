<template>
  <div class="send-stats-page">
    <!-- ===== 客户模式：精细化回执统计 ===== -->
    <template v-if="!isAdminMode">
      <div class="page-header-row">
        <div>
          <h1 class="page-title">{{ $t('sendStats.receiptTitle') }}</h1>
          <p class="page-desc">{{ $t('sendStats.receiptDesc') }}</p>
        </div>
        <div class="header-actions">
          <el-button type="primary" plain size="small" :loading="loading" @click="loadCustomerData">
            <el-icon><Refresh /></el-icon> {{ $t('common.refresh') }}
          </el-button>
          <el-button type="success" size="small" @click="exportCustomerExcel">
            <el-icon><Download /></el-icon> {{ $t('sendStats.exportExcel') }}
          </el-button>
        </div>
      </div>

      <!-- 日期筛选 -->
      <div class="soft-card filter-panel">
        <div class="filter-row">
          <div class="filter-group">
            <label class="filter-label">{{ $t('sendStats.dateRange') }}</label>
            <div class="date-filter-row">
              <div class="date-shortcuts">
                <button
                  v-for="s in dateShortcuts"
                  :key="s.key"
                  class="shortcut-btn"
                  :class="{ active: activeShortcut === s.key }"
                  @click="applyShortcut(s)"
                >{{ s.label }}</button>
              </div>
              <el-date-picker
                v-model="dateRange"
                type="daterange"
                range-separator="~"
                :start-placeholder="$t('reports.startDate')"
                :end-placeholder="$t('reports.endDate')"
                value-format="YYYY-MM-DD"
                style="width: 260px"
                @change="onDatePickerChange"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 汇总卡片 -->
      <div class="receipt-summary" v-if="cSummary">
        <div class="receipt-card total">
          <div class="rc-icon"><el-icon><ChatDotRound /></el-icon></div>
          <div class="rc-body">
            <div class="rc-label">{{ $t('sendStats.submitTotal') }}</div>
            <div class="rc-value">{{ (cSummary.submit_total || 0).toLocaleString() }}</div>
          </div>
        </div>
        <div class="receipt-card delivered">
          <div class="rc-icon"><el-icon><CircleCheck /></el-icon></div>
          <div class="rc-body">
            <div class="rc-label">{{ $t('sendStats.delivered') }}</div>
            <div class="rc-value">{{ (cSummary.delivered || 0).toLocaleString() }}</div>
            <div class="rc-rate">{{ cSummary.delivery_rate || 0 }}%</div>
          </div>
        </div>
        <div class="receipt-card failed">
          <div class="rc-icon"><el-icon><CircleClose /></el-icon></div>
          <div class="rc-body">
            <div class="rc-label">{{ $t('sendStats.failed') }}</div>
            <div class="rc-value">{{ (cSummary.failed || 0).toLocaleString() }}</div>
          </div>
        </div>
        <div class="receipt-card waiting">
          <div class="rc-icon"><el-icon><Clock /></el-icon></div>
          <div class="rc-body">
            <div class="rc-label">{{ $t('sendStats.waitingReceipt') }}</div>
            <div class="rc-value">{{ ((cSummary.pending || 0) + (cSummary.queued || 0) + (cSummary.sent || 0)).toLocaleString() }}</div>
            <div class="rc-sub">
              {{ $t('sendStats.pending') }}: {{ cSummary.pending || 0 }} /
              {{ $t('sendStats.queued') }}: {{ cSummary.queued || 0 }} /
              {{ $t('sendStats.sent') }}: {{ cSummary.sent || 0 }}
            </div>
          </div>
        </div>
        <div class="receipt-card expired">
          <div class="rc-icon"><el-icon><Warning /></el-icon></div>
          <div class="rc-body">
            <div class="rc-label">{{ $t('sendStats.expired') }}</div>
            <div class="rc-value">{{ (cSummary.expired || 0).toLocaleString() }}</div>
          </div>
        </div>
        <div class="receipt-card spending">
          <div class="rc-icon"><el-icon><Wallet /></el-icon></div>
          <div class="rc-body">
            <div class="rc-label">{{ $t('sendStats.totalSpending') }}</div>
            <div class="rc-value">${{ fmt5(cSummary.total_spending) }}</div>
          </div>
        </div>
      </div>

      <!-- 每日回执明细表（优先显示） -->
      <el-card class="data-card" style="margin-bottom: 24px">
        <template #header>
          <div class="card-header">
            <el-icon><List /></el-icon>
            <span>{{ $t('sendStats.dailyDetail') }}</span>
            <span class="table-count">({{ cItems.length }})</span>
          </div>
        </template>
        <el-table :data="cItems" v-loading="loading" style="width: 100%" :default-sort="{ prop: 'date', order: 'descending' }" stripe>
          <el-table-column prop="date" :label="$t('sendStats.date')" min-width="110" sortable>
            <template #default="{ row }">
              <span class="date-text">{{ row.date }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="submit_total" :label="$t('sendStats.submitTotal')" min-width="100" align="center" sortable>
            <template #default="{ row }">
              <span class="num-bold">{{ row.submit_total.toLocaleString() }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('sendStats.delivered')" min-width="130" align="center" sortable prop="delivered">
            <template #default="{ row }">
              <div class="receipt-num delivered">
                <span class="num">{{ row.delivered.toLocaleString() }}</span>
                <span class="pct" v-if="row.submit_total > 0">{{ (row.delivered / row.submit_total * 100).toFixed(1) }}%</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('sendStats.failed')" min-width="120" align="center" sortable prop="failed">
            <template #default="{ row }">
              <div class="receipt-num failed">
                <span class="num">{{ row.failed.toLocaleString() }}</span>
                <span class="pct" v-if="row.submit_total > 0 && row.failed > 0">{{ (row.failed / row.submit_total * 100).toFixed(1) }}%</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('sendStats.waitingReceipt')" min-width="130" align="center" sortable prop="pending">
            <template #default="{ row }">
              <div class="receipt-num waiting">
                <span class="num">{{ ((row.pending || 0) + (row.queued || 0) + (row.sent || 0)).toLocaleString() }}</span>
                <el-tooltip v-if="(row.pending || 0) + (row.queued || 0) + (row.sent || 0) > 0" placement="top">
                  <template #content>
                    {{ $t('sendStats.pending') }}: {{ row.pending || 0 }}<br/>
                    {{ $t('sendStats.queued') }}: {{ row.queued || 0 }}<br/>
                    {{ $t('sendStats.sent') }}: {{ row.sent || 0 }}
                  </template>
                  <el-icon class="detail-icon"><Warning /></el-icon>
                </el-tooltip>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('sendStats.expired')" min-width="100" align="center" sortable prop="expired">
            <template #default="{ row }">
              <span :class="row.expired > 0 ? 'text-muted-num' : 'text-zero'">{{ row.expired }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('sendStats.deliveryRate')" min-width="140" align="center" sortable prop="delivery_rate">
            <template #default="{ row }">
              <div class="rate-bar">
                <el-progress
                  :percentage="row.delivery_rate"
                  :stroke-width="14"
                  :text-inside="true"
                  :format="() => row.delivery_rate + '%'"
                  :color="getRateColor(row.delivery_rate)"
                  style="width: 100%"
                />
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('sendStats.totalSpending')" min-width="120" align="right" sortable prop="total_spending">
            <template #default="{ row }">
              <span class="spending-num">${{ fmt5(row.total_spending) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 图表行 -->
      <el-row :gutter="20" class="chart-row">
        <el-col :span="14">
          <el-card class="chart-card">
            <template #header>
              <div class="card-header">
                <el-icon><TrendCharts /></el-icon>
                <span>{{ $t('sendStats.trendTitle') }}</span>
              </div>
            </template>
            <div ref="cTrendRef" class="chart-div"></div>
          </el-card>
        </el-col>
        <el-col :span="10">
          <el-card class="chart-card">
            <template #header>
              <div class="card-header">
                <el-icon><PieChart /></el-icon>
                <span>{{ $t('sendStats.receiptDistribution') }}</span>
              </div>
            </template>
            <div ref="cPieRef" class="chart-div"></div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 失败原因分析 -->
      <el-row :gutter="20" class="fail-analysis-row" v-if="failCategories.length > 0">
        <el-col :span="10">
          <el-card class="chart-card fail-pie-card">
            <template #header>
              <div class="card-header">
                <el-icon><PieChart /></el-icon>
                <span>{{ $t('sendStats.failAnalysis') }}</span>
                <el-tag size="small" type="danger" class="fail-tag">{{ failTotal.toLocaleString() }}</el-tag>
              </div>
            </template>
            <div ref="failPieRef" class="chart-div"></div>
          </el-card>
        </el-col>
        <el-col :span="14">
          <el-card class="fail-table-card">
            <template #header>
              <div class="card-header">
                <el-icon><Warning /></el-icon>
                <span>{{ $t('sendStats.failAnalysis') }} - {{ $t('sendStats.failDetail') }}</span>
              </div>
            </template>
            <el-table :data="failCategories" style="width: 100%" :default-sort="{ prop: 'count', order: 'descending' }">
              <el-table-column :label="$t('sendStats.failCategory')" min-width="160">
                <template #default="{ row }">
                  <div class="fail-cat-cell">
                    <span class="fail-dot" :style="{ background: getFailColor(row.category) }"></span>
                    <span class="fail-cat-label">{{ $t('sendStats.reason_' + row.category) }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="count" :label="$t('sendStats.failCount')" width="100" align="right" sortable>
                <template #default="{ row }">
                  <span class="fail-count">{{ row.count.toLocaleString() }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="percentage" :label="$t('sendStats.failPercent')" width="140" align="center" sortable>
                <template #default="{ row }">
                  <div class="fail-bar-cell">
                    <el-progress
                      :percentage="row.percentage"
                      :stroke-width="12"
                      :text-inside="true"
                      :format="() => row.percentage + '%'"
                      :color="getFailColor(row.category)"
                      style="width: 100%"
                    />
                  </div>
                </template>
              </el-table-column>
              <el-table-column :label="$t('sendStats.failDetail')" min-width="240">
                <template #default="{ row }">
                  <div class="fail-details">
                    <el-tooltip v-for="(d, i) in row.details" :key="i" :content="d.error_message" placement="top">
                      <el-tag size="small" type="info" class="fail-detail-tag">
                        {{ d.error_message.length > 30 ? d.error_message.slice(0, 30) + '...' : d.error_message }}
                        <span class="fail-detail-cnt">×{{ d.count }}</span>
                      </el-tag>
                    </el-tooltip>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <!-- 无失败提示 -->
      <div v-else-if="!loading && cSummary && (cSummary.failed || 0) === 0" class="no-fail-hint">
        <el-icon><CircleCheck /></el-icon>
        <span>{{ $t('sendStats.noFailData') }}</span>
      </div>
    </template>

    <!-- ===== 管理员模式（原逻辑保持不变） ===== -->
    <template v-else>
      <div class="page-header-row">
        <div>
          <h1 class="page-title">{{ $t('sendStats.title') }}</h1>
      <p class="page-desc">{{ $t('sendStats.pageDesc') }}</p>
        </div>
        <div class="header-actions">
          <el-button type="primary" plain size="small" :loading="loading" @click="loadAll">
            <el-icon><Refresh /></el-icon> {{ $t('common.refresh') }}
          </el-button>
          <el-button type="success" size="small" @click="exportExcel">
            <el-icon><Download /></el-icon> {{ $t('sendStats.exportExcel') }}
          </el-button>
        </div>
    </div>

      <!-- 筛选面板 -->
      <div class="soft-card filter-panel">
        <div class="filter-row">
          <div class="filter-group">
            <label class="filter-label">{{ $t('sendStats.groupBy') }}</label>
            <div class="dim-tabs">
              <button
                v-for="d in dimOptions"
                :key="d.value"
                class="dim-tab"
                :class="{ active: filters.group_by === d.value }"
                @click="filters.group_by = d.value; loadAll()"
              >
                <el-icon><component :is="d.icon" /></el-icon>
                <span>{{ d.label }}</span>
              </button>
            </div>
          </div>

          <div class="filter-group">
            <label class="filter-label">{{ $t('sendStats.customer') }}</label>
            <el-select v-model="filters.account_id" :placeholder="$t('sendStats.allCustomers')" clearable filterable style="width: 180px" @change="loadAll">
            <el-option v-for="a in accountOptions" :key="a.id" :label="`${a.account_name} (${a.id})`" :value="a.id" />
          </el-select>
          </div>

          <div class="filter-group">
            <label class="filter-label">{{ $t('sendStats.sales') }}</label>
            <el-select v-model="filters.sales_id" :placeholder="$t('sendStats.allSales')" clearable style="width: 150px" @change="loadAll">
            <el-option v-for="s in staffOptions" :key="s.id" :label="s.real_name || s.username" :value="s.id" />
          </el-select>
          </div>

          <div class="filter-group">
            <label class="filter-label">{{ $t('sendStats.channel') }}</label>
            <el-select v-model="filters.channel_id" :placeholder="$t('sendStats.allChannels')" clearable style="width: 180px" @change="loadAll">
            <el-option v-for="c in channelOptions" :key="c.id" :label="c.channel_name" :value="c.id" />
          </el-select>
          </div>

          <div class="filter-group">
            <label class="filter-label">{{ $t('sendStats.country') }}</label>
            <el-select v-model="filters.country_code" placeholder="" clearable filterable style="width: 140px" @change="loadAll">
              <el-option :label="$t('sendStats.allCountries')" :value="undefined" />
              <el-option v-for="c in countryOptions" :key="c.iso" :label="`${c.flag} ${c.name}`" :value="c.iso" />
          </el-select>
          </div>

          <div class="filter-group">
            <label class="filter-label">{{ $t('sendStats.dateRange') }}</label>
            <div class="date-filter-row">
              <div class="date-shortcuts">
                <button
                  v-for="s in dateShortcuts"
                  :key="s.key"
                  class="shortcut-btn"
                  :class="{ active: activeShortcut === s.key }"
                  @click="applyShortcut(s)"
                >{{ s.label }}</button>
              </div>
              <el-date-picker
                v-model="dateRange"
                type="daterange"
                range-separator="~"
                :start-placeholder="$t('reports.startDate')"
                :end-placeholder="$t('reports.endDate')"
                value-format="YYYY-MM-DD"
                style="width: 260px"
                @change="onDatePickerChange"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 汇总卡片 -->
      <div class="summary-grid" v-if="summary">
        <div v-for="(card, idx) in adminSummaryCards" :key="idx" class="stat-card" :class="card.type">
          <div class="stat-icon">
            <el-icon><component :is="card.icon" /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-label">{{ card.label }}</div>
            <div class="stat-value">{{ card.value }}</div>
            <div class="stat-sub">{{ card.sub }}</div>
          </div>
        </div>
      </div>

      <!-- 图表行 -->
      <el-row :gutter="20" class="chart-row">
        <el-col :span="14">
          <el-card class="chart-card">
            <template #header>
              <div class="card-header">
                <el-icon><TrendCharts /></el-icon>
                <span>{{ $t('sendStats.trendTitle') }}</span>
              </div>
            </template>
            <div ref="trendChartRef" class="chart-div"></div>
    </el-card>
        </el-col>
        <el-col :span="10">
          <el-card class="chart-card">
            <template #header>
              <div class="card-header">
                <el-icon><PieChart /></el-icon>
                <span>{{ dimLabel }} {{ $t('reports.distribution') }}</span>
              </div>
            </template>
            <div ref="pieChartRef" class="chart-div"></div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 数据表格 -->
      <el-card class="data-card">
        <template #header>
          <div class="card-header">
            <el-icon><List /></el-icon>
            <span>{{ dimLabel }} {{ $t('reports.dataDetails') }}</span>
            <span class="table-count">({{ items.length }})</span>
          </div>
        </template>
        <el-table :data="items" v-loading="loading" style="width: 100%" :default-sort="{ prop: 'submit_total', order: 'descending' }">
          <el-table-column :label="dimLabel" prop="dim_label" min-width="160">
          <template #default="{ row }">
              <div class="dim-cell">
                <span v-if="filters.group_by === 'country'" class="country-label">
                  {{ getCountryDisplay(row.country_code) }}
                </span>
                <template v-else-if="filters.group_by === 'channel'">
                  <span class="name-text">{{ row.channel_name || '-' }}</span>
                  <span class="sub-id" v-if="row.channel_code">{{ row.channel_code }}</span>
                </template>
                <template v-else-if="filters.group_by === 'sales'">
                  <span class="name-text">{{ row.sales_name || $t('sendStats.unassigned') }}</span>
                  <span class="sub-id" v-if="row.sales_id">ID: {{ row.sales_id }}</span>
                </template>
                <template v-else>
                  <span class="name-text">{{ row.account_name || '-' }}</span>
                  <span class="sub-id" v-if="row.account_id">ID: {{ row.account_id }}</span>
                </template>
              </div>
          </template>
        </el-table-column>
          <el-table-column prop="submit_total" :label="$t('sendStats.submitTotal')" width="110" align="right" sortable />
          <el-table-column prop="success_count" :label="$t('sendStats.successCount')" width="100" align="right" sortable />
          <el-table-column prop="failed_count" :label="$t('sendStats.failedCount')" width="90" align="right" sortable>
            <template #default="{ row }">
              <span :class="row.failed_count > 0 ? 'text-danger' : ''">{{ row.failed_count }}</span>
            </template>
        </el-table-column>
          <el-table-column prop="pending_count" :label="$t('sendStats.pendingCount')" width="90" align="right" sortable>
            <template #default="{ row }">
              <span :class="row.pending_count > 0 ? 'text-warning' : ''">{{ row.pending_count }}</span>
            </template>
        </el-table-column>
          <el-table-column prop="success_rate" :label="$t('sendStats.successRate')" width="120" align="right" sortable>
            <template #default="{ row }">
              <div class="rate-cell">
                <span :class="getRateClass(row.success_rate)">{{ row.success_rate }}%</span>
                <el-progress
                  :percentage="row.success_rate"
                  :status="getRateStatus(row.success_rate)"
                  :show-text="false"
                  :stroke-width="3"
                  style="width: 44px; margin-top: 2px"
                />
              </div>
            </template>
        </el-table-column>
          <el-table-column prop="avg_unit_price" :label="$t('sendStats.unitPrice')" width="110" align="right" sortable>
            <template #default="{ row }">
              <span class="mono-num">${{ fmt5(row.avg_unit_price) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="total_revenue" :label="$t('sendStats.totalRevenue')" width="120" align="right" sortable>
            <template #default="{ row }">
              <span class="currency revenue">${{ fmt5(row.total_revenue) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="total_cost" :label="$t('sendStats.totalCost')" width="120" align="right" sortable>
            <template #default="{ row }">
              <span class="currency cost">${{ fmt5(row.total_cost) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="profit" :label="$t('sendStats.profit')" width="120" align="right" sortable>
            <template #default="{ row }">
              <span class="currency profit" :class="{ negative: row.profit < 0 }">
                ${{ fmt5(row.profit) }}
              </span>
            </template>
        </el-table-column>
      </el-table>
    </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Refresh, Download, User, Connection, Location, Avatar,
  PieChart, TrendCharts, List, Money, Wallet, Checked, ChatDotRound,
  CircleCheck, CircleClose, Clock, Warning
} from '@element-plus/icons-vue'
import { getSendStatistics, getAdminDailyStats, getAccountsAdmin, getChannelsAdmin } from '@/api/admin'
import { getCustomerSendStatistics, getCustomerDailyStats, getCustomerFailAnalysis } from '@/api/sms'
import request from '@/api/index'
import { COUNTRY_LIST, findCountryByIso } from '@/constants/countries'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import * as XLSX from 'xlsx'

const { t } = useI18n()

const isAdminMode = computed(() => {
  const impersonateMode = sessionStorage.getItem('impersonate_mode') === '1'
  return !impersonateMode && !!localStorage.getItem('admin_token')
})

const loading = ref(false)

// ===== 客户模式状态 =====
const cItems = ref<any[]>([])
const cSummary = ref<any>(null)
const cTrendData = ref<any[]>([])
const cTrendRef = ref<HTMLElement | null>(null)
const cPieRef = ref<HTMLElement | null>(null)
let cTrendChart: echarts.ECharts | null = null
let cPieChart: echarts.ECharts | null = null

const failCategories = ref<any[]>([])
const failTotal = ref(0)
const failPieRef = ref<HTMLElement | null>(null)
let failPieChart: echarts.ECharts | null = null


// ===== 管理员模式状态 =====
const items = ref<any[]>([])
const summary = ref<any>(null)
const trendData = ref<any[]>([])
const accountOptions = ref<any[]>([])
const staffOptions = ref<any[]>([])
const channelOptions = ref<any[]>([])
const countryOptions = ref(COUNTRY_LIST)

const trendChartRef = ref<HTMLElement | null>(null)
const pieChartRef = ref<HTMLElement | null>(null)
let trendChart: echarts.ECharts | null = null
let pieChart: echarts.ECharts | null = null

// ===== 公共 =====
const dateRange = ref<string[]>([])
const activeShortcut = ref('')

const defaultGroupBy = (() => {
  const impersonateMode = sessionStorage.getItem('impersonate_mode') === '1'
  return (!impersonateMode && !!localStorage.getItem('admin_token')) ? 'account' : 'country'
})()

const filters = reactive({
  account_id: undefined as number | undefined,
  sales_id: undefined as number | undefined,
  channel_id: undefined as number | undefined,
  country_code: undefined as string | undefined,
  group_by: defaultGroupBy,
})

const dimOptions = computed(() => [
  { label: t('sendStats.dimAccount'), value: 'account', icon: User },
  { label: t('sendStats.dimChannel'), value: 'channel', icon: Connection },
  { label: t('sendStats.dimCountry'), value: 'country', icon: Location },
  { label: t('sendStats.dimSales'), value: 'sales', icon: Avatar },
])

const dimLabel = computed(() => {
  const map: Record<string, string> = {
    account: t('sendStats.customer'),
    channel: t('sendStats.channel'),
    country: t('sendStats.country'),
    sales: t('sendStats.staff'),
  }
  return map[filters.group_by] || t('sendStats.customer')
})

const fmt5 = (v: any) => (Number(v) || 0).toFixed(5)

const fmtDate = (d: Date) => {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const dateShortcuts = computed(() => [
  { key: 'today', label: t('sendStats.today') },
  { key: 'yesterday', label: t('sendStats.yesterday') },
  { key: 'thisWeek', label: t('sendStats.thisWeek') },
  { key: 'thisMonth', label: t('sendStats.thisMonth') },
  { key: 'lastMonth', label: t('sendStats.lastMonth') },
])

const calcShortcutRange = (key: string): [string, string] => {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  switch (key) {
    case 'today':
      return [fmtDate(today), fmtDate(today)]
    case 'yesterday': {
      const y = new Date(today)
      y.setDate(y.getDate() - 1)
      return [fmtDate(y), fmtDate(y)]
    }
    case 'thisWeek': {
      const day = today.getDay() || 7
      const mon = new Date(today)
      mon.setDate(today.getDate() - day + 1)
      return [fmtDate(mon), fmtDate(today)]
    }
    case 'thisMonth': {
      const first = new Date(today.getFullYear(), today.getMonth(), 1)
      return [fmtDate(first), fmtDate(today)]
    }
    case 'lastMonth': {
      const first = new Date(today.getFullYear(), today.getMonth() - 1, 1)
      const last = new Date(today.getFullYear(), today.getMonth(), 0)
      return [fmtDate(first), fmtDate(last)]
    }
    default:
      return [fmtDate(today), fmtDate(today)]
  }
}

const applyShortcut = (s: { key: string }) => {
  activeShortcut.value = s.key
  dateRange.value = calcShortcutRange(s.key)
  if (isAdminMode.value) loadAll()
  else loadCustomerData()
}

const onDatePickerChange = () => {
  activeShortcut.value = ''
  if (isAdminMode.value) loadAll()
  else loadCustomerData()
}

const initDates = () => {
  activeShortcut.value = 'thisMonth'
  dateRange.value = calcShortcutRange('thisMonth')
}

const getDateParams = () => {
  const p: any = {}
  if (dateRange.value?.length === 2) {
    p.start_date = dateRange.value[0]
    p.end_date = dateRange.value[1]
  }
  return p
}

// ===== 客户模式数据加载 =====
const loadCustomerStats = async () => {
  const res = await getCustomerSendStatistics(getDateParams())
  if (res.success) {
    cItems.value = res.items || []
    cSummary.value = res.summary || null
  } else {
    ElMessage.warning(res.detail || t('common.loadFailed'))
  }
}

const loadCustomerTrend = async () => {
  const params = { ...getDateParams(), days: 90 }
  const res = await getCustomerDailyStats(params)
  if (res.success) {
    cTrendData.value = res.statistics || []
  } else {
    ElMessage.warning(res.detail || t('common.loadFailed'))
  }
}

const loadCustomerFailAnalysis = async () => {
  try {
    const res = await getCustomerFailAnalysis(getDateParams())
    if (res.success) {
      failCategories.value = res.categories || []
      failTotal.value = res.total_failed || 0
    }
  } catch {
    failCategories.value = []
    failTotal.value = 0
  }
}

const loadCustomerData = async () => {
  loading.value = true
  try {
    await Promise.all([loadCustomerStats(), loadCustomerTrend(), loadCustomerFailAnalysis()])
    nextTick(() => updateCustomerCharts())
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || e.message || t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

const FAIL_COLORS: Record<string, string> = {
  undelivered: '#ef4444',
  rejected: '#f97316',
  unknown_receipt: '#a855f7',
  submit_rejected: '#ec4899',
  no_channel: '#64748b',
  channel_error: '#78716c',
  upstream_error: '#eab308',
  system_error: '#6366f1',
  timeout: '#94a3b8',
  other: '#475569',
  unknown: '#334155',
}

const getFailColor = (cat: string) => FAIL_COLORS[cat] || '#64748b'

const updateCustomerCharts = () => {
  updateCustomerTrendChart()
  updateCustomerPieChart()
  updateFailPieChart()
}

const RECEIPT_COLORS = {
  delivered: '#10b981',
  failed: '#ef4444',
  pending: '#f59e0b',
  queued: '#6366f1',
  sent: '#3b82f6',
  expired: '#94a3b8',
}

const updateCustomerTrendChart = () => {
  if (!cTrendRef.value) return
  if (!cTrendChart) cTrendChart = echarts.init(cTrendRef.value)

  const dates = cTrendData.value.map(d => d.date)
  const delivered = cTrendData.value.map(d => d.delivered)
  const failed = cTrendData.value.map(d => d.failed)
  const pending = cTrendData.value.map(d => (d.pending || 0) + (d.queued || 0) + (d.sent || 0))
  const expired = cTrendData.value.map(d => d.expired)
  const rates = cTrendData.value.map(d => d.delivery_rate)

  cTrendChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { top: 0, textStyle: { fontSize: 11, color: '#94a3b8' } },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '40px', containLabel: true },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { fontSize: 10, color: '#64748b', rotate: dates.length > 20 ? 30 : 0 },
      axisLine: { lineStyle: { color: '#334155' } },
    },
    yAxis: [
      { type: 'value', name: t('sendStats.submitTotal'), axisLabel: { fontSize: 10, color: '#64748b' }, splitLine: { lineStyle: { color: '#1e293b' } } },
      { type: 'value', name: '%', max: 100, axisLabel: { fontSize: 10, color: '#64748b' }, splitLine: { show: false } },
    ],
    series: [
      {
        name: t('sendStats.delivered'),
        type: 'bar',
        stack: 'receipt',
        data: delivered,
        itemStyle: { color: RECEIPT_COLORS.delivered, borderRadius: [0, 0, 0, 0] },
        barMaxWidth: 24,
      },
      {
        name: t('sendStats.failed'),
        type: 'bar',
        stack: 'receipt',
        data: failed,
        itemStyle: { color: RECEIPT_COLORS.failed },
        barMaxWidth: 24,
      },
      {
        name: t('sendStats.waitingReceipt'),
        type: 'bar',
        stack: 'receipt',
        data: pending,
        itemStyle: { color: RECEIPT_COLORS.pending },
        barMaxWidth: 24,
      },
      {
        name: t('sendStats.expired'),
        type: 'bar',
        stack: 'receipt',
        data: expired,
        itemStyle: { color: RECEIPT_COLORS.expired, borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 24,
      },
      {
        name: t('sendStats.deliveryRate'),
        type: 'line',
        yAxisIndex: 1,
        data: rates,
        smooth: true,
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: { color: '#fbbf24', width: 2 },
        itemStyle: { color: '#fbbf24' },
      },
    ],
  }, true)
}

const updateCustomerPieChart = () => {
  if (!cPieRef.value) return
  if (!cPieChart) cPieChart = echarts.init(cPieRef.value)

  const s = cSummary.value
  if (!s) return

  const pieData = [
    { name: t('sendStats.delivered'), value: s.delivered || 0, itemStyle: { color: RECEIPT_COLORS.delivered } },
    { name: t('sendStats.failed'), value: s.failed || 0, itemStyle: { color: RECEIPT_COLORS.failed } },
    { name: t('sendStats.pending'), value: s.pending || 0, itemStyle: { color: RECEIPT_COLORS.pending } },
    { name: t('sendStats.queued'), value: s.queued || 0, itemStyle: { color: RECEIPT_COLORS.queued } },
    { name: t('sendStats.sent'), value: s.sent || 0, itemStyle: { color: RECEIPT_COLORS.sent } },
    { name: t('sendStats.expired'), value: s.expired || 0, itemStyle: { color: RECEIPT_COLORS.expired } },
  ].filter(d => d.value > 0)

  cPieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 10, textStyle: { fontSize: 11, color: '#94a3b8' } },
    series: [{
      type: 'pie',
      radius: ['38%', '68%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 8, borderColor: 'rgba(0,0,0,0.3)', borderWidth: 2 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 13, fontWeight: 'bold' } },
      data: pieData,
    }],
  }, true)
}

const updateFailPieChart = () => {
  if (!failPieRef.value) return
  if (!failPieChart) failPieChart = echarts.init(failPieRef.value)

  const pieData = failCategories.value.map(c => ({
    name: t('sendStats.reason_' + c.category),
    value: c.count,
    itemStyle: { color: getFailColor(c.category) },
  }))

  failPieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: {
      bottom: 0,
      icon: 'circle',
      itemWidth: 8,
      textStyle: { fontSize: 11, color: '#94a3b8' },
    },
    series: [{
      type: 'pie',
      radius: ['35%', '65%'],
      center: ['50%', '42%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 6, borderColor: 'rgba(0,0,0,0.3)', borderWidth: 2 },
      label: {
        show: true,
        position: 'outside',
        formatter: '{b}\n{d}%',
        fontSize: 11,
        color: '#94a3b8',
      },
      labelLine: { length: 12, length2: 8 },
      emphasis: { label: { show: true, fontSize: 13, fontWeight: 'bold' } },
      data: pieData,
    }],
  }, true)
}

const exportCustomerExcel = () => {
  const data = cItems.value.map(row => ({
    [t('sendStats.date')]: row.date,
    [t('sendStats.submitTotal')]: row.submit_total,
    [t('sendStats.delivered')]: row.delivered,
    [t('sendStats.failed')]: row.failed,
    [t('sendStats.pending')]: row.pending,
    [t('sendStats.queued')]: row.queued,
    [t('sendStats.sent')]: row.sent,
    [t('sendStats.expired')]: row.expired,
    [t('sendStats.deliveryRate')]: `${row.delivery_rate}%`,
    [t('sendStats.totalSpending')]: Number(fmt5(row.total_spending)),
  }))
  const ws = XLSX.utils.json_to_sheet(data)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'ReceiptStats')
  XLSX.writeFile(wb, `ReceiptStats_${new Date().getTime()}.xlsx`)
}

// ===== 管理员模式数据加载 =====
const getFilterParams = () => {
  const p: any = { ...getDateParams() }
  if (filters.account_id) p.account_id = filters.account_id
  if (filters.sales_id) p.sales_id = filters.sales_id
  if (filters.channel_id) p.channel_id = filters.channel_id
  if (filters.country_code) p.country_code = filters.country_code
  return p
}

const loadStats = async () => {
  const params = { ...getFilterParams(), group_by: filters.group_by }
  const res = await getSendStatistics(params)
  if (res.success) {
    items.value = res.items || []
    summary.value = res.summary || null
  } else {
    ElMessage.warning(res.detail || t('common.loadFailed'))
  }
}

const loadTrend = async () => {
  const params = { ...getFilterParams(), days: 90 }
  const res = await getAdminDailyStats(params)
  if (res.success) {
    trendData.value = res.statistics || []
  } else {
    ElMessage.warning(res.detail || t('common.loadFailed'))
  }
}

const loadAll = async () => {
  loading.value = true
  try {
    await Promise.all([loadStats(), loadTrend()])
    nextTick(() => updateAdminCharts())
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || e.message || t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

const loadAccounts = async () => {
  try {
    const res = await getAccountsAdmin({ limit: 500, offset: 0 })
    accountOptions.value = res.accounts || []
  } catch { accountOptions.value = [] }
}

const loadStaff = async () => {
  try {
    const res = await request.get('/admin/users', { params: { include_monthly_stats: false } })
    staffOptions.value = res.users || []
  } catch { staffOptions.value = [] }
}

const loadChannels = async () => {
  try {
    const res = await getChannelsAdmin()
    channelOptions.value = res.channels || []
  } catch { channelOptions.value = [] }
}

const adminSummaryCards = computed(() => {
  const s = summary.value
  if (!s) return []
  return [
    {
      label: t('sendStats.submitTotal'),
      value: (s.submit_total || 0).toLocaleString(),
      sub: `${t('sendStats.successCount')}: ${(s.success_count || 0).toLocaleString()}`,
      icon: Money,
      type: 'primary',
    },
    {
      label: t('sendStats.successRate'),
      value: `${s.success_rate || 0}%`,
      sub: `${t('sendStats.failedCount')}: ${(s.failed_count || 0).toLocaleString()} / ${t('sendStats.pendingCount')}: ${(s.pending_count || 0).toLocaleString()}`,
      icon: Checked,
      type: s.success_rate >= 80 ? 'success' : 'warning',
    },
    {
      label: t('sendStats.totalRevenue'),
      value: `$${fmt5(s.total_revenue)}`,
      sub: `${t('sendStats.unitPrice')}: $${s.submit_total > 0 ? (s.total_revenue / s.submit_total).toFixed(5) : '0.00000'}`,
      icon: Wallet,
      type: 'info',
    },
    {
      label: t('sendStats.totalCost'),
      value: `$${fmt5(s.total_cost)}`,
      sub: `${t('sendStats.unitPrice')}: $${s.submit_total > 0 ? (s.total_cost / s.submit_total).toFixed(5) : '0.00000'}`,
      icon: ChatDotRound,
      type: 'warning',
    },
    {
      label: t('sendStats.profit'),
      value: `$${fmt5(s.profit)}`,
      sub: `${t('sendStats.profitMargin')}: ${s.total_revenue > 0 ? (s.profit / s.total_revenue * 100).toFixed(2) : '0.00'}%`,
      icon: TrendCharts,
      type: (s.profit || 0) >= 0 ? 'success' : 'danger',
    },
  ]
})

const updateAdminCharts = () => {
  updateAdminTrendChart()
  updateAdminPieChart()
}

const updateAdminTrendChart = () => {
  if (!trendChartRef.value) return
  if (!trendChart) trendChart = echarts.init(trendChartRef.value)

  const dates = trendData.value.map(d => d.date)
  const sent = trendData.value.map(d => d.total_sent)
  const delivered = trendData.value.map(d => d.total_delivered)
  const failed = trendData.value.map(d => d.total_failed || 0)
  const rates = trendData.value.map(d => d.success_rate)

  trendChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { top: 0, textStyle: { fontSize: 11, color: '#94a3b8' } },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '40px', containLabel: true },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { fontSize: 10, color: '#64748b', rotate: dates.length > 20 ? 30 : 0 },
      axisLine: { lineStyle: { color: '#334155' } },
    },
    yAxis: [
      { type: 'value', name: t('sendStats.submitTotal'), axisLabel: { fontSize: 10, color: '#64748b' }, splitLine: { lineStyle: { color: '#1e293b' } } },
      { type: 'value', name: '%', max: 100, axisLabel: { fontSize: 10, color: '#64748b' }, splitLine: { show: false } },
    ],
    series: [
      {
        name: t('sendStats.submitTotal'),
        type: 'bar',
        data: sent,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#3b82f6' },
            { offset: 1, color: '#1d4ed8' },
          ]),
          borderRadius: [3, 3, 0, 0],
        },
        barMaxWidth: 20,
      },
      {
        name: t('sendStats.successCount'),
        type: 'bar',
        data: delivered,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#2dd4bf' },
            { offset: 1, color: '#0d9488' },
          ]),
          borderRadius: [3, 3, 0, 0],
        },
        barMaxWidth: 20,
      },
      {
        name: t('sendStats.failedCount'),
        type: 'bar',
        data: failed,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#f87171' },
            { offset: 1, color: '#dc2626' },
          ]),
          borderRadius: [3, 3, 0, 0],
        },
        barMaxWidth: 20,
      },
      {
        name: t('sendStats.successRate'),
        type: 'line',
        yAxisIndex: 1,
        data: rates,
        smooth: true,
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: { color: '#fbbf24', width: 2 },
        itemStyle: { color: '#fbbf24' },
      },
    ],
  }, true)
}

const updateAdminPieChart = () => {
  if (!pieChartRef.value) return
  if (!pieChart) pieChart = echarts.init(pieChartRef.value)

  const sorted = [...items.value].sort((a, b) => b.submit_total - a.submit_total).slice(0, 10)
  const pieData = sorted.map(d => ({
    name: d.dim_label || '-',
    value: d.submit_total,
  }))

  pieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 10, textStyle: { fontSize: 11, color: '#94a3b8' } },
    series: [{
      type: 'pie',
      radius: ['38%', '68%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 8, borderColor: 'rgba(0,0,0,0.3)', borderWidth: 2 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 13, fontWeight: 'bold' } },
      data: pieData,
    }],
  }, true)
}

const exportExcel = () => {
  const data = items.value.map(row => ({
    [dimLabel.value]: row.dim_label || '-',
    [t('sendStats.submitTotal')]: row.submit_total,
    [t('sendStats.successCount')]: row.success_count,
    [t('sendStats.failedCount')]: row.failed_count,
    [t('sendStats.pendingCount')]: row.pending_count,
    [t('sendStats.successRate')]: `${row.success_rate}%`,
    [t('sendStats.unitPrice')]: Number(fmt5(row.avg_unit_price)),
    [t('sendStats.totalRevenue')]: Number(fmt5(row.total_revenue)),
    [t('sendStats.totalCost')]: Number(fmt5(row.total_cost)),
    [t('sendStats.profit')]: Number(fmt5(row.profit)),
  }))
  const ws = XLSX.utils.json_to_sheet(data)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'SendStats')
  XLSX.writeFile(wb, `SendStats_${new Date().getTime()}.xlsx`)
}

// ===== 公共 =====
const getCountryDisplay = (code: string) => {
  if (!code) return '-'
  const c = findCountryByIso(code)
  return c ? `${c.flag} ${c.name}` : code
}

const getRateClass = (rate: number) => {
  if (rate >= 90) return 'text-success'
  if (rate >= 70) return 'text-warning'
  return 'text-danger'
}

const getRateStatus = (rate: number) => {
  if (rate >= 90) return 'success'
  if (rate >= 70) return 'warning'
  return 'exception'
}

const getRateColor = (rate: number) => {
  if (rate >= 90) return '#10b981'
  if (rate >= 70) return '#f59e0b'
  return '#ef4444'
}

const handleResize = () => {
  trendChart?.resize()
  pieChart?.resize()
  cTrendChart?.resize()
  cPieChart?.resize()
  failPieChart?.resize()
}

onMounted(() => {
  initDates()
  if (isAdminMode.value) {
  loadAccounts()
  loadStaff()
  loadChannels()
    loadAll()
  } else {
    loadCustomerData()
  }
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
  pieChart?.dispose()
  cTrendChart?.dispose()
  cPieChart?.dispose()
  failPieChart?.dispose()
})
</script>

<style scoped>
.send-stats-page {
  padding: 24px;
  background: var(--bg-body);
  min-height: 100%;
}

.page-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 800;
  margin: 0;
  letter-spacing: -0.02em;
  background: linear-gradient(135deg, #3b82f6, #2dd4bf);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.page-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 4px 0 0;
}

.header-actions {
  display: flex;
  gap: 10px;
}

/* 筛选面板 */
.filter-panel {
  background: var(--bg-secondary);
  border-radius: 16px;
  padding: 20px 24px;
  margin-bottom: 24px;
  border: 1px solid rgba(255,255,255,0.03);
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  align-items: flex-end;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.dim-tabs {
  display: flex;
  gap: 4px;
  background: var(--bg-tertiary);
  border-radius: 10px;
  padding: 3px;
}

.dim-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.dim-tab:hover {
  color: var(--text-primary);
  background: rgba(255,255,255,0.04);
}

.dim-tab.active {
  background: var(--primary);
  color: #fff;
  box-shadow: 0 2px 8px rgba(59,130,246,0.35);
}

.date-filter-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.date-shortcuts {
  display: flex;
  gap: 4px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  padding: 3px;
}

.shortcut-btn {
  padding: 5px 12px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.shortcut-btn:hover {
  color: var(--text-primary);
  background: rgba(255,255,255,0.04);
}

.shortcut-btn.active {
  background: var(--primary);
  color: #fff;
  box-shadow: 0 2px 6px rgba(59,130,246,0.3);
}

/* ===== 客户回执汇总卡片 ===== */
.receipt-summary {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 14px;
  margin-bottom: 24px;
}

.receipt-card {
  background: var(--bg-secondary);
  border-radius: 14px;
  padding: 18px 16px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border: 1px solid rgba(255,255,255,0.03);
  transition: all 0.25s ease;
}

.receipt-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 20px rgba(0,0,0,0.25);
}

.rc-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}

.receipt-card.total .rc-icon { background: rgba(59,130,246,0.15); color: #3b82f6; }
.receipt-card.delivered .rc-icon { background: rgba(16,185,129,0.15); color: #10b981; }
.receipt-card.failed .rc-icon { background: rgba(239,68,68,0.15); color: #ef4444; }
.receipt-card.waiting .rc-icon { background: rgba(245,158,11,0.15); color: #f59e0b; }
.receipt-card.expired .rc-icon { background: rgba(148,163,184,0.15); color: #94a3b8; }
.receipt-card.spending .rc-icon { background: rgba(99,102,241,0.15); color: #6366f1; }

.rc-body { flex: 1; min-width: 0; }
.rc-label { font-size: 11px; color: var(--text-tertiary); margin-bottom: 4px; font-weight: 500; }
.rc-value { font-size: 20px; font-weight: 800; color: var(--text-primary); line-height: 1.2; }
.rc-rate { font-size: 13px; font-weight: 700; color: #10b981; margin-top: 2px; }
.rc-sub { font-size: 10px; color: var(--text-quaternary, #64748b); margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* ===== 管理员汇总卡片 ===== */
.summary-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: var(--bg-secondary);
  border-radius: 16px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: all 0.25s ease;
  border: 1px solid rgba(255,255,255,0.03);
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px rgba(0,0,0,0.3);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  flex-shrink: 0;
}

.stat-card.primary .stat-icon { background: rgba(59,130,246,0.15); color: #3b82f6; }
.stat-card.success .stat-icon { background: rgba(45,212,191,0.15); color: #2dd4bf; }
.stat-card.warning .stat-icon { background: rgba(251,191,36,0.15); color: #fbbf24; }
.stat-card.info .stat-icon { background: rgba(148,163,184,0.15); color: #94a3b8; }
.stat-card.danger .stat-icon { background: rgba(248,113,113,0.15); color: #f87171; }

.stat-info { flex: 1; min-width: 0; }
.stat-label { font-size: 12px; color: var(--text-tertiary); margin-bottom: 4px; }
.stat-value { font-size: 22px; font-weight: 800; color: var(--text-primary); margin-bottom: 2px; }
.stat-sub { font-size: 11px; color: var(--text-quaternary, #64748b); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* 图表 */
.chart-row { margin-bottom: 24px; }
.chart-card { border-radius: 16px; overflow: hidden; height: 400px; }
.chart-div { height: 320px; width: 100%; }

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 14px;
}

.table-count {
  color: var(--text-quaternary, #64748b);
  font-weight: 400;
  font-size: 12px;
  margin-left: 4px;
}

/* 表格 */
.data-card {
  border-radius: 16px;
}

.dim-cell {
  display: flex;
  flex-direction: column;
}

.name-text {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 13px;
}

.sub-id {
  font-size: 11px;
  color: var(--text-quaternary, #64748b);
  margin-top: 1px;
}

.country-label {
  font-size: 13px;
  font-weight: 600;
}

.mono-num {
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  font-size: 12px;
  color: var(--text-secondary);
}

.currency {
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  font-weight: 700;
  font-size: 13px;
}

.revenue { color: #3b82f6; }
.cost { color: var(--text-tertiary); font-weight: 500; }
.profit { color: #2dd4bf; }
.profit.negative { color: #f87171; }

.rate-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.text-success { color: #34C759; font-weight: 700; }
.text-warning { color: #FF9500; font-weight: 700; }
.text-danger { color: #FF3B30; font-weight: 700; }
.text-info { color: #6366f1; font-weight: 600; }
.text-muted { color: #94a3b8; font-weight: 600; }

/* 客户表格优化 */
.date-text {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}

.num-bold {
  font-weight: 800;
  font-size: 14px;
  color: var(--text-primary);
}

.receipt-num {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.receipt-num .num {
  font-weight: 700;
  font-size: 14px;
}

.receipt-num .pct {
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 600;
}

.receipt-num.delivered .num { color: #10b981; }
.receipt-num.delivered .pct { background: rgba(16,185,129,0.12); color: #10b981; }

.receipt-num.failed .num { color: #ef4444; }
.receipt-num.failed .pct { background: rgba(239,68,68,0.12); color: #ef4444; }

.receipt-num.waiting .num { color: #f59e0b; }
.receipt-num.waiting .detail-icon { color: #f59e0b; font-size: 14px; cursor: help; }

.text-muted-num { color: #94a3b8; font-weight: 600; font-size: 13px; }
.text-zero { color: var(--text-quaternary, #475569); font-size: 13px; }

.rate-bar {
  width: 100%;
  padding: 0 4px;
}

.rate-bar :deep(.el-progress-bar__inner) {
  border-radius: 7px;
  transition: width 0.6s ease;
}

.rate-bar :deep(.el-progress-bar__outer) {
  border-radius: 7px;
  background: rgba(255,255,255,0.06);
}

.rate-bar :deep(.el-progress-bar__innerText) {
  font-size: 11px;
  font-weight: 700;
}

.spending-num {
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  font-size: 13px;
  font-weight: 600;
  color: #6366f1;
}

/* ===== 失败原因分析 ===== */
.fail-analysis-row {
  margin-bottom: 24px;
}

.fail-pie-card {
  border-radius: 16px;
  overflow: hidden;
  height: 400px;
}

.fail-table-card {
  border-radius: 16px;
  overflow: hidden;
}

.fail-tag {
  margin-left: 8px;
}

.fail-cat-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.fail-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.fail-cat-label {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}

.fail-count {
  font-weight: 800;
  font-size: 14px;
  color: #ef4444;
}

.fail-bar-cell {
  width: 100%;
  padding: 0 4px;
}

.fail-bar-cell :deep(.el-progress-bar__inner) {
  border-radius: 6px;
}

.fail-bar-cell :deep(.el-progress-bar__outer) {
  border-radius: 6px;
  background: rgba(255,255,255,0.06);
}

.fail-bar-cell :deep(.el-progress-bar__innerText) {
  font-size: 10px;
  font-weight: 700;
}

.fail-details {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.fail-detail-tag {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  cursor: help;
}

.fail-detail-cnt {
  margin-left: 4px;
  font-weight: 700;
  color: var(--el-color-danger);
}

.no-fail-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 24px;
  margin-bottom: 24px;
  background: rgba(16,185,129,0.08);
  border-radius: 12px;
  color: #10b981;
  font-weight: 600;
  font-size: 14px;
}

.no-fail-hint .el-icon {
  font-size: 20px;
}

.time-text-sm {
  font-size: 12px;
  color: var(--text-tertiary);
}

.text-zero {
  color: var(--text-quaternary, #475569);
  font-size: 13px;
}

@media (max-width: 1400px) {
  .summary-grid { grid-template-columns: repeat(3, 1fr); }
  .receipt-summary { grid-template-columns: repeat(3, 1fr); }
}

@media (max-width: 1100px) {
  .summary-grid { grid-template-columns: repeat(2, 1fr); }
  .receipt-summary { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 900px) {
  .filter-row { flex-direction: column; }
  .summary-grid { grid-template-columns: 1fr; }
  .receipt-summary { grid-template-columns: 1fr; }
  .page-header-row { flex-direction: column; align-items: flex-start; gap: 12px; }
}
</style>
