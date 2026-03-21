<template>
  <div class="data-numbers-page">
    <div class="page-header">
      <div class="header-left">
        <h1>{{ t('dataPool.numberPoolTitle') }}</h1>
        <p class="subtitle">{{ t('dataPool.numberPoolDesc') }}</p>
      </div>
      <div class="header-right">
        <el-button type="primary" @click="showImportDialog = true">
          <el-icon><Upload /></el-icon>
          {{ t('dataPool.importNumbers') }}
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-value">{{ stats.total?.toLocaleString() || 0 }}</div>
        <div class="stat-label">{{ t('dataPool.totalNumbers') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.by_status?.active?.toLocaleString() || 0 }}</div>
        <div class="stat-label">{{ t('dataPool.activeNumbers') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.by_status?.inactive?.toLocaleString() || 0 }}</div>
        <div class="stat-label">{{ t('dataPool.inactiveNumbers') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ Object.keys(stats.by_country || {}).length }}</div>
        <div class="stat-label">{{ t('dataPool.coveredCountries') }}</div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-select v-model="filters.country" :placeholder="t('dataPool.selectCountry')" clearable @change="loadData">
        <el-option v-for="(count, code) in stats.by_country" :key="code" :label="`${code} (${count})`" :value="code" />
      </el-select>
      <el-select v-model="filters.status" :placeholder="t('common.status')" clearable @change="loadData">
        <el-option :label="t('dataPool.active')" value="active" />
        <el-option :label="t('dataPool.disabled')" value="inactive" />
        <el-option :label="t('dataPool.unknown')" value="unknown" />
        <el-option :label="t('dataPool.blacklisted')" value="blacklisted" />
      </el-select>
      <el-input v-model="filters.tag" :placeholder="t('dataPool.tagFilter')" clearable style="width: 200px" @keyup.enter="loadData">
        <template #prefix>
          <el-icon><PriceTag /></el-icon>
        </template>
      </el-input>
      <el-button @click="loadData">
        <el-icon><Search /></el-icon>
        {{ t('common.search') }}
      </el-button>
    </div>

    <!-- 数据表格 -->
    <div class="data-table">
      <el-table :data="numbers" v-loading="loading" stripe>
        <el-table-column prop="phone_number" :label="t('dataPool.phoneNumber')" min-width="150" />
        <el-table-column prop="country_code" :label="t('dataPool.country')" width="100" />
        <el-table-column :label="t('dataPool.tag')" min-width="200">
          <template #default="{ row }">
            <el-tag v-for="tag in (row.tags || [])" :key="tag" size="small" style="margin: 2px">
              {{ tag }}
            </el-tag>
            <span v-if="!row.tags || row.tags.length === 0" class="empty-text">{{ t('dataPool.noTags') }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="t('common.status')" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">{{ getStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="use_count" :label="t('dataPool.useCount')" width="100" />
        <el-table-column prop="source" :label="t('dataPool.source')" width="120" />
        <el-table-column prop="batch_id" :label="t('dataPool.batchId')" width="180" />
        <el-table-column prop="created_at" :label="t('dataPool.importTime')" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </div>

    <!-- 导入对话框 -->
    <el-dialog v-model="showImportDialog" :title="t('dataPool.importNumbersTitle')" width="500px">
      <el-form label-width="100px">
        <el-form-item :label="t('dataPool.selectFile')">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            accept=".csv,.txt"
            :on-change="handleFileChange"
          >
            <template #trigger>
              <el-button type="primary">{{ t('dataPool.selectCsvFile') }}</el-button>
            </template>
            <template #tip>
              <div class="upload-tip">
                {{ t('dataPool.csvFormatTip') }}
              </div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item :label="t('dataPool.sourceRemark')">
          <el-input v-model="importForm.source" :placeholder="t('dataPool.sourceExample')" />
        </el-form-item>
        <el-form-item :label="t('dataPool.defaultTags')">
          <el-input v-model="importForm.defaultTags" :placeholder="t('dataPool.tagsCommaSeparated')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showImportDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="handleImport" :loading="importing">
          {{ t('dataPool.startImport') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Upload, Search, PriceTag } from '@element-plus/icons-vue'
import request from '@/api/index'

const { t } = useI18n()

const loading = ref(false)
const importing = ref(false)
const numbers = ref([])
const stats = ref({})
const showImportDialog = ref(false)
const uploadRef = ref(null)
const importFile = ref(null)

const filters = ref({
  country: '',
  status: '',
  tag: ''
})

const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0
})

const importForm = ref({
  source: '',
  defaultTags: ''
})

const loadStats = async () => {
  try {
    const res = await request.get('/admin/data/numbers/stats')
    if (res.success) {
      stats.value = res
    }
  } catch (error) {
    console.error('Load stats failed:', error)
  }
}

const loadData = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.value.page,
      page_size: pagination.value.pageSize
    }
    if (filters.value.country) params.country = filters.value.country
    if (filters.value.status) params.status = filters.value.status
    if (filters.value.tag) params.tag = filters.value.tag

    const res = await request.get('/admin/data/numbers', { params })
    if (res.success) {
      numbers.value = res.items
      pagination.value.total = res.total
    }
  } catch (error) {
    ElMessage.error(t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

const handleFileChange = (file) => {
  importFile.value = file.raw
}

const handleImport = async () => {
  if (!importFile.value) {
    ElMessage.warning(t('dataPool.pleaseSelectFile'))
    return
  }

  importing.value = true
  try {
    const formData = new FormData()
    formData.append('file', importFile.value)
    if (importForm.value.source) {
      formData.append('source', importForm.value.source)
    }
    if (importForm.value.defaultTags) {
      formData.append('default_tags', importForm.value.defaultTags)
    }

    const res = await request.post('/admin/data/numbers/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    if (res.success) {
      ElMessage.success(t('dataPool.importCompleteMsg', { valid: res.valid_count, duplicate: res.duplicate_count, invalid: res.invalid_count }))
      showImportDialog.value = false
      importForm.value = { source: '', defaultTags: '' }
      importFile.value = null
      loadStats()
      loadData()
    }
  } catch (error) {
    ElMessage.error(t('dataPool.importFailed') + ': ' + (error.message || t('common.unknownError')))
  } finally {
    importing.value = false
  }
}

const getStatusType = (status) => {
  const types = {
    active: 'success',
    inactive: 'info',
    unknown: 'warning',
    blacklisted: 'danger'
  }
  return types[status] || 'info'
}

const getStatusLabel = (status) => {
  const labels = {
    active: t('dataPool.active'),
    inactive: t('dataPool.disabled'),
    unknown: t('dataPool.unknown'),
    blacklisted: t('dataPool.blacklisted')
  }
  return labels[status] || status
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

onMounted(() => {
  loadStats()
  loadData()
})
</script>

<style scoped>
.data-numbers-page {
  width: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 24px;
  font-weight: 600;
  margin: 0;
}

.subtitle {
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  font-size: 14px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 20px;
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 600;
  color: var(--el-color-primary);
}

.stat-label {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.data-table {
  background: var(--el-bg-color);
  border-radius: 12px;
  border: 1px solid var(--el-border-color-lighter);
  overflow: hidden;
}

.pagination-wrapper {
  padding: 16px;
  display: flex;
  justify-content: flex-end;
}

.empty-text {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

.upload-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 8px;
  line-height: 1.5;
}
</style>
