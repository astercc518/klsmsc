<template>
  <div class="business-report-container">
    <!-- 顶部标题与背景装饰 -->
    <div class="report-header">
      <div class="header-content">
        <h1 class="page-title text-gradient">{{ $t('reports.title') }}</h1>
        <p class="page-desc">{{ $t('reports.pageDesc') }}</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" plain size="small" @click="fetchData" :loading="loading">
          <el-icon><Refresh /></el-icon> {{ $t('common.refresh') }}
        </el-button>
        <el-button type="success" size="small" @click="exportExcel">
          <el-icon><Download /></el-icon> {{ $t('common.export') }}
        </el-button>
      </div>
    </div>

    <!-- 筛选面板 - Soft UI 风格 -->
    <div class="soft-card filter-panel">
      <div class="filter-header">
        <el-icon class="filter-main-icon"><Search /></el-icon>
        <span>{{ $t('common.filter') }}</span>
      </div>
      
      <div class="filter-content">
        <!-- 聚合维度 - 触感选择器 -->
        <div class="filter-group">
          <label class="filter-label">{{ $t('reports.dimension') }}</label>
          <div class="soft-inset selector-group">
            <button 
              v-for="opt in dimensionOptions" 
              :key="opt.value"
              class="soft-button selector-item"
              :class="{ active: filterForm.dimension === opt.value }"
              @click="handleDimensionChange(opt.value)"
            >
              <el-icon><component :is="opt.icon" /></el-icon>
              <span>{{ opt.label }}</span>
            </button>
          </div>
        </div>
        
        <!-- 业务类型 - 触感切换器 -->
        <div class="filter-group">
          <label class="filter-label">{{ $t('reports.businessType') }}</label>
          <div class="soft-inset selector-group">
            <button 
              v-for="opt in typeOptions" 
              :key="opt.value"
              class="soft-button selector-item"
              :class="{ active: filterForm.businessType === opt.value }"
              @click="handleTypeChange(opt.value)"
            >
              <el-icon><component :is="opt.icon" /></el-icon>
              <span>{{ opt.label }}</span>
            </button>
          </div>
        </div>

        <!-- 时间范围 - 触感排布 -->
        <div class="filter-group">
          <label class="filter-label">{{ $t('reports.timeRange') }}</label>
          <div class="time-range-row">
            <el-select v-model="filterForm.timeRange" @change="handleTimeRangeChange" class="soft-select-refined" style="width: 140px">
              <el-option :label="$t('reports.today')" value="today" />
              <el-option :label="$t('reports.thisWeek')" value="this_week" />
              <el-option :label="$t('reports.thisMonth')" value="this_month" />
              <el-option :label="$t('reports.lastMonth')" value="last_month" />
              <el-option :label="$t('reports.custom')" value="custom" />
            </el-select>

            <transition name="fade-slide">
              <div v-if="filterForm.timeRange === 'custom'" class="custom-date-wrapper">
                <el-date-picker
                  v-model="filterForm.dateRange"
                  type="daterange"
                  range-separator="-"
                  :start-placeholder="$t('reports.startDate')"
                  :end-placeholder="$t('reports.endDate')"
                  value-format="YYYY-MM-DD"
                  @change="fetchData"
                  class="premium-date-picker-mini"
                />
              </div>
            </transition>
          </div>
        </div>
      </div>
    </div>

    <!-- 汇总数据卡片 -->
    <div class="summary-grid">
      <div v-for="(item, index) in summaryStats" :key="index" class="stat-card" :class="item.type">
        <div class="stat-icon">
          <el-icon><component :is="item.icon" /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-label">{{ item.label }}</div>
          <div class="stat-value">{{ item.value }}</div>
          <div class="stat-footer">
            <span class="trend" :class="item.trend > 0 ? 'up' : 'down'">
              {{ item.tag }}
            </span>
            <span class="subtext">{{ item.subValue }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 可视化图表区 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="10">
        <el-card class="chart-card">
          <template #header>
            <div class="card-header">
              <el-icon><PieChart /></el-icon>
              <span>{{ $t('reports.distribution') }} ({{ dimLabel }})</span>
            </div>
          </template>
          <div ref="pieChartRef" class="chart-div"></div>
        </el-card>
      </el-col>
      <el-col :span="14">
        <el-card class="chart-card">
          <template #header>
            <div class="card-header">
              <el-icon><TrendCharts /></el-icon>
              <span>{{ $t('reports.trend') }} ({{ $t('reports.revenue') }} / {{ $t('reports.profit') }})</span>
            </div>
          </template>
          <div ref="barChartRef" class="chart-div"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 详细数据表格 -->
    <el-card class="data-card">
      <template #header>
        <div class="card-header">
          <el-icon><List /></el-icon>
          <span>{{ $t('reports.dataDetails') }}</span>
        </div>
      </template>
      <el-table 
        :data="tableData" 
        v-loading="loading" 
        style="width: 100%"
        :header-cell-style="{ background: 'var(--bg-lighter)', color: 'var(--text-secondary)' }"
      >
        <el-table-column :label="dimLabel" prop="dim_name" min-width="180">
          <template #default="{ row }">
            <div class="dim-identifier">
              <span v-if="filterForm.dimension === 'country'" class="country-cell">
                {{ getCountryName(row.dim_id) }}
              </span>
              <span v-else class="name-cell">{{ row.dim_name || 'Unknown' }}</span>
              <span class="id-tag" v-if="row.dim_id && filterForm.dimension !== 'country'">ID: {{ row.dim_id }}</span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column :label="$t('reports.businessType')" width="110">
          <template #default="{ row }">
            <el-tag :type="row.business_type === 'sms' ? 'primary' : 'warning'" effect="light" size="small">
              {{ row.business_type.toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column :label="$t('reports.sendCount')" prop="count" width="120" align="right" sortable />
        
        <el-table-column :label="$t('reports.successRate')" width="110" align="right" sortable>
          <template #default="{ row }">
            <div class="rate-indicator">
              <span :class="getRateClass(row.success_rate)">{{ row.success_rate }}%</span>
              <el-progress 
                :percentage="row.success_rate" 
                :status="getRateStatus(row.success_rate)" 
                :show-text="false" 
                :stroke-width="3"
                style="width: 40px; margin-top: 4px"
              />
            </div>
          </template>
        </el-table-column>

        <el-table-column :label="$t('reports.revenue')" width="140" align="right" sortable>
          <template #default="{ row }">
            <span class="currency-text revenue">${{ row.revenue.toFixed(4) }}</span>
          </template>
        </el-table-column>

        <el-table-column :label="$t('reports.cost')" width="140" align="right" sortable>
          <template #default="{ row }">
            <span class="currency-text cost">${{ row.cost.toFixed(4) }}</span>
          </template>
        </el-table-column>

        <el-table-column :label="$t('reports.profit')" width="140" align="right" sortable>
          <template #default="{ row }">
            <span class="currency-text profit" :class="{ negative: row.profit < 0 }">
              ${{ row.profit.toFixed(4) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { 
  Refresh, Download, Search, User, UserFilled, Shop, Connection, Location, 
  PieChart, TrendCharts, List, Money, Wallet, Checked, ChatDotRound, Coin, Grid
} from '@element-plus/icons-vue'
const ProfitIcon = TrendCharts
import { getBusinessReport } from '@/api/reports'
import { findCountryByIso } from '@/constants/countries'
import { ElMessage } from 'element-plus'
import * as XLSX from 'xlsx'
import * as echarts from 'echarts'

const { t } = useI18n()
const loading = ref(false)
const tableData = ref<any[]>([])

const pieChartRef = ref<HTMLElement | null>(null)
const barChartRef = ref<HTMLElement | null>(null)
let pieChart: echarts.ECharts | null = null
let barChart: echarts.ECharts | null = null

const filterForm = ref({
  dimension: 'customer',
  businessType: 'all',
  timeRange: 'today',
  dateRange: [] as string[]
})

const dimensionOptions = computed(() => [
  { label: t('reports.dimCustomer'), value: 'customer', icon: User },
  { label: t('reports.dimEmployee'), value: 'employee', icon: UserFilled },
  { label: t('reports.dimSupplier'), value: 'supplier', icon: Shop },
  { label: t('reports.dimChannel'), value: 'channel', icon: Connection },
  { label: t('reports.dimCountry'), value: 'country', icon: Location }
])

const typeOptions = computed(() => [
  { label: t('common.all'), value: 'all', icon: PieChart },
  { label: 'SMS', value: 'sms', icon: ChatDotRound },
  { label: 'Data', value: 'data', icon: Coin }
])

const handleDimensionChange = (val: string) => {
  filterForm.value.dimension = val
  fetchData()
}

const handleTypeChange = (val: string) => {
  filterForm.value.businessType = val
  fetchData()
}

const dimLabel = computed(() => {
  const map: any = {
    customer: t('reports.dimCustomer'),
    employee: t('reports.dimEmployee'),
    supplier: t('reports.dimSupplier'),
    channel: t('reports.dimChannel'),
    country: t('reports.dimCountry')
  }
  return map[filterForm.value.dimension]
})

const summaryStats = computed(() => {
  const totalCount = tableData.value.reduce((acc, cur) => acc + cur.count, 0)
  const totalRevenue = tableData.value.reduce((acc, cur) => acc + cur.revenue, 0)
  const totalProfit = tableData.value.reduce((acc, cur) => acc + cur.profit, 0)
  const avgRate = tableData.value.length > 0 
    ? (tableData.value.reduce((acc, cur) => acc + cur.success_rate, 0) / tableData.value.length)
    : 0

  return [
    { 
      label: t('reports.count'), 
      value: totalCount.toLocaleString(), 
      icon: Money, 
      type: 'primary', 
      tag: 'VOLUME', 
      trend: 1, 
      subValue: `${tableData.value.length} ${t('reports.dimension')}` 
    },
    { 
      label: t('reports.totalRevenue'), 
      value: `$${totalRevenue.toFixed(2)}`, 
      icon: Wallet, 
      type: 'success', 
      tag: 'REVENUE', 
      trend: 1, 
      subValue: totalCount > 0 ? `$${(totalRevenue / totalCount).toFixed(4)} / unit` : '-' 
    },
    { 
      label: t('reports.totalProfit'), 
      value: `$${totalProfit.toFixed(2)}`, 
      icon: ProfitIcon, 
      type: 'warning', 
      tag: 'PROFIT', 
      trend: totalProfit > 0 ? 1 : -1, 
      subValue: totalRevenue > 0 ? `${(totalProfit / totalRevenue * 100).toFixed(1)}% margin` : '-' 
    },
    { 
      label: t('reports.successRate'), 
      value: `${avgRate.toFixed(2)}%`, 
      icon: Checked, 
      type: 'info', 
      tag: 'HEALTH', 
      trend: avgRate > 80 ? 1 : -1, 
      subValue: avgRate > 80 ? 'Good' : 'Needs Attention' 
    }
  ]
})

const handleTimeRangeChange = () => {
  if (filterForm.value.timeRange !== 'custom') {
    fetchData()
  }
}

const fetchData = async () => {
  loading.value = true
  try {
    const params: any = {
      dimension: filterForm.value.dimension,
      business_type: filterForm.value.businessType,
      time_range: filterForm.value.timeRange
    }
    if (filterForm.value.timeRange === 'custom' && filterForm.value.dateRange.length === 2) {
      params.start_date = filterForm.value.dateRange[0]
      params.end_date = filterForm.value.dateRange[1]
    }
    
    const res = await getBusinessReport(params)
    if (res.success) {
      tableData.value = res.data
      nextTick(() => {
        updateCharts()
      })
    }
  } catch (error: any) {
    ElMessage.error(error.message || 'Error')
  } finally {
    loading.value = false
  }
}

const updateCharts = () => {
  if (!pieChartRef.value || !barChartRef.value) return

  if (!pieChart) pieChart = echarts.init(pieChartRef.value)
  if (!barChart) barChart = echarts.init(barChartRef.value)

  // 1. Pie Chart: Revenue Distribution
  const pieData = tableData.value
    .map(d => ({ name: d.dim_name || 'Unknown', value: d.revenue }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8) // Top 8

  pieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: ${c} ({d}%)' },
    legend: { bottom: '0', icon: 'circle', itemWidth: 10 },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: '14', fontWeight: 'bold' } },
      data: pieData
    }]
  })

  // 2. Bar Chart: Revenue vs Profit comparison
  const barCategories = tableData.value.map(d => d.dim_name || 'Unknown').slice(0, 10)
  const revenueData = tableData.value.map(d => d.revenue).slice(0, 10)
  const profitData = tableData.value.map(d => d.profit).slice(0, 10)

  barChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: '0' },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: barCategories, axisLabel: { interval: 0, rotate: 30 } },
    yAxis: { type: 'value' },
    series: [
      { 
        name: t('reports.revenue'), 
        type: 'bar', 
        data: revenueData, 
        itemStyle: { 
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#3b82f6' },
            { offset: 1, color: '#2563eb' }
          ]),
          borderRadius: [4, 4, 0, 0]
        } 
      },
      { 
        name: t('reports.profit'), 
        type: 'bar', 
        data: profitData, 
        itemStyle: { 
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#2dd4bf' },
            { offset: 1, color: '#0d9488' }
          ]),
          borderRadius: [4, 4, 0, 0]
        } 
      }
    ]
  })
}

