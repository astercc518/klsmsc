<template>
  <div class="notifications">
    <el-card class="stats-card">
      <div class="stats-grid">
        <div class="stat-item">
          <div class="stat-value">{{ stats.total_notifications }}</div>
          <div class="stat-label">{{ $t('notifications.total') }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-value" style="color: #f56c6c">{{ stats.unread_notifications }}</div>
          <div class="stat-label">{{ $t('notifications.unread') }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-value" style="color: #409eff">{{ stats.today_notifications }}</div>
          <div class="stat-label">{{ $t('notifications.today') }}</div>
        </div>
        <div class="stat-item">
          <el-button type="primary" @click="markAllAsRead" :disabled="stats.unread_notifications === 0">
            {{ $t('notifications.markAllRead') }}
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card class="main-card">
      <template #header>
        <div class="card-header">
          <span>{{ $t('notifications.list') }}</span>
          <el-radio-group v-model="filterType" @change="loadNotifications">
            <el-radio-button label="">{{ $t('systemConfig.all') }}</el-radio-button>
            <el-radio-button label="false">{{ $t('notifications.unread') }}</el-radio-button>
            <el-radio-button label="true">{{ $t('notifications.read') }}</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <div v-loading="loading" class="notification-list">
        <div 
          v-for="item in notifications" 
          :key="item.id"
          class="notification-item"
          :class="{ unread: !item.is_read, [`priority-${item.priority}`]: true }"
        >
          <div class="notification-header">
            <div class="title-row">
              <span v-if="!item.is_read" class="unread-dot"></span>
              <span class="title">{{ item.title }}</span>
              <el-tag 
                v-if="item.priority === 'urgent'" 
                type="danger" 
                size="small"
                effect="dark"
              >
                {{ $t('notifications.urgent') }}
              </el-tag>
              <el-tag 
                v-else-if="item.priority === 'high'" 
                type="warning" 
                size="small"
              >
                {{ $t('notifications.important') }}
              </el-tag>
            </div>
            <div class="time">{{ formatDateTime(item.created_at) }}</div>
          </div>
          <div class="notification-content">{{ item.content }}</div>
          <div class="notification-actions">
            <el-button 
              v-if="!item.is_read" 
              link 
              type="primary" 
              size="small" 
              @click="markAsRead(item.id)"
            >
              {{ $t('notifications.markRead') }}
            </el-button>
            <el-button 
              v-if="item.action_url" 
              link 
              type="primary" 
              size="small"
            >
              {{ $t('notifications.viewDetails') }}
            </el-button>
            <el-button 
              link 
              type="danger" 
              size="small" 
              @click="deleteNotification(item.id)"
            >
              {{ $t('common.delete') }}
            </el-button>
          </div>
        </div>

        <el-empty v-if="notifications.length === 0 && !loading" :description="$t('notifications.noNotifications')" />
      </div>

      <el-pagination
        v-if="notifications.length > 0"
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="pagination.total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @current-change="loadNotifications"
        @size-change="loadNotifications"
        style="margin-top: 20px; text-align: right"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { notificationApi } from '@/api/notification'

const { t } = useI18n()
const loading = ref(false)
const filterType = ref('')

const stats = reactive({
  total_notifications: 0,
  unread_notifications: 0,
  today_notifications: 0
})

const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0,
  unread_count: 0
})

const notifications = ref<any[]>([])

const formatDateTime = (dateStr: string) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  
  // 1分钟内
  if (diff < 60000) return t('notifications.justNow')
  // 1小时内
  if (diff < 3600000) return t('notifications.minutesAgo', { count: Math.floor(diff / 60000) })
  // 1天内
  if (diff < 86400000) return t('notifications.hoursAgo', { count: Math.floor(diff / 3600000) })
  // 7天内
  if (diff < 604800000) return t('notifications.daysAgo', { count: Math.floor(diff / 86400000) })
  
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const loadStats = async () => {
  try {
    const res = await notificationApi.getStats()
    Object.assign(stats, res.data)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('notifications.loadStatsFailed'))
  }
}

const loadNotifications = async () => {
  loading.value = true
  try {
    const res = await notificationApi.list({
      page: pagination.page,
      page_size: pagination.page_size,
      is_read: filterType.value === '' ? undefined : filterType.value === 'true'
    })
    notifications.value = res.data.items
    pagination.total = res.data.total
    pagination.unread_count = res.data.unread_count
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('notifications.loadNotificationsFailed'))
  } finally {
    loading.value = false
  }
}

const markAsRead = async (id: number) => {
  try {
    await notificationApi.markRead(id)
    loadNotifications()
    loadStats()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.operationFailed'))
  }
}

const markAllAsRead = async () => {
  try {
    await notificationApi.markAllRead()
    ElMessage.success(t('notifications.allMarkedRead'))
    loadNotifications()
    loadStats()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.operationFailed'))
  }
}

const deleteNotification = async (id: number) => {
  try {
    await ElMessageBox.confirm(t('notifications.confirmDelete'), t('common.tip'), {
      type: 'warning'
    })
    await notificationApi.delete(id)
    ElMessage.success(t('common.deleteSuccess'))
    loadNotifications()
    loadStats()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || t('common.deleteFailed'))
    }
  }
}

onMounted(() => {
  loadStats()
  loadNotifications()
})
</script>

<style scoped>
.notifications {
  width: 100%;
}

.stats-card {
  margin-bottom: 20px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  align-items: center;
}

.stat-item {
  text-align: center;
}

.stat-value {
  font-size: 32px;
  font-weight: bold;
  color: #303133;
}

.stat-label {
  margin-top: 8px;
  font-size: 14px;
  color: #909399;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.notification-list {
  min-height: 400px;
}

.notification-item {
  padding: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  transition: background-color 0.2s;
}

.notification-item:hover {
  background-color: var(--el-fill-color-light);
}

.notification-item.unread {
  background-color: var(--el-color-primary-light-9);
}

.notification-item:last-child {
  border-bottom: none;
}

.notification-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.unread-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  background-color: var(--el-color-danger);
  border-radius: 50%;
}

.title {
  font-size: 16px;
  font-weight: bold;
  color: var(--el-text-color-primary);
}

.time {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.notification-content {
  color: var(--el-text-color-regular);
  line-height: 1.6;
  margin-bottom: 10px;
}

.notification-actions {
  display: flex;
  gap: 10px;
}
</style>
