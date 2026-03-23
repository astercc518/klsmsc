<template>
  <div class="batch-send-page">
    <!-- 统计卡片 -->
    <div class="stats-cards">
      <div class="stat-card">
        <div class="stat-icon total">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/>
            <path d="M7 6H13M7 10H13M7 14H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ stats.total_batches }}</span>
          <span class="stat-label">{{ $t('batchSend.totalTasks') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon processing">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5"/>
            <path d="M10 6V10L13 13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ stats.processing_batches }}</span>
          <span class="stat-label">{{ $t('batchSend.processing') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon completed">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5"/>
            <path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ stats.completed_batches }}</span>
          <span class="stat-label">{{ $t('batchSend.completed') }}</span>
        </div>
      </div>
      <div class="stat-card action">
        <el-button type="primary" size="large" @click="showUploadDialog" class="create-btn">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M9 3V15M3 9H15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          {{ $t('batchSend.createTask') }}
        </el-button>
      </div>
    </div>

    <!-- 任务列表 -->
    <div class="task-panel">
      <div class="panel-header">
        <h3 class="panel-title">{{ $t('batchSend.taskList') }}</h3>
        <el-button @click="loadBatches" :icon="Refresh" size="small">{{ $t('common.refresh') }}</el-button>
      </div>
      
      <el-table :data="batches" v-loading="loading" stripe>
        <el-table-column prop="batch_name" :label="$t('batchSend.batchName')" width="200" />
        <el-table-column prop="total_count" :label="$t('batchSend.totalCount')" width="80" />
        <el-table-column prop="success_count" :label="$t('batchSend.successCount')" width="80">
          <template #default="{ row }">
            <span style="color: #67c23a; font-weight: bold">{{ row.success_count }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="failed_count" :label="$t('batchSend.failedCount')" width="80">
          <template #default="{ row }">
            <span v-if="row.failed_count > 0" style="color: #f56c6c; font-weight: bold">{{ row.failed_count }}</span>
            <span v-else>0</span>
          </template>
        </el-table-column>
        <el-table-column prop="progress" :label="$t('batchSend.progress')" width="150">
          <template #default="{ row }">
            <el-progress :percentage="row.progress" :status="row.status === 'completed' ? 'success' : undefined" />
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('batchSend.status')" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'pending'" type="info">{{ $t('batchSend.pending') }}</el-tag>
            <el-tag v-else-if="row.status === 'processing'" type="primary">{{ $t('batchSend.processing') }}</el-tag>
            <el-tag v-else-if="row.status === 'completed'" type="success">{{ $t('batchSend.completed') }}</el-tag>
            <el-tag v-else-if="row.status === 'failed'" type="danger">{{ $t('batchSend.failed') }}</el-tag>
            <el-tag v-else type="warning">{{ $t('batchSend.cancelled') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="$t('common.createdAt')" width="180" />
        <el-table-column :label="$t('common.action')" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewDetail(row)">{{ $t('common.detail') }}</el-button>
            <el-button 
              v-if="row.status === 'pending' || row.status === 'processing'" 
              link 
              type="danger" 
              size="small" 
              @click="cancelBatch(row)"
            >
              {{ $t('common.cancel') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          layout="total, prev, pager, next"
          @current-change="loadBatches"
          background
          small
        />
      </div>
    </div>

    <!-- 上传对话框 -->
    <el-dialog v-model="uploadDialogVisible" :title="$t('batchSend.createTask')" width="600px">
      <el-form :model="uploadForm" ref="uploadFormRef" label-width="120px">
        <el-form-item :label="$t('batchSend.taskName')" required>
          <el-input v-model="uploadForm.batch_name" :placeholder="$t('batchSend.taskNamePlaceholder')" />
        </el-form-item>
        
        <el-form-item :label="$t('batchSend.selectTemplate')">
          <el-select v-model="uploadForm.template_id" :placeholder="$t('batchSend.noTemplate')" clearable style="width: 100%">
            <el-option 
              v-for="tpl in templates" 
              :key="tpl.id" 
              :label="tpl.name" 
              :value="tpl.id" 
            />
          </el-select>
          <div style="color: #909399; font-size: 12px; margin-top: 5px">
            {{ $t('batchSend.templateTip') }}
          </div>
        </el-form-item>
        
        <el-form-item :label="$t('batchSend.senderId')">
          <el-input v-model="uploadForm.sender_id" :placeholder="$t('batchSend.senderIdPlaceholder')" />
        </el-form-item>
        
        <el-form-item :label="$t('batchSend.uploadCsv')" required>
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            accept=".csv"
            :on-change="handleFileChange"
            :file-list="fileList"
          >
            <el-button type="primary">{{ $t('batchSend.selectFile') }}</el-button>
            <template #tip>
              <div style="color: #909399; font-size: 12px; margin-top: 10px">
                <div>• {{ $t('batchSend.csvTip1') }}</div>
                <div>• {{ $t('batchSend.csvTip2') }}</div>
                <div>• {{ $t('batchSend.csvTip3') }}</div>
                <code style="display: block; background: var(--el-fill-color-light); padding: 8px; margin-top: 5px; border-radius: 4px;">
phone,name,code<br>
+8613800138000,John,123456<br>
+8613800138001,Jane,654321
                </code>
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="uploadDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitUpload" :loading="uploading">{{ $t('batchSend.startSend') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, Refresh } from '@element-plus/icons-vue'
import { getBatches, getBatchStats, uploadBatchFile, cancelBatch as cancelBatchApi, type SmsBatch } from '@/api/batch'
import { getTemplates } from '@/api/template'

const { t } = useI18n()
const loading = ref(false)
const batches = ref<SmsBatch[]>([])
const stats = reactive({
  total_batches: 0,
  pending_batches: 0,
  processing_batches: 0,
  completed_batches: 0,
  failed_batches: 0,
  total_messages: 0,
  success_messages: 0,
  failed_messages: 0
})
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

const uploadDialogVisible = ref(false)
const uploading = ref(false)
const uploadFormRef = ref()
const uploadRef = ref()
const fileList = ref([])
const uploadForm = reactive({
  batch_name: '',
  template_id: null as number | null,
  sender_id: ''
})

const templates = ref<any[]>([])

const loadBatches = async () => {
  loading.value = true
  try {
    const res = await getBatches({ page: pagination.page, page_size: pagination.pageSize })
    batches.value = res.items
    pagination.total = res.total
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.failed'))
  } finally {
    loading.value = false
  }
}

const loadStats = async () => {
  try {
    const res = await getBatchStats()
    Object.assign(stats, res)
  } catch (error) {
    console.error('Failed to load stats', error)
  }
}

const loadTemplates = async () => {
  try {
    const res = await getTemplates({ page: 1, page_size: 100, status: 'approved' })
    templates.value = res.items
  } catch (error) {
    console.error('Failed to load templates', error)
  }
}

const showUploadDialog = () => {
  resetUploadForm()
  uploadDialogVisible.value = true
}

const handleFileChange = (file: any) => {
  fileList.value = [file]
}

const submitUpload = async () => {
  if (!uploadForm.batch_name) {
    ElMessage.warning(t('batchSend.pleaseEnterBatchName'))
    return
  }
  
  if (fileList.value.length === 0) {
    ElMessage.warning(t('batchSend.pleaseSelectCsv'))
    return
  }
  
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', fileList.value[0].raw)
    formData.append('batch_name', uploadForm.batch_name)
    if (uploadForm.template_id) {
      formData.append('template_id', uploadForm.template_id.toString())
    }
    if (uploadForm.sender_id) {
      formData.append('sender_id', uploadForm.sender_id)
    }
    
    const res = await uploadBatchFile(formData)
    ElMessage.success(res.message || t('batchSend.uploadSuccess'))
    uploadDialogVisible.value = false
    loadBatches()
    loadStats()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('batchSend.uploadFailed'))
  } finally {
    uploading.value = false
  }
}

const viewDetail = (row: SmsBatch) => {
  ElMessageBox.alert(
    `${t('batchSend.totalCount')}: ${row.total_count}<br>
     ${t('batchSend.successCount')}: ${row.success_count}<br>
     ${t('batchSend.failedCount')}: ${row.failed_count}<br>
     ${t('batchSend.progress')}: ${row.progress}%<br>
     ${row.error_message ? `${t('common.error')}: ${row.error_message}` : ''}`,
    t('batchSend.batchDetail'),
    { dangerouslyUseHTMLString: true }
  )
}

const cancelBatch = (row: SmsBatch) => {
  ElMessageBox.confirm(t('batchSend.confirmCancel', { name: row.batch_name }), t('common.info'), {
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel'),
    type: 'warning'
  }).then(async () => {
    try {
      await cancelBatchApi(row.id)
      ElMessage.success(t('batchSend.cancelled'))
      loadBatches()
      loadStats()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('common.failed'))
    }
  }).catch(() => {})
}

const resetUploadForm = () => {
  uploadForm.batch_name = ''
  uploadForm.template_id = null
  uploadForm.sender_id = ''
  fileList.value = []
}

onMounted(() => {
  loadBatches()
  loadStats()
  loadTemplates()
})
</script>

<style scoped>
.batch-send-page {
  width: 100%;
}

/* 统计卡片 */
.stats-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 14px;
  transition: all 0.2s;
}

.stat-card:hover {
  border-color: var(--border-hover);
  transform: translateY(-2px);
}

.stat-card.action {
  justify-content: center;
  padding: 12px;
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-icon.total {
  background: rgba(102, 126, 234, 0.12);
  color: #667EEA;
}

.stat-icon.processing {
  background: rgba(64, 158, 255, 0.12);
  color: #409EFF;
}

.stat-icon.completed {
  background: rgba(56, 239, 125, 0.12);
  color: #38EF7D;
}

.stat-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 12px;
  color: var(--text-tertiary);
}

.create-btn {
  width: 100%;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
}

/* 任务面板 */
.task-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 14px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

/* 表格 */
.task-table {
  --el-table-border-color: var(--border-default);
}

.task-name {
  font-weight: 500;
  color: var(--text-primary);
}

.count-success {
  color: #38EF7D;
  font-weight: 600;
}

.count-fail {
  color: #F5576C;
  font-weight: 600;
}

.time-text {
  font-size: 13px;
  color: var(--text-tertiary);
}

.pagination {
  padding: 16px 20px;
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid var(--border-default);
}

code {
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

/* 响应式 */
@media (max-width: 1200px) {
  .stats-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-cards {
    grid-template-columns: 1fr;
  }
}
</style>
