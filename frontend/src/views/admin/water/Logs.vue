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
      <el-table-column label="账号 / 设备" min-width="250">
        <template #default="{ row }">
          <!-- 注册且含凭据串:拆显 账号 / 密码 / affiliateCode(+复制) -->
          <div v-if="row.action === 'register' && row.device_info && row.device_info.includes('账号')" class="creds-box">
            <div v-for="(seg, i) in parseCreds(row.device_info)" :key="i" class="creds-line">
              <span class="creds-k">{{ seg.k }}</span>
              <span class="creds-v" :class="{ mono: seg.mono }">{{ seg.v }}</span>
            </div>
            <el-button link type="primary" size="small" style="padding:0" @click="copyText(row.device_info)">复制</el-button>
          </div>
          <!-- 点击/其它:设备指纹 -->
          <el-tooltip v-else-if="row.user_agent" :content="row.user_agent" placement="top" effect="dark">
            <span>{{ row.device_info || row.user_agent }}</span>
          </el-tooltip>
          <span v-else-if="row.device_info">{{ row.device_info }}</span>
          <span v-else style="color: #909399">-</span>
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
import { ElMessage } from 'element-plus'
import { getLogs, getLogScreenshot } from '@/api/water'

// 注册凭据串 "账号 X ┊ 密码 Y ┊ affiliateCode Z ┊ TK688 @ host" → 拆成带标签的行
const parseCreds = (s: string) => {
  return (s || '').split('┊').map((raw) => {
    const seg = raw.trim()
    const m = seg.match(/^(账号|密码|affiliateCode)\s+(.+)$/)
    if (m) return { k: m[1], v: m[2], mono: true }
    return { k: '来源', v: seg, mono: false } // "TK688 @ host"
  }).filter((x) => x.v)
}

const copyText = async (t: string) => {
  try {
    await navigator.clipboard.writeText(t)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择')
  }
}

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
.creds-box { line-height: 1.5; }
.creds-line { display: flex; gap: 6px; font-size: 12px; }
.creds-k { color: #909399; min-width: 78px; }
.creds-v { color: #303133; word-break: break-all; }
.creds-v.mono { font-family: monospace; color: #409eff; }
</style>
