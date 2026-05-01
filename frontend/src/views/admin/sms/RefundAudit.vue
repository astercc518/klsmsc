<template>
  <div class="refund-audit-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">退款审核</h1>
        <p class="page-desc">对因系统问题导致提交失败的短信进行人工审核退款</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" @click="loadList">刷新</el-button>
        <el-button
          v-if="selected.length > 0"
          type="primary"
          @click="openBatchRefund"
        >批量退款 ({{ selected.length }})</el-button>
      </div>
    </div>

    <!-- 筛选区 -->
    <div class="filter-bar">
      <el-input v-model="filters.keyword" placeholder="消息ID / 手机号" clearable style="width: 200px" @change="loadList" />
      <el-input v-model.number="filters.account_id" placeholder="账户ID" clearable style="width: 130px" @change="loadList" />
      <el-input v-model.number="filters.batch_id" placeholder="批次ID" clearable style="width: 130px" @change="loadList" />
      <el-input v-model.number="filters.channel_id" placeholder="通道ID" clearable style="width: 130px" @change="loadList" />
    </div>

    <!-- 列表 -->
    <el-table
      v-loading="loading"
      :data="items"
      stripe
      class="audit-table"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="45" />
      <el-table-column prop="sms_log_id" label="SMS ID" width="90" />
      <el-table-column label="账户" width="100">
        <template #default="{ row }">
          <span class="muted">#{{ row.account_id }}</span>
        </template>
      </el-table-column>
      <el-table-column label="批次" width="90">
        <template #default="{ row }">
          <span v-if="row.batch_id" class="muted">#{{ row.batch_id }}</span>
          <span v-else class="muted">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="phone_number" label="手机号" width="150" />
      <el-table-column prop="country_code" label="国家" width="70" />
      <el-table-column label="费用" width="110">
        <template #default="{ row }">
          <span>{{ fmtMoney(row.selling_price) }}</span>
          <span class="currency">{{ row.currency || '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag type="danger" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="分类" width="130">
        <template #default="{ row }">
          <el-tag :type="categoryType(row.category)" size="small">{{ row.category }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="error_message" label="错误信息" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="muted">{{ row.error_message || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="提交时间" width="165">
        <template #default="{ row }">
          {{ fmtTime(row.submit_time) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openSingle(row)">审核</el-button>
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

    <!-- 单条审核抽屉 -->
    <el-drawer v-model="singleVisible" title="退款审核" size="520px" :before-close="closeSingle">
      <div v-if="preview" class="audit-drawer">
        <el-alert
          v-if="!preview.eligible"
          :title="`不符合退款条件：${preview.reason}`"
          type="error"
          :closable="false"
          style="margin-bottom: 16px"
        />
        <el-alert
          v-else
          title="符合退款条件"
          type="success"
          :closable="false"
          style="margin-bottom: 16px"
        />

        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="SMS ID">{{ preview.sms_log_id }}</el-descriptions-item>
          <el-descriptions-item label="消息ID">{{ preview.message_id }}</el-descriptions-item>
          <el-descriptions-item label="账户ID">{{ preview.account_id }}</el-descriptions-item>
          <el-descriptions-item label="退款金额">
            <span class="amount-highlight">{{ fmtMoney(preview.amount_to_refund) }} {{ preview.currency || '' }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="preview.error_message" label="错误信息">
            <span class="muted">{{ preview.error_message }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="preview.upstream_message_id" label="上游消息ID">
            <span class="muted">{{ preview.upstream_message_id }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="preview.refunded_at" label="已退款时间">
            <el-tag type="info" size="small">已于 {{ fmtTime(preview.refunded_at) }} 退款</el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <el-form label-width="80px" style="margin-top: 20px">
          <el-form-item label="备注">
            <el-input v-model="auditNote" type="textarea" :rows="3" placeholder="可选，记录退款原因（最长200字）" maxlength="200" show-word-limit />
          </el-form-item>
        </el-form>
      </div>

      <div v-else-if="previewLoading" class="drawer-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>

      <template #footer>
        <el-button @click="closeSingle">取消</el-button>
        <el-button
          type="primary"
          :loading="submitting"
          :disabled="!preview?.eligible || !!preview?.refunded_at"
          @click="confirmSingle"
        >确认退款</el-button>
      </template>
    </el-drawer>

    <!-- 批量退款确认对话框 -->
    <el-dialog v-model="batchVisible" title="批量退款确认" width="500px" :close-on-click-modal="false">
      <div class="batch-confirm">
        <el-alert type="warning" :closable="false" style="margin-bottom: 16px">
          <template #title>即将对 {{ selected.length }} 条记录执行退款，此操作不可撤销</template>
        </el-alert>
        <p class="batch-ids">
          涉及 SMS ID：
          <span v-for="id in selected.slice(0, 10)" :key="id" class="id-chip">{{ id }}</span>
          <span v-if="selected.length > 10" class="muted">...等共 {{ selected.length }} 条</span>
        </p>
        <el-form label-width="80px" style="margin-top: 12px">
          <el-form-item label="备注">
            <el-input v-model="batchNote" type="textarea" :rows="2" placeholder="可选" maxlength="200" />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="batchVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchSubmitting" @click="submitBatch">确认批量退款</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Loading } from '@element-plus/icons-vue'
import {
  listRefundable, previewRefund, executeRefund, executeRefundBatch,
  type RefundCandidate,
} from '@/api/sms-refund'

const route = useRoute()
const loading = ref(false)
const items = ref<RefundCandidate[]>([])
const pagination = reactive({ total: 0, page: 1, page_size: 20 })
const filters = reactive<{ keyword?: string; account_id?: number; batch_id?: number; channel_id?: number }>({})

const selected = ref<number[]>([])

const singleVisible = ref(false)
const preview = ref<Awaited<ReturnType<typeof previewRefund>>['data'] | null>(null)
const previewLoading = ref(false)
const auditNote = ref('')
const submitting = ref(false)

const batchVisible = ref(false)
const batchNote = ref('')
const batchSubmitting = ref(false)

function onSelectionChange(rows: RefundCandidate[]) {
  selected.value = rows.map(r => r.sms_log_id)
}

async function loadList() {
  loading.value = true
  try {
    const { data } = await listRefundable({
      ...filters,
      page: pagination.page,
      page_size: pagination.page_size,
    })
    if (data.success) {
      items.value = data.items
      pagination.total = data.total
    }
  } finally {
    loading.value = false
  }
}

async function openSingle(row: RefundCandidate) {
  preview.value = null
  auditNote.value = ''
  singleVisible.value = true
  previewLoading.value = true
  try {
    const { data } = await previewRefund(row.sms_log_id)
    preview.value = data
  } finally {
    previewLoading.value = false
  }
}

function closeSingle() {
  singleVisible.value = false
  preview.value = null
}

async function confirmSingle() {
  if (!preview.value) return
  try {
    await ElMessageBox.confirm(
      `确认对 SMS #${preview.value.sms_log_id} 退款 ${fmtMoney(preview.value.amount_to_refund)} ${preview.value.currency || ''}？`,
      '退款确认', { type: 'warning', confirmButtonText: '确认退款', cancelButtonText: '取消' }
    )
  } catch { return }

  submitting.value = true
  try {
    const { data } = await executeRefund(preview.value.sms_log_id, auditNote.value || undefined)
    if (data.success) {
      ElMessage.success(`退款成功，退还 ${fmtMoney(data.amount)} ${data.category || ''}`)
      closeSingle()
      loadList()
    } else {
      ElMessage.error(data.reason || '退款失败')
    }
  } finally {
    submitting.value = false
  }
}

function openBatchRefund() {
  batchNote.value = ''
  batchVisible.value = true
}

async function submitBatch() {
  if (selected.value.length === 0) return
  batchSubmitting.value = true
  try {
    const { data } = await executeRefundBatch(selected.value, batchNote.value || undefined)
    if (data.success) {
      ElMessage.success(`批量退款完成：成功 ${data.ok ?? 0} 条，失败 ${data.failed ?? 0} 条，总计退还 ${fmtMoney(data.total_amount)}`)
      if (data.failures && data.failures.length > 0) {
        const failList = data.failures.slice(0, 5).map(f => `#${f.sms_log_id}: ${f.reason}`).join('\n')
        ElMessage.warning(`部分退款失败：\n${failList}`)
      }
      batchVisible.value = false
      selected.value = []
      loadList()
    } else {
      ElMessage.error(data.error || '批量退款失败')
    }
  } finally {
    batchSubmitting.value = false
  }
}

function categoryType(cat: string): any {
  if (!cat) return 'info'
  if (cat.includes('失败') || cat.includes('error')) return 'danger'
  if (cat.includes('超时') || cat.includes('timeout')) return 'warning'
  return 'info'
}

function fmtMoney(v: any) {
  if (v == null || v === '') return '-'
  return Number(v).toFixed(4)
}

function fmtTime(t?: string | null) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}

onMounted(() => {
  const batchId = route.query.batch_id
  if (batchId) filters.batch_id = Number(batchId)
  loadList()
})
</script>

<style scoped>
.refund-audit-page { padding: 16px 24px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.page-title { font-size: 22px; margin: 0 0 4px 0; }
.page-desc { color: var(--el-text-color-secondary); margin: 0; }
.header-actions { display: flex; gap: 8px; }

.filter-bar { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; align-items: center; }

.audit-table { margin-bottom: 12px; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.currency { margin-left: 4px; color: var(--el-text-color-secondary); font-size: 11px; }

.pagination-bar { display: flex; justify-content: flex-end; }

.audit-drawer { padding: 0 4px; }
.amount-highlight { font-size: 16px; font-weight: 600; color: var(--el-color-primary); }

.drawer-loading { display: flex; gap: 8px; align-items: center; justify-content: center; padding: 40px 0; color: var(--el-text-color-secondary); }

.batch-confirm { padding: 0 4px; }
.batch-ids { font-size: 13px; color: var(--el-text-color-secondary); margin: 0 0 4px 0; }
.id-chip { display: inline-block; background: var(--el-fill-color-light); border-radius: 4px; padding: 1px 6px; margin: 2px 3px 2px 0; font-size: 12px; }
</style>
