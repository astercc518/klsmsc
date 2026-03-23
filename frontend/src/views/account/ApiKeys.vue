<template>
  <div class="api-keys-page">
    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic :title="$t('apiKeys.totalKeys')" :value="stats.total_keys" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic :title="$t('apiKeys.activeKeys')" :value="stats.active_keys">
            <template #suffix><span style="color: #67c23a">↗</span></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic :title="$t('apiKeys.totalUsage')" :value="stats.total_usage" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-button type="primary" size="large" @click="showCreateDialog" style="width: 100%">
            <el-icon><Plus /></el-icon> {{ $t('apiKeys.createKey') }}
          </el-button>
        </el-card>
      </el-col>
    </el-row>

    <!-- 密钥列表 -->
    <el-card style="margin-top: 20px">
      <template #header><h3>{{ $t('apiKeys.keyList') }}</h3></template>
      
      <el-table :data="keys" v-loading="loading" stripe>
        <el-table-column prop="key_name" :label="$t('apiKeys.keyName')" width="150" />
        <el-table-column prop="api_key" :label="$t('apiKeys.apiKey')" min-width="250">
          <template #default="{ row }">
            <code>{{ row.api_key }}</code>
            <el-button link size="small" @click="copyKey(row.api_key)">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </template>
        </el-table-column>
        <el-table-column prop="permission" :label="$t('apiKeys.permission')" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.permission === 'read_only'" type="info">{{ $t('apiKeys.readOnly') }}</el-tag>
            <el-tag v-else-if="row.permission === 'read_write'" type="success">{{ $t('apiKeys.readWrite') }}</el-tag>
            <el-tag v-else type="warning">{{ $t('apiKeys.fullAccess') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('common.status')" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'active'" type="success">{{ $t('apiKeys.active') }}</el-tag>
            <el-tag v-else type="info">{{ $t('apiKeys.disabled') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="usage_count" :label="$t('apiKeys.usageCount')" width="100" />
        <el-table-column prop="last_used_at" :label="$t('apiKeys.lastUsed')" width="180" />
        <el-table-column :label="$t('common.action')" width="250" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="editKey(row)">{{ $t('common.edit') }}</el-button>
            <el-button link type="warning" size="small" @click="regenerateKey(row)">{{ $t('apiKeys.regenerate') }}</el-button>
            <el-button link type="danger" size="small" @click="deleteKey(row)">{{ $t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          layout="total, prev, pager, next"
          @current-change="loadKeys"
        />
      </div>
    </el-card>

    <!-- 创建对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? $t('apiKeys.editKey') : $t('apiKeys.createKey')" width="600px">
      <el-form :model="formData" ref="formRef" label-width="120px">
        <el-form-item :label="$t('apiKeys.keyName')" required>
          <el-input v-model="formData.key_name" :placeholder="$t('apiKeys.keyNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('apiKeys.permissionLevel')">
          <el-select v-model="formData.permission" style="width: 100%">
            <el-option :label="$t('apiKeys.readOnly')" value="read_only" />
            <el-option :label="$t('apiKeys.readWrite')" value="read_write" />
            <el-option :label="$t('apiKeys.fullAccess')" value="full" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('apiKeys.rateLimit')">
          <el-input-number v-model="formData.rate_limit" :min="1" :max="10000" />
          <span style="margin-left: 10px; color: #909399">{{ $t('apiKeys.requestsPerMinute') }}</span>
        </el-form-item>
        <el-form-item :label="$t('apiKeys.validity')">
          <el-input-number v-model="formData.expires_days" :min="1" :max="3650" :placeholder="$t('apiKeys.unlimited')" />
          <span style="margin-left: 10px; color: #909399">{{ $t('apiKeys.daysEmptyPermanent') }}</span>
        </el-form-item>
        <el-form-item :label="$t('common.description')">
          <el-input v-model="formData.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 密钥显示对话框（创建成功后） -->
    <el-dialog v-model="secretDialogVisible" :title="$t('apiKeys.keyCreatedSuccess')" width="600px" :close-on-click-modal="false">
      <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 20px">
        <template #title>{{ $t('apiKeys.saveKeyWarning') }}</template>
      </el-alert>
      
      <el-descriptions :column="1" border>
        <el-descriptions-item label="API Key">
          <code>{{ newSecret.api_key }}</code>
          <el-button link @click="copyKey(newSecret.api_key)"><el-icon><CopyDocument /></el-icon></el-button>
        </el-descriptions-item>
        <el-descriptions-item label="API Secret">
          <code>{{ newSecret.api_secret }}</code>
          <el-button link @click="copyKey(newSecret.api_secret)"><el-icon><CopyDocument /></el-icon></el-button>
        </el-descriptions-item>
      </el-descriptions>

      <template #footer>
        <el-button type="primary" @click="secretDialogVisible = false">{{ $t('apiKeys.keySaved') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, CopyDocument } from '@element-plus/icons-vue'
import { getApiKeys, getApiKeyStats, createApiKey, updateApiKey, regenerateApiKey, deleteApiKey as delApiKey, type ApiKey } from '@/api/apiKey'

const { t } = useI18n()
const loading = ref(false)
const keys = ref<ApiKey[]>([])
const stats = reactive({ total_keys: 0, active_keys: 0, disabled_keys: 0, expired_keys: 0, total_usage: 0 })
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

const dialogVisible = ref(false)
const secretDialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(0)
const submitting = ref(false)

const formRef = ref()
const formData = reactive({
  key_name: '',
  permission: 'read_write',
  rate_limit: 1000,
  expires_days: undefined as number | undefined,
  description: ''
})

const newSecret = reactive({ api_key: '', api_secret: '' })

const loadKeys = async () => {
  loading.value = true
  try {
    const res = await getApiKeys({ page: pagination.page, page_size: pagination.pageSize })
    keys.value = res.items
    pagination.total = res.total
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

const loadStats = async () => {
  try {
    const res = await getApiKeyStats()
    Object.assign(stats, res)
  } catch (error) {
    console.error('Failed to load stats', error)
  }
}

const showCreateDialog = () => {
  isEdit.value = false
  resetForm()
  dialogVisible.value = true
}

const editKey = (row: ApiKey) => {
  isEdit.value = true
  editId.value = row.id
  formData.key_name = row.key_name
  formData.permission = row.permission
  formData.rate_limit = row.rate_limit
  formData.description = row.description || ''
  dialogVisible.value = true
}

const submitForm = async () => {
  submitting.value = true
  try {
    if (isEdit.value) {
      await updateApiKey(editId.value, formData)
      ElMessage.success(t('common.updateSuccess'))
      dialogVisible.value = false
    } else {
      const res = await createApiKey(formData)
      newSecret.api_key = res.api_key
      newSecret.api_secret = res.api_secret
      dialogVisible.value = false
      secretDialogVisible.value = true
    }
    loadKeys()
    loadStats()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.operationFailed'))
  } finally {
    submitting.value = false
  }
}

const regenerateKey = (row: ApiKey) => {
  ElMessageBox.confirm(t('apiKeys.confirmRegenerate', { name: row.key_name }), t('common.warning'), {
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel'),
    type: 'warning'
  }).then(async () => {
    try {
      const res = await regenerateApiKey(row.id)
      newSecret.api_key = res.api_key
      newSecret.api_secret = res.api_secret
      secretDialogVisible.value = true
      loadKeys()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('common.operationFailed'))
    }
  }).catch(() => {})
}

const deleteKey = (row: ApiKey) => {
  ElMessageBox.confirm(t('apiKeys.confirmDelete', { name: row.key_name }), t('common.tip'), {
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel'),
    type: 'warning'
  }).then(async () => {
    try {
      await delApiKey(row.id)
      ElMessage.success(t('common.deleteSuccess'))
      loadKeys()
      loadStats()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('common.deleteFailed'))
    }
  }).catch(() => {})
}

const copyKey = (text: string) => {
  navigator.clipboard.writeText(text)
  ElMessage.success(t('common.copiedToClipboard'))
}

const resetForm = () => {
  formData.key_name = ''
  formData.permission = 'read_write'
  formData.rate_limit = 1000
  formData.expires_days = undefined
  formData.description = ''
}

onMounted(() => {
  loadKeys()
  loadStats()
})
</script>

<style scoped>
.api-keys-page {
  width: 100%;
}

.stats-row {
  margin-bottom: 20px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

code {
  background: var(--el-fill-color-light);
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
}
</style>
