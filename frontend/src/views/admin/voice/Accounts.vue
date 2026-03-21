<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">{{ $t('voice.accountsTitle') }}</h1>
        <p class="page-desc">{{ $t('voice.accountsDesc') }}</p>
      </div>
    </div>

    <!-- 筛选 -->
    <div class="filter-card">
      <el-form :inline="true" :model="filters">
        <el-form-item :label="$t('voice.country')">
          <el-input v-model="filters.country_code" :placeholder="$t('voice.countryCode')" clearable style="width: 120px;" />
        </el-form-item>
        <el-form-item :label="$t('common.status')">
          <el-select v-model="filters.status" :placeholder="$t('voice.allStatus')" clearable>
            <el-option :label="$t('voice.active')" value="active" />
            <el-option :label="$t('voice.suspended')" value="suspended" />
            <el-option :label="$t('voice.closed')" value="closed" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">{{ $t('smsRecords.query') }}</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 数据表格 -->
    <div class="table-card">
      <el-table :data="accounts" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column :label="$t('voice.localAccount')" width="150">
          <template #default="{ row }">
            <span>{{ row.account?.account_name || row.account_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="okcc_account" :label="$t('voice.okccAccount')" width="150" />
        <el-table-column prop="country_code" :label="$t('voice.country')" width="80" />
        <el-table-column prop="balance" :label="$t('voice.balance')" width="100">
          <template #default="{ row }">
            ${{ parseFloat(row.balance || 0).toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="total_calls" :label="$t('voice.totalCalls')" width="90" />
        <el-table-column prop="total_minutes" :label="$t('voice.totalMinutes')" width="90" />
        <el-table-column prop="status" :label="$t('common.status')" width="90">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_sync_at" :label="$t('voice.lastSync')" width="160">
          <template #default="{ row }">
            {{ formatDate(row.last_sync_at) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="syncAccount(row)">{{ $t('voice.sync') }}</el-button>
            <el-button 
              size="small" 
              :type="row.status === 'active' ? 'warning' : 'success'"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'active' ? $t('voice.suspend') : $t('voice.resume') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import request from '@/api/index'
import { formatDate } from '@/utils/date'

const { t } = useI18n()

interface VoiceAccount {
  id: number
  account_id: number
  account?: { account_name: string }
  okcc_account: string
  country_code: string
  balance: number
  total_calls: number
  total_minutes: number
  status: string
  last_sync_at?: string
}

const loading = ref(false)
const accounts = ref<VoiceAccount[]>([])

const filters = ref({
  country_code: '',
  status: ''
})

const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0
})

const getStatusType = (status: string) => {
  const map: Record<string, string> = {
    active: 'success',
    suspended: 'warning',
    closed: 'danger'
  }
  return map[status] || 'info'
}

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = {
    active: t('voice.active'),
    suspended: t('voice.suspended'),
    closed: t('voice.closed')
  }
  return map[status] || status
}

const loadData = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (filters.value.country_code) params.append('country_code', filters.value.country_code)
    if (filters.value.status) params.append('status', filters.value.status)
    params.append('page', String(pagination.value.page))
    params.append('page_size', String(pagination.value.pageSize))
    
    const res = await request.get(`/admin/voice/accounts?${params.toString()}`)
    if (res.success) {
      accounts.value = res.items || []
      pagination.value.total = res.total || 0
    }
  } catch (e: any) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    loading.value = false
  }
}

const syncAccount = async (row: VoiceAccount) => {
  try {
    await request.post(`/admin/voice/accounts/${row.id}/sync`)
    ElMessage.success(t('voice.syncRequestSent'))
    loadData()
  } catch (e: any) {
    ElMessage.error(e.message || t('voice.syncFailed'))
  }
}

const toggleStatus = async (row: VoiceAccount) => {
  const newStatus = row.status === 'active' ? 'suspended' : 'active'
  try {
    await request.put(`/admin/voice/accounts/${row.id}`, { status: newStatus })
    ElMessage.success(t('voice.statusUpdated'))
    loadData()
  } catch (e: any) {
    ElMessage.error(e.message || t('common.failed'))
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.page-container {
  width: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.page-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

.filter-card {
  background: var(--bg-card);
  padding: 16px 24px;
  border-radius: 12px;
  border: 1px solid var(--border-default);
  margin-bottom: 24px;
}

.table-card {
  background: var(--bg-card);
  padding: 16px;
  border-radius: 12px;
  border: 1px solid var(--border-default);
}

.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
