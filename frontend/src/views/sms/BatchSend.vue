<template>
  <div class="batch-send-page">
    <!-- 统计卡片 -->
    <div class="stats-cards">
      <div class="stat-card">
        <div class="stat-icon total">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/>
            <path d="M7 6H13M7 10H13M7 14H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ stats.total_batches }}</span>
          <span class="stat-label">{{ $t('batchSend.totalTasks') }}</span>
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
          <span class="stat-value">{{ stats.processing_batches }}</span>
          <span class="stat-label">{{ $t('batchSend.processing') }}</span>
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
          <span class="stat-value">{{ stats.completed_batches }}</span>
          <span class="stat-label">{{ $t('batchSend.completed') }}</span>
        </div>
      </div>
      <div class="stat-card action">
        <el-button type="primary" size="large" @click="showUploadDialog" class="create-btn">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M9 3V15M3 9H15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          {{ $t('batchSend.createTask') }}
        </el-button>
      </div>
    </div>

    <p class="stats-strip">{{ $t('batchSend.pendingAndFailedStrip', { pending: stats.pending_batches, failed: stats.failed_batches }) }}</p>

    <!-- 任务列表 -->
    <div class="task-panel">
      <div class="panel-header">
        <div class="panel-header-text">
          <h3 class="panel-title">{{ $t('batchSend.taskList') }}</h3>
          <p class="panel-desc">{{ $t('batchSend.taskSourceHint') }}</p>
        </div>
        <el-tooltip :content="$t('batchSend.listPollHint')" placement="top">
          <el-button :icon="Refresh" size="small" @click="onManualRefresh">{{ $t('common.refresh') }}</el-button>
        </el-tooltip>
      </div>

      <el-alert type="info" :closable="false" show-icon class="batch-metric-hint">
        {{ $t('batchSend.listMetricClarify') }}
      </el-alert>

      <el-empty v-if="!loading && batches.length === 0" :description="$t('batchSend.emptyList')" class="task-empty" />
      <div v-else class="table-scroll-wrapper">
      <el-table :data="batches" v-loading="loading" stripe class="task-table-inner" :table-layout="'auto'">
        <el-table-column prop="id" :label="$t('batchSend.batchIdCol')" width="72" />
        <el-table-column prop="batch_name" :label="$t('batchSend.batchName')" min-width="160" show-overflow-tooltip />
        <el-table-column prop="channel_code" :label="$t('smsSend.channel')" width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag v-if="row.channel_code" size="small" effect="plain" type="info">{{ row.channel_code }}</el-tag>
            <span v-else style="color:var(--text-quaternary)">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="total_count" :label="$t('batchSend.totalCount')" width="96" align="right" />
        <el-table-column prop="success_count" width="116">
          <template #header>
            <el-tooltip :content="$t('batchSend.channelAcceptedTooltip')" placement="top" :show-after="400">
              <span class="batch-col-header">{{ $t('batchSend.successCount') }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span style="color: #409eff; font-weight: bold">{{ row.success_count }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="delivered_count" width="128" align="center">
          <template #header>
            <el-tooltip :content="$t('batchSend.deliveredReceiptTooltip')" placement="top" :show-after="400">
              <span class="batch-col-header">{{ $t('batchSend.deliveredReceiptCount') }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span style="color: #67c23a; font-weight: bold">{{ batchDeliveredCount(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sent_awaiting_receipt_count" width="116" align="center">
          <template #header>
            <el-tooltip :content="$t('batchSend.awaitingReceiptTooltip')" placement="top" :show-after="400">
              <span class="batch-col-header">{{ $t('batchSend.awaitingReceiptCount') }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="batchSentAwaitingCount(row) > 0 ? 'awaiting-receipt' : ''">{{ batchSentAwaitingCount(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="failed_count" :label="$t('batchSend.failedCount')" width="88">
          <template #default="{ row }">
            <span v-if="row.failed_count > 0" style="color: #f56c6c; font-weight: bold">{{ row.failed_count }}</span>
            <span v-else>0</span>
          </template>
        </el-table-column>
        <el-table-column prop="progress" :label="$t('batchSend.progress')" width="150">
          <template #default="{ row }">
            <el-progress :percentage="row.progress" :status="row.status === 'completed' ? 'success' : undefined" />
          </template>
        </el-table-column>
        <el-table-column width="160" align="center">
          <template #header>
            <el-tooltip :content="$t('batchSend.successRateTooltip')" placement="top" :show-after="400">
              <span class="batch-rate-header">{{ $t('batchSend.successRate') }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span v-if="row.total_count > 0" :class="getDeliveryRateClass(row)">
              {{ batchDeliveryRatePercent(row) }}
            </span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('batchSend.status')" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'pending'" type="info">{{ $t('batchSend.pending') }}</el-tag>
            <el-tooltip v-else-if="row.status === 'processing'" :content="$t('batchSend.processingTooltip')" placement="top" :show-after="200">
              <el-tag type="primary" class="tag-tooltip-wrap">{{ $t('batchSend.processing') }}</el-tag>
            </el-tooltip>
            <el-tag v-else-if="row.status === 'completed'" type="success">{{ $t('batchSend.completed') }}</el-tag>
            <el-tag v-else-if="row.status === 'failed'" type="danger">{{ $t('batchSend.failed') }}</el-tag>
            <el-tag v-else type="warning">{{ $t('batchSend.cancelled') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('batchSend.createdAtLocal')" width="148">
          <template #default="{ row }">
            {{ formatBatchDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('batchSend.completedAt')" width="148">
          <template #default="{ row }">
            <span v-if="row.completed_at" class="time-text">{{ formatBatchDate(row.completed_at) }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="240" fixed="right">
          <template #default="{ row }">
            <div class="task-actions">
              <el-button link type="primary" size="small" @click="viewDetail(row)">{{ $t('common.detail') }}</el-button>
              <el-button
                link
                type="primary"
                size="small"
                :loading="exportingBatchId === row.id"
                @click="exportBatchCsv(row)"
              >
                {{ $t('batchSend.exportCsv') }}
              </el-button>
              <el-button
                v-if="canRetryFailedBatch(row)"
                link
                type="warning"
                size="small"
                @click="retryFailedBatch(row)"
              >
                {{ $t('batchSend.retryFailed') }}
              </el-button>
              <el-button
                v-if="canResendUnsentBatch(row)"
                link
                type="primary"
                size="small"
                @click="resendUnsentBatch(row)"
              >
                {{ $t('batchSend.resendUnsent') }}
              </el-button>
              <el-button
                v-if="canRequeueQueuedBatch(row)"
                link
                type="warning"
                size="small"
                @click="requeueQueuedBatch(row)"
              >
                {{ $t('batchSend.requeueQueued') }}
              </el-button>
              <el-button
                link
                type="success"
                size="small"
                @click="openClickStats(row)"
              >
                短链点击
              </el-button>
              <el-button
                v-if="row.status === 'pending' || row.status === 'processing'"
                link
                type="danger"
                size="small"
                @click="cancelBatch(row)"
              >
                {{ $t('common.cancel') }}
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      </div><!-- /table-scroll-wrapper -->

      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadBatches"
          @size-change="onPageSizeChange"
          background
          size="small"
        />
      </div>
    </div>

    <el-dialog
      v-model="detailVisible"
      :title="$t('batchSend.taskSendRecords')"
      width="920px"
      class="batch-task-records-dialog"
      destroy-on-close
      @closed="onDetailDialogClosed"
    >
      <div v-loading="detailLoading" class="detail-body">
        <el-alert v-if="detailError && !detailLoading" type="error" :closable="false" show-icon class="detail-alert">
          {{ detailError }}
        </el-alert>
        <template v-if="detailBatch">
          <div class="detail-task-summary">
            <span class="summary-line">
              <span class="summary-k">{{ $t('batchSend.batchIdCol') }}</span>
              {{ detailBatch.id }}
            </span>
            <span class="summary-name" :title="detailBatch.batch_name">{{ detailBatch.batch_name }}</span>
            <el-tag size="small" :type="batchStatusTagType(detailBatch.status)">{{ batchStatusLabel(detailBatch.status) }}</el-tag>
            <span class="summary-meta">
              {{ $t('batchSend.totalCount') }} {{ detailBatch.total_count }} · {{ $t('batchSend.successCount') }}
              {{ detailBatch.success_count }} · {{ $t('batchSend.deliveredReceiptCount') }}
              {{ batchDeliveredCount(detailBatch) }} · {{ $t('batchSend.awaitingReceiptCount') }}
              {{ batchSentAwaitingCount(detailBatch) }} · {{ $t('batchSend.failedCount') }} {{ detailBatch.failed_count }} ·
              {{ $t('batchSend.progress') }} {{ detailBatch.progress }}%
            </span>
            <span class="summary-meta">{{ $t('batchSend.createdAtLocal') }} {{ formatBatchDate(detailBatch.created_at) }}</span>
          </div>
          <el-alert
            v-if="detailBatch.error_message"
            type="warning"
            :closable="false"
            show-icon
            class="detail-batch-alert"
          >
            {{ detailBatch.error_message }}
          </el-alert>
          <div class="detail-records-toolbar">
            <el-input
              v-model="detailMessageId"
              clearable
              :placeholder="$t('batchSend.messageIdFilterPlaceholder')"
              class="detail-msgid-input"
              @keyup.enter="searchDetailRecords"
            />
            <el-button type="primary" @click="searchDetailRecords">{{ $t('smsRecords.query') }}</el-button>
          </div>
          <el-table :data="detailRecords" stripe max-height="440" size="small" class="detail-records-table">
            <el-table-column v-if="isAdmin" prop="account_id" :label="$t('smsRecords.accountId')" width="72" align="center" />
            <el-table-column prop="message_id" :label="$t('smsRecords.messageId')" min-width="148" show-overflow-tooltip />
            <el-table-column prop="phone_number" :label="$t('smsRecords.phoneNumber')" width="142" show-overflow-tooltip />
            <el-table-column prop="status" :label="$t('smsRecords.status')" width="108">
              <template #default="{ row }">
                <el-tag size="small" :type="recordStatusTagType(row.status)">{{ recordStatusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="submit_time" :label="$t('smsRecords.submitTime')" width="168">
              <template #default="{ row }">{{ formatBatchDate(row.submit_time) }}</template>
            </el-table-column>
            <el-table-column
              prop="channel_code"
              :label="$t('smsRecords.channel')"
              min-width="120"
              show-overflow-tooltip
            />
          </el-table>
          <div class="detail-records-pagination">
            <el-pagination
              v-model:current-page="detailRecPagination.page"
              v-model:page-size="detailRecPagination.pageSize"
              :total="detailRecPagination.total"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next"
              size="small"
              background
              @current-change="loadDetailRecords"
              @size-change="onDetailPageSizeChange"
            />
          </div>
        </template>
      </div>
    </el-dialog>

    <!-- 上传对话框 -->
    <el-dialog v-model="uploadDialogVisible" :title="$t('batchSend.createTask')" width="600px">
      <el-form :model="uploadForm" ref="uploadFormRef" label-width="120px">
        <el-form-item :label="$t('batchSend.taskName')" required>
          <el-input v-model="uploadForm.batch_name" :placeholder="$t('batchSend.taskNamePlaceholder')" />
        </el-form-item>
        
        <el-form-item :label="$t('batchSend.selectTemplate')">
          <el-select v-model="uploadForm.template_id" :placeholder="$t('batchSend.noTemplate')" clearable style="width: 100%">
            <el-option 
              v-for="tpl in templates" 
              :key="tpl.id" 
              :label="tpl.name" 
              :value="tpl.id" 
            />
          </el-select>
          <div style="color: #909399; font-size: 12px; margin-top: 5px">
            {{ $t('batchSend.templateTip') }}
          </div>
        </el-form-item>
        
        <el-form-item :label="$t('batchSend.senderId')">
          <el-input v-model="uploadForm.sender_id" :placeholder="$t('batchSend.senderIdPlaceholder')" />
        </el-form-item>
        
        <el-form-item :label="$t('batchSend.uploadCsv')" required>
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            accept=".csv"
            :on-change="handleFileChange"
            :file-list="fileList"
          >
            <el-button type="primary">{{ $t('batchSend.selectFile') }}</el-button>
            <template #tip>
              <div style="color: #909399; font-size: 12px; margin-top: 10px">
                <div>• {{ $t('batchSend.csvTip1') }}</div>
                <div>• {{ $t('batchSend.csvTip2') }}</div>
                <div>• {{ $t('batchSend.csvTip3') }}</div>
                <code style="display: block; background: var(--el-fill-color-light); padding: 8px; margin-top: 5px; border-radius: 4px;">
phone,name,code<br>
+8613800138000,John,123456<br>
+8613800138001,Jane,654321
                </code>
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="uploadDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitUpload" :loading="uploading">{{ $t('batchSend.startSend') }}</el-button>
      </template>
    </el-dialog>

    <!-- ========== 短链点击统计对话框 ========== -->
    <el-dialog
      v-model="clickStatsVisible"
      :title="`短链点击 — 批次 #${clickStatsBatch?.id ?? ''}`"
      width="820px"
      destroy-on-close
    >
      <div v-loading="clickStatsLoading">
        <div class="click-stats-summary">
          <div class="cs-card">
            <div class="cs-num">{{ clickStats.total_links }}</div>
            <div class="cs-label">短链总数</div>
          </div>
          <div class="cs-card">
            <div class="cs-num cs-num-primary">{{ clickStats.clicked_links }}</div>
            <div class="cs-label">被点击</div>
          </div>
          <div class="cs-card">
            <div class="cs-num cs-num-success">{{ clickStats.total_clicks }}</div>
            <div class="cs-label">总点击次数</div>
          </div>
          <div class="cs-card">
            <div class="cs-num">{{ clickRatePercent }}</div>
            <div class="cs-label">点击率</div>
          </div>
        </div>

        <div class="click-actions">
          <el-button
            type="primary"
            size="small"
            :disabled="!clickStats.clicked_links"
            @click="downloadClickedCsv"
          >
            下载 CSV（{{ clickStats.clicked_links }} 个号码）
          </el-button>
          <el-button size="small" @click="loadClickedPhones(1)">刷新列表</el-button>
        </div>

        <el-table :data="clickedPhones" stripe size="small" style="margin-top: 12px">
          <el-table-column prop="phone_number" label="手机号码" width="160" />
          <el-table-column prop="click_count" label="点击次数" width="100" align="right" />
          <el-table-column prop="last_click_at" label="最近点击时间" width="190">
            <template #default="{ row }">
              {{ row.last_click_at ? formatBatchDate(row.last_click_at) : '—' }}
            </template>
          </el-table-column>
          <el-table-column prop="original_url" label="跳转链接" show-overflow-tooltip />
          <el-table-column prop="token" label="Token" width="100" />
        </el-table>

        <div class="pagination" v-if="clickedTotal > 0">
          <el-pagination
            v-model:current-page="clickedPage"
            :page-size="clickedPageSize"
            :total="clickedTotal"
            layout="total, prev, pager, next, jumper"
            @current-change="loadClickedPhones"
            background
            size="small"
          />
        </div>

        <el-empty
          v-if="!clickStatsLoading && !clickedPhones.length"
          description="暂无被点击的号码"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, Refresh } from '@element-plus/icons-vue'
import {
  getBatches,
  getBatchStats,
  uploadBatchFile,
  cancelBatch as cancelBatchApi,
  retryBatchFailed as retryBatchFailedApi,
  resendUnsentBatch as resendUnsentBatchApi,
  requeueBatchQueued as requeueBatchQueuedApi,
  exportBatchRecordsCsv,
  type SmsBatch,
} from '@/api/batch'
import { getSMSRecords } from '@/api/sms'
import { getTemplates } from '@/api/template'
import {
  getBatchClickStats,
  listBatchClickedPhones,
  downloadBatchClickedPhonesCsvUrl,
  type ClickStats,
  type ClickedPhoneRow,
} from '@/api/short-link'

const { t } = useI18n()
const router = useRouter()
const loading = ref(false)
const batches = ref<SmsBatch[]>([])
const stats = reactive({
  total_batches: 0,
  pending_batches: 0,
  processing_batches: 0,
  completed_batches: 0,
  failed_batches: 0,
  total_messages: 0,
  success_messages: 0,
  failed_messages: 0
})
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

const detailVisible = ref(false)
const detailLoading = ref(false)
/** 当前查看的任务（用于摘要与 batch_id 查询） */
const detailBatch = ref<SmsBatch | null>(null)
const detailRecords = ref<any[]>([])
const detailRecPagination = reactive({ page: 1, pageSize: 20, total: 0 })
const detailMessageId = ref('')
/** 记录列表加载失败时在弹窗内展示 */
const detailError = ref('')

const isAdmin = computed(() => {
  if (typeof sessionStorage !== 'undefined' && sessionStorage.getItem('impersonate_mode') === '1') return false
  return !!localStorage.getItem('admin_token')
})

const uploadDialogVisible = ref(false)
const uploading = ref(false)
const uploadFormRef = ref()
const uploadRef = ref()
const fileList = ref([])
const uploadForm = reactive({
  batch_name: '',
  template_id: null as number | null,
  sender_id: ''
})

const templates = ref<any[]>([])
/** 正在导出 CSV 的任务 id，用于按钮 loading */
const exportingBatchId = ref<number | null>(null)

// ========== 短链点击统计 ==========
const clickStatsVisible = ref(false)
const clickStatsLoading = ref(false)
const clickStatsBatch = ref<SmsBatch | null>(null)
const clickStats = reactive<ClickStats>({
  batch_id: 0,
  total_links: 0,
  clicked_links: 0,
  total_clicks: 0,
})
const clickedPhones = ref<ClickedPhoneRow[]>([])
const clickedPage = ref(1)
const clickedPageSize = ref(20)
const clickedTotal = ref(0)

const clickRatePercent = computed(() => {
  if (!clickStats.total_links) return '—'
  const r = (clickStats.clicked_links / clickStats.total_links) * 100
  return `${r.toFixed(1)}%`
})

async function openClickStats(row: SmsBatch) {
  clickStatsBatch.value = row
  clickStatsVisible.value = true
  clickStatsLoading.value = true
  Object.assign(clickStats, { batch_id: row.id, total_links: 0, clicked_links: 0, total_clicks: 0 })
  clickedPhones.value = []
  clickedTotal.value = 0
  clickedPage.value = 1
  try {
    const [statsResp, phonesResp]: any = await Promise.all([
      getBatchClickStats(row.id),
      listBatchClickedPhones(row.id, 1, clickedPageSize.value),
    ])
    Object.assign(clickStats, statsResp?.data?.data || statsResp?.data || {})
    const ph = phonesResp?.data?.data || phonesResp?.data || {}
    clickedPhones.value = ph.items || []
    clickedTotal.value = ph.total || 0
  } catch (e: any) {
    ElMessage.error(`加载点击数据失败：${e?.message || e}`)
  } finally {
    clickStatsLoading.value = false
  }
}

async function loadClickedPhones(page = 1) {
  if (!clickStatsBatch.value) return
  clickStatsLoading.value = true
  try {
    const resp: any = await listBatchClickedPhones(
      clickStatsBatch.value.id, page, clickedPageSize.value,
    )
    const ph = resp?.data?.data || resp?.data || {}
    clickedPhones.value = ph.items || []
    clickedTotal.value = ph.total || 0
    clickedPage.value = page
  } catch (e: any) {
    ElMessage.error(`加载失败：${e?.message || e}`)
  } finally {
    clickStatsLoading.value = false
  }
}

function downloadClickedCsv() {
  if (!clickStatsBatch.value) return
  // 直接打开 URL 由浏览器流式下载；带 Cookie / 代理认证由 nginx 透传
  const url = downloadBatchClickedPhonesCsvUrl(clickStatsBatch.value.id)
  window.open(url, '_blank')
}

/** 回执已送达条数（缺省兼容旧后端） */
function batchDeliveredCount(row: SmsBatch & Record<string, unknown>): number {
  const v = row.delivered_count ?? row.deliveredCount
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 仍为 sent、等待终态回执的条数 */
function batchSentAwaitingCount(row: SmsBatch & Record<string, unknown>): number {
  const v = row.sent_awaiting_receipt_count ?? row.sentAwaitingReceiptCount
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 回执送达率展示字符串 */
function batchDeliveryRatePercent(row: SmsBatch): string {
  if (row.total_count <= 0) return '-'
  const d = batchDeliveredCount(row as SmsBatch & Record<string, unknown>)
  return `${((d / row.total_count) * 100).toFixed(1)}%`
}

function getDeliveryRateClass(row: SmsBatch): string {
  if (row.total_count <= 0) return 'text-muted'
  const d = batchDeliveredCount(row as SmsBatch & Record<string, unknown>)
  const rate = (d / row.total_count) * 100
  if (rate >= 90) return 'rate-high'
  if (rate >= 60) return 'rate-mid'
  return 'rate-low'
}

/** 列表与详情中的时间展示 */
function formatBatchDate(iso: string | null | undefined): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleString()
}

/** 失败条数（兼容 snake_case / camelCase） */
function batchFailedCount(row: SmsBatch & Record<string, unknown>): number {
  const v = row.failed_count ?? row.failedCount
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 是否显示「失败重发」：有失败记录，且非待处理/已取消（含处理中部分失败、已完成、全失败） */
function canRetryFailedBatch(row: SmsBatch & Record<string, unknown>): boolean {
  if (batchFailedCount(row) <= 0) return false
  const st = String(row.status ?? '').toLowerCase()
  if (st === 'pending' || st === 'cancelled') return false
  return true
}

/** 未发送（=未入库到 sms_logs）条数 */
function batchUnsentCount(row: SmsBatch & Record<string, unknown>): number {
  const total = Number(row.total_count) || 0
  const ok = Number(row.success_count) || 0
  const fl = Number(row.failed_count) || 0
  const wait = Number(row.sent_awaiting_receipt_count ?? 0) || 0
  return Math.max(0, total - ok - fl - wait)
}

/** 是否显示「补发未发送」：有缺口、是 CSV 上传的批次、状态非待处理/已取消 */
function canResendUnsentBatch(row: SmsBatch & Record<string, unknown>): boolean {
  if (!row.file_path) return false
  if (batchUnsentCount(row) <= 0) return false
  const st = String(row.status ?? '').toLowerCase()
  if (st === 'pending' || st === 'cancelled') return false
  return true
}

/** 排队中条数 = processing_count（worker 已收但尚未给出终态/上游接收的部分） */
function batchQueuedCount(row: SmsBatch & Record<string, unknown>): number {
  const v = row.processing_count
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 是否显示「排队中重投」：批次状态非 pending/cancelled，且仍有 processing_count > 0。
 * Worker/RabbitMQ 异常导致消息卡 queued 时，运营无需查后端就能从 UI 触发恢复。
 */
function canRequeueQueuedBatch(row: SmsBatch & Record<string, unknown>): boolean {
  if (batchQueuedCount(row) <= 0) return false
  const st = String(row.status ?? '').toLowerCase()
  if (st === 'pending' || st === 'cancelled') return false
  return true
}

/** 存在处理中/待处理批次时定时拉列表，避免用户以为「页面不更新」 */
const LIST_POLL_MS = 15000
let listPollTimer: ReturnType<typeof setInterval> | null = null

function stopListPoll() {
  if (listPollTimer != null) {
    clearInterval(listPollTimer)
    listPollTimer = null
  }
}

function maybeStartListPoll() {
  stopListPoll()
  const need = batches.value.some(
    (b) =>
      b.status === 'processing' ||
      b.status === 'pending' ||
      // COMPLETED 但仍有 sent_awaiting_receipt_count > 0：DLR 还在陆续到达，继续轮询以同步送达率
      (b.status === 'completed' && (b.sent_awaiting_receipt_count ?? 0) > 0),
  )
  if (!need) return
  listPollTimer = setInterval(() => {
    void loadBatches(true)
    void loadStats()
  }, LIST_POLL_MS)
}

const loadBatches = async (silent = false) => {
  if (!silent) loading.value = true
  try {
    const res = await getBatches({ page: pagination.page, page_size: pagination.pageSize })
    batches.value = res.items
    pagination.total = res.total
  } catch (error: any) {
    if (!silent) ElMessage.error(error.response?.data?.detail || t('common.failed'))
  } finally {
    if (!silent) loading.value = false
    maybeStartListPoll()
  }
}

function onPageSizeChange() {
  pagination.page = 1
  loadBatches()
}

/** 手动刷新：列表 + 顶部统计 */
function onManualRefresh() {
  void loadBatches(false)
  void loadStats()
}

const loadStats = async () => {
  try {
    const res = await getBatchStats()
    Object.assign(stats, res)
  } catch (error) {
    console.error('Failed to load stats', error)
  }
}

const loadTemplates = async () => {
  try {
    const res = await getTemplates({ page: 1, page_size: 100, status: 'approved' })
    templates.value = res.items
  } catch (error) {
    console.error('Failed to load templates', error)
  }
}

const showUploadDialog = () => {
  resetUploadForm()
  uploadDialogVisible.value = true
}

const handleFileChange = (file: any) => {
  fileList.value = [file]
}

const submitUpload = async () => {
  if (!uploadForm.batch_name) {
    ElMessage.warning(t('batchSend.pleaseEnterBatchName'))
    return
  }
  
  if (fileList.value.length === 0) {
    ElMessage.warning(t('batchSend.pleaseSelectCsv'))
    return
  }
  
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', fileList.value[0].raw)
    formData.append('batch_name', uploadForm.batch_name)
    if (uploadForm.template_id) {
      formData.append('template_id', uploadForm.template_id.toString())
    }
    if (uploadForm.sender_id) {
      formData.append('sender_id', uploadForm.sender_id)
    }
    
    const res = await uploadBatchFile(formData)
    ElMessage.success(res.message || t('batchSend.uploadSuccess'))
    uploadDialogVisible.value = false
    loadBatches()
    loadStats()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('batchSend.uploadFailed'))
  } finally {
    uploading.value = false
  }
}

function batchStatusLabel(status: string) {
  const map: Record<string, string> = {
    pending: t('batchSend.pending'),
    processing: t('batchSend.processing'),
    completed: t('batchSend.completed'),
    failed: t('batchSend.failed'),
    cancelled: t('batchSend.cancelled'),
  }
  return map[status] || status
}

function batchStatusTagType(status: string): 'info' | 'primary' | 'success' | 'danger' | 'warning' {
  if (status === 'pending') return 'info'
  if (status === 'processing') return 'primary'
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  return 'warning'
}

function recordStatusLabel(status: string) {
  const map: Record<string, string> = {
    pending: t('smsStatus.pending'),
    queued: t('smsStatus.queued'),
    sent: t('smsStatus.sent'),
    delivered: t('smsStatus.delivered'),
    failed: t('smsStatus.failed'),
    expired: t('smsStatus.expired'),
  }
  return map[status] || status
}

function recordStatusTagType(status: string): 'info' | 'primary' | 'success' | 'danger' | 'warning' {
  if (status === 'pending' || status === 'queued') return 'info'
  if (status === 'sent') return 'primary'
  if (status === 'delivered') return 'success'
  if (status === 'failed') return 'danger'
  return 'warning'
}

const loadDetailRecords = async () => {
  if (!detailBatch.value) return
  detailLoading.value = true
  detailError.value = ''
  try {
    const res: any = await getSMSRecords({
      page: detailRecPagination.page,
      page_size: detailRecPagination.pageSize,
      batch_id: detailBatch.value.id,
      message_id: detailMessageId.value.trim() || undefined,
    })
    if (res?.success) {
      detailRecords.value = res.records || []
      detailRecPagination.total = res.total || 0
    } else {
      detailRecords.value = []
      detailRecPagination.total = 0
    }
  } catch (error: any) {
    const d = error.response?.data
    const msg =
      (typeof d?.detail === 'string' && d.detail) ||
      error?.message ||
      t('batchSend.recordsLoadFailed')
    detailError.value = msg
    detailRecords.value = []
    detailRecPagination.total = 0
    ElMessage.error(msg)
  } finally {
    detailLoading.value = false
  }
}

const searchDetailRecords = () => {
  detailRecPagination.page = 1
  loadDetailRecords()
}

const onDetailPageSizeChange = () => {
  detailRecPagination.page = 1
  loadDetailRecords()
}

const onDetailDialogClosed = () => {
  detailBatch.value = null
  detailRecords.value = []
  detailError.value = ''
  detailMessageId.value = ''
  detailRecPagination.page = 1
  detailRecPagination.pageSize = 20
  detailRecPagination.total = 0
}

const viewDetail = (row: SmsBatch) => {
  const bid = Number(row?.id)
  if (!Number.isFinite(bid) || bid <= 0) {
    ElMessage.error(t('batchSend.invalidBatchId'))
    return
  }
  router.push({ path: '/sms/records', query: { batch_id: String(bid) } })
}

const exportBatchCsv = async (row: SmsBatch) => {
  const id = Number(row?.id)
  if (!Number.isFinite(id) || id <= 0) {
    ElMessage.error(t('batchSend.invalidBatchId'))
    return
  }
  exportingBatchId.value = id
  try {
    const res: BlobPart = await exportBatchRecordsCsv(id)
    const blob = new Blob([res], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `batch_${id}_${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success(t('batchSend.exportCsvSuccess'))
  } catch (error: any) {
    const d = error.response?.data
    let msg = t('batchSend.exportCsvFailed')
    if (d instanceof Blob) {
      try {
        const text = await d.text()
        const j = JSON.parse(text)
        if (typeof j?.detail === 'string') msg = j.detail
      } catch {
        /* 忽略 */
      }
    } else if (typeof d?.detail === 'string') {
      msg = d.detail
    }
    ElMessage.error(msg)
  } finally {
    exportingBatchId.value = null
  }
}

const cancelBatch = (row: SmsBatch) => {
  ElMessageBox.confirm(t('batchSend.confirmCancel', { name: row.batch_name }), t('common.info'), {
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel'),
    type: 'warning'
  }).then(async () => {
    try {
      await cancelBatchApi(row.id)
      ElMessage.success(t('batchSend.cancelled'))
      loadBatches()
      loadStats()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('common.failed'))
    }
  }).catch(() => {})
}

const retryFailedBatch = (row: SmsBatch & Record<string, unknown>) => {
  if (batchFailedCount(row) <= 0) return
  ElMessageBox.confirm(t('batchSend.confirmRetryFailed'), t('common.info'), {
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel'),
    type: 'warning'
  }).then(async () => {
    try {
      const res = await retryBatchFailedApi(row.id)
      const msg =
        res.message ||
        (res.partial
          ? t('batchSend.retryPartial', { count: res.retried, pending: res.pending_skipped })
          : t('batchSend.retrySuccess', { count: res.retried }))
      // 余额仅够前 N 条：后端已扣已发，剩余仍 failed —— 用 warning 提示用户去充值
      if (res.partial) {
        ElMessage.warning({ message: msg, duration: 6000 })
      } else {
        ElMessage.success(msg)
      }
      loadBatches()
      loadStats()
    } catch (error: any) {
      const d = error.response?.data?.detail
      ElMessage.error(typeof d === 'string' ? d : t('batchSend.retryFailedMsg'))
    }
  }).catch(() => {})
}

const requeueQueuedBatch = (row: SmsBatch & Record<string, unknown>) => {
  if (batchQueuedCount(row) <= 0) return
  ElMessageBox.confirm(t('batchSend.confirmRequeueQueued'), t('common.info'), {
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel'),
    type: 'warning',
  }).then(async () => {
    try {
      const res = await requeueBatchQueuedApi(row.id)
      ElMessage.success(
        res.message || t('batchSend.requeueQueuedSuccess', { count: res.retried }),
      )
      loadBatches()
      loadStats()
    } catch (error: any) {
      const d = error.response?.data?.detail
      ElMessage.error(typeof d === 'string' ? d : t('batchSend.requeueQueuedFailed'))
    }
  }).catch(() => {})
}

const resendUnsentBatch = (row: SmsBatch & Record<string, unknown>) => {
  const unsent = batchUnsentCount(row)
  if (unsent <= 0) return
  ElMessageBox.confirm(
    t('batchSend.confirmResendUnsent', { name: row.batch_name || `#${row.id}` }),
    t('common.info'),
    {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'warning',
    },
  ).then(async () => {
    try {
      const res = await resendUnsentBatchApi(row.id)
      ElMessage.success(
        res.message ||
          t('batchSend.resendUnsentSuccess', { count: res.unsent_count }),
      )
      loadBatches()
      loadStats()
    } catch (error: any) {
      const d = error.response?.data?.detail
      ElMessage.error(typeof d === 'string' ? d : t('batchSend.resendUnsentFailed'))
    }
  }).catch(() => {})
}

const resetUploadForm = () => {
  uploadForm.batch_name = ''
  uploadForm.template_id = null
  uploadForm.sender_id = ''
  fileList.value = []
}

function onVisibilityRefresh() {
  if (document.visibilityState !== 'visible') return
  void loadBatches(true)
  void loadStats()
}

onMounted(() => {
  loadBatches()
  loadStats()
  loadTemplates()
  document.addEventListener('visibilitychange', onVisibilityRefresh)
})

onUnmounted(() => {
  stopListPoll()
  document.removeEventListener('visibilitychange', onVisibilityRefresh)
})
</script>

<style scoped>
.batch-send-page {
  width: 100%;
}

/* 短链点击对话框 */
.click-stats-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.cs-card {
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 14px 12px;
  text-align: center;
}
.cs-num {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.1;
  color: var(--el-text-color-primary);
}
.cs-num-primary { color: var(--el-color-primary); }
.cs-num-success { color: var(--el-color-success); }
.cs-label {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.click-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 列表上方：通道接受 vs 终态回执 vs 手机送达 说明 */
.batch-metric-hint {
  margin: 0 0 14px;
  align-items: flex-start;
}

.batch-metric-hint :deep(.el-alert__content) {
  line-height: 1.55;
  font-size: 13px;
}

/* 表头「终态回执送达率」悬停说明 */
.batch-rate-header {
  cursor: help;
  border-bottom: 1px dashed var(--el-text-color-secondary);
}

.batch-col-header {
  cursor: help;
  border-bottom: 1px dashed var(--el-text-color-secondary);
}

.awaiting-receipt {
  color: #e6a23c;
  font-weight: 600;
}

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

.stat-card.action {
  justify-content: center;
  padding: 12px;
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-icon.total {
  background: rgba(102, 126, 234, 0.12);
  color: #667EEA;
}

.stat-icon.processing {
  background: rgba(64, 158, 255, 0.12);
  color: #409EFF;
}

.stat-icon.completed {
  background: rgba(56, 239, 125, 0.12);
  color: #38EF7D;
}

.stat-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 12px;
  color: var(--text-tertiary);
}

.create-btn {
  width: 100%;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
}

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

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

/* 表格 */
.table-scroll-wrapper {
  overflow-x: auto;
}
.task-table-inner :deep(.el-table__header th .cell),
.task-table-inner :deep(.el-table__body td .cell) {
  white-space: nowrap;
  word-break: keep-all;
  padding-left: 10px;
  padding-right: 10px;
}

/* 操作列：排除整表 nowrap，否则多按钮重叠 */
.task-table-inner :deep(.el-table__fixed-right .cell) {
  white-space: normal !important;
  word-break: normal;
}

.task-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  line-height: 1.5;
}

.task-name {
  font-weight: 500;
  color: var(--text-primary);
}

.count-success {
  color: #38EF7D;
  font-weight: 600;
}

.count-fail {
  color: #F5576C;
  font-weight: 600;
}

.time-text {
  font-size: 13px;
  color: var(--text-tertiary);
}

.pagination {
  padding: 16px 20px;
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid var(--border-default);
}

.stats-strip {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.panel-header-text {
  flex: 1;
  min-width: 0;
}

.panel-desc {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.5;
  max-width: 720px;
}

.task-empty {
  padding: 32px 16px;
}

.detail-body {
  min-height: 80px;
}

.detail-alert {
  margin-bottom: 12px;
}

.detail-task-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--text-secondary);
}

.detail-task-summary .summary-k {
  color: var(--text-tertiary);
  margin-right: 4px;
}

.detail-task-summary .summary-name {
  font-weight: 600;
  color: var(--text-primary);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1 1 200px;
  min-width: 0;
}

.detail-task-summary .summary-meta {
  flex-basis: 100%;
  font-size: 12px;
  color: var(--text-tertiary);
}

.detail-batch-alert {
  margin-bottom: 12px;
}

.detail-records-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
}

.detail-msgid-input {
  flex: 1;
  min-width: 200px;
  max-width: 360px;
}

.detail-records-table {
  width: 100%;
}

.detail-records-pagination {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

.tag-tooltip-wrap {
  cursor: help;
}

.rate-high {
  color: #67c23a;
  font-weight: 700;
}

.rate-mid {
  color: #e6a23c;
  font-weight: 700;
}

.rate-low {
  color: #f56c6c;
  font-weight: 700;
}

.text-muted {
  color: var(--text-tertiary);
}

code {
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

/* 响应式 */
@media (max-width: 1200px) {
  .stats-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-cards {
    grid-template-columns: 1fr;
  }
}
</style>
