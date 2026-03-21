<template>
  <div class="my-tickets-page">
    <div class="page-header">
      <h2 class="page-title">{{ $t('myTickets.title') }}</h2>
      <el-button type="primary" @click="showCreateDialog">
        <el-icon><Plus /></el-icon>
        {{ $t('myTickets.createTicket') }}
      </el-button>
    </div>

    <!-- 搜索筛选 -->
    <el-card class="filter-card">
      <el-form :inline="true" :model="filters" class="filter-form">
        <el-form-item :label="$t('myTickets.type')">
          <el-select v-model="filters.ticket_type" :placeholder="$t('systemConfig.all')" clearable>
            <el-option :label="$t('myTickets.testApply')" value="test" />
            <el-option :label="$t('myTickets.registration')" value="registration" />
            <el-option :label="$t('myTickets.recharge')" value="recharge" />
            <el-option :label="$t('myTickets.technical')" value="technical" />
            <el-option :label="$t('myTickets.billing')" value="billing" />
            <el-option :label="$t('myTickets.feedback')" value="feedback" />
            <el-option :label="$t('myTickets.other')" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('common.status')">
          <el-select v-model="filters.status" :placeholder="$t('systemConfig.all')" clearable>
            <el-option :label="$t('myTickets.pending')" value="open" />
            <el-option :label="$t('myTickets.inProgress')" value="in_progress" />
            <el-option :label="$t('myTickets.waitingReply')" value="pending_user" />
            <el-option :label="$t('myTickets.resolved')" value="resolved" />
            <el-option :label="$t('myTickets.closed')" value="closed" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadTickets">{{ $t('common.search') }}</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 工单列表 -->
    <el-card class="table-card">
      <el-table :data="tickets" v-loading="loading" stripe @row-click="viewTicket">
        <el-table-column prop="ticket_no" :label="$t('myTickets.ticketNo')" width="180" />
        <el-table-column prop="title" :label="$t('myTickets.ticketTitle')" min-width="200" show-overflow-tooltip />
        <el-table-column prop="ticket_type" :label="$t('myTickets.type')" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ ticketTypeMap[row.ticket_type] || row.ticket_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="priority" :label="$t('tickets.priority')" width="80">
          <template #default="{ row }">
            <el-tag :type="priorityTagType(row.priority)" size="small">
              {{ priorityMap[row.priority] || row.priority }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('common.status')" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusMap[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="$t('common.createdAt')" width="160">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="resolved_at" :label="$t('myTickets.resolvedAt')" width="160">
          <template #default="{ row }">
            {{ formatTime(row.resolved_at) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.actions')" width="100" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click.stop="viewTicket(row)">{{ $t('common.view') }}</el-button>
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
          @size-change="loadTickets"
          @current-change="loadTickets"
        />
      </div>
    </el-card>

    <!-- 创建工单对话框 -->
    <el-dialog v-model="createDialogVisible" :title="$t('myTickets.createTicket')" width="600px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item :label="$t('myTickets.type')" prop="ticket_type">
          <el-select v-model="form.ticket_type" :placeholder="$t('myTickets.selectType')" style="width: 100%">
            <el-option :label="$t('myTickets.testApply')" value="test" />
            <el-option :label="$t('myTickets.registration')" value="registration" />
            <el-option :label="$t('myTickets.recharge')" value="recharge" />
            <el-option :label="$t('myTickets.technical')" value="technical" />
            <el-option :label="$t('myTickets.billing')" value="billing" />
            <el-option :label="$t('myTickets.feedback')" value="feedback" />
            <el-option :label="$t('myTickets.other')" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('tickets.priority')" prop="priority">
          <el-radio-group v-model="form.priority">
            <el-radio value="low">{{ $t('tickets.low') }}</el-radio>
            <el-radio value="normal">{{ $t('tickets.normal') }}</el-radio>
            <el-radio value="high">{{ $t('tickets.high') }}</el-radio>
            <el-radio value="urgent">{{ $t('tickets.urgent') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="$t('myTickets.ticketTitle')" prop="title">
          <el-input v-model="form.title" :placeholder="$t('myTickets.titlePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('myTickets.description')" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="5"
            :placeholder="$t('myTickets.descriptionPlaceholder')"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="createDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="submitTicket">{{ $t('common.submit') }}</el-button>
      </template>
    </el-dialog>

    <!-- 工单详情对话框 -->
    <el-drawer
      v-model="detailDrawerVisible"
      :title="$t('myTickets.ticketDetail')"
      size="550px"
      destroy-on-close
    >
      <div v-if="currentTicket" class="ticket-detail">
        <div class="ticket-info">
          <div class="info-row">
            <span class="label">{{ $t('myTickets.ticketNo') }}:</span>
            <span class="value">{{ currentTicket.ticket_no }}</span>
          </div>
          <div class="info-row">
            <span class="label">{{ $t('myTickets.ticketTitle') }}:</span>
            <span class="value">{{ currentTicket.title }}</span>
          </div>
          <div class="info-row">
            <span class="label">{{ $t('myTickets.type') }}:</span>
            <el-tag size="small">{{ ticketTypeMap[currentTicket.ticket_type] }}</el-tag>
          </div>
          <div class="info-row">
            <span class="label">{{ $t('common.status') }}:</span>
            <el-tag :type="statusTagType(currentTicket.status)" size="small">
              {{ statusMap[currentTicket.status] }}
            </el-tag>
          </div>
          <div class="info-row">
            <span class="label">{{ $t('common.createdAt') }}:</span>
            <span class="value">{{ formatTime(currentTicket.created_at) }}</span>
          </div>
        </div>

        <el-divider>{{ $t('myTickets.problemDescription') }}</el-divider>
        <div class="ticket-description">
          {{ currentTicket.description || $t('myTickets.noDescription') }}
        </div>

        <el-divider>{{ $t('myTickets.communicationRecord') }}</el-divider>
        <div class="replies-list">
          <div
            v-for="reply in currentTicket.replies"
            :key="reply.id"
            :class="['reply-item', reply.reply_by_type === 'account' ? 'reply-mine' : 'reply-support']"
          >
            <div class="reply-header">
              <span class="reply-author">
                {{ reply.reply_by_type === 'account' ? $t('myTickets.me') : $t('myTickets.support') }}
                <el-tag v-if="reply.is_solution" type="success" size="small">{{ $t('myTickets.solution') }}</el-tag>
              </span>
              <span class="reply-time">{{ formatTime(reply.created_at) }}</span>
            </div>
            <div class="reply-content">{{ reply.content }}</div>
          </div>
          <el-empty v-if="!currentTicket.replies?.length" :description="$t('myTickets.noReplies')" :image-size="80" />
        </div>

        <template v-if="!['closed', 'cancelled', 'resolved'].includes(currentTicket.status)">
          <el-divider>{{ $t('myTickets.reply') }}</el-divider>
          <div class="reply-form">
            <el-input
              v-model="replyContent"
              type="textarea"
              :rows="3"
              :placeholder="$t('myTickets.replyPlaceholder')"
            />
            <div class="reply-actions">
              <el-button type="primary" :loading="replySubmitting" @click="submitReply">{{ $t('common.send') }}</el-button>
            </div>
          </div>
        </template>

        <template v-if="currentTicket.status === 'resolved' && !currentTicket.satisfaction_rating">
          <el-divider>{{ $t('myTickets.rating') }}</el-divider>
          <div class="rating-form">
            <p>{{ $t('myTickets.ratingPrompt') }}</p>
            <el-rate v-model="rating" :colors="['#99A9BF', '#F7BA2A', '#FF9900']" />
            <el-input
              v-model="ratingComment"
              type="textarea"
              :rows="2"
              :placeholder="$t('myTickets.ratingCommentPlaceholder')"
              style="margin-top: 12px"
            />
            <el-button type="primary" style="margin-top: 12px" :loading="ratingSubmitting" @click="submitRating">
              {{ $t('myTickets.submitRating') }}
            </el-button>
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  getMyTickets, createTicket, getTicketDetail, replyTicket, rateTicket,
  type Ticket, type TicketDetail
} from '@/api/ticket'

const { t } = useI18n()

// 映射 - 使用计算属性以支持响应式语言切换
const ticketTypeMap = computed<Record<string, string>>(() => ({
  test: t('myTickets.testApply'),
  registration: t('myTickets.registration'),
  recharge: t('myTickets.recharge'),
  technical: t('myTickets.technical'),
  billing: t('myTickets.billing'),
  feedback: t('myTickets.feedback'),
  other: t('myTickets.other')
}))

const statusMap = computed<Record<string, string>>(() => ({
  open: t('myTickets.pending'),
  assigned: t('myTickets.inProgress'),
  in_progress: t('myTickets.inProgress'),
  pending_user: t('myTickets.waitingReply'),
  resolved: t('myTickets.resolved'),
  closed: t('myTickets.closed'),
  cancelled: t('myTickets.cancelled')
}))

const priorityMap = computed<Record<string, string>>(() => ({
  urgent: t('tickets.urgent'),
  high: t('tickets.high'),
  normal: t('tickets.normal'),
  low: t('tickets.low')
}))

const statusTagType = (status: string) => {
  const map: Record<string, string> = {
    open: 'warning',
    assigned: 'primary',
    in_progress: 'primary',
    pending_user: 'danger',
    resolved: 'success',
    closed: 'info'
  }
  return map[status] || 'info'
}

const priorityTagType = (priority: string) => {
  const map: Record<string, string> = {
    urgent: 'danger',
    high: 'warning',
    normal: '',
    low: 'info'
  }
  return map[priority] || ''
}

const formatTime = (time?: string) => {
  if (!time) return '-'
  return new Date(time).toLocaleString('zh-CN')
}

// 数据
const loading = ref(false)
const tickets = ref<Ticket[]>([])
const filters = reactive({
  ticket_type: '',
  status: ''
})
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

// 创建
const createDialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({
  ticket_type: 'other',
  priority: 'normal',
  title: '',
  description: ''
})

const rules = computed<FormRules>(() => ({
  ticket_type: [{ required: true, message: t('myTickets.selectTypeRequired'), trigger: 'change' }],
  title: [{ required: true, message: t('myTickets.titleRequired'), trigger: 'blur' }]
}))

// 详情
const detailDrawerVisible = ref(false)
const currentTicket = ref<TicketDetail | null>(null)
const replyContent = ref('')
const replySubmitting = ref(false)

// 评价
const rating = ref(5)
const ratingComment = ref('')
const ratingSubmitting = ref(false)

// 方法
const loadTickets = async () => {
  loading.value = true
  try {
    const res = await getMyTickets({
      page: pagination.page,
      page_size: pagination.pageSize,
      ticket_type: filters.ticket_type || undefined,
      status: filters.status || undefined
    })
    if (res.data.success) {
      tickets.value = res.data.tickets
      pagination.total = res.data.total
    }
  } catch (error) {
    console.error('Failed to load tickets:', error)
  } finally {
    loading.value = false
  }
}

const showCreateDialog = () => {
  Object.assign(form, {
    ticket_type: 'other',
    priority: 'normal',
    title: '',
    description: ''
  })
  createDialogVisible.value = true
}

const submitTicket = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return

    submitting.value = true
    try {
      const res = await createTicket(form)
      if (res.data.success) {
        ElMessage.success(t('myTickets.createSuccess'))
        createDialogVisible.value = false
        loadTickets()
      }
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('myTickets.createFailed'))
    } finally {
      submitting.value = false
    }
  })
}