const getCountryName = (code: string) => {
  if (!code || code === 'Unknown') return 'Unknown'
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

const exportExcel = () => {
  const exportData = tableData.value.map(row => ({
    [dimLabel.value]: row.dim_name,
    'Type': row.business_type,
    'Count': row.count,
    'Delivered': row.delivered,
    'Success %': `${row.success_rate}%`,
    'Revenue (USD)': row.revenue,
    'Cost (USD)': row.cost,
    'Profit (USD)': row.profit
  }))
  
  const ws = XLSX.utils.json_to_sheet(exportData)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'Report')
  XLSX.writeFile(wb, `BusinessReport_${new Date().getTime()}.xlsx`)
}

// Window resize handler
const handleResize = () => {
  pieChart?.resize()
  barChart?.resize()
}

onMounted(() => {
  fetchData()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  pieChart?.dispose()
  barChart?.dispose()
})
</script>

<style scoped>
.business-report-container {
  padding: 24px;
  background: var(--bg-body);
  min-height: 100%;
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 28px;
}

.page-title {
  font-size: 26px;
  font-weight: 800;
  margin: 0;
  letter-spacing: -0.02em;
}

.page-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 6px 0 0;
}

.header-actions {
  display: flex;
  gap: 12px;
}

/* Filter Panel Optimization */
.filter-panel {
  padding: 24px;
  margin-bottom: 30px;
}

