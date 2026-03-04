<template>
  <div class="sub-accounts">
    <el-card class="stats-card">
      <div class="stats-grid">
        <div class="stat-item">
          <div class="stat-value">{{ stats.total_sub_accounts }}</div>
          <div class="stat-label">{{ $t('subAccounts.totalSubs') }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-value" style="color: #67c23a">{{ stats.active_sub_accounts }}</div>
          <div class="stat-label">{{ $t('subAccounts.activeSubs') }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-value" style="color: #e6a23c">{{ stats.suspended_sub_accounts }}</div>
          <div class="stat-label">{{ $t('subAccounts.suspendedSubs') }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-value" style="color: #409eff">{{ stats.total_sent_by_subs }}</div>
          <div class="stat-label">{{ $t('reports.totalSent') }}</div>
        </div>
      </div>
    </el-card>

    <el-card class="main-card">
      <template #header>
        <div class="card-header">
          <span>{{ $t('subAccounts.title') }}</span>
          <el-button type="primary" @click="showCreateDialog">{{ $t('subAccounts.createSub') }}</el-button>
        </div>
      </template>

      <el-form :inline="true" :model="searchForm" class="search-form">
        <el-form-item :label="$t('staff.role')">
          <el-select v-model="searchForm.role" :placeholder="$t('systemConfig.all')" clearable @change="loadSubAccounts">
            <el-option :label="$t('subAccounts.viewer')" value="viewer" />
            <el-option :label="$t('subAccounts.operator')" value="operator" />
            <el-option :label="$t('subAccounts.manager')" value="manager" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('common.status')">
          <el-select v-model="searchForm.status" :placeholder="$t('systemConfig.all')" clearable @change="loadSubAccounts">
            <el-option :label="$t('apiKeys.active')" value="active" />
            <el-option :label="$t('subAccounts.suspended')" value="suspended" />
            <el-option :label="$t('apiKeys.disabled')" value="disabled" />
          </el-select>
        </el-form-item>
      </el-form>

      <el-table :data="subAccounts" v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" :label="$t('subAccounts.username')" min-width="120" />
        <el-table-column prop="email" :label="$t('subAccounts.email')" min-width="150" />
        <el-table-column :label="$t('subAccounts.role')" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.role === 'viewer'" type="info">{{ $t('subAccounts.viewer') }}</el-tag>
            <el-tag v-else-if="row.role === 'operator'" type="success">{{ $t('subAccounts.operator') }}</el-tag>
            <el-tag v-else type="warning">{{ $t('subAccounts.manager') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.status')" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'active'" type="success">{{ $t('subAccounts.active') }}</el-tag>
            <el-tag v-else-if="row.status === 'suspended'" type="warning">{{ $t('subAccounts.suspended') }}</el-tag>
            <el-tag v-else type="danger">{{ $t('subAccounts.disabled') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_sent" :label="$t('subAccounts.totalSent')" width="100" />
        <el-table-column :label="$t('subAccounts.lastLogin')" width="180">
          <template #default="{ row }">
            {{ row.last_login_at ? formatDateTime(row.last_login_at) : $t('subAccounts.notLoggedIn') }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="250" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="showEditDialog(row)">{{ $t('common.edit') }}</el-button>
            <el-button link type="warning" size="small" @click="showResetPasswordDialog(row)">{{ $t('subAccounts.resetPassword') }}</el-button>
            <el-button link type="danger" size="small" @click="deleteSubAccount(row.id)">{{ $t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="pagination.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="loadSubAccounts"
        @size-change="loadSubAccounts"
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
        <el-form-item :label="$t('subAccounts.username')" prop="username">
          <el-input v-model="form.username" :placeholder="$t('subAccounts.enterUsername')" :disabled="!!form.id" />
        </el-form-item>
        <el-form-item :label="$t('subAccounts.email')" prop="email">
          <el-input v-model="form.email" :placeholder="$t('subAccounts.enterEmail')" />
        </el-form-item>
        <el-form-item v-if="!form.id" :label="$t('subAccounts.password')" prop="password">
          <el-input v-model="form.password" type="password" :placeholder="$t('subAccounts.passwordMinLength')" show-password />
        </el-form-item>
        <el-form-item :label="$t('subAccounts.role')" prop="role">
          <el-select v-model="form.role">
            <el-option :label="$t('subAccounts.viewerDesc')" value="viewer" />
            <el-option :label="$t('subAccounts.operatorDesc')" value="operator" />
            <el-option :label="$t('subAccounts.managerDesc')" value="manager" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('common.status')" prop="status" v-if="form.id">
          <el-select v-model="form.status">
            <el-option :label="$t('subAccounts.active')" value="active" />
            <el-option :label="$t('subAccounts.suspended')" value="suspended" />
            <el-option :label="$t('subAccounts.disabled')" value="disabled" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('subAccounts.rateLimit')" prop="rate_limit">
          <el-input-number v-model="form.rate_limit" :min="1" :max="10000" :placeholder="$t('subAccounts.perHour')" />
          <span style="margin-left: 10px; color: #909399">{{ $t('subAccounts.requestsPerHour') }}</span>
        </el-form-item>
        <el-form-item :label="$t('subAccounts.dailyLimit')" prop="daily_limit">
          <el-input-number v-model="form.daily_limit" :min="1" :placeholder="$t('subAccounts.smsCount')" />
          <span style="margin-left: 10px; color: #909399">{{ $t('subAccounts.messagesPerDay') }}</span>
        </el-form-item>
        <el-form-item :label="$t('subAccounts.remark')">
          <el-input v-model="form.description" type="textarea" :rows="3" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="passwordDialogVisible" :title="$t('subAccounts.resetPassword')" width="400px">
      <el-form :model="passwordForm" :rules="passwordRules" ref="passwordFormRef" label-width="80px">
        <el-form-item :label="$t('subAccounts.newPassword')" prop="password">
          <el-input v-model="passwordForm.password" type="password" :placeholder="$t('subAccounts.passwordMinLength')" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitPasswordReset" :loading="submitting">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { subAccountApi } from '@/api/subAccount'
import type { FormInstance } from 'element-plus'

const { t } = useI18n()
const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const passwordDialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const passwordFormRef = ref<FormInstance>()

const stats = reactive({
  total_sub_accounts: 0,
  active_sub_accounts: 0,
  suspended_sub_accounts: 0,
  total_sent_by_subs: 0
})

const searchForm = reactive({
  role: '',
  status: ''
})

const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
})

const subAccounts = ref<any[]>([])

const form = reactive({
  id: 0,
  username: '',
  email: '',
  password: '',
  role: 'operator',
  status: 'active',
  rate_limit: 1000,
  daily_limit: 10000,
  description: ''
})

const passwordForm = reactive({
  sub_account_id: 0,
  password: ''
})

const rules = computed(() => ({
  username: [
    { required: true, message: t('subAccounts.validation.usernameRequired'), trigger: 'blur' },
    { min: 3, max: 100, message: t('subAccounts.validation.usernameLength'), trigger: 'blur' }
  ],
  password: [
    { required: true, message: t('subAccounts.validation.passwordRequired'), trigger: 'blur' },
    { min: 8, message: t('subAccounts.validation.passwordMin'), trigger: 'blur' }
  ],
  role: [{ required: true, message: t('subAccounts.validation.roleRequired'), trigger: 'change' }]
}))

const passwordRules = computed(() => ({
  password: [
    { required: true, message: t('subAccounts.validation.newPasswordRequired'), trigger: 'blur' },
    { min: 8, message: t('subAccounts.validation.passwordMin'), trigger: 'blur' }
  ]
}))

const formatDateTime = (dateStr: string) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const loadStats = async () => {
  try {
    const res = await subAccountApi.getStats()
    Object.assign(stats, res.data)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('subAccounts.loadStatsFailed'))
  }
}

const loadSubAccounts = async () => {
  loading.value = true
  try {
    const res = await subAccountApi.list({
      page: pagination.page,
      page_size: pagination.page_size,
      role: searchForm.role || undefined,
      status: searchForm.status || undefined
    })
    subAccounts.value = res.data.items
    pagination.total = res.data.total
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

const showCreateDialog = () => {
  dialogTitle.value = t('subAccounts.createSubAccount')
  dialogVisible.value = true
}

const showEditDialog = (row: any) => {
  dialogTitle.value = t('subAccounts.editSubAccount')
  form.id = row.id
  form.username = row.username
  form.email = row.email
  form.role = row.role
  form.status = row.status
  form.rate_limit = row.rate_limit
  form.daily_limit = row.daily_limit
  form.description = row.description
  dialogVisible.value = true
}

const showResetPasswordDialog = (row: any) => {
  passwordForm.sub_account_id = row.id
  passwordDialogVisible.value = true
}

const submitForm = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return

    submitting.value = true
    try {
      if (form.id) {
        await subAccountApi.update(form.id, form)
        ElMessage.success(t('common.updateSuccess'))
      } else {
        await subAccountApi.create(form)
        ElMessage.success(t('common.createSuccess'))
      }
      
      dialogVisible.value = false
      loadSubAccounts()
      loadStats()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('common.operationFailed'))
    } finally {
      submitting.value = false
    }
  })
}

const submitPasswordReset = async () => {
  if (!passwordFormRef.value) return
  await passwordFormRef.value.validate(async (valid) => {
    if (!valid) return

    submitting.value = true
    try {
      await subAccountApi.resetPassword(passwordForm.sub_account_id, passwordForm.password)
      ElMessage.success(t('subAccounts.passwordResetSuccess'))
      passwordDialogVisible.value = false
      passwordForm.password = ''
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('subAccounts.resetFailed'))
    } finally {
      submitting.value = false
    }
  })
}

const deleteSubAccount = async (id: number) => {
  try {
    await ElMessageBox.confirm(t('subAccounts.confirmDelete'), t('common.tip'), {
      type: 'warning'
    })
    await subAccountApi.delete(id)
    ElMessage.success(t('common.deleteSuccess'))
    loadSubAccounts()
    loadStats()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || t('common.deleteFailed'))
    }
  }
}

const resetForm = () => {
  formRef.value?.resetFields()
  form.id = 0
  form.password = ''
}

onMounted(() => {
  loadStats()
  loadSubAccounts()
})
</script>

<style scoped>
.sub-accounts {
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