const viewTicket = async (row: Ticket) => {
  try {
    const res = await getTicketDetail(row.id)
    if (res.data.success) {
      currentTicket.value = res.data.ticket
      replyContent.value = ''
      rating.value = 5
      ratingComment.value = ''
      detailDrawerVisible.value = true
    }
  } catch (error) {
    console.error('Failed to load ticket detail:', error)
    ElMessage.error(t('myTickets.loadDetailFailed'))
  }
}

const submitReply = async () => {
  if (!replyContent.value.trim()) {
    ElMessage.warning(t('myTickets.replyContentRequired'))
    return
  }
  if (!currentTicket.value) return

  replySubmitting.value = true
  try {
    await replyTicket(currentTicket.value.id, {
      content: replyContent.value
    })
    ElMessage.success(t('myTickets.replySuccess'))
    replyContent.value = ''
    // 重新加载
    const res = await getTicketDetail(currentTicket.value.id)
    if (res.data.success) {
      currentTicket.value = res.data.ticket
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('myTickets.replyFailed'))
  } finally {
    replySubmitting.value = false
  }
}

const submitRating = async () => {
  if (!currentTicket.value) return

  ratingSubmitting.value = true
  try {
    await rateTicket(currentTicket.value.id, rating.value, ratingComment.value || undefined)
    ElMessage.success(t('myTickets.ratingSuccess'))
    // 重新加载
    const res = await getTicketDetail(currentTicket.value.id)
    if (res.data.success) {
      currentTicket.value = res.data.ticket
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('myTickets.ratingFailed'))
  } finally {
    ratingSubmitting.value = false
  }
}

