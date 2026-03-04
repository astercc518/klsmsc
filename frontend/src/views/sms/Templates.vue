<template>
  <div class="templates-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <h2>{{ $t('templates.title') }}</h2>
          <el-button type="primary" @click="showCreateDialog">
            <el-icon><Plus /></el-icon>
            {{ $t('templates.addTemplate') }}
          </el-button>
        </div>
      </template>

      <!-- 筛选 -->
      <el-form :inline="true" class="filter-form">
        <el-form-item :label="$t('templates.category')">
          <el-select v-model="filters.category" :placeholder="$t('common.all')" clearable style="width: 150px">
            <el-option :label="$t('templates.verification')" value="verification" />
            <el-option :label="$t('templates.notification')" value="notification" />
            <el-option :label="$t('templates.marketing')" value="marketing" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('common.status')">
          <el-select v-model="filters.status" :placeholder="$t('common.all')" clearable style="width: 150px">
            <el-option :label="$t('templates.pending')" value="pending" />
            <el-option :label="$t('templates.approved')" value="approved" />
            <el-option :label="$t('templates.rejected')" value="rejected" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('common.search')">
          <el-input v-model="filters.keyword" :placeholder="$t('templates.templateName')" clearable style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">{{ $t('smsRecords.query') }}</el-button>
          <el-button @click="resetFilters">{{ $t('common.reset') }}</el-button>
        </el-form-item>
      </el-form>

      <!-- 表格 -->
      <el-table :data="templates" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" :label="$t('templates.templateName')" min-width="150" />
        <el-table-column prop="category" :label="$t('templates.category')" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.category === 'verification'" type="success">{{ $t('templates.verification') }}</el-tag>
            <el-tag v-else-if="row.category === 'notification'">{{ $t('templates.notification') }}</el-tag>
            <el-tag v-else type="warning">{{ $t('templates.marketing') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="content" :label="$t('templates.content')" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status" :label="$t('common.status')" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'pending'" type="info">{{ $t('templates.pending') }}</el-tag>
            <el-tag v-else-if="row.status === 'approved'" type="success">{{ $t('templates.approved') }}</el-tag>
            <el-tag v-else-if="row.status === 'rejected'" type="danger">{{ $t('templates.rejected') }}</el-tag>
            <el-tag v-else type="info">{{ $t('templates.disabled') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="usage_count" :label="$t('templates.usageCount')" width="100" />
        <el-table-column prop="created_at" :label="$t('common.createdAt')" width="180" />
        <el-table-column :label="$t('common.action')" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewTemplate(row)">{{ $t('common.view') }}</el-button>
            <el-button link type="primary" size="small" @click="editTemplate(row)" 
              v-if="row.status === 'pending' || row.status === 'rejected'">{{ $t('common.edit') }}</el-button>
            <el-button link type="danger" size="small" @click="deleteTemplate(row)">{{ $t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadData"
          @size-change="loadData"
        />
      </div>
    </el-card>

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="600px">
      <el-form :model="formData" :rules="rules" ref="formRef" label-width="100px">
        <el-form-item :label="$t('templates.templateName')" prop="name">
          <el-input v-model="formData.name" :placeholder="$t('templates.pleaseEnterName')" />
        </el-form-item>
        <el-form-item :label="$t('templates.category')" prop="category">
          <el-select v-model="formData.category" :placeholder="$t('common.all')" style="width: 100%">
            <el-option :label="$t('templates.verification')" value="verification" />
            <el-option :label="$t('templates.notification')" value="notification" />
            <el-option :label="$t('templates.marketing')" value="marketing" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('templates.content')" prop="content">
          <el-input
            v-model="formData.content"
            type="textarea"
            :rows="5"
            :placeholder="$t('templates.contentPlaceholder')"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
        <el-form-item :label="$t('templates.variables')">
          <el-tag
            v-for="(variable, index) in formData.variables"
            :key="index"
            closable
            @close="removeVariable(index)"
            style="margin-right: 8px"
          >
            {{ variable }}
          </el-tag>
          <el-input
            v-if="inputVisible"
            ref="inputRef"
            v-model="inputValue"
            size="small"
            style="width: 100px"
            @keyup.enter="handleInputConfirm"
            @blur="handleInputConfirm"
          />
          <el-button v-else size="small" @click="showInput">+ {{ $t('templates.addVariable') }}</el-button>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { getTemplates, createTemplate, updateTemplate, deleteTemplate as delTemplate, type Template } from '@/api/template'

const { t } = useI18n()
const loading = ref(false)
const templates = ref<Template[]>([])
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const filters = reactive({
  category: '',
  status: '',
  keyword: ''
})

const dialogVisible = ref(false)
const dialogTitle = ref('')
const isEdit = ref(false)
const editId = ref(0)
const submitting = ref(false)

const formRef = ref<FormInstance>()
const formData = reactive({
  name: '',
  category: 'notification',
  content: '',
  variables: [] as string[]
})

const rules = {
  name: [{ required: true, message: () => t('templates.pleaseEnterName'), trigger: 'blur' }],
  category: [{ required: true, message: () => t('templates.pleaseSelectCategory'), trigger: 'change' }],
  content: [{ required: true, message: () => t('templates.pleaseEnterContent'), trigger: 'blur' }]
}

// 变量输入
const inputVisible = ref(false)
const inputValue = ref('')
const inputRef = ref()

const loadData = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...filters
    }
    const res = await getTemplates(params)
    templates.value = res.items
    pagination.total = res.total
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  filters.category = ''
  filters.status = ''
  filters.keyword = ''
  pagination.page = 1
  loadData()
}

const showCreateDialog = () => {
  isEdit.value = false
  dialogTitle.value = t('templates.addTemplate')
  resetForm()
  dialogVisible.value = true
}

const editTemplate = (row: Template) => {
  isEdit.value = true
  dialogTitle.value = t('templates.editTemplate')
  editId.value = row.id
  formData.name = row.name
  formData.category = row.category
  formData.content = row.content
  formData.variables = row.variables || []
  dialogVisible.value = true
}

const viewTemplate = (row: Template) => {
  const statusLabels: Record<string, string> = {
    pending: t('templates.pending'),
    approved: t('templates.approved'),
    rejected: t('templates.rejected')
  }
  ElMessageBox.alert(
    `<strong>${t('templates.content')}：</strong><br/>${row.content}<br/><br/>
     <strong>${t('templates.variables')}：</strong>${row.variables?.join(', ') || t('common.none')}<br/>
     <strong>${t('common.status')}：</strong>${statusLabels[row.status] || row.status}<br/>
     ${row.reject_reason ? `<strong>${t('templates.rejectReason')}：</strong>${row.reject_reason}` : ''}`,
    row.name,
    {
      dangerouslyUseHTMLString: true,
      confirmButtonText: t('common.close')
    }
  )
}

const submitForm = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    
    submitting.value = true
    try {
      const data = {
        name: formData.name,
        category: formData.category,
        content: formData.content,
        variables: formData.variables.length > 0 ? formData.variables : undefined
      }
      
      if (isEdit.value) {
        await updateTemplate(editId.value, data)
        ElMessage.success(t('templates.updateSuccess'))
      } else {
        await createTemplate(data)
        ElMessage.success(t('templates.createSuccess'))
      }
      
      dialogVisible.value = false
      loadData()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('common.failed'))
    } finally {
      submitting.value = false
    }
  })
}

const deleteTemplate = (row: Template) => {
  ElMessageBox.confirm(t('templates.confirmDelete', { name: row.name }), t('common.info'), {
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel'),
    type: 'warning'
  }).then(async () => {
    try {
      await delTemplate(row.id)
      ElMessage.success(t('templates.deleteSuccess'))
      loadData()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('common.failed'))
    }
  }).catch(() => {})
}

const showInput = () => {
  inputVisible.value = true
  nextTick(() => {
    inputRef.value?.focus()
  })
}

const handleInputConfirm = () => {
  if (inputValue.value && !formData.variables.includes(inputValue.value)) {
    formData.variables.push(inputValue.value)
  }
  inputVisible.value = false
  inputValue.value = ''
}

const removeVariable = (index: number) => {
  formData.variables.splice(index, 1)
}

const resetForm = () => {
  formData.name = ''
  formData.category = 'notification'
  formData.content = ''
  formData.variables = []
  formRef.value?.resetFields()
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.templates-page {
  width: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.filter-form {
  margin-bottom: 20px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
