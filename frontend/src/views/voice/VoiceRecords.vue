<template>
  <div class="voice-page">
    <div class="page-header">
      <h1 class="page-title">{{ $t('menu.callRecords') }}</h1>
      <p class="page-desc">{{ $t('voiceCustomer.recordsDesc') }}</p>
    </div>

    <el-card v-loading="loading">
      <div class="toolbar">
        <el-select v-model="dateBasis" style="width: 150px" @change="onFilterChange">
          <el-option :label="$t('voice.dateBasisCreated')" value="created_at" />
          <el-option :label="$t('voice.dateBasisStart')" value="start_time" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          :range-separator="$t('voice.dateRangeSep')"
          :start-placeholder="$t('voice.startDate')"
          :end-placeholder="$t('voice.endDate')"
          style="width: 280px"
          clearable
          @change="onFilterChange"
        />
        <el-select
          v-model="statusFilter"
          :placeholder="$t('voice.allStatus')"
          style="width: 150px"
          clearable
          @change="onFilterChange"
        >
          <el-option :label="$t('voice.initiated')" value="initiated" />
          <el-option :label="$t('voice.ringing')" value="ringing" />
          <el-option :label="$t('voice.answered')" value="answered" />
          <el-option :label="$t('voice.busy')" value="busy" />
          <el-option :label="$t('voice.failed')" value="failed" />
          <el-option :label="$t('voice.completed')" value="completed" />
        </el-select>
        <el-select
          v-model="directionFilter"
          :placeholder="$t('voice.directionFilterPlaceholder')"
          style="width: 130px"
          clearable
          @change="onFilterChange"
        >
          <el-option :label="$t('voice.inbound')" value="inbound" />
          <el-option :label="$t('voice.outbound')" value="outbound" />
        </el-select>
        <el-input
          v-model="campaignIdInput"
          :placeholder="$t('voice.campaignIdFilterPlaceholder')"
          style="width: 140px"
          clearable
          @clear="onCampaignIdClear"
          @keyup.enter="onFilterChange(); load()"
        />
        <el-button type="primary" @click="load">{{ $t('smsRecords.query') }}</el-button>
        <el-button type="primary" plain :loading="exporting" @click="handleExport">{{ $t('voice.exportCsv') }}</el-button>
      </div>
      <el-table :data="items" stripe class="mt-table">
        <el-table-column prop="call_id" :label="$t('voice.callId')" min-width="160" show-overflow-tooltip />
        <el-table-column prop="caller" :label="$t('voice.caller')" width="130" />
        <el-table-column prop="callee" :label="$t('voice.callee')" width="130" />
        <el-table-column :label="$t('voice.callDirection')" width="90">
          <template #default="{ row }">
            {{ directionLabel(row.direction) }}
          </template>
        </el-table-column>
        <el-table-column prop="outbound_campaign_id" :label="$t('voice.outboundCampaignIdShort')" width="100">
          <template #default="{ row }">
            {{ row.outbound_campaign_id ?? '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="outbound_campaign_name" :label="$t('voice.outboundCampaignName')" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.outbound_campaign_name || '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="billsec" :label="$t('voice.duration')" width="90" />
        <el-table-column prop="cost" :label="$t('voice.cost')" width="90" />
        <el-table-column prop="status" :label="$t('voice.status')" width="100" />
        <el-table-column prop="voice_route_id" :label="$t('voice.voiceRouteIdCol')" width="100">
          <template #default="{ row }">
            {{ row.voice_route_id ?? '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="hangup_cause" :label="$t('voice.hangupCause')" min-width="120" show-overflow-tooltip />
        <el-table-column prop="created_at" :label="$t('voice.recordCreatedAt')" width="170" />
        <el-table-column :label="$t('voice.recording')" width="100">
          <template #default="{ row }">
            <a v-if="row.recording_url" :href="row.recording_url" target="_blank" rel="noopener">{{ $t('voiceCustomer.openLink') }}</a>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="start_time" :label="$t('voice.startTime')" width="170" />
      </el-table>
      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="onPage"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { getVoiceCallsCustomer, exportVoiceCallsCustomerCsv } from '@/api/voice-customer'

const { t } = useI18n()
function directionLabel(d: string | null | undefined) {
  if (!d) return '—'
  if (d === 'inbound') return t('voice.inbound')
  if (d === 'outbound') return t('voice.outbound')
  return d
}
const loading = ref(false)
const exporting = ref(false)
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const dateRange = ref<[string, string] | null>(null)
const dateBasis = ref<'created_at' | 'start_time'>('created_at')
/** 未选表示不筛选状态 */
const statusFilter = ref<string | undefined>(undefined)
const directionFilter = ref<string | undefined>(undefined)
/** 外呼任务 ID 文本，空则不带参数 */
const campaignIdInput = ref('')

function onFilterChange() {
  page.value = 1
}

function onCampaignIdClear() {
  onFilterChange()
}

/** 解析任务 ID：非法或空返回 undefined */
function parsedCampaignId(): number | undefined {
  const s = campaignIdInput.value?.trim()
  if (!s) return undefined
  const n = Number.parseInt(s, 10)
  if (!Number.isFinite(n) || n < 1) return undefined
  return n
}

async function load() {
  const rawCampaign = campaignIdInput.value?.trim()
  if (rawCampaign && parsedCampaignId() === undefined) {
    ElMessage.warning(t('voice.campaignIdInvalid'))
    return
  }
  loading.value = true
  try {
    const [start_date, end_date] = dateRange.value || []
    const res: any = await getVoiceCallsCustomer({
      page: page.value,
      page_size: pageSize.value,
      start_date: start_date || undefined,
      end_date: end_date || undefined,
      date_basis: dateBasis.value,
      status: statusFilter.value || undefined,
      direction: directionFilter.value || undefined,
      outbound_campaign_id: parsedCampaignId(),
    })
    if (res?.success) {
      items.value = res.items || []
      total.value = res.total || 0
    }
  } catch {
    ElMessage.error(t('voice.loadCallsFailed'))
  } finally {
    loading.value = false
  }
}

function onPage(p: number) {
  page.value = p
  load()
}

async function handleExport() {
  const rawCampaign = campaignIdInput.value?.trim()
  if (rawCampaign && parsedCampaignId() === undefined) {
    ElMessage.warning(t('voice.campaignIdInvalid'))
    return
  }
  exporting.value = true
  try {
    const [start_date, end_date] = dateRange.value || []
    const blob = (await exportVoiceCallsCustomerCsv({
      start_date: start_date || undefined,
      end_date: end_date || undefined,
      date_basis: dateBasis.value,
      status: statusFilter.value || undefined,
      direction: directionFilter.value || undefined,
      outbound_campaign_id: parsedCampaignId(),
    })) as Blob
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `voice_calls_${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')}.csv`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success(t('voice.exportCsvDone'))
  } catch {
    ElMessage.error(t('common.failed'))
  } finally {
    exporting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.voice-page {
  width: 100%;
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
.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}
.mt-table {
  margin-top: 0;
}
</style>
