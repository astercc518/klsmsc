<template>
  <div class="page-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">{{ $t('staff.title') }}</h1>
        <p class="page-desc">{{ $t('staff.pageDesc') }}</p>
      </div>
      <div class="header-right">
        <el-button type="primary" @click="showCreateDialog" class="add-btn">
          <el-icon><Plus /></el-icon>
          {{ $t('staff.addStaff') }}
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon blue">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="8" r="4" stroke="currentColor" stroke-width="2"/><path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" stroke="currentColor" stroke-width="2"/></svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ staffList.length }}</span>
          <span class="stat-label">{{ $t('staff.totalStaff') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon green">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M22 4 12 14.01l-3-3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ staffList.filter(s => s.status === 'active').length }}</span>
          <span class="stat-label">{{ $t('staff.activeStaff') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon purple">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" stroke="currentColor" stroke-width="2"/><circle cx="9" cy="7" r="4" stroke="currentColor" stroke-width="2"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" stroke="currentColor" stroke-width="2"/></svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ staffList.filter(s => s.role === 'sales').length }}</span>
          <span class="stat-label">{{ $t('staff.salesStaff') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon orange">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ staffList.filter(s => s.tg_id || s.tg_username).length }}</span>
          <span class="stat-label">{{ $t('staff.tgConfigured') }}</span>
        </div>
      </div>
    </div>

    <!-- 筛选和表格卡片 -->
    <div class="main-card">
      <div class="card-header">
        <div class="filter-section">
          <el-select v-model="filters.role" :placeholder="$t('staff.allRoles')" clearable style="width: 130px" @change="loadData">
            <el-option :label="$t('roles.sales')" value="sales" />
            <el-option :label="$t('roles.tech')" value="tech" />
            <el-option :label="$t('roles.finance')" value="finance" />
            <el-option :label="$t('roles.admin')" value="admin" />
          </el-select>
          <el-select v-model="filters.status" :placeholder="$t('customers.allStatus')" clearable style="width: 130px" @change="loadData">
            <el-option :label="$t('staff.normal')" value="active" />
            <el-option :label="$t('staff.disabled')" value="inactive" />
            <el-option :label="$t('staff.locked')" value="locked" />
          </el-select>
          <el-button @click="loadData" :icon="Refresh">{{ $t('common.refresh') }}</el-button>
          <el-button type="warning" :loading="syncing" @click="showClearTgDialog" :icon="Connection">
            {{ $t('staff.clearStaffTg') }}
          </el-button>
        </div>
      </div>

      <!-- 数据表格 -->
      <el-table :data="staffList" v-loading="loading" stripe class="data-table">
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column prop="username" :label="$t('staff.username')" min-width="120">
          <template #default="{ row }">
            <div class="user-cell">
              <div class="avatar">{{ (row.real_name || row.username || '?').charAt(0).toUpperCase() }}</div>
              <div class="user-info">
                <span class="username">{{ row.username }}</span>
                <span class="realname">{{ row.real_name || '-' }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="role" :label="$t('staff.role')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="getRoleType(row.role)" size="small" effect="light">{{ getRoleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="tg_username" :label="$t('staff.telegram')" min-width="150">
          <template #default="{ row }">
            <div class="tg-cell" v-if="row.tg_username || row.tg_id">
              <span class="tg-name">{{ row.tg_username ? `@${row.tg_username}` : '-' }}</span>
              <el-tag v-if="row.tg_id" type="success" size="small" effect="plain">{{ $t('staff.bound') }}</el-tag>
              <el-tag v-else-if="row.tg_username" type="warning" size="small" effect="plain">{{ $t('staff.pending') }}</el-tag>
            </div>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="commission_rate" :label="$t('staff.commission')" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.commission_rate" class="commission">{{ row.commission_rate }}%</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="monthly_performance" :label="$t('staff.monthlyPerformance')" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.monthly_performance" class="money">${{ row.monthly_performance.toFixed(2) }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="monthly_commission" :label="$t('staff.monthlyCommission')" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.monthly_commission" class="money">${{ row.monthly_commission.toFixed(2) }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('common.status')" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'danger'" size="small" effect="light">
              {{ row.status === 'active' ? $t('staff.normal') : row.status === 'locked' ? $t('staff.locked') : $t('staff.disabled') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" :label="$t('staff.lastLogin')" width="160">
          <template #default="{ row }">
            <span class="time-text">{{ formatDate(row.last_login_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="180" fixed="right" align="center">
          <template #default="{ row }">
            <div class="action-btns">
              <el-button link type="primary" size="small" @click="editStaff(row)">{{ $t('common.edit') }}</el-button>
              <el-button link type="success" size="small" @click="loginAsStaff(row)" v-if="row.status === 'active'">
                <el-icon style="margin-right: 2px"><User /></el-icon>
                {{ $t('staff.loginAs') }}
              </el-button>
              <el-dropdown trigger="click" v-if="row.role !== 'super_admin'">
                <el-button link type="primary" size="small">{{ $t('common.more') }}</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item @click="resetPassword(row)">{{ $t('staff.resetPassword') }}</el-dropdown-item>
                    <el-dropdown-item v-if="row.tg_id" @click="unbindStaffTelegram(row)">{{ $t('staff.unbindTg') }}</el-dropdown-item>
                    <el-dropdown-item @click="toggleStatus(row)">
                      {{ row.status === 'active' ? $t('staff.disableAccount') : $t('staff.enableAccount') }}
                    </el-dropdown-item>
                    <el-dropdown-item divided @click="showOffboardDialog(row)" style="color: #f56c6c">{{ $t('staff.offboard') }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog 
      v-model="dialogVisible" 
      :title="isEdit ? $t('staff.editStaff') : $t('staff.addStaff')"
      width="500px"
      destroy-on-close
    >
      <el-form :model="form" :rules="rules" ref="formRef" label-width="80px">
        <el-form-item :label="$t('staff.username')" prop="username" v-if="!isEdit">
          <el-input v-model="form.username" :placeholder="$t('staff.username')" />
        </el-form-item>
        <el-form-item :label="$t('login.password')" prop="password" v-if="!isEdit">
          <el-input v-model="form.password" type="password" :placeholder="$t('staff.loginPassword')" show-password>
            <template #append>
              <el-button size="small" @click="form.password = generatePassword()">{{ $t('staff.autoGenerate') }}</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item :label="$t('login.password')" prop="password" v-if="isEdit">
          <el-input v-model="form.password" type="password" :placeholder="$t('staff.passwordLeaveEmpty')" show-password>
            <template #append>
              <el-button size="small" @click="form.password = generatePassword()">{{ $t('staff.autoGenerate') }}</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item :label="$t('staff.realName')" prop="real_name">
          <el-input v-model="form.real_name" :placeholder="$t('staff.realName')" />
        </el-form-item>
        <el-form-item :label="$t('staff.role')" prop="role">
          <el-select v-model="form.role" :placeholder="$t('staff.selectRole')">
            <el-option :label="$t('roles.sales')" value="sales" />
            <el-option :label="$t('roles.tech')" value="tech" />
            <el-option :label="$t('roles.finance')" value="finance" />
            <el-option :label="$t('roles.admin')" value="admin" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('staff.telegram')" prop="tg_username">
          <el-input v-model="form.tg_username" :placeholder="$t('staff.telegramUsername')" />
          <div class="form-hint">{{ $t('staff.telegramUsernameHint') }}</div>
        </el-form-item>
        <el-form-item :label="$t('staff.commissionRate')" prop="commission_rate">
          <el-input-number v-model="form.commission_rate" :min="0" :max="100" :precision="2" placeholder="0-100" style="width: 100%">
            <template #suffix>%</template>
          </el-input-number>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 离职处理对话框 -->
    <el-dialog
      v-model="offboardDialogVisible"
      :title="$t('staff.offboard')"
      width="480px"
      destroy-on-close
    >
      <div class="offboard-preview">
        <p class="offboard-desc">{{ $t('staff.offboardDesc', { name: offboardTarget?.real_name || offboardTarget?.username }) }}</p>
        <el-skeleton v-if="!offboardPreview" :rows="2" animated class="mb-12" />
        <el-descriptions v-if="offboardPreview" :column="1" border size="small">
          <el-descriptions-item :label="$t('staff.offboardCustomers')">{{ offboardPreview.customer_count }}</el-descriptions-item>
          <el-descriptions-item :label="$t('staff.offboardInvites')">{{ offboardPreview.unused_invite_count }}</el-descriptions-item>
        </el-descriptions>
        <el-form-item v-if="offboardPreview && (offboardPreview.customer_count > 0 || offboardPreview.unused_invite_count > 0) && activeSalesList.length" :label="$t('staff.reassignTo')" class="mt-12">
          <el-select v-model="offboardReassignId" :placeholder="$t('staff.selectReassignSales')" clearable style="width: 100%">
            <el-option
              v-for="s in activeSalesList"
              :key="s.id"
              :label="`${s.real_name || s.username} (${s.username})`"
              :value="s.id"
            />
          </el-select>
          <div class="offboard-hint">{{ $t('staff.offboardReassignHint') }}</div>
        </el-form-item>
      </div>
      <template #footer>
        <el-button @click="offboardDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="danger" @click="submitOffboard" :loading="offboarding">
          {{ $t('staff.offboardConfirm') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog
      v-model="resetDialogVisible"
      :title="resetTargetStaff ? `${$t('staff.resetPassword')} - ${resetTargetStaff.real_name || resetTargetStaff.username}` : $t('staff.resetPassword')"
      width="460px"
      @opened="focusResetPasswordInput"
      @closed="resetTargetStaff = null"
    >
      <el-form :model="resetForm" ref="resetFormRef" label-width="100px">
        <el-form-item :label="$t('staff.newPassword')" prop="password" :rules="passwordRules">
          <div class="reset-pwd-block">
            <!-- 密码预览区：有内容时完整展示，便于查看和复制 -->
            <div v-if="resetForm.password" class="reset-pwd-preview">
              <code class="pwd-display">{{ resetForm.password }}</code>
              <el-button size="small" type="primary" text @click="copyResetPassword" class="pwd-copy-inline">
                <el-icon><DocumentCopy /></el-icon>
                {{ $t('common.copy') }}
              </el-button>
            </div>
            <el-input
              ref="resetPasswordInputRef"
              v-model="resetForm.password"
              type="password"
              :placeholder="$t('staff.minSixChars')"
              show-password
              autocomplete="new-password"
              class="reset-pwd-input"
            />
            <div class="reset-pwd-actions">
              <el-button size="small" class="pwd-action-btn" @click="handleAutoGenerate">
                {{ $t('staff.autoGenerate') }}
              </el-button>
              <el-button
                v-if="resetForm.password"
                size="small"
                class="pwd-action-btn"
                @click="copyResetPassword"
                :title="$t('common.copy')"
              >
                <el-icon><DocumentCopy /></el-icon>
              </el-button>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitResetPassword" :loading="resetting">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, User, Connection, DocumentCopy } from '@element-plus/icons-vue'
import request from '@/api/index'
import { formatDate } from '@/utils/date'

const { t } = useI18n()
const router = useRouter()

interface Staff {
  id: number
  username: string
  real_name: string
  tg_username?: string
  role: string
  status: string
  tg_id?: number
  commission_rate?: number
  monthly_performance?: number
  monthly_commission?: number
  last_login_at?: string
  created_at?: string
}

const loading = ref(false)
const staffList = ref<Staff[]>([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const currentStaffId = ref<number | null>(null)
const submitting = ref(false)

const resetDialogVisible = ref(false)
const resetForm = ref({ password: '' })
const resetting = ref(false)
const syncing = ref(false)
const offboardDialogVisible = ref(false)
const offboardPreview = ref<{ customer_count: number; unused_invite_count: number } | null>(null)
const offboardTarget = ref<Staff | null>(null)
const offboardReassignId = ref<number | null>(null)
const offboarding = ref(false)
const activeSalesList = ref<Staff[]>([])

const filters = ref({
  role: '',
  status: ''
})

const form = ref({
  username: '',
  password: '',
  real_name: '',
  role: 'sales',
  tg_username: '',
  commission_rate: 0
})

const formRef = ref()
const resetFormRef = ref()

const rules = computed(() => ({
  username: [{ required: true, message: () => t('staff.pleaseEnterUsername'), trigger: 'blur' }],
  password: isEdit.value
    ? [{ min: 6, message: () => t('staff.passwordMinSix'), trigger: 'blur' }]  // 编辑时可选，填了则至少6位
    : [{ required: true, message: () => t('staff.pleaseEnterPassword'), trigger: 'blur', min: 6 }],
  real_name: [{ required: true, message: () => t('staff.pleaseEnterRealName'), trigger: 'blur' }],
  role: [{ required: true, message: () => t('staff.pleaseSelectRole'), trigger: 'change' }]
}))

const passwordRules = [
  { required: true, message: () => t('staff.pleaseEnterNewPassword'), trigger: 'blur' },
  { min: 6, message: () => t('staff.passwordMinSix'), trigger: 'blur' }
]

// 生成随机密码（12位，含大小写字母和数字）
const generatePassword = () => {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789'
  let pwd = ''
  for (let i = 0; i < 12; i++) {
    pwd += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  return pwd
}

const getRoleLabel = (role: string) => {
  const map: Record<string, string> = {
    super_admin: t('roles.superAdmin'),
    admin: t('roles.admin'),
    sales: t('roles.sales'),
    tech: t('roles.tech'),
    finance: t('roles.finance')
  }
  return map[role] || role
}

const getRoleType = (role: string) => {
  const map: Record<string, string> = {
    super_admin: 'danger',
    admin: 'warning',
    sales: 'primary',
    tech: 'success',
    finance: 'info'
  }
  return map[role] || 'info'
}

const syncInactiveTelegram = async (username?: string) => {
  syncing.value = true
  try {
    const params = username ? { username } : {}
    const res = await request.post('/admin/users/sync-inactive-telegram', null, { params })
    if (res?.success) {
      ElMessage.success(res.message || t('staff.syncInactiveSuccess', { count: res.cleared_count ?? 0 }))
      await loadData()
    }
  } catch (e: any) {
    ElMessage.error(e.message || t('staff.syncInactiveFailed'))
  } finally {
    syncing.value = false
  }
}

/** 单行解除 TG 绑定（与顶部「清除员工TG绑定」同一接口） */
const unbindStaffTelegram = async (row: Staff) => {
  try {
    await ElMessageBox.confirm(
      t('staff.unbindTgConfirm', { name: row.real_name || row.username }),
      t('staff.unbindTg'),
      { type: 'warning', confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel') }
    )
    await syncInactiveTelegram(row.username)
  } catch {
    /* 取消 */
  }
}

const showClearTgDialog = async () => {
  try {
    const { value } = await ElMessageBox.prompt(
      t('staff.clearStaffTgPrompt'),
      t('staff.clearStaffTg'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        inputPlaceholder: 'KL04',
        inputValidator: () => true,
      }
    )
    await syncInactiveTelegram(value?.trim() || undefined)
  } catch {
    // 用户取消
  }
}

const loadData = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (filters.value.role) params.append('role', filters.value.role)
    if (filters.value.status) params.append('status', filters.value.status)
    
    const res = await request.get(`/admin/users?${params.toString()}`)
    if (res.success) {
      staffList.value = res.users || []
    }
  } catch (e: any) {
    ElMessage.error(e.message || t('staff.loadFailed'))
  } finally {
    loading.value = false
  }
}

const showCreateDialog = () => {
  isEdit.value = false
  currentStaffId.value = null
  form.value = {
    username: '',
    password: '',
    real_name: '',
    role: 'sales',
    tg_username: '',
    commission_rate: 0
  }
  dialogVisible.value = true
}

const editStaff = (row: Staff) => {
  isEdit.value = true
  currentStaffId.value = row.id
  form.value = {
    username: row.username,
    password: '',
    real_name: row.real_name,
    role: row.role,
    tg_username: row.tg_username || '',
    commission_rate: row.commission_rate || 0
  }
  dialogVisible.value = true
}

const submitForm = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  
  submitting.value = true
  try {
    if (isEdit.value && currentStaffId.value) {
      const payload: Record<string, unknown> = {
        real_name: form.value.real_name,
        role: form.value.role,
        tg_username: form.value.tg_username || null,
        commission_rate: form.value.commission_rate || 0
      }
      if (form.value.password?.trim()) {
        payload.password = form.value.password.trim()
      }
      const res = await request.put(`/admin/users/${currentStaffId.value}`, payload) as { message?: string }
      ElMessage.success(res?.message || t('staff.updateSuccess'))
    } else {
      await request.post('/admin/users', form.value)
      ElMessage.success(t('staff.createSuccess'))
    }
    dialogVisible.value = false
    loadData()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || e.message || t('staff.operationFailed'))
  } finally {
    submitting.value = false
  }
}

const resetTargetStaff = ref<Staff | null>(null)
const resetPasswordInputRef = ref<{ focus: () => void } | null>(null)

const resetPassword = (row: Staff) => {
  currentStaffId.value = row.id
  resetTargetStaff.value = row
  resetForm.value = { password: '' }
  resetDialogVisible.value = true
}

const focusResetPasswordInput = () => {
  nextTick(() => resetPasswordInputRef.value?.focus?.())
}

const copyResetPassword = () => {
  if (!resetForm.value.password) return
  navigator.clipboard.writeText(resetForm.value.password).then(() => {
    ElMessage.success(t('common.copied'))
  })
}

const handleAutoGenerate = () => {
  const pwd = generatePassword()
  resetForm.value.password = pwd
  navigator.clipboard.writeText(pwd).then(() => {
    ElMessage.success(t('staff.autoGenAndCopied'))
  })
}

const submitResetPassword = async () => {
  try {
    await resetFormRef.value?.validate()
  } catch {
    return
  }
  
  resetting.value = true
  try {
    await request.put(`/admin/users/${currentStaffId.value}`, {
      password: resetForm.value.password
    })
    ElMessage.success(t('staff.passwordResetSuccess'))
    resetDialogVisible.value = false
    resetTargetStaff.value = null
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || t('staff.resetFailed'))
  } finally {
    resetting.value = false
  }
}

const toggleStatus = async (row: Staff) => {
  const newStatus = row.status === 'active' ? 'inactive' : 'active'
  const action = newStatus === 'active' ? t('staff.enable') : t('staff.disable')
  
  try {
    await ElMessageBox.confirm(
      t('staff.confirmToggleStatus', { action, name: row.real_name }),
      t('staff.confirmOperation'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel')
      }
    )
    await request.put(`/admin/users/${row.id}`, { status: newStatus })
    ElMessage.success(t('staff.statusChanged', { action }))
    loadData()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.detail || t('staff.operationFailed'))
    }
  }
}

const showOffboardDialog = async (row: Staff) => {
  offboardTarget.value = row
  offboardReassignId.value = null
  offboardPreview.value = null
  offboardDialogVisible.value = true
  try {
    const res = await request.get(`/admin/users/${row.id}/offboard-preview`)
    if (res?.success && res.staff) {
      offboardPreview.value = {
        customer_count: res.customer_count ?? 0,
        unused_invite_count: res.unused_invite_count ?? 0
      }
    }
    const salesRes = await request.get('/admin/users', {
      params: { role: 'sales', status: 'active', include_monthly_stats: false },
    })
    activeSalesList.value = (salesRes?.users || []).filter((s: Staff) => s.id !== row.id)
  } catch (e: any) {
    ElMessage.error(e.message || t('staff.loadFailed'))
    offboardDialogVisible.value = false
  }
}

const submitOffboard = async () => {
  if (!offboardTarget.value) return
  offboarding.value = true
  try {
    const res = await request.post(`/admin/users/${offboardTarget.value.id}/offboard`, {
      reassign_sales_id: offboardReassignId.value || undefined
    })
    if (res?.success) {
      const msg = [
        t('staff.offboardSuccess'),
        res.customers_reassigned > 0 ? t('staff.offboardCustomersReassigned', { count: res.customers_reassigned }) : '',
        res.invites_transferred > 0 ? t('staff.offboardInvitesTransferred', { count: res.invites_transferred }) : ''
      ].filter(Boolean).join('；')
      ElMessage.success(msg)
      offboardDialogVisible.value = false
      loadData()
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || e.message || t('staff.offboardFailed'))
  } finally {
    offboarding.value = false
  }
}

const loginAsStaff = async (row: Staff) => {
  try {
    await ElMessageBox.confirm(
      t('staff.confirmLoginAs', { name: row.real_name || row.username, role: getRoleLabel(row.role) }),
      t('staff.switchIdentity'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'info'
      }
    )
    
    const res = await request.post(`/admin/users/${row.id}/impersonate`)
    if (res.success && res.token) {
      // 保存原管理员凭证以便后续恢复
      const currentToken = localStorage.getItem('admin_token')
      const currentAdminId = localStorage.getItem('admin_id')
      if (currentToken) {
        sessionStorage.setItem('original_admin_token', currentToken)
        sessionStorage.setItem('original_admin_id', currentAdminId || '')
      }
      
      // 设置新的员工身份
      localStorage.setItem('admin_token', res.token)
      localStorage.setItem('admin_id', String(res.user_id || ''))
      localStorage.setItem('admin_role', res.role || '')
      localStorage.setItem('account_name', res.real_name || res.username || '')
      sessionStorage.setItem('impersonate_staff_mode', '1')
      
      ElMessage.success(t('staff.switchedTo', { name: res.real_name || res.username }))
      
      // 跳转到仪表盘
      router.push('/dashboard')
    } else {
      ElMessage.error(res.error || t('staff.switchFailed'))
    }
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.detail || e.message || t('staff.operationFailed'))
    }
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.page-container {
  width: 100%;
  padding: 8px;
}

/* 页面头部 */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.header-left {
  flex: 1;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 6px;
  letter-spacing: -0.02em;
}

.page-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

.add-btn {
  height: 40px;
  padding: 0 20px;
  font-weight: 500;
}

.mt-12 { margin-top: 12px; }
.mb-12 { margin-bottom: 12px; }
.offboard-preview { padding: 4px 0; }
.offboard-desc { margin: 0 0 12px; color: var(--text-secondary); font-size: 14px; }
.offboard-hint { margin-top: 6px; font-size: 12px; color: var(--text-tertiary); }
.form-hint { margin-top: 6px; font-size: 12px; color: var(--text-tertiary); line-height: 1.45; }

/* 统计卡片 */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: all 0.2s ease;
}

.stat-card:hover {
  border-color: var(--primary);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-icon.blue {
  background: rgba(102, 126, 234, 0.12);
  color: #667eea;
}

.stat-icon.green {
  background: rgba(56, 239, 125, 0.12);
  color: #38ef7d;
}

.stat-icon.purple {
  background: rgba(118, 75, 162, 0.12);
  color: #764ba2;
}

.stat-icon.orange {
  background: rgba(255, 154, 63, 0.12);
  color: #ff9a3f;
}

.stat-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1;
}

.stat-label {
  font-size: 13px;
  color: var(--text-tertiary);
}

/* 主卡片 */
.main-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  overflow: hidden;
}

.card-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.filter-section {
  display: flex;
  gap: 12px;
  align-items: center;
}

/* 表格样式 */
.data-table {
  --el-table-header-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
}

.data-table :deep(.el-table__header th) {
  background: var(--bg-secondary) !important;
  font-weight: 600;
  font-size: 13px;
  color: var(--text-secondary);
  padding: 14px 0;
}

.data-table :deep(.el-table__body td) {
  padding: 12px 0;
}

/* 用户单元格 */
.user-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
}

.user-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.username {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.realname {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* TG单元格 */
.tg-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tg-name {
  font-size: 13px;
  color: var(--text-secondary);
}

/* 文本样式 */
.text-muted {
  color: var(--text-quaternary);
  font-size: 13px;
}

.commission {
  font-weight: 600;
  color: var(--primary);
}

.money {
  font-weight: 600;
  color: #38ef7d;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.time-text {
  font-size: 13px;
  color: var(--text-tertiary);
}

/* 操作按钮 */
.action-btns {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

/* 响应式 */
@media (max-width: 1200px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-row {
    grid-template-columns: 1fr;
  }
  
  .page-header {
    flex-direction: column;
    gap: 16px;
  }
  
  .header-right {
    width: 100%;
  }
  
  .add-btn {
    width: 100%;
  }
}

/* 重置密码对话框 */
.reset-pwd-block {
  width: 100%;
}
/* 密码预览：自动生成/输入后完整显示 */
.reset-pwd-preview {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  margin-bottom: 12px;
  background: var(--bg-input);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  flex-wrap: wrap;
}
.reset-pwd-preview .pwd-display {
  flex: 1;
  min-width: 0;
  font-family: ui-monospace, 'SF Mono', Monaco, monospace;
  font-size: 15px;
  letter-spacing: 1px;
  color: var(--text-primary);
  word-break: break-all;
}
.reset-pwd-preview .pwd-copy-inline {
  flex-shrink: 0;
}
.reset-pwd-block .reset-pwd-input {
  width: 100%;
  display: block;
  margin-bottom: 10px;
}
.reset-pwd-block .reset-pwd-input :deep(.el-input__wrapper) {
  width: 100%;
  box-sizing: border-box;
  min-width: 0;
}
.reset-pwd-block :deep(.el-input) {
  width: 100%;
}
.reset-pwd-block .reset-pwd-actions {
  display: flex;
  gap: 10px;
}
.reset-pwd-block .pwd-action-btn {
  flex-shrink: 0;
  background: var(--bg-input) !important;
  border: 1px solid var(--border-default) !important;
  color: var(--text-secondary) !important;
}
.reset-pwd-block .pwd-action-btn:hover {
  background: var(--bg-hover) !important;
  border-color: var(--border-hover) !important;
  color: var(--primary) !important;
}
</style>
