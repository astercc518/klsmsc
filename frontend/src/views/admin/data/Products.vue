<template>
  <div class="products-page">
    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <el-row :gutter="12" align="middle">
        <el-col :span="4">
          <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 100%">
            <el-option value="active" label="上架" />
            <el-option value="inactive" label="下架" />
            <el-option value="sold_out" label="售罄" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="filters.product_type" placeholder="全部类型" clearable style="width: 100%">
            <el-option value="data_only" label="纯数据" />
            <el-option value="combo" label="组合套餐" />
            <el-option value="data_and_send" label="买即发" />
          </el-select>
        </el-col>
        <el-col :span="3">
          <el-input v-model="searchText" placeholder="搜索名称/编码" clearable @clear="loadData" @keyup.enter="loadData" />
        </el-col>
        <el-col :span="9">
          <el-button type="primary" @click="loadData">查询</el-button>
          <el-button type="success" :icon="Plus" @click="openCreateDialog">{{ t('dataPool.createProduct') }}</el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 数据表格 -->
    <el-card shadow="never">
      <el-table :data="products" v-loading="loading" stripe border style="width: 100%" default-sort="{ prop: 'id', order: 'ascending' }">
        <el-table-column prop="id" label="ID" width="70" sortable />
        <el-table-column prop="product_name" label="商品名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="国家" width="100">
          <template #default="{ row }">{{ countryName(row.country_code) }}</template>
        </el-table-column>
        <el-table-column label="来源" width="80">
          <template #default="{ row }">{{ row.source_label || '-' }}</template>
        </el-table-column>
        <el-table-column label="用途" width="80">
          <template #default="{ row }">{{ row.purpose_label || '-' }}</template>
        </el-table-column>
        <el-table-column label="时效" width="80">
          <template #default="{ row }">{{ row.freshness_label || '-' }}</template>
        </el-table-column>
        <el-table-column label="单价" width="100" sortable :sort-by="(row: any) => Number(row.price_per_number)">
          <template #default="{ row }">
            <span style="color:#67C23A;font-weight:600">${{ row.price_per_number }}</span>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="100" sortable sort-by="total_quantity">
          <template #default="{ row }">
            <span style="font-weight:600">{{ (row.total_quantity ?? 0).toLocaleString() }}</span>
          </template>
        </el-table-column>
        <el-table-column label="已售" width="100" sortable sort-by="total_sold">
          <template #default="{ row }">
            <span style="color:#E6A23C;font-weight:600">{{ (row.total_sold ?? 0).toLocaleString() }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未售" width="120" sortable sort-by="unsold_count">
          <template #default="{ row }">
            <span style="font-weight:600;margin-right:6px">{{ (row.unsold_count ?? 0).toLocaleString() }}</span>
            <el-button size="small" :icon="Refresh" circle @click="handleRefreshStock(row)" title="刷新库存" />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : (row.status === 'sold_out' ? 'danger' : 'info')" size="small">
              {{ row.status === 'active' ? '上架' : (row.status === 'sold_out' ? '售罄' : '下架') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.actions')" width="120" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openEditDialog(row)">{{ t('common.edit') }}</el-button>
            <el-button size="small" type="danger" link @click="handleDelete(row)">{{ t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑商品' : '新建商品'"
      width="600px"
      :close-on-click-modal="false"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" label-position="top">
        <template v-if="!isEdit">
          <!-- 新建模式：与上传数据一致的模板选择流程 -->
          <el-form-item label="① 选择国家" required>
            <CountrySelect v-model="createCountry" placeholder="先选国家，快速筛选模板" />
          </el-form-item>

          <el-form-item label="② 选择定价模板" required>
            <el-select
              v-model="createTemplateId"
              :placeholder="tplLoading ? '加载中...' : `共 ${createFilteredTpls.length} 个模板`"
              filterable clearable style="width: 100%"
              @change="onCreateTplChange"
            >
              <template v-if="createCountry">
                <el-option-group v-if="createCountryTpls.length" :label="`${countryName(createCountryIso)} 专属模板`">
                  <el-option v-for="tpl in createCountryTpls" :key="tpl.id" :value="tpl.id" :label="tpl.name">
                    <span>{{ tpl.source_label }}-{{ tpl.purpose_label }}-{{ tpl.freshness_label }}</span>
                    <span style="float:right;color:#67C23A;font-size:12px;margin-left:12px">${{ tpl.price_per_number }}</span>
                  </el-option>
                </el-option-group>
                <el-option-group v-if="createWildcardTpls.length" label="通用模板 (全部国家)">
                  <el-option v-for="tpl in createWildcardTpls" :key="tpl.id" :value="tpl.id" :label="tpl.name">
                    <span>{{ tpl.source_label }}-{{ tpl.purpose_label }}-{{ tpl.freshness_label }}</span>
                    <span style="float:right;color:#67C23A;font-size:12px;margin-left:12px">${{ tpl.price_per_number }}</span>
                  </el-option>
                </el-option-group>
              </template>
              <template v-else>
                <el-option v-for="tpl in tplList" :key="tpl.id" :value="tpl.id" :label="tpl.name">
                  <span>{{ tpl.source_label }}-{{ tpl.purpose_label }}-{{ tpl.freshness_label }}</span>
                  <span style="float:right;color:#67C23A;font-size:12px;margin-left:12px">${{ tpl.price_per_number }}</span>
                </el-option>
              </template>
            </el-select>
          </el-form-item>

          <!-- 选中模板的信息卡 -->
          <el-card v-if="createSelectedTpl" shadow="never" class="tpl-info-card">
            <el-descriptions :column="3" border size="small">
              <el-descriptions-item label="国家">{{ countryName(createCountryIso) }}</el-descriptions-item>
              <el-descriptions-item label="来源">{{ createSelectedTpl.source_label }}</el-descriptions-item>
              <el-descriptions-item label="用途">{{ createSelectedTpl.purpose_label }}</el-descriptions-item>
              <el-descriptions-item label="时效">{{ createSelectedTpl.freshness_label }}</el-descriptions-item>
              <el-descriptions-item label="售价">
                <span style="color:#67C23A;font-weight:600">${{ createSelectedTpl.price_per_number }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="成本">
                <span style="color:#F56C6C">${{ createSelectedTpl.cost_per_number }}</span>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>

          <!-- 第三步：上传数据文件 -->
          <el-form-item label="③ 上传数据文件 (CSV/TXT)" v-if="createSelectedTpl">
            <el-upload
              ref="createUploadRef"
              :auto-upload="false"
              :limit="1"
              accept=".csv,.txt"
              :on-change="handleCreateFileChange"
              :on-remove="() => (createFile = null)"
              drag
            >
              <el-icon style="font-size: 40px; color: var(--el-color-primary)"><UploadFilled /></el-icon>
              <div style="margin-top: 8px">点击或拖拽文件到此处上传</div>
            </el-upload>
            <div class="el-upload__tip">支持 CSV/TXT 格式，最大 500MB，自动清洗去重入库并创建商品</div>
          </el-form-item>

          <!-- 导入任务已提交提示 -->
          <el-card v-if="createImportResult" shadow="never" class="import-result-card">
            <div style="text-align:center;padding:16px 0">
              <el-icon style="font-size:40px;color:var(--el-color-success)"><UploadFilled /></el-icon>
              <div style="margin-top:12px;font-size:16px;font-weight:600;color:var(--el-color-success)">导入任务已提交，商品将自动创建</div>
              <div style="margin-top:8px;font-size:13px;color:var(--el-text-color-secondary)">
                批次号：{{ createImportResult.batch_id }}
              </div>
              <div style="margin-top:4px;font-size:13px;color:var(--el-text-color-secondary)">
                可到「数据上传」页面查看导入进度
              </div>
            </div>
          </el-card>

          <el-divider v-if="!createImportResult" content-position="left">或手动创建空商品</el-divider>
        </template>

        <template v-if="!createImportResult">
          <el-form-item label="商品编码" required>
            <el-input v-model="form.product_code" :disabled="isEdit" placeholder="选择模板后自动生成" />
          </el-form-item>
          <el-form-item label="商品名称" required>
            <el-input v-model="form.product_name" placeholder="选择模板后自动生成" />
          </el-form-item>

          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="单价 (USD)" required>
                <el-input-number v-model="form.price_per_number" :precision="4" :step="0.01" :min="0" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="最小购买量">
                <el-input-number v-model="form.min_purchase" :min="1" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="最大购买量">
                <el-input-number v-model="form.max_purchase" :min="1" style="width:100%" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <el-form-item v-if="isEdit" label="状态">
          <el-select v-model="form.status" style="width:100%">
            <el-option value="active" label="上架" />
            <el-option value="inactive" label="下架" />
            <el-option value="sold_out" label="售罄" />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">{{ createImportResult ? '关闭' : '取消' }}</el-button>
        <el-button v-if="!isEdit && createSelectedTpl && !createImportResult" type="success" :loading="createImporting" @click="submitCreateWithImport" :icon="UploadFilled">
          上传数据并创建商品
        </el-button>
        <el-button v-if="!createImportResult" type="primary" :loading="submitting" @click="submitForm">
          {{ isEdit ? '保存' : '仅创建空商品' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, UploadFilled } from '@element-plus/icons-vue'
import {
  getProducts,
  createProduct,
  updateProduct,
  deleteProduct,
  refreshProductStock,
  getPricingTemplates,
  importNumbers,
  type PricingTemplate,
} from '@/api/data-admin'
import { findCountryByIso } from '@/constants/countries'
import CountrySelect from '@/components/CountrySelect.vue'

const { t } = useI18n()

function countryName(iso: string): string {
  if (!iso) return '全部'
  const c = findCountryByIso(iso)
  return c ? c.name : iso
}

// ====== 列表 ======
const loading = ref(false)
const products = ref<any[]>([])
const filters = reactive({ status: '', product_type: '' })
const searchText = ref('')

onMounted(() => { loadData() })

async function loadData() {
  loading.value = true
  try {
    const res = await getProducts({
      status: filters.status || undefined,
      product_type: filters.product_type || undefined,
    })
    if (res.success) {
      let items = res.items || []
      const q = searchText.value.trim().toLowerCase()
      if (q) {
        items = items.filter((p: any) =>
          (p.product_name || '').toLowerCase().includes(q) ||
          (p.product_code || '').toLowerCase().includes(q) ||
          (p.country_code || '').toLowerCase().includes(q) ||
          (p.source_label || '').includes(q) ||
          (p.purpose_label || '').includes(q)
        )
      }
      products.value = items
    }
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

// ====== 弹窗 ======
const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)
const currentId = ref<number | null>(null)
const formRef = ref()

const form = reactive({
  product_code: '',
  product_name: '',
  price_per_number: 0.1,
  min_purchase: 100,
  max_purchase: 100000,
  status: 'active',
  _filter_criteria: {} as any,
})

// --- 新建：模板选择 ---
const tplList = ref<PricingTemplate[]>([])
const tplLoading = ref(false)
const createCountry = ref('')
const createTemplateId = ref<number | null>(null)
const createSelectedTpl = ref<PricingTemplate | null>(null)

const createCountryIso = computed(() => createCountry.value || '')

const createCountryTpls = computed(() =>
  createCountry.value ? tplList.value.filter((tp: PricingTemplate) => tp.country_code === createCountry.value) : []
)
const createWildcardTpls = computed(() =>
  tplList.value.filter((tp: PricingTemplate) => tp.country_code === '*')
)
const createFilteredTpls = computed(() =>
  createCountry.value
    ? [...createCountryTpls.value, ...createWildcardTpls.value]
    : tplList.value
)

const createFile = ref<File | null>(null)
const createImporting = ref(false)
const createImportResult = ref<any>(null)
const createUploadRef = ref()

watch(createCountry, () => {
  createTemplateId.value = null
  createSelectedTpl.value = null
})

function onCreateTplChange(id: number | null) {
  if (!id) { createSelectedTpl.value = null; return }
  const tpl = tplList.value.find((tp: PricingTemplate) => tp.id === id) || null
  createSelectedTpl.value = tpl
  if (tpl) {
    const iso = createCountryIso.value || (tpl.country_code !== '*' ? tpl.country_code : '')
    const cName = iso ? countryName(iso) : '全球'
    form.product_code = `${iso || 'ALL'}-${tpl.source}-${tpl.purpose}-${tpl.freshness}`
    form.product_name = `${cName}-${tpl.source_label}-${tpl.purpose_label}-${tpl.freshness_label}`
    form.price_per_number = Number(tpl.price_per_number)
    form._filter_criteria = {
      country: iso || undefined,
      source: tpl.source,
      purpose: tpl.purpose,
      freshness: tpl.freshness,
    }
  }
}

function handleCreateFileChange(file: any) {
  const maxSize = 500 * 1024 * 1024
  if (file.raw && file.raw.size > maxSize) {
    ElMessage.warning('文件大小不能超过 500MB')
    createFile.value = null
    createUploadRef.value?.clearFiles()
    return
  }
  createFile.value = file.raw
}

async function submitCreateWithImport() {
  if (!createFile.value) {
    ElMessage.warning('请选择要上传的数据文件')
    return
  }
  if (!createSelectedTpl.value) {
    ElMessage.warning('请先选择定价模板')
    return
  }
  createImporting.value = true
  createImportResult.value = null
  try {
    const tpl = createSelectedTpl.value
    const formData = new FormData()
    formData.append('file', createFile.value)
    const params: any = {
      source: tpl.source,
      purpose: tpl.purpose,
      freshness: tpl.freshness,
      pricing_template_id: tpl.id,
    }
    if (createCountry.value) params.country_code = createCountry.value
    const res = await importNumbers(formData, params)
    if (res.success) {
      createImportResult.value = res
      ElMessage.success('导入任务已提交，商品将在导入完成后自动创建')
      setTimeout(() => loadData(), 3000)
    }
  } catch (e: any) {
    ElMessage.error('导入失败: ' + (e.message || ''))
  } finally {
    createImporting.value = false
  }
}

async function loadTplList() {
  tplLoading.value = true
  try {
    const res = await getPricingTemplates({ page: 1, page_size: 500, status: 'active' })
    tplList.value = res.items || []
  } catch { tplList.value = [] }
  finally { tplLoading.value = false }
}

// --- 打开弹窗 ---
function openCreateDialog() {
  isEdit.value = false
  currentId.value = null
  form.product_code = ''
  form.product_name = ''
  form.price_per_number = 0.1
  form.min_purchase = 100
  form.max_purchase = 100000
  form.status = 'active'
  form._filter_criteria = {}
  createCountry.value = ''
  createTemplateId.value = null
  createSelectedTpl.value = null
  createFile.value = null
  createImporting.value = false
  createImportResult.value = null
  dialogVisible.value = true
  loadTplList()
}

function openEditDialog(row: any) {
  isEdit.value = true
  currentId.value = row.id
  form.product_code = row.product_code
  form.product_name = row.product_name
  form.price_per_number = Number(row.price_per_number)
  form.min_purchase = row.min_purchase
  form.max_purchase = row.max_purchase
  form.status = row.status
  form._filter_criteria = row.filter_criteria || {}
  dialogVisible.value = true
}

function resetForm() {
  formRef.value?.resetFields()
}

async function submitForm() {
  if (!form.product_code || !form.product_name) {
    ElMessage.warning('请选择定价模板或填写商品编码和名称')
    return
  }

  submitting.value = true
  try {
    if (isEdit.value && currentId.value) {
      await updateProduct(currentId.value, {
        product_name: form.product_name,
        price_per_number: String(form.price_per_number),
        min_purchase: form.min_purchase,
        max_purchase: form.max_purchase,
        status: form.status,
      })
    } else {
      const criteria = { ...form._filter_criteria }
      await createProduct({
        product_code: form.product_code,
        product_name: form.product_name,
        filter_criteria: criteria,
        price_per_number: String(form.price_per_number),
        min_purchase: form.min_purchase,
        max_purchase: form.max_purchase,
        product_type: 'data_only',
      })
    }
    ElMessage.success('操作成功')
    dialogVisible.value = false
    loadData()
  } catch (e: any) {
    ElMessage.error(e.message || '操作失败')
  } finally {
    submitting.value = false
  }
}

// ====== 操作 ======
async function handleRefreshStock(row: any) {
  try {
    const res = await refreshProductStock(row.id)
    if (res.success) {
      row.stock_count = res.stock_count
      row.unsold_count = res.stock_count
      row.total_quantity = res.stock_count + (row.total_sold || 0)
      if (res.status) row.status = res.status
      ElMessage.success(`库存已更新: ${res.stock_count.toLocaleString()}`)
    }
  } catch { ElMessage.error('刷新库存失败') }
}

async function handleDelete(row: any) {
  try {
    await ElMessageBox.confirm(`确定删除商品「${row.product_name}」？`, '确认', { type: 'warning' })
    await deleteProduct(row.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}
</script>

<style scoped>
.products-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-card :deep(.el-card__body) {
  padding: 16px;
}

.tpl-info-card {
  margin-bottom: 16px;
  background: var(--el-fill-color-light);
}
.tpl-info-card :deep(.el-card__body) {
  padding: 12px;
}
.import-result-card {
  margin: 12px 0;
  border-color: var(--el-color-success-light-5);
  background: var(--el-color-success-light-9);
}
.import-result-card :deep(.el-card__body) {
  padding: 8px 12px;
}
</style>
