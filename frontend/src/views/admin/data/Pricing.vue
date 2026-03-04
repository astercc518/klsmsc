<template>
  <div class="pricing-page">
    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <el-row :gutter="12" align="middle">
        <el-col :span="4">
          <CountrySelect v-model="filters.country_code" placeholder="搜索国家" :show-all-option="false" />
        </el-col>
        <el-col :span="4">
          <el-select v-model="filters.source" placeholder="全部来源" clearable style="width:100%">
            <el-option v-for="s in SOURCE_OPTIONS" :key="s.value" :value="s.value" :label="s.label" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="filters.purpose" placeholder="全部用途" clearable style="width:100%">
            <el-option v-for="p in PURPOSE_OPTIONS" :key="p.value" :value="p.value" :label="p.label" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="filters.freshness" placeholder="全部时效" clearable style="width:100%">
            <el-option v-for="f in FRESHNESS_OPTIONS" :key="f.value" :value="f.value" :label="f.label" />
          </el-select>
        </el-col>
        <el-col :span="8">
          <el-button type="primary" @click="loadData">查询</el-button>
          <el-button type="success" @click="openCreateDialog">新增模板</el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 数据表格 -->
    <el-card shadow="never">
      <el-table :data="items" v-loading="loading" stripe border style="width:100%">
        <el-table-column prop="name" label="模板名称" min-width="220" show-overflow-tooltip />
        <el-table-column label="国家" width="140">
          <template #default="{ row }">
            {{ formatCountry(row.country_code) }}
          </template>
        </el-table-column>
        <el-table-column prop="source_label" label="来源" width="100" />
        <el-table-column prop="purpose_label" label="用途" width="80" />
        <el-table-column prop="freshness_label" label="时效" width="80" />
        <el-table-column label="售价" width="120">
          <template #default="{ row }">
            <span style="color:#67C23A;font-weight:600">${{ row.price_per_number }}</span>
          </template>
        </el-table-column>
        <el-table-column label="成本" width="120">
          <template #default="{ row }">
            <span style="color:#F56C6C">${{ row.cost_per_number }}</span>
          </template>
        </el-table-column>
        <el-table-column label="利润" width="120">
          <template #default="{ row }">
            <span :style="{ color: profit(row) >= 0 ? '#67C23A' : '#F56C6C', fontWeight: 600 }">
              ${{ profit(row).toFixed(4) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="remarks" label="备注" min-width="150" show-overflow-tooltip />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-popconfirm title="确认删除?" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="total > pageSize"
        style="margin-top:16px;justify-content:flex-end"
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="handlePageChange"
      />
    </el-card>

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑定价模板' : '新增定价模板'" width="560px" destroy-on-close>
      <el-form :model="form" label-width="80px">
        <el-form-item label="模板名称">
          <el-input :modelValue="autoName" disabled placeholder="自动生成：国家-来源-用途-时效-价格" />
        </el-form-item>
        <el-form-item label="国家" required>
          <CountrySelect v-model="form.country_code" placeholder="选择国家 (* 全部)" :show-all-option="true" />
        </el-form-item>
        <el-form-item label="来源" required>
          <el-select v-model="form.source" placeholder="请选择来源" style="width:100%" :disabled="!!editingId">
            <el-option v-for="s in SOURCE_OPTIONS" :key="s.value" :value="s.value" :label="s.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="用途" required>
          <el-select v-model="form.purpose" placeholder="请选择用途" style="width:100%" :disabled="!!editingId">
            <el-option v-for="p in PURPOSE_OPTIONS" :key="p.value" :value="p.value" :label="p.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="时效" required>
          <el-select v-model="form.freshness" placeholder="请选择时效" style="width:100%" :disabled="!!editingId">
            <el-option v-for="f in FRESHNESS_OPTIONS" :key="f.value" :value="f.value" :label="f.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="售价" required>
          <el-input v-model="form.price_per_number" placeholder="0.0500">
            <template #prepend>$</template>
          </el-input>
        </el-form-item>
        <el-form-item label="成本">
          <el-input v-model="form.cost_per_number" placeholder="0.0000">
            <template #prepend>$</template>
          </el-input>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remarks" type="textarea" :rows="2" placeholder="可选" />
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
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  getPricingTemplates, createPricingTemplate, updatePricingTemplate,
  deletePricingTemplate, type PricingTemplate
} from '@/api/data-admin'
import CountrySelect from '@/components/CountrySelect.vue'
import { findCountryByIso, findCountryByDial } from '@/constants/countries'

const { t } = useI18n()

function formatCountry(code: string): string {
  if (!code || code === '*') return '全部 (*)'
  const c = findCountryByIso(code) || findCountryByDial(code)
  return c ? `${c.name} (+${c.dial})` : code
}

const SOURCE_OPTIONS = [
  { value: 'credential', label: '撞库' },
  { value: 'penetration', label: '渗透' },
  { value: 'social_eng', label: '社工库' },
  { value: 'telemarketing', label: '电销' },
  { value: 'otp', label: 'OTP' },
]
const PURPOSE_OPTIONS = [
  { value: 'bc', label: 'BC' },
  { value: 'part_time', label: '兼职' },
  { value: 'dating', label: '交友' },
  { value: 'finance', label: '金融' },
  { value: 'stock', label: '股票' },
]
const FRESHNESS_OPTIONS = [
  { value: '3day', label: '3日内' },
  { value: '7day', label: '7日内' },
  { value: '30day', label: '30日内' },
  { value: 'history', label: '历史' },
]

const loading = ref(false)
const submitting = ref(false)
const items = ref<PricingTemplate[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const filters = ref({ country_code: '', source: '', purpose: '', freshness: '' })

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const form = ref({
  country_code: '*',
  source: '',
  purpose: '',
  freshness: '',
  price_per_number: '',
  cost_per_number: '0',
  remarks: '',
})

const SOURCE_MAP = Object.fromEntries(SOURCE_OPTIONS.map(s => [s.value, s.label]))
const PURPOSE_MAP = Object.fromEntries(PURPOSE_OPTIONS.map(p => [p.value, p.label]))
const FRESHNESS_MAP = Object.fromEntries(FRESHNESS_OPTIONS.map(f => [f.value, f.label]))

const autoName = computed(() => {
  const { country_code, source, purpose, freshness, price_per_number } = form.value
  const cInfo = findCountryByIso(country_code) || findCountryByDial(country_code)
  const countryName = (!country_code || country_code === '*') ? '全部' : (cInfo?.name || country_code)
  const parts = [
    countryName,
    SOURCE_MAP[source] || '',
    PURPOSE_MAP[purpose] || '',
    FRESHNESS_MAP[freshness] || '',
    price_per_number || '',
  ].filter(Boolean)
  return parts.join('-')
})

watch(() => form.value.price_per_number, (newPrice) => {
  if (!editingId.value && newPrice) {
    const price = parseFloat(newPrice)
    if (!isNaN(price)) {
      form.value.cost_per_number = (price * 0.3).toFixed(4)
    }
  }
})

function profit(row: PricingTemplate): number {
  return parseFloat(row.price_per_number || '0') - parseFloat(row.cost_per_number || '0')
}

async function loadData() {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value }
    if (filters.value.country_code) params.country_code = filters.value.country_code
    if (filters.value.source) params.source = filters.value.source
    if (filters.value.purpose) params.purpose = filters.value.purpose
    if (filters.value.freshness) params.freshness = filters.value.freshness
    const res = await getPricingTemplates(params)
    items.value = res.items || []
    total.value = res.total || 0
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

function handlePageChange(p: number) {
  page.value = p
  loadData()
}

function openCreateDialog() {
  editingId.value = null
  form.value = { country_code: '*', source: '', purpose: '', freshness: '', price_per_number: '', cost_per_number: '0', remarks: '' }
  dialogVisible.value = true
}

function openEditDialog(row: PricingTemplate) {
  editingId.value = row.id
  form.value = {
    country_code: row.country_code,
    source: row.source,
    purpose: row.purpose,
    freshness: row.freshness,
    price_per_number: row.price_per_number,
    cost_per_number: row.cost_per_number || '0',
    remarks: row.remarks || '',
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!form.value.source || !form.value.purpose || !form.value.freshness || !form.value.price_per_number) {
    ElMessage.warning('请填写必填项')
    return
  }
  submitting.value = true
  try {
    if (editingId.value) {
      await updatePricingTemplate(editingId.value, {
        name: autoName.value,
        price_per_number: form.value.price_per_number,
        cost_per_number: form.value.cost_per_number,
        remarks: form.value.remarks,
      })
      ElMessage.success('更新成功')
    } else {
      await createPricingTemplate({
        name: autoName.value,
        country_code: form.value.country_code || '*',
        source: form.value.source,
        purpose: form.value.purpose,
        freshness: form.value.freshness,
        price_per_number: form.value.price_per_number,
        cost_per_number: form.value.cost_per_number,
        remarks: form.value.remarks || undefined,
      })
      ElMessage.success('新增成功')
    }
    dialogVisible.value = false
    loadData()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

async function handleDelete(id: number) {
  try {
    await deletePricingTemplate(id)
    ElMessage.success('删除成功')
    loadData()
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(() => loadData())
</script>

<style scoped>
.pricing-page { padding: 0; }
.filter-card { margin-bottom: 16px; }
</style>
