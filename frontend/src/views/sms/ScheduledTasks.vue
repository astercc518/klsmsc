<template>
  <div class="scheduled-tasks">
    <el-card class="stats-card">
      <div class="stats-grid">
        <div class="stat-item">
          <div class="stat-value">{{ stats.total_tasks }}</div>
          <div class="stat-label">{{ $t('scheduledTasks.totalTasks') }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-value" style="color: #409eff">{{ stats.pending_tasks }}</div>
          <div class="stat-label">{{ $t('scheduledTasks.pending') }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-value" style="color: #67c23a">{{ stats.completed_tasks }}</div>
          <div class="stat-label">{{ $t('scheduledTasks.completed') }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-value" style="color: #f56c6c">{{ stats.failed_tasks }}</div>
          <div class="stat-label">{{ $t('scheduledTasks.failed') }}</div>
        </div>
      </div>
    </el-card>

    <el-card class="main-card">
      <template #header>
        <div class="card-header">
          <span>{{ $t('scheduledTasks.title') }}</span>
          <el-button type="primary" @click="showCreateDialog">{{ $t('scheduledTasks.createTask') }}</el-button>
        </div>
      </template>

      <el-form :inline="true" :model="searchForm" class="search-form">
        <el-form-item :label="$t('common.status')">
          <el-select v-model="searchForm.status" :placeholder="$t('common.all')" clearable @change="loadTasks">
            <el-option :label="$t('scheduledTasks.pending')" value="pending" />
            <el-option :label="$t('scheduledTasks.running')" value="running" />
            <el-option :label="$t('scheduledTasks.completed')" value="completed" />
            <el-option :label="$t('scheduledTasks.failed')" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('scheduledTasks.frequency')">
          <el-select v-model="searchForm.frequency" :placeholder="$t('common.all')" clearable @change="loadTasks">
            <el-option :label="$t('scheduledTasks.once')" value="once" />
            <el-option :label="$t('scheduledTasks.daily')" value="daily" />
            <el-option :label="$t('scheduledTasks.weekly')" value="weekly" />
            <el-option :label="$t('scheduledTasks.monthly')" value="monthly" />
          </el-select>
        </el-form-item>
      </el-form>

      <el-table :data="tasks" v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="task_name" :label="$t('scheduledTasks.taskName')" min-width="150" />
        <el-table-column :label="$t('scheduledTasks.frequency')" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.frequency === 'once'" type="info">{{ $t('scheduledTasks.once') }}</el-tag>
            <el-tag v-else-if="row.frequency === 'daily'" type="success">{{ $t('scheduledTasks.daily') }}</el-tag>
            <el-tag v-else-if="row.frequency === 'weekly'" type="warning">{{ $t('scheduledTasks.weekly') }}</el-tag>
            <el-tag v-else type="danger">{{ $t('scheduledTasks.monthly') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('scheduledTasks.scheduledTime')" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.scheduled_time) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.status')" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'pending'" type="info">{{ $t('scheduledTasks.pending') }}</el-tag>
            <el-tag v-else-if="row.status === 'running'">{{ $t('scheduledTasks.running') }}</el-tag>
            <el-tag v-else-if="row.status === 'completed'" type="success">{{ $t('scheduledTasks.completed') }}</el-tag>
            <el-tag v-else type="danger">{{ $t('scheduledTasks.failed') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('scheduledTasks.executionStats')" width="120">
          <template #default="{ row }">
            <span style="color: #67c23a">{{ row.success_runs }}</span> / 
            <span style="color: #f56c6c">{{ row.failed_runs }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="executeTask(row.id)" 
              :disabled="row.status === 'running'">{{ $t('common.execute') }}</el-button>
            <el-button link type="primary" size="small" @click="showEditDialog(row)">{{ $t('common.edit') }}</el-button>
            <el-button link type="danger" size="small" @click="deleteTask(row.id)">{{ $t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="pagination.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="loadTasks"
        @size-change="loadTasks"
        style="margin-top: 20px; text-align: right"
      />
    </el-card>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="600px"
      @close="resetForm"
    >
      <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
        <el-form-item :label="$t('scheduledTasks.taskName')" prop="task_name">
          <el-input v-model="form.task_name" :placeholder="$t('scheduledTasks.pleaseEnterTaskName')" />
        </el-form-item>
        <el-form-item :label="$t('scheduledTasks.phoneNumbers')" prop="phone_numbers">
          <el-input
            v-model="phoneNumbersText"
            type="textarea"
            :rows="4"
            :placeholder="$t('scheduledTasks.phoneNumbersPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="$t('scheduledTasks.smsContent')" prop="content">
          <el-input v-model="form.content" type="textarea" :rows="3" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item :label="$t('scheduledTasks.frequency')" prop="frequency">
          <el-select v-model="form.frequency">
            <el-option :label="$t('scheduledTasks.once')" value="once" />
            <el-option :label="$t('scheduledTasks.daily')" value="daily" />
            <el-option :label="$t('scheduledTasks.weekly')" value="weekly" />
            <el-option :label="$t('scheduledTasks.monthly')" value="monthly" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('scheduledTasks.scheduledTime')" prop="scheduled_time">
          <el-date-picker
            v-model="form.scheduled_time"
            type="datetime"
            :placeholder="$t('scheduledTasks.pleaseSelectTime')"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DDTHH:mm:ss"
          />
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
import { ref, reactive, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { scheduledTaskApi } from '@/api/scheduledTask'
import type { FormInstance } from 'element-plus'

const { t } = useI18n()
const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()

const stats = reactive({
  total_tasks: 0,
  pending_tasks: 0,
  running_tasks: 0,
  completed_tasks: 0,
  failed_tasks: 0
})

const searchForm = reactive({
  status: '',
  frequency: ''
})

const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
})

const tasks = ref<any[]>([])

const form = reactive({
  id: 0,
  task_name: '',
  phone_numbers: [] as string[],
  content: '',
  frequency: 'once',
  scheduled_time: '',
  sender_id: ''
})

const phoneNumbersText = ref('')

const rules = {
  task_name: [{ required: true, message: () => t('scheduledTasks.pleaseEnterTaskName'), trigger: 'blur' }],
  phone_numbers: [{ required: true, message: () => t('scheduledTasks.pleaseEnterPhone'), trigger: 'blur' }],
  content: [{ required: true, message: () => t('scheduledTasks.pleaseEnterContent'), trigger: 'blur' }],
  frequency: [{ required: true, message: () => t('scheduledTasks.pleaseSelectFrequency'), trigger: 'change' }],
  scheduled_time: [{ required: true, message: () => t('scheduledTasks.pleaseSelectTime'), trigger: 'change' }]
}

const formatDateTime = (dateStr: string) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const loadStats = async () => {
  try {
    const res = await scheduledTaskApi.getStats()
    Object.assign(stats, res.data)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.loadFailed'))
  }
}

const loadTasks = async () => {
  loading.value = true
  try {
    const res = await scheduledTaskApi.list({
      page: pagination.page,
      page_size: pagination.page_size,
      status: searchForm.status || undefined,
      frequency: searchForm.frequency || undefined
    })
    tasks.value = res.data.items
    pagination.total = res.data.total
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.failed'))
  } finally {
    loading.value = false
  }
}

const showCreateDialog = () => {
  dialogTitle.value = t('scheduledTasks.createTask')
  dialogVisible.value = true
}

const showEditDialog = (row: any) => {
  dialogTitle.value = t('scheduledTasks.editTask')
  form.id = row.id
  form.task_name = row.task_name
  form.content = row.content
  form.frequency = row.frequency
  form.scheduled_time = row.scheduled_time
  phoneNumbersText.value = row.phone_numbers.join('\n')
  dialogVisible.value = true
}

const submitForm = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return

    // 解析手机号
    const phones = phoneNumbersText.value.split('\n').filter(p => p.trim())
    if (phones.length === 0) {
      ElMessage.error(t('scheduledTasks.pleaseEnterPhone'))
      return
    }
    if (phones.length > 1000) {
      ElMessage.error(t('scheduledTasks.maxPhoneLimit'))
      return
    }

    submitting.value = true
    try {
      const data = {
        ...form,
        phone_numbers: phones
      }
      
      if (form.id) {
        await scheduledTaskApi.update(form.id, data)
        ElMessage.success(t('scheduledTasks.updateSuccess'))
      } else {
        await scheduledTaskApi.create(data)
        ElMessage.success(t('scheduledTasks.createSuccess'))
      }
      
      dialogVisible.value = false
      loadTasks()
      loadStats()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('common.failed'))
    } finally {
      submitting.value = false
    }
  })
}

const executeTask = async (id: number) => {
  try {
    await scheduledTaskApi.execute(id)
    ElMessage.success(t('scheduledTasks.executeStarted'))
    loadTasks()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.failed'))
  }
}

const deleteTask = async (id: number) => {
  try {
    await ElMessageBox.confirm(t('scheduledTasks.confirmDelete'), t('common.info'), {
      type: 'warning'
    })
    await scheduledTaskApi.delete(id)
    ElMessage.success(t('scheduledTasks.deleteSuccess'))
    loadTasks()
    loadStats()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || t('common.failed'))
    }
  }
}

const resetForm = () => {
  formRef.value?.resetFields()
  form.id = 0
  phoneNumbersText.value = ''
}

onMounted(() => {
  loadStats()
  loadTasks()
})
</script>

<style scoped>
.scheduled-tasks {
  width: 100%;
}

.stats-card {
  margin-bottom: 20px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.stat-item {
  text-align: center;
}

.stat-value {
  font-size: 32px;
  font-weight: bold;
  color: #303133;
}

.stat-label {
  margin-top: 8px;
  font-size: 14px;
  color: #909399;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.search-form {
  margin-bottom: 20px;
}
</style>
