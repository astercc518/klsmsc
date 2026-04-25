<template>
  <div class="reports">
    <div class="page-header">
      <h2>{{ $t('reports.title') }}</h2>
      <p class="page-desc">{{ $t('reports.pageDesc') }}</p>
    </div>

    <!-- 日期筛选 -->
    <el-card class="filter-card">
      <el-form :inline="true" :model="filterForm" class="filter-form">
        <el-form-item :label="$t('reports.startDate')">
          <el-date-picker
            v-model="filterForm.startDate"
            type="date"
            :placeholder="$t('reports.selectStartDate')"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            clearable
          />
        </el-form-item>
        <el-form-item :label="$t('reports.endDate')">
          <el-date-picker
            v-model="filterForm.endDate"
            type="date"
            :placeholder="$t('reports.selectEndDate')"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            clearable
          />
        </el-form-item>
        <el-form-item>
          <el-button-group>
            <el-button size="small" @click="applyQuickRange('today')">{{ $t('reports.today') }}</el-button>
            <el-button size="small" @click="applyQuickRange(7)">{{ $t('reports.last7Days') }}</el-button>
            <el-button size="small" @click="applyQuickRange(30)">{{ $t('reports.last30Days') }}</el-button>
            <el-button size="small" @click="applyQuickRange('month')">{{ $t('reports.thisMonth') }}</el-button>
          </el-button-group>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="loadStatistics">
            <el-icon><Search /></el-icon>
            {{ $t('smsRecords.query') }}
          </el-button>
          <el-button @click="resetFilter">{{ $t('common.reset') }}</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-item">
            <div class="stat-icon sent">
              <el-icon><Document /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-label">{{ $t('reports.totalSent') }}</div>
              <div class="stat-value">{{ statistics.total_sent }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-item">
            <div class="stat-icon delivered">
              <el-icon><CircleCheck /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-label">{{ $t('reports.totalDelivered') }}</div>
              <div class="stat-value">{{ statistics.total_delivered }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-item">
            <div class="stat-icon failed">
              <el-icon><CircleClose /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-label">{{ $t('reports.totalFailed') }}</div>
              <div class="stat-value">{{ statistics.total_failed }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-item">
            <div class="stat-icon pending">
              <el-icon><Clock /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-label">{{ $t('reports.totalPending') }}</div>
              <div class="stat-value">{{ statistics.total_pending ?? 0 }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-item">
            <div class="stat-icon rate">
              <el-icon><TrendCharts /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-label">{{ $t('reports.successRate') }}</div>
              <div class="stat-value">{{ statistics.success_rate }}%</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-item">
            <div class="stat-icon cost">
              <el-icon><Money /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-label">{{ $t('reports.totalCost') }}</div>
              <div class="stat-value">{{ statistics.total_cost.toFixed(4) }} {{ statistics.currency }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-item">
            <div class="stat-icon revenue">
              <el-icon><Wallet /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-label">{{ $t('reports.totalRevenue') }}</div>
              <div class="stat-value">{{ (statistics.total_revenue ?? 0).toFixed(4) }} {{ statistics.currency }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-item">
            <div class="stat-icon profit">
              <el-icon><Coin /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-label">{{ $t('reports.totalProfit') }}</div>
              <div class="stat-value" :class="{ negative: (statistics.total_profit ?? 0) < 0 }">
                {{ (statistics.total_profit ?? 0).toFixed(4) }} {{ statistics.currency }}
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 成功率分析 -->
    <el-row :gutter="20" class="analysis-row">
      <el-col :xs="24" :lg="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>{{ $t('reports.byChannelStats') }}</span>
              <el-button size="small" @click="exportChannelData">
                <el-icon><Download /></el-icon>
                {{ $t('common.export') }}
              </el-button>
            </div>
          </template>
          <el-table :data="successRateData.by_channel" stripe max-height="320">
            <el-table-column prop="channel_name" :label="$t('reports.channelName')" min-width="120" />
            <el-table-column prop="total" :label="$t('reports.sendCount')" width="90" align="right" />
            <el-table-column prop="delivered" :label="$t('reports.deliveredCount')" width="90" align="right" />
            <el-table-column prop="success_rate" :label="$t('reports.successRate')" width="100" align="right">
              <template #default="{ row }">
                <el-tag :type="row.success_rate >= 95 ? 'success' : row.success_rate >= 90 ? 'warning' : 'danger'" size="small">
                  {{ row.success_rate }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!successRateData.by_channel?.length" :description="$t('common.noData')" />
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>{{ $t('reports.byCountryStats') }}</span>
              <el-button size="small" @click="exportCountryData">
                <el-icon><Download /></el-icon>
                {{ $t('common.export') }}
              </el-button>
            </div>
          </template>
          <el-table :data="successRateData.by_country" stripe max-height="320">
            <el-table-column :label="$t('reports.countryCode')" width="100">
              <template #default="{ row }">
                {{ getCountryName(row.country_code) }}
              </template>
            </el-table-column>
            <el-table-column prop="total" :label="$t('reports.sendCount')" width="90" align="right" />
            <el-table-column prop="delivered" :label="$t('reports.deliveredCount')" width="90" align="right" />
            <el-table-column prop="success_rate" :label="$t('reports.successRate')" width="100" align="right">
              <template #default="{ row }">
                <el-tag :type="row.success_rate >= 95 ? 'success' : row.success_rate >= 90 ? 'warning' : 'danger'" size="small">
                  {{ row.success_rate }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!successRateData.by_country?.length" :description="$t('common.noData')" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表展示 -->
    <el-row :gutter="20" class="charts-row">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>{{ $t('reports.sendTrend') }}</span>
              <div class="chart-actions">
                <el-select v-model="chartDays" @change="loadDailyStats" style="width: 120px" size="small">
                  <el-option :label="$t('reports.last7Days')" :value="7" />
                  <el-option :label="$t('reports.last30Days')" :value="30" />
                  <el-option :label="$t('reports.last90Days')" :value="90" />
                </el-select>
                <el-button size="small" @click="exportDailyStats">
                  <el-icon><Download /></el-icon>
                  {{ $t('common.export') }}
                </el-button>
              </div>
            </div>
          </template>
          <div ref="trendChartRef" class="chart-container"></div>
          <el-empty v-if="!dailyStatsData.length" :description="$t('common.noData')" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="charts-row">
      <el-col :xs="24" :lg="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>{{ $t('reports.successRateTrend') }}</span>
            </div>
          </template>
          <div ref="successRateChartRef" class="chart-container-sm"></div>
          <el-empty v-if="!dailyStatsData.length" :description="$t('common.noData')" />
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>{{ $t('reports.costTrend') }}</span>
            </div>
          </template>
          <div ref="costChartRef" class="chart-container-sm"></div>
          <el-empty v-if="!dailyStatsData.length" :description="$t('common.noData')" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 费用汇总 -->
    <el-row :gutter="20" class="cost-row">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>{{ $t('reports.costStats') }}</span>
            </div>
          </template>
          <div class="cost-summary">
            <div class="cost-item">
              <span class="cost-label">{{ $t('reports.totalCost') }}:</span>
              <span class="cost-value">{{ statistics.total_cost.toFixed(4) }} {{ statistics.currency }}</span>
            </div>
            <div class="cost-item">
              <span class="cost-label">{{ $t('reports.totalRevenue') }}:</span>
              <span class="cost-value revenue">{{ (statistics.total_revenue ?? 0).toFixed(4) }} {{ statistics.currency }}</span>
            </div>
            <div class="cost-item">
              <span class="cost-label">{{ $t('reports.totalProfit') }}:</span>
              <span class="cost-value" :class="(statistics.total_profit ?? 0) >= 0 ? 'profit' : 'negative'">
                {{ (statistics.total_profit ?? 0).toFixed(4) }} {{ statistics.currency }}
              </span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Document, CircleCheck, CircleClose, TrendCharts, Download, Search, Clock, Money, Wallet, Coin } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import * as XLSX from '@e965/xlsx'
import { getStatistics, getSuccessRate, getDailyStats } from '@/api/reports'
import { findCountryByIso, findCountryByDial } from '@/constants/countries'

const { t } = useI18n()
const loading = ref(false)
const filterForm = ref({
  startDate: '',
  endDate: ''
})

const statistics = ref({
  total_sent: 0,
  total_delivered: 0,
  total_failed: 0,
  total_pending: 0,
  success_rate: 0,
  total_cost: 0,
  total_revenue: 0,
  total_profit: 0,
  currency: 'USD'
})

const successRateData = ref({
  overall_rate: 0,
  by_channel: [] as any[],
  by_country: [] as any[]
})

const chartDays = ref(30)
const dailyStatsData = ref<any[]>([])

const trendChartRef = ref<HTMLElement>()
const successRateChartRef = ref<HTMLElement>()
const costChartRef = ref<HTMLElement>()

let trendChart: echarts.ECharts | null = null
let successRateChart: echarts.ECharts | null = null
let costChart: echarts.ECharts | null = null

const getCountryName = (code: string) => {
  if (!code) return code
  const c = findCountryByIso(code) || findCountryByDial(code)
  return c ? c.name : code
}

const applyQuickRange = (range: number | 'today' | 'month') => {
  const end = new Date()
  const start = new Date()
  if (range === 'today') {
    filterForm.value.startDate = end.toISOString().split('T')[0]
    filterForm.value.endDate = end.toISOString().split('T')[0]
  } else if (range === 'month') {
    start.setDate(1)
    filterForm.value.startDate = start.toISOString().split('T')[0]
    filterForm.value.endDate = end.toISOString().split('T')[0]
  } else {
    start.setDate(end.getDate() - range)
    filterForm.value.startDate = start.toISOString().split('T')[0]
    filterForm.value.endDate = end.toISOString().split('T')[0]
  }
  loadStatistics()
}

const loadStatistics = async (showToast = false) => {
  loading.value = true
  try {
    const statsRes = await getStatistics(
      filterForm.value.startDate || undefined,
      filterForm.value.endDate || undefined
    )
    statistics.value = { ...statistics.value, ...statsRes }

    const rateRes = await getSuccessRate(
      filterForm.value.startDate || undefined,
      filterForm.value.endDate || undefined
    )
    successRateData.value = rateRes

    if (showToast) ElMessage.success(t('reports.loadSuccess'))
  } catch (error: any) {
    ElMessage.error(t('reports.loadFailed') + ': ' + (error.message || t('common.unknownError')))
  } finally {
    loading.value = false
  }
}

const loadDailyStats = async () => {
  try {
    const res = await getDailyStats(chartDays.value)
    dailyStatsData.value = res.statistics || []
    updateCharts()
  } catch (error: any) {
    ElMessage.error(t('reports.loadDailyStatsFailed') + ': ' + (error.message || t('common.unknownError')))
  }
}

const initCharts = async () => {
  await nextTick()
  if (trendChartRef.value) trendChart = echarts.init(trendChartRef.value)
  if (successRateChartRef.value) successRateChart = echarts.init(successRateChartRef.value)
  if (costChartRef.value) costChart = echarts.init(costChartRef.value)
  await loadDailyStats()
}

const updateCharts = () => {
  if (!dailyStatsData.value.length) return

  const dates = dailyStatsData.value.map(item => item.date)
  const sentData = dailyStatsData.value.map(item => item.total_sent)
  const deliveredData = dailyStatsData.value.map(item => item.total_delivered)
  const successRateArr = dailyStatsData.value.map(item => item.success_rate)
  const costData = dailyStatsData.value.map(item => item.total_cost)
  const revenueData = dailyStatsData.value.map(item => item.total_revenue ?? item.total_cost)

  if (trendChart) {
    trendChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      legend: { data: [t('reports.sendCount'), t('reports.deliveredCount')] },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', boundaryGap: false, data: dates },
      yAxis: { type: 'value' },
      series: [
        { name: t('reports.sendCount'), type: 'line', smooth: true, data: sentData, itemStyle: { color: '#409eff' } },
        { name: t('reports.deliveredCount'), type: 'line', smooth: true, data: deliveredData, itemStyle: { color: '#67c23a' } }
      ]
    })
  }

  if (successRateChart) {
    successRateChart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', boundaryGap: false, data: dates },
      yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
      series: [{
        name: t('reports.successRate'),
        type: 'line',
        smooth: true,
        data: successRateArr,
        itemStyle: { color: '#e6a23c' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(230,162,60,0.3)' }, { offset: 1, color: 'rgba(230,162,60,0.1)' }] } }
      }]
    })
  }

  if (costChart) {
    costChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: [t('reports.totalCost'), t('reports.totalRevenue')] },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', boundaryGap: false, data: dates },
      yAxis: { type: 'value' },
      series: [
        { name: t('reports.totalCost'), type: 'bar', data: costData, itemStyle: { color: '#f56c6c' } },
        { name: t('reports.totalRevenue'), type: 'bar', data: revenueData, itemStyle: { color: '#67c23a' } }
      ]
    })
  }
}

const handleResize = () => {
  trendChart?.resize()
  successRateChart?.resize()
  costChart?.resize()
}

const exportToExcel = (data: any[], filename: string, sheetName: string) => {
  try {
    const ws = XLSX.utils.json_to_sheet(data)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, sheetName)
    const excelBuffer = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
    const blob = new Blob([excelBuffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${filename}_${new Date().toISOString().split('T')[0]}.xlsx`
    link.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success(t('reports.exportSuccess'))
  } catch (error: any) {
    ElMessage.error(t('reports.exportFailed') + ': ' + (error.message || t('common.unknownError')))
  }
}

const exportChannelData = () => {
  const data = successRateData.value.by_channel.map(item => ({
    [t('reports.channelCode')]: item.channel_code,
    [t('reports.channelName')]: item.channel_name,
    [t('reports.sendCount')]: item.total,
    [t('reports.deliveredCount')]: item.delivered,
    [t('reports.successRatePercent')]: item.success_rate
  }))
  exportToExcel(data, t('reports.channelStats'), t('reports.byChannelStats'))
}

const exportCountryData = () => {
  const data = successRateData.value.by_country.map(item => ({
    [t('reports.countryCode')]: getCountryName(item.country_code),
    [t('reports.sendCount')]: item.total,
    [t('reports.deliveredCount')]: item.delivered,
    [t('reports.successRatePercent')]: item.success_rate
  }))
  exportToExcel(data, t('reports.countryStats'), t('reports.byCountryStats'))
}

const exportDailyStats = () => {
  const data = dailyStatsData.value.map(item => ({
    [t('reports.date')]: item.date,
    [t('reports.sendCount')]: item.total_sent,
    [t('reports.deliveredCount')]: item.total_delivered,
    [t('reports.successRatePercent')]: item.success_rate,
    [t('reports.totalCost')]: item.total_cost,
    [t('reports.totalRevenue')]: item.total_revenue ?? item.total_cost,
    [t('reports.totalProfit')]: (item.total_profit ?? (item.total_revenue ?? item.total_cost) - item.total_cost)
  }))
  exportToExcel(data, t('reports.dailyStats'), t('reports.dailyStats'))
}

const resetFilter = () => {
  filterForm.value.startDate = ''
  filterForm.value.endDate = ''
  applyQuickRange(30)
}

onMounted(async () => {
  const end = new Date()
  const start = new Date()
  start.setDate(end.getDate() - 30)
  filterForm.value.endDate = end.toISOString().split('T')[0]
  filterForm.value.startDate = start.toISOString().split('T')[0]
  await loadStatistics(false)
  await initCharts()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
  successRateChart?.dispose()
  costChart?.dispose()
})
</script>

<style scoped>
.reports { width: 100%; }

.page-header { margin-bottom: 20px; }
.page-header h2 { margin: 0 0 8px 0; font-size: 22px; }
.page-desc { margin: 0; color: var(--text-tertiary); font-size: 14px; }

.filter-card { margin-bottom: 20px; }
.filter-form { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }

.stats-row, .analysis-row, .charts-row, .cost-row { margin-bottom: 20px; }

.stat-card { margin-bottom: 16px; }
.stat-item { display: flex; align-items: center; }
.stat-icon {
  width: 48px; height: 48px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  color: white; margin-right: 12px;
}
.stat-icon.sent { background: linear-gradient(135deg, #409eff, #66b1ff); }
.stat-icon.delivered { background: linear-gradient(135deg, #67c23a, #85ce61); }
.stat-icon.failed { background: linear-gradient(135deg, #f56c6c, #f78989); }
.stat-icon.pending { background: linear-gradient(135deg, #909399, #a6a9ad); }
.stat-icon.rate { background: linear-gradient(135deg, #e6a23c, #ebb563); }
.stat-icon.cost { background: linear-gradient(135deg, #f56c6c, #f78989); }
.stat-icon.revenue { background: linear-gradient(135deg, #67c23a, #85ce61); }
.stat-icon.profit { background: linear-gradient(135deg, #409eff, #66b1ff); }

.stat-content { flex: 1; min-width: 0; }
.stat-label { font-size: 13px; color: var(--text-tertiary); margin-bottom: 4px; }
.stat-value { font-size: 20px; font-weight: 600; color: var(--text-primary); }
.stat-value.negative { color: #f56c6c; }

.card-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.chart-actions { display: flex; gap: 8px; align-items: center; }
.chart-container { width: 100%; height: 380px; }
.chart-container-sm { width: 100%; height: 280px; }

.cost-summary { display: flex; flex-wrap: wrap; gap: 24px; padding: 16px 0; }
.cost-item { display: flex; align-items: center; gap: 8px; }
.cost-label { font-size: 14px; color: var(--text-tertiary); }
.cost-value { font-size: 18px; font-weight: 600; }
.cost-value.revenue { color: #67c23a; }
.cost-value.profit { color: #409eff; }
.cost-value.negative { color: #f56c6c; }
</style>
