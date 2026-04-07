<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">{{ $t('bizAccounts.title') }}</h1>
        <p class="page-desc">{{ $t('bizAccounts.pageDesc') }}</p>
      </div>
    </div>

    <!-- 筛选 -->
    <div class="filter-card">
      <div class="filter-row">
        <el-input
          v-model="filters.keyword"
          :placeholder="$t('bizAccounts.searchPlaceholder')"
          clearable
          style="width: 220px;"
          :prefix-icon="Search"
          @keyup.enter="loadData"
          @clear="loadData"
        />
        <el-select v-model="filters.business_type" :placeholder="$t('bizAccounts.allTypes')" clearable @change="loadData">
          <el-option label="语音 Voice" value="voice" />
          <el-option label="数据 Data" value="data" />
        </el-select>
        <el-select v-model="filters.status" :placeholder="$t('bizAccounts.allStatus')" clearable @change="loadData">
          <el-option :label="$t('common.enable')" value="active" />
          <el-option label="已暂停" value="suspended" />
          <el-option label="已关闭" value="closed" />
        </el-select>
        <el-button type="primary" @click="loadData" :icon="Search">{{ $t('smsRecords.query') }}</el-button>
        <el-button @click="resetFilters">{{ $t('common.reset') }}</el-button>
        <el-button type="warning" :loading="syncing" :icon="Refresh" @click="handleSync">同步OKCC余额</el-button>
      </div>
    </div>

    <!-- 统计 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon blue"><el-icon :size="22"><User /></el-icon></div>
        <div class="stat-info">
          <span class="stat-value">{{ total }}</span>
          <span class="stat-label">{{ $t('bizAccounts.totalAccounts') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon green"><el-icon :size="22"><Headset /></el-icon></div>
        <div class="stat-info">
          <span class="stat-value">{{ voiceCount }}</span>
          <span class="stat-label">{{ $t('bizAccounts.voiceAccounts') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon purple"><el-icon :size="22"><DataLine /></el-icon></div>
        <div class="stat-info">
          <span class="stat-value">{{ dataCount }}</span>
          <span class="stat-label">{{ $t('bizAccounts.dataAccounts') }}</span>
        </div>
      </div>
    </div>

    <!-- 表格 -->
    <div class="table-card">
      <el-table :data="items" v-loading="loading" stripe>
        <el-table-column prop="account_name" :label="$t('bizAccounts.accountName')" min-width="160">
          <template #default="{ row }">
            <span class="account-name">{{ row.account_name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="business_type" :label="$t('bizAccounts.bizType')" width="100">
          <template #default="{ row }">
            <el-tag :type="row.business_type === 'voice' ? 'success' : 'primary'" size="small">
              {{ row.business_type === 'voice' ? '语音' : '数据' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="country_code" :label="$t('bizAccounts.country')" width="100">
          <template #default="{ row }">
            {{ countryLabel(row.country_code) }}
          </template>
        </el-table-column>
        <el-table-column prop="supplier_url" :label="$t('bizAccounts.supplierSystem')" min-width="160">
          <template #default="{ row }">
            <a v-if="row.supplier_url" :href="row.supplier_url" target="_blank" class="link-text">{{ row.supplier_url }}</a>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('bizAccounts.credentialSummary')" min-width="200">
          <template #default="{ row }">
            <template v-if="row.supplier_credentials">
              <div v-if="row.supplier_credentials.client_name" class="cred-line">
                客户名: <code>{{ row.supplier_credentials.client_name }}</code>
              </div>
              <div v-if="row.supplier_credentials.agent_range" class="cred-line">
                坐席: <code>{{ row.supplier_credentials.agent_range }}</code>
              </div>
              <div v-if="row.supplier_credentials.domain" class="cred-line">
                域名: <code>{{ row.supplier_credentials.domain }}</code>
              </div>
              <el-button link type="primary" size="small" @click="showDetail(row)">
                {{ $t('bizAccounts.viewAll') }}
              </el-button>
            </template>
            <span v-else class="text-muted">{{ $t('bizAccounts.noCredentials') }}</span>
          </template>
        </el-table-column>
        <el-table-column label="OKCC余额" width="140">
          <template #default="{ row }">
            <template v-if="row.okcc_balance !== null && row.okcc_balance !== undefined">
              <span :class="['balance-text', row.okcc_balance < 0 ? 'negative' : 'positive']">
                ¥{{ Number(row.okcc_balance).toFixed(2) }}
              </span>
              <div v-if="row.okcc_synced_at" class="sync-time">{{ row.okcc_synced_at }}</div>
            </template>
            <span v-else class="text-muted">未同步</span>
          </template>
        </el-table-column>
        <el-table-column label="资费套餐" min-width="180">
          <template #default="{ row }">
            <template v-if="row.supplier_credentials?.billing_package">
              <span class="pkg-name">{{ row.supplier_credentials.billing_package }}</span>
            </template>
            <template v-else-if="row.unit_price">
              <span>¥{{ row.unit_price?.toFixed(4) }}</span>
            </template>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="sales_name" :label="$t('bizAccounts.sales')" width="100">
          <template #default="{ row }">
            {{ row.sales_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('bizAccounts.status')" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : row.status === 'suspended' ? 'warning' : 'danger'" size="small">
              {{ row.status === 'active' ? '正常' : row.status === 'suspended' ? '暂停' : '关闭' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="$t('bizAccounts.createdAt')" width="160">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.actions')" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="showDetail(row)">{{ $t('bizAccounts.detail') }}</el-button>
            <el-button link type="primary" size="small" @click="showEdit(row)">{{ $t('common.edit') }}</el-button>
            <el-popconfirm :title="$t('bizAccounts.confirmDelete')" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button link type="danger" size="small">{{ $t('common.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadData"
          @size-change="loadData"
        />
      </div>
    </div>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="$t('bizAccounts.detailTitle')" width="680px" destroy-on-close>
      <div v-if="currentAccount" class="detail-content">
        <el-descriptions :column="2" border size="default">
          <el-descriptions-item :label="$t('bizAccounts.accountName')">
            <code class="code-text">{{ currentAccount.account_name }}</code>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('bizAccounts.bizType')">
            <el-tag :type="currentAccount.business_type === 'voice' ? 'success' : 'primary'" size="small">
              {{ currentAccount.business_type === 'voice' ? '语音' : '数据' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('bizAccounts.country')">{{ countryLabel(currentAccount.country_code) }}</el-descriptions-item>
          <el-descriptions-item label="资费套餐">
            {{ currentAccount.supplier_credentials?.billing_package || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('bizAccounts.unitPrice')">¥{{ currentAccount.unit_price?.toFixed(4) }}/分钟</el-descriptions-item>
          <el-descriptions-item :label="$t('bizAccounts.sales')">{{ currentAccount.sales_name || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('bizAccounts.status')">{{ currentAccount.status }}</el-descriptions-item>
          <el-descriptions-item :label="$t('bizAccounts.createdAt')" :span="2">
            {{ currentAccount.created_at ? new Date(currentAccount.created_at).toLocaleString('zh-CN') : '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- 供应商凭据 -->
        <template v-if="currentAccount.supplier_credentials">
          <el-divider content-position="left">{{ $t('bizAccounts.supplierInfo') }}</el-divider>

          <div v-if="currentAccount.supplier_url" class="info-row">
            <span class="info-label">{{ $t('bizAccounts.systemUrl') }}</span>
            <a :href="currentAccount.supplier_url" target="_blank" class="link-text">{{ currentAccount.supplier_url }}</a>
          </div>

          <!-- 分段显示 -->
          <template v-if="currentAccount.supplier_credentials.sections">
            <div v-for="(sec, key) in currentAccount.supplier_credentials.sections" :key="key" class="cred-section">
              <h4 class="section-title">{{ sectionLabel(key) }}</h4>
              <div v-for="(val, field) in sec" :key="field" class="info-row">
                <span class="info-label">{{ field }}</span>
                <code class="code-text">{{ val }}</code>
              </div>
            </div>
          </template>

          <!-- 非分段模式 -->
          <template v-else>
            <div v-for="(val, key) in currentAccount.supplier_credentials" :key="key" class="info-row">
              <template v-if="key !== 'sections' && key !== 'system_url'">
                <span class="info-label">{{ credLabel(key as string) }}</span>
                <code class="code-text">{{ val }}</code>
              </template>
            </div>
          </template>

          <div v-if="currentAccount.supplier_credentials.dial_rule" class="info-row highlight">
            <span class="info-label">{{ $t('bizAccounts.dialRule') }}</span>
            <span>{{ currentAccount.supplier_credentials.dial_rule }}</span>
          </div>
        </template>
        <el-empty v-else :description="$t('bizAccounts.noCredentials')" :image-size="60" />
      </div>
    </el-dialog>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editVisible" :title="$t('bizAccounts.editTitle')" width="500px" destroy-on-close>
      <el-form v-if="editForm" :model="editForm" label-width="100px">
        <el-form-item :label="$t('bizAccounts.accountName')">
          <el-input v-model="editForm.account_name" />
        </el-form-item>
        <el-form-item :label="$t('bizAccounts.status')">
          <el-select v-model="editForm.status" style="width: 100%;">
            <el-option label="正常" value="active" />
            <el-option label="暂停" value="suspended" />
            <el-option label="关闭" value="closed" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('bizAccounts.unitPrice')">
          <el-input-number v-model="editForm.unit_price" :precision="4" :step="0.001" :min="0" style="width: 100%;" />
        </el-form-item>
        <el-form-item :label="$t('bizAccounts.companyName')">
          <el-input v-model="editForm.company_name" />
        </el-form-item>
        <el-form-item :label="$t('bizAccounts.contactPerson')">
          <el-input v-model="editForm.contact_person" />
        </el-form-item>
        <el-form-item :label="$t('bizAccounts.contactPhone')">
          <el-input v-model="editForm.contact_phone" />
        </el-form-item>
        <el-form-item :label="$t('bizAccounts.supplierUrl')">
          <el-input v-model="editForm.supplier_url" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { Search, User, Headset, DataLine, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import {
  getBusinessAccounts,
  updateBusinessAccount,
  deleteBusinessAccount,
  syncOkccBalances,
  type BusinessAccount,
} from '@/api/admin'
import { findCountryByIso, findCountryByDial } from '@/constants/countries'

const { t, locale } = useI18n()

function countryLabel(code: string): string {
  if (!code) return '-'
  const raw = String(code).trim()
  let c = findCountryByIso(raw.toUpperCase())
  if (!c) {
    const dial = raw.replace(/^0+/, '')
    c = findCountryByDial(dial)
  }
  if (!c) return raw
  return locale.value.startsWith('zh') ? c.name : c.en
}

const loading = ref(false)
const saving = ref(false)
const syncing = ref(false)
const items = ref<BusinessAccount[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const filters = ref({
  keyword: '',
  business_type: '',
  status: '',
})

const voiceCount = computed(() => items.value.filter(i => i.business_type === 'voice').length)
const dataCount = computed(() => items.value.filter(i => i.business_type === 'data').length)

const detailVisible = ref(false)
const editVisible = ref(false)
const currentAccount = ref<BusinessAccount | null>(null)
const editForm = ref<any>(null)

async function loadData() {
  loading.value = true
  try {
    const res = await getBusinessAccounts({
      ...filters.value,
      page: page.value,
      page_size: pageSize.value,
    })
    if (res.success) {
      items.value = res.items
      total.value = res.total
    }
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.value = { keyword: '', business_type: '', status: '' }
  page.value = 1
  loadData()
}

function showDetail(row: BusinessAccount) {
  currentAccount.value = row
  detailVisible.value = true
}

function showEdit(row: BusinessAccount) {
  editForm.value = {
    id: row.id,
    account_name: row.account_name,
    status: row.status,
    unit_price: row.unit_price,
    company_name: row.company_name || '',
    contact_person: row.contact_person || '',
    contact_phone: row.contact_phone || '',
    supplier_url: row.supplier_url || '',
  }
  editVisible.value = true
}

async function handleSave() {
  if (!editForm.value) return
  saving.value = true
  try {
    const { id, ...data } = editForm.value
    const res = await updateBusinessAccount(id, data)
    if (res.success) {
      ElMessage.success('保存成功')
      editVisible.value = false
      loadData()
    }
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(id: number) {
  try {
    const res = await deleteBusinessAccount(id)
    if (res.success) {
      ElMessage.success('已删除')
      loadData()
    }
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  }
}

async function handleSync() {
  syncing.value = true
  try {
    const res = await syncOkccBalances()
    if (res.success) {
      ElMessage.success(`同步完成：已更新 ${res.stats?.synced || 0} 个账户余额`)
      loadData()
    }
  } catch (e: any) {
    ElMessage.error(e.message || '同步失败')
  } finally {
    syncing.value = false
  }
}

function sectionLabel(key: string): string {
  const map: Record<string, string> = {
    enterprise_login: '🏢 企业客户登录',
    agent_register: '📞 坐席注册',
    agent_login: '👤 坐席登录',
  }
  return map[key] || key
}

function credLabel(key: string): string {
  const map: Record<string, string> = {
    client_name: '客户名',
    username: '用户名',
    password: '密码',
    agent_range: '坐席号',
    agent_password: '口令',
    domain: '域名',
    dial_rule: '送号规则',
    system_url: '系统地址',
  }
  return map[key] || key
}

onMounted(() => { loadData() })
</script>

<style scoped>
.page-container { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-title { font-size: 22px; font-weight: 600; margin: 0 0 4px; }
.page-desc { color: var(--el-text-color-secondary); font-size: 14px; margin: 0; }

.filter-card { background: var(--el-bg-color); border-radius: 8px; padding: 16px 20px; margin-bottom: 16px; border: 1px solid var(--el-border-color-lighter); }
.filter-row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }

.stats-row { display: flex; gap: 16px; margin-bottom: 16px; }
.stat-card { flex: 1; background: var(--el-bg-color); border-radius: 8px; padding: 16px 20px; display: flex; align-items: center; gap: 14px; border: 1px solid var(--el-border-color-lighter); }
.stat-icon { width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: #fff; }
.stat-icon.blue { background: linear-gradient(135deg, #409eff, #337ecc); }
.stat-icon.green { background: linear-gradient(135deg, #67c23a, #529b2e); }
.stat-icon.purple { background: linear-gradient(135deg, #a855f7, #7c3aed); }
.stat-info { display: flex; flex-direction: column; }
.stat-value { font-size: 22px; font-weight: 700; line-height: 1.2; }
.stat-label { font-size: 13px; color: var(--el-text-color-secondary); }

.table-card { background: var(--el-bg-color); border-radius: 8px; padding: 16px; border: 1px solid var(--el-border-color-lighter); }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 16px; }

.account-name { font-weight: 600; font-family: monospace; }
.link-text { color: var(--el-color-primary); text-decoration: none; }
.link-text:hover { text-decoration: underline; }
.text-muted { color: var(--el-text-color-placeholder); }
.cred-line { font-size: 12px; line-height: 1.6; }
.cred-line code { background: var(--el-fill-color-light); padding: 1px 4px; border-radius: 3px; font-size: 12px; }

.detail-content { max-height: 65vh; overflow-y: auto; }
.cred-section { margin-top: 16px; }
.section-title { font-size: 15px; font-weight: 600; margin: 0 0 8px; padding-bottom: 6px; border-bottom: 1px solid var(--el-border-color-lighter); }
.info-row { display: flex; align-items: center; padding: 6px 0; gap: 12px; }
.info-label { min-width: 80px; color: var(--el-text-color-secondary); font-size: 13px; flex-shrink: 0; }
.info-row.highlight { background: var(--el-color-warning-light-9); border-radius: 6px; padding: 8px 12px; margin-top: 8px; }
.code-text { background: var(--el-fill-color-light); padding: 2px 8px; border-radius: 4px; font-family: monospace; font-size: 13px; user-select: all; }
.balance-text { font-weight: 600; font-family: monospace; font-size: 14px; }
.balance-text.positive { color: var(--el-color-success); }
.balance-text.negative { color: var(--el-color-danger); }
.sync-time { font-size: 11px; color: var(--el-text-color-placeholder); margin-top: 2px; }
.pkg-name { font-size: 13px; color: var(--el-text-color-regular); }
</style>
