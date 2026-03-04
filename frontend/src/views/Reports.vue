<template>
  <div class="reports">
    <h2>{{ $t('reports.title') }}</h2>
    
    <!-- 日期筛选 -->
    <el-card class="filter-card">
      <el-form :inline="true" :model="filterForm">
        <el-form-item :label="$t('reports.startDate')">
          <el-date-picker
            v-model="filterForm.startDate"
            type="date"
            :placeholder="$t('reports.selectStartDate')"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item :label="$t('reports.endDate')">
          <el-date-picker
            v-model="filterForm.endDate"
            type="date"
            :placeholder="$t('reports.selectEndDate')"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadStatistics">{{ $t('smsRecords.query') }}</el-button>
          <el-button @click="resetFilter">{{ $t('common.reset') }}</el-button>
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card>
          <div class="stat-item">
            <div class="stat-icon" style="background-color: #409eff">
              <el-icon size="30"><Document /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-label">{{ $t('reports.totalSent') }}</div>
              <div class="stat-value">{{ statistics.total_sent }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card>
          <div class="stat-item">
            <div class="stat-icon" style="background-color: #67c23a">
              <el-icon size="30"><CircleCheck /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-label">{{ $t('reports.totalDelivered') }}</div>
              <div class="stat-value">{{ statistics.total_delivered }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card>
          <div class="stat-item">
            <div class="stat-icon" style="background-color: #f56c6c">
              <el-icon size="30"><CircleClose /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-label">{{ $t('reports.totalFailed') }}</div>
              <div class="stat-value">{{ statistics.total_failed }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card>
          <div class="stat-item">
            <div class="stat-icon" style="background-color: #e6a23c">
              <el-icon size="30"><TrendCharts /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-label">{{ $t('reports.successRate') }}</div>
              <div class="stat-value">{{ statistics.success_rate }}%</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 成功率分析 -->
    <el-row :gutter="20" class="analysis-row">
      <el-col :span="12">
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
          <el-table :data="successRateData.by_channel" stripe>
            <el-table-column prop="channel_name" :label="$t('reports.channelName')" />
            <el-table-column prop="total" :label="$t('reports.sendCount')" width="100" />
            <el-table-column prop="delivered" :label="$t('reports.deliveredCount')" width="100" />
            <el-table-column prop="success_rate" :label="$t('reports.successRate')" width="120">
              <template #default="{ row }">
                <el-tag :type="row.success_rate >= 95 ? 'success' : row.success_rate >= 90 ? 'warning' : 'danger'">
                  {{ row.success_rate }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      
      <el-col :span="12">
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
          <el-table :data="successRateData.by_country" stripe>
            <el-table-column prop="country_code" :label="$t('reports.countryCode')" width="120" />
            <el-table-column prop="total" :label="$t('reports.sendCount')" width="100" />
            <el-table-column prop="delivered" :label="$t('reports.deliveredCount')" width="100" />
            <el-table-column prop="success_rate" :label="$t('reports.successRate')" width="120">
              <template #default="{ row }">
                <el-tag :type="row.success_rate >= 95 ? 'success' : row.success_rate >= 90 ? 'warning' : 'danger'">
                  {{ row.success_rate }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
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
              <div style="display: flex; gap: 10px; align-items: center">
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
          <div ref="trendChartRef" style="width: 100%; height: 400px;"></div>
        </el-card>
      </el-col>
    </el-row>
    
    <el-row :gutter="20" class="charts-row">
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>{{ $t('reports.successRateTrend') }}</span>
            </div>
          </template>
          <div ref="successRateChartRef" style="width: 100%; height: 300px;"></div>
        </el-card>
      </el-col>
      
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>{{ $t('reports.costTrend') }}</span>
            </div>
          </template>
          <div ref="costChartRef" style="width: 100%; height: 300px;"></div>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 费用统计 -->
    <el-row :gutter="20" class="cost-row">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>{{ $t('reports.costStats') }}</span>
            </div>
          </template>
          <div class="cost-info">
            <div class="cost-item">
              <span class="cost-label">{{ $t('reports.totalCost') }}:</span>
              <span class="cost-value">{{ statistics.total_cost.toFixed(4) }} {{ statistics.currency }}</span>
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
import { Document, CircleCheck, CircleClose, TrendCharts, Download } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import * as XLSX from 'xlsx'
import { getStatistics, getSuccessRate, getDailyStats } from '@/api/reports'

const { t } = useI18n()
const filterForm = ref({
  startDate: '',
  endDate: ''
})

const statistics = ref({
  total_sent: 0,
  total_delivered: 0,
  total_failed: 0,
  success_rate: 0,
  total_cost: 0,
  currency: 'USD'
})

const successRateData = ref({
  overall_rate: 0,
  by_channel: [],
  by_country: []
})

const chartDays = ref(30)
const dailyStatsData = ref<any[]>([])

// 图表引用
const trendChartRef = ref<HTMLElement>()
const successRateChartRef = ref<HTMLElement>()
const costChartRef = ref<HTMLElement>()

// ECharts实例
let trendChart: echarts.ECharts | null = null
let successRateChart: echarts.ECharts | null = null
let costChart: echarts.ECharts | null = null

const loadStatistics = async () => {
  try {
    // 加载统计数据
    const statsRes = await getStatistics(
      filterForm.value.startDate || undefined,
      filterForm.value.endDate || undefined
    )
    statistics.value = statsRes
    
    // 加载成功率分析
    const rateRes = await getSuccessRate(
      filterForm.value.startDate || undefined,
      filterForm.value.endDate || undefined
    )
    successRateData.value = rateRes
    
    ElMessage.success(t('reports.loadSuccess'))
  } catch (error: any) {
    ElMessage.error(t('reports.loadFailed') + ': ' + (error.message || t('common.unknownError')))
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
  
  // 初始化发送趋势图表
  if (trendChartRef.value) {
    trendChart = echarts.init(trendChartRef.value)
  }
  
  // 初始化成功率趋势图表
  if (successRateChartRef.value) {
    successRateChart = echarts.init(successRateChartRef.value)
  }
  
  // 初始化费用趋势图表
  if (costChartRef.value) {
    costChart = echarts.init(costChartRef.value)
  }
  
  // 加载数据并更新图表
  await loadDailyStats()
}

const updateCharts = () => {
  if (!dailyStatsData.value.length) return
  
  const dates = dailyStatsData.value.map(item => item.date)
  const sentData = dailyStatsData.value.map(item => item.total_sent)
  const deliveredData = dailyStatsData.value.map(item => item.total_delivered)
  const successRateData = dailyStatsData.value.map(item => item.success_rate)
  const costData = dailyStatsData.value.map(item => item.total_cost)
  
  // 更新发送趋势图表
  if (trendChart) {
    trendChart.setOption({
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross'
        }
      },
      legend: {
        data: [t('reports.sendCount'), t('reports.deliveredCount')]
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: dates
      },
      yAxis: {
        type: 'value'
      },
      series: [
        {
          name: t('reports.sendCount'),
          type: 'line',
          smooth: true,
          data: sentData,
          itemStyle: { color: '#409eff' }
        },
        {
          name: t('reports.deliveredCount'),
          type: 'line',
          smooth: true,
          data: deliveredData,
          itemStyle: { color: '#67c23a' }
        }
      ]
    })
  }
  
  // 更新成功率趋势图表
  if (successRateChart) {
    successRateChart.setOption({
      tooltip: {
        trigger: 'axis'
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: dates
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 100,
        axisLabel: {
          formatter: '{value}%'
        }
      },
      series: [
        {
          name: t('reports.successRate'),
          type: 'line',
          smooth: true,
          data: successRateData,
          itemStyle: { color: '#e6a23c' },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(230, 162, 60, 0.3)' },
                { offset: 1, color: 'rgba(230, 162, 60, 0.1)' }
              ]
            }
          }
        }
      ]
    })
  }
  
  // 更新费用趋势图表
  if (costChart) {
    costChart.setOption({
      tooltip: {
        trigger: 'axis'
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: dates
      },
      yAxis: {
        type: 'value'
      },
      series: [
        {
          name: t('reports.cost'),
          type: 'bar',
          data: costData,
          itemStyle: { color: '#409eff' }
        }
      ]
    })
  }
}

// 窗口大小改变时重新调整图表
const handleResize = () => {
  trendChart?.resize()
  successRateChart?.resize()
  costChart?.resize()
}

// 导出Excel数据
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
    [t('reports.countryCode')]: item.country_code,
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
    [t('reports.cost')]: item.total_cost
  }))
  exportToExcel(data, t('reports.dailyStats'), t('reports.dailyStats'))
}

