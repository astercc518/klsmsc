<template>
  <div class="admin-tasks-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">短信任务管理</h1>
        <p class="page-desc">全局批次任务监控与运维：暂停 / 切换通道 / 清空队列 / 失败退款</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" @click="loadList">刷新</el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-chip processing">
        <span class="stat-chip-label">处理中</span>
        <span class="stat-chip-value">{{ stats.processing }}</span>
      </div>
      <div class="stat-chip paused">
        <span class="stat-chip-label">已暂停</span>
        <span class="stat-chip-value">{{ stats.paused }}</span>
      </div>
      <div class="stat-chip completed">
        <span class="stat-chip-label">已完成</span>
        <span class="stat-chip-value">{{ stats.completed }}</span>
      </div>
      <div class="stat-chip total">
        <span class="stat-chip-label">总记录</span>
        <span class="stat-chip-value">{{ pagination.total }}</span>
      </div>
    </div>

    <!-- 筛选区 -->
    <div class="filter-bar">
      <el-input v-model="filters.keyword" placeholder="批次名/关键词" clearable style="width: 200px" @change="loadList" />
      <el-select v-model="filters.status" placeholder="状态" clearable style="width: 150px" @change="loadList">
        <el-option label="待处理" value="pending" />
        <el-option label="处理中" value="processing" />
        <el-option label="已暂停" value="paused" />
        <el-option label="已完成" value="completed" />
        <el-option label="失败" value="failed" />
        <el-option label="已取消" value="cancelled" />
      </el-select>
      <el-input v-model.number="filters.account_id" placeholder="账户ID" clearable style="width: 130px" @change="loadList" />
      <el-input v-model.number="filters.channel_id" placeholder="通道ID" clearable style="width: 130px" @change="loadList" />
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        style="width: 260px"
        @change="onDateChange"
      />
    </div>

    <!-- 列表 -->
    <el-table v-loading="loading" :data="items" stripe class="task-table">
      <el-table-column prop="id" label="批次ID" width="90" />
      <el-table-column label="账户" width="180">
        <template #default="{ row }">
          <div class="acct-cell">
            <span>{{ row.account_name || `acc#${row.account_id}` }}</span>
            <span class="acct-id">#{{ row.account_id }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="batch_name" label="批次名" min-width="220" show-overflow-tooltip />
      <el-table-column label="进度" width="220">
        <template #default="{ row }">
          <div class="progress-cell">
            <el-progress :percentage="row.progress || 0" :status="progressStatus(row)" :stroke-width="6" />
            <div class="progress-detail">
              {{ row.success_count }}/{{ row.total_count }}
              <span class="muted"> · 送达 {{ row.delivered_count }} · 失败 {{ row.failed_count }}</span>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">
          {{ fmtTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="320" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.status === 'processing' || row.status === 'pending'" link type="warning" @click="onPause(row)">暂停</el-button>
          <el-button v-if="row.status === 'paused'" link type="primary" @click="onResume(row)">继续</el-button>
          <el-button v-if="row.status === 'paused'" link type="primary" @click="openSwitch(row)">切换通道继续</el-button>
          <el-button v-if="row.status === 'paused'" link type="danger" @click="onClearQueue(row)">清空队列</el-button>
          <el-button v-if="['completed','failed'].includes(row.status)" link type="success" @click="goRefund(row)">失败退款</el-button>
          <el-button link @click="openDetail(row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-bar">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :page-sizes="[20, 50, 100]"
        :total="pagination.total"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="loadList"
        @size-change="loadList"
      />
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" title="批次详情" size="640px">
      <div v-if="detail" class="detail-panel">
        <h3>{{ detail.batch_name }}</h3>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="批次ID">{{ detail.id }}</el-descriptions-item>
          <el-descriptions-item label="状态"><el-tag :type="statusType(detail.status)">{{ statusLabel(detail.status) }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="账户">{{ detail.account_name || `#${detail.account_id}` }}</el-descriptions-item>
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
                <span :class="diffClass(switchPreview.total_diff)">
                  {{ formatMoney(switchPreview.total_diff) }}
                </span>
                <span class="muted" style="margin-left: 6px">
                  {{ (switchPreview.total_diff || 0) > 0 ? '需要扣款' : (switchPreview.total_diff || 0) < 0 ? '退回余额' : '无变化' }}
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="账户当前余额">{{ formatMoney(switchPreview.balance_before) }}</el-descriptions-item>
              <el-descriptions-item label="预计调整后余额">
                <span :class="(switchPreview.balance_sufficient ?? true) ? '' : 'err-text'">
                  {{ formatMoney(switchPreview.balance_after_estimate) }}
                </span>
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
        <el-button
          type="primary"
          :loading="switchSubmitting"
          :disabled="!canSubmitSwitch"
          @click="submitSwitch"
        >确认切换并继续</el-button>
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
const filters = reactive<{ keyword?: string; status?: string; account_id?: number; channel_id?: number; start_date?: string; end_date?: string }>({})
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

const canSubmitSwitch = computed(() => {
  return (
    !!switchForm.new_channel_id &&
    switchPreview.value?.success === true &&
    (switchPreview.value?.balance_sufficient ?? true) &&
    switchConfirmText.value.trim() === '确认'
  )
})

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
    const { data } = await listAdminBatches({
      ...filters,
      page: pagination.page,
      page_size: pagination.page_size,
    })
    if (data.success) {
      items.value = data.items
      pagination.total = data.total
      // 简单聚合：从当前页统计（仅作大致显示，不查后端单独的 stats）
      computeStats(data.items)
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
  const { data } = await getAdminBatch(row.id)
  if (data.success) detail.value = data.batch
  else ElMessage.error(data.error || '加载失败')
}

async function onPause(row: AdminBatchItem) {
  try {
    await ElMessageBox.confirm(
      `确认暂停批次 #${row.id} 「${row.batch_name}」？\n暂停后未发条目不会被消费，可恢复或清空队列。\n注意：已下发到 SMPP 上游网关的消息无法回收。`,
      '暂停任务', { type: 'warning', confirmButtonText: '确认暂停', cancelButtonText: '取消' }
    )
  } catch { return }
  const { data } = await pauseBatch(row.id)
  if (data.success) {
    ElMessage.success(`已暂停，未发条数 ${data.unsent_count ?? 0}`)
    if (data.warning) ElMessage.warning(data.warning)
    loadList()
  } else {
    ElMessage.error(data.reason || '暂停失败')
  }
}

async function onResume(row: AdminBatchItem) {
  try {
    await ElMessageBox.confirm(`确认恢复批次 #${row.id}？将重新入队所有未发消息。`, '恢复发送', {
      type: 'info', confirmButtonText: '确认恢复', cancelButtonText: '取消'
    })
  } catch { return }
  const { data } = await resumeBatch(row.id)
  if (data.success) {
    ElMessage.success(`已恢复，重新入队 ${data.requeued_ok ?? 0} 条`)
    loadList()
  } else {
    ElMessage.error(data.reason || '恢复失败')
  }
}

async function onClearQueue(row: AdminBatchItem) {
  try {
    await ElMessageBox.confirm(
      `确认清空批次 #${row.id} 的未发队列？所有未发条目将标记为 cancelled，无法恢复。`,
      '清空队列', { type: 'error', confirmButtonText: '确认清空', cancelButtonText: '取消' }
    )
  } catch { return }
  const { data } = await clearBatchQueue(row.id)
  if (data.success) {
    ElMessage.success(`已清空，取消条数 ${data.cancelled_logs ?? 0}`)
    loadList()
  } else {
    ElMessage.error(data.reason || '清空失败')
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
      channels.value = (res.data?.channels || res.data?.data || []).filter((c: any) => c.status === 'active' && !c.is_deleted)
    } catch (e) { /* ignore */ }
  }
  switchVisible.value = true
}

async function onPreviewSwitch() {
  if (!switchTarget.value || !switchForm.new_channel_id) return
  switchPreview.value = null
  const { data } = await previewSwitchChannel(switchTarget.value.id, switchForm.new_channel_id)
  switchPreview.value = data
}

async function submitSwitch() {
  if (!switchTarget.value || !switchForm.new_channel_id) return
  switchSubmitting.value = true
  try {
    const { data } = await resumeBatch(switchTarget.value.id, { new_channel_id: switchForm.new_channel_id })
    if (data.success) {
      ElMessage.success(`已切换通道并恢复发送，重新入队 ${data.requeued_ok ?? 0} 条`)
      switchVisible.value = false
      loadList()
    } else {
      ElMessage.error(data.reason || '切换失败')
    }
  } finally {
    switchSubmitting.value = false
  }
}

function goRefund(row: AdminBatchItem) {
  router.push({ path: '/admin/sms/refund-audit', query: { batch_id: String(row.id) } })
}

// 格式化辅助
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
  return ''
}
function fmtTime(t?: string | null) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}
function formatMoney(v: any) {
  if (v == null || v === '') return '-'
  return Number(v).toFixed(4)
}
function diffClass(v: any) {
  if (v == null) return ''
  const n = Number(v)
  if (n > 0) return 'err-text'
  if (n < 0) return 'ok-text'
  return ''
}

