<template>
  <div class="data-orders-page">
    <div class="page-header">
      <div class="header-left">
        <h1>{{ t('dataPool.ordersTitle') }}</h1>
        <p class="subtitle">{{ t('dataPool.ordersDesc') }}</p>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-select v-model="filters.status" :placeholder="t('dataPool.orderStatus')" clearable @change="loadData">
        <el-option :label="t('dataPool.pending')" value="pending" />
        <el-option :label="t('dataPool.processing')" value="processing" />
        <el-option :label="t('dataPool.completed')" value="completed" />
        <el-option :label="t('dataPool.cancelled')" value="cancelled" />
        <el-option :label="t('dataPool.expired')" value="expired" />
      </el-select>
      <el-input v-model="filters.accountId" :placeholder="t('dataPool.accountIdPlaceholder')" clearable style="width: 150px" @keyup.enter="loadData" />
      <el-button @click="loadData">
        <el-icon><Search /></el-icon>
        {{ t('common.search') }}
      </el-button>
    </div>

    <!-- 订单表格 -->
    <div class="data-table">
      <el-table :data="orders" v-loading="loading" stripe>
        <el-table-column prop="order_no" :label="t('dataPool.orderNo')" min-width="200">
          <template #default="{ row }">
            <span class="order-no">{{ row.order_no }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="account_name" :label="t('dataPool.customer')" width="120" />
        <el-table-column prop="product_name" :label="t('dataPool.product')" min-width="150" />
        <el-table-column :label="t('dataPool.filterCriteria')" min-width="200">
          <template #default="{ row }">
            <el-tooltip :content="JSON.stringify(row.filter_criteria)" placement="top">
              <code class="filter-code">{{ JSON.stringify(row.filter_criteria) }}</code>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="quantity" :label="t('dataPool.quantity')" width="100" align="right">
          <template #default="{ row }">
            {{ row.quantity?.toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column :label="t('dataPool.cost')" width="120" align="right">
          <template #default="{ row }">
            <span class="price">${{ row.total_price }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="t('common.status')" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('dataPool.executionProgress')" width="120">
          <template #default="{ row }">
            <el-progress 
              v-if="row.status === 'processing'"
              :percentage="Math.round((row.executed_count / row.quantity) * 100)" 
              :stroke-width="6"
            />
            <span v-else-if="row.status === 'completed'" class="completed-text">
              {{ row.executed_count }}/{{ row.quantity }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="t('dataPool.createTime')" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import request from '@/api/index'

const { t } = useI18n()

const loading = ref(false)
const orders = ref([])

const filters = ref({
  status: '',
  accountId: ''
})

const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0
})

const loadData = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.value.page,
      page_size: pagination.value.pageSize
    }
    if (filters.value.status) params.status = filters.value.status
    if (filters.value.accountId) params.account_id = filters.value.accountId

    const res = await request.get('/admin/data/orders', { params })
    if (res.success) {
      orders.value = res.items
      pagination.value.total = res.total
    }
  } catch (error) {
    ElMessage.error(t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

const getStatusType = (status) => {
  const types = {
    pending: 'warning',
    processing: 'primary',
    completed: 'success',
    cancelled: 'info',
    expired: 'danger'
  }
  return types[status] || 'info'
}

const getStatusLabel = (status) => {
  const labels = {
    pending: t('dataPool.pending'),
    processing: t('dataPool.processing'),
    completed: t('dataPool.completed'),
    cancelled: t('dataPool.cancelled'),
    expired: t('dataPool.expired')
  }
  return labels[status] || status
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.data-orders-page {
  width: 100%;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 24px;
  font-weight: 600;
  margin: 0;
}

.subtitle {
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  font-size: 14px;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.data-table {
  background: var(--el-bg-color);
  border-radius: 12px;
  border: 1px solid var(--el-border-color-lighter);
  overflow: hidden;
}

.pagination-wrapper {
  padding: 16px;
  display: flex;
  justify-content: flex-end;
}

.order-no {
  font-family: monospace;
  font-size: 12px;
}

.filter-code {
  background: var(--el-fill-color);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
}

.price {
  font-weight: 600;
  color: var(--el-color-success);
}

.completed-text {
  color: var(--el-color-success);
  font-weight: 500;
}
</style>
