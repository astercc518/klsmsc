<template>
  <div class="voice-page">
    <div class="page-header">
      <h1 class="page-title">{{ $t('voiceCustomer.outboundCampaignsTitle') }}</h1>
      <p class="page-desc">{{ $t('voiceCustomer.outboundCampaignsDesc') }}</p>
    </div>

    <el-card v-loading="loading">
      <div class="toolbar">
        <el-button type="primary" @click="openCreate">{{ $t('voice.newCampaign') }}</el-button>
      </div>
      <el-table :data="items" stripe class="mt-table">
        <el-table-column prop="id" label="ID" width="72" />
        <el-table-column prop="name" :label="$t('common.name')" min-width="140" />
        <el-table-column prop="status" :label="$t('common.status')" width="100" />
        <el-table-column prop="timezone" :label="$t('voice.campaignTimezone')" width="130" show-overflow-tooltip />
        <el-table-column :label="$t('voice.campaignWindow')" width="140">
          <template #default="{ row }">
            {{ formatWindow(row) }}
          </template>
        </el-table-column>
        <el-table-column prop="max_concurrent" :label="$t('voice.campaignMaxConcurrent')" width="88" />
        <el-table-column :label="$t('voice.callerIdMode')" width="108">
          <template #default="{ row }">
            {{ callerModeLabel(row.caller_id_mode) }}
          </template>
        </el-table-column>
        <el-table-column prop="ai_mode" :label="$t('voice.aiMode')" width="80" />
        <el-table-column :label="$t('common.action')" width="380" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="setStatus(row, 'running')">{{ $t('voice.start') }}</el-button>
            <el-button size="small" @click="setStatus(row, 'paused')">{{ $t('voice.pause') }}</el-button>
            <el-button
              v-if="row.status === 'draft' || row.status === 'paused'"
              size="small"
              @click="openEdit(row)"
            >
              {{ $t('dialog.edit') }}
            </el-button>
            <el-button size="small" type="warning" @click="openImport(row)">{{ $t('voice.importContacts') }}</el-button>
            <el-button size="small" type="info" @click="openContacts(row)">{{ $t('voice.viewContacts') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showCreate" :title="$t('voice.newCampaign')" width="560px">
      <el-form label-width="140px">
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
        <el-form-item v-if="form.ai_mode === 'ai'" :label="$t('voice.aiPrompt', 'AI Prompt')">
          <el-input v-model="form.ai_prompt" type="textarea" :rows="4" :placeholder="$t('voice.aiPromptHint', 'Enter ChatGPT/LLM system prompt')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="create">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEdit" :title="$t('voice.editCampaign')" width="560px">
      <p class="form-hint">{{ $t('voice.editCampaignHint') }}</p>
      <el-form label-width="140px">
        <el-form-item :label="$t('common.name')">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item :label="$t('voice.campaignTimezone')">
          <el-input v-model="editForm.timezone" />
        </el-form-item>
        <el-form-item :label="$t('voice.campaignWindow')">
          <div class="window-row">
            <el-time-select v-model="editForm.window_start" start="00:00" step="00:30" end="23:30" style="width: 120px" clearable />
            <span class="window-sep">—</span>
            <el-time-select v-model="editForm.window_end" start="00:00" step="00:30" end="23:30" style="width: 120px" clearable />
          </div>
        </el-form-item>
        <el-form-item :label="$t('voice.campaignMaxConcurrent')">
          <el-input-number v-model="editForm.max_concurrent" :min="1" :max="9999" />
        </el-form-item>
        <el-form-item :label="$t('voice.callerIdMode')">
          <el-select v-model="editForm.caller_id_mode" style="width: 100%">
            <el-option :label="$t('voice.callerModeFixed')" value="fixed" />
            <el-option :label="$t('voice.callerModeRoundRobin')" value="round_robin" />
            <el-option :label="$t('voice.callerModeRandom')" value="random" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editForm.caller_id_mode === 'fixed'" :label="$t('voice.fixedCallerIdId')">
          <el-input-number v-model="editForm.fixed_caller_id_id" :min="1" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="$t('voice.aiMode')">
          <el-select v-model="editForm.ai_mode" style="width: 100%">
            <el-option label="IVR" value="ivr" />
            <el-option label="AI" value="ai" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editForm.ai_mode === 'ai'" :label="$t('voice.aiPrompt', 'AI Prompt')">
          <el-input v-model="editForm.ai_prompt" type="textarea" :rows="4" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="saveEdit">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showImport" :title="$t('voice.importContacts')" width="560px">
      <el-input v-model="importText" type="textarea" :rows="8" :placeholder="$t('voice.onePhonePerLine')" />
      <p class="form-hint">{{ $t('voiceCustomer.csvImportHint') }}</p>
      <el-upload
        class="csv-upload"
        :show-file-list="false"
        accept=".csv,text/csv"
        :before-upload="onCsvBeforeUpload"
      >
        <el-button type="success" plain>{{ $t('voiceCustomer.uploadCsv') }}</el-button>
      </el-upload>
      <template #footer>
        <el-button @click="showImport = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="doImport">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showContacts" :title="$t('voice.campaignContactsTitle')" width="720px" @opened="onContactsOpened">
      <div class="contacts-toolbar">
        <span>{{ $t('voice.contactStatusFilter') }}</span>
        <el-select v-model="contactStatus" style="width: 160px" @change="contactPage = 1; loadContacts()">
          <el-option :label="$t('voice.allContactStatus')" value="" />
          <el-option label="pending" value="pending" />
          <el-option label="dialing" value="dialing" />
          <el-option label="completed" value="completed" />
          <el-option label="failed" value="failed" />
          <el-option label="skipped" value="skipped" />
        </el-select>
      </div>
      <el-table :data="contactItems" v-loading="contactsLoading" stripe max-height="420">
        <el-table-column prop="phone_e164" :label="$t('voice.contactPhone')" min-width="140" />
        <el-table-column prop="status" :label="$t('common.status')" width="100" />
        <el-table-column prop="attempt_count" :label="$t('voice.contactAttempts')" width="90" />
        <el-table-column prop="last_error" :label="$t('voice.contactLastError')" min-width="160" show-overflow-tooltip />
      </el-table>
      <el-pagination
        v-if="contactTotal > 0"
        class="mt-2"
        layout="prev, pager, next, total"
        :total="contactTotal"
        v-model:current-page="contactPage"
        :page-size="contactPageSize"
        @current-change="loadContacts"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import {
  getVoiceOutboundCampaignsCustomer,
  createVoiceOutboundCampaignCustomer,
  updateVoiceOutboundCampaignCustomer,
  setVoiceOutboundCampaignStatusCustomer,
  importVoiceCampaignContactsCustomer,
  importVoiceCampaignContactsCsvCustomer,
  getVoiceCampaignContactsCustomer,
} from '@/api/voice-customer'

const { t } = useI18n()
const loading = ref(false)
const items = ref<any[]>([])
const showCreate = ref(false)
const form = ref({
  name: '',
  timezone: 'Asia/Shanghai',
  window_start: '' as string | undefined,
  window_end: '' as string | undefined,
  max_concurrent: 1,
  caller_id_mode: 'fixed' as 'fixed' | 'round_robin' | 'random',
  fixed_caller_id_id: undefined as number | undefined,
  ai_mode: 'ivr' as 'ivr' | 'ai',
  ai_prompt: '',
})

const showEdit = ref(false)
const editRow = ref<any>(null)
const editForm = ref({
  name: '',
  timezone: 'Asia/Shanghai',
  window_start: '' as string | undefined,
  window_end: '' as string | undefined,
  max_concurrent: 1,
  caller_id_mode: 'fixed' as 'fixed' | 'round_robin' | 'random',
  fixed_caller_id_id: undefined as number | undefined,
  ai_mode: 'ivr' as 'ivr' | 'ai',
  ai_prompt: '',
})

const showImport = ref(false)
const importRow = ref<any>(null)
const importText = ref('')

const showContacts = ref(false)
const contactsRow = ref<any>(null)
const contactItems = ref<any[]>([])
const contactTotal = ref(0)
const contactPage = ref(1)
const contactPageSize = ref(20)
const contactStatus = ref('')
const contactsLoading = ref(false)

async function load() {
  loading.value = true
  try {
    const res: any = await getVoiceOutboundCampaignsCustomer()
    items.value = res.items || []
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
    random: t('voice.callerModeRandom'),
  }
  return m[mode || 'fixed'] || mode || '—'
}

function openCreate() {
  form.value = {
    name: '',
    timezone: 'Asia/Shanghai',
    window_start: undefined,
    window_end: undefined,
    max_concurrent: 1,
    caller_id_mode: 'fixed',
    fixed_caller_id_id: undefined,
    ai_mode: 'ivr',
    ai_prompt: '',
  }
  showCreate.value = true
}

async function create() {
  if (!form.value.name?.trim()) {
    ElMessage.warning(t('voice.campaignNameRequired'))
    return
  }
  const payload: Record<string, unknown> = {
    name: form.value.name.trim(),
    timezone: form.value.timezone || 'Asia/Shanghai',
    max_concurrent: form.value.max_concurrent,
    caller_id_mode: form.value.caller_id_mode,
    ai_mode: form.value.ai_mode,
  }
  if (form.value.window_start) payload.window_start = form.value.window_start
  if (form.value.window_end) payload.window_end = form.value.window_end
  if (form.value.caller_id_mode === 'fixed' && form.value.fixed_caller_id_id) {
    payload.fixed_caller_id_id = form.value.fixed_caller_id_id
  }
  if (form.value.ai_mode === 'ai') {
    payload.ai_prompt = form.value.ai_prompt || ''
  }
  await createVoiceOutboundCampaignCustomer(payload)
  ElMessage.success(t('voice.createSuccess'))
  showCreate.value = false
  load()
}

async function setStatus(row: any, status: string) {
  await setVoiceOutboundCampaignStatusCustomer(row.id, status)
  ElMessage.success(t('voice.updateSuccess'))
  load()
}

function openEdit(row: any) {
  editRow.value = row
  editForm.value = {
    name: row.name || '',
    timezone: row.timezone || 'Asia/Shanghai',
    window_start: row.window_start || undefined,
    window_end: row.window_end || undefined,
    max_concurrent: row.max_concurrent ?? 1,
    caller_id_mode: (row.caller_id_mode || 'fixed') as 'fixed' | 'round_robin' | 'random',
    fixed_caller_id_id: row.fixed_caller_id_id ?? undefined,
    ai_mode: (row.ai_mode || 'ivr') as 'ivr' | 'ai',
    ai_prompt: row.ai_prompt || '',
  }
  showEdit.value = true
}

async function saveEdit() {
  if (!editRow.value?.id) return
  if (!editForm.value.name?.trim()) {
    ElMessage.warning(t('voice.campaignNameRequired'))
    return
  }
  const payload: Record<string, unknown> = {
    name: editForm.value.name.trim(),
    timezone: editForm.value.timezone || 'Asia/Shanghai',
    max_concurrent: editForm.value.max_concurrent,
    caller_id_mode: editForm.value.caller_id_mode,
    ai_mode: editForm.value.ai_mode,
  }
  if (editForm.value.window_start) payload.window_start = editForm.value.window_start
  else payload.window_start = null
  if (editForm.value.window_end) payload.window_end = editForm.value.window_end
  else payload.window_end = null
  if (editForm.value.caller_id_mode === 'fixed' && editForm.value.fixed_caller_id_id) {
    payload.fixed_caller_id_id = editForm.value.fixed_caller_id_id
  } else {
    payload.fixed_caller_id_id = null
  }
  if (editForm.value.ai_mode === 'ai') {
    payload.ai_prompt = editForm.value.ai_prompt || ''
  } else {
    payload.ai_prompt = null
  }
  await updateVoiceOutboundCampaignCustomer(editRow.value.id, payload)
  ElMessage.success(t('voice.updateSuccess'))
  showEdit.value = false
  load()
}

function openImport(row: any) {
  importRow.value = row
  importText.value = ''
  showImport.value = true
}

async function doImport() {
  const phones = importText.value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
  await importVoiceCampaignContactsCustomer(importRow.value.id, phones)
  ElMessage.success(t('voice.updateSuccess'))
  showImport.value = false
}

async function onCsvBeforeUpload(file: File) {
  if (!importRow.value?.id) return false
  try {
    const res: any = await importVoiceCampaignContactsCsvCustomer(importRow.value.id, file)
    ElMessage.success(t('voiceCustomer.csvImported', { n: res.imported ?? 0 }))
    showImport.value = false
    load()
  } catch {
    ElMessage.error(t('common.failed'))
  }
  return false
}

function openContacts(row: any) {
  contactsRow.value = row
  contactPage.value = 1
  contactStatus.value = ''
  contactItems.value = []
  contactTotal.value = 0
  showContacts.value = true
}

function onContactsOpened() {
  loadContacts()
}

async function loadContacts() {
  if (!contactsRow.value?.id) return
  contactsLoading.value = true
  try {
    const res: any = await getVoiceCampaignContactsCustomer(contactsRow.value.id, {
      page: contactPage.value,
      page_size: contactPageSize.value,
      status: contactStatus.value || undefined,
    })
    contactItems.value = res.items || []
    contactTotal.value = res.total ?? 0
  } finally {
    contactsLoading.value = false
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
.toolbar {
  margin-bottom: 16px;
}
.mt-table {
  margin-top: 0;
}
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
  margin: 8px 0;
  font-size: 12px;
  color: var(--text-tertiary);
}
.csv-upload {
  margin-top: 8px;
}
.contacts-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.mt-2 {
  margin-top: 12px;
}
</style>
