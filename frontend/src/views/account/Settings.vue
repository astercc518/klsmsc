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
            <el-form-item :label="$t('accountSettings.telegramNotify')">
              <el-switch v-model="notifyForm.telegram_notify" />
              <span v-if="notifyForm.telegram_notify" style="margin-left: 10px; color: #409eff">
                {{ $t('accountSettings.telegramBound') }}
              </span>
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
import { ElMessage } from 'element-plus'
import { getAccountInfo } from '@/api/account'

const { t } = useI18n()
const profileLoading = ref(false)
const passwordLoading = ref(false)
const notifyLoading = ref(false)

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
    const res = await getAccountInfo()
    profileForm.username = res.username
    profileForm.email = res.email || ''
    profileForm.company = res.company_name || ''
    profileForm.phone = res.contact_phone || ''
  } catch (error: any) {
    ElMessage.error(t('accountSettings.loadAccountInfoFailed'))
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
</style>
