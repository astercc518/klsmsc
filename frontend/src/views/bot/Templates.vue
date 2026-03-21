<template>
  <div class="templates-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>{{ $t('bot.templatesTitle') }}</span>
          <div>
            <el-button @click="showCreateDialog">{{ $t('bot.createWhitelist') }}</el-button>
          <el-button @click="loadData">{{ $t('common.refresh') }}</el-button>
          </div>
        </div>
      </template>

      <!-- 筛选器 -->
      <el-form :inline="true" class="filter-form" style="margin-bottom: 20px">
        <el-form-item :label="$t('systemConfig.search')">
          <el-input 
            v-model="searchText" 
            :placeholder="$t('bot.searchContent')" 
            style="width: 300px"
            clearable
            @keyup.enter="loadData"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">{{ $t('smsRecords.query') }}</el-button>
          <el-button @click="resetSearch">{{ $t('common.reset') }}</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="templates" v-loading="loading" style="width: 100%">
        <el-table-column prop="account_name" :label="$t('bot.account')" width="150" />
        <el-table-column prop="hash" :label="$t('bot.hash')" width="150">
          <template #default="scope">
            <el-tooltip :content="scope.row.hash" placement="top">
              <span>{{ scope.row.hash.substring(0, 8) }}...</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="text" :label="$t('bot.content')" />
        <el-table-column prop="status" :label="$t('common.status')" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'approved' ? 'success' : 'danger'">
              {{ scope.row.status === 'approved' ? $t('bot.approved') : $t('bot.rejected') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="$t('bot.joinTime')" width="180">
          <template #default="scope">
            {{ new Date(scope.row.created_at).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="200">
          <template #default="scope">
            <el-button link type="primary" size="small" @click="handleEdit(scope.row)">{{ $t('common.edit') }}</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(scope.row)">{{ $t('common.delete') }}</el-button>
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

    <!-- 创建/编辑对话框 -->
    <el-dialog 
      v-model="dialogVisible" 
      :title="editingTemplate ? $t('bot.editWhitelist') : $t('bot.createWhitelist')" 
      width="600px"
    >
      <el-form :model="form" :rules="formRules" ref="formRef" label-width="100px">
        <el-form-item :label="$t('bot.accountId')" prop="account_id">
          <el-input-number v-model="form.account_id" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="$t('bot.contentText')" prop="content_text">
          <el-input 
            v-model="form.content_text" 
            type="textarea" 
            :rows="5"
            :placeholder="$t('bot.contentTextPlaceholder')"
            maxlength="1000"
            show-word-limit
          />
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
import { ref, reactive, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { getTemplates, deleteTemplate, createTemplate, updateTemplate } from '@/api/bot'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

const { t } = useI18n()
const templates = ref([])
const loading = ref(false)
const page = ref(1)
const limit = ref(50)
const total = ref(0)
const searchText = ref('')

const dialogVisible = ref(false)
const submitting = ref(false)
const editingTemplate = ref<any>(null)
const formRef = ref<FormInstance>()
const form = reactive({
  account_id: 0,
  content_text: ''
})

const formRules = computed<FormRules>(() => ({
  account_id: [
    { required: true, message: t('bot.enterAccountId'), trigger: 'blur' },
    { type: 'number', min: 1, message: t('bot.accountIdMin'), trigger: 'blur' }
  ],
  content_text: [
    { required: true, message: t('bot.enterContentText'), trigger: 'blur' },
    { min: 1, max: 1000, message: t('bot.contentTextLength'), trigger: 'blur' }
  ]
}))

const loadData = async () => {
  loading.value = true
  try {
    const res = await getTemplates({
      search: searchText.value || undefined,
      page: page.value,
      limit: limit.value
    })
    templates.value = res.items || res
    total.value = res.total || res.length || 0
  } finally {
    loading.value = false
  }
}

const resetSearch = () => {
  searchText.value = ''
  page.value = 1
  loadData()
}

const showCreateDialog = () => {
  editingTemplate.value = null
  form.account_id = 0
  form.content_text = ''
  dialogVisible.value = true
}

const handleEdit = (row: any) => {
  editingTemplate.value = row
  form.account_id = row.account_id
  form.content_text = row.text
  dialogVisible.value = true
}

const handleSubmit = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    
    submitting.value = true
    try {
      if (editingTemplate.value) {
        await updateTemplate(editingTemplate.value.id, {
          status: 'approved'
        })
        ElMessage.success(t('bot.updateSuccess'))
      } else {
        await createTemplate({
          account_id: form.account_id,
          content_text: form.content_text
        })
        ElMessage.success(t('bot.createSuccess'))
      }
      dialogVisible.value = false
      loadData()
    } catch (error: any) {
      ElMessage.error(error.message || t('botAudit.operationFailed'))
    } finally {
      submitting.value = false
    }
  })
}

const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      t('bot.deleteConfirmMessage'),
      t('bot.deleteConfirmTitle'),
      {
        type: 'warning',
        confirmButtonText: t('bot.deleteButton'),
        cancelButtonText: t('common.cancel')
      }
    )
  
  await deleteTemplate(row.id)
  ElMessage.success(t('bot.removed'))
  loadData()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(t('bot.deleteFailed'))
    }
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.templates-container {
  width: 100%;
}
.filter-form {
  margin-bottom: 20px;
}
.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-header > div {
  display: flex;
  gap: 10px;
}
</style>
