<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">{{ $t('voice.accountsTitle') }}</h1>
        <p class="page-desc">{{ $t('voice.accountsDesc') }}</p>
      </div>
    </div>

    <!-- 筛选 -->
    <div class="filter-card">
      <el-form :inline="true" :model="filters">
        <el-form-item :label="$t('voice.accountId')">
          <el-input
            v-model="filters.account_id"
            :placeholder="$t('voice.accountIdFilterHint')"
            clearable
            style="width: 120px"
          />
        </el-form-item>
        <el-form-item :label="$t('voice.accountNameSearch')">
          <el-input
            v-model="filters.account_name"
            :placeholder="$t('voice.accountNameSearchHint')"
            clearable
            style="width: 160px"
            @keyup.enter="loadData"
          />
        </el-form-item>
        <el-form-item :label="$t('voice.country')">
          <el-input v-model="filters.country_code" :placeholder="$t('voice.countryCode')" clearable style="width: 120px;" />
        </el-form-item>
        <el-form-item :label="$t('voice.assigneeStaff')">
          <el-select
            v-model="filters.sales_id"
            :placeholder="$t('voice.allStaff')"
            clearable
            filterable
            style="width: 180px"
          >
            <el-option
              v-for="u in staffOptions"
              :key="u.id"
              :label="staffLabel(u)"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('common.status')">
          <el-select v-model="filters.status" :placeholder="$t('voice.allStatus')" clearable>
            <el-option :label="$t('voice.active')" value="active" />
            <el-option :label="$t('voice.suspended')" value="suspended" />
            <el-option :label="$t('voice.closed')" value="closed" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">{{ $t('smsRecords.query') }}</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 数据表格 -->
    <div class="table-card">
      <div class="table-toolbar">
        <el-button type="primary" @click="openCreateVoice">{{ $t('voice.createVoiceAccount') }}</el-button>
      </div>
      <el-table :data="accounts" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column :label="$t('voice.localAccount')" width="150">
          <template #default="{ row }">
            <span>{{ row.account?.account_name || row.account_id }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('voice.assigneeStaff')" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.sales">{{ row.sales.real_name || row.sales.username }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="okcc_account" :label="$t('voice.okccAccount')" width="130" show-overflow-tooltip />
        <el-table-column :label="$t('voice.sipLoginName')" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.sip_login_hint || '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="external_id" :label="$t('voice.externalId')" width="120" show-overflow-tooltip />
        <el-table-column :label="$t('voice.defaultCallerNumber')" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.default_caller_number">{{ row.default_caller_number }}</span>
            <span v-else-if="row.default_caller_id_id">#{{ row.default_caller_id_id }}</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="country_code" :label="$t('voice.country')" width="80" />
        <el-table-column prop="balance" :label="$t('voice.balance')" width="100">
          <template #default="{ row }">
            ${{ parseFloat(row.balance || 0).toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="max_concurrent_calls" :label="$t('voice.maxConcurrentCalls')" width="100" />
        <el-table-column prop="daily_outbound_limit" :label="$t('voice.dailyOutboundLimit')" width="110" />
        <el-table-column prop="total_calls" :label="$t('voice.totalCalls')" width="90" />
        <el-table-column prop="total_minutes" :label="$t('voice.totalMinutes')" width="90" />
        <el-table-column prop="status" :label="$t('common.status')" width="90">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_sync_at" :label="$t('voice.lastSync')" width="160">
          <template #default="{ row }">
            {{ formatDate(row.last_sync_at) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('voice.syncError')" min-width="120">
          <template #default="{ row }">
            <el-tooltip v-if="row.sync_error" :content="row.sync_error" placement="top" max-width="400">
              <el-tag type="danger" effect="plain">{{ $t('voice.syncErrorShort') }}</el-tag>
            </el-tooltip>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="460" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openAssignStaff(row)">{{ $t('voice.editAssignee') }}</el-button>
            <el-button size="small" @click="goCallerIds(row)">{{ $t('voice.callerIdsShort') }}</el-button>
            <el-button size="small" @click="openEditSip(row)">{{ $t('voice.editSipUsername') }}</el-button>
            <el-button size="small" @click="syncAccount(row)">{{ $t('voice.sync') }}</el-button>
            <el-button size="small" @click="openQuota(row)">{{ $t('voice.quotaEdit') }}</el-button>
            <el-button size="small" type="danger" plain @click="resetSipPassword(row)">
              {{ $t('voice.resetSipPassword') }}
            </el-button>
            <el-button 
              size="small" 
              :type="row.status === 'active' ? 'warning' : 'success'"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'active' ? $t('voice.suspend') : $t('voice.resume') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </div>

    <el-dialog v-model="createVisible" :title="$t('voice.createVoiceAccountTitle')" width="480px" @closed="resetCreateForm">
      <p class="sip-hint">{{ $t('voice.createVoiceAccountHint') }}</p>
      <el-form label-width="120px">
        <el-form-item :label="$t('voice.businessAccountIdLabel')" required>
          <el-input-number
            v-model="createForm.account_id"
            :min="1"
            :step="1"
            controls-position="right"
            style="width: 100%"
            :placeholder="$t('voice.accountIdFilterHint')"
          />
        </el-form-item>
        <el-form-item :label="$t('voice.countryCode')" required>
          <el-input v-model="createForm.country_code" maxlength="10" show-word-limit :placeholder="$t('voice.countryCodeExample')" />
        </el-form-item>
        <el-form-item :label="$t('voice.assignMode')">
          <el-radio-group v-model="createForm.assign_mode">
            <el-radio value="inherit">{{ $t('voice.assignInherit') }}</el-radio>
            <el-radio value="none">{{ $t('voice.assignNone') }}</el-radio>
            <el-radio value="explicit">{{ $t('voice.assignExplicit') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="createForm.assign_mode === 'explicit'" :label="$t('voice.assigneeStaff')" required>
          <el-select
            v-model="createForm.sales_id"
            :placeholder="$t('voice.selectStaff')"
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="u in staffOptions"
              :key="u.id"
              :label="staffLabel(u)"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="createSaving" @click="submitCreateVoice">{{ $t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="sipVisible" :title="$t('voice.editSipUsername')" width="480px" @closed="sipForm.sip_username = ''">
      <p class="sip-hint">{{ $t('voice.editSipUsernameHint') }}</p>
      <el-form label-width="120px">
        <el-form-item :label="$t('voice.sipUsernameField')">
          <el-input v-model="sipForm.sip_username" clearable :placeholder="$t('voice.sipUsernamePlaceholder')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="sipVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="sipSaving" @click="saveSipUsername">{{ $t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="assignVisible" :title="$t('voice.editAssignee')" width="440px" @closed="assignForm.id = 0">
      <el-form label-width="120px">
        <el-form-item :label="$t('voice.assigneeStaff')">
          <el-select
            v-model="assignForm.sales_id"
            :placeholder="$t('voice.selectStaffOrClear')"
            clearable
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="u in staffOptions"
              :key="u.id"
              :label="staffLabel(u)"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
        <p class="sip-hint">{{ $t('voice.editAssigneeHint') }}</p>
      </el-form>
      <template #footer>
        <el-button @click="assignVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="assignSaving" @click="saveAssignStaff">{{ $t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="quotaVisible" :title="$t('voice.quotaEdit')" width="440px">
      <el-form label-width="140px">
        <el-form-item :label="$t('voice.maxConcurrentCalls')">
          <el-input-number v-model="quotaForm.max_concurrent_calls" :min="0" :max="99999" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="$t('voice.dailyOutboundLimit')">
          <el-input-number v-model="quotaForm.daily_outbound_limit" :min="0" :max="9999999" style="width: 100%" />
        </el-form-item>
        <p class="quota-hint">{{ $t('voice.quotaZeroHint') }}</p>
      </el-form>
      <template #footer>
        <el-button @click="quotaVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="quotaSaving" @click="saveQuota">{{ $t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/index'
import {
  createVoiceAccount,
  getVoiceAccounts,
  resetVoiceAccountSipPassword,
  updateVoiceAccount,
  type VoiceAccountListItem
} from '@/api/voice-admin'
import { formatDate } from '@/utils/date'

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const accounts = ref<VoiceAccountListItem[]>([])
/** 员工下拉（与 /admin/users 一致，不含超管） */
const staffOptions = ref<{ id: number; username: string; real_name?: string | null }[]>([])

const filters = ref({
  account_id: '',
  account_name: '',
  country_code: '',
  status: '',
  sales_id: undefined as number | undefined
})

const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0
})

const quotaVisible = ref(false)
const quotaSaving = ref(false)
const quotaForm = ref({ id: 0, max_concurrent_calls: 0, daily_outbound_limit: 0 })

const sipVisible = ref(false)
const sipSaving = ref(false)
const sipForm = ref({ id: 0, sip_username: '' as string })

const assignVisible = ref(false)
const assignSaving = ref(false)
const assignForm = ref({ id: 0, sales_id: undefined as number | undefined })

const createVisible = ref(false)
const createSaving = ref(false)
const createForm = ref({
  account_id: undefined as number | undefined,
  country_code: 'US',
  assign_mode: 'inherit' as 'inherit' | 'none' | 'explicit',
  sales_id: undefined as number | undefined
})

function staffLabel(u: { username: string; real_name?: string | null }) {
  const name = u.real_name?.trim() || u.username
  return u.real_name ? `${name} (${u.username})` : u.username
}

async function loadStaff() {
  try {
    const res: any = await request.get('/admin/users', { params: { status: 'active' } })
    staffOptions.value = res.users || []
  } catch {
    staffOptions.value = []
  }
}

function resetCreateForm() {
  createForm.value = {
    account_id: undefined,
    country_code: 'US',
    assign_mode: 'inherit',
    sales_id: undefined
  }
}

function openAssignStaff(row: VoiceAccountListItem) {
  assignForm.value = { id: row.id, sales_id: row.sales_id ?? undefined }
  assignVisible.value = true
}

async function saveAssignStaff() {
  assignSaving.value = true
  try {
    await updateVoiceAccount(assignForm.value.id, {
      sales_id: assignForm.value.sales_id ?? null
    })
    ElMessage.success(t('voice.updateSuccess'))
    assignVisible.value = false
    loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || t('common.failed'))
  } finally {
    assignSaving.value = false
  }
}

function openCreateVoice() {
  resetCreateForm()
  createVisible.value = true
}

async function submitCreateVoice() {
  const aid = createForm.value.account_id
  if (aid == null || aid < 1) {
    ElMessage.warning(t('voice.businessAccountIdInvalid'))
    return
  }
  const cc = createForm.value.country_code?.trim()
  if (!cc) {
    ElMessage.warning(t('voice.countryCodeRequired'))
    return
  }
  if (createForm.value.assign_mode === 'explicit' && !createForm.value.sales_id) {
    ElMessage.warning(t('voice.selectStaffRequired'))
    return
  }
  createSaving.value = true
  try {
    const payload: Parameters<typeof createVoiceAccount>[0] = {
      account_id: aid,
      country_code: cc,
      assign_mode: createForm.value.assign_mode
    }
    if (createForm.value.assign_mode === 'explicit') {
      payload.sales_id = createForm.value.sales_id
    }
    const res: any = await createVoiceAccount(payload)
    if (res?.success) {
      createVisible.value = false
      await ElMessageBox.alert(
        `${t('voice.sipUserLabel')}: ${res.sip_username ?? res.okcc_account ?? '—'}\n${t('voice.sipPasswordLabel')}: ${res.sip_password ?? '—'}\n\n${t('voice.voiceAccountIdLabel')}: ${res.voice_account_id}`,
        t('voice.createVoiceAccountSuccessTitle'),
        { confirmButtonText: t('common.confirm') }
      )
      loadData()
    }
  } catch (e: any) {
    // 4xx/5xx 多数已在 axios 拦截器中提示；仅补充网络错误与 422 校验详情
    const st = e?.response?.status
    if (!e?.response) {
      ElMessage.error(e?.message || t('common.failed'))
    } else if (st === 422) {
      const d = e?.response?.data?.detail
      ElMessage.error(typeof d === 'string' ? d : t('common.failed'))
    }
  } finally {
    createSaving.value = false
  }
}

function parseAccountIdFilter(): number | undefined {
  const s = filters.value.account_id?.trim()
  if (!s) return undefined
  const n = Number.parseInt(s, 10)
  return Number.isFinite(n) && n > 0 ? n : undefined
}

function goCallerIds(row: VoiceAccountListItem) {
  router.push({ path: '/admin/voice/caller-ids', query: { account_id: String(row.account_id) } })
}

function openEditSip(row: VoiceAccountListItem) {
  sipForm.value = {
    id: row.id,
    sip_username: row.sip_username ?? ''
  }
  sipVisible.value = true
}

async function saveSipUsername() {
  sipSaving.value = true
  try {
    await updateVoiceAccount(sipForm.value.id, {
      sip_username: sipForm.value.sip_username.trim() || null
    })
    ElMessage.success(t('voice.updateSuccess'))
    sipVisible.value = false
    loadData()
  } catch (e: any) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    sipSaving.value = false
  }
}

const openQuota = (row: VoiceAccountListItem) => {
  quotaForm.value = {
    id: row.id,
    max_concurrent_calls: row.max_concurrent_calls ?? 0,
    daily_outbound_limit: row.daily_outbound_limit ?? 0
  }
  quotaVisible.value = true
}

const saveQuota = async () => {
  quotaSaving.value = true
  try {
    await updateVoiceAccount(quotaForm.value.id, {
      max_concurrent_calls: quotaForm.value.max_concurrent_calls,
      daily_outbound_limit: quotaForm.value.daily_outbound_limit
    })
    ElMessage.success(t('voice.quotaSaved'))
    quotaVisible.value = false
    loadData()
  } catch (e: any) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    quotaSaving.value = false
  }
}

const getStatusType = (status: string) => {
  const map: Record<string, string> = {
    active: 'success',
    suspended: 'warning',
    closed: 'danger'
  }
  return map[status] || 'info'
}

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = {
    active: t('voice.active'),
    suspended: t('voice.suspended'),
    closed: t('voice.closed')
  }
  return map[status] || status
}

const loadData = async () => {
  loading.value = true
  try {
    const aid = parseAccountIdFilter()
    const res: any = await getVoiceAccounts({
      account_id: aid,
      account_name: filters.value.account_name?.trim() || undefined,
      country_code: filters.value.country_code || undefined,
      status: filters.value.status || undefined,
      sales_id: filters.value.sales_id,
      page: pagination.value.page,
      page_size: pagination.value.pageSize
    })
    if (res.success) {
      accounts.value = res.items || []
      pagination.value.total = res.total || 0
    }
  } catch (e: any) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    loading.value = false
  }
}

const syncAccount = async (row: VoiceAccountListItem) => {
  try {
    await request.post(`/admin/voice/accounts/${row.id}/sync`)
    ElMessage.success(t('voice.syncRequestSent'))
    loadData()
  } catch (e: any) {
    ElMessage.error(e.message || t('voice.syncFailed'))
  }
}

const toggleStatus = async (row: VoiceAccountListItem) => {
  const newStatus = row.status === 'active' ? 'suspended' : 'active'
  try {
    await updateVoiceAccount(row.id, { status: newStatus })
    ElMessage.success(t('voice.statusUpdated'))
    loadData()
  } catch (e: any) {
    ElMessage.error(e.message || t('common.failed'))
  }
}

const resetSipPassword = async (row: VoiceAccountListItem) => {
  try {
    await ElMessageBox.confirm(t('voice.confirmResetSipPassword'), t('voice.resetSipPassword'), {
      type: 'warning',
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel')
    })
  } catch {
    return
  }
  try {
    const res: any = await resetVoiceAccountSipPassword(row.id)
    if (res?.success && res.sip_password) {
      await ElMessageBox.alert(
        `${t('voice.sipUserLabel')}: ${res.sip_username || '—'}\n${t('voice.sipPasswordLabel')}: ${res.sip_password}`,
        t('voice.sipPasswordShowOnce'),
        { confirmButtonText: t('common.confirm'), dangerouslyUseHTMLString: false }
      )
      ElMessage.success(t('voice.sipPasswordResetLogged'))
    }
  } catch (e: any) {
    ElMessage.error(e.message || t('common.failed'))
  }
}

onMounted(() => {
  loadStaff()
  loadData()
})
</script>

<style scoped>
.page-container {
  width: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.page-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

.filter-card {
  background: var(--bg-card);
  padding: 16px 24px;
  border-radius: 12px;
  border: 1px solid var(--border-default);
  margin-bottom: 24px;
}

.table-card {
  background: var(--bg-card);
  padding: 16px;
  border-radius: 12px;
  border: 1px solid var(--border-default);
}

.table-toolbar {
  margin-bottom: 12px;
}

.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.quota-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0 0 0 140px;
}

.sip-hint {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 12px;
  line-height: 1.5;
}

.text-muted {
  color: var(--text-tertiary);
}
</style>
