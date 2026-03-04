<template>
  <div class="recharge-audit-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>{{ $t('botAudit.rechargeAudit') }}</span>
          <el-button @click="loadData">{{ $t('common.refresh') }}</el-button>
        </div>
      </template>

      <div class="audit-list" v-loading="loading">
        <el-empty v-if="orders.length === 0" :description="$t('botAudit.noPendingOrders')" />
        
        <el-row :gutter="20">
          <el-col :span="8" v-for="order in orders" :key="order.id">
            <el-card shadow="hover" class="order-card">
              <div class="proof-image">
                <el-image 
                  :src="order.proof || 'placeholder.png'" 
                  :preview-src-list="[order.proof]"
                  fit="cover"
                  style="width: 100%; height: 200px"
                >
                  <template #error>
                    <div class="image-slot">
                      {{ $t('botAudit.noImage') }}
                    </div>
                  </template>
                </el-image>
              </div>
              <div class="order-info">
                <div class="info-row">
                  <span class="label">{{ $t('botAudit.orderNo') }}:</span>
                  <span class="value">{{ order.order_no }}</span>
                </div>
                <div class="info-row">
                  <span class="label">{{ $t('voice.accountId') }}:</span>
                  <span class="value">{{ order.account_id }}</span>
                </div>
                <div class="info-row amount-row">
                  <span class="label">{{ $t('botAudit.applyAmount') }}:</span>
                  <span class="value amount">${{ order.amount }}</span>
                </div>
                <div class="info-row">
                  <span class="label">{{ $t('botAudit.submitTime2') }}:</span>
                  <span class="value">{{ new Date(order.created_at).toLocaleString() }}</span>
                </div>
              </div>
              <div class="actions">
                <el-button type="success" @click="handleAudit(order, 'approve')">{{ $t('botAudit.confirmReceived') }}</el-button>
                <el-button type="danger" @click="handleAudit(order, 'reject')">{{ $t('botAudit.reject') }}</el-button>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getRecharges, auditRecharge } from '@/api/bot'
import { ElMessage, ElMessageBox } from 'element-plus'

const { t } = useI18n()
const orders = ref([])
const loading = ref(false)

const page = ref(1)
const limit = ref(20)
const total = ref(0)

const loadData = async () => {
  loading.value = true
  try {
    const res = await getRecharges({ 
      status: 'pending',
      page: page.value,
      limit: limit.value
    })
    orders.value = res.items || res
    total.value = res.total || res.length || 0
  } finally {
    loading.value = false
  }
}

const handleAudit = async (order: any, action: 'approve' | 'reject') => {
  try {
  if (action === 'reject') {
    const { value: reason } = await ElMessageBox.prompt(t('botAudit.enterRejectReason'), t('botAudit.rejectTicket'), {
      confirmButtonText: t('botAudit.submit'),
      cancelButtonText: t('common.cancel'),
        inputValidator: (value) => {
          if (!value || value.trim().length === 0) {
            return t('botAudit.rejectReasonEmpty')
          }
          return true
        }
    })
    await auditRecharge(order.id, action, reason)
  } else {
      await ElMessageBox.confirm(
        `${t('botAudit.confirmPayment', { amount: order.amount, currency: order.currency || 'USD' })}\n\n${t('botAudit.accountLabel')}: ${order.account_name || order.account_id}`,
        t('botAudit.confirmArrival'),
        {
          type: 'warning',
          confirmButtonText: t('botAudit.confirm'),
          cancelButtonText: t('common.cancel')
        }
      )
    await auditRecharge(order.id, action)
  }
  
  ElMessage.success(t('botAudit.operationSuccess'))
  loadData()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || t('botAudit.operationFailed'))
    }
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.recharge-audit-container {
  width: 100%;
}
.order-card {
  margin-bottom: 20px;
}
.order-info {
  padding: 10px 0;
}
.info-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
  font-size: 14px;
}
.amount-row {
  font-weight: bold;
  font-size: 16px;
  color: #67c23a;
  margin: 10px 0;
}
.actions {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
}
.actions .el-button {
  flex: 1;
}
.image-slot {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  background: var(--bg-input);
  color: var(--text-tertiary);
}

[data-theme="light"] .image-slot {
  background: rgba(0, 0, 0, 0.03);
}
</style>
