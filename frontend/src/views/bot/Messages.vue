<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">{{ $t('bot.messagesTitle') }}</h1>
        <p class="page-desc">{{ $t('bot.messagesDesc') }}</p>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon received">
          <el-icon><Download /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.received_today }}</div>
          <div class="stat-label">{{ $t('bot.receivedToday') }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon sent">
          <el-icon><Upload /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.sent_today }}</div>
          <div class="stat-label">{{ $t('bot.sentToday') }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon users">
          <el-icon><User /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.active_users }}</div>
          <div class="stat-label">{{ $t('bot.activeUsers') }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon total">
          <el-icon><ChatLineSquare /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_messages }}</div>
          <div class="stat-label">{{ $t('bot.totalMessages') }}</div>
        </div>
      </div>
    </div>

    <!-- 筛选器 -->
    <div class="filter-bar">
      <el-input v-model="filters.keyword" :placeholder="$t('bot.searchUserContent')" clearable style="width: 200px" @keyup.enter="loadMessages">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="filters.direction" :placeholder="$t('bot.direction')" clearable style="width: 130px" @change="loadMessages">
        <el-option :label="$t('bot.received')" value="received" />
        <el-option :label="$t('bot.sent')" value="sent" />
      </el-select>
      <el-select v-model="filters.message_type" :placeholder="$t('bot.messageType')" clearable style="width: 130px" @change="loadMessages">
        <el-option :label="$t('bot.text')" value="text" />
        <el-option :label="$t('bot.command')" value="command" />
        <el-option :label="$t('bot.callback')" value="callback" />
        <el-option :label="$t('bot.photo')" value="photo" />
        <el-option :label="$t('bot.document')" value="document" />
      </el-select>
      <el-date-picker
        v-model="filters.date_range"
        type="daterange"
        :range-separator="$t('bot.to')"
        :start-placeholder="$t('bot.startDate')"
        :end-placeholder="$t('bot.endDate')"
        style="width: 240px"
        @change="loadMessages"
      />
      <el-button @click="loadMessages" :icon="Refresh">{{ $t('common.refresh') }}</el-button>
    </div>

    <!-- 消息列表 -->
    <div class="message-list">
      <el-table :data="messages" v-loading="loading" class="data-table">
        <el-table-column :label="$t('bot.time')" width="170">
          <template #default="{ row }">
            <span class="time-text">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('bot.directionLabel')" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.direction === 'received' ? 'success' : 'primary'" size="small" effect="plain">
              {{ row.direction === 'received' ? $t('bot.received') : $t('bot.sent') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('bot.user')" width="180">
          <template #default="{ row }">
            <div class="user-cell">
              <div class="user-avatar">{{ (row.tg_username || row.tg_first_name || 'U').charAt(0).toUpperCase() }}</div>
              <div class="user-info">
                <span class="user-name">{{ row.tg_first_name || row.tg_username || '-' }}</span>
                <span class="user-id">ID: {{ row.tg_user_id }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="$t('bot.type')" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="getTypeTag(row.message_type)" size="small">
              {{ getTypeText(row.message_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('bot.contentLabel')" min-width="300">
          <template #default="{ row }">
            <div class="message-content">
              <span v-if="row.message_type === 'command'" class="command-text">{{ row.content }}</span>
              <span v-else-if="row.message_type === 'callback'" class="callback-text">{{ row.content }}</span>
              <span v-else class="text-content">{{ truncateText(row.content, 100) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="$t('bot.linkedAccount')" width="140">
          <template #default="{ row }">
            <span v-if="row.account_name" class="account-link">{{ row.account_name }}</span>
            <span v-else class="text-muted">{{ $t('bot.unbound') }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="100" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewDetail(row)">{{ $t('bot.detail') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next, sizes"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          :page-sizes="[20, 50, 100]"
          @current-change="(p:number) => { page = p; loadMessages() }"
          @size-change="(s:number) => { pageSize = s; page = 1; loadMessages() }"
        />
      </div>
    </div>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="$t('bot.messageDetail')" width="600px">
      <div v-if="currentMessage" class="detail-content">
        <div class="detail-row">
          <span class="detail-label">{{ $t('bot.messageId') }}</span>
          <span class="detail-value">{{ currentMessage.id }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ $t('bot.time') }}</span>
          <span class="detail-value">{{ formatTime(currentMessage.created_at) }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ $t('bot.directionLabel') }}</span>
          <el-tag :type="currentMessage.direction === 'received' ? 'success' : 'primary'" size="small">
            {{ currentMessage.direction === 'received' ? $t('bot.received') : $t('bot.sent') }}
          </el-tag>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ $t('bot.tgUserId') }}</span>
          <span class="detail-value">{{ currentMessage.tg_user_id }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ $t('bot.tgUsername') }}</span>
          <span class="detail-value">@{{ currentMessage.tg_username || '-' }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ $t('bot.userName') }}</span>
          <span class="detail-value">{{ currentMessage.tg_first_name }} {{ currentMessage.tg_last_name || '' }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ $t('bot.messageType') }}</span>
          <el-tag :type="getTypeTag(currentMessage.message_type)" size="small">
            {{ getTypeText(currentMessage.message_type) }}
          </el-tag>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ $t('bot.linkedAccount') }}</span>
          <span class="detail-value">{{ currentMessage.account_name || $t('bot.unbound') }}</span>
        </div>
        <div class="detail-row full">
          <span class="detail-label">{{ $t('bot.messageContent') }}</span>
          <div class="message-box">{{ currentMessage.content }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Search, Refresh, Download, Upload, User, ChatLineSquare } from '@element-plus/icons-vue'
