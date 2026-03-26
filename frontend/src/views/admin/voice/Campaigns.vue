<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t('voice.campaignsTitle') }}</h1>
      <p class="page-desc">{{ $t('voice.campaignsDesc') }}</p>
    </div>
    <div class="table-card">
      <el-button type="primary" @click="showCreate = true">{{ $t('common.add') }}</el-button>
      <el-table :data="items" v-loading="loading" stripe class="mt-2">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="account_id" :label="$t('voice.accountIdCol')" width="100" />
        <el-table-column prop="name" :label="$t('common.name')" min-width="140" />
        <el-table-column prop="status" :label="$t('common.status')" width="100" />
        <el-table-column prop="timezone" :label="$t('voice.campaignTimezone')" width="130" show-overflow-tooltip />
        <el-table-column :label="$t('voice.campaignWindow')" width="140">
          <template #default="{ row }">
            {{ formatWindow(row) }}
          </template>
        </el-table-column>
        <el-table-column prop="max_concurrent" :label="$t('voice.campaignMaxConcurrent')" width="90" />
        <el-table-column :label="$t('voice.callerIdMode')" width="110">
          <template #default="{ row }">
            {{ callerModeLabel(row.caller_id_mode) }}
          </template>
        </el-table-column>
        <el-table-column prop="ai_mode" :label="$t('voice.aiMode')" width="90" />
        <el-table-column :label="$t('common.action')" width="280">
          <template #default="{ row }">
            <el-button size="small" @click="setStatus(row, 'running')">{{ $t('voice.start') }}</el-button>
            <el-button size="small" @click="setStatus(row, 'paused')">{{ $t('voice.pause') }}</el-button>
            <el-button size="small" type="warning" @click="openImport(row)">{{ $t('voice.importContacts') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <el-dialog v-model="showCreate" :title="$t('voice.newCampaign')" width="560px">
      <el-form label-width="140px">
        <el-form-item :label="$t('voice.accountIdCol')">
          <el-input v-model.number="form.account_id" type="number" />
        </el-form-item>
        <el-form-item :label="$t('common.name')">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item :label="$t('voice.campaignTimezone')">
          <el-input v-model="form.timezone" :placeholder="$t('voice.campaignTimezonePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('voice.campaignWindow')">
          <div class="window-row">
            <el-time-select
              v-model="form.window_start"
              :placeholder="$t('voice.windowStart')"
              start="00:00"
              step="00:30"
              end="23:30"
              style="width: 120px"
              clearable
            />
            <span class="window-sep">—</span>
            <el-time-select
              v-model="form.window_end"
              :placeholder="$t('voice.windowEnd')"
              start="00:00"
              step="00:30"
              end="23:30"
              style="width: 120px"
              clearable
            />
          </div>
          <p class="form-hint">{{ $t('voice.campaignWindowHint') }}</p>
        </el-form-item>
        <el-form-item :label="$t('voice.campaignMaxConcurrent')">
          <el-input-number v-model="form.max_concurrent" :min="1" :max="9999" />
        </el-form-item>
        <el-form-item :label="$t('voice.callerIdMode')">
          <el-select v-model="form.caller_id_mode" style="width: 100%">
            <el-option :label="$t('voice.callerModeFixed')" value="fixed" />
            <el-option :label="$t('voice.callerModeRoundRobin')" value="round_robin" />
            <el-option :label="$t('voice.callerModeRandom')" value="random" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.caller_id_mode === 'fixed'" :label="$t('voice.fixedCallerIdId')">
          <el-input-number v-model="form.fixed_caller_id_id" :min="1" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="$t('voice.aiMode')">
          <el-select v-model="form.ai_mode" style="width: 100%">
            <el-option label="IVR" value="ivr" />
            <el-option label="AI" value="ai" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="create">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="showImport" :title="$t('voice.importContacts')" width="520px">
      <el-input v-model="importText" type="textarea" :rows="8" :placeholder="$t('voice.onePhonePerLine')" />
      <template #footer>
        <el-button type="primary" @click="doImport">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { getVoiceCampaigns, createVoiceCampaign, setVoiceCampaignStatus, importVoiceCampaignContacts } from '@/api/voice-admin'

const { t } = useI18n()
const loading = ref(false)
const items = ref<any[]>([])
const showCreate = ref(false)
const form = ref({
  account_id: 1,
  name: '',
  timezone: 'Asia/Shanghai',
  window_start: '' as string | undefined,
  window_end: '' as string | undefined,
  max_concurrent: 1,
  caller_id_mode: 'fixed' as 'fixed' | 'round_robin' | 'random',
  fixed_caller_id_id: undefined as number | undefined,
  ai_mode: 'ivr' as 'ivr' | 'ai'
})
const showImport = ref(false)
const importRow = ref<any>(null)
const importText = ref('')

async function load() {
  loading.value = true
  try {
    const res: any = await getVoiceCampaigns()
    items.value = res.items || res.data?.items || []
  } finally {
    loading.value = false
  }
}

function formatWindow(row: { window_start?: string | null; window_end?: string | null }) {
  const a = row.window_start
  const b = row.window_end
  if (!a && !b) return '—'
  return `${a || '—'} – ${b || '—'}`
}

function callerModeLabel(mode: string | undefined) {
  const m: Record<string, string> = {
    fixed: t('voice.callerModeFixed'),
    round_robin: t('voice.callerModeRoundRobin'),
    random: t('voice.callerModeRandom')
  }
  return m[mode || 'fixed'] || mode || '—'
}

async function create() {
  if (!form.value.name?.trim()) {
    ElMessage.warning(t('voice.campaignNameRequired'))
    return
  }
  const payload: Record<string, unknown> = {
    account_id: form.value.account_id,
    name: form.value.name.trim(),
    timezone: form.value.timezone || 'Asia/Shanghai',
    max_concurrent: form.value.max_concurrent,
    caller_id_mode: form.value.caller_id_mode,
    ai_mode: form.value.ai_mode
  }
  if (form.value.window_start) payload.window_start = form.value.window_start
  if (form.value.window_end) payload.window_end = form.value.window_end
  if (form.value.caller_id_mode === 'fixed' && form.value.fixed_caller_id_id) {
    payload.fixed_caller_id_id = form.value.fixed_caller_id_id
  }
  await createVoiceCampaign(payload)
  ElMessage.success(t('voice.createSuccess'))
  showCreate.value = false
  load()
}

async function setStatus(row: any, status: string) {
  await setVoiceCampaignStatus(row.id, status)
  ElMessage.success(t('voice.updateSuccess'))
  load()
}

function openImport(row: any) {
  importRow.value = row
  importText.value = ''
  showImport.value = true
}

async function doImport() {
  const phones = importText.value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
  await importVoiceCampaignContacts(importRow.value.id, phones)
  ElMessage.success(t('voice.updateSuccess'))
  showImport.value = false
}

onMounted(load)
</script>
<style scoped>
.mt-2 { margin-top: 12px; }
.window-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.window-sep {
  color: var(--text-tertiary);
}
.form-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
