<template>
  <div class="my-orders-page">
    <h2 class="page-title">我的数据订单</h2>

    <el-table :data="orders" v-loading="loading" stripe border style="width: 100%">
      <el-table-column prop="order_no" label="订单号" width="220" />
      <el-table-column prop="product_name" label="商品名称" min-width="160" />
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
      <el-table-column label="评分" width="150" align="center">
        <template #default="{ row }">
          <template v-if="row._my_rating">
            <div class="star-display">
              <span v-for="s in 5" :key="s" class="star-icon" :class="{ filled: s <= row._my_rating }">★</span>
            </div>
          </template>
          <el-button
            v-else-if="row.product_id"
            size="small"
            type="primary"
            link
            @click="openRateDialog(row)"
          >评分</el-button>
          <span v-else style="color:#c0c4cc">-</span>
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

    <!-- 评分弹窗 -->
    <el-dialog v-model="rateDialogVisible" title="数据商品评分" width="420px" :close-on-click-modal="false">
      <div class="rate-dialog-body">
        <div class="rate-product-info">
          <span class="rate-label">商品：</span>
          <span class="rate-value">{{ rateTarget.product_name }}</span>
        </div>
        <div class="rate-product-info">
          <span class="rate-label">订单：</span>
          <span class="rate-value">{{ rateTarget.order_no }}</span>
        </div>
        <div class="rate-stars-section">
          <span class="rate-label">评分：</span>
          <div class="rate-stars">
            <span
              v-for="s in 5"
              :key="s"
              class="rate-star"
              :class="{ active: s <= rateForm.rating, hover: s <= rateHover }"
              @mouseenter="rateHover = s"
              @mouseleave="rateHover = 0"
              @click="rateForm.rating = s"
            >★</span>
          </div>
          <span class="rate-score-text">{{ rateScoreText }}</span>
        </div>
        <div class="rate-comment-section">
          <span class="rate-label">评价：</span>
          <el-input
            v-model="rateForm.comment"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="对数据质量的评价（选填）"
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="rateDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="rateLoading" :disabled="!rateForm.rating" @click="submitRate">
          提交评分
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getMyOrders, cancelOrder, rateProduct } from '@/api/data'
import { ElMessage, ElMessageBox } from 'element-plus'

const orders = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

// 评分
const rateDialogVisible = ref(false)
const rateLoading = ref(false)
const rateHover = ref(0)
const rateTarget = ref<any>({})
const rateForm = ref({ rating: 0, comment: '' })

const rateScoreText = computed(() => {
  const r = rateHover.value || rateForm.value.rating
  const texts = ['', '很差', '较差', '一般', '良好', '优秀']
  return texts[r] || ''
})

async function loadOrders() {
  loading.value = true
  try {
    const res = await getMyOrders({ page: page.value, page_size: pageSize.value })
    orders.value = (res.items || []).map((o: any) => ({ ...o, _my_rating: o._my_rating || 0 }))
    total.value = res.total || 0
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openRateDialog(row: any) {
  rateTarget.value = row
  rateForm.value = { rating: 0, comment: '' }
  rateHover.value = 0
  rateDialogVisible.value = true
}

async function submitRate() {
  if (!rateForm.value.rating) return
  rateLoading.value = true
  try {
    await rateProduct(rateTarget.value.product_id, {
      rating: rateForm.value.rating,
      order_id: rateTarget.value.id,
      comment: rateForm.value.comment || undefined,
    })
    ElMessage.success('评分成功！')
    rateDialogVisible.value = false
    // 更新本地数据
    const idx = orders.value.findIndex(o => o.id === rateTarget.value.id)
    if (idx >= 0) orders.value[idx]._my_rating = rateForm.value.rating
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e.message || '评分失败')
  } finally {
    rateLoading.value = false
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
  const m: Record<string, string> = { pending: '待处理', processing: '处理中', completed: '已完成', cancelled: '已取消', refunded: '已退款' }
  return m[s] || s
}
function statusTag(s: string) {
  const m: Record<string, '' | 'success' | 'danger' | 'info' | 'warning'> = { pending: '', processing: 'warning', completed: 'success', cancelled: 'info', refunded: 'danger' }
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

<style scoped>
.my-orders-page {
  padding: 20px;
}
.page-title {
  margin-bottom: 20px;
  font-size: 20px;
  font-weight: 600;
}

/* 星星展示（表格内） */
.star-display {
  display: inline-flex;
  gap: 1px;
}
.star-icon {
  font-size: 14px;
  color: #dcdfe6;
}
.star-icon.filled {
  color: #f7ba2a;
}

/* 评分弹窗 */
.rate-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.rate-product-info {
  display: flex;
  align-items: center;
}
.rate-label {
  min-width: 50px;
  color: #606266;
  font-weight: 500;
}
.rate-value {
  color: #303133;
}
.rate-stars-section {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rate-stars {
  display: inline-flex;
  gap: 4px;
}
.rate-star {
  font-size: 28px;
  color: #dcdfe6;
  cursor: pointer;
  transition: color 0.15s, transform 0.15s;
}
.rate-star.active {
  color: #f7ba2a;
}
.rate-star.hover {
  color: #f7ba2a;
  transform: scale(1.15);
}
.rate-score-text {
  font-size: 14px;
  color: #e6a23c;
  font-weight: 500;
  min-width: 32px;
}
.rate-comment-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>
