<template>
  <div class="admin-profile-page">
    <h1 class="page-title">{{ $t('adminProfile.title') }}</h1>
    <p class="page-desc">{{ $t('adminProfile.desc') }}</p>

    <el-row :gutter="20">
      <!-- 基本信息 -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>{{ $t('adminProfile.basicInfo') }}</span>
          </template>
          <el-descriptions v-if="profile" :column="1" border>
            <el-descriptions-item :label="$t('adminProfile.username')">{{ profile.username }}</el-descriptions-item>
            <el-descriptions-item :label="$t('adminProfile.realName')">{{ profile.real_name || '-' }}</el-descriptions-item>
            <el-descriptions-item :label="$t('adminProfile.role')">{{ roleName(profile.role) }}</el-descriptions-item>
            <el-descriptions-item :label="$t('adminProfile.email')">{{ profile.email || '-' }}</el-descriptions-item>
            <el-descriptions-item :label="$t('adminProfile.phone')">{{ profile.phone || '-' }}</el-descriptions-item>
            <el-descriptions-item :label="$t('adminProfile.lastLogin')">{{ formatTime(profile.last_login_at) }}</el-descriptions-item>
            <el-descriptions-item :label="$t('adminProfile.createdAt')">{{ formatTime(profile.created_at) }}</el-descriptions-item>
          </el-descriptions>
          <el-skeleton v-else :rows="5" animated />
        </el-card>
      </el-col>

      <!-- 修改密码 -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>{{ $t('accountSettings.changePassword') }}</span>
          </template>
          <el-form :model="passwordForm" ref="passwordFormRef" label-width="140px">
            <el-form-item :label="$t('accountSettings.currentPassword')" required>
              <el-input
                v-model="passwordForm.old_password"
                type="password"
                show-password
                :placeholder="$t('accountSettings.enterCurrentPassword')"
              />
            </el-form-item>
            <el-form-item :label="$t('accountSettings.newPassword')" required>
              <el-input
                v-model="passwordForm.new_password"
                type="password"
                show-password
                :placeholder="$t('adminProfile.passwordHint')"
              />
            </el-form-item>
            <el-form-item :label="$t('accountSettings.confirmPassword')" required>
              <el-input
                v-model="passwordForm.confirm_password"
                type="password"
                show-password
                :placeholder="$t('accountSettings.enterNewPassword')"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleChangePassword" :loading="passwordLoading">
                {{ $t('accountSettings.changePassword') }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <!-- Telegram 绑定 -->
    <el-row style="margin-top: 20px">
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>{{ $t('accountSettings.tgBinding') }}</span>
          </template>
          <div class="tg-binding-section">
            <div v-if="tgBound" class="tg-status tg-bound">
              <el-tag type="success" size="large">{{ $t('accountSettings.tgBoundStatus') }}</el-tag>
              <div class="tg-info">
                <p>Telegram ID: <strong>{{ profile?.tg_id }}</strong></p>
                <p v-if="profile?.tg_username">Username: <strong>@{{ profile.tg_username }}</strong></p>
              </div>
              <el-button type="danger" plain @click="handleUnbindTg" :loading="unbindLoading">
                {{ $t('accountSettings.tgUnbind') }}
              </el-button>
            </div>
            <div v-else class="tg-status tg-unbound">
              <el-tag type="info" size="large">{{ $t('accountSettings.tgNotBoundStatus') }}</el-tag>
              <div class="tg-steps">
                <h4>{{ $t('adminProfile.tgBindSteps') }}</h4>
                <ol>
                  <li>{{ $t('adminProfile.tgStep1') }}</li>
                  <li>{{ $t('adminProfile.tgStep2') }}</li>
                  <li>{{ $t('adminProfile.tgStep3') }}</li>
                </ol>
              </div>
              <div class="tg-code-area">
                <div v-if="bindCode" class="bind-code-display">
                  <span class="code-label">{{ $t('accountSettings.tgBindCode') }}:</span>
                  <span class="code-value">{{ bindCode }}</span>
                  <el-button size="small" type="primary" @click="copyBindCode">{{ $t('common.copy') }}</el-button>
                  <span class="code-expire">{{ $t('accountSettings.tgCodeExpire') }}</span>
                </div>
                <el-button type="primary" @click="handleGenBindCode" :loading="codeLoading">
                  {{ bindCode ? $t('accountSettings.tgRegenerate') : $t('accountSettings.tgGenerate') }}
                </el-button>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- TG 群组配置（管理员可见） -->
    <el-row v-if="isAdmin" style="margin-top: 20px">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div style="display:flex; justify-content:space-between; align-items:center">
              <span>{{ $t('adminProfile.groupConfig') }}</span>
              <el-button type="primary" size="small" @click="saveGroupConfig" :loading="groupSaving">
                {{ $t('common.save') }}
              </el-button>
            </div>
          </template>
          <el-form label-width="120px" label-position="left">
            <el-form-item :label="$t('adminProfile.techGroupId')">
              <el-input v-model="groupConfig.tech_group_id" placeholder="-100xxxxxxxxxx" />
              <div class="form-tip">{{ $t('adminProfile.techGroupTip') }}</div>
            </el-form-item>
            <el-form-item :label="$t('adminProfile.billingGroupId')">
              <el-input v-model="groupConfig.billing_group_id" placeholder="-100xxxxxxxxxx" />
              <div class="form-tip">{{ $t('adminProfile.billingGroupTip') }}</div>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import {
  getAdminProfile,
  changeAdminPassword,
  generateTgBindCode,
  unbindTelegram,
  type AdminProfile
} from '@/api/admin'
import { getBotConfig, saveBotConfig } from '@/api/bot'

const { t } = useI18n()
const profile = ref<AdminProfile | null>(null)
const passwordLoading = ref(false)
const passwordFormRef = ref<FormInstance>()
const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: ''
})
const bindCode = ref('')
const codeLoading = ref(false)
const unbindLoading = ref(false)
const tgBound = ref(false)