onMounted(() => {
  loadTickets()
})
</script>

<style scoped>
.my-tickets-page {
  width: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.filter-card {
  margin-bottom: 20px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.table-card {
  margin-bottom: 20px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.ticket-detail {
  padding: 0 10px;
}

.ticket-info {
  background: var(--bg-hover);
  border-radius: 8px;
  padding: 16px;
}

.info-row {
  display: flex;
  margin-bottom: 8px;
}

.info-row:last-child {
  margin-bottom: 0;
}

.info-row .label {
  width: 80px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.info-row .value {
  color: var(--text-primary);
}

.ticket-description {
  background: var(--bg-hover);
  border-radius: 8px;
  padding: 16px;
  color: var(--text-primary);
  white-space: pre-wrap;
  line-height: 1.6;
}

.replies-list {
  max-height: 300px;
  overflow-y: auto;
}

.reply-item {
  padding: 12px;
  border-radius: 8px;
  margin-bottom: 12px;
}

.reply-mine {
  background: rgba(64, 158, 255, 0.1);
  margin-left: 40px;
}

.reply-support {
  background: var(--bg-hover);
  margin-right: 40px;
}

.reply-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.reply-author {
  font-weight: 500;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.reply-time {
  font-size: 12px;
  color: var(--text-secondary);
}

.reply-content {
  color: var(--text-primary);
  line-height: 1.6;
  white-space: pre-wrap;
}

.reply-form {
  margin-top: 16px;
}

.reply-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.rating-form {
  text-align: center;
  padding: 20px;
  background: var(--bg-hover);
  border-radius: 8px;
}
</style>
