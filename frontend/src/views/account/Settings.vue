<template>
  <div class="settings-page">
    <el-row :gutter="20">
      <!-- 基础信息 -->
      <el-col :span="12">
        <el-card>
          <template #header><h3>{{ $t('accountSettings.basicInfo') }}</h3></template>
          <el-form :model="profileForm" label-width="120px">
            <el-form-item :label="$t('accountSettings.username')">
              <el-input v-model="profileForm.username" disabled />
            </el-form-item>
            <el-form-item :label="$t('accountSettings.email')">
              <el-input v-model="profileForm.email" />
            </el-form-item>
            <el-form-item :label="$t('accountSettings.company')">
              <el-input v-model="profileForm.company" />
            </el-form-item>
            <el-form-item :label="$t('accountSettings.phone')">
              <el-input v-model="profileForm.phone" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="updateProfile" :loading="profileLoading">
                {{ $t('accountSettings.saveChanges') }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- 修改密码 -->
      <el-col :span="12">
        <el-card>
          <template #header><h3>{{ $t('accountSettings.changePassword') }}</h3></template>
          <el-form :model="passwordForm" ref="passwordFormRef" label-width="120px">
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
                :placeholder="$t('accountSettings.passwordHint')"
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
              <el-button type="primary" @click="changePassword" :loading="passwordLoading">
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
          <template #header><h3>{{ $t('accountSettings.tgBinding') }}</h3></template>
          <div class="tg-binding-section">
            <!-- 已绑定状态 -->
            <div v-if="tgBound" class="tg-status tg-bound">
              <el-tag type="success" size="large">{{ $t('accountSettings.tgBoundStatus') }}</el-tag>
              <div class="tg-info">
                <p>Telegram ID: <strong>{{ tgId }}</strong></p>
                <p v-if="tgUsername">Username: <strong>@{{ tgUsername }}</strong></p>
              </div>
              <el-button type="danger" plain @click="handleUnbindTg" :loading="unbindLoading">
                {{ $t('accountSettings.tgUnbind') }}
              </el-button>
            </div>
            <!-- 未绑定状态 -->
            <div v-else class="tg-status tg-unbound">
              <el-tag type="info" size="large">{{ $t('accountSettings.tgNotBoundStatus') }}</el-tag>
              <div class="tg-steps">
                <h4>{{ $t('accountSettings.tgBindSteps') }}</h4>
                <ol>
                  <li>{{ $t('accountSettings.tgStep1') }}</li>
                  <li>{{ $t('accountSettings.tgStep2') }}</li>
                  <li>{{ $t('accountSettings.tgStep3') }}</li>
                </ol>
              </div>
              <div class="tg-code-area">
                <div v-if="bindCode" class="bind-code-display">
                  <span class="code-label">{{ $t('accountSettings.tgBindCode') }}:</span>
                  <span class="code-value">{{ bindCode }}</span>
                  <el-button size="small" type="primary" @click="copyBindCode">{{ $t('common.copy') }}</el-button>
                  <span class="code-expire">{{ $t('accountSettings.tgCodeExpire') }}</span>
                </div>
                <el-button 
                  type="primary" 
                  @click="handleGenBindCode" 
                  :loading="codeLoading"
                >
                  {{ bindCode ? $t('accountSettings.tgRegenerate') : $t('accountSettings.tgGenerate') }}
                </el-button>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 通知设置 -->
    <el-row style="margin-top: 20px">
      <el-col :span="24">
        <el-card>
          <template #header><h3>{{ $t('accountSettings.notificationSettings') }}</h3></template>
          <el-form label-width="200px">
            <el-form-item :label="$t('accountSettings.lowBalanceAlert')">
              <el-switch v-model="notifyForm.balance_alert" />
              <span style="margin-left: 10px; color: #909399">
                {{ $t('accountSettings.lowBalanceAlertDesc') }}
              </span>
            </el-form-item>
            <el-form-item :label="$t('accountSettings.sendFailAlert')">
              <el-switch v-model="notifyForm.send_fail_alert" />
              <span style="margin-left: 10px; color: #909399">
                {{ $t('accountSettings.sendFailAlertDesc') }}
              </span>
            </el-form-item>
            <el-form-item :label="$t('accountSettings.batchCompleteAlert')">
              <el-switch v-model="notifyForm.batch_complete_alert" />
              <span style="margin-left: 10px; color: #909399">
                {{ $t('accountSettings.batchCompleteAlertDesc') }}
              </span>
            </el-form-item>
            <el-form-item :label="$t('accountSettings.emailNotify')">
              <el-switch v-model="notifyForm.email_notify" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="updateNotifySettings" :loading="notifyLoading">
                {{ $t('accountSettings.saveSettings') }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getAccountInfo, generateAccountTgBindCode, unbindAccountTelegram } from '@/api/account'

const { t } = useI18n()
const profileLoading = ref(false)
const passwordLoading = ref(false)
const notifyLoading = ref(false)

// TG 绑定
const tgBound = ref(false)
const tgId = ref<number | null>(null)
const tgUsername = ref('')
const bindCode = ref('')
const codeLoading = ref(false)
const unbindLoading = ref(false)

const profileForm = reactive({
  username: '',
  email: '',
  company: '',
  phone: ''
})

const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: ''
})

