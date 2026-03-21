<template>
  <div class="system-security">
    <p class="sec-desc">{{ $t('system.security.desc') }}</p>
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" class="filter-form">
        <el-form-item :label="$t('system.logs.module')">
          <el-select v-model="filters.module" clearable :placeholder="$t('systemConfig.all')" style="width: 140px" @change="loadData">
            <el-option :label="$t('system.security.moduleLogin')" value="login" />
            <el-option :label="$t('system.security.moduleSecurity')" value="security" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">{{ $t('smsRecords.query') }}</el-button>
          <el-button @click="resetFilters">{{ $t('common.reset') }}</el-button>
        </el-form-item>
      </el-form>
    </el-card>
    <el-card shadow="never" class="table-card">
    <el-table :data="items" v-loading="loading" stripe style="width: 100%" max-height="420">
      <el-table-column prop="created_at" :label="$t('system.logs.time')" width="170" />
      <el-table-column prop="admin_name" :label="$t('system.logs.operator')" width="100" />
      <el-table-column prop="action" :label="$t('system.logs.action')" width="80" />
      <el-table-column prop="title" :label="$t('system.logs.title')" min-width="180" show-overflow-tooltip />
      <el-table-column prop="detail" :label="$t('system.logs.detail')" min-width="200" show-overflow-tooltip />
      <el-table-column prop="ip_address" :label="$t('system.logs.ip')" width="120" />
      <el-table-column prop="status" :label="$t('system.security.result')" width="90">
        <template #default="scope">
          <el-tag :type="scope.row.status === 'success' ? 'success' : (scope.row.status === 'failed' ? 'danger' : 'info')" size="small">
            {{ scope.row.status === 'success' ? $t('system.security.success') : (scope.row.status === 'failed' ? $t('system.security.failed') : scope.row.status) }}
          </el-tag>
        </template>
      </el-table-column>
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
import { getSystemLogs } from '@/api/system'

const loading = ref(false)
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const filters = reactive({
  module: 'login'
})

const loadData = async () => {
  loading.value = true
  try {
    const res = await getSystemLogs({
      page: page.value,
      page_size: pageSize.value,
      module: filters.module || undefined
    })
    items.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  filters.module = 'login'
  page.value = 1
  loadData()
}

onMounted(loadData)
</script>

<style scoped>
.system-security { padding: 0; }
.sec-desc { color: var(--el-text-color-secondary); font-size: 14px; margin-bottom: 16px; line-height: 1.5; }
.filter-card { margin-bottom: 16px; }
.filter-card :deep(.el-card__body) { padding: 16px 20px; }
.filter-form { margin-bottom: 0; }
.table-card :deep(.el-card__body) { padding: 16px 20px; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
