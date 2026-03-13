<template>
  <div class="send-stats-page">
    <div class="page-header">
      <h2>{{ $t('sendStats.title') }}</h2>
      <p class="page-desc">{{ $t('sendStats.pageDesc') }}</p>
    </div>

    <el-card class="filter-card">
      <el-form :inline="true" :model="filters" class="filter-form">
        <el-form-item :label="$t('sendStats.customerAccount')">
          <el-select v-model="filters.account_id" :placeholder="$t('sendStats.allCustomers')" clearable filterable style="width: 180px">
            <el-option v-for="a in accountOptions" :key="a.id" :label="`${a.account_name} (${a.id})`" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('sendStats.sales')">
          <el-select v-model="filters.sales_id" :placeholder="$t('sendStats.allSales')" clearable style="width: 150px">
            <el-option v-for="s in staffOptions" :key="s.id" :label="s.real_name || s.username" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('sendStats.channel')">
          <el-select v-model="filters.channel_id" :placeholder="$t('sendStats.allChannels')" clearable style="width: 180px">
            <el-option v-for="c in channelOptions" :key="c.id" :label="c.channel_name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('sendStats.reportType')">
          <el-select v-model="filters.report_type" style="width: 120px">
            <el-option :label="$t('sendStats.dailyReport')" value="day" />
            <el-option :label="$t('sendStats.weeklyReport')" value="week" />
            <el-option :label="$t('sendStats.monthlyReport')" value="month" />
            <el-option :label="$t('sendStats.quarterlyReport')" value="quarter" />
            <el-option :label="$t('sendStats.yearlyReport')" value="year" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('reports.startDate')">
          <el-date-picker v-model="filters.start_date" type="date" value-format="YYYY-MM-DD" clearable style="width: 140px" />
        </el-form-item>
        <el-form-item :label="$t('reports.endDate')">
          <el-date-picker v-model="filters.end_date" type="date" value-format="YYYY-MM-DD" clearable style="width: 140px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="loadData">
            <el-icon><Search /></el-icon>
            {{ $t('smsRecords.query') }}
          </el-button>
          <el-button @click="resetFilters">{{ $t('common.reset') }}</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card>
      <el-table :data="items" v-loading="loading" class="data-table">
        <el-table-column prop="account_id" :label="$t('sendStats.customer')" min-width="120">
          <template #default="{ row }">
            {{ row.account_name }} ({{ row.account_id }})
          </template>
        </el-table-column>
        <el-table-column prop="avg_unit_price" :label="$t('sendStats.unitPrice')" width="100" align="right">
          <template #default="{ row }">{{ row.avg_unit_price?.toFixed(4) || '-' }}</template>
        </el-table-column>
        <el-table-column prop="submit_total" :label="$t('sendStats.submitTotal')" width="100" align="right" />
        <el-table-column prop="success_count" :label="$t('sendStats.successCount')" width="100" align="right" />
        <el-table-column prop="success_rate" :label="$t('sendStats.successRate')" width="100" align="right">
          <template #default="{ row }">{{ row.success_rate }}%</template>
        </el-table-column>
        <el-table-column prop="total_cost" :label="$t('sendStats.totalCost')" width="100" align="right">
          <template #default="{ row }">{{ row.total_cost?.toFixed(2) || '-' }}</template>
        </el-table-column>
        <el-table-column prop="total_revenue" :label="$t('sendStats.totalRevenue')" width="100" align="right">
          <template #default="{ row }">{{ row.total_revenue?.toFixed(2) || '-' }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search } from '@element-plus/icons-vue'
import { getSendStatistics, getAccountsAdmin, getChannelsAdmin } from '@/api/admin'
import request from '@/api/index'
import { ElMessage } from 'element-plus'

const { t } = useI18n()
const loading = ref(false)
const items = ref<any[]>([])
const accountOptions = ref<any[]>([])
const staffOptions = ref<any[]>([])
const channelOptions = ref<any[]>([])

const filters = reactive({
  account_id: undefined as number | undefined,
  sales_id: undefined as number | undefined,
  channel_id: undefined as number | undefined,
  report_type: 'day',
  start_date: '',
  end_date: ''
})

const loadAccounts = async () => {
  try {
    const res = await getAccountsAdmin({ limit: 500, offset: 0 })
    accountOptions.value = res.accounts || []
  } catch {
    accountOptions.value = []
  }
}

const loadStaff = async () => {
  try {
    const res = await request.get('/admin/users')
    staffOptions.value = res.users || []
  } catch {
    staffOptions.value = []
  }
}

const loadChannels = async () => {
  try {
    const res = await getChannelsAdmin()
    channelOptions.value = res.channels || []
  } catch {
    channelOptions.value = []
  }
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await getSendStatistics({
      account_id: filters.account_id,
      sales_id: filters.sales_id,
      channel_id: filters.channel_id,
      report_type: filters.report_type,
      start_date: filters.start_date || undefined,
      end_date: filters.end_date || undefined
    })
    items.value = res.items || []
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  filters.account_id = undefined
  filters.sales_id = undefined
  filters.channel_id = undefined
  filters.report_type = 'day'
  filters.start_date = ''
  filters.end_date = ''
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 30)
  filters.start_date = start.toISOString().slice(0, 10)
  filters.end_date = end.toISOString().slice(0, 10)
  loadData()
}

onMounted(() => {
  loadAccounts()
  loadStaff()
  loadChannels()
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 30)
  filters.start_date = start.toISOString().slice(0, 10)
  filters.end_date = end.toISOString().slice(0, 10)
  loadData()
})
</script>

<style scoped>
.send-stats-page { padding: 20px; }
.page-header { margin-bottom: 20px; }
.page-header h2 { margin: 0 0 8px 0; font-size: 20px; }
.page-desc { margin: 0; color: var(--text-secondary); font-size: 14px; }
.filter-card { margin-bottom: 16px; }
.filter-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
</style>
