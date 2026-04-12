<template>
  <div class="water-logs">
    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-select v-model="filters.action" placeholder="操作类型" clearable style="width: 120px" @change="loadData">
        <el-option label="全部" value="" />
        <el-option label="点击" value="click" />
        <el-option label="注册" value="register" />
      </el-select>
      <el-select v-model="filters.status" placeholder="状态" clearable style="width: 120px" @change="loadData">
        <el-option label="全部" value="" />
        <el-option label="成功" value="success" />
        <el-option label="失败" value="failed" />
        <el-option label="处理中" value="processing" />
        <el-option label="待处理" value="pending" />
      </el-select>
      <el-input v-model="filters.batch_id" placeholder="批次ID" clearable style="width: 120px" @clear="loadData" @keyup.enter="loadData" />
      <el-date-picker v-model="dateRange" type="daterange" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" value-format="YYYY-MM-DD" style="width: 260px" @change="onDateChange" />
      <el-button type="primary" @click="loadData">查询</el-button>
    </div>

    <!-- 表格 -->
    <el-table :data="tableData" v-loading="loading" stripe border style="width: 100%; margin-top: 15px" size="small">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="时间" width="160">
        <template #default="{ row }">{{ row.created_at?.replace('T', ' ') }}</template>
      </el-table-column>
      <el-table-column prop="batch_id" label="批次" width="70" />
      <el-table-column prop="channel_id" label="通道" width="70" />
      <el-table-column label="URL" min-width="250" show-overflow-tooltip>
        <template #default="{ row }">
          <a :href="row.url" target="_blank" style="color: #409eff">{{ row.url }}</a>
        </template>
      </el-table-column>
      <el-table-column prop="action" label="类型" width="70" align="center">
        <template #default="{ row }">
          <el-tag :type="row.action === 'click' ? 'primary' : 'warning'" size="small">
            {{ row.action === 'click' ? '点击' : '注册' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : row.status === 'processing' ? 'warning' : 'info'" size="small">
            {{ { success: '成功', failed: '失败', processing: '处理中', pending: '待处理' }[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="代理IP" width="230">
        <template #default="{ row }">
          <span v-if="row.proxy_ip">{{ row.proxy_ip }}</span>
          <span v-else style="color: #909399">-</span>
          <el-tag v-if="row.proxy_country" size="small" type="info" style="margin-left: 6px">{{ countryName(row.proxy_country) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="耗时" width="80" align="center">
        <template #default="{ row }">{{ row.duration_ms ? `${row.duration_ms}ms` : '-' }}</template>
      </el-table-column>
      <el-table-column prop="error_message" label="错误信息" min-width="200" show-overflow-tooltip />
      <el-table-column label="截图" width="70" align="center">
        <template #default="{ row }">
          <el-button v-if="row.has_screenshot" size="small" type="primary" link @click="viewScreenshot(row)">查看</el-button>
          <span v-else>-</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-wrap">
      <el-pagination background layout="total, sizes, prev, pager, next" :total="total" :page-sizes="[20, 50, 100]" v-model:current-page="currentPage" v-model:page-size="pageSize" @current-change="loadData" @size-change="loadData" />
    </div>

    <!-- 截图预览 -->
    <el-dialog v-model="screenshotVisible" title="截图预览" width="600px">
      <div style="text-align: center">
        <img :src="screenshotUrl" style="max-width: 100%; max-height: 500px" alt="截图" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getLogs, getLogScreenshot } from '@/api/water'

const { t, tm } = useI18n()
const countriesMap = tm('countries') as Record<string, string>

const countryName = (code: string) => {
  if (!code) return ''
  const upper = code.toUpperCase()
  return countriesMap?.[upper] || upper
}

const loading = ref(false)
const tableData = ref<any[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const dateRange = ref<string[] | null>(null)
const screenshotVisible = ref(false)
const screenshotUrl = ref('')

const filters = reactive({
  action: '',
  status: '',
  batch_id: '',
})

const onDateChange = () => {
  loadData()
}

const loadData = async () => {
  loading.value = true
  try {
    const params: any = { page: currentPage.value, page_size: pageSize.value }
    if (filters.action) params.action = filters.action
    if (filters.status) params.status = filters.status
    if (filters.batch_id) params.batch_id = parseInt(filters.batch_id)
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }
    const res: any = await getLogs(params)
    tableData.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const viewScreenshot = (row: any) => {
  screenshotUrl.value = getLogScreenshot(row.id)
  screenshotVisible.value = true
}

onMounted(() => loadData())
</script>

<style scoped>
.water-logs { padding: 0; }
.filter-bar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
