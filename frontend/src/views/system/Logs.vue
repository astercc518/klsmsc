<template>
  <div class="system-logs">
    <!-- 统计概览 -->
    <div class="stats-bar">
      <div class="stat-item">
        <span class="stat-value">{{ stats.total.toLocaleString() }}</span>
        <span class="stat-label">总日志条数</span>
      </div>
      <div class="stat-divider" />
      <div class="stat-item">
        <span class="stat-value accent-blue">{{ stats.today.toLocaleString() }}</span>
        <span class="stat-label">今日操作</span>
      </div>
      <div class="stat-divider" />
      <div class="module-tags">
        <span class="stat-label" style="margin-right:8px">按模块</span>
        <el-tag
          v-for="(info, mod) in stats.by_module"
          :key="mod"
          :type="moduleTagType(String(mod))"
          size="small"
          class="module-tag"
          @click="setModuleFilter(String(mod))"
        >
          {{ info.label }} {{ info.count }}
        </el-tag>
      </div>
    </div>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <!-- 快捷时间 -->
        <el-button-group class="time-shortcuts">
          <el-button
            v-for="t in TIME_SHORTCUTS"
            :key="t.value"
            :type="activeShortcut === t.value ? 'primary' : 'default'"
            size="small"
            @click="applyShortcut(t.value)"
          >{{ t.label }}</el-button>
        </el-button-group>

        <el-date-picker
          v-model="dateRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          size="small"
          style="width: 340px"
          :shortcuts="[]"
          @change="onDateChange"
        />

        <el-select
          v-model="filters.module"
          clearable
          placeholder="全部模块"
          size="small"
          style="width: 120px"
          @change="onFilterChange"
        >
          <el-option v-for="(label, key) in modules" :key="key" :label="label" :value="key" />
        </el-select>

        <el-select
          v-model="filters.status"
          clearable
          placeholder="全部状态"
          size="small"
          style="width: 100px"
          @change="onFilterChange"
        >
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
        </el-select>

        <el-input
          v-model="filters.admin_name"
          placeholder="操作人"
          clearable
          size="small"
          style="width: 110px"
          @keyup.enter="onFilterChange"
          @clear="onFilterChange"
        />

        <el-input
          v-model="filters.keyword"
          placeholder="关键词搜索"
          clearable
          size="small"
          style="width: 160px"
          @keyup.enter="onFilterChange"
          @clear="onFilterChange"
        />

        <el-button size="small" type="primary" :icon="Search" @click="onFilterChange">查询</el-button>
        <el-button size="small" @click="resetFilters">重置</el-button>
        <el-button size="small" :icon="Download" :loading="exporting" @click="onExportCsv">导出 CSV</el-button>
      </div>
    </el-card>

    <!-- 日志表格 -->
    <el-card shadow="never" class="table-card">
      <el-table
        :data="items"
        v-loading="loading"
        stripe
        style="width: 100%"
        row-key="id"
        @expand-change="onExpandChange"
      >
        <!-- 展开行：显示格式化 detail -->
        <el-table-column type="expand" width="36">
          <template #default="{ row }">
            <div class="expand-detail">
              <div v-if="row.error_message" class="error-msg">
                <el-icon><Warning /></el-icon> {{ row.error_message }}
              </div>
              <template v-if="row._parsedDetail">
                <pre class="detail-json">{{ JSON.stringify(row._parsedDetail, null, 2) }}</pre>
              </template>
              <span v-else-if="row.detail" class="detail-raw">{{ row.detail }}</span>
              <span v-else class="detail-empty">无附加信息</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="时间" width="158" fixed>
          <template #default="{ row }">
            <el-tooltip :content="row.created_at" placement="top">
              <span class="time-cell">{{ formatRelative(row.created_at) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="模块" width="100">
          <template #default="{ row }">
            <el-tag :type="moduleTagType(row.module)" size="small" effect="light">
              {{ row.module_label || row.module }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-tag :type="actionTagType(row.action)" size="small" effect="plain">
              {{ ACTION_LABELS[row.action] || row.action }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="结果" width="72">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status === 'success' ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="操作人" width="96">
          <template #default="{ row }">
            <div class="admin-cell">
              <span class="admin-avatar">{{ (row.admin_name || '?')[0].toUpperCase() }}</span>
              <span>{{ row.admin_name || '系统' }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="描述" min-width="200" show-overflow-tooltip prop="title" />

        <el-table-column label="IP" width="130">
          <template #default="{ row }">
            <span
              v-if="row.ip_address"
              class="ip-link"
              @click="setIpFilter(row.ip_address)"
            >{{ row.ip_address }}</span>
            <span v-else class="text-muted">—</span>
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
          @size-change="onSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Search, Warning, Download } from '@element-plus/icons-vue'
import { getSystemLogs, getSystemLogModules, getSystemLogStats, exportSystemLogs, type AdminLogItem } from '@/api/system'

const loading = ref(false)
const exporting = ref(false)
const items = ref<(AdminLogItem & { _parsedDetail?: any })[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const modules = ref<Record<string, string>>({})
const stats = reactive({ total: 0, today: 0, by_module: {} as Record<string, { count: number; label: string }> })
const dateRange = ref<[Date, Date] | null>(null)
const activeShortcut = ref('today')

const filters = reactive({
  module: '',
  status: '',
  admin_name: '',
  keyword: '',
  start_date: '',
  end_date: '',
})

const TIME_SHORTCUTS = [
  { label: '今天', value: 'today' },
  { label: '7天', value: '7d' },
  { label: '30天', value: '30d' },
  { label: '全部', value: 'all' },
]

const MODULE_COLORS: Record<string, string> = {
  login: 'primary',
  config: 'warning',
  security: 'danger',
  finance: 'success',
  account: '',
  channel: 'info',
  sms: 'info',
  system: '',
}

const ACTION_LABELS: Record<string, string> = {
  create: '新建',
  update: '修改',
  delete: '删除',
  login: '登录',
  export: '导出',
  import: '导入',
  query: '查询',
}

const ACTION_COLORS: Record<string, string> = {
  create: 'success',
  update: 'primary',
  delete: 'danger',
  login: 'info',
  export: 'warning',
  import: 'warning',
}

function moduleTagType(mod: string) {
  return (MODULE_COLORS[mod] || '') as any
}

function actionTagType(action: string) {
  return (ACTION_COLORS[action] || '') as any
}

function applyShortcut(value: string) {
  activeShortcut.value = value
  dateRange.value = null
  const now = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  if (value === 'today') {
    filters.start_date = todayStart.toISOString()
    filters.end_date = ''
  } else if (value === '7d') {
    const d = new Date(todayStart); d.setDate(d.getDate() - 6)
    filters.start_date = d.toISOString()
    filters.end_date = ''
  } else if (value === '30d') {
    const d = new Date(todayStart); d.setDate(d.getDate() - 29)
    filters.start_date = d.toISOString()
    filters.end_date = ''
  } else {
    filters.start_date = ''
    filters.end_date = ''
  }
  page.value = 1
  loadData()
}

function onDateChange(val: [Date, Date] | null) {
  activeShortcut.value = ''
  if (val) {
    filters.start_date = val[0].toISOString()
    filters.end_date = val[1].toISOString()
  } else {
    filters.start_date = ''
    filters.end_date = ''
  }
  page.value = 1
  loadData()
}

function onFilterChange() {
  page.value = 1
  loadData()
}

function onSizeChange() {
  page.value = 1
  loadData()
}

function setModuleFilter(mod: string) {
  filters.module = filters.module === mod ? '' : mod
  page.value = 1
  loadData()
}

function setIpFilter(ip: string) {
  filters.keyword = ip
  page.value = 1
  loadData()
}

function resetFilters() {
  filters.module = ''
  filters.status = ''
  filters.admin_name = ''
  filters.keyword = ''
  dateRange.value = null
  activeShortcut.value = 'today'
  applyShortcut('today')
}

function onExpandChange(row: any) {
  if (!row._parsedDetail && row.detail) {
    try { row._parsedDetail = JSON.parse(row.detail) } catch { /* raw string */ }
  }
}

function formatRelative(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const diff = Date.now() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days} 天前`
  return d.toLocaleDateString('zh-CN')
}

async function loadData() {
  loading.value = true
  try {
    const res = await getSystemLogs({
      page: page.value,
      page_size: pageSize.value,
      module: filters.module || undefined,
      admin_name: filters.admin_name || undefined,
      keyword: filters.keyword || undefined,
      start_date: filters.start_date || undefined,
      end_date: filters.end_date || undefined,
    })
    items.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

async function onExportCsv() {
  exporting.value = true
  try {
    const rows = await exportSystemLogs({
      module: filters.module || undefined,
      admin_name: filters.admin_name || undefined,
      keyword: filters.keyword || undefined,
      start_date: filters.start_date || undefined,
      end_date: filters.end_date || undefined,
    })
    const header = ['ID', '时间', '模块', '操作', '操作人', '描述', 'IP', '结果', '错误信息']
    const lines = rows.map(r => [
      r.id,
      r.created_at,
      r.module_label || r.module,
      r.action,
      r.admin_name,
      `"${(r.title || '').replace(/"/g, '""')}"`,
      r.ip_address || '',
      r.status,
      `"${(r.error_message || '').replace(/"/g, '""')}"`,
    ].join(','))
    const csv = [header.join(','), ...lines].join('\n')
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `system_logs_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  const [modRes, statsRes] = await Promise.all([
    getSystemLogModules(),
    getSystemLogStats(),
  ])
  modules.value = modRes.modules
  stats.total = statsRes.total
  stats.today = statsRes.today
  stats.by_module = statsRes.by_module
  applyShortcut('today')
})
</script>

<style scoped>
.system-logs { display: flex; flex-direction: column; gap: 12px; }

.stats-bar {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 12px 20px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  flex-wrap: wrap;
}
.stat-item { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.stat-value { font-size: 22px; font-weight: 700; color: var(--el-text-color-primary); line-height: 1; }
.stat-value.accent-blue { color: var(--el-color-primary); }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); }
.stat-divider { width: 1px; height: 36px; background: var(--el-border-color-lighter); }
.module-tags { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.module-tag { cursor: pointer; }

.filter-card :deep(.el-card__body) { padding: 12px 16px; }
.filter-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.time-shortcuts .el-button { padding: 5px 10px; }

.table-card :deep(.el-card__body) { padding: 0; }
.table-card :deep(.el-table__expand-icon) { margin-right: 4px; }

.expand-detail {
  padding: 12px 24px 12px 48px;
  background: var(--el-fill-color-lighter);
}
.detail-json {
  margin: 0;
  font-size: 12px;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--el-text-color-regular);
  max-height: 300px;
  overflow-y: auto;
}
.detail-raw { font-size: 12px; font-family: monospace; color: var(--el-text-color-regular); }
.detail-empty { font-size: 12px; color: var(--el-text-color-placeholder); }
.error-msg {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--el-color-danger);
  font-size: 12px;
  margin-bottom: 8px;
}

.time-cell { font-size: 13px; color: var(--el-text-color-regular); }
.admin-cell { display: flex; align-items: center; gap: 6px; }
.admin-avatar {
  width: 24px; height: 24px;
  border-radius: 50%;
  background: var(--el-color-primary-light-7);
  color: var(--el-color-primary);
  font-size: 11px;
  font-weight: 600;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.ip-link {
  color: var(--el-color-primary);
  cursor: pointer;
  font-family: monospace;
  font-size: 12px;
}
.ip-link:hover { text-decoration: underline; }
.text-muted { color: var(--el-text-color-placeholder); }

.pagination-wrap { padding: 12px 16px; display: flex; justify-content: flex-end; }
</style>
