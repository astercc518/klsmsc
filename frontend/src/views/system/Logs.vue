<template>
  <div class="system-logs">
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="24" :sm="12">
        <el-card shadow="hover" class="stat-card stat-total">
          <el-statistic :title="$t('system.logs.total')" :value="stats.total" />
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12">
        <el-card shadow="hover" class="stat-card stat-today">
          <el-statistic :title="$t('system.logs.today')" :value="stats.today" />
        </el-card>
      </el-col>
    </el-row>
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" class="filter-form">
        <el-form-item :label="$t('system.logs.module')">
          <el-select v-model="filters.module" clearable :placeholder="$t('systemConfig.all')" style="width: 140px" @change="loadData">
            <el-option v-for="(label, key) in modules" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('system.logs.adminName')">
          <el-input v-model="filters.admin_name" :placeholder="$t('system.logs.adminNamePlaceholder')" clearable style="width: 120px" @keyup.enter="loadData" />
        </el-form-item>
        <el-form-item :label="$t('system.logs.keyword')">
          <el-input v-model="filters.keyword" :placeholder="$t('system.logs.keywordPlaceholder')" clearable style="width: 160px" @keyup.enter="loadData" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">{{ $t('smsRecords.query') }}</el-button>
          <el-button @click="resetFilters">{{ $t('common.reset') }}</el-button>
        </el-form-item>
      </el-form>
    </el-card>
    <el-card shadow="never" class="table-card">
      <el-table :data="items" v-loading="loading" stripe style="width: 100%" max-height="480">
        <el-table-column prop="created_at" :label="$t('system.logs.time')" width="170" />
        <el-table-column prop="module_label" :label="$t('system.logs.module')" width="100" />
        <el-table-column prop="admin_name" :label="$t('system.logs.operator')" width="100" />
        <el-table-column prop="action" :label="$t('system.logs.action')" width="80" />
        <el-table-column prop="title" :label="$t('system.logs.title')" min-width="180" show-overflow-tooltip />
        <el-table-column prop="detail" :label="$t('system.logs.detail')" min-width="200" show-overflow-tooltip />
        <el-table-column prop="ip_address" :label="$t('system.logs.ip')" width="120" />
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadData"
          @size-change="loadData"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { getSystemLogs, getSystemLogModules, getSystemLogStats } from '@/api/system'

const loading = ref(false)
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const modules = ref<Record<string, string>>({})
const stats = reactive({ total: 0, today: 0 })

const filters = reactive({
  module: '',
  admin_name: '',
  keyword: ''
})

const loadData = async () => {
  loading.value = true
  try {
    const res = await getSystemLogs({
      page: page.value,
      page_size: pageSize.value,
      module: filters.module || undefined,
      admin_name: filters.admin_name || undefined,
      keyword: filters.keyword || undefined
    })
    items.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  filters.module = ''
  filters.admin_name = ''
  filters.keyword = ''
  page.value = 1
  loadData()
}

onMounted(async () => {
  const [modRes, statsRes] = await Promise.all([
    getSystemLogModules(),
    getSystemLogStats()
  ])
  modules.value = modRes.modules
  stats.total = statsRes.total
  stats.today = statsRes.today
  loadData()
})
</script>

<style scoped>
.system-logs { padding: 0; }
.stats-row { margin-bottom: 20px; }
.stat-card { margin-bottom: 0; }
.stat-card :deep(.el-card__body) { padding: 20px; }
.filter-card { margin-bottom: 16px; }
.filter-card :deep(.el-card__body) { padding: 16px 20px; }
.filter-form { margin-bottom: 0; }
.table-card :deep(.el-card__body) { padding: 16px 20px; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
