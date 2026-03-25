<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">{{ $t('tickets.title') }}</h1>
        <p class="page-desc">{{ $t('tickets.pageDesc') }}</p>
      </div>
      <div class="header-right">
        <el-button @click="loadTickets" :icon="Refresh">{{ $t('common.refresh') }}</el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card urgent">
        <div class="stat-icon">
          <el-icon><Warning /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ dashboard.pending_count }}</div>
          <div class="stat-label">{{ $t('tickets.pending') }}</div>
        </div>
      </div>
      <div class="stat-card today">
        <div class="stat-icon">
          <el-icon><Calendar /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ dashboard.today_count }}</div>
          <div class="stat-label">{{ $t('tickets.todayNew') }}</div>
        </div>
      </div>
      <div class="stat-card progress">
        <div class="stat-icon">
          <el-icon><Loading /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ dashboard.status_stats?.in_progress || 0 }}</div>
          <div class="stat-label">{{ $t('tickets.inProgress') }}</div>
        </div>
      </div>
      <div class="stat-card resolved">
        <div class="stat-icon">
          <el-icon><CircleCheck /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ dashboard.status_stats?.resolved || 0 }}</div>
          <div class="stat-label">{{ $t('tickets.resolved') }}</div>
        </div>
      </div>
      <div class="stat-card total">
        <div class="stat-icon">
          <el-icon><Tickets /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ dashboard.total_count }}</div>
          <div class="stat-label">{{ $t('tickets.totalTickets') }}</div>
        </div>
      </div>
    </div>

    <!-- 搜索筛选 -->
    <div class="filter-bar">
      <el-input v-model="filters.keyword" :placeholder="$t('tickets.searchPlaceholder')" clearable style="width: 200px" @keyup.enter="loadTickets">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="filters.ticket_type" :placeholder="$t('tickets.ticketType')" clearable style="width: 130px" @change="loadTickets">
        <el-option :label="$t('tickets.testApp')" value="test" />
        <el-option :label="$t('tickets.registration')" value="registration" />
        <el-option :label="$t('tickets.recharge')" value="recharge" />
        <el-option :label="$t('tickets.technical')" value="technical" />
        <el-option :label="$t('tickets.billing')" value="billing" />
        <el-option :label="$t('tickets.feedback')" value="feedback" />
        <el-option :label="$t('tickets.other')" value="other" />
      </el-select>
      <el-select v-model="filters.status" :placeholder="$t('common.status')" clearable style="width: 120px" @change="loadTickets">
        <el-option :label="$t('tickets.open')" value="open" />
        <el-option :label="$t('tickets.assigned')" value="assigned" />
        <el-option :label="$t('tickets.inProgress')" value="in_progress" />
        <el-option :label="$t('tickets.pendingUser')" value="pending_user" />
        <el-option :label="$t('tickets.resolved')" value="resolved" />
        <el-option :label="$t('tickets.closed')" value="closed" />
      </el-select>
      <el-select v-model="filters.priority" :placeholder="$t('tickets.priority')" clearable style="width: 110px" @change="loadTickets">
        <el-option :label="$t('tickets.urgent')" value="urgent" />
        <el-option :label="$t('tickets.high')" value="high" />
        <el-option :label="$t('tickets.normal')" value="normal" />
        <el-option :label="$t('tickets.low')" value="low" />
      </el-select>
      <el-button @click="resetFilters">{{ $t('common.reset') }}</el-button>
    </div>

    <!-- 工单列表 -->
    <div class="table-card">
      <el-table :data="tickets" v-loading="loading" class="data-table" @row-click="viewTicket">
        <el-table-column prop="ticket_no" :label="$t('tickets.ticketNo')" width="160">
          <template #default="{ row }">
            <span class="ticket-no">{{ row.ticket_no }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="title" :label="$t('tickets.subject')" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="title-cell">
              <span class="ticket-title">{{ row.title }}</span>
              <el-tag v-if="isNew(row.created_at)" type="danger" size="small" effect="dark" class="new-tag">{{ $t('tickets.new') }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="ticket_type" :label="$t('tickets.ticketType')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="typeTagType(row.ticket_type)" size="small" effect="plain">
              {{ getTicketTypeLabel(row.ticket_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="priority" :label="$t('tickets.priority')" width="80" align="center">
          <template #default="{ row }">
            <span :class="['priority-dot', `priority-${row.priority}`]"></span>
            {{ getPriorityLabel(row.priority) }}
          </template>
        </el-table-column>
        <el-table-column prop="account_name" :label="$t('tickets.customer')" width="130">
          <template #default="{ row }">
            <span class="customer-name">{{ row.account_name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assignee_name" :label="$t('tickets.assignee')" width="100">
          <template #default="{ row }">
            <span v-if="row.assignee_name" class="assignee-name">{{ row.assignee_name }}</span>
            <span v-else class="text-muted">{{ $t('tickets.unassigned') }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('common.status')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="$t('tickets.createdAt')" width="150">
          <template #default="{ row }">
            <span class="time-text">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.actions')" width="240" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click.stop="viewTicket(row)">{{ $t('common.view') }}</el-button>
            <el-button
              v-if="row.status === 'open'"
              type="warning"
              link
              size="small"
              @click.stop="handleAssign(row)"
            >{{ $t('tickets.assign') }}</el-button>
            <el-button
              v-if="['open', 'assigned', 'in_progress', 'pending_user'].includes(row.status)"
              type="success"
              link
              size="small"
              @click.stop="handleResolve(row)"
            >{{ $t('tickets.resolve') }}</el-button>
            <el-button
              v-if="row.status === 'resolved'"
              type="info"
              link
              size="small"
              @click.stop="handleClose(row)"
            >{{ $t('tickets.close') }}</el-button>
            <el-button type="danger" link size="small" @click.stop="handleDelete(row)">{{ $t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next, sizes"
          :total="pagination.total"
          :page-size="pagination.pageSize"
          :current-page="pagination.page"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="(p:number) => { pagination.page = p; loadTickets() }"
          @size-change="(s:number) => { pagination.pageSize = s; pagination.page = 1; loadTickets() }"
        />
      </div>
    </div>

    <!-- 工单详情抽屉 -->
    <el-drawer
      v-model="detailDrawerVisible"
      :title="$t('tickets.detail')"
      size="650px"
      destroy-on-close
    >
      <div v-if="currentTicket" class="ticket-detail">
        <!-- 基本信息 -->
        <div class="detail-section">
          <div class="section-header">
            <h3>{{ $t('tickets.basicInfo') }}</h3>
            <div class="header-actions">
              <el-tag :type="statusTagType(currentTicket.status)" size="default">
                {{ getStatusLabel(currentTicket.status) }}
              </el-tag>
            </div>
          </div>
          <div class="info-grid">
            <div class="info-item">
              <span class="info-label">{{ $t('tickets.ticketNo') }}</span>
              <span class="info-value">{{ currentTicket.ticket_no }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('tickets.type') }}</span>
              <el-tag :type="typeTagType(currentTicket.ticket_type)" size="small">
                {{ getTicketTypeLabel(currentTicket.ticket_type) }}
              </el-tag>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('tickets.priority') }}</span>
              <span :class="['priority-text', `priority-${currentTicket.priority}`]">
                {{ getPriorityLabel(currentTicket.priority) }}
              </span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('tickets.customer') }}</span>
              <span class="info-value">{{ currentTicket.account_name || '-' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('tickets.assignee') }}</span>
              <span class="info-value">{{ currentTicket.assignee_name || $t('tickets.unassigned') }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('tickets.createdAt') }}</span>
              <span class="info-value">{{ formatTime(currentTicket.created_at) }}</span>
            </div>
          </div>
        </div>

        <!-- 标题和描述 -->
        <div class="detail-section">
          <div class="section-header">
            <h3>{{ currentTicket.title }}</h3>
          </div>
          <div class="description-box">
            {{ currentTicket.description || $t('tickets.noDescription') }}
          </div>
        </div>

        <!-- 快捷操作 -->
        <div class="quick-actions" v-if="!['resolved', 'closed', 'cancelled'].includes(currentTicket.status)">
          <el-button v-if="currentTicket.status === 'open'" type="warning" @click="handleAssign(currentTicket)">
            <el-icon><User /></el-icon> {{ $t('tickets.assignTicket') }}
          </el-button>
          <el-button type="primary" @click="changeStatus('in_progress')" v-if="['open', 'assigned'].includes(currentTicket.status)">
            <el-icon><VideoPlay /></el-icon> {{ $t('tickets.startProcessing') }}
          </el-button>
          <el-button type="success" @click="handleResolve(currentTicket)">
            <el-icon><CircleCheck /></el-icon> {{ $t('tickets.markResolved') }}
          </el-button>
        </div>

        <!-- 沟通记录 -->
        <div class="detail-section">
          <div class="section-header">
            <h3>{{ $t('tickets.communication') }}</h3>
            <span class="reply-count">{{ $t('tickets.replyCount', { count: currentTicket.replies?.length || 0 }) }}</span>
          </div>
          <div class="timeline">
            <div
              v-for="reply in currentTicket.replies"
              :key="reply.id"
              :class="['timeline-item', reply.reply_by_type === 'admin' ? 'admin-reply' : 'user-reply']"
            >
              <div class="timeline-avatar">
                {{ (reply.reply_by_name || (reply.reply_by_type === 'admin' ? $t('tickets.staff') : $t('tickets.customerUser'))).charAt(0) }}
              </div>
              <div class="timeline-content">
                <div class="timeline-header">
                  <span class="author">{{ reply.reply_by_name || (reply.reply_by_type === 'admin' ? $t('tickets.staff') : $t('tickets.customerUser')) }}</span>
                  <div class="tags">
                    <el-tag v-if="reply.is_internal" type="warning" size="small">{{ $t('tickets.internal') }}</el-tag>
                    <el-tag v-if="reply.is_solution" type="success" size="small">{{ $t('tickets.solution') }}</el-tag>
                  </div>
                  <span class="time">{{ formatTime(reply.created_at) }}</span>
                </div>
                <div class="timeline-body">{{ reply.content }}</div>
                <div v-if="reply.attachments?.length" class="timeline-attachments">
                  <TicketAttachmentImage
                    v-for="(att, idx) in reply.attachments"
                    :key="idx"
                    :ticket-id="currentTicket!.id"
                    :filename="att"
                    class="attachment-thumb"
                  />
                </div>
              </div>
            </div>
            <div v-if="!currentTicket.replies?.length" class="no-replies">
              {{ $t('tickets.noReplies') }}
            </div>
          </div>
        </div>

        <!-- 回复表单 -->
        <div class="reply-form" v-if="!['closed', 'cancelled'].includes(currentTicket.status)">
          <el-input
            v-model="replyContent"
            type="textarea"
            :rows="3"
            :placeholder="$t('tickets.replyPlaceholder')"
            resize="none"
          />
          <div class="reply-toolbar">
            <el-checkbox v-model="isInternalNote">{{ $t('tickets.internalNote') }}</el-checkbox>
            <el-button type="primary" :loading="replySubmitting" @click="submitReply">
              <el-icon><Promotion /></el-icon> {{ $t('tickets.sendReply') }}
            </el-button>
          </div>
        </div>

        <!-- 解决方案 -->
        <div class="detail-section" v-if="currentTicket.resolution">
          <div class="section-header">
            <h3>{{ $t('tickets.solution') }}</h3>
          </div>
          <div class="resolution-box">
            {{ currentTicket.resolution }}
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- 分配对话框 -->
    <el-dialog v-model="assignDialogVisible" :title="$t('tickets.assignTicket')" width="420px">
      <el-form label-width="80px">
        <el-form-item :label="$t('tickets.assignee')">
          <el-select v-model="assignAdminId" :placeholder="$t('tickets.selectAssignee')" style="width: 100%" filterable>
            <el-option
              v-for="admin in adminList"
              :key="admin.id"
              :label="`${admin.real_name || admin.username} (${admin.role})`"
              :value="admin.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('tickets.note')">
          <el-input v-model="assignNote" type="textarea" :rows="2" :placeholder="$t('tickets.assignNotePlaceholder')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="assignSubmitting" @click="submitAssign">{{ $t('tickets.confirmAssign') }}</el-button>
      </template>
    </el-dialog>

    <!-- 解决对话框 -->
    <el-dialog v-model="resolveDialogVisible" :title="$t('tickets.resolveTicket')" width="520px">
      <el-form label-width="80px">
        <el-form-item :label="$t('tickets.solution')" required>
          <el-input
            v-model="resolution"
            type="textarea"
            :rows="4"
            :placeholder="$t('tickets.solutionPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="$t('tickets.uploadImages')">
          <el-upload
            ref="resolveUploadRef"
            :auto-upload="false"
            :limit="5"
            accept="image/*"
            :file-list="resolveFileList"
            :on-change="onResolveFileChange"
            :on-remove="onResolveFileRemove"
          >
            <el-button type="primary" link size="small">
              <el-icon><Plus /></el-icon>
              {{ $t('tickets.uploadImages') }}
            </el-button>
          </el-upload>
          <div class="upload-tip">{{ $t('tickets.uploadImagesTip') }}</div>
        </el-form-item>
        <el-form-item :label="$t('tickets.satisfaction')">
          <el-rate v-model="satisfactionScore" :colors="['#99A9BF', '#F7BA2A', '#FF9900']" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resolveDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="resolveSubmitting" @click="submitResolve">{{ $t('tickets.confirmResolve') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
  Search, Refresh, Warning, Calendar, Loading, CircleCheck, Tickets, 
  User, VideoPlay, Promotion, Plus 
} from '@element-plus/icons-vue'
import {
  getAdminTickets, getTicketsDashboard, getAdminTicketDetail,
  assignTicket, adminReplyTicket, resolveTicket, updateTicketStatus, deleteAdminTicket,
  type Ticket, type TicketDetail
} from '@/api/ticket'
import request from '@/api/index'
import TicketAttachmentImage from './TicketAttachmentImage.vue'

const { t } = useI18n()

// 获取翻译后的标签
const getTicketTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    test: t('tickets.testApp'),
    registration: t('tickets.registration'),
    recharge: t('tickets.recharge'),
    technical: t('tickets.technical'),
    billing: t('tickets.billing'),
    feedback: t('tickets.feedback'),
    other: t('tickets.other')
  }
  return map[type] || type
}

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = {
    open: t('tickets.open'),
    assigned: t('tickets.assigned'),
    in_progress: t('tickets.inProgress'),
    pending_user: t('tickets.pendingUser'),
    resolved: t('tickets.resolved'),
    closed: t('tickets.closed'),
    cancelled: t('tickets.cancelled')
  }
  return map[status] || status
}

const getPriorityLabel = (priority: string) => {
  const map: Record<string, string> = {
    urgent: t('tickets.urgent'),
    high: t('tickets.high'),
    normal: t('tickets.normal'),
    low: t('tickets.low')
  }
  return map[priority] || priority
}

const statusTagType = (status: string) => {
  const map: Record<string, string> = {
    open: 'danger',
    assigned: 'warning',
    in_progress: 'primary',
    pending_user: 'info',
    resolved: 'success',
    closed: 'info'
  }
  return map[status] || 'info'
}

const typeTagType = (type: string) => {
  const map: Record<string, string> = {
    test: '',
    registration: 'success',
    recharge: 'warning',
    technical: 'primary',
    billing: 'danger',
    feedback: 'info'
  }
  return map[type] || ''
}

const formatTime = (time?: string) => {
  if (!time) return '-'
  return new Date(time).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const isNew = (createdAt: string) => {
  if (!createdAt) return false
  const created = new Date(createdAt)
  const now = new Date()
  return (now.getTime() - created.getTime()) < 24 * 60 * 60 * 1000
}

// 数据
const loading = ref(false)
const tickets = ref<Ticket[]>([])
const dashboard = ref<any>({ pending_count: 0, today_count: 0, total_count: 0, status_stats: {} })
const filters = reactive({
  keyword: '',
  ticket_type: '',
  status: '',
  priority: ''
})
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

// 详情
const detailDrawerVisible = ref(false)
const currentTicket = ref<TicketDetail | null>(null)
const replyContent = ref('')
const isInternalNote = ref(false)
const replySubmitting = ref(false)

// 分配
const assignDialogVisible = ref(false)
const assignAdminId = ref<number | null>(null)
const assignNote = ref('')
const assignSubmitting = ref(false)
const assigningTicket = ref<Ticket | null>(null)
const adminList = ref<any[]>([])

// 解决
const resolveDialogVisible = ref(false)
const resolution = ref('')
const satisfactionScore = ref(5)
const resolveSubmitting = ref(false)
const resolvingTicket = ref<Ticket | null>(null)
const resolveUploadRef = ref()
const resolveFileList = ref<any[]>([])
const resolveUploadFiles = ref<File[]>([])

// 方法
const loadDashboard = async () => {
  try {
    const res: any = await getTicketsDashboard()
    if (res.success) {
      dashboard.value = res.dashboard
    }
  } catch (error) {
    console.error('Failed to load dashboard:', error)
  }
}

const loadTickets = async () => {
  loading.value = true
  try {
    const res: any = await getAdminTickets({
      page: pagination.page,
      page_size: pagination.pageSize,
      keyword: filters.keyword || undefined,
      ticket_type: filters.ticket_type || undefined,
      status: filters.status || undefined,
      priority: filters.priority || undefined
    })
    if (res.success) {
      tickets.value = res.tickets
      pagination.total = res.total
    }
  } catch (error) {
    console.error('Failed to load tickets:', error)
  } finally {
    loading.value = false
  }
}

const loadAdminList = async () => {
  try {
    const res = await request.get('/admin/users')
    if (res.users) {
      adminList.value = res.users.filter((u: any) => u.status === 'active')
    }
  } catch (error) {
    console.error('Failed to load admin list:', error)
  }
}

const resetFilters = () => {
  filters.keyword = ''
  filters.ticket_type = ''
  filters.status = ''
  filters.priority = ''
  pagination.page = 1
  loadTickets()
}

const viewTicket = async (row: Ticket) => {
  try {
    const res: any = await getAdminTicketDetail(row.id)
    if (res.success) {
      currentTicket.value = res.ticket
      replyContent.value = ''
      isInternalNote.value = false
      detailDrawerVisible.value = true
    }
  } catch (error) {
    console.error('Failed to load ticket detail:', error)
    ElMessage.error(t('tickets.loadDetailFailed'))
  }
}

const submitReply = async () => {
  if (!replyContent.value.trim()) {
    ElMessage.warning(t('tickets.pleaseEnterReply'))
    return
  }
  if (!currentTicket.value) return

  replySubmitting.value = true
  try {
    await adminReplyTicket(currentTicket.value.id, {
      content: replyContent.value,
      is_internal: isInternalNote.value
    })
    ElMessage.success(t('tickets.replySuccess'))
    replyContent.value = ''
    const res: any = await getAdminTicketDetail(currentTicket.value.id)
    if (res.success) {
      currentTicket.value = res.ticket
    }
    loadTickets()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('tickets.replyFailed'))
  } finally {
    replySubmitting.value = false
  }
}

const handleAssign = (row: Ticket | TicketDetail) => {
  assigningTicket.value = row as Ticket
  assignAdminId.value = null
  assignNote.value = ''
  assignDialogVisible.value = true
}

const submitAssign = async () => {
  if (!assignAdminId.value || !assigningTicket.value) {
    ElMessage.warning(t('tickets.pleaseSelectAssignee'))
    return
  }

  assignSubmitting.value = true
  try {
    await assignTicket(assigningTicket.value.id, assignAdminId.value)
    ElMessage.success(t('tickets.assignSuccess'))
    assignDialogVisible.value = false
    loadTickets()
    loadDashboard()
    if (currentTicket.value && currentTicket.value.id === assigningTicket.value.id) {
      const res: any = await getAdminTicketDetail(currentTicket.value.id)
      if (res.success) {
        currentTicket.value = res.ticket
      }
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('tickets.assignFailed'))
  } finally {
    assignSubmitting.value = false
  }
}

const onResolveFileChange = (file: any, fileList: any[]) => {
  resolveFileList.value = fileList
  resolveUploadFiles.value = fileList.map((f) => f.raw).filter(Boolean)
}

const onResolveFileRemove = (file: any, fileList: any[]) => {
  resolveFileList.value = fileList
  resolveUploadFiles.value = fileList.map((f) => f.raw).filter(Boolean)
}

const handleResolve = (row: Ticket | TicketDetail) => {
  resolvingTicket.value = row as Ticket
  resolution.value = ''
  satisfactionScore.value = 5
  resolveFileList.value = []
  resolveUploadFiles.value = []
  resolveUploadRef.value?.clearFiles?.()
  resolveDialogVisible.value = true
}

const submitResolve = async () => {
  if (!resolution.value.trim()) {
    ElMessage.warning(t('tickets.pleaseEnterSolution'))
    return
  }
  if (!resolvingTicket.value) return

  resolveSubmitting.value = true
  try {
    await resolveTicket(
      resolvingTicket.value.id,
      resolution.value,
      resolveUploadFiles.value.length ? resolveUploadFiles.value : undefined
    )
    ElMessage.success(t('tickets.ticketResolved'))
    resolveDialogVisible.value = false
    detailDrawerVisible.value = false
    loadTickets()
    loadDashboard()
  } catch (error: any) {
    // 5xx 时拦截器已显示「服务器错误」，此处不再重复
    if (!error.response || error.response.status < 500) {
      ElMessage.error(error.response?.data?.detail || t('tickets.uploadFailed'))
    }
  } finally {
    resolveSubmitting.value = false
  }
}

const handleClose = async (row: Ticket) => {
  try {
    await updateTicketStatus(row.id, 'closed')
    ElMessage.success(t('tickets.ticketClosed'))
    loadTickets()
    loadDashboard()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('tickets.operationFailed'))
  }
}

const handleDelete = async (row: Ticket) => {
  try {
    await ElMessageBox.confirm(
      t('tickets.deleteConfirm', { no: row.ticket_no }),
      t('common.warning'),
      { type: 'warning', confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel') }
    )
  } catch {
    return
  }
  try {
    await deleteAdminTicket(row.id)
    ElMessage.success(t('tickets.deleteSuccess'))
    if (currentTicket.value?.id === row.id) {
      detailDrawerVisible.value = false
      currentTicket.value = null
    }
    loadTickets()
    loadDashboard()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('tickets.deleteFailed'))
  }
}

const changeStatus = async (status: string) => {
  if (!currentTicket.value) return
  try {
    await updateTicketStatus(currentTicket.value.id, status)
    ElMessage.success(t('tickets.statusUpdated'))
    const res: any = await getAdminTicketDetail(currentTicket.value.id)
    if (res.success) {
      currentTicket.value = res.ticket
    }
    loadTickets()
    loadDashboard()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('tickets.operationFailed'))
  }
}

