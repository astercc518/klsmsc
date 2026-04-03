<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">{{ t('menu.adminCustomerData') }}</h2>
    </div>

    <el-alert
      v-if="summaryTruncated"
      type="info"
      :closable="false"
      show-icon
      class="summary-truncate-tip"
      :title="t('dataPool.privateLibTruncatedHint')"
    />

    <!-- 筛选（管理端） -->
    <div class="filter-section">
      <el-input
        v-model.number="filterForm.account_id"
        :placeholder="t('dataPool.adminFilterAccountId')"
        clearable
        class="filter-input"
        @keyup.enter="loadData"
      />
      <el-input
        v-model="filterForm.country_query"
        :placeholder="t('dataPool.adminFilterCountryQuery')"
        clearable
        class="filter-input"
        @keyup.enter="loadData"
      />
      <el-tooltip :content="t('dataPool.adminFilterMinCardCount')" placement="top">
        <el-input-number
          v-model="filterForm.min_card_count"
          :min="0"
          :precision="0"
          :step="1000"
          controls-position="right"
          class="filter-input-number filter-count-input"
        />
      </el-tooltip>
      <el-tooltip :content="t('dataPool.adminFilterMaxCardCount')" placement="top">
        <el-input-number
          v-model="filterForm.max_card_count"
          :min="0"
          :precision="0"
          :step="1000"
          controls-position="right"
          class="filter-input-number filter-count-input"
        />
      </el-tooltip>
      <el-input
        v-model="filterForm.batch_id"
        :placeholder="t('dataPool.searchBatch')"
        clearable
        class="filter-input"
        @keyup.enter="loadData"
      />
      <el-tooltip :content="t('dataPool.privateLibMaxBatchesHint')" placement="top">
        <el-input-number
          v-model="filterForm.max_batches"
          :min="0"
          :max="10000"
          :step="50"
          controls-position="right"
          class="filter-input-number"
        />
      </el-tooltip>
      <el-button type="primary" :icon="Search" @click="loadData">{{ t('common.search') }}</el-button>
      <el-button :icon="Refresh" @click="resetFilters">{{ t('common.reset') }}</el-button>
    </div>

    <div v-loading="loading" class="groups-wrap">
      <el-empty
        v-if="!loading && groups.length === 0"
        :description="t('dataPool.privateLibEmpty')"
      />

      <el-row :gutter="16">
        <el-col :xs="24" :sm="12" :lg="8" v-for="(g, idx) in groups" :key="idx">
          <el-card class="group-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <div class="card-title">
                  <span class="card-name">
                    <span class="admin-account-mark">#{{ g.account_id }} {{ g.account_name }}</span>
                    <span class="card-dim-sep">·</span>
                    <span class="card-dim-name">{{ getGroupName(g) }}</span>
                  </span>
                </div>
                <span class="card-count">
                  {{ g.count.toLocaleString() }}
                  {{ t('dataPool.privateLibPieces') }}
                </span>
              </div>
            </template>
            <div class="card-body">
              <div class="card-info">
                <div class="info-row" v-if="g.library_origin">
                  <span class="info-label">{{ t('dataMyNumbers.libraryOriginLabel') }}</span>
                  <el-tag size="small" :type="libraryOriginTagType(g.library_origin)">
                    {{ libraryOriginText(g.library_origin) }}
                  </el-tag>
                </div>
                <div class="usage-stats">
                  <div class="usage-item">
                    <span class="usage-label">{{ t('dataPool.privateLibUnused') }}</span>
                    <span class="usage-value success">{{ g.unused_count.toLocaleString() }}</span>
                  </div>
                  <div class="usage-item">
                    <span class="usage-label">{{ t('dataPool.privateLibUsed') }}</span>
                    <span class="usage-value info">{{ g.used_count.toLocaleString() }}</span>
                  </div>
                </div>
                <div class="info-row">
                  <span class="info-label">{{ t('dataPool.source') }}</span>
                  <el-tag size="small" type="danger">{{ g.source_label || g.source }}</el-tag>
                </div>
                <div class="info-row">
                  <span class="info-label">{{ t('dataPool.purpose') }}</span>
                  <el-tag size="small" type="warning">{{ g.purpose_label || g.purpose }}</el-tag>
                </div>
                <div class="info-row" v-if="g.remarks">
                  <span class="info-label">{{ t('dataPool.privateLibRemarksCol') }}</span>
                  <span class="info-remarks" :title="g.remarks">{{ g.remarks }}</span>
                </div>
                <div class="info-row" v-if="g.last_at">
                  <span class="info-label">{{ t('dataPool.privateLibLastAt') }}</span>
                  <span class="info-date">{{ fmtDate(g.last_at) }}</span>
                </div>
              </div>

              <div class="card-actions">
                <el-button type="danger" size="small" plain @click="handleDeleteGroup(g)">
                  {{ t('dataPool.privateLibDeleteCard') }}
                </el-button>
                <el-button type="primary" size="small" plain @click="handleImpersonateGroup(g)">
                  {{ t('dataPool.privateLibImpersonate') }}
                </el-button>
                <el-dropdown @command="(cmd: string) => handleExportGroup(g, cmd)">
                  <el-button type="primary" size="small">
                    {{ t('dataPool.privateLibDownload') }}
                    <el-icon style="margin-left: 4px"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="csv">{{ t('dataPool.privateLibExportCsv') }}</el-dropdown-item>
                      <el-dropdown-item command="txt">{{ t('dataPool.privateLibExportTxt') }}</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Search, Refresh, ArrowDown } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getAdminPrivateLibrarySummary,
  exportAdminPrivateLibraryNumbersUrl,
  impersonateAccount,
  deleteAdminPrivateLibraryCard,
} from '@/api/data-admin'
import { findCountryByIso, searchCountries } from '@/constants/countries'

