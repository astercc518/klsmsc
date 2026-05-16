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
      <!-- 移动端：卡片列表 -->
      <div v-if="isMobile" class="rec-card-list" v-loading="loading">
        <div
          v-for="row in logs"
          :key="row.id || row.created_at"
          class="rec-card"
          :class="row.amount >= 0 ? 'positive' : 'negative'"
        >
          <div class="rec-row rec-row-top">
            <el-tag :type="changeTypeTag(row.change_type)" size="small">{{ changeTypeLabel(row.change_type) }}</el-tag>
            <span class="rec-amount" :class="row.amount >= 0 ? 'text-success' : 'text-danger'">
              {{ row.amount >= 0 ? '+' : '' }}{{ row.amount.toFixed(2) }}
            </span>
          </div>
          <div class="rec-customer" v-if="row.account_name">{{ row.account_name }}</div>
          <div class="rec-row rec-row-meta">
            <span class="rec-time">{{ formatDate(row.created_at) }}</span>
            <span class="rec-balance" v-if="row.balance_after != null">
              {{ $t('rechargeRecords.balanceAfter') }}: {{ row.balance_after.toFixed(2) }}
            </span>
          </div>
          <div class="rec-remark" v-if="row.description">{{ row.description }}</div>
          <el-tag v-if="row.exclude_performance" type="info" size="small">{{ $t('rechargeRecords.excludePerformance') }}</el-tag>
        </div>
        <el-empty v-if="!logs.length && !loading" :image-size="60" />
      </div>

      <!-- 桌面端：表格 -->
      <el-table v-else :data="logs" v-loading="loading" class="data-table">
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
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useFilterPersist } from '@/composables/useFilterPersist'

const { isMobile } = useBreakpoint()

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

// 持久化筛选条件（按账号隔离）；放在 onMounted 之前以便恢复值优先于默认值
useFilterPersist(`recharge-records:${localStorage.getItem('account_id') || 'anon'}`, { filters })

onMounted(() => {
  loadAccounts()
  loadStaff()
  // 仅在恢复值为空时填默认 30 天窗口
  if (!filters.start_date || !filters.end_date) {
    const end = new Date()
    const start = new Date()
    start.setDate(start.getDate() - 30)
    filters.start_date = start.toISOString().slice(0, 10)
    filters.end_date = end.toISOString().slice(0, 10)
  }
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

/* 移动端卡片列表 */
.rec-card-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 160px;
}
.rec-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  background: var(--bg-secondary, #fff);
  border: 1px solid var(--border-default, rgba(0,0,0,0.08));
  border-left: 3px solid var(--border-default, rgba(0,0,0,0.12));
  border-radius: 10px;
}
.rec-card.positive { border-left-color: var(--el-color-success, #67c23a); }
.rec-card.negative { border-left-color: var(--el-color-warning, #e6a23c); }
.rec-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.rec-amount {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 18px;
  font-weight: 700;
}
.rec-customer {
  font-size: 13px;
  color: var(--text-primary, #0a1425);
  font-weight: 500;
}
.rec-row-meta {
  font-size: 12px;
  color: var(--text-tertiary, #8a96a6);
}
.rec-time { font-variant-numeric: tabular-nums; }
.rec-balance { font-family: 'SF Mono', 'Consolas', monospace; }
.rec-remark {
  font-size: 12px;
  color: var(--text-secondary, #5f6c7c);
  background: var(--bg-input, rgba(0,0,0,0.03));
  padding: 6px 8px;
  border-radius: 6px;
  line-height: 1.4;
  word-break: break-word;
}

@media (max-width: 768px) {
  .recharge-records-page { padding: 12px; }
  .filter-form :deep(.el-form-item) {
    width: 100%;
    margin-right: 0 !important;
  }
  .filter-form :deep(.el-select),
  .filter-form :deep(.el-date-editor) {
    width: 100% !important;
  }
}
</style>
