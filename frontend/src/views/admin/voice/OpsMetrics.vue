<template>
  <div class="voice-ops-page">
    <div class="page-header">
      <div>
        <h2>{{ $t('voice.opsMetricsTitle') }}</h2>
        <p class="page-desc">{{ $t('voice.opsMetricsDesc') }}</p>
      </div>
      <el-button type="primary" :loading="loading" @click="load">
        {{ $t('voice.opsRefresh') }}
      </el-button>
    </div>

    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      class="mb-3"
      :title="error"
      show-icon
    />

    <div v-loading="loading" class="metrics-grid">
      <el-card v-for="card in cards" :key="card.key" shadow="hover" class="metric-card">
        <div class="metric-value">{{ card.display }}</div>
        <div class="metric-label">{{ card.label }}</div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getVoiceOpsMetrics, type VoiceOpsMetrics } from '@/api/voice-admin'

const { t } = useI18n()
const loading = ref(true)
const error = ref('')
const data = ref<VoiceOpsMetrics | null>(null)

function formatRate(v: number | null | undefined) {
  if (v === null || v === undefined) return '—'
  return `${(v * 100).toFixed(2)}%`
}

const cards = computed(() => {
  const m = data.value
  if (!m) {
    return []
  }
  return [
    {
      key: 'window',
      label: t('voice.opsWindowHours'),
      display: String(m.window_hours ?? 24)
    },
    {
      key: 'cdr_ok',
      label: t('voice.opsCdrProcessed'),
      display: String(m.cdr_webhook_processed ?? 0)
    },
    {
      key: 'cdr_fail',
      label: t('voice.opsCdrFailed'),
      display: String(m.cdr_webhook_failed ?? 0)
    },
    {
      key: 'camp',
      label: t('voice.opsCampaignsRunning'),
      display: String(m.campaigns_running ?? 0)
    },
    {
      key: 'calls_total',
      label: t('voice.opsCallsTotal24h'),
      display: String(m.voice_calls_total_24h ?? 0)
    },
    {
      key: 'calls_conn',
      label: t('voice.opsCallsConnected24h'),
      display: String(m.voice_calls_connected_24h ?? 0)
    },
    {
      key: 'rate',
      label: t('voice.opsAnswerRate24h'),
      display: formatRate(m.voice_answer_rate_24h)
    },
    {
      key: 'pending',
      label: t('voice.opsOutboundPending'),
      display: String(m.outbound_contacts_pending ?? 0)
    }
  ]
})

async function load() {
  error.value = ''
  loading.value = true
  try {
    const res = await getVoiceOpsMetrics()
    if (res && (res as VoiceOpsMetrics).success !== false) {
      data.value = res as VoiceOpsMetrics
    } else {
      error.value = t('voice.opsLoadFailed')
    }
  } catch (e: unknown) {
    const msg = e && typeof e === 'object' && 'message' in e ? String((e as Error).message) : ''
    error.value = msg || t('voice.opsLoadFailed')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.voice-ops-page {
  width: 100%;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
}
.page-header h2 {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
}
.page-desc {
  margin: 0;
  font-size: 14px;
  color: var(--text-tertiary);
}
.mb-3 {
  margin-bottom: 16px;
}
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}
.metric-card :deep(.el-card__body) {
  padding: 20px;
}
.metric-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--el-color-primary);
  line-height: 1.2;
  margin-bottom: 8px;
  font-variant-numeric: tabular-nums;
}
.metric-label {
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
