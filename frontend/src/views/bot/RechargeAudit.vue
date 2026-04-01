<template>
  <div class="recharge-audit-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>{{ $t('botAudit.rechargeAudit') }}</span>
          <el-button @click="loadData" :loading="loading" circle icon="Refresh" />
        </div>
      </template>

      <el-table :data="orders" v-loading="loading" style="width: 100%">
        <el-table-column prop="order_no" :label="$t('botAudit.orderNo')" width="180" />
        <el-table-column prop="account_name" :label="$t('botAudit.accountLabel')" width="150" />
        <el-table-column :label="$t('botAudit.applyAmount')" width="150">
          <template #default="scope">
            <span class="amount">{{ scope.row.amount }} {{ scope.row.currency }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('botAudit.proof')" width="120">
          <template #default="scope">
            <el-image
              v-if="scope.row.proof"
              style="width: 50px; height: 50px"
              :src="scope.row.proof"
              :preview-src-list="[scope.row.proof]"
              fit="cover"
              preview-teleported
            >
              <template #error>
                <div class="image-error">
                  <el-icon><Picture /></el-icon>
                </div>
              </template>
            </el-image>
            <span v-else class="no-proof">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('common.status')" width="100">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">
              {{ getStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="$t('common.createdAt')" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')">
          <template #default="scope">
            <div v-if="scope.row.status === 'pending'">
              <el-button type="success" size="small" @click="handleApprove(scope.row)">
                {{ $t('botAudit.approve') }}
              </el-button>
              <el-button type="danger" size="small" @click="handleReject(scope.row)">
                {{ $t('botAudit.reject') }}
              </el-button>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          :page-size="limit"
          :total="total"
          @current-change="loadData"
          layout="total, prev, pager, next"
        />
      </div>
    </el-card>

    <!-- 驳回原因对话框 -->
    <el-dialog v-model="rejectDialogVisible" :title="$t('botAudit.rejectTicket')" width="400px">
      <el-form label-position="top">
        <el-form-item :label="$t('botAudit.enterRejectReason')">
          <el-input
            v-model="rejectReason"
            type="textarea"
            :rows="3"
            :placeholder="$t('botAudit.rejectReasonEmpty')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rejectDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="confirmReject" :loading="submitting">
          {{ $t('common.confirm') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getRecharges, auditRecharge } from '@/api/bot'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Picture } from '@element-plus/icons-vue'

const { t } = useI18n()
const orders = ref([])
const loading = ref(false)
const page = ref(1)
const limit = ref(20)
const total = ref(0)

const rejectDialogVisible = ref(false)
const rejectReason = ref('')
const currentOrder = ref(null)
const submitting = ref(false)

const loadData = async () => {
  loading.value = true
  try {
    const res = await getRecharges({
      status: 'pending',
      page: page.value,
      limit: limit.value
    })
    orders.value = res.items
    total.value = res.total
  } catch (error) {
    console.error('Failed to load recharge orders:', error)
  } finally {
    loading.value = false
  }
}

const handleApprove = (order: any) => {
  ElMessageBox.confirm(
    t('botAudit.confirmPayment', { amount: order.amount, currency: order.currency }),
    t('botAudit.confirmReceived'),
    {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'warning'
    }
  ).then(async () => {
    try {
      await auditRecharge(order.id, { action: 'approve' })
      ElMessage.success(t('botAudit.operationSuccess'))
      loadData()
    } catch (error) {
      console.error('Approve failed:', error)
    }
  })
}

const handleReject = (order: any) => {
  currentOrder.value = order
  rejectReason.value = ''
  rejectDialogVisible.value = true
}

const confirmReject = async () => {
  if (!rejectReason.value.trim()) {
    ElMessage.warning(t('botAudit.rejectReasonEmpty'))
    return
  }

  submitting.value = true
  try {
    await auditRecharge(currentOrder.value.id, {
      action: 'reject',
      reason: rejectReason.value.trim()
    })
    ElMessage.success(t('botAudit.operationSuccess'))
    rejectDialogVisible.value = false
    loadData()
  } catch (error) {
    console.error('Reject failed:', error)
  } finally {
    submitting.value = false
  }
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString()
}

const getStatusType = (status: string) => {
  const map: Record<string, string> = {
    pending: 'warning',
    completed: 'success',
    rejected: 'danger'
  }
  return map[status] || 'info'
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    pending: t('common.pending'),
    completed: t('common.completed'),
    rejected: t('common.rejected')
  }
  return map[status] || status
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.recharge-audit-container {
  padding: 0;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.amount {
  font-weight: bold;
  color: #f56c6c;
}
.image-error {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  background: #f5f7fa;
  color: #909399;
  font-size: 20px;
}
.no-proof {
  color: #909399;
}
.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
