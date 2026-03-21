<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">{{ t('dataPool.ordersTitle') }}</h2>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="8">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ stats.total_orders ?? '-' }}</div>
          <div class="stat-label">{{ t('dataPool.totalOrders') }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value stat-success">{{ stats.completed_orders ?? '-' }}</div>
          <div class="stat-label">{{ t('dataPool.completedOrders') }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value stat-primary">{{ stats.total_quantity ?? '-' }}</div>
          <div class="stat-label">{{ t('dataPool.totalQuantity') }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 筛选栏 -->
    <div class="filter-card">
      <el-form :inline="true" :model="filters">
        <el-form-item :label="t('dataPool.customerId')">
          <el-input
            v-model="filters.account_id"
            :placeholder="t('dataPool.customerId')"
            clearable
            style="width: 120px;"
          />
        </el-form-item>
        <el-form-item :label="t('common.status')">
          <el-select v-model="filters.status" :placeholder="t('dataPool.allStatus')" clearable>
            <el-option :label="t('dataPool.processing')" value="pending" />
            <el-option :label="t('dataPool.completed')" value="completed" />
            <el-option :label="t('dataPool.cancelled')" value="cancelled" />
            <el-option :label="t('dataPool.expired')" value="expired" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('dataPool.orderType')">
          <el-select v-model="filters.order_type" :placeholder="t('dataPool.allTypes')" clearable>
            <el-option :label="t('dataPool.orderTypeDataOnly')" value="data_only" />
            <el-option :label="t('dataPool.orderTypeCombo')" value="combo" />
            <el-option :label="t('dataPool.orderTypeDataAndSend')" value="data_and_send" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleQuery">{{ t('smsRecords.query') }}</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 订单列表 -->
    <div class="table-card">
      <el-table :data="orders" v-loading="loading" stripe>
        <el-table-column prop="order_no" :label="t('dataPool.orderNo')" width="180">
          <template #default="{ row }">
            <span class="text-mono">{{ row.order_no }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('dataPool.customer')" width="150">
          <template #default="{ row }">
            <div>{{ row.account_name || t('dataPool.unknown') }}</div>
            <div class="text-sub">ID: {{ row.account_id }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="product_name" :label="t('dataPool.productFilter')" min-width="140" />
        <el-table-column :label="t('dataPool.orderType')" width="110">
          <template #default="{ row }">
            <el-tag :type="orderTypeTagType(row.order_type)" size="small">
              {{ orderTypeLabel(row.order_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="quantity" :label="t('dataPool.quantity')" width="80" />
        <el-table-column prop="unit_price" :label="t('dataPool.unitPrice')" width="90" />
        <el-table-column :label="t('dataPool.totalPrice')" width="100">
          <template #default="{ row }">
            <span class="font-bold">{{ row.total_price }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.status')" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="cancel_reason" :label="t('dataPool.cancelReason')" width="120" show-overflow-tooltip />
        <el-table-column :label="t('dataPool.refundAmount')" width="100">
          <template #default="{ row }">
            <span v-if="row.refund_amount">{{ row.refund_amount }}</span>
            <span v-else class="text-sub">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('dataPool.orderTime')" width="160">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column :label="t('dataPool.executedAt')" width="160">
          <template #default="{ row }">
            {{ row.executed_at ? formatDate(row.executed_at) : '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="t('common.action')" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewDetail(row)">
              {{ t('dataPool.detail') }}
            </el-button>
            <el-button
              v-if="row.status === 'pending' || row.status === 'completed'"
              size="small"
              type="warning"
              @click="handleCancel(row)"
            >
              {{ t('dataPool.cancelOrder') }}
            </el-button>
            <el-button
              v-if="row.status === 'completed' && !row.refund_amount"
              size="small"
              type="danger"
              @click="handleRefund(row)"
            >
              {{ t('dataPool.refundOrder') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="filters.page"
          v-model:page-size="filters.page_size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </div>

    <!-- 订单详情对话框 -->
    <el-dialog v-model="detailVisible" :title="t('dataPool.orderDetail')" width="800px">
      <template v-if="detailData">
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="t('dataPool.orderNo')">
            <span class="text-mono">{{ detailData.order_no }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataPool.customer')">
            {{ detailData.account_name }} (ID: {{ detailData.account_id }})
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataPool.productFilter')">
            {{ detailData.product_name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataPool.orderType')">
            <el-tag :type="orderTypeTagType(detailData.order_type)" size="small">
              {{ orderTypeLabel(detailData.order_type) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataPool.quantity')">{{ detailData.quantity }}</el-descriptions-item>
          <el-descriptions-item :label="t('dataPool.totalPrice')">{{ detailData.total_price }}</el-descriptions-item>
          <el-descriptions-item :label="t('common.status')">
            <el-tag :type="statusTagType(detailData.status)" size="small">
              {{ statusLabel(detailData.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataPool.orderTime')">
            {{ formatDate(detailData.created_at) }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- 关联号码列表 -->
        <h4 style="margin: 16px 0 8px;">{{ t('dataPool.associatedNumbers') }}</h4>
        <el-table :data="detailNumbers" v-loading="detailLoading" max-height="300">
          <el-table-column prop="phone_number" :label="t('dataPool.phoneNumber')" width="160">
            <template #default="{ row }">
              <span class="text-mono">{{ row.phone_number }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="country_code" :label="t('dataPool.country')" width="80" />
          <el-table-column prop="carrier" :label="t('dataPool.carrier')" width="120" />
          <el-table-column prop="status" :label="t('common.status')" width="100">
            <template #default="{ row }">
              <el-tag size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('dataPool.tags')" min-width="150">
            <template #default="{ row }">
              <el-tag v-for="tag in (row.tags || [])" :key="tag" size="small" class="tag-item">
                {{ tag }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getOrders,
  getOrderStats,
  getOrderDetail,
  cancelOrder,
  refundOrder,
  type DataOrder
} from '@/api/data-admin'
import { formatDate } from '@/utils/date'

const { t } = useI18n()

const loading = ref(false)
const orders = ref<DataOrder[]>([])
const total = ref(0)

const filters = reactive({
  account_id: '',
  status: '',
  order_type: '',
  page: 1,
  page_size: 20
})

const stats = reactive({
  total_orders: 0,
  completed_orders: 0,
  total_quantity: 0
})

// 详情对话框
const detailVisible = ref(false)
const detailLoading = ref(false)
const detailData = ref<DataOrder | null>(null)
const detailNumbers = ref<any[]>([])

// 订单类型映射
function orderTypeTagType(type: string) {
  const map: Record<string, string> = {
    data_only: '',
    combo: 'success',
    data_and_send: 'warning'
  }
  return map[type] || 'info'
}

function orderTypeLabel(type: string) {
  const map: Record<string, string> = {
    data_only: t('dataPool.orderTypeDataOnly'),
    combo: t('dataPool.orderTypeCombo'),
    data_and_send: t('dataPool.orderTypeDataAndSend')
  }
  return map[type] || type
}

// 状态映射
function statusTagType(status: string) {
  const map: Record<string, string> = {
    pending: 'warning',
    completed: 'success',
    cancelled: 'info',
    expired: 'danger'
  }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    pending: t('dataPool.processing'),
    completed: t('dataPool.completed'),
    cancelled: t('dataPool.cancelled'),
    expired: t('dataPool.expired')
  }
  return map[status] || status
}

// 加载统计数据
async function loadStats() {
  try {
    const res = await getOrderStats()
    if (res.success) {
      Object.assign(stats, res.data || res)
    }
  } catch (e) {
    console.error('加载订单统计失败', e)
  }
}

// 加载订单列表
async function loadData() {
  loading.value = true
  try {
    const res = await getOrders({
      ...filters,
      account_id: filters.account_id ? parseInt(filters.account_id) : undefined,
      status: filters.status || undefined,
      order_type: filters.order_type || undefined
    })
    if (res.success) {
      orders.value = res.items || []
      total.value = res.total || 0
    }
  } catch (e: any) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    loading.value = false
  }
}

// 点击查询按钮时重置页码
function handleQuery() {
  filters.page = 1
  loadData()
}

// 查看订单详情
async function viewDetail(row: DataOrder) {
  detailVisible.value = true
  detailLoading.value = true
  detailData.value = row
  detailNumbers.value = []
  try {
    const res = await getOrderDetail(row.id)
    if (res.success) {
      detailData.value = res.data?.order || res.order || row
      detailNumbers.value = res.data?.numbers || res.numbers || []
    }
  } catch (e: any) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    detailLoading.value = false
  }
}

// 取消订单
async function handleCancel(row: DataOrder) {
  try {
    const { value } = await ElMessageBox.prompt(
      t('dataPool.cancelReasonPrompt'),
      t('dataPool.cancelOrder'),
      { confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), inputPlaceholder: t('dataPool.cancelReasonPlaceholder') }
    )
    await cancelOrder(row.id, { reason: value })
    ElMessage.success(t('dataPool.cancelSuccess'))
    loadData()
    loadStats()
  } catch (e: any) {
    if (e === 'cancel' || e?.toString?.().includes('cancel')) return
    ElMessage.error(e.message || t('common.failed'))
  }
}

// 退款
async function handleRefund(row: DataOrder) {
  try {
    const { value: reason } = await ElMessageBox.prompt(
      t('dataPool.refundReasonPrompt'),
      t('dataPool.refundOrder'),
      { confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), inputPlaceholder: t('dataPool.refundReasonPlaceholder') }
    )
    const { value: amount } = await ElMessageBox.prompt(
      t('dataPool.refundAmountPrompt'),
      t('dataPool.refundOrder'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        inputPlaceholder: row.total_price,
        inputValue: row.total_price
      }
    )
    await refundOrder(row.id, { reason, refund_amount: amount })
    ElMessage.success(t('dataPool.refundSuccess'))
    loadData()
    loadStats()
  } catch (e: any) {
    if (e === 'cancel' || e?.toString?.().includes('cancel')) return
    ElMessage.error(e.message || t('common.failed'))
  }
}

onMounted(() => {
  loadData()
  loadStats()
})
</script>

<style scoped>
.page-container {
  width: 100%;
}

.page-header {
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-value.stat-success {
  color: var(--el-color-success);
}

.stat-value.stat-primary {
  color: var(--el-color-primary);
}

.stat-label {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-top: 4px;
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

.text-mono {
  font-family: monospace;
  font-size: 13px;
}

.text-sub {
  font-size: 12px;
  color: var(--text-quaternary);
}

.font-bold {
  font-weight: 600;
}

.tag-item {
  margin-right: 4px;
  margin-bottom: 2px;
}
</style>
