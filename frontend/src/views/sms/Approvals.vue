<template>
  <div class="approvals-page">
    <!-- 与「发送短信」页一致的概览卡片，便于扫一眼掌握队列 -->
    <div class="stats-cards">
      <div class="stat-card">
        <div class="stat-icon filtered">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M3 4h14M6 8h8M9 12h2M10 16h0.01" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ total }}</span>
          <span class="stat-label">{{ t('smsApprovalsPage.statFiltered') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon page">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5" />
            <path d="M7 6h6M7 10h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ list.length }}</span>
          <span class="stat-label">{{ t('smsApprovalsPage.statPageRows') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon pending">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5" />
            <path d="M10 6v4l3 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ pendingGlobalTotal }}</span>
          <span class="stat-label">{{ t('smsApprovalsPage.statPendingAll') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon sendable">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M18 2L9 11M18 2l-6 16-3-7-7-3 16-6z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ sendableOnPage }}</span>
          <span class="stat-label">{{ t('smsApprovalsPage.statSendablePage') }}</span>
        </div>
      </div>
    </div>

    <div class="form-panel">
      <div class="panel-accent" aria-hidden="true" />
      <div class="panel-header">
        <div class="panel-header-text">
          <h1 class="panel-title">{{ t('menu.smsApprovals') }}</h1>
          <p class="panel-desc">{{ t('smsApprovalsPage.pageDesc') }}</p>
        </div>
        <div class="panel-header-actions">
          <el-button type="primary" class="header-btn-primary" @click="showSubmitDialog">
            <el-icon><Plus /></el-icon>
            {{ t('smsApprovalsPage.submitAudit') }}
          </el-button>
          <el-button class="header-btn-ghost" @click="loadList">
            <el-icon><Refresh /></el-icon>
            {{ t('common.refresh') }}
          </el-button>
        </div>
      </div>

      <div class="panel-toolbar">
        <div class="filter-section">
          <el-select
            v-model="filterStatus"
            :placeholder="t('smsApprovalsPage.allStatus')"
            clearable
            class="filter-status"
            @change="onFilterChange"
          >
            <el-option :label="t('smsApprovalsPage.pending')" value="pending" />
            <el-option :label="t('smsApprovalsPage.approved')" value="approved" />
            <el-option :label="t('smsApprovalsPage.rejected')" value="rejected" />
          </el-select>
          <el-input
            v-model="searchKeyword"
            clearable
            :prefix-icon="Search"
            :placeholder="t('smsApprovalsPage.searchPlaceholder')"
            class="filter-search"
            @clear="flushSearch"
          />
        </div>
        <span class="toolbar-hint">{{ t('smsApprovalsPage.filterHint') }}</span>
      </div>

      <div class="table-scroll">
        <el-table
          v-loading="loading"
          :data="list"
          size="default"
          class="data-table approvals-table"
          :table-layout="'auto'"
          :max-height="tableMaxHeight ?? undefined"
          :empty-text="t('smsApprovalsPage.emptyText')"
        >
          <el-table-column
            prop="approval_no"
            :label="t('smsApprovalsPage.colApprovalNo')"
            min-width="124"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <span class="mono cell-approval-no">{{ row.approval_no }}</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="phone_number"
            :label="t('smsApprovalsPage.colPhone')"
            min-width="108"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <span class="cell-phone">{{ row.phone_number?.trim() || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="content"
            :label="t('smsApprovalsPage.colContent')"
            min-width="200"
            show-overflow-tooltip
          />
          <el-table-column
            prop="status"
            :label="t('smsApprovalsPage.colStatus')"
            width="96"
            align="center"
          >
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="reviewed_at"
            :label="t('smsApprovalsPage.colReviewedAt')"
            min-width="148"
            show-overflow-tooltip
            class-name="col-time"
          >
            <template #default="{ row }">
              <span class="time-text">{{ row.reviewed_at ? formatTime(row.reviewed_at) : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="created_at"
            :label="t('smsApprovalsPage.colCreatedAt')"
            min-width="148"
            show-overflow-tooltip
            class-name="col-time"
          >
            <template #default="{ row }">
              <span class="time-text">{{ formatTime(row.created_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('smsApprovalsPage.colAction')"
            width="168"
            fixed="right"
            align="center"
          >
            <template #default="{ row }">
              <div class="action-cell">
                <el-button
                  v-if="row.status === 'approved' && !row.message_id"
                  type="primary"
                  size="small"
                  :loading="jumpToSendLoadingId === row.id"
                  @click.stop="handleExecute(row)"
                >
                  {{ t('smsApprovalsPage.sendNow') }}
                </el-button>
                <el-button v-else-if="row.message_id" type="success" size="small" disabled>
                  {{ t('smsApprovalsPage.sent') }}
                </el-button>
                <span v-else class="cell-action-placeholder">—</span>
                <el-button
                  v-if="!row.message_id"
                  type="danger"
                  link
                  size="small"
                  :loading="deleteLoadingId === row.id"
                  @click.stop="handleDelete(row)"
                >
                  {{ t('common.delete') }}
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="loadList"
          @current-change="loadList"
        />
      </div>
    </div>

    <el-dialog v-model="submitVisible" :title="t('smsApprovalsPage.dialogSubmitTitle')" width="min(500px, 92vw)" @close="resetSubmitForm">
      <p class="dialog-submit-tip">{{ t('smsApprovalsPage.submitContentOnlyTip') }}</p>
      <el-form ref="submitFormRef" :model="submitForm" :rules="submitRules" label-width="88px">
        <el-form-item :label="t('smsApprovalsPage.messageLabel')" prop="message">
          <el-input
            v-model="submitForm.message"
            type="textarea"
            :rows="6"
            :placeholder="t('smsApprovalsPage.messagePlaceholder')"
            maxlength="1000"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">{{ t('smsApprovalsPage.submitAudit') }}</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { getSmsApprovals, submitSmsApproval, getSmsApprovalDetail, deleteSmsApproval } from '@/api/sms'

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const list = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filterStatus = ref<string>('')
const searchKeyword = ref('')
/** 全账户待审核条数（与当前列表筛选无关，独立请求） */
const pendingGlobalTotal = ref(0)
let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null

const sendableOnPage = computed(
  () => list.value.filter((r) => r.status === 'approved' && !r.message_id).length,
)

async function refreshPendingTotal() {
  try {
    const res: any = await getSmsApprovals({ status: 'pending', limit: 1, offset: 0 })
    pendingGlobalTotal.value = Number(res?.total) || 0
  } catch {
    pendingGlobalTotal.value = 0
  }
}

const submitVisible = ref(false)
const submitting = ref(false)
const submitFormRef = ref<FormInstance>()
const submitForm = ref({ message: '' })
const submitRules = computed<FormRules>(() => ({
  message: [{ required: true, message: t('smsSend.enterContent'), trigger: 'blur' }],
}))

/** 跳转发送页时加载审核详情 */
const jumpToSendLoadingId = ref<number | null>(null)
const deleteLoadingId = ref<number | null>(null)

/** 视口高度，用于表格仅在实际行数超出可视区域时启用纵向滚动 */
const viewportH = ref(typeof window !== 'undefined' ? window.innerHeight : 800)
function updateViewport() {
  viewportH.value = window.innerHeight
}

const tableMaxHeight = computed(() => {
  const n = list.value.length
  if (n === 0) return undefined
  const headerApprox = 48
  const rowApprox = 52
  const natural = headerApprox + n * rowApprox
  const reserve = 296
  const cap = Math.max(280, viewportH.value - reserve)
  return natural > cap ? cap : undefined
})

watch(searchKeyword, () => {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    page.value = 1
    loadList()
  }, 320)
})

const statusLabel = (s: string) => {
  const m: Record<string, string> = {
    pending: t('smsApprovalsPage.pending'),
    approved: t('smsApprovalsPage.approved'),
    rejected: t('smsApprovalsPage.rejected'),
  }
  return m[s] || s
}

const statusType = (s: string) => {
  const m: Record<string, string> = { pending: 'warning', approved: 'success', rejected: 'danger' }
  return m[s] || 'info'
}

const formatTime = (time: string) => {
  if (!time) return '-'
  try {
    const d = new Date(time)
    return d.toLocaleString()
  } catch {
    return time
  }
}

const onFilterChange = () => {
  page.value = 1
  loadList()
}

const flushSearch = () => {
  page.value = 1
  loadList()
}

const loadList = async () => {
  loading.value = true
  try {
    const q = searchKeyword.value.trim()
    const res: any = await getSmsApprovals({
      status: filterStatus.value || undefined,
      search: q || undefined,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    list.value = res.items || []
    total.value = res.total || 0
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('smsApprovalsPage.loadFailed'))
  } finally {
    loading.value = false
  }
  void refreshPendingTotal()
}

const showSubmitDialog = () => {
  submitVisible.value = true
}

const resetSubmitForm = () => {
  submitForm.value = { message: '' }
  submitFormRef.value?.resetFields()
}

const handleSubmit = async () => {
  if (!submitFormRef.value) return
  await submitFormRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const res: any = await submitSmsApproval({ message: submitForm.value.message.trim() })
      const ticketHint = res?.ticket_no
        ? ` ${t('smsApprovalsPage.ticketNo', { no: res.ticket_no })}`
        : ''
      ElMessage.success(`${t('smsApprovalsPage.submitOk')}${ticketHint}`)
      submitVisible.value = false
      resetSubmitForm()
      loadList()
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || e?.message || t('smsApprovalsPage.submitFailed'))
    } finally {
      submitting.value = false
    }
  })
}

/** 立即发送：跳转发送短信页并预填完整审核文案（及已有号码） */
const handleExecute = async (row: any) => {
  jumpToSendLoadingId.value = row.id
  try {
    const res: any = await getSmsApprovalDetail(row.id)
    const message = typeof res.content === 'string' ? res.content : ''
    const phone = (res.phone_number || '').trim()
    sessionStorage.setItem(
      'sms_send_prefill_from_approval',
      JSON.stringify({
        message,
        phone_numbers_text: phone,
      }),
    )
    await router.push({ name: 'SmsSend' })
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('smsApprovalsPage.detailLoadFailed'))
  } finally {
    jumpToSendLoadingId.value = null
  }
}

function handleDelete(row: any) {
  ElMessageBox.confirm(t('smsApprovalsPage.deleteConfirm'), t('common.tip'), {
    type: 'warning',
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel'),
  })
    .then(async () => {
      deleteLoadingId.value = row.id
      try {
        await deleteSmsApproval(row.id)
        ElMessage.success(t('smsApprovalsPage.deleteOk'))
        loadList()
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.detail || e?.message || t('smsApprovalsPage.deleteFailed'))
      } finally {
        deleteLoadingId.value = null
      }
    })
    .catch(() => {})
}

onMounted(() => {
  updateViewport()
  window.addEventListener('resize', updateViewport)
  loadList()
})

onUnmounted(() => {
  window.removeEventListener('resize', updateViewport)
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
})
</script>

<style scoped>
/* 与发送短信页相同的通栏节奏：无 max-width，避免宽屏两侧大块留白 */
.approvals-page {
  width: 100%;
  min-height: 100%;
  box-sizing: border-box;
}

.stats-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 14px;
  transition: border-color 0.2s, transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  border-color: var(--border-hover);
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-icon.filtered {
  background: rgba(102, 126, 234, 0.12);
  color: #667eea;
}

.stat-icon.page {
  background: rgba(79, 172, 254, 0.12);
  color: #4facfe;
}

.stat-icon.pending {
  background: rgba(255, 210, 0, 0.12);
  color: #ffd200;
}

.stat-icon.sendable {
  background: rgba(56, 239, 125, 0.12);
  color: #38ef7d;
}

.stat-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.15;
}

.stat-label {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.35;
}

.form-panel {
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  overflow: hidden;
  min-width: 0;
  box-shadow: var(--shadow-sm);
}

.panel-accent {
  height: 3px;
  width: 100%;
  flex-shrink: 0;
  background: var(--gradient-primary);
}

.panel-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--border-default);
}

.panel-header-text {
  flex: 1;
  min-width: min(100%, 240px);
}

.panel-title {
  font-size: clamp(1.05rem, 2.5vw, 1.125rem);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.panel-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0;
  line-height: 1.55;
  max-width: 52rem;
}

.panel-header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.header-btn-primary {
  height: 40px;
  padding: 0 20px;
  font-weight: 500;
}

.header-btn-ghost {
  height: 40px;
}

.panel-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.filter-section {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.filter-status {
  width: 148px;
  min-width: 120px;
}

.filter-search {
  flex: 1 1 200px;
  max-width: min(100%, 440px);
  min-width: 160px;
}

.toolbar-hint {
  font-size: 12px;
  color: var(--text-quaternary);
  flex-shrink: 0;
}

.table-scroll {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.data-table {
  --el-table-header-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
}

.data-table :deep(.el-table__header th) {
  background: var(--bg-secondary) !important;
  font-weight: 600;
  font-size: 13px;
  color: var(--text-secondary);
  padding: 14px 0;
}

.data-table :deep(.el-table__body td) {
  padding: 12px 0;
}

.data-table :deep(.el-table__inner-wrapper::before) {
  display: none;
}

.approvals-table :deep(.cell) {
  line-height: 1.45;
}

.pager {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  padding: 14px 24px 18px;
  border-top: 1px solid var(--border-default);
  background: var(--bg-card);
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}

.cell-approval-no {
  display: inline-block;
  max-width: 100%;
  white-space: nowrap;
}

.cell-phone {
  font-size: 13px;
}

.time-text {
  font-size: 13px;
  color: var(--text-tertiary);
}

.cell-action-placeholder {
  color: var(--text-quaternary);
  font-size: 13px;
}

.action-cell {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.dialog-submit-tip {
  margin: 0 0 14px 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-tertiary);
}

@media (max-width: 1200px) {
  .stats-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-cards {
    grid-template-columns: 1fr;
  }

  .panel-header {
    flex-direction: column;
    align-items: stretch;
  }

  .panel-header-actions .el-button {
    flex: 1;
  }

  .panel-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar-hint {
    order: -1;
  }

  .filter-section {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-status,
  .filter-search {
    width: 100% !important;
    max-width: none;
  }

  /* 窄屏隐藏次要列，避免操作列被挤出视口 */
  .approvals-table :deep(.col-time) {
    display: none;
  }

  .pager :deep(.el-pagination) {
    justify-content: center;
    width: 100%;
  }

  .pager :deep(.el-pagination__sizes),
  .pager :deep(.el-pagination__jump) {
    display: none;
  }
}

</style>