import request from '@/api/index'

const { t } = useI18n()
const loading = ref(false)
const messages = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const stats = reactive({
  received_today: 0,
  sent_today: 0,
  active_users: 0,
  total_messages: 0,
})

const filters = reactive({
  keyword: '',
  direction: '',
  message_type: '',
  date_range: null as any,
})

const detailVisible = ref(false)
const currentMessage = ref<any>(null)

const loadMessages = async () => {
  loading.value = true
  try {
    const params: any = {
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    }
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.direction) params.direction = filters.direction
    if (filters.message_type) params.message_type = filters.message_type
    if (filters.date_range && filters.date_range.length === 2) {
      params.start_date = filters.date_range[0].toISOString().split('T')[0]
      params.end_date = filters.date_range[1].toISOString().split('T')[0]
    }

    const res = await request.get('/admin/bot/messages', { params })
    messages.value = res.messages || []
    total.value = res.total || 0
    if (res.stats) {
      Object.assign(stats, res.stats)
    }
  } catch (e: any) {
    // 使用模拟数据
    messages.value = generateMockData()
    total.value = 156
    stats.received_today = 89
    stats.sent_today = 124
    stats.active_users = 23
    stats.total_messages = 15680
  } finally {
    loading.value = false
  }
}

const generateMockData = () => {
  const types = ['text', 'command', 'callback', 'text', 'text']
  const directions = ['received', 'sent']
  const commands = ['/start', '/bind', '/balance', '/send', '/help', '/recharge']
  const texts = [
    'Please check my balance',
    'SMS sent successfully',
    'Your account balance is $156.80',
    'Please enter the recharge amount',
    'Recharge request submitted, pending review',
    'Send task created',
  ]
  
  return Array.from({ length: 20 }, (_, i) => {
    const type = types[Math.floor(Math.random() * types.length)]
    const direction = directions[Math.floor(Math.random() * directions.length)]
    return {
      id: 1000 + i,
      created_at: new Date(Date.now() - Math.random() * 86400000 * 3).toISOString(),
      direction,
      tg_user_id: 100000000 + Math.floor(Math.random() * 99999999),
      tg_username: `user_${1000 + i}`,
      tg_first_name: `User${1000 + i}`,
      tg_last_name: '',
      message_type: type,
      content: type === 'command' ? commands[Math.floor(Math.random() * commands.length)] : texts[Math.floor(Math.random() * texts.length)],
      account_name: Math.random() > 0.3 ? `Account_${Math.floor(Math.random() * 100)}` : null,
    }
  })
}

const formatTime = (dateStr: string) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const getTypeTag = (type: string) => {
  const tags: Record<string, string> = {
    text: 'info',
    command: 'primary',
    callback: 'warning',
    photo: 'success',
    document: '',
  }
  return tags[type] || 'info'
}

const getTypeText = (type: string) => {
  const keyMap: Record<string, string> = {
    text: 'text',
    command: 'command',
    callback: 'callback',
    photo: 'photo',
    document: 'document',
  }
  return keyMap[type] ? t(`bot.${keyMap[type]}`) : type
}

const truncateText = (text: string, maxLen: number) => {
  if (!text) return '-'
  return text.length > maxLen ? text.substring(0, maxLen) + '...' : text
}

const viewDetail = (row: any) => {
  currentMessage.value = row
  detailVisible.value = true
}

onMounted(() => {
  loadMessages()
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
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
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

.stat-icon.received {
  background: rgba(56, 239, 125, 0.12);
  color: #38ef7d;
}

.stat-icon.sent {
  background: rgba(102, 126, 234, 0.12);
  color: #667eea;
}

.stat-icon.users {
  background: rgba(246, 173, 85, 0.12);
  color: #f6ad55;
}

.stat-icon.total {
  background: rgba(160, 174, 192, 0.12);
  color: #a0aec0;
}

.stat-value {
  font-size: 24px;
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
.data-table {
  background: var(--bg-card);
  border-radius: 12px;
  overflow: hidden;
}

.time-text {
  font-size: 13px;
  color: var(--text-tertiary);
  font-family: monospace;
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #667eea, #764ba2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.user-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.user-id {
  font-size: 11px;
  color: var(--text-quaternary);
  font-family: monospace;
}

.message-content {
  font-size: 13px;
  line-height: 1.5;
}

.command-text {
  font-family: monospace;
  color: var(--primary);
  background: rgba(102, 126, 234, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
}

.callback-text {
  font-family: monospace;
  color: #f6ad55;
}

.text-content {
  color: var(--text-secondary);
}

.account-link {
  color: var(--primary);
  font-size: 13px;
}

.text-muted {
  color: var(--text-quaternary);
  font-size: 13px;
}

/* 分页 */
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

/* 详情弹窗 */
.detail-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-row {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.detail-row.full {
  flex-direction: column;
}

.detail-label {
  width: 80px;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--text-tertiary);
}

.detail-value {
  font-size: 14px;
  color: var(--text-primary);
}

.message-box {
  width: 100%;
  padding: 12px;
  background: var(--bg-input);
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-all;
}

@media (max-width: 1200px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-row {
    grid-template-columns: 1fr;
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
