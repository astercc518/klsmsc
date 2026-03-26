<template>
  <div class="voice-calls-page">
    <div class="page-header">
      <h2>{{ $t('voice.callRecords') }}</h2>
      <div class="header-actions">
        <el-input v-model="filters.account_id" :placeholder="$t('voice.accountId')" style="width: 120px" clearable />
        <el-input
          v-model="filters.outbound_campaign_id"
          :placeholder="$t('voice.campaignIdFilter')"
          style="width: 130px"
          clearable
        />
        <el-select v-model="filters.status" :placeholder="$t('voice.status')" style="width: 140px" clearable>
          <el-option :label="$t('voice.initiated')" value="initiated" />
          <el-option :label="$t('voice.ringing')" value="ringing" />
          <el-option :label="$t('voice.answered')" value="answered" />
          <el-option :label="$t('voice.busy')" value="busy" />
          <el-option :label="$t('voice.failed')" value="failed" />
          <el-option :label="$t('voice.completed')" value="completed" />
        </el-select>
        <el-select v-model="filters.date_basis" style="width: 150px">
          <el-option :label="$t('voice.dateBasisCreated')" value="created_at" />
          <el-option :label="$t('voice.dateBasisStart')" value="start_time" />
        </el-select>
        <el-date-picker
          v-model="filters.dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          :range-separator="$t('voice.dateRangeSep')"
          :start-placeholder="$t('voice.startDate')"
          :end-placeholder="$t('voice.endDate')"
          style="width: 260px"
          clearable
        />
        <el-button @click="loadCalls">{{ $t('smsRecords.query') }}</el-button>
        <el-button type="primary" plain :loading="exporting" @click="handleExportCsv">{{ $t('voice.exportCsv') }}</el-button>
      </div>
    </div>

    <el-card>
      <el-table :data="calls" stripe v-loading="loading">
        <el-table-column prop="call_id" :label="$t('voice.callId')" min-width="160" />
        <el-table-column prop="account_id" :label="$t('voice.accountId')" width="100" />
        <el-table-column prop="outbound_campaign_id" :label="$t('voice.campaignIdCol')" width="110" />
        <el-table-column prop="outbound_campaign_name" :label="$t('voice.outboundCampaignName')" min-width="130" show-overflow-tooltip />
        <el-table-column prop="caller" :label="$t('voice.caller')" width="140" />
        <el-table-column prop="callee" :label="$t('voice.callee')" width="140" />
        <el-table-column prop="status" :label="$t('voice.status')" width="100" />
        <el-table-column prop="duration" :label="$t('voice.duration')" width="120" />
        <el-table-column prop="cost" :label="$t('voice.cost')" width="100" />
        <el-table-column prop="voice_route_id" :label="$t('voice.voiceRouteIdCol')" width="110" />
        <el-table-column prop="start_time" :label="$t('voice.startTime')" width="180">
          <template #default="{ row }">
            {{ row.start_time ? new Date(row.start_time).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="end_time" :label="$t('voice.endTime')" width="180">
          <template #default="{ row }">
            {{ row.end_time ? new Date(row.end_time).toLocaleString() : '-' }}
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next, sizes"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="(p:number)=>{ page=p; loadCalls() }"
          @size-change="(s:number)=>{ pageSize=s; page=1; loadCalls() }"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { getVoiceCalls, exportVoiceCallsCsv } from '@/api/voice-admin'

const { t } = useI18n()
const calls = ref<any[]>([])
const loading = ref(false)
const exporting = ref(false)
const total = ref(0)
let page = 1
let pageSize = 20

const filters = reactive({
  account_id: '',
  outbound_campaign_id: '',
  status: '',
  date_basis: 'created_at' as 'created_at' | 'start_time',
  dateRange: null as [string, string] | null,
})

function buildQueryParams() {
  const [start_date, end_date] = filters.dateRange || []
  return {
    account_id: filters.account_id ? Number(filters.account_id) : undefined,
    outbound_campaign_id: filters.outbound_campaign_id
      ? Number(filters.outbound_campaign_id)
      : undefined,
    status: filters.status || undefined,
    start_date: start_date || undefined,
    end_date: end_date || undefined,
    date_basis: filters.date_basis,
    page,
    page_size: pageSize,
  }
}

const loadCalls = async () => {
  loading.value = true
  try {
    const res = await getVoiceCalls(buildQueryParams())
    calls.value = res.items || []
    total.value = res.total || 0
  } catch (error: any) {
    ElMessage.error(t('voice.loadCallsFailed'))
  } finally {
    loading.value = false
  }
}

async function handleExportCsv() {
  exporting.value = true
  try {
    const [start_date, end_date] = filters.dateRange || []
    const blob = (await exportVoiceCallsCsv({
      account_id: filters.account_id ? Number(filters.account_id) : undefined,
      outbound_campaign_id: filters.outbound_campaign_id
        ? Number(filters.outbound_campaign_id)
        : undefined,
      status: filters.status || undefined,
      start_date: start_date || undefined,
      end_date: end_date || undefined,
      date_basis: filters.date_basis,
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

onMounted(() => {
  loadCalls()
})
</script>

<style scoped>
.voice-calls-page {
  width: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: flex-end;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
