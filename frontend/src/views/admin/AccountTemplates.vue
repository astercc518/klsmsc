<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">{{ $t('accountTemplates.title') }}</h1>
        <p class="page-desc">{{ $t('accountTemplates.pageDesc') }}</p>
      </div>
      <el-button type="primary" @click="showCreateDialog">
        <el-icon><Plus /></el-icon>
        {{ $t('accountTemplates.addTemplate') }}
      </el-button>
    </div>

    <!-- 筛选 -->
    <div class="filter-card">
      <el-form :inline="true" :model="filters">
        <el-form-item :label="$t('accountTemplates.businessType')">
          <el-select v-model="filters.business_type" :placeholder="$t('accountTemplates.allTypes')" clearable>
            <el-option :label="$t('accountTemplates.sms')" value="sms" />
            <el-option :label="$t('accountTemplates.data')" value="data" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('accountTemplates.country')">
          <el-autocomplete
            v-model="filterCountryDisplay"
            :fetch-suggestions="countryQuerySearch"
            :placeholder="$t('accountTemplates.filterCountryPlaceholder')"
            value-key="name"
            clearable
            style="width: 180px;"
            @select="handleFilterCountrySelect"
            @clear="filters.country_code = ''"
          >
            <template #default="{ item }">
              <span>{{ item.name }}</span>
              <span style="float: right; color: var(--el-text-color-secondary); font-size: 12px;">
                +{{ item.dial }} ({{ item.iso }})
              </span>
            </template>
          </el-autocomplete>
        </el-form-item>
        <el-form-item :label="$t('common.status')">
          <el-select v-model="filters.status" :placeholder="$t('accountTemplates.allStatus')" clearable>
            <el-option :label="$t('common.enable')" value="active" />
            <el-option :label="$t('common.disable')" value="inactive" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">{{ $t('smsRecords.query') }}</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 数据表格 -->
    <div class="table-card">
      <el-table :data="templates" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="template_code" :label="$t('accountTemplates.templateCode')" width="130" />
        <el-table-column prop="template_name" :label="$t('accountTemplates.templateName')" min-width="150" />
        <el-table-column prop="business_type" :label="$t('accountTemplates.businessType')" width="100">
          <template #default="{ row }">
            <el-tag :type="getBusinessTypeColor(row.business_type)">
              {{ getBusinessTypeLabel(row.business_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="country_code" :label="$t('accountTemplates.country')" width="120">
          <template #default="{ row }">
            <span>{{ row.country_name || row.country_code }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="default_price" :label="$t('accountTemplates.defaultPrice')" width="100">
          <template #default="{ row }">
            ${{ row.default_price?.toFixed(4) || '0.0000' }}
          </template>
        </el-table-column>
        <el-table-column prop="supplier_group_name" :label="$t('accountTemplates.supplierGroup')" width="140">
          <template #default="{ row }">
            {{ row.supplier_group_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="channel_ids" :label="$t('accountTemplates.channels')" min-width="160">
          <template #default="{ row }">
            {{ getChannelDisplay(row.channel_ids) || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('common.status')" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'danger'">
              {{ row.status === 'active' ? $t('common.enable') : $t('common.disable') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="$t('common.createdAt')" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="editTemplate(row)">{{ $t('common.edit') }}</el-button>
            <el-button 
              size="small" 
              :type="row.status === 'active' ? 'warning' : 'success'"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'active' ? $t('common.disable') : $t('common.enable') }}
            </el-button>
            <el-button size="small" type="danger" @click="deleteTemplate(row)">{{ $t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
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
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog 
      v-model="dialogVisible" 
      :title="isEdit ? $t('accountTemplates.editTemplate') : $t('accountTemplates.addTemplate')"
      width="600px"
    >
      <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="$t('accountTemplates.templateName')" prop="template_name">
              <el-input v-model="form.template_name" :placeholder="$t('accountTemplates.templateNamePlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('accountTemplates.templateCode')">
              <el-input v-model="form.template_code" :placeholder="$t('accountTemplates.autoGenerate')" disabled />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="$t('accountTemplates.businessType')" prop="business_type">
              <el-select v-model="form.business_type" :placeholder="$t('accountTemplates.selectBusinessType')" :disabled="isEdit">
                <el-option :label="$t('accountTemplates.sms')" value="sms" />
                <el-option :label="$t('accountTemplates.data')" value="data" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('accountTemplates.countryName')" prop="country_name">
              <el-autocomplete
                v-model="form.country_name"
                :fetch-suggestions="countryQuerySearch"
                :placeholder="$t('accountTemplates.countrySearchPlaceholder')"
                value-key="name"
                clearable
                @select="handleCountrySelect"
                @clear="form.country_code = ''"
              >
                <template #default="{ item }">
                  <span>{{ item.name }}</span>
                  <span style="float: right; color: var(--el-text-color-secondary); font-size: 12px;">
                    +{{ item.dial }} ({{ item.iso }})
                  </span>
                </template>
              </el-autocomplete>
              <div v-if="form.country_code" class="country-code-hint">
                {{ $t('accountTemplates.countryCode') }}: {{ form.country_code }}
              </div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="$t('accountTemplates.defaultPrice')">
              <el-input-number v-model="form.default_price" :min="0" :precision="4" :step="0.01" style="width: 100%;" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="$t('accountTemplates.supplierGroupId')">
              <el-input v-model="form.supplier_group_id" :placeholder="$t('accountTemplates.supplierGroupIdPlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('accountTemplates.supplierGroupName')">
              <el-input v-model="form.supplier_group_name" :placeholder="$t('accountTemplates.supplierGroupNamePlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item :label="$t('accountTemplates.linkedChannels')" v-if="form.business_type === 'sms'">
          <el-select v-model="form.channel_ids" multiple :placeholder="$t('accountTemplates.selectChannels')" style="width: 100%;">
            <el-option 
              v-for="ch in channels" 
              :key="ch.id" 
              :label="`${ch.channel_code} - ${ch.channel_name}`" 
              :value="ch.id" 
            />
          </el-select>
        </el-form-item>

        <el-form-item :label="$t('accountTemplates.externalProductId')" v-if="form.business_type !== 'sms'">
          <el-input v-model="form.external_product_id" :placeholder="$t('accountTemplates.externalProductIdPlaceholder')" />
        </el-form-item>

        <el-form-item :label="$t('accountTemplates.description')">
          <el-input v-model="form.description" type="textarea" :rows="2" :placeholder="$t('accountTemplates.descriptionPlaceholder')" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import request from '@/api/index'
import { formatDate } from '@/utils/date'
import { searchCountries, COUNTRY_LIST, type CountryItem } from '@/constants/countries'

const { t } = useI18n()

// 国家快速搜索：支持名称、区号(如84)、ISO代码
const countryQuerySearch = (queryString: string, cb: (results: CountryItem[]) => void) => {
  const results = queryString ? searchCountries(queryString) : searchCountries('')
  cb(results)
}

// 选择国家后自动填充国家代码
const handleCountrySelect = (item: CountryItem) => {
  form.value.country_name = item.name
  form.value.country_code = item.iso
}

// 筛选区：选择国家后设置 country_code
const filterCountryDisplay = ref('')
const handleFilterCountrySelect = (item: CountryItem) => {
  filters.value.country_code = item.iso
  filterCountryDisplay.value = item.name
}

interface Template {
  id: number
  template_code: string
  template_name: string
  business_type: string
  country_code: string
  country_name?: string
  supplier_group_id?: number
  supplier_group_name?: string
  channel_ids?: number[]
  external_product_id?: string
  default_price?: number
  description?: string
  status: string
  created_at?: string
}

interface Channel {
  id: number
  channel_code: string
  channel_name: string
}

const loading = ref(false)
const templates = ref<Template[]>([])
const channels = ref<Channel[]>([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const currentTemplateId = ref<number | null>(null)
const submitting = ref(false)

const filters = ref({
  business_type: '',
  country_code: '',
  status: ''
})

const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0
})

const form = ref({
  template_code: '',
  template_name: '',
  business_type: 'sms',
  country_code: '',
  country_name: '',
  supplier_group_id: '',
  supplier_group_name: '',
  channel_ids: [] as number[],
  external_product_id: '',
  default_price: 0,
  description: ''
})

const formRef = ref()

const rules = computed(() => ({
  template_name: [{ required: true, message: t('accountTemplates.pleaseEnterTemplateName'), trigger: 'blur' }],
  business_type: [{ required: true, message: t('accountTemplates.pleaseSelectBusinessType'), trigger: 'change' }],
  country_name: [{ required: true, message: t('accountTemplates.pleaseSelectCountry'), trigger: 'change' }]
}))

const getBusinessTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    sms: t('accountTemplates.sms'),
    data: t('accountTemplates.data')
  }
  return map[type] || type
}

const getBusinessTypeColor = (type: string) => {
  const map: Record<string, string> = {
    sms: 'primary',
    data: 'warning'
  }
  return map[type] || 'info'
}

// 根据 channel_ids 显示通道名称
const getChannelDisplay = (channelIds?: number[]) => {
  if (!channelIds?.length) return ''
  const names = channelIds
    .map(id => channels.value.find(c => c.id === id))
    .filter(Boolean)
    .map(c => `${(c as Channel).channel_code} - ${(c as Channel).channel_name}`)
  return names.join('、')
}

const loadData = async () => {
  // 若用户输入了国家但未从下拉选择，尝试解析（支持名称、代码、区号如84）
  let countryCode = filters.value.country_code
  if (filterCountryDisplay.value && !countryCode) {
    const matches = searchCountries(filterCountryDisplay.value.trim())
    if (matches.length === 1) {
      countryCode = matches[0].iso
      filters.value.country_code = countryCode
    } else if (matches.length > 1) {
      const q = filterCountryDisplay.value.trim()
      const exact = matches.find(c =>
        c.name === q || c.iso.toUpperCase() === q.toUpperCase() || c.dial === q
      )
      if (exact) {
        countryCode = exact.iso
        filters.value.country_code = countryCode
      }
    }
  }

  loading.value = true
  try {
    const params = new URLSearchParams()
    if (filters.value.business_type) params.append('business_type', filters.value.business_type)
    if (countryCode) params.append('country_code', countryCode)
    if (filters.value.status) params.append('status', filters.value.status)
    params.append('page', String(pagination.value.page))
    params.append('page_size', String(pagination.value.pageSize))
    
    const res = await request.get(`/admin/account-templates?${params.toString()}`)
    if (res.success) {
      templates.value = res.items
      pagination.value.total = res.total
    }
  } catch (e: any) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    loading.value = false
  }
}

const loadChannels = async () => {
  try {
    const res = await request.get('/admin/channels')
    if (res.success) {
      channels.value = res.channels || []
    }
  } catch (e) {
    console.error('Load channels failed', e)
  }
}

const showCreateDialog = () => {
  isEdit.value = false
  currentTemplateId.value = null
  form.value = {
    template_code: '',
    template_name: '',
    business_type: 'sms',
    country_code: '',
    country_name: '',
    supplier_group_id: '',
    supplier_group_name: '',
    channel_ids: [],
    external_product_id: '',
    default_price: 0,
    description: ''
  }
  dialogVisible.value = true
}

const editTemplate = (row: Template) => {
  isEdit.value = true
  currentTemplateId.value = row.id
  // 若仅有国家代码无名称，从列表反查国家名称
  let countryName = row.country_name || ''
  if (!countryName && row.country_code) {
    const c = COUNTRY_LIST.find(x => x.iso === row.country_code || x.dial === row.country_code)
    if (c) countryName = c.name
  }
  form.value = {
    template_code: row.template_code,
    template_name: row.template_name,
    business_type: row.business_type,
    country_code: row.country_code,
    country_name: countryName,
    supplier_group_id: row.supplier_group_id ? String(row.supplier_group_id) : '',
    supplier_group_name: row.supplier_group_name || '',
    channel_ids: row.channel_ids || [],
    external_product_id: row.external_product_id || '',
    default_price: row.default_price || 0,
    description: row.description || ''
  }
  dialogVisible.value = true
}

const submitForm = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  // 若用户输入了国家名称但未从下拉选择，尝试根据名称匹配国家代码
  if (form.value.country_name && !form.value.country_code) {
    const matched = COUNTRY_LIST.find(
      c => c.name === form.value.country_name || c.en.toLowerCase() === form.value.country_name.toLowerCase()
    )
    if (matched) {
      form.value.country_code = matched.iso
    } else {
      ElMessage.warning(t('accountTemplates.pleaseSelectCountry'))
      return
    }
  }

  if (!form.value.country_code) {
    ElMessage.warning(t('accountTemplates.pleaseSelectCountry'))
    return
  }
  
  submitting.value = true
  try {
    const payload = {
      ...form.value,
      supplier_group_id: form.value.supplier_group_id ? parseInt(form.value.supplier_group_id) : null
    }
    
    if (isEdit.value && currentTemplateId.value) {
      await request.put(`/admin/account-templates/${currentTemplateId.value}`, payload)
      ElMessage.success(t('accountTemplates.updateSuccess'))
    } else {
      await request.post('/admin/account-templates', payload)
      ElMessage.success(t('accountTemplates.createSuccess'))
    }
    dialogVisible.value = false
    loadData()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || e.message || t('common.failed'))
  } finally {
    submitting.value = false
  }
}

const toggleStatus = async (row: Template) => {
  const newStatus = row.status === 'active' ? 'inactive' : 'active'
  const action = newStatus === 'active' ? t('common.enable') : t('common.disable')
  
  try {
    await ElMessageBox.confirm(
      t('accountTemplates.confirmToggleStatus', { action, name: row.template_name }),
      t('dialog.confirmTitle')
    )
    await request.put(`/admin/account-templates/${row.id}`, { status: newStatus })
    ElMessage.success(t('accountTemplates.statusChanged', { action }))
    loadData()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.detail || t('common.failed'))
    }
  }
}

const deleteTemplate = async (row: Template) => {
  try {
    await ElMessageBox.confirm(
      t('accountTemplates.confirmDelete', { name: row.template_name }), 
      t('dialog.deleteTitle'),
      { type: 'warning' }
    )
    await request.delete(`/admin/account-templates/${row.id}`)
    ElMessage.success(t('accountTemplates.deleteSuccess'))
    loadData()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.detail || t('common.failed'))
    }
  }
}

onMounted(() => {
  loadData()
  loadChannels()
})
</script>

<style scoped>
.page-container {
  width: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.page-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

.filter-card {
  background: var(--bg-card);
  padding: 16px 24px;
  border-radius: 12px;
  border: 1px solid var(--border-default);
  margin-bottom: 24px;
}

.table-card {
  background: var(--bg-card);
  padding: 16px;
  border-radius: 12px;
  border: 1px solid var(--border-default);
}

.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.country-code-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
