<template>
  <div class="accounts-page">
    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="5">
        <el-card shadow="never" class="stat-card">
          <el-statistic title="总账户数" :value="stats.total" />
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="never" class="stat-card">
          <el-statistic title="活跃账户" :value="stats.active" value-style="color:#67C23A" />
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="never" class="stat-card">
          <div class="stat-custom">
            <span class="stat-val" style="color:#409EFF">${{ stats.total_balance.toFixed(2) }}</span>
            <span class="stat-lbl">总余额</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="never" class="stat-card">
          <div class="stat-custom">
            <span class="stat-val" style="color:#E6A23C">${{ stats.total_spent.toFixed(2) }}</span>
            <span class="stat-lbl">总消费</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <el-statistic title="总提取量" :value="stats.total_extracted" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <el-row :gutter="12" align="middle">
        <el-col :span="4">
          <el-select v-model="filters.status" placeholder="全部状态" clearable style="width:100%">
            <el-option value="active" label="活跃" />
            <el-option value="suspended" label="暂停" />
            <el-option value="closed" label="关闭" />
          </el-select>
        </el-col>
        <el-col :span="5">
          <el-input v-model="filters.search" placeholder="搜索账户名/邮箱" clearable @keyup.enter="loadData" />
        </el-col>
        <el-col :span="12">
          <el-button type="primary" @click="loadData">查询</el-button>
          <el-button type="success" :icon="Plus" @click="openCreateDialog">新建数据账户</el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 数据表格 -->
    <el-card shadow="never">
      <el-table :data="accounts" v-loading="loading" stripe border style="width:100%">
        <el-table-column prop="id" label="ID" width="60" sortable />
        <el-table-column label="关联账户" min-width="180">
          <template #default="{ row }">
            <div style="font-weight:600">{{ row.account_name || '-' }}</div>
            <div style="font-size:12px;color:var(--el-text-color-secondary)">{{ row.account_email || '' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="国家" width="100">
          <template #default="{ row }">{{ countryName(row.country_code) }}</template>
        </el-table-column>
        <el-table-column label="余额" width="120" sortable :sort-by="(r: any) => r.balance">
          <template #default="{ row }">
            <span style="font-weight:600;color:#409EFF">${{ (row.balance || 0).toFixed(2) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="总提取" width="90" prop="total_extracted" sortable />
        <el-table-column label="总消费" width="110" sortable :sort-by="(r: any) => r.total_spent">
          <template #default="{ row }">
            <span style="color:#E6A23C">${{ row.total_spent.toFixed(2) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="备注" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.remarks || '-' }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'active'" size="small" type="warning" link @click="handleLogin(row)">登录</el-button>
            <el-button v-if="row.status !== 'closed'" size="small" type="success" link @click="openRechargeDialog(row)">充值</el-button>
            <el-button size="small" type="primary" link @click="openEditDialog(row)">编辑</el-button>
            <el-button size="small" link @click="viewLogs(row)">记录</el-button>
            <el-button v-if="row.status !== 'closed'" size="small" type="warning" link @click="handleClose(row)">关闭</el-button>
            <el-button v-if="row.status === 'closed'" size="small" type="danger" link @click="handleForceDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="display:flex;justify-content:flex-end;margin-top:16px">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </el-card>

    <!-- 新建弹窗 -->
    <el-dialog v-model="createVisible" title="新建数据账户" width="520px" :close-on-click-modal="false">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="关联账户" required>
          <el-select
            v-model="createForm.account_id"
            filterable remote reserve-keyword
            :remote-method="searchAccounts"
            :loading="acctSearchLoading"
            placeholder="搜索账户名或邮箱"
            style="width:100%"
          >
            <el-option
              v-for="a in availableAccounts"
              :key="a.id"
              :value="a.id"
              :label="a.account_name"
              :disabled="a.has_data_account"
            >
              <span>{{ a.account_name }}</span>
              <span style="float:right;color:var(--el-text-color-secondary);font-size:12px">
                {{ a.email }}
                <el-tag v-if="a.has_data_account" size="small" type="info" style="margin-left:4px">已存在</el-tag>
              </span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="国家">
          <CountrySelect v-model="createForm.country_code" placeholder="选择国家（可选）" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="createForm.remarks" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="createLoading" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editVisible" title="编辑数据账户" width="480px" :close-on-click-modal="false">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="账户">
          <el-input :model-value="editRow?.account_name || ''" disabled />
        </el-form-item>
        <el-form-item label="国家">
          <CountrySelect v-model="editForm.country_code" placeholder="选择国家" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editForm.status" style="width:100%">
            <el-option value="active" label="活跃" />
            <el-option value="suspended" label="暂停" />
            <el-option value="closed" label="关闭" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.remarks" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editLoading" @click="handleEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 充值弹窗 -->
    <el-dialog v-model="rechargeVisible" title="账户充值" width="420px" :close-on-click-modal="false">
      <div style="margin-bottom:16px;padding:12px;background:var(--el-fill-color-lighter);border-radius:8px">
        <div style="font-weight:600">{{ rechargeRow?.account_name }}</div>
        <div style="font-size:13px;color:var(--el-text-color-secondary);margin-top:4px">
          当前余额：<span style="color:#409EFF;font-weight:600">${{ (rechargeRow?.balance || 0).toFixed(2) }}</span>
          <span style="margin-left:8px;font-size:12px;color:var(--el-text-color-placeholder)">（短信+数据共用）</span>
        </div>
      </div>
      <el-form :model="rechargeForm" label-width="80px">
        <el-form-item label="充值金额" required>
          <el-input-number v-model="rechargeForm.amount" :precision="2" :step="50" :min="0.01" style="width:100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="rechargeForm.remarks" placeholder="充值备注（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rechargeVisible = false">取消</el-button>
        <el-button type="success" :loading="rechargeLoading" @click="handleRecharge">确认充值</el-button>
      </template>
    </el-dialog>

    <!-- 操作记录弹窗 -->
    <el-dialog v-model="logsVisible" :title="`操作记录 - ${logsRow?.account_name || ''}`" width="750px">
      <el-table :data="logs" v-loading="logsLoading" stripe max-height="400">
        <el-table-column label="类型" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_recharge ? 'success' : ''" size="small">
              {{ row.is_recharge ? '充值' : '提取' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120">
          <template #default="{ row }">
            <span v-if="row.is_recharge" style="color:#67C23A;font-weight:600">
              +${{ Math.abs(row.total_cost).toFixed(2) }}
            </span>
            <span v-else style="color:#F56C6C">
              -${{ row.total_cost.toFixed(2) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="提取数量" width="90">
          <template #default="{ row }">{{ row.count || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : (row.status === 'failed' ? 'danger' : 'info')" size="small">
              {{ row.status === 'success' ? '成功' : (row.status === 'failed' ? '失败' : '进行中') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.remarks || '-' }}</template>
        </el-table-column>
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  getAccounts,
  getAccountStats,
  getAvailableAccounts,
  createDataAccount,
  updateDataAccount,
  deleteDataAccount,
  rechargeDataAccount,
  syncAccount,
  getAccountLogs,
  impersonateAccount,
} from '@/api/data-admin'
import CountrySelect from '@/components/CountrySelect.vue'
import { findCountryByIso } from '@/constants/countries'

function countryName(code: string): string {
  if (!code) return '-'
  const c = findCountryByIso(code)
  return c ? c.name : code
}

function statusType(s: string) {
  return s === 'active' ? 'success' : s === 'suspended' ? 'warning' : 'danger'
}
function statusLabel(s: string) {
  return s === 'active' ? '活跃' : s === 'suspended' ? '暂停' : '关闭'
}
function fmtDate(val: string | null) {
  if (!val) return '-'
  return val.replace('T', ' ').slice(0, 19)
}

// ====== 列表 ======
const loading = ref(false)
const accounts = ref<any[]>([])
const filters = reactive({ status: '', search: '' })
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
const stats = reactive({ total: 0, active: 0, total_balance: 0, total_spent: 0, total_extracted: 0 })

onMounted(() => { loadData(); loadStats() })

async function loadData() {
  loading.value = true
  try {
    const res = await getAccounts({
      status: filters.status || undefined,
      search: filters.search || undefined,
      page: pagination.page,
      page_size: pagination.pageSize,
    })
    if (res.success) {
      accounts.value = res.items || []
      pagination.total = res.total || 0
    }
  } catch (e: any) { ElMessage.error(e.message || '加载失败') }
  finally { loading.value = false }
}

async function loadStats() {
  try {
    const res = await getAccountStats()
    if (res.success) Object.assign(stats, res)
  } catch { /* ignore */ }
}

// ====== 新建 ======
const createVisible = ref(false)
const createLoading = ref(false)
const createForm = reactive({ account_id: null as number | null, country_code: '', remarks: '' })
const availableAccounts = ref<any[]>([])
const acctSearchLoading = ref(false)

function openCreateDialog() {
  createForm.account_id = null
  createForm.country_code = ''
  createForm.remarks = ''
  createVisible.value = true
  searchAccounts('')
}

async function searchAccounts(q: string) {
  acctSearchLoading.value = true
  try {
    const res = await getAvailableAccounts(q || undefined)
    availableAccounts.value = res.items || []
  } catch { availableAccounts.value = [] }
  finally { acctSearchLoading.value = false }
}

async function handleCreate() {
  if (!createForm.account_id) {
    ElMessage.warning('请选择关联账户')
    return
  }
  createLoading.value = true
  try {
    const res = await createDataAccount({
      account_id: createForm.account_id,
      country_code: createForm.country_code || undefined,
      remarks: createForm.remarks || undefined,
    })
    if (res.success) {
      ElMessage.success('创建成功')
      createVisible.value = false
      loadData()
      loadStats()
    }
  } catch (e: any) { ElMessage.error(e.message || '创建失败') }
  finally { createLoading.value = false }
}

// ====== 编辑 ======
const editVisible = ref(false)
const editLoading = ref(false)
const editRow = ref<any>(null)
const editForm = reactive({ country_code: '', status: 'active', remarks: '' })

function openEditDialog(row: any) {
  editRow.value = row
  editForm.country_code = row.country_code || ''
  editForm.status = row.status || 'active'
  editForm.remarks = row.remarks || ''
  editVisible.value = true
}

async function handleEdit() {
  editLoading.value = true
  try {
    const res = await updateDataAccount(editRow.value.id, {
      country_code: editForm.country_code,
      status: editForm.status,
      remarks: editForm.remarks,
    })
    if (res.success) {
      ElMessage.success('更新成功')
      editVisible.value = false
      loadData()
    }
  } catch (e: any) { ElMessage.error(e.message || '更新失败') }
  finally { editLoading.value = false }
}

// ====== 充值 ======
const rechargeVisible = ref(false)
const rechargeLoading = ref(false)
const rechargeRow = ref<any>(null)
const rechargeForm = reactive({ amount: 100, remarks: '' })

function openRechargeDialog(row: any) {
  rechargeRow.value = row
  rechargeForm.amount = 100
  rechargeForm.remarks = ''
  rechargeVisible.value = true
}

async function handleRecharge() {
  if (!rechargeForm.amount || rechargeForm.amount <= 0) {
    ElMessage.warning('请输入有效金额')
    return
  }
  rechargeLoading.value = true
  try {
    const res = await rechargeDataAccount(rechargeRow.value.id, {
      amount: rechargeForm.amount,
      remarks: rechargeForm.remarks,
    })
    if (res.success) {
      ElMessage.success(res.message || '充值成功')
      rechargeVisible.value = false
      loadData()
      loadStats()
    }
  } catch (e: any) { ElMessage.error(e.message || '充值失败') }
  finally { rechargeLoading.value = false }
}

// ====== 操作记录 ======
const logsVisible = ref(false)
const logsLoading = ref(false)
const logsRow = ref<any>(null)
const logs = ref<any[]>([])

async function viewLogs(row: any) {
  logsRow.value = row
  logsVisible.value = true
  logsLoading.value = true
  try {
    const res = await getAccountLogs(row.id, { page: 1, page_size: 50 })
    if (res.success) logs.value = res.items || []
  } catch (e: any) { ElMessage.error(e.message || '获取记录失败') }
  finally { logsLoading.value = false }
}

// ====== 登录（代客户登录数据商店） ======
async function handleLogin(row: any) {
  try {
    const res = await impersonateAccount(row.account_id)
    if (res.success && res.api_key) {
      const params = new URLSearchParams({
        impersonate: '1',
        api_key: res.api_key,
        account_id: String(row.account_id),
        account_name: row.account_name || '',
        redirect: '/data/store',
      })
      window.open(`/login?${params.toString()}`, '_blank')
      ElMessage.success(`已打开 ${row.account_name} 的数据商店`)
    }
  } catch (e: any) {
    ElMessage.error(e.message || '登录失败')
  }
}

// ====== 同步 ======
async function handleSync(row: any) {
  try {
    const res = await syncAccount(row.id)
    if (res.success) {
      row.balance = res.balance
      ElMessage.success(`刷新成功，余额: $${res.balance.toFixed(2)}`)
    }
  } catch (e: any) { ElMessage.error(e.message || '同步失败') }
}

// ====== 关闭 ======
async function handleClose(row: any) {
  try {
    await ElMessageBox.confirm(`确定关闭账户「${row.account_name}」？关闭后将无法充值和提取。`, '确认关闭', { type: 'warning' })
    const res = await deleteDataAccount(row.id, false)
    if (res.success) {
      ElMessage.success('账户已关闭')
      loadData()
      loadStats()
    }
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '操作失败')
  }
}

// ====== 永久删除 ======
async function handleForceDelete(row: any) {
  try {
    await ElMessageBox.confirm(
      `确定永久删除账户「${row.account_name}」？此操作不可恢复！`,
      '确认删除',
      { type: 'error', confirmButtonText: '确认删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' }
    )
    const res = await deleteDataAccount(row.id, true)
    if (res.success) {
      ElMessage.success('账户已永久删除')
      loadData()
      loadStats()
    }
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}
</script>

<style scoped>
.accounts-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.stats-row { margin-bottom: 0; }
.stat-card { text-align: center; }
.stat-custom { text-align: center; padding: 8px 0; }
.stat-val { display: block; font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; }
.stat-lbl { display: block; font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }
.filter-card :deep(.el-card__body) { padding: 16px; }
</style>