const { t, locale } = useI18n()

/** 与客户卡片一致，并带管理端账户字段 */
interface AdminPrivateGroup {
  account_id: number
  account_name: string
  country_code: string
  source: string
  source_label: string
  purpose: string
  purpose_label: string
  count: number
  used_count: number
  unused_count: number
  carriers: { name: string; count: number }[]
  batch_id: string
  remarks: string
  first_at: string | null
  last_at: string | null
  library_origin?: string
}

const loading = ref(false)
const groups = ref<AdminPrivateGroup[]>([])
const summaryTruncated = ref(false)

const filterForm = ref({
  account_id: undefined as number | undefined,
  country_query: '',
  batch_id: '',
  max_batches: 0,
  min_card_count: undefined as number | undefined,
  max_card_count: undefined as number | undefined,
})

/** 将国家名称/国码/区号前缀解析为逗号分隔 ISO，供汇总接口 country_codes */
function resolveCountryCodesForSummary(raw: string): string | undefined {
  const q = raw.trim()
  if (!q) return undefined
  const hits = searchCountries(q)
  if (hits.length > 0) {
    const seen = new Set<string>()
    const codes: string[] = []
    for (const c of hits) {
      if (!seen.has(c.iso)) {
        seen.add(c.iso)
        codes.push(c.iso)
      }
    }
    return codes.join(',')
  }
  if (/^[A-Za-z]{2}$/.test(q)) return q.toUpperCase()
  return undefined
}

const apiV1Base =
  import.meta.env.VITE_API_BASE_URL != null && import.meta.env.VITE_API_BASE_URL !== ''
    ? `${import.meta.env.VITE_API_BASE_URL}/api/v1`
    : '/api/v1'

function libraryOriginText(origin: string) {
  if (origin === 'manual') return t('dataMyNumbers.libraryOriginManual')
  if (origin === 'purchased') return t('dataMyNumbers.libraryOriginPurchased')
  if (origin === 'mixed') return t('dataMyNumbers.libraryOriginMixed')
  return origin
}

function libraryOriginTagType(origin: string): 'success' | 'warning' | 'info' {
  if (origin === 'manual') return 'success'
  if (origin === 'purchased') return 'warning'
  return 'info'
}

function getGroupName(group: AdminPrivateGroup) {
  const country = findCountryByIso(group.country_code)
  const countryName = country ? country.name : group.country_code || t('dataPool.unknown')
  const sourceName = group.source_label || group.source || '—'
  const purposeName = group.purpose_label || group.purpose || '—'
  const baseName = `${countryName}-${sourceName}-${purposeName}`
  if (group.remarks && group.remarks !== '') {
    return `${baseName} (${group.remarks})`
  }
  if (group.last_at) {
    return `${baseName} [${fmtDate(group.last_at)}]`
  }
  return baseName
}

function fmtDate(d: string | null): string {
  if (!d) return '-'
  const loc = String(locale.value || '').toLowerCase().startsWith('zh') ? 'zh-CN' : 'en-US'
  return new Date(d).toLocaleDateString(loc)
}

