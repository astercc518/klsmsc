<template>
  <div class="records-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">{{ $t('smsRecords.title') }}</h1>
        <p class="page-desc">{{ $t('smsRecords.pageDesc') }}</p>
      </div>
      <div class="header-actions">
        <button class="refresh-btn" @click="loadRecords">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M15 9C15 12.3137 12.3137 15 9 15C5.68629 15 3 12.3137 3 9C3 5.68629 5.68629 3 9 3C11.2091 3 13.1274 4.20055 14.1818 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M12 6H15V3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          {{ $t('common.refresh') }}
        </button>
      </div>
    </div>
    
    <!-- 筛选栏 -->
    <div class="filter-card">
      <div class="filter-content">
        <div class="filter-item" v-if="isAdmin">
          <label class="filter-label">{{ $t('smsRecords.customerAccount') }}</label>
          <el-select 
            v-model="searchForm.account_id" 
            :placeholder="$t('smsRecords.allAccounts')" 
            clearable 
            size="large"
            class="filter-select"
          >
            <el-option
              v-for="acc in accounts"
              :key="acc.id"
              :label="`${acc.account_name} (ID: ${acc.id})`"
              :value="acc.id"
            />
          </el-select>
        </div>
        
        <div class="filter-item">
          <label class="filter-label">{{ $t('smsRecords.statusFilter') }}</label>
          <el-select 
            v-model="searchForm.status" 
            :placeholder="$t('smsRecords.allStatus')" 
            clearable 
            size="large"
            class="filter-select"
          >
            <el-option :label="$t('smsStatus.pending')" value="pending">
              <div class="status-option">
                <span class="status-dot pending"></span>
                {{ $t('smsStatus.pending') }}
              </div>
            </el-option>
            <el-option :label="$t('smsStatus.queued')" value="queued">
              <div class="status-option">
                <span class="status-dot queued"></span>
                {{ $t('smsStatus.queued') }}
              </div>
            </el-option>
            <el-option :label="$t('smsStatus.sent')" value="sent">
              <div class="status-option">
                <span class="status-dot sent"></span>
                {{ $t('smsStatus.sent') }}
              </div>
            </el-option>
            <el-option :label="$t('smsStatus.delivered')" value="delivered">
              <div class="status-option">
                <span class="status-dot delivered"></span>
                {{ $t('smsStatus.delivered') }}
              </div>
            </el-option>
            <el-option :label="$t('smsStatus.failed')" value="failed">
              <div class="status-option">
                <span class="status-dot failed"></span>
                {{ $t('smsStatus.failed') }}
              </div>
            </el-option>
          </el-select>
        </div>
        
        <div class="filter-actions">
          <button class="filter-btn search" @click="handleSearch">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.5"/>
              <path d="M11 11L14 14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            {{ $t('smsRecords.query') }}
          </button>
          <button class="filter-btn reset" @click="handleReset">
            {{ $t('common.reset') }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- 数据表格 -->
    <div class="table-card">
      <div class="table-wrapper" v-loading="loading">
        <table class="data-table" v-if="records.length > 0">
          <thead>
            <tr>
              <th v-if="isAdmin">{{ $t('smsRecords.accountId') }}</th>
              <th>{{ $t('smsRecords.messageId') }}</th>
              <th>{{ $t('smsRecords.phoneNumber') }}</th>
              <th>{{ $t('smsRecords.country') }}</th>
              <th>{{ $t('smsRecords.content') }}</th>
              <th>{{ $t('smsRecords.status') }}</th>
              <th>{{ $t('smsRecords.cost') }}</th>
              <th>{{ $t('smsRecords.submitTime') }}</th>
              <th>{{ $t('common.action') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in records" :key="record.message_id">
              <td v-if="isAdmin">
                <span class="account-id">{{ record.account_id }}</span>
              </td>
              <td>
                <span class="message-id">{{ record.message_id?.substring(0, 8) }}...</span>
              </td>
              <td>
                <span class="phone-number">{{ record.phone_number }}</span>
              </td>
              <td>
                <span class="country">{{ record.country_name || '-' }}</span>
              </td>
              <td class="message-cell">
                <span class="message-preview">{{ record.message?.substring(0, 30) }}{{ record.message?.length > 30 ? '...' : '' }}</span>
              </td>
              <td>
                <span class="status-badge" :class="record.status">
                  {{ getStatusText(record.status) }}
                </span>
              </td>
              <td>
                <span class="cost">{{ record.total_cost }} {{ record.currency }}</span>
              </td>
              <td>
                <span class="time">{{ record.submit_time }}</span>
              </td>
              <td>
                <button class="detail-btn" @click="handleViewDetail(record)">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.5"/>
                    <path d="M1 8C2.5 4.5 5 2.5 8 2.5C11 2.5 13.5 4.5 15 8C13.5 11.5 11 13.5 8 13.5C5 13.5 2.5 11.5 1 8Z" stroke="currentColor" stroke-width="1.5"/>
                  </svg>
                  {{ $t('common.detail') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        
        <!-- 空状态 -->
        <div class="empty-state" v-if="!loading && records.length === 0">
          <div class="empty-icon">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <rect x="8" y="6" width="32" height="36" rx="4" stroke="currentColor" stroke-width="2"/>
              <path d="M16 16H32M16 24H28M16 32H24" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </div>
          <h3 class="empty-title">{{ $t('smsRecords.noRecords') }}</h3>
          <p class="empty-desc">{{ $t('smsRecords.noRecordsDesc') }}</p>
          <button class="empty-action" @click="$router.push('/sms/send')">
            {{ $t('smsSend.sendNow') }}
          </button>
        </div>
      </div>
      
      <!-- 分页 -->
      <div class="pagination-wrapper" v-if="records.length > 0">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadRecords"
          @current-change="loadRecords"
        />
      </div>
    </div>
    
    <!-- 详情对话框 -->
    <el-dialog 
      v-model="detailVisible" 
      :title="$t('smsRecords.smsDetail')" 
      width="560px"
      class="detail-dialog"
    >
      <div class="detail-content" v-if="currentRecord">
        <div class="detail-section">
          <h4 class="detail-section-title">{{ $t('smsRecords.basicInfo') }}</h4>
          <div class="detail-grid">
            <div class="detail-item">
              <span class="detail-label">{{ $t('smsRecords.messageId') }}</span>
              <span class="detail-value mono">{{ currentRecord.message_id }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">{{ $t('smsRecords.phoneNumber') }}</span>
              <span class="detail-value">{{ currentRecord.phone_number }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">{{ $t('smsRecords.country') }}</span>
              <span class="detail-value">{{ currentRecord.country_name || '-' }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">{{ $t('smsRecords.carrier') }}</span>
              <span class="detail-value">{{ currentRecord.operator || '-' }}</span>
            </div>
          </div>
        </div>
        
        <div class="detail-section">
          <h4 class="detail-section-title">{{ $t('smsRecords.smsContent') }}</h4>
          <div class="message-box">
            {{ currentRecord.message }}
          </div>
        </div>
        
        <div class="detail-section">
          <h4 class="detail-section-title">{{ $t('smsRecords.sendStatus') }}</h4>
          <div class="detail-grid">
            <div class="detail-item">
              <span class="detail-label">{{ $t('smsRecords.status') }}</span>
              <span class="status-badge" :class="currentRecord.status">
                {{ getStatusText(currentRecord.status) }}
              </span>
            </div>
            <div class="detail-item">
              <span class="detail-label">{{ $t('smsRecords.senderId') }}</span>
              <span class="detail-value">{{ currentRecord.sender_id || '-' }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">{{ $t('smsRecords.parts') }}</span>
              <span class="detail-value">{{ currentRecord.message_count || 1 }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">{{ $t('smsRecords.cost') }}</span>
              <span class="detail-value highlight">{{ currentRecord.total_cost }} {{ currentRecord.currency }}</span>
            </div>
          </div>
        </div>
        
        <div class="detail-section">
          <h4 class="detail-section-title">{{ $t('smsRecords.timeInfo') }}</h4>
          <div class="detail-grid">
            <div class="detail-item">
              <span class="detail-label">{{ $t('smsRecords.submitTime') }}</span>
              <span class="detail-value">{{ currentRecord.submit_time }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">{{ $t('smsRecords.sentTime') }}</span>
              <span class="detail-value">{{ currentRecord.sent_time || '-' }}</span>
            </div>
            <div class="detail-item" v-if="currentRecord.delivery_time">
              <span class="detail-label">{{ $t('smsRecords.deliveryTime') }}</span>
              <span class="detail-value">{{ currentRecord.delivery_time }}</span>
            </div>
          </div>
        </div>
        
        <div class="detail-section" v-if="currentRecord.error_message">
          <h4 class="detail-section-title error">{{ $t('smsRecords.errorMsg') }}</h4>
          <div class="error-box">
            {{ currentRecord.error_message }}
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { getSMSRecords } from '@/api/sms'
import { getAccountsAdmin } from '@/api/admin'

const { t } = useI18n()
const loading = ref(false)
const detailVisible = ref(false)
const currentRecord = ref<any>(null)

const isAdmin = computed(() => {
  // 模拟登录模式下不是管理员
  if (sessionStorage.getItem('impersonate_mode') === '1') {
    return false
  }
  return !!localStorage.getItem('admin_token')
})

const accounts = ref<any[]>([])

const searchForm = ref({
  message_id: '',
  phone_number: '',
  status: '',
  account_id: null as number | null,
})

const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0,
})

const records = ref<any[]>([])

const loadAccounts = async () => {
  if (!isAdmin.value) return
  try {
    const res: any = await getAccountsAdmin({ page: 1, page_size: 100 })
    if (res?.success || res?.accounts) {
      accounts.value = res.accounts || []
    }
  } catch (error) {
    console.error('Failed to load accounts:', error)
  }
}

const loadRecords = async () => {
  loading.value = true
  try {
    const params: any = {
      page: pagination.value.page,
      page_size: pagination.value.pageSize,
    }
    
    if (searchForm.value.status) {
      params.status = searchForm.value.status
    }
    
    if (isAdmin.value && searchForm.value.account_id) {
      params.account_id = searchForm.value.account_id
    }
    
    const res: any = await getSMSRecords(params)
    
    if (res?.success) {
      records.value = (res.records || []).map((r: any) => ({
        ...r,
        total_cost: r.cost || 0,
        country_name: r.country_code || '-',
      }))
      pagination.value.total = res.total || 0
    } else {
      records.value = []
      pagination.value.total = 0
    }
  } catch (error: any) {
    console.error('Failed to load send records:', error)
    ElMessage.error(t('common.failed') + ': ' + (error.message || t('common.error')))
    records.value = []
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.value.page = 1
  loadRecords()
}

const handleReset = () => {
  searchForm.value = {
    message_id: '',
    phone_number: '',
    status: '',
    account_id: null,
  }
  handleSearch()
}

const handleViewDetail = (row: any) => {
  currentRecord.value = row
  detailVisible.value = true
}

const getStatusText = (status: string) => {
  const statusKeys: Record<string, string> = {
    pending: 'smsStatus.pending',
    queued: 'smsStatus.queued',
    sent: 'smsStatus.sent',
    delivered: 'smsStatus.delivered',
    failed: 'smsStatus.failed',
  }
  return statusKeys[status] ? t(statusKeys[status]) : status
}

onMounted(() => {
  loadAccounts()
  loadRecords()
})
</script>

<style scoped>
.records-page {
  width: 100%;
  animation: fadeIn 0.5s var(--ease-default);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ========== 页面头部 ========== */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
  letter-spacing: -0.02em;
}

.page-desc {
  font-size: 15px;
  color: var(--text-tertiary);
  margin: 0;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: var(--bg-input);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s var(--ease-default);
}

.refresh-btn:hover {
  background: var(--bg-hover);
  border-color: var(--border-hover);
  color: var(--text-primary);
}

/* ========== 筛选栏 ========== */
.filter-card {
  background: var(--bg-card);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid var(--border-default);
  border-radius: 20px;
  padding: 20px 24px;
  margin-bottom: 24px;
}

.filter-content {
  display: flex;
  gap: 20px;
  align-items: flex-end;
  flex-wrap: wrap;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 200px;
}

.filter-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-quaternary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

:deep(.filter-select .el-input__wrapper) {
  background: var(--bg-input) !important;
  border: 1px solid var(--border-default) !important;
  border-radius: 12px !important;
}

.status-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-dot.pending { background: var(--info); }
.status-dot.queued { background: var(--warning); }
.status-dot.sent { background: var(--primary); }
.status-dot.delivered { background: var(--success); }
.status-dot.failed { background: var(--danger); }

.filter-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.filter-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.filter-btn.search {
  background: linear-gradient(135deg, #2997FF 0%, #0071E3 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(41, 151, 255, 0.3);
}

.filter-btn.search:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(41, 151, 255, 0.4);
}

.filter-btn.reset {
  background: var(--bg-input);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.filter-btn.reset:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* ========== 数据表格 ========== */
.table-card {
  background: var(--bg-card);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid var(--border-default);
  border-radius: 20px;
  overflow: hidden;
}

.table-wrapper {
  padding: 0;
  min-height: 400px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th {
  padding: 16px 20px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-quaternary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  background: var(--bg-input);
  border-bottom: 1px solid var(--border-default);
}

.data-table td {
  padding: 16px 20px;
  font-size: 14px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.15s;
}

.data-table tr:hover td {
  background: rgba(41, 151, 255, 0.04);
}

.data-table tr:last-child td {
  border-bottom: none;
}

.message-id {
  font-family: 'SF Mono', Monaco, monospace;
  font-size: 12px;
  color: var(--text-tertiary);
  background: rgba(255, 255, 255, 0.04);
  padding: 4px 8px;
  border-radius: 6px;
}

.phone-number {
  font-weight: 500;
  color: var(--text-primary);
}

.message-cell {
  max-width: 200px;
}

.message-preview {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-tertiary);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.status-badge.pending { background: rgba(100, 210, 255, 0.15); color: var(--info); }
.status-badge.queued { background: rgba(255, 159, 10, 0.15); color: var(--warning); }
.status-badge.sent { background: rgba(41, 151, 255, 0.15); color: var(--primary); }
.status-badge.delivered { background: rgba(50, 215, 75, 0.15); color: var(--success); }
.status-badge.failed { background: rgba(255, 69, 58, 0.15); color: var(--danger); }

.cost {
  font-weight: 500;
  color: var(--text-primary);
}

.time {
  font-size: 13px;
  color: var(--text-tertiary);
}

.detail-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.detail-btn:hover {
  background: rgba(41, 151, 255, 0.1);
  border-color: var(--primary);
  color: var(--primary);
}

/* ========== 空状态 ========== */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
}

.empty-icon {
  color: var(--text-quaternary);
  margin-bottom: 20px;
}

.empty-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 8px;
}

.empty-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0 0 24px;
}

.empty-action {
  padding: 12px 24px;
  background: linear-gradient(135deg, #2997FF 0%, #0071E3 100%);
  border: none;
  border-radius: 12px;
  color: white;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.empty-action:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(41, 151, 255, 0.35);
}

/* ========== 分页 ========== */
.pagination-wrapper {
  padding: 20px 24px;
  border-top: 1px solid var(--border-subtle);
  display: flex;
  justify-content: flex-end;
}

/* ========== 详情对话框 ========== */
.detail-content {
  padding: 0;
}

.detail-section {
  margin-bottom: 24px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.detail-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 16px;
}

.detail-section-title.error {
  color: var(--danger);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-size: 12px;
  color: var(--text-quaternary);
}

.detail-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.detail-value.mono {
  font-family: 'SF Mono', Monaco, monospace;
  font-size: 12px;
  word-break: break-all;
}

.detail-value.highlight {
  color: var(--primary);
  font-weight: 600;
}

.message-box {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 16px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.error-box {
  background: rgba(255, 69, 58, 0.1);
  border: 1px solid rgba(255, 69, 58, 0.2);
  border-radius: 12px;
  padding: 16px;
  font-size: 14px;
  color: var(--danger);
}

/* ========== 响应式 ========== */
@media (max-width: 1024px) {
  .filter-content {
    flex-direction: column;
    align-items: stretch;
  }
  
  .filter-item {
    min-width: auto;
  }
  
  .filter-actions {
    margin-left: 0;
    margin-top: 8px;
  }
  
  .data-table {
    display: block;
    overflow-x: auto;
  }
}

@media (max-width: 640px) {
  .page-header {
    flex-direction: column;
    gap: 16px;
    align-items: flex-start;
  }
  
  .detail-grid {
    grid-template-columns: 1fr;
  }
}

/* ========== 亮色主题 - Apple Style ========== */
[data-theme="light"] .filter-card {
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 0.5px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

[data-theme="light"] .table-card {
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 0.5px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

[data-theme="light"] .data-table th {
  background: var(--bg-input);
}

[data-theme="light"] .data-table tr:hover td {
  background: rgba(0, 122, 255, 0.04);
}

[data-theme="light"] .filter-btn.search {
  background: var(--gradient-primary);
  box-shadow: 0 4px 12px rgba(0, 122, 255, 0.3);
}

[data-theme="light"] .filter-btn.search:hover {
  box-shadow: 0 6px 16px rgba(0, 122, 255, 0.4);
}
</style>
