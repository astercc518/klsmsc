<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">{{ $t('bot.title') }}</h1>
        <p class="page-desc">{{ $t('bot.pageDesc') }}</p>
      </div>
      <div class="header-right">
        <el-button type="primary" @click="saveConfig" :loading="saving">
          <el-icon><Check /></el-icon>
          {{ $t('bot.saveConfig') }}
        </el-button>
      </div>
    </div>

    <div class="config-grid">
      <!-- Bot信息 -->
      <el-card class="config-card">
        <template #header>
          <div class="card-header">
            <el-icon class="header-icon"><Setting /></el-icon>
            <span>{{ $t('bot.botInfo') }}</span>
          </div>
        </template>
        <el-form label-width="120px" label-position="left">
          <el-form-item :label="$t('bot.botToken')">
            <el-input v-model="config.bot_token" type="password" show-password :placeholder="$t('bot.botTokenPlaceholder')" />
          </el-form-item>
          <el-form-item :label="$t('bot.botUsername')">
            <el-input v-model="config.bot_username" placeholder="your_bot">
              <template #prepend>@</template>
            </el-input>
          </el-form-item>
          <el-form-item :label="$t('bot.botStatus')">
            <el-tag :type="statusType" size="large">
              {{ statusText }}
            </el-tag>
            <el-button type="warning" size="small" style="margin-left: 12px" @click="restartBot" :loading="restarting">
              {{ $t('bot.restartBot') }}
            </el-button>
            <el-button type="primary" size="small" style="margin-left: 8px" @click="loadConfig" :loading="loading">
              {{ $t('bot.refreshStatus') }}
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 管理群配置 -->
      <el-card class="config-card">
        <template #header>
          <div class="card-header">
            <el-icon class="header-icon"><ChatDotRound /></el-icon>
            <span>{{ $t('bot.adminGroup') }}</span>
          </div>
        </template>
        <el-form label-width="120px" label-position="left">
          <el-form-item :label="$t('bot.adminGroupId')">
            <el-input v-model="config.admin_group_id" :placeholder="$t('bot.adminGroupIdPlaceholder')" />
            <div class="form-tip">{{ $t('bot.adminGroupTip') }}</div>
          </el-form-item>
          <el-form-item :label="$t('bot.notifyGroupId')">
            <el-input v-model="config.notify_group_id" :placeholder="$t('bot.adminGroupIdPlaceholder')" />
            <div class="form-tip">{{ $t('bot.notifyGroupTip') }}</div>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 功能开关 -->
      <el-card class="config-card">
        <template #header>
          <div class="card-header">
            <el-icon class="header-icon"><Switch /></el-icon>
            <span>{{ $t('bot.features') }}</span>
          </div>
        </template>
        <el-form label-width="140px" label-position="left">
          <el-form-item :label="$t('bot.selfRegister')">
            <el-switch v-model="config.enable_register" />
            <span class="switch-desc">{{ $t('bot.selfRegisterDesc') }}</span>
          </el-form-item>
          <el-form-item :label="$t('bot.selfRecharge')">
            <el-switch v-model="config.enable_recharge" />
            <span class="switch-desc">{{ $t('bot.selfRechargeDesc') }}</span>
          </el-form-item>
          <el-form-item :label="$t('bot.batchReview')">
            <el-switch v-model="config.enable_batch_review" />
            <span class="switch-desc">{{ $t('bot.batchReviewDesc') }}</span>
          </el-form-item>
          <el-form-item :label="$t('bot.queryBalance')">
            <el-switch v-model="config.enable_balance_query" />
            <span class="switch-desc">{{ $t('bot.queryBalanceDesc') }}</span>
          </el-form-item>
          <el-form-item :label="$t('bot.sendSms')">
            <el-switch v-model="config.enable_send_sms" />
            <span class="switch-desc">{{ $t('bot.sendSmsDesc') }}</span>
          </el-form-item>
          <el-form-item :label="$t('bot.ticketSystem')">
            <el-switch v-model="config.enable_ticket" />
            <span class="switch-desc">{{ $t('bot.ticketSystemDesc') }}</span>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 消息设置 -->
      <el-card class="config-card">
        <template #header>
          <div class="card-header">
            <el-icon class="header-icon"><Message /></el-icon>
            <span>{{ $t('bot.messageSettings') }}</span>
          </div>
        </template>
        <el-form label-width="120px" label-position="left">
          <el-form-item :label="$t('bot.welcomeMessage')">
            <el-input v-model="config.welcome_message" type="textarea" :rows="3" :placeholder="$t('bot.welcomeMessagePlaceholder')" />
          </el-form-item>
          <el-form-item :label="$t('bot.helpInfo')">
            <el-input v-model="config.help_message" type="textarea" :rows="3" :placeholder="$t('bot.helpInfoPlaceholder')" />
          </el-form-item>
          <el-form-item :label="$t('bot.maintenanceNotice')">
            <el-input v-model="config.maintenance_message" type="textarea" :rows="2" :placeholder="$t('bot.maintenanceNoticePlaceholder')" />
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 限制设置 -->
      <el-card class="config-card">
        <template #header>
          <div class="card-header">
            <el-icon class="header-icon"><Warning /></el-icon>
            <span>{{ $t('bot.limitSettings') }}</span>
          </div>
        </template>
        <el-form label-width="140px" label-position="left">
          <el-form-item :label="$t('bot.singleSendLimit')">
            <el-input-number v-model="config.max_recipients" :min="1" :max="10000" />
            <span class="input-suffix">{{ $t('bot.perTime') }}</span>
          </el-form-item>
          <el-form-item :label="$t('bot.dailySendLimit')">
            <el-input-number v-model="config.daily_limit" :min="0" :max="1000000" :step="1000" />
            <span class="input-suffix">{{ $t('bot.perDayNoLimit') }}</span>
          </el-form-item>
          <el-form-item :label="$t('bot.minRechargeAmount')">
            <el-input-number v-model="config.min_recharge" :min="0" :precision="2" />
            <span class="input-suffix">USD</span>
          </el-form-item>
          <el-form-item :label="$t('bot.operationCooldown')">
            <el-input-number v-model="config.cooldown_seconds" :min="0" :max="3600" />
            <span class="input-suffix">{{ $t('bot.seconds') }}</span>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- Webhook配置 -->
      <el-card class="config-card">
        <template #header>
          <div class="card-header">
            <el-icon class="header-icon"><Link /></el-icon>
            <span>{{ $t('bot.webhookConfig') }}</span>
          </div>
        </template>
        <el-form label-width="120px" label-position="left">
          <el-form-item :label="$t('bot.webhookUrl')">
            <el-input v-model="config.webhook_url" placeholder="https://your-domain.com/bot/webhook" />
          </el-form-item>
          <el-form-item :label="$t('bot.useWebhook')">
            <el-switch v-model="config.use_webhook" />
            <span class="switch-desc">{{ $t('bot.pollModeDesc') }}</span>
          </el-form-item>
        </el-form>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Check, Setting, ChatDotRound, Switch, Message, Warning, Link } from '@element-plus/icons-vue'