onMounted(() => {
  loadDashboard()
  loadTickets()
  loadAdminList()
})
</script>

<style scoped>
.page-container {
  width: 100%;
  padding: 8px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.header-left {
  flex: 1;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 6px;
}

.page-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 12px;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
}

.stat-card.urgent .stat-icon {
  background: rgba(245, 108, 108, 0.12);
  color: #f56c6c;
}

.stat-card.today .stat-icon {
  background: rgba(102, 126, 234, 0.12);
  color: #667eea;
}

.stat-card.progress .stat-icon {
  background: rgba(230, 162, 60, 0.12);
  color: #e6a23c;
}

.stat-card.resolved .stat-icon {
  background: rgba(103, 194, 58, 0.12);
  color: #67c23a;
}

.stat-card.total .stat-icon {
  background: rgba(144, 147, 153, 0.12);
  color: #909399;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

/* 筛选器 */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

/* 表格 */
.table-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 16px;
}

.ticket-no {
  font-family: monospace;
  font-size: 13px;
  color: var(--primary);
}

.title-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ticket-title {
  font-size: 14px;
  color: var(--text-primary);
}

.new-tag {
  font-size: 10px;
  padding: 0 4px;
}

.priority-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}

.priority-dot.priority-urgent { background: #f56c6c; }
.priority-dot.priority-high { background: #e6a23c; }
.priority-dot.priority-normal { background: #909399; }
.priority-dot.priority-low { background: #c0c4cc; }

.customer-name {
  font-size: 13px;
  color: var(--text-secondary);
}

.assignee-name {
  font-size: 13px;
  color: var(--text-primary);
}

.text-muted {
  color: var(--text-quaternary);
  font-size: 13px;
}

.time-text {
  font-size: 12px;
  color: var(--text-tertiary);
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

/* 工单详情 */
.ticket-detail {
  padding: 0 8px;
}

.detail-section {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  background: var(--bg-input);
  border-radius: 10px;
  padding: 16px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 12px;
  color: var(--text-quaternary);
}

.info-value {
  font-size: 14px;
  color: var(--text-primary);
}

.priority-text {
  font-size: 14px;
  font-weight: 500;
}

.priority-text.priority-urgent { color: #f56c6c; }
.priority-text.priority-high { color: #e6a23c; }
.priority-text.priority-normal { color: #909399; }
.priority-text.priority-low { color: #c0c4cc; }

.description-box {
  background: var(--bg-input);
  border-radius: 10px;
  padding: 16px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
}

.quick-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  padding: 16px;
  background: var(--bg-input);
  border-radius: 10px;
}

/* 时间线 */
.timeline {
  max-height: 400px;
  overflow-y: auto;
}

.timeline-item {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.timeline-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
}

.admin-reply .timeline-avatar {
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: white;
}

.user-reply .timeline-avatar {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.timeline-content {
  flex: 1;
  background: var(--bg-input);
  border-radius: 10px;
  padding: 12px 16px;
}

.admin-reply .timeline-content {
  background: rgba(102, 126, 234, 0.08);
}

.timeline-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.timeline-header .author {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.timeline-header .tags {
  display: flex;
  gap: 4px;
}

.timeline-header .time {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-quaternary);
}

.timeline-body {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
}

.timeline-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.upload-tip {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.no-replies {
  text-align: center;
  padding: 32px;
  color: var(--text-quaternary);
}

.reply-count {
  font-size: 13px;
  color: var(--text-tertiary);
}

/* 回复表单 */
.reply-form {
  background: var(--bg-input);
  border-radius: 10px;
  padding: 16px;
}

.reply-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}

/* 解决方案 */
.resolution-box {
  background: rgba(103, 194, 58, 0.08);
  border-radius: 10px;
  padding: 16px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
}

@media (max-width: 1400px) {
  .stats-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }
  
  .filter-bar > * {
    width: 100% !important;
  }
}
</style>