const resetFilter = () => {
  filterForm.value.startDate = ''
  filterForm.value.endDate = ''
  loadStatistics()
}

onMounted(async () => {
  // 默认加载最近30天的数据
  const endDate = new Date()
  const startDate = new Date()
  startDate.setDate(endDate.getDate() - 30)
  
  filterForm.value.endDate = endDate.toISOString().split('T')[0]
  filterForm.value.startDate = startDate.toISOString().split('T')[0]
  
  await loadStatistics()
  await initCharts()
  
  // 监听窗口大小变化
  window.addEventListener('resize', handleResize)
})

// 组件卸载时清理
onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
  successRateChart?.dispose()
  costChart?.dispose()
})
</script>

<style scoped>
.reports {
  width: 100%;
}

h2 {
  margin-bottom: 20px;
}

.filter-card {
  margin-bottom: 20px;
}

.stats-row,
.analysis-row,
.charts-row,
.cost-row {
  margin-bottom: 20px;
}

.stat-item {
  display: flex;
  align-items: center;
}

.stat-icon {
  width: 60px;
  height: 60px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  margin-right: 15px;
}

.stat-content {
  flex: 1;
}

.stat-label {
  font-size: 14px;
  color: var(--text-tertiary);
  margin-bottom: 5px;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: var(--text-primary);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.cost-info {
  padding: 20px;
}

.cost-item {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.cost-label {
  font-size: 16px;
  color: var(--text-tertiary);
  margin-right: 10px;
}

.cost-value {
  font-size: 24px;
  font-weight: bold;
  color: #409eff;
}
</style>