import request from '@/api/index'

const { t } = useI18n()
const saving = ref(false)
const loading = ref(false)
const restarting = ref(false)

const config = reactive({
  bot_token: '',
  bot_username: '',
  bot_status: 'unknown',
  admin_group_id: '',
  notify_group_id: '',
  enable_register: true,
  enable_recharge: true,
  enable_batch_review: true,
  enable_balance_query: true,
  enable_send_sms: true,
  enable_ticket: true,
  welcome_message: '',
  help_message: '',
  maintenance_message: '',
  max_recipients: 1000,
  daily_limit: 0,
  min_recharge: 10,
  cooldown_seconds: 5,
  webhook_url: '',
  use_webhook: false,
})

// 状态映射
const getStatusType = (status: string) => {
  const map: Record<string, string> = {
    'active': 'success',
    'running': 'success',
    'stopped': 'danger',
    'error': 'danger',
    'unknown': 'warning',
  }
  return map[status] || 'info'
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    'active': 'running',
    'running': 'running',
    'stopped': 'stopped',
    'error': 'error',
    'unknown': 'unknown',
  }
  return t(`bot.${map[status] || 'unknown'}`)
}

const statusType = computed(() => getStatusType(config.bot_status))
const statusText = computed(() => getStatusText(config.bot_status))

const loadConfig = async () => {
  loading.value = true
  try {
    const res = await request.get('/admin/bot/config')
    if (res.config) {
      Object.assign(config, {
        ...res.config,
        notify_group_id: res.config.notification_group_id || '',
        daily_limit: res.config.daily_send_limit || 0,
        min_recharge: res.config.min_recharge_amount || 10,
        cooldown_seconds: res.config.send_cooldown_seconds || 5,
      })
    }
  } catch (e: any) {
    ElMessage.error(t('bot.loadConfigFailed'))
  } finally {
    loading.value = false
  }
}

const saveConfig = async () => {
  saving.value = true
  try {
    await request.post('/admin/bot/config', {
      ...config,
      notification_group_id: config.notify_group_id,
      daily_send_limit: config.daily_limit,
      min_recharge_amount: config.min_recharge,
      send_cooldown_seconds: config.cooldown_seconds,
    })
    ElMessage.success(t('bot.configSaved'))
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || t('bot.saveFailed'))
  } finally {
    saving.value = false
  }
}

const restartBot = async () => {
  restarting.value = true
  try {
    await request.post('/admin/bot/restart')
    ElMessage.success(t('bot.botRestartSent'))
    // 延迟刷新状态
    setTimeout(() => loadConfig(), 3000)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || t('bot.restartFailed'))
  } finally {
    restarting.value = false
  }
}

onMounted(() => {
  loadConfig()
})
</script>

<style scoped>
.page-container {
  width: 100%;
  padding: 8px;
}

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
}

.page-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.config-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 12px;
}

.config-card :deep(.el-card__header) {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.config-card :deep(.el-card__body) {
  padding: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-icon {
  font-size: 18px;
  color: var(--primary);
}

.form-tip {
  font-size: 12px;
  color: var(--text-quaternary);
  margin-top: 4px;
}

.switch-desc {
  margin-left: 12px;
  font-size: 13px;
  color: var(--text-tertiary);
}

.input-suffix {
  margin-left: 8px;
  font-size: 13px;
  color: var(--text-tertiary);
}

@media (max-width: 1200px) {
  .config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
