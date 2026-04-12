<template>
  <div class="proxy-manage">
    <!-- 统计卡片 -->
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-value">{{ stats.total }}</div>
        <div class="stat-label">总代理数</div>
      </div>
      <div class="stat-card success">
        <div class="stat-value">{{ stats.active }}</div>
        <div class="stat-label">在线</div>
      </div>
      <div class="stat-card danger">
        <div class="stat-value">{{ stats.inactive }}</div>
        <div class="stat-label">离线</div>
      </div>
    </div>

    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button type="primary" @click="openDialog()">新增代理</el-button>
      <el-select v-model="filterCountry" placeholder="按国家筛选" clearable style="width: 150px; margin-left: 10px" @change="loadData">
        <el-option label="全部" value="" />
        <el-option label="通用 (*)" value="*" />
        <el-option label="泰国 (TH)" value="TH" />
        <el-option label="巴西 (BR)" value="BR" />
        <el-option label="印度 (IN)" value="IN" />
      </el-select>
    </div>

    <!-- 表格 -->
    <el-table :data="tableData" v-loading="loading" stripe border style="width: 100%; margin-top: 15px">
      <el-table-column prop="name" label="名称" width="180" />
      <el-table-column prop="proxy_type" label="类型" width="90">
        <template #default="{ row }">
          <el-tag size="small">{{ row.proxy_type.toUpperCase() }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="endpoint_masked" label="地址" min-width="220" show-overflow-tooltip />
      <el-table-column prop="country_code" label="国家" width="80" align="center" />
      <el-table-column prop="status" label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : row.status === 'testing' ? 'warning' : 'danger'" size="small">
            {{ row.status === 'active' ? '在线' : row.status === 'testing' ? '测试中' : '离线' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="max_concurrency" label="最大并发" width="90" align="center" />
      <el-table-column prop="last_test_result" label="最近测试" min-width="200" show-overflow-tooltip />
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openDialog(row)">编辑</el-button>
          <el-dropdown trigger="click" @command="(cmd: string) => handleTest(row, cmd)" style="margin: 0 4px">
            <el-button size="small" type="warning" :loading="row._testing">
              测试<el-icon style="margin-left: 4px"><arrow-down /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="">默认</el-dropdown-item>
                <el-dropdown-item command="th">泰国 (TH)</el-dropdown-item>
                <el-dropdown-item command="br">巴西 (BR)</el-dropdown-item>
                <el-dropdown-item command="in">印度 (IN)</el-dropdown-item>
                <el-dropdown-item command="id">印尼 (ID)</el-dropdown-item>
                <el-dropdown-item command="ph">菲律宾 (PH)</el-dropdown-item>
                <el-dropdown-item command="vn">越南 (VN)</el-dropdown-item>
                <el-dropdown-item command="us">美国 (US)</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button size="small" :type="row.status === 'active' ? 'danger' : 'success'" @click="handleToggle(row)">
            {{ row.status === 'active' ? '停用' : '启用' }}
          </el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-wrap">
      <el-pagination background layout="total, prev, pager, next" :total="total" :page-size="pageSize" v-model:current-page="currentPage" @current-change="loadData" />
    </div>

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑代理' : '新增代理'" width="520px" destroy-on-close>
      <el-form :model="form" label-width="100px">
        <el-form-item label="代理名称" required>
          <el-input v-model="form.name" placeholder="如: BrightData 泰国住宅" />
        </el-form-item>
        <el-form-item label="代理类型">
          <el-select v-model="form.proxy_type" style="width: 100%">
            <el-option label="HTTP" value="http" />
            <el-option label="HTTPS" value="https" />
            <el-option label="SOCKS5" value="socks5" />
          </el-select>
        </el-form-item>
        <el-form-item label="代理地址" required>
          <el-input v-model="form.endpoint" placeholder="http://user:pass@host:port" />
        </el-form-item>
        <el-form-item label="目标国家">
          <el-input v-model="form.country_code" placeholder="* 表示通用" style="width: 120px" />
        </el-form-item>
        <el-form-item label="自动路由">
          <el-switch v-model="form.country_auto" />
          <span style="margin-left: 8px; color: #999; font-size: 12px">支持 {country} 占位符</span>
        </el-form-item>
        <el-form-item label="最大并发">
          <el-input-number v-model="form.max_concurrency" :min="1" :max="100" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { getProxies, createProxy, updateProxy, deleteProxy, testProxy } from '@/api/water'

const loading = ref(false)
const submitting = ref(false)
const tableData = ref<any[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20
const filterCountry = ref('')
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)

const form = reactive({
  name: '',
  proxy_type: 'http',
  endpoint: '',
  country_code: '*',
  country_auto: false,
  max_concurrency: 10,
  remark: '',
})

const stats = computed(() => {
  const active = tableData.value.filter(p => p.status === 'active').length
  return { total: total.value, active, inactive: total.value - active }
})

const loadData = async () => {
  loading.value = true
  try {
    const params: any = { page: currentPage.value, page_size: pageSize }
    if (filterCountry.value) params.country_code = filterCountry.value
    const res: any = await getProxies(params)
    tableData.value = (res.items || []).map((p: any) => ({ ...p, _testing: false }))
    total.value = res.total || 0
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const openDialog = (row?: any) => {
  if (row) {
    editingId.value = row.id
    Object.assign(form, {
      name: row.name,
      proxy_type: row.proxy_type,
      endpoint: row.endpoint,
      country_code: row.country_code,
      country_auto: row.country_auto,
      max_concurrency: row.max_concurrency,
      remark: row.remark || '',
    })
  } else {
    editingId.value = null
    Object.assign(form, { name: '', proxy_type: 'http', endpoint: '', country_code: '*', country_auto: false, max_concurrency: 10, remark: '' })
  }
  dialogVisible.value = true
}

const handleSubmit = async () => {
  if (!form.name || !form.endpoint) {
    ElMessage.warning('请填写必填项')
    return
  }
  submitting.value = true
  try {
    if (editingId.value) {
      await updateProxy(editingId.value, { ...form })
      ElMessage.success('更新成功')
    } else {
      await createProxy({ ...form })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await loadData()
  } catch (e) {
    console.error(e)
  } finally {
    submitting.value = false
  }
}

const handleTest = async (row: any, testCountry: string = '') => {
  row._testing = true
  try {
    const res: any = await testProxy(row.id, testCountry)
    if (res.success) {
      const countryInfo = res.test_country ? ` (${res.test_country.toUpperCase()})` : ''
      ElMessage.success(`连通性测试通过！出口 IP: ${res.ip}${countryInfo}，延迟: ${res.latency_ms}ms`)
    } else {
      ElMessage.error(`测试失败: ${res.error}`)
    }
    await loadData()
  } catch (e) {
    console.error(e)
  } finally {
    row._testing = false
  }
}

const handleToggle = async (row: any) => {
  const newStatus = row.status === 'active' ? 'inactive' : 'active'
  await updateProxy(row.id, { status: newStatus })
  ElMessage.success(newStatus === 'active' ? '已启用' : '已停用')
  await loadData()
}

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(`确定删除代理「${row.name}」？`, '确认')
  await deleteProxy(row.id)
  ElMessage.success('删除成功')
  await loadData()
}

onMounted(() => loadData())
</script>

<style scoped>
.proxy-manage { padding: 0; }
.stat-cards { display: flex; gap: 16px; margin-bottom: 16px; }
.stat-card { flex: 1; background: #f5f7fa; border-radius: 8px; padding: 16px 20px; text-align: center; }
.stat-card.success { background: #f0f9eb; }
.stat-card.danger { background: #fef0f0; }
.stat-value { font-size: 28px; font-weight: bold; color: #303133; }
.stat-card.success .stat-value { color: #67c23a; }
.stat-card.danger .stat-value { color: #f56c6c; }
.stat-label { font-size: 13px; color: #909399; margin-top: 4px; }
.toolbar { display: flex; align-items: center; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
