<template>
  <div class="security">
    <el-card class="stats-card">
      <div class="stats-grid">
        <div class="stat-item">
          <div class="stat-value">{{ stats.total_events }}</div>
          <div class="stat-label">{{ $t('security.totalEvents') }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-value" style="color: #409eff">{{ stats.login_attempts_today }}</div>
          <div class="stat-label">{{ $t('security.loginToday') }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-value" style="color: #f56c6c">{{ stats.failed_logins_today }}</div>
          <div class="stat-label">{{ $t('security.failedLogins') }}</div>
        </div>
        <div class="stat-item">
          <div class="stat-value" style="color: #e6a23c">{{ stats.suspicious_activities }}</div>
          <div class="stat-label">{{ $t('security.suspiciousActivity') }}</div>
        </div>
      </div>
    </el-card>

    <el-tabs v-model="activeTab">
      <el-tab-pane :label="$t('security.securityLogs')" name="logs">
        <el-card>
          <el-form :inline="true" :model="searchForm" class="search-form">
            <el-form-item :label="$t('security.eventType')">
              <el-select v-model="searchForm.event_type" :placeholder="$t('systemConfig.all')" clearable @change="loadLogs">
                <el-option :label="$t('security.login')" value="login" />
                <el-option :label="$t('security.loginFailed')" value="login_failed" />
                <el-option :label="$t('security.passwordChange')" value="password_change" />
                <el-option :label="$t('security.apiKeyOps')" value="api_key_create" />
                <el-option :label="$t('security.suspicious')" value="suspicious_activity" />
                <el-option :label="$t('security.rateLimited')" value="rate_limit_exceeded" />
              </el-select>
            </el-form-item>
            <el-form-item :label="$t('security.securityLevel')">
              <el-select v-model="searchForm.level" :placeholder="$t('systemConfig.all')" clearable @change="loadLogs">
                <el-option :label="$t('security.info')" value="info" />
                <el-option :label="$t('security.warning')" value="warning" />
                <el-option :label="$t('security.danger')" value="danger" />
                <el-option :label="$t('security.critical')" value="critical" />
              </el-select>
            </el-form-item>
          </el-form>

          <el-table :data="logs" v-loading="loadingLogs" style="width: 100%">
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column :label="$t('security.eventType')" width="140">
              <template #default="{ row }">
                <el-tag :type="getEventTypeTagType(row.event_type)" size="small">
                  {{ getEventTypeLabel(row.event_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="$t('security.securityLevel')" width="100">
              <template #default="{ row }">
                <el-tag :type="getLevelTagType(row.level)" size="small">
                  {{ getLevelLabel(row.level) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="ip_address" :label="$t('security.ipAddress')" width="140" />
            <el-table-column :label="$t('security.details')" min-width="200">
              <template #default="{ row }">
                <span v-if="row.details">{{ JSON.stringify(row.details) }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.time')" width="180">
              <template #default="{ row }">
                {{ formatDateTime(row.created_at) }}
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="logPagination.page"
            v-model:page-size="logPagination.page_size"
            :total="logPagination.total"
            :page-sizes="[10, 20, 50]"
            layout="total, sizes, prev, pager, next"
            @current-change="loadLogs"
            @size-change="loadLogs"
            style="margin-top: 20px; text-align: right"
          />
        </el-card>
      </el-tab-pane>

      <el-tab-pane :label="$t('security.loginRecords')" name="login">
        <el-card>
          <el-form :inline="true" class="search-form">
            <el-form-item :label="$t('common.status')">
              <el-select v-model="loginSuccess" :placeholder="$t('systemConfig.all')" clearable @change="loadLoginAttempts">
                <el-option :label="$t('security.success')" :value="true" />
                <el-option :label="$t('security.failed')" :value="false" />
              </el-select>
            </el-form-item>
          </el-form>

          <el-table :data="loginAttempts" v-loading="loadingAttempts" style="width: 100%">
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="username" :label="$t('security.username')" width="140" />
            <el-table-column prop="ip_address" :label="$t('security.ipAddress')" width="140" />
            <el-table-column :label="$t('security.result')" width="100">
              <template #default="{ row }">
                <el-tag v-if="row.success" type="success">{{ $t('security.success') }}</el-tag>
                <el-tag v-else type="danger">{{ $t('security.failed') }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="$t('security.failureReason')" min-width="200">
              <template #default="{ row }">
                {{ row.failure_reason || '-' }}
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.time')" width="180">
              <template #default="{ row }">
                {{ formatDateTime(row.created_at) }}
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="attemptPagination.page"
            v-model:page-size="attemptPagination.page_size"
            :total="attemptPagination.total"
            :page-sizes="[10, 20, 50]"
            layout="total, sizes, prev, pager, next"
            @current-change="loadLoginAttempts"
            @size-change="loadLoginAttempts"
            style="margin-top: 20px; text-align: right"
          />
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { securityLogApi } from '@/api/securityLog'

const { t } = useI18n()
const activeTab = ref('logs')
const loadingLogs = ref(false)
const loadingAttempts = ref(false)
const loginSuccess = ref<boolean | undefined>(undefined)

const stats = reactive({
  total_events: 0,
  login_attempts_today: 0,
  failed_logins_today: 0,
  suspicious_activities: 0,
  rate_limit_exceeded: 0
})

const searchForm = reactive({
  event_type: '',
  level: ''
})

const logPagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
})

const attemptPagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
})

const logs = ref<any[]>([])
const loginAttempts = ref<any[]>([])

const formatDateTime = (dateStr: string) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const getEventTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    login: t('security.eventLogin'),
    login_failed: t('security.eventLoginFailed'),
    logout: t('security.eventLogout'),
    password_change: t('security.eventPasswordChange'),
    api_key_create: t('security.eventApiKeyCreate'),
    api_key_delete: t('security.eventApiKeyDelete'),
    permission_change: t('security.eventPermissionChange'),
    suspicious_activity: t('security.eventSuspicious'),
    rate_limit_exceeded: t('security.eventRateLimited')
  }
  return labels[type] || type
}

const getEventTypeTagType = (type: string) => {
  if (type.includes('failed') || type === 'suspicious_activity') return 'danger'
  if (type === 'rate_limit_exceeded') return 'warning'
  return 'info'
}

const getLevelLabel = (level: string) => {
  const labels: Record<string, string> = {
    info: t('security.levelInfo'),
    warning: t('security.levelWarning'),
    danger: t('security.levelDanger'),
    critical: t('security.levelCritical')
  }
  return labels[level] || level
}

const getLevelTagType = (level: string) => {
  const types: Record<string, string> = {
    info: 'info',
    warning: 'warning',
    danger: 'danger',
    critical: 'danger'
  }
  return types[level] || 'info'
}

const loadStats = async () => {
  try {
    const res = await securityLogApi.getStats()
    Object.assign(stats, res.data)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('security.loadStatsFailed'))
  }
}

const loadLogs = async () => {
  loadingLogs.value = true
  try {
    const res = await securityLogApi.list({
      page: logPagination.page,
      page_size: logPagination.page_size,
      event_type: searchForm.event_type || undefined,
      level: searchForm.level || undefined
    })
    logs.value = res.data.items
    logPagination.total = res.data.total
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('security.loadLogsFailed'))
  } finally {
    loadingLogs.value = false
  }
}

const loadLoginAttempts = async () => {
  loadingAttempts.value = true
  try {
    const res = await securityLogApi.getLoginAttempts({
      page: attemptPagination.page,
      page_size: attemptPagination.page_size,
      success: loginSuccess.value
    })
    loginAttempts.value = res.data
    // Note: API返回的是数组，没有total，这里需要处理
    attemptPagination.total = res.data.length
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('security.loadLoginRecordsFailed'))
  } finally {
    loadingAttempts.value = false
  }
}

watch(activeTab, (newTab) => {
  if (newTab === 'logs') {
    loadLogs()
  } else if (newTab === 'login') {
    loadLoginAttempts()
  }
})

onMounted(() => {
  loadStats()
  loadLogs()
})
</script>

<style scoped>
.security {
  width: 100%;
}

.stats-card {
  margin-bottom: 20px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
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

.search-form {
  margin-bottom: 20px;
}
</style>