.filter-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 15px;
}

.filter-main-icon {
  color: var(--primary);
  font-size: 18px;
}

.filter-content {
  display: flex;
  flex-wrap: wrap;
  gap: 32px;
  align-items: flex-start;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.filter-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding-left: 4px;
}

.selector-group {
  display: flex;
  padding: 4px;
  gap: 4px;
}

.selector-item {
  height: 36px;
  padding: 0 16px;
  font-size: 13px;
  gap: 8px;
  border-radius: 10px;
}

.selector-item el-icon {
  font-size: 16px;
}

.time-range-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.custom-date-wrapper {
  animation: slideInRight 0.3s var(--ease-soft);
}

@keyframes slideInRight {
  from { opacity: 0; transform: translateX(10px); }
  to { opacity: 1; transform: translateX(0); }
}

/* Summary Grid */
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-bottom: 30px;
}

.stat-card {
  background: var(--bg-secondary);
  border-radius: 20px;
  padding: 24px;
  display: flex;
  align-items: center;
  gap: 20px;
  transition: all 0.3s var(--ease-soft);
  border: 1px solid rgba(255, 255, 255, 0.03);
  box-shadow: var(--shadow-soft-out);
}

.stat-card:hover {
  transform: translateY(-8px);
  background: var(--bg-tertiary);
  border-color: rgba(59, 130, 246, 0.3);
  box-shadow: 16px 24px 40px rgba(0,0,0,0.4);
}