const isAdmin = computed(() => {
  const role = profile.value?.role
  return role === 'super_admin' || role === 'admin'
})

const groupConfig = reactive({
  tech_group_id: '',
  billing_group_id: '',
})
const groupSaving = ref(false)

const roleName = (role: string) => {
  const map: Record<string, string> = {
    super_admin: t('roles.superAdmin'),
    admin: t('roles.admin'),
    sales: t('roles.sales'),
    finance: t('roles.finance'),
    tech: t('roles.tech')
  }
  return map[role] || role
}

const formatTime = (val?: string) => {
  if (!val) return '-'
  try {
    const d = new Date(val)
    return d.toLocaleString()
  } catch {
    return val
  }
}

const loadProfile = async () => {
  try {
    const res: any = await getAdminProfile()
    if (res?.success && res?.profile) {
      profile.value = res.profile
      tgBound.value = !!res.profile.tg_id
    }
  } catch (e: any) {
    ElMessage.error(e.message || t('adminProfile.loadFailed'))
  }
}

const handleChangePassword = async () => {
  if (!passwordForm.old_password) {
    ElMessage.warning(t('accountSettings.enterCurrentPasswordRequired'))
    return
  }
  if (!passwordForm.new_password || passwordForm.new_password.length < 6) {
    ElMessage.warning(t('adminProfile.passwordMin6'))
    return
  }
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    ElMessage.warning(t('accountSettings.passwordMismatch'))
    return
  }
  passwordLoading.value = true
  try {
    const res: any = await changeAdminPassword({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password
    })
    if (res?.success) {
      ElMessage.success(t('accountSettings.passwordChangeSuccess'))
      passwordForm.old_password = ''
      passwordForm.new_password = ''
      passwordForm.confirm_password = ''
    } else {
      const errMsg = res?.error === 'old_password_wrong'
        ? t('adminProfile.oldPasswordWrong')
        : res?.error === 'password_too_short'
          ? t('adminProfile.passwordMin6')
          : res?.error || t('common.error')
      ElMessage.error(errMsg)
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error === 'old_password_wrong'
      ? t('adminProfile.oldPasswordWrong')
      : e.message || t('common.error'))
  } finally {
    passwordLoading.value = false
  }
}

const handleGenBindCode = async () => {
  codeLoading.value = true
  try {
    const res: any = await generateTgBindCode()
    if (res?.success && res?.code) {
      bindCode.value = res.code
      ElMessage.success(t('accountSettings.tgCodeGenerated'))
    }
  } catch (e: any) {
    ElMessage.error(e.message || t('common.error'))
  } finally {
    codeLoading.value = false
  }
}

const copyBindCode = () => {
  navigator.clipboard.writeText(bindCode.value).then(() => {
    ElMessage.success(t('common.copied'))
  })
}

const handleUnbindTg = async () => {
  try {
    await ElMessageBox.confirm(t('accountSettings.tgUnbindConfirm'), t('common.confirm'), { type: 'warning' })
  } catch {
    return
  }
  unbindLoading.value = true
  try {
    const res: any = await unbindTelegram()
    if (res?.success) {
      tgBound.value = false
      if (profile.value) {
        profile.value.tg_id = undefined
        profile.value.tg_username = undefined
      }
      ElMessage.success(t('accountSettings.tgUnbindSuccess'))
    } else {
      ElMessage.error(res?.error === 'not_bound' ? t('adminProfile.tgNotBound') : res?.error || t('common.error'))
    }
  } catch (e: any) {
    ElMessage.error(e.message || t('common.error'))
  } finally {
    unbindLoading.value = false
  }
}

const loadGroupConfig = async () => {
  try {
    const res: any = await getBotConfig()
    if (res?.config) {
      groupConfig.tech_group_id = res.config.tech_group_id || ''
      groupConfig.billing_group_id = res.config.billing_group_id || ''
    }
  } catch { /* 非管理员可能无权限 */ }
}

const saveGroupConfig = async () => {
  groupSaving.value = true
  try {
    await saveBotConfig({
      tech_group_id: groupConfig.tech_group_id,
      billing_group_id: groupConfig.billing_group_id,
    })
    ElMessage.success(t('common.saveSuccess'))
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || t('common.failed'))
  } finally {
    groupSaving.value = false
  }
}

onMounted(async () => {
  await loadProfile()
  if (isAdmin.value) {
    loadGroupConfig()
  }
})
</script>

<style scoped>
.admin-profile-page {
  padding: 0;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 4px;
}
.page-desc {
  font-size: 13px;
  color: var(--text-3);
  margin: 0 0 24px;
}
.tg-binding-section {
  padding: 4px 0;
}
.tg-status {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.tg-info p {
  margin: 4px 0;
  font-size: 13px;
}
.tg-steps h4 {
  margin: 0 0 8px;
  font-size: 14px;
}
.tg-steps ol {
  margin: 0;
  padding-left: 20px;
  color: var(--text-3);
}
.tg-steps li {
  margin: 4px 0;
}
.tg-code-area {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.bind-code-display {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.code-label { font-weight: 500; }
.code-value {
  font-family: monospace;
  font-size: 18px;
  letter-spacing: 2px;
}
.code-expire { font-size: 12px; color: var(--text-4); }
.form-tip {
  font-size: 12px;
  color: var(--text-4);
  margin-top: 4px;
  line-height: 1.4;
}
</style>
