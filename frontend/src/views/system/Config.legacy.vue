<template>
  <div class="config-container">
    <el-card shadow="never" class="filter-card">
      <div class="config-header">
        <el-form :inline="true" class="filter-form">
      <el-form-item :label="$t('systemConfig.search')">
        <el-input 
          v-model="searchText" 
          :placeholder="$t('systemConfig.searchPlaceholder')" 
          style="width: 300px"
          clearable
          @keyup.enter="loadData"
        />
      </el-form-item>
      <el-form-item :label="$t('systemConfig.configType')">
        <el-select v-model="filterPublic" clearable :placeholder="$t('systemConfig.all')" style="width: 150px">
          <el-option :label="$t('systemConfig.public')" :value="true" />
          <el-option :label="$t('systemConfig.private')" :value="false" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="loadData">{{ $t('smsRecords.query') }}</el-button>
        <el-button @click="resetFilters">{{ $t('common.reset') }}</el-button>
      </el-form-item>
      <el-form-item class="config-actions">
        <el-button type="primary" @click="showCreateDialog">{{ $t('systemConfig.addConfig') }}</el-button>
      </el-form-item>
        </el-form>
      </div>
    </el-card>
    <el-card shadow="never" class="table-card">
    <el-table :data="configs" v-loading="loading" stripe style="width: 100%">
      <el-table-column prop="config_key" :label="$t('systemConfig.configKey')" width="200" />
      <el-table-column prop="config_value" :label="$t('systemConfig.configValue')">
        <template #default="scope">
          <span v-if="scope.row.config_key.includes('token') || scope.row.config_key.includes('password')">
            {{ maskSensitive(scope.row.config_value) }}
          </span>
          <span v-else>{{ scope.row.config_value }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="config_type" :label="$t('systemConfig.type')" width="100" />
      <el-table-column prop="description" :label="$t('systemConfig.description')" />
      <el-table-column prop="is_public" :label="$t('systemConfig.isPublic')" width="80">
        <template #default="scope">
          <el-tag :type="scope.row.is_public ? 'success' : 'info'">
            {{ scope.row.is_public ? $t('systemConfig.yes') : $t('systemConfig.no') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="$t('common.action')" width="150">
        <template #default="scope">
          <el-button link type="primary" size="small" @click="handleEdit(scope.row)">{{ $t('common.edit') }}</el-button>
          <el-button link type="danger" size="small" @click="handleDelete(scope.row)">{{ $t('common.delete') }}</el-button>
        </template>
      </el-table-column>
    </el-table>
    </el-card>
    <el-dialog 
      v-model="dialogVisible" 
      :title="editingConfig ? $t('systemConfig.editConfig') : $t('systemConfig.addConfig')" 
      width="600px"
    >
      <el-form :model="form" :rules="formRules" ref="formRef" label-width="100px">
        <el-form-item :label="$t('systemConfig.configKey')" prop="config_key" v-if="!editingConfig">
          <el-input v-model="form.config_key" :placeholder="$t('systemConfig.configKeyPlaceholder')" />
        </el-form-item>
        <el-form-item v-else :label="$t('systemConfig.configKey')">
          <el-input v-model="editingConfig.config_key" disabled />
        </el-form-item>
        <el-form-item :label="$t('systemConfig.configValue')" prop="config_value">
          <el-input 
            v-model="form.config_value" 
            type="textarea" 
            :rows="3"
            :placeholder="$t('systemConfig.configValuePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="$t('systemConfig.type')" prop="config_type" v-if="!editingConfig">
          <el-select v-model="form.config_type" style="width: 100%">
            <el-option :label="$t('systemConfig.string')" value="string" />
            <el-option :label="$t('systemConfig.number')" value="number" />
            <el-option :label="$t('systemConfig.boolean')" value="boolean" />
            <el-option label="JSON" value="json" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('systemConfig.description')" prop="description">
          <el-input v-model="form.description" :placeholder="$t('systemConfig.descriptionPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('systemConfig.isPublic')" prop="is_public">
          <el-switch v-model="form.is_public" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getConfigs, createConfig, updateConfig, deleteConfig } from '@/api/system'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import type { SystemConfig } from '@/api/system'

const { t } = useI18n()
const configs = ref<SystemConfig[]>([])
const loading = ref(false)
const searchText = ref('')
const filterPublic = ref<boolean | null>(null)

const dialogVisible = ref(false)
const submitting = ref(false)
const editingConfig = ref<SystemConfig | null>(null)
const formRef = ref<FormInstance>()
const form = reactive({
  config_key: '',
  config_value: '',
  config_type: 'string',
  description: '',
  is_public: false
})

const formRules = computed<FormRules>(() => ({
  config_key: [
    { required: true, message: t('systemConfig.pleaseEnterConfigKey'), trigger: 'blur' },
    { pattern: /^[a-z_][a-z0-9_]*$/, message: t('systemConfig.configKeyPattern'), trigger: 'blur' }
  ],
  config_value: [
    { required: true, message: t('systemConfig.pleaseEnterConfigValue'), trigger: 'blur' }
  ]
}))

const loadData = async () => {
  loading.value = true
  try {
    const res = await getConfigs({
      search: searchText.value || undefined,
      is_public: filterPublic.value !== null ? filterPublic.value : undefined
    })
    configs.value = res
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  searchText.value = ''
  filterPublic.value = null
  loadData()
}

const showCreateDialog = () => {
  editingConfig.value = null
  form.config_key = ''
  form.config_value = ''
  form.config_type = 'string'
  form.description = ''
  form.is_public = false
  dialogVisible.value = true
}

const handleEdit = (row: SystemConfig) => {
  editingConfig.value = row
  form.config_value = row.config_value
  form.description = row.description || ''
  form.is_public = row.is_public
  dialogVisible.value = true
}

const handleSubmit = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    
    submitting.value = true
    try {
      if (editingConfig.value) {
        await updateConfig(editingConfig.value.config_key, {
          config_value: form.config_value,
          description: form.description,
          is_public: form.is_public
        })
        ElMessage.success(t('systemConfig.saveSuccess'))
      } else {
        await createConfig({
          config_key: form.config_key,
          config_value: form.config_value,
          config_type: form.config_type,
          description: form.description,
          is_public: form.is_public
        })
        ElMessage.success(t('systemConfig.saveSuccess'))
      }
      dialogVisible.value = false
      loadData()
    } catch (error: any) {
      ElMessage.error(error.message || t('common.failed'))
    } finally {
      submitting.value = false
    }
  })
}

const handleDelete = async (row: SystemConfig) => {
  try {
    await ElMessageBox.confirm(
      t('systemConfig.confirmDeleteConfig', { key: row.config_key }),
      t('dialog.warningTitle'),
      {
        type: 'warning',
        confirmButtonText: t('common.delete'),
        cancelButtonText: t('common.cancel')
      }
    )
    
    await deleteConfig(row.config_key)
    ElMessage.success(t('systemConfig.deleteSuccess'))
    loadData()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(t('common.failed'))
    }
  }
}

const maskSensitive = (value: string) => {
  if (!value) return ''
  if (value.length <= 8) return '****'
  return value.substring(0, 4) + '****' + value.substring(value.length - 4)
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.config-container { width: 100%; }
.filter-card { margin-bottom: 16px; }
.filter-card :deep(.el-card__body) { padding: 16px 20px; }
.config-header { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 12px; }
.filter-form { margin-bottom: 0; flex: 1; }
.config-actions { margin-left: auto; }
.table-card :deep(.el-card__body) { padding: 16px 20px; }
</style>
