<template>
  <div class="recharge-records-page">
    <div class="page-header">
      <h2>{{ $t('rechargeRecords.title') }}</h2>
      <p class="page-desc">{{ $t('rechargeRecords.pageDesc') }}</p>
    </div>

    <el-card class="filter-card">
      <el-form :inline="true" :model="filters" class="filter-form">
        <el-form-item :label="$t('rechargeRecords.customerAccount')">
          <el-select v-model="filters.account_id" :placeholder="$t('rechargeRecords.allCustomers')" clearable filterable style="width: 180px">
            <el-option v-for="a in accountOptions" :key="a.id" :label="`${a.account_name} (${a.id})`" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('rechargeRecords.sales')">
          <el-select v-model="filters.sales_id" :placeholder="$t('rechargeRecords.allSales')" clearable style="width: 150px">
            <el-option v-for="s in staffOptions" :key="s.id" :label="s.real_name || s.username" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('rechargeRecords.changeType')">
          <el-select v-model="filters.change_type" :placeholder="$t('rechargeRecords.allTypes')" clearable style="width: 130px">
            <el-option :label="$t('rechargeRecords.deposit')" value="deposit" />
            <el-option :label="$t('rechargeRecords.withdraw')" value="withdraw" />
            <el-option :label="$t('rechargeRecords.refundRecharge')" value="refund_recharge" />
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
      <el-table :data="logs" v-loading="loading" class="data-table">
        <el-table-column prop="created_at" :label="$t('rechargeRecords.time')" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="account_name" :label="$t('rechargeRecords.customer')" min-width="120" />
        <el-table-column prop="change_type" :label="$t('rechargeRecords.type')" width="120">
          <template #default="{ row }">
            <el-tag :type="changeTypeTag(row.change_type)" size="small">{{ changeTypeLabel(row.change_type) }}</el-tag>
            <el-tag v-if="row.exclude_performance" type="info" size="small" class="ml-1">{{ $t('rechargeRecords.excludePerformance') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="amount" :label="$t('rechargeRecords.amount')" width="120" align="right">
          <template #default="{ row }">
            <span :class="row.amount >= 0 ? 'text-success' : 'text-danger'">
              {{ row.amount >= 0 ? '+' : '' }}{{ row.amount.toFixed(2) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="balance_after" :label="$t('rechargeRecords.balanceAfter')" width="120" align="right">
          <template #default="{ row }">{{ row.balance_after?.toFixed(2) || '-' }}</template>
        </el-table-column>
        <el-table-column prop="description" :label="$t('rechargeRecords.remark')" min-width="150" show-overflow-tooltip />
      </el-table>
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadData"
        class="mt-16"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search } from '@element-plus/icons-vue'
import { getRechargeLogs, getAccountsAdmin } from '@/api/admin'
import request from '@/api/index'
import { formatDate } from '@/utils/date'
import { ElMessage } from 'element-plus'

const { t } = useI18n()
const loading = ref(false)
const logs = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const accountOptions = ref<any[]>([])
const staffOptions = ref<any[]>([])

const filters = reactive({
  account_id: undefined as number | undefined,
  sales_id: undefined as number | undefined,
  change_type: '',
  start_date: '',
  end_date: ''
})

const changeTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    deposit: t('rechargeRecords.deposit'),
    withdraw: t('rechargeRecords.withdraw'),
    refund_recharge: t('rechargeRecords.refundRecharge')
  }
  return map[type] || type
}

const changeTypeTag = (type: string) => {
  const map: Record<string, string> = {
    deposit: 'success',
    withdraw: 'warning',
    refund_recharge: 'info'
  }
  return map[type] || 'info'
}

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
    const res = await request.get('/admin/users', { params: { include_monthly_stats: false } })
    staffOptions.value = res.users || []
  } catch {
    staffOptions.value = []
  }
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await getRechargeLogs({
      account_id: filters.account_id,
      sales_id: filters.sales_id,
      change_type: filters.change_type || undefined,
      start_date: filters.start_date || undefined,
      end_date: filters.end_date || undefined,
      page: page.value,
      page_size: pageSize.value
    })
    logs.value = res.logs || []
    total.value = res.total || 0
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  filters.account_id = undefined
  filters.sales_id = undefined
  filters.change_type = ''
  filters.start_date = ''
  filters.end_date = ''
  page.value = 1
  loadData()
}

onMounted(() => {
  loadAccounts()
  loadStaff()
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 30)
  filters.start_date = start.toISOString().slice(0, 10)
  filters.end_date = end.toISOString().slice(0, 10)
  loadData()
})
</script>

<style scoped>
.recharge-records-page { padding: 20px; }
.page-header { margin-bottom: 20px; }
.page-header h2 { margin: 0 0 8px 0; font-size: 20px; }
.page-desc { margin: 0; color: var(--text-secondary); font-size: 14px; }
.filter-card { margin-bottom: 16px; }
.filter-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.text-success { color: var(--el-color-success); }
.text-danger { color: var(--el-color-danger); }
.ml-1 { margin-left: 4px; }
.mt-16 { margin-top: 16px; }
</style>