async function loadData() {
  loading.value = true
  summaryTruncated.value = false
  try {
    const params: Record<string, unknown> = {
      max_batches: filterForm.value.max_batches ?? 0,
    }
    if (filterForm.value.account_id != null && filterForm.value.account_id !== ('' as unknown as number)) {
      const n = Number(filterForm.value.account_id)
      if (!Number.isNaN(n) && n > 0) params.account_id = n
    }
    const countryCodes = resolveCountryCodesForSummary(filterForm.value.country_query || '')
    if (countryCodes) params.country_codes = countryCodes
    if (filterForm.value.batch_id?.trim()) params.batch_id = filterForm.value.batch_id.trim()
    if (filterForm.value.min_card_count != null && filterForm.value.min_card_count >= 0) {
      params.min_card_count = filterForm.value.min_card_count
    }
    if (filterForm.value.max_card_count != null && filterForm.value.max_card_count >= 0) {
      params.max_card_count = filterForm.value.max_card_count
    }

    const res: any = await getAdminPrivateLibrarySummary(params)
    if (res.success) {
      groups.value = (res.items || []) as AdminPrivateGroup[]
      summaryTruncated.value = Boolean(res.meta?.truncated)
    } else {
      ElMessage.error(t('common.loadFailed'))
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filterForm.value = {
    account_id: undefined,
    country_query: '',
    batch_id: '',
    max_batches: 0,
    min_card_count: undefined,
    max_card_count: undefined,
  }
  loadData()
}

async function handleDeleteGroup(g: AdminPrivateGroup) {
  try {
    await ElMessageBox.confirm(
      t('dataPool.privateLibDeleteConfirm', {
        account: g.account_id,
        count: g.count.toLocaleString(),
        name: getGroupName(g),
      }),
      t('dataPool.privateLibDeleteTitle'),
      {
        type: 'warning',
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
      },
    )
  } catch {
    return
  }
  try {
    const res = await deleteAdminPrivateLibraryCard({
      account_id: g.account_id,
      country_code: g.country_code ?? '',
      source: g.source ?? '',
      purpose: g.purpose ?? '',
      batch_id: g.batch_id ?? '',
      remarks: g.remarks || undefined,
    })
    if (res.success === false) {
      ElMessage.warning(res.message || t('common.operationFailed'))
      return
    }
    ElMessage.success(res.message || t('common.operationSuccess'))
    await loadData()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('common.operationFailed'))
  }
}

async function handleImpersonateGroup(g: AdminPrivateGroup) {
  try {
    const res: any = await impersonateAccount(g.account_id)
    if (res.success && res.api_key) {
      const params = new URLSearchParams({
        impersonate: '1',
        api_key: res.api_key,
        account_id: String(g.account_id),
        account_name: g.account_name || '',
        redirect: '/data/my-numbers',
      })
      window.open(`/login?${params.toString()}`, '_blank')
      ElMessage.success(t('customers.impersonateSuccess', { name: g.account_name || g.account_id }))
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.message || t('common.error'))
  }
}

/** 按当前卡片维度导出私库明细（CSV）；TXT 为纯号码，复用同接口加 fmt=txt 若后端支持——当前仅 CSV，TXT 用前端说明 */
function handleExportGroup(g: AdminPrivateGroup, fmt: string) {
  const token = localStorage.getItem('admin_token')
  const params: Record<string, string | number | boolean> = {
    account_id: g.account_id,
    country_code: g.country_code || '',
    batch_id: g.batch_id ?? '',
    source: g.source || '',
    purpose: g.purpose || '',
  }
  if (fmt === 'csv') {
    const path = exportAdminPrivateLibraryNumbersUrl(params)
    const downloadUrl = `${apiV1Base}${path.startsWith('/') ? path : `/${path}`}`
    fetch(downloadUrl, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((response) => {
        if (!response.ok) throw new Error(t('common.operationFailed'))
        return response.blob().then((blob) => ({ blob, response }))
      })
      .then(({ blob, response }) => {
        const filenameMatch = response.headers.get('content-disposition')?.match(/filename="?([^"]+)"?/)
        const filename = filenameMatch
          ? filenameMatch[1]
          : `private_lib_${g.account_id}_${Date.now()}.csv`
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = filename
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        URL.revokeObjectURL(link.href)
        ElMessage.success(t('common.operationSuccess'))
      })
      .catch(() => {
        ElMessage.error(t('common.operationFailed'))
      })
    return
  }
  if (fmt === 'txt') {
    ElMessage.info(t('dataPool.privateLibTxtHint'))
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.summary-truncate-tip {
  margin-bottom: 16px;
}
.page-container {
  width: 100%;
  padding: 0 4px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0;
}

.filter-section {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding: 14px 16px;
  background: var(--el-fill-color-light);
  border-radius: 12px;
  border: 1px solid var(--el-border-color-lighter);
}
.filter-input {
  width: 200px;
  max-width: 100%;
}
.filter-input-number {
  width: 160px;
}

.usage-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  padding: 10px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}
.usage-item {
  display: flex;
  flex-direction: column;
  flex: 1;
}
.usage-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-bottom: 2px;
}
.usage-value {
  font-size: 16px;
  font-weight: 700;
}
.usage-value.success {
  color: var(--el-color-success);
}
.usage-value.info {
  color: var(--el-color-info);
}

.group-card {
  margin-bottom: 16px;
  border-radius: 12px;
  transition: transform 0.2s;
}
.group-card:hover {
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}
.card-title {
  display: flex;
  align-items: flex-start;
  min-width: 0;
  flex: 1;
}
.card-name {
  font-weight: 600;
  font-size: 14px;
  line-height: 1.4;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px;
  min-width: 0;
}
.admin-account-mark {
  color: var(--el-color-primary);
  flex-shrink: 0;
}
.card-dim-sep {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.card-dim-name {
  word-break: break-word;
  min-width: 0;
}
.card-count {
  font-size: 18px;
  font-weight: 700;
  color: var(--el-color-primary);
  flex-shrink: 0;
  white-space: nowrap;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.card-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.info-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.info-label {
  color: var(--el-text-color-secondary);
  min-width: 56px;
  flex-shrink: 0;
}
.info-date {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.card-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.info-remarks {
  color: var(--el-text-color-regular);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}
.groups-wrap {
  min-height: 200px;
}
</style>