.stat-icon {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
}

.stat-card.primary .stat-icon { background: rgba(59, 130, 246, 0.15); color: #3b82f6; }
.stat-card.success .stat-icon { background: rgba(45, 212, 191, 0.15); color: #2dd4bf; }
.stat-card.warning .stat-icon { background: rgba(251, 191, 36, 0.15); color: #fbbf24; }
.stat-card.info .stat-icon { background: rgba(148, 163, 184, 0.15); color: #94a3b8; }

.stat-info { flex: 1; }
.stat-label { font-size: 13px; color: var(--text-tertiary); margin-bottom: 6px; }
.stat-value { font-size: 24px; font-weight: 800; color: var(--text-primary); margin-bottom: 4px; }
.stat-footer { display: flex; align-items: center; gap: 8px; font-size: 12px; }

.trend { font-weight: 700; padding: 2px 8px; border-radius: 6px; font-size: 11px; }
.trend.up { background: rgba(52, 199, 89, 0.15); color: #34C759; }
.trend.down { background: rgba(255, 59, 48, 0.15); color: #FF3B30; }
.subtext { color: var(--text-quaternary); }

/* Charts */
.chart-row { margin-bottom: 24px; }
.chart-card { border-radius: 20px; overflow: hidden; height: 400px; box-shadow: var(--shadow-sm); }
.chart-div { height: 320px; width: 100%; }

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  font-size: 15px;
}

/* Table Refinement */
.data-card {
  border-radius: 20px;
  box-shadow: var(--shadow-sm);
}

.dim-identifier { display: flex; flex-direction: column; }
.name-cell { font-weight: 700; color: var(--text-primary); font-size: 14px; }
.id-tag { font-size: 11px; color: var(--text-quaternary); margin-top: 2px; }

.currency-text { font-family: 'Inter', monospace; font-weight: 700; font-size: 14px; }
.revenue { color: #3b82f6; }
.cost { color: var(--text-tertiary); font-weight: 500; }
.profit { color: #2dd4bf; }
.profit.negative { color: #f87171; }

.rate-indicator { display: flex; flex-direction: column; align-items: flex-end; }
.text-success { color: #34C759; font-weight: 700; }
.text-warning { color: #FF9500; font-weight: 700; }
.text-danger { color: #FF3B30; font-weight: 700; }

.premium-date-picker-mini :deep(.el-input__wrapper) {
  height: 36px;
  padding: 0 10px;
  background: var(--bg-input) !important;
  box-shadow: inset 0 0 0 1px var(--border-default) !important;
}

.soft-select-refined :deep(.el-input__wrapper) {
  height: 36px;
  border-radius: 10px;
  background: var(--bg-input) !important;
  box-shadow: inset 0 0 0 1px var(--border-default) !important;
}

@media (max-width: 1400px) {
  .filter-content { gap: 20px; }
}

@media (max-width: 1200px) {
  .summary-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 900px) {
  .filter-content { flex-direction: column; gap: 24px; }
  .selector-group { width: 100%; overflow-x: auto; }
}

@media (max-width: 600px) {
  .summary-grid { grid-template-columns: 1fr; }
  .report-header { flex-direction: column; align-items: flex-start; gap: 16px; }
}
</style>
