<template>
  <div class="voice-page">
    <div class="page-header">
      <h1 class="page-title">{{ $t('voiceCustomer.sipTitle') }}</h1>
      <p class="page-desc">{{ $t('voiceCustomer.sipDesc') }}</p>
    </div>

    <el-alert v-if="errorMsg" type="warning" :title="errorMsg" show-icon class="mb-4" />

    <el-card v-loading="loading" v-else-if="me">
      <template #header>
        <span>{{ $t('voiceCustomer.accountInfo') }}</span>
      </template>
      <el-descriptions :column="1" border>
        <el-descriptions-item :label="$t('voiceCustomer.vaId')">{{ me.voice_account?.id }}</el-descriptions-item>
        <el-descriptions-item :label="$t('voice.country')">{{ me.voice_account?.country_code }}</el-descriptions-item>
        <el-descriptions-item :label="$t('voice.balance')">${{ Number(me.voice_account?.balance || 0).toFixed(2) }}</el-descriptions-item>
        <el-descriptions-item :label="$t('common.status')">{{ me.voice_account?.status }}</el-descriptions-item>
        <el-descriptions-item :label="$t('voiceCustomer.defaultCaller')">
          <template v-if="me.voice_account?.default_caller">
            {{ me.voice_account.default_caller.number_e164 }}
            <span v-if="me.voice_account.default_caller.label" class="muted">（{{ me.voice_account.default_caller.label }}）</span>
          </template>
          <span v-else class="muted">—</span>
        </el-descriptions-item>
      </el-descriptions>

      <h3 class="section-title">{{ $t('voiceCustomer.sipParams') }}</h3>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="SIP Domain">{{ me.sip?.sip_domain || '—' }}</el-descriptions-item>
        <el-descriptions-item label="SIP Port">{{ me.sip?.sip_port }}</el-descriptions-item>
        <el-descriptions-item label="Transport">{{ me.sip?.sip_transport }}</el-descriptions-item>
        <el-descriptions-item :label="$t('voiceCustomer.sipUser')">{{ me.sip?.sip_username }}</el-descriptions-item>
      </el-descriptions>

      <h3 class="section-title">{{ $t('voiceCustomer.policyTitle') }}</h3>
      <el-descriptions :column="1" border>
        <el-descriptions-item :label="$t('voiceCustomer.policyHangupSms')">{{ me.policy?.hangup_sms_max_per_callee_per_day }}</el-descriptions-item>
        <el-descriptions-item :label="$t('voiceCustomer.policyMinBalance')">{{ me.policy?.min_balance_for_originate }}</el-descriptions-item>
        <el-descriptions-item :label="$t('voice.maxConcurrentCalls')">{{ me.policy?.max_concurrent_calls }}</el-descriptions-item>
        <el-descriptions-item :label="$t('voice.dailyOutboundLimit')">{{ me.policy?.daily_outbound_limit }}</el-descriptions-item>
      </el-descriptions>
      <p class="hint">{{ $t('voiceCustomer.sipHint') }}</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getVoiceMe } from '@/api/voice-customer'

const { t } = useI18n()
const loading = ref(true)
const me = ref<any>(null)
const errorMsg = ref('')

onMounted(async () => {
  loading.value = true
  errorMsg.value = ''
  try {
    const res: any = await getVoiceMe()
    if (res?.success) me.value = res
    else errorMsg.value = t('voiceCustomer.noVoiceAccount')
  } catch (e: any) {
    const d = e?.response?.data?.detail
    errorMsg.value = typeof d === 'string' ? d : t('voiceCustomer.noVoiceAccount')
    me.value = null
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.voice-page {
  max-width: 720px;
}
.page-header {
  margin-bottom: 20px;
}
.page-title {
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 8px;
}
.page-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}
.mb-4 {
  margin-bottom: 16px;
}
.section-title {
  font-size: 16px;
  margin: 24px 0 12px;
}
.hint {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-top: 16px;
  line-height: 1.6;
}
.muted {
  color: var(--text-tertiary);
}
</style>
