<template>
  <div class="batch-audit-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>{{ $t('botAudit.batchAudit') }}</span>
          <el-button @click="loadData" :loading="loading" circle icon="Refresh" />
        </div>
      </template>

      <el-table :data="batches" v-loading="loading" style="width: 100%">
        <el-table-column prop="id" :label="$t('botAudit.batchIdLabel')" width="100" />
        <el-table-column prop="account_name" :label="$t('botAudit.accountLabel')" width="150" />
        <el-table-column :label="$t('botAudit.batchInfo')" width="200">
          <template #default="scope">
            <div>{{ $t('smsSend.totalNumbers') }}: {{ scope.row.total_count }}</div>
            <div>{{ $t('botAudit.costLabel') }}: <span class="cost">${{ scope.row.total_cost }}</span></div>
          </template>
        </el-table-column>
        <el-table-column :label="$t('botAudit.contentPreview')" min-width="300">
          <template #default="scope">
            <div class="content-preview" @click="showFullContent(scope.row.content)">
              {{ scope.row.content }}
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="$t('common.createdAt')" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="180">
          <template #default="scope">
            <div v-if="scope.row.status === 'pending_audit'">
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
    <el-dialog v-model="rejectDialogVisible" :title="$t('botAudit.rejectBatch')" width="400px">
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

    <!-- 完整内容对话框 -->
    <el-dialog v-model="contentDialogVisible" :title="$t('botAudit.fullContent')" width="600px">
      <div class="full-content">
        {{ currentContent }}
      </div>
      <template #footer>
        <el-button @click="contentDialogVisible = false">{{ $t('common.close') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getBotBatches, auditBatch } from '@/api/bot'
import { ElMessage, ElMessageBox } from 'element-plus'

const { t } = useI18n()
const batches = ref([])
const loading = ref(false)
const page = ref(1)
const limit = ref(20)
const total = ref(0)

const rejectDialogVisible = ref(false)
const rejectReason = ref('')
const currentBatch = ref(null)
const submitting = ref(false)

const contentDialogVisible = ref(false)
const currentContent = ref('')

const loadData = async () => {
  loading.value = true
  try {
    const res = await getBotBatches({
      status: 'pending_audit',
      page: page.value,
      limit: limit.value
    })
    batches.value = res.items
    total.value = res.total
  } catch (error) {
    console.error('Failed to load batches:', error)
  } finally {
    loading.value = false
  }
}

const handleApprove = (batch: any) => {
  ElMessageBox.confirm(
    t('botAudit.confirmBatch', { action: t('botAudit.approve') }),
    t('common.confirm'),
    {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'warning'
    }
  ).then(async () => {
    try {
      await auditBatch(batch.id, { action: 'approve' })
      ElMessage.success(t('botAudit.operationSuccess'))
      loadData()
    } catch (error) {
      console.error('Approve failed:', error)
    }
  })
}

const handleReject = (batch: any) => {
  currentBatch.value = batch
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
    await auditBatch(currentBatch.value.id, {
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

const showFullContent = (content: string) => {
  currentContent.value = content
  contentDialogVisible.value = true
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString()
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.batch-audit-container {
  padding: 0;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.cost {
  color: #f56c6c;
  font-weight: bold;
}
.content-preview {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}
.content-preview:hover {
  color: #409eff;
}
.full-content {
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.6;
  max-height: 400px;
  overflow-y: auto;
  padding: 10px;
  background: #f8f9fa;
  border-radius: 4px;
}
.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
