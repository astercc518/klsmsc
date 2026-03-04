<template>
  <div style="padding: 20px">
    <h2 style="margin-bottom: 20px">我的数据订单</h2>

    <el-table :data="orders" v-loading="loading" stripe border style="width: 100%">
      <el-table-column prop="order_no" label="订单号" width="220" />
      <el-table-column prop="product_name" label="商品名称" min-width="180" />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">
          <el-tag :type="orderTypeTag(row.order_type)" size="small">{{ orderTypeLabel(row.order_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="quantity" label="数量" width="80" align="right" />
      <el-table-column label="单价" width="100" align="right">
        <template #default="{ row }">${{ row.unit_price }}</template>
      </el-table-column>
      <el-table-column label="总价" width="100" align="right">
        <template #default="{ row }">
          <span style="color:#e6a23c;font-weight:600">${{ row.total_price }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.status === 'pending'" size="small" type="danger" link @click="handleCancel(row)">取消</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div style="display:flex;justify-content:flex-end;margin-top:16px">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadOrders"
        @current-change="loadOrders"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getMyOrders, cancelOrder } from '@/api/data'
import { ElMessage, ElMessageBox } from 'element-plus'

const orders = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

async function loadOrders() {
  loading.value = true
  try {
    const res = await getMyOrders({ page: page.value, page_size: pageSize.value })
    orders.value = res.items || []
    total.value = res.total || 0
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function orderTypeLabel(t: string) {
  const m: Record<string, string> = { data_only: '纯数据', combo: '组合套餐', data_and_send: '买即发' }
  return m[t] || t
}
function orderTypeTag(t: string) {
  const m: Record<string, '' | 'success' | 'warning'> = { data_only: '', combo: 'success', data_and_send: 'warning' }
  return m[t] ?? ''
}
function statusLabel(s: string) {
  const m: Record<string, string> = { pending: '待处理', completed: '已完成', cancelled: '已取消', refunded: '已退款' }
  return m[s] || s
}
function statusTag(s: string) {
  const m: Record<string, '' | 'success' | 'danger' | 'info'> = { pending: '', completed: 'success', cancelled: 'info', refunded: 'danger' }
  return m[s] ?? ''
}
function fmtDate(d: string) {
  if (!d) return '-'
  return new Date(d).toLocaleString('zh-CN')
}

async function handleCancel(row: any) {
  try {
    await ElMessageBox.confirm('确定要取消此订单吗？', '取消订单', { type: 'warning' })
    await cancelOrder(row.id, { reason: '客户主动取消' })
    ElMessage.success('订单已取消')
    loadOrders()
  } catch { /* 用户取消操作 */ }
}

onMounted(loadOrders)
</script>