const notifyForm = reactive({
  balance_alert: true,
  send_fail_alert: true,
  batch_complete_alert: true,
  email_notify: true,
  telegram_notify: false
})

const passwordFormRef = ref()

const loadAccountInfo = async () => {
  try {
    const res: any = await getAccountInfo()
    profileForm.username = res.account_name || res.username || ''
    profileForm.email = res.email || ''
    profileForm.company = res.company_name || ''
    profileForm.phone = res.contact_phone || ''
    tgId.value = res.tg_id || null
    tgUsername.value = res.tg_username || ''
    tgBound.value = !!res.tg_id
  } catch (error: any) {
    ElMessage.error(t('accountSettings.loadAccountInfoFailed'))
  }
}

const handleGenBindCode = async () => {
  codeLoading.value = true
  try {
    const res: any = await generateAccountTgBindCode()
    if (res?.success && res?.code) {
      bindCode.value = res.code
      ElMessage.success(t('accountSettings.tgCodeGenerated'))
    } else {
      ElMessage.error(res?.message || t('common.error'))
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
    const res: any = await unbindAccountTelegram()
    if (res?.success) {
      tgBound.value = false
      tgId.value = null
      tgUsername.value = ''
      ElMessage.success(t('accountSettings.tgUnbindSuccess'))
    }
  } catch (e: any) {
    ElMessage.error(e.message || t('common.error'))
  } finally {
    unbindLoading.value = false
  }
}

const updateProfile = async () => {
  profileLoading.value = true
  try {
    // TODO: 调用更新API
    // await updateAccountInfo(profileForm)
    await new Promise(resolve => setTimeout(resolve, 1000))
    ElMessage.success(t('common.saveSuccess'))
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.saveFailed'))
  } finally {
    profileLoading.value = false
  }
}

const changePassword = async () => {
  if (!passwordForm.old_password) {
    ElMessage.warning(t('accountSettings.enterCurrentPasswordRequired'))
    return
  }
  if (!passwordForm.new_password || passwordForm.new_password.length < 8) {
    ElMessage.warning(t('accountSettings.newPasswordMinLength'))
    return
  }
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    ElMessage.warning(t('accountSettings.passwordMismatch'))
    return
  }
  
  passwordLoading.value = true
  try {
    // TODO: 调用修改密码API
    // await changeAccountPassword({
    //   old_password: passwordForm.old_password,
    //   new_password: passwordForm.new_password
    // })
    await new Promise(resolve => setTimeout(resolve, 1000))
    ElMessage.success(t('accountSettings.passwordChangeSuccess'))
    // 清空表单
    passwordForm.old_password = ''
    passwordForm.new_password = ''
    passwordForm.confirm_password = ''
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.updateFailed'))
  } finally {
    passwordLoading.value = false
  }
}

const updateNotifySettings = async () => {
  notifyLoading.value = true
  try {
    // TODO: 调用更新通知设置API
    // await updateNotifySettings(notifyForm)
    await new Promise(resolve => setTimeout(resolve, 1000))
    ElMessage.success(t('accountSettings.settingsSaved'))
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.saveFailed'))
  } finally {
    notifyLoading.value = false
  }
}

onMounted(() => {
  loadAccountInfo()
})
</script>

<style scoped>
.settings-page {
  width: 100%;
}

.tg-binding-section {
  padding: 10px 0;
}

.tg-status {
  display: flex;
  flex-direction: column;
  gap: 16px;
  align-items: flex-start;
}

.tg-info p {
  margin: 4px 0;
  color: var(--text-secondary);
}

.tg-steps h4 {
  margin: 0 0 8px;
}

.tg-steps ol {
  padding-left: 20px;
  color: var(--text-secondary);
  line-height: 2;
}

.tg-code-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.bind-code-display {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: var(--bg-input);
  border-radius: 8px;
  border: 1px solid var(--border-default);
}

.code-value {
  font-size: 24px;
  font-weight: 700;
  font-family: monospace;
  letter-spacing: 4px;
  color: var(--primary);
}

.code-expire {
  font-size: 12px;
  color: var(--text-quaternary);
}
</style>