onMounted(() => {
  loadList()
})
</script>

<style scoped>
.admin-tasks-page { padding: 16px 24px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.page-title { font-size: 22px; margin: 0 0 4px 0; }
.page-desc { color: var(--el-text-color-secondary); margin: 0; }

.stats-row { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.stat-chip { background: var(--el-fill-color-light); padding: 12px 18px; border-radius: 8px; min-width: 140px; }
.stat-chip-label { display: block; font-size: 12px; color: var(--el-text-color-secondary); }
.stat-chip-value { display: block; font-size: 22px; font-weight: 600; margin-top: 2px; }
.stat-chip.processing { border-left: 3px solid var(--el-color-primary); }
.stat-chip.paused { border-left: 3px solid var(--el-color-warning); }
.stat-chip.completed { border-left: 3px solid var(--el-color-success); }
.stat-chip.total { border-left: 3px solid var(--el-color-info); }

.filter-bar { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; align-items: center; }

.task-table { margin-bottom: 12px; }
.acct-cell { display: flex; flex-direction: column; }
.acct-id { font-size: 11px; color: var(--el-text-color-secondary); }
.progress-cell { display: flex; flex-direction: column; gap: 4px; }
.progress-detail { font-size: 12px; color: var(--el-text-color-regular); }
.muted { color: var(--el-text-color-secondary); }

.pagination-bar { display: flex; justify-content: flex-end; }

.detail-panel { padding: 0 12px; }
.status-counts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.status-pill { background: var(--el-fill-color-light); padding: 4px 10px; border-radius: 999px; font-size: 12px; }
.err-text { color: var(--el-color-danger); }
.ok-text { color: var(--el-color-success); }

.dialog-hint { color: var(--el-text-color-secondary); margin: 0 0 12px 0; }
.preview-box { margin-top: 12px; }
.preview-error { color: var(--el-color-danger); display: flex; gap: 6px; align-items: center; }
</style>
