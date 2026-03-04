<template>
  <div class="batch-audit-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>{{ $t('botAudit.batchAudit') }}</span>
          <el-button @click="loadData">{{ $t('common.refresh') }}</el-button>
        </div>
      </template>

      <el-table :data="batches" v-loading="loading" style="width: 100%">
        <el-table-column prop="created_at" :label="$t('botAudit.submitTime')" width="180">
          <template #default="scope">
            {{ new Date(scope.row.created_at).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column prop="account_id" :label="$t('voice.accountId')" width="100" />
        <el-table-column :label="$t('botAudit.batchInfo')" width="200">
          <template #default="scope">
            <div>{{ $t('botAudit.totalCount') }}: {{ scope.row.total_count }}</div>
            <div>{{ $t('botAudit.totalCost') }}: <span class="cost">${{ scope.row.total_cost }}</span></div>
          </template>
        </el-table-column>
        <el-table-column :label="$t('botAudit.contentPreview')">
          <template #default="scope">
            <el-popover
              placement="top-start"
              :title="$t('botAudit.fullContent')"
              :width="400"
              trigger="hover"
              :content="scope.row.content"
            >
              <template #reference>
                <div class="content-preview">{{ scope.row.content }}</div>
              </template>
            </el-popover>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="250">
          <template #default="scope">
            <el-button type="success" size="small" @click="handleAudit(scope.row, 'approve')">{{ $t('botAudit.approve') }}</el-button>
            <el-button type="danger" size="small" @click="handleAudit(scope.row, 'reject')">{{ $t('botAudit.reject') }}</el-button>
            <el-button type="primary" size="small" link>{{ $t('botAudit.sendTest') }}</el-button>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getBatches, auditBatch } from '@/api/bot'
import { ElMessage, ElMessageBox } from 'element-plus'

const { t } = useI18n()
const batches = ref([])
const loading = ref(false)
const page = ref(1)
const limit = ref(20)
const total = ref(0)

const loadData = async () => {
  loading.value = true
  try {
    const res = await getBatches({ 
      status: 'pending_audit',
      page: page.value,
      limit: limit.value
    })
    batches.value = res.items || res
    total.value = res.total || res.length || 0
  } finally {
    loading.value = false
  }
}

const handleAudit = async (batch: any, action: 'approve' | 'reject') => {
  try {
  const actionText = action === 'approve' ? t('botAudit.pass') : t('botAudit.reject')
    
    if (action === 'reject') {
      const { value: reason } = await ElMessageBox.prompt(
        t('botAudit.enterRejectReason'),
        t('botAudit.rejectBatch'),
        {
          confirmButtonText: t('botAudit.submit'),
          cancelButtonText: t('common.cancel'),
          inputValidator: (value) => {
            if (!value || value.trim().length === 0) {
              return t('botAudit.rejectReasonEmpty')
            }
            return true
          }
        }
      )
      await auditBatch(batch.id, action, reason)
    } else {
      await ElMessageBox.confirm(
        `${t('botAudit.confirmBatch', { action: actionText })}\n\n${t('botAudit.batchIdLabel')}: ${batch.id}\n${t('botAudit.totalLabel')}: ${batch.total_count}\n${t('botAudit.costLabel')}: ${batch.total_cost}`,
        t('botAudit.tip'),
        {
          type: action === 'approve' ? 'success' : 'warning',
          confirmButtonText: t('botAudit.confirm'),
          cancelButtonText: t('common.cancel')
        }
      )
  await auditBatch(batch.id, action)
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
.batch-audit-container {
  width: 100%;
}
.cost {
  color: #f56c6c;
  font-weight: bold;
}
.content-preview {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
}
</style>
