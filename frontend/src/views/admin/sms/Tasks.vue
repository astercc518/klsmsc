<template>
  <div class="admin-tasks-page">

    <!-- 统计卡片（与 BatchSend 一致样式） -->
    <div class="stats-cards">
      <div class="stat-card">
        <div class="stat-icon total">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/>
            <path d="M7 6H13M7 10H13M7 14H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ pagination.total }}</span>
          <span class="stat-label">全部任务</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon processing">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5"/>
            <path d="M10 6V10L13 13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ stats.processing }}</span>
          <span class="stat-label">处理中</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon paused">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5"/>
            <rect x="7" y="7" width="2" height="6" rx="1" fill="currentColor"/>
            <rect x="11" y="7" width="2" height="6" rx="1" fill="currentColor"/>
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ stats.paused }}</span>
          <span class="stat-label">已暂停</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon completed">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5"/>
            <path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ stats.completed }}</span>
          <span class="stat-label">已完成</span>
        </div>
      </div>
    </div>

    <!-- 任务面板 -->
    <div class="task-panel">
      <div class="panel-header">
        <div class="panel-header-text">
          <h3 class="panel-title">全局短信任务</h3>
          <p class="panel-desc">全局批次任务监控与运维：暂停 / 切换通道 / 清空队列 / 失败退款</p>
        </div>
        <div class="panel-actions">
          <!-- 筛选区 -->
          <el-input v-model="filters.keyword" placeholder="批次名/关键词" clearable style="width: 160px" @change="loadList" />
          <el-select v-model="filters.status" placeholder="状态" clearable style="width: 120px" @change="loadList">
            <el-option label="待处理" value="pending" />
            <el-option label="处理中" value="processing" />
            <el-option label="已暂停" value="paused" />
            <el-option label="已完成" value="completed" />
            <el-option label="失败" value="failed" />
            <el-option label="已取消" value="cancelled" />
          </el-select>
          <el-input v-model.number="filters.account_id" placeholder="账户ID" clearable style="width: 100px" @change="loadList" />
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            value-format="YYYY-MM-DD"
            style="width: 240px"
            @change="onDateChange"
          />
          <el-button :icon="Refresh" @click="loadList">刷新</el-button>
        </div>
      </div>

      <div class="table-scroll-wrapper">
        <el-table v-loading="loading" :data="items" stripe class="task-table-inner" :table-layout="'auto'">

          <el-table-column prop="id" label="批次ID" width="72" />

          <el-table-column label="账户" width="150">
            <template #default="{ row }">
              <div class="acct-cell">
                <span class="acct-name">{{ row.account_name || `账户` }}</span>
                <span class="acct-id">#{{ row.account_id }}</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column prop="batch_name" label="批次名" min-width="160" show-overflow-tooltip />

          <el-table-column prop="total_count" label="总数" width="80" align="right" />

          <el-table-column width="90" align="right">
            <template #header>
              <el-tooltip content="通道已受理条数（sent / delivered）" placement="top" :show-after="400">
                <span class="col-hint">成功</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="count-success">{{ row.success_count }}</span>
            </template>
          </el-table-column>

          <el-table-column width="90" align="right">
            <template #header>
              <el-tooltip content="已收到终态送达回执" placement="top" :show-after="400">
                <span class="col-hint">送达</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="count-delivered">{{ row.delivered_count }}</span>
            </template>
          </el-table-column>

          <el-table-column width="96" align="right">
            <template #header>
              <el-tooltip content="已发出、等待终态回执" placement="top" :show-after="400">
                <span class="col-hint">等待回执</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span :class="sentAwaiting(row) > 0 ? 'count-awaiting' : ''">{{ sentAwaiting(row) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="失败" width="72" align="right">
            <template #default="{ row }">
              <span v-if="row.failed_count > 0" class="count-fail">{{ row.failed_count }}</span>
              <span v-else>0</span>
            </template>
          </el-table-column>

          <el-table-column label="进度" width="140">
            <template #default="{ row }">
              <el-progress :percentage="row.progress || 0" :status="progressStatus(row)" :stroke-width="5" />
            </template>
          </el-table-column>

          <el-table-column width="84" align="right">
            <template #header>
              <el-tooltip content="终态送达率 = 送达 / 总数" placement="top" :show-after="400">
                <span class="col-hint">送达率</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span v-if="row.total_count > 0" :class="deliveryRateClass(row)">{{ deliveryRate(row) }}</span>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>

          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>

          <el-table-column label="创建时间" width="148">
            <template #default="{ row }">
              <span class="time-text">{{ fmtTime(row.created_at) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="完成时间" width="148">
            <template #default="{ row }">
              <span v-if="row.completed_at" class="time-text">{{ fmtTime(row.completed_at) }}</span>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <div class="task-actions">
                <el-button v-if="row.status === 'processing' || row.status === 'pending'" link type="warning" size="small" @click="onPause(row)">暂停</el-button>
                <el-button v-if="row.status === 'paused'" link type="primary" size="small" @click="onResume(row)">继续</el-button>
                <el-button v-if="row.status === 'paused'" link type="primary" size="small" @click="openSwitch(row)">切换通道</el-button>
                <el-button v-if="row.status === 'paused'" link type="danger" size="small" @click="onClearQueue(row)">清空队列</el-button>
                <el-button v-if="['completed','failed'].includes(row.status)" link type="success" size="small" @click="goRefund(row)">系统退款</el-button>
                <el-button link size="small" @click="openDetail(row)">详情</el-button>
              </div>
            </template>
          </el-table-column>

        </el-table>
      </div>

      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :page-sizes="[20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          background
          size="small"
          @current-change="loadList"
          @size-change="loadList"
        />
      </div>
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" title="批次详情" size="640px">
      <div v-if="detail" class="detail-panel">
        <h3>{{ detail.batch_name }}</h3>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="批次ID">{{ detail.id }}</el-descriptions-item>
          <el-descriptions-item label="状态"><el-tag :type="statusType(detail.status)" size="small">{{ statusLabel(detail.status) }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="账户">{{ detail.account_name || `#${detail.account_id}` }}</el-descriptions-item>
          <el-descriptions-item label="进度">{{ detail.progress }}%</el-descriptions-item>
          <el-descriptions-item label="总数">{{ detail.total_count }}</el-descriptions-item>
          <el-descriptions-item label="成功">{{ detail.success_count }}</el-descriptions-item>
          <el-descriptions-item label="送达">{{ detail.delivered_count }}</el-descriptions-item>
          <el-descriptions-item label="失败">{{ detail.failed_count }}</el-descriptions-item>
          <el-descriptions-item label="处理中">{{ detail.processing_count }}</el-descriptions-item>
          <el-descriptions-item label="可退款">{{ detail.refundable_count || 0 }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ fmtTime(detail.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ fmtTime(detail.completed_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="detail.error_message" label="错误" :span="2">
            <span class="err-text">{{ detail.error_message }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="detail.current_channel" label="当前通道" :span="2">
            <span>
              {{ detail.current_channel.channel_code }} ({{ detail.current_channel.protocol }})
              <el-tag size="small" :type="detail.current_channel.connection_status === 'online' ? 'success' : 'info'" style="margin-left: 8px">
                {{ detail.current_channel.connection_status || '-' }}
              </el-tag>
            </span>
          </el-descriptions-item>
        </el-descriptions>

        <h4 style="margin-top: 20px">状态分布</h4>
        <div class="status-counts">
          <span v-for="(cnt, st) in detail.status_counts" :key="st" class="status-pill">
            {{ st }}: <b>{{ cnt }}</b>
          </span>
        </div>
      </div>
    </el-drawer>

    <!-- 切换通道对话框 -->
    <el-dialog v-model="switchVisible" title="切换通道继续发送" width="600px" :close-on-click-modal="false">
      <div v-if="switchTarget">
        <p class="dialog-hint">批次 #{{ switchTarget.id }} · {{ switchTarget.batch_name }}</p>

        <el-form label-width="100px">
          <el-form-item label="新通道">
            <el-select v-model="switchForm.new_channel_id" placeholder="选择新通道" style="width: 100%" @change="onPreviewSwitch">
              <el-option v-for="ch in channels" :key="ch.id" :label="`${ch.channel_code} (${ch.protocol})`" :value="ch.id" />
            </el-select>
          </el-form-item>
        </el-form>

        <div v-if="switchPreview" class="preview-box">
          <div v-if="!switchPreview.success" class="preview-error">
            <el-icon><WarningFilled /></el-icon>
            {{ switchPreview.reason }}
          </div>
          <template v-else>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="未发条数">{{ switchPreview.unsent_count }}</el-descriptions-item>
              <el-descriptions-item label="新通道">{{ switchPreview.new_channel_code }}</el-descriptions-item>
              <el-descriptions-item label="价差">
                <span :class="diffClass(switchPreview.total_diff)">{{ fmtMoney(switchPreview.total_diff) }}</span>
                <span class="text-muted" style="margin-left: 6px">
                  {{ (switchPreview.total_diff || 0) > 0 ? '需要扣款' : (switchPreview.total_diff || 0) < 0 ? '退回余额' : '无变化' }}
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="账户当前余额">{{ fmtMoney(switchPreview.balance_before) }}</el-descriptions-item>
              <el-descriptions-item label="预计调整后余额">
                <span :class="(switchPreview.balance_sufficient ?? true) ? '' : 'err-text'">{{ fmtMoney(switchPreview.balance_after_estimate) }}</span>
              </el-descriptions-item>
            </el-descriptions>
            <el-alert v-if="!switchPreview.balance_sufficient" type="error" :closable="false" style="margin-top: 12px">
              账户余额不足，无法切换通道
            </el-alert>
          </template>
        </div>

        <el-form label-width="100px" style="margin-top: 16px">
          <el-form-item label="确认输入">
            <el-input v-model="switchConfirmText" placeholder='请输入"确认"以继续' />
          </el-form-item>
        </el-form>
      </div>

      <template #footer>
        <el-button @click="switchVisible = false">取消</el-button>
        <el-button type="primary" :loading="switchSubmitting" :disabled="!canSubmitSwitch" @click="submitSwitch">
          确认切换并继续
        </el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, WarningFilled } from '@element-plus/icons-vue'
import {
  listAdminBatches, getAdminBatch, pauseBatch, resumeBatch,
  clearBatchQueue, previewSwitchChannel,
  type AdminBatchItem, type AdminBatchDetail, type PreviewSwitchResult,
} from '@/api/admin-batches'
import { getChannelsAdmin } from '@/api/admin'

const router = useRouter()
const loading = ref(false)
const items = ref<AdminBatchItem[]>([])
const pagination = reactive({ total: 0, page: 1, page_size: 20 })
const filters = reactive<{ keyword?: string; status?: string; account_id?: number; start_date?: string; end_date?: string }>({})
const dateRange = ref<[string, string] | null>(null)

const stats = reactive({ processing: 0, paused: 0, completed: 0 })

const detailVisible = ref(false)
const detail = ref<AdminBatchDetail | null>(null)

const switchVisible = ref(false)
const switchTarget = ref<AdminBatchItem | null>(null)
const switchForm = reactive<{ new_channel_id?: number }>({})
const switchPreview = ref<PreviewSwitchResult | null>(null)
const switchConfirmText = ref('')
const switchSubmitting = ref(false)

const channels = ref<any[]>([])

const canSubmitSwitch = computed(() =>
  !!switchForm.new_channel_id &&
  switchPreview.value?.success === true &&
  (switchPreview.value?.balance_sufficient ?? true) &&
  switchConfirmText.value.trim() === '确认'
)

function onDateChange(v: any) {
  if (Array.isArray(v) && v.length === 2) {
    filters.start_date = v[0]
    filters.end_date = v[1]
  } else {
    filters.start_date = undefined
    filters.end_date = undefined
  }
  loadList()
}

async function loadList() {
  loading.value = true
  try {
    const res = await listAdminBatches({ ...filters, page: pagination.page, page_size: pagination.page_size })
    if (res.success) {
      items.value = res.items
      pagination.total = res.total
      computeStats(res.items)
    }
  } finally {
    loading.value = false
  }
}

function computeStats(rows: AdminBatchItem[]) {
  stats.processing = rows.filter(r => r.status === 'processing').length
  stats.paused = rows.filter(r => r.status === 'paused').length
  stats.completed = rows.filter(r => r.status === 'completed').length
}

async function openDetail(row: AdminBatchItem) {
  detailVisible.value = true
  detail.value = null
  const res = await getAdminBatch(row.id)
  if (res.success) detail.value = res.batch
  else ElMessage.error(res.error || '加载失败')
}

async function onPause(row: AdminBatchItem) {
  try {
    await ElMessageBox.confirm(
      `确认暂停批次 #${row.id} 「${row.batch_name}」？\n暂停后未发条目不会被消费，可恢复或清空队列。\n注意：已下发到 SMPP 上游网关的消息无法回收。`,
      '暂停任务', { type: 'warning', confirmButtonText: '确认暂停', cancelButtonText: '取消' }
    )
  } catch { return }
  const res = await pauseBatch(row.id)
  if (res.success) {
    ElMessage.success(`已暂停，未发条数 ${res.unsent_count ?? 0}`)
    if (res.warning) ElMessage.warning(res.warning)
    loadList()
  } else {
    ElMessage.error(res.reason || '暂停失败')
  }
}

async function onResume(row: AdminBatchItem) {
  try {
    await ElMessageBox.confirm(`确认恢复批次 #${row.id}？将重新入队所有未发消息。`, '恢复发送', {
      type: 'info', confirmButtonText: '确认恢复', cancelButtonText: '取消'
    })
  } catch { return }
  const res = await resumeBatch(row.id)
  if (res.success) {
    ElMessage.success(`已恢复，重新入队 ${res.requeued_ok ?? 0} 条`)
    loadList()
  } else {
    ElMessage.error(res.reason || '恢复失败')
  }
}

async function onClearQueue(row: AdminBatchItem) {
  try {
    await ElMessageBox.confirm(
      `确认清空批次 #${row.id} 的未发队列？所有未发条目将标记为 cancelled，无法恢复。`,
      '清空队列', { type: 'error', confirmButtonText: '确认清空', cancelButtonText: '取消' }
    )
  } catch { return }
  const res = await clearBatchQueue(row.id)
  if (res.success) {
    ElMessage.success(`已清空，取消条数 ${res.cancelled_logs ?? 0}`)
    loadList()
  } else {
    ElMessage.error(res.reason || '清空失败')
  }
}

async function openSwitch(row: AdminBatchItem) {
  switchTarget.value = row
  switchForm.new_channel_id = undefined
  switchPreview.value = null
  switchConfirmText.value = ''
  if (channels.value.length === 0) {
    try {
      const res = await getChannelsAdmin()
      channels.value = (res.channels || res.data || []).filter((c: any) => c.status === 'active' && !c.is_deleted)
    } catch { /* ignore */ }
  }
  switchVisible.value = true
}

async function onPreviewSwitch() {
  if (!switchTarget.value || !switchForm.new_channel_id) return
  switchPreview.value = null
  switchPreview.value = await previewSwitchChannel(switchTarget.value.id, switchForm.new_channel_id)
}

async function submitSwitch() {
  if (!switchTarget.value || !switchForm.new_channel_id) return
  switchSubmitting.value = true
  try {
    const res = await resumeBatch(switchTarget.value.id, { new_channel_id: switchForm.new_channel_id })
    if (res.success) {
      ElMessage.success(`已切换通道并恢复发送，重新入队 ${res.requeued_ok ?? 0} 条`)
      switchVisible.value = false
      loadList()
    } else {
      ElMessage.error(res.reason || '切换失败')
    }
  } finally {
    switchSubmitting.value = false
  }
}

function goRefund(row: AdminBatchItem) {
  router.push({ path: '/admin/sms/refund-audit', query: { batch_id: String(row.id) } })
}

// 等待回执 = success_count - delivered_count
function sentAwaiting(row: AdminBatchItem): number {
  return Math.max(0, (row.success_count || 0) - (row.delivered_count || 0))
}

// 送达率
function deliveryRate(row: AdminBatchItem): string {
  if (!row.total_count) return '-'
  return `${((row.delivered_count / row.total_count) * 100).toFixed(1)}%`
}

function deliveryRateClass(row: AdminBatchItem): string {
  if (!row.total_count) return 'text-muted'
  const rate = (row.delivered_count / row.total_count) * 100
  if (rate >= 90) return 'rate-high'
  if (rate >= 60) return 'rate-mid'
  return 'rate-low'
}

function statusLabel(s: string) {
  return ({ pending: '待处理', processing: '处理中', paused: '已暂停', completed: '已完成', failed: '失败', cancelled: '已取消' } as Record<string, string>)[s] || s
}

function statusType(s: string): any {
  return ({ pending: 'info', processing: 'primary', paused: 'warning', completed: 'success', failed: 'danger', cancelled: 'info' } as Record<string, string>)[s] || ''
}

function progressStatus(row: AdminBatchItem): any {
  if (row.status === 'failed' || row.status === 'cancelled') return 'exception'
  if (row.status === 'completed') return 'success'
  if (row.status === 'paused') return 'warning'
  return undefined
}

function fmtTime(t?: string | null) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}

function fmtMoney(v: any) {
  if (v == null || v === '') return '-'
  return Number(v).toFixed(4)
}

function diffClass(v: any) {
  const n = Number(v)
  if (n > 0) return 'err-text'
  if (n < 0) return 'ok-text'
  return ''
}

onMounted(() => { loadList() })
</script>

<style scoped>
.admin-tasks-page { width: 100%; }

/* 统计卡片 */
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
  transition: all 0.2s;
}

.stat-card:hover {
  border-color: var(--border-hover);
  transform: translateY(-2px);
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

.stat-icon.total    { background: rgba(102, 126, 234, 0.12); color: #667EEA; }
.stat-icon.processing { background: rgba(64, 158, 255, 0.12); color: #409EFF; }
.stat-icon.paused   { background: rgba(230, 162, 60, 0.12); color: #E6A23C; }
.stat-icon.completed { background: rgba(56, 239, 125, 0.12); color: #38EF7D; }

.stat-info { display: flex; flex-direction: column; gap: 2px; }
.stat-value { font-size: 22px; font-weight: 700; color: var(--text-primary); }
.stat-label { font-size: 12px; color: var(--text-tertiary); }

/* 任务面板 */
.task-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 14px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.panel-header-text { flex: 1; min-width: 0; }

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.panel-desc {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.panel-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

/* 表格 */
.table-scroll-wrapper { overflow-x: auto; }

.task-table-inner :deep(.el-table__header th .cell),
.task-table-inner :deep(.el-table__body td .cell) {
  white-space: nowrap;
  word-break: keep-all;
  padding-left: 10px;
  padding-right: 10px;
}

.task-table-inner :deep(.el-table__fixed-right .cell) {
  white-space: normal !important;
  word-break: normal;
}

.task-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  line-height: 1.5;
}

/* 账户列 */
.acct-cell { display: flex; flex-direction: column; line-height: 1.4; }
.acct-name { font-size: 13px; }
.acct-id { font-size: 11px; color: var(--el-text-color-secondary); }

/* 数字着色 */
.count-success  { color: #409eff; font-weight: 600; }
.count-delivered { color: #67c23a; font-weight: 600; }
.count-awaiting  { color: #e6a23c; font-weight: 600; }
.count-fail      { color: #f56c6c; font-weight: 600; }

/* 送达率 */
.rate-high { color: #38EF7D; font-weight: 600; }
.rate-mid  { color: #E6A23C; font-weight: 600; }
.rate-low  { color: #F5576C; font-weight: 600; }

/* 表头悬停提示 */
.col-hint {
  cursor: help;
  border-bottom: 1px dashed var(--el-text-color-secondary);
}

.time-text { font-size: 13px; color: var(--text-tertiary); }
.text-muted { color: var(--el-text-color-secondary); }

/* 分页 */
.pagination {
  padding: 16px 20px;
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid var(--border-default);
}

/* 详情抽屉 */
.detail-panel { padding: 0 12px; }
.status-counts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.status-pill { background: var(--el-fill-color-light); padding: 4px 10px; border-radius: 999px; font-size: 12px; }
.err-text { color: var(--el-color-danger); }
.ok-text  { color: var(--el-color-success); }

/* 切换通道对话框 */
.dialog-hint { color: var(--el-text-color-secondary); margin: 0 0 12px 0; font-size: 13px; }
.preview-box { margin-top: 12px; }
.preview-error { color: var(--el-color-danger); display: flex; gap: 6px; align-items: center; }
</style>
