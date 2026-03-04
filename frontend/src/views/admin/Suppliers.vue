<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">{{ $t('suppliers.title') }}</h1>
        <p class="page-desc">{{ $t('suppliers.pageDesc') }}</p>
      </div>
      <div class="header-right">
        <el-button @click="loadSuppliers" :icon="Refresh">{{ $t('common.refresh') }}</el-button>
        <el-button type="primary" @click="showCreateDialog">
          <el-icon><Plus /></el-icon>
          {{ $t('suppliers.addSupplier') }}
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon active">
          <el-icon><CircleCheck /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.active_count }}</div>
          <div class="stat-label">{{ $t('suppliers.active') }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon total">
          <el-icon><OfficeBuilding /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_count }}</div>
          <div class="stat-label">{{ $t('suppliers.totalSuppliers') }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon sms">
          <el-icon><Message /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.sms_count }}</div>
          <div class="stat-label">{{ $t('suppliers.hasRates') }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon voice">
          <el-icon><Phone /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.voice_count }}</div>
          <div class="stat-label">{{ $t('suppliers.hasCountries') }}</div>
        </div>
      </div>
    </div>

    <!-- 搜索筛选 -->
    <div class="filter-bar">
      <el-input v-model="filters.keyword" :placeholder="$t('suppliers.searchPlaceholder')" clearable style="width: 200px" @keyup.enter="loadSuppliers">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="filters.business_type" :placeholder="$t('suppliers.businessType')" clearable style="width: 120px" @change="loadSuppliers">
        <el-option :label="$t('suppliers.sms')" value="sms" />
        <el-option :label="$t('suppliers.voice')" value="voice" />
        <el-option :label="$t('suppliers.data')" value="data" />
      </el-select>
      <el-select v-model="filters.resource_type" :placeholder="$t('suppliers.resourceType')" clearable style="width: 130px" @change="loadSuppliers">
        <el-option :label="$t('suppliers.otp')" value="otp" />
        <el-option :label="$t('suppliers.marketing')" value="marketing" />
        <el-option :label="$t('suppliers.notification')" value="notification" />
        <el-option :label="$t('suppliers.international')" value="international" />
      </el-select>
      <el-select v-model="filters.status" :placeholder="$t('common.status')" clearable style="width: 100px" @change="loadSuppliers">
        <el-option :label="$t('suppliers.active')" value="active" />
        <el-option :label="$t('suppliers.inactive')" value="inactive" />
      </el-select>
      <el-button @click="resetFilters">{{ $t('common.reset') }}</el-button>
    </div>

    <!-- 供应商列表 -->
    <div class="table-card">
      <el-table :data="suppliers" v-loading="loading" class="data-table">
        <el-table-column prop="supplier_name" :label="$t('suppliers.supplierName')" min-width="150">
          <template #default="{ row }">
            <div class="supplier-cell">
              <span class="supplier-name">{{ row.supplier_name }}</span>
              <el-tag v-if="row.status === 'active'" type="success" size="small" effect="plain">{{ $t('suppliers.active') }}</el-tag>
              <el-tag v-else type="info" size="small" effect="plain">{{ $t('suppliers.inactive') }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="supplier_group" :label="$t('suppliers.supplierGroup')" width="130">
          <template #default="{ row }">
            <span>{{ row.supplier_group || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rate_count" :label="$t('suppliers.rateCount')" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.rate_count > 0" type="success" size="small">{{ row.rate_count }} {{ $t('suppliers.items') }}</el-tag>
            <span v-else class="no-rate">{{ $t('suppliers.notConfigured') }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="country_count" :label="$t('suppliers.coveredCountries')" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.country_count > 0">{{ row.country_count }} {{ $t('suppliers.units') }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="notes" :label="$t('suppliers.notes')" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="notes-text">{{ row.notes || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="200" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="success" link size="small" @click="showRatesDialog(row)">{{ $t('suppliers.rateTable') }}</el-button>
            <el-button type="primary" link size="small" @click="editSupplier(row)">{{ $t('common.edit') }}</el-button>
            <el-popconfirm :title="$t('suppliers.confirmDelete')" @confirm="deleteSupplier(row)">
              <template #reference>
                <el-button type="danger" link size="small">{{ $t('common.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next, sizes"
          :total="pagination.total"
          :page-size="pagination.pageSize"
          :current-page="pagination.page"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="(p:number) => { pagination.page = p; loadSuppliers() }"
          @size-change="(s:number) => { pagination.pageSize = s; pagination.page = 1; loadSuppliers() }"
        />
      </div>
    </div>

    <!-- 创建/编辑供应商对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? $t('suppliers.editSupplier') : $t('suppliers.addSupplier')"
      width="650px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="$t('suppliers.supplierName')" prop="supplier_name">
              <el-input v-model="form.supplier_name" :placeholder="$t('suppliers.supplierName')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('suppliers.supplierGroup')">
              <el-input v-model="form.supplier_group" :placeholder="$t('suppliers.groupNameOptional')" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="$t('common.status')">
              <el-select v-model="form.status" style="width: 100%">
                <el-option :label="$t('suppliers.active')" value="active" />
                <el-option :label="$t('suppliers.inactive')" value="inactive" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('suppliers.costCurrency')">
              <el-select v-model="form.cost_currency" style="width: 100%">
                <el-option label="USD" value="USD" />
                <el-option label="CNY" value="CNY" />
                <el-option label="EUR" value="EUR" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-alert type="info" :closable="false" style="margin-bottom: 16px">
          <template #title>
            <span>{{ $t('suppliers.multiBusinessTip') }}</span>
          </template>
        </el-alert>

        <el-divider content-position="left">{{ $t('suppliers.contactInfoOptional') }}</el-divider>
        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item :label="$t('suppliers.contactPerson')">
              <el-input v-model="form.contact_person" :placeholder="$t('suppliers.contactPerson')" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="$t('suppliers.contactPhone')">
              <el-input v-model="form.contact_phone" :placeholder="$t('suppliers.contactPhone')" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="$t('suppliers.contactEmail')">
              <el-input v-model="form.contact_email" :placeholder="$t('suppliers.contactEmail')" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item :label="$t('suppliers.notes')">
          <el-input v-model="form.notes" type="textarea" :rows="2" :placeholder="$t('suppliers.notesPlaceholder')" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">
          {{ isEdit ? $t('common.save') : $t('dialog.create') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 报价表对话框 -->
    <el-dialog
      v-model="ratesDialogVisible"
      :title="`${$t('suppliers.rateTable')} - ${currentSupplier?.supplier_name || ''}`"
      width="900px"
      destroy-on-close
    >
      <div class="rates-header">
        <el-button type="primary" size="small" @click="showAddRateDialog">
          <el-icon><Plus /></el-icon>
          {{ $t('suppliers.addRate') }}
        </el-button>
        <el-button type="success" size="small" @click="showBatchAddDialog">
          <el-icon><DocumentAdd /></el-icon>
          {{ $t('suppliers.batchAdd') }}
        </el-button>
        <el-divider direction="vertical" />
        <el-button size="small" @click="downloadTemplate">
          <el-icon><Download /></el-icon>
          {{ $t('suppliers.downloadTemplate') }}
        </el-button>
        <el-upload
          ref="uploadRef"
          :auto-upload="false"
          :show-file-list="false"
          accept=".csv,.xlsx,.xls"
          :on-change="handleFileChange"
        >
          <el-button type="warning" size="small">
            <el-icon><Upload /></el-icon>
            {{ $t('suppliers.importRates') }}
          </el-button>
        </el-upload>
      </div>

      <el-table :data="supplierRates" v-loading="ratesLoading" class="rates-table">
        <el-table-column prop="country_code" :label="$t('suppliers.country')" width="100">
          <template #default="{ row }">
            {{ getCountryName(row.country_code) }}
          </template>
        </el-table-column>
        <el-table-column prop="resource_type" :label="$t('suppliers.resourceType')" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="resourceTypeTagMap[row.resource_type] || ''">
              {{ getResourceTypeLabel(row.resource_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="business_scope" :label="$t('suppliers.businessScope')" width="90">
          <template #default="{ row }">
            <el-tag size="small" type="info">
              {{ getBusinessScopeLabel(row.business_scope) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="cost_price" :label="$t('suppliers.cost')" width="100" align="right">
          <template #default="{ row }">
            <span class="cost-text">${{ formatCost(row.cost_price) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sell_price" :label="$t('suppliers.sellPrice')" width="100" align="right">
          <template #default="{ row }">
            <span class="sell-text">${{ formatCost(row.sell_price) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" :label="$t('suppliers.notes')" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.remark || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('common.status')" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
              {{ row.status === 'active' ? $t('suppliers.active') : $t('suppliers.inactive') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="100" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="editRate(row)">{{ $t('common.edit') }}</el-button>
            <el-popconfirm :title="$t('suppliers.confirmDeleteRate')" @confirm="deleteRate(row)">
              <template #reference>
                <el-button type="danger" link size="small">{{ $t('common.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 添加/编辑报价对话框 -->
    <el-dialog
      v-model="rateFormDialogVisible"
      :title="isEditRate ? $t('suppliers.editRate') : $t('suppliers.addRate')"
      width="550px"
      destroy-on-close
    >
      <el-form ref="rateFormRef" :model="rateForm" :rules="rateRules" label-width="90px">
        <el-form-item :label="$t('suppliers.businessType')" prop="business_type">
          <el-radio-group v-model="rateForm.business_type" @change="onBusinessTypeChange">
            <el-radio-button value="sms">
              <el-icon><Message /></el-icon> {{ $t('suppliers.sms') }}
            </el-radio-button>
            <el-radio-button value="voice">
              <el-icon><Phone /></el-icon> {{ $t('suppliers.voice') }}
            </el-radio-button>
            <el-radio-button value="data">
              <el-icon><Connection /></el-icon> {{ $t('suppliers.data') }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="$t('suppliers.country')" prop="country_code">
          <el-select 
            v-model="rateForm.country_code" 
            filterable 
            allow-create 
            :reserve-keyword="false"
            :placeholder="$t('suppliers.selectCountryPlaceholder')" 
            style="width: 100%"
          >
            <el-option v-for="item in allCountries" :key="item.code" :label="`${item.name} (${item.code})`" :value="item.code" />
          </el-select>
          <div class="form-tip">{{ $t('suppliers.countryInputTip') }}</div>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="$t('suppliers.resourceType')" prop="resource_type">
              <el-select 
                v-model="rateForm.resource_type" 
                filterable 
                allow-create 
                :reserve-keyword="false"
                :placeholder="$t('suppliers.selectTypePlaceholder')" 
                style="width: 100%"
              >
                <el-option v-for="item in resourceTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('suppliers.businessScope')" prop="business_scope">
              <el-select 
                v-model="rateForm.business_scope" 
                filterable 
                allow-create 
                :reserve-keyword="false"
                :placeholder="$t('suppliers.selectScopePlaceholder')" 
                style="width: 100%"
              >
                <el-option v-for="item in businessScopeOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="$t('suppliers.cost')" prop="cost_price">
              <el-input-number v-model="rateForm.cost_price" :min="0" :precision="6" :step="0.001" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('suppliers.sellPrice')" prop="sell_price">
              <el-input-number v-model="rateForm.sell_price" :min="0" :precision="6" :step="0.001" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="$t('suppliers.notes')">
          <el-input v-model="rateForm.remark" type="textarea" :rows="2" :placeholder="$t('suppliers.notesPlaceholder')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rateFormDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="rateSubmitting" @click="submitRateForm">{{ $t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 批量添加报价对话框 -->
    <el-dialog
      v-model="batchDialogVisible"
      :title="$t('suppliers.batchAddRates')"
      width="1100px"
      destroy-on-close
    >
      <div class="batch-tips">
        <el-alert type="info" :closable="false">
          <template #title>
            <span>{{ $t('suppliers.batchAddTip') }}</span>
          </template>
        </el-alert>
      </div>
      
      <el-table :data="batchRates" class="batch-table" max-height="400">
        <el-table-column :label="$t('suppliers.businessType')" width="90">
          <template #default="{ row }">
            <el-select v-model="row.business_type" size="small" style="width: 100%" @change="(val: string) => { row.resource_type = getResourceTypeOptions(val)[0]?.value || '' }">
              <el-option :label="$t('suppliers.sms')" value="sms" />
              <el-option :label="$t('suppliers.voice')" value="voice" />
              <el-option :label="$t('suppliers.data')" value="data" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column :label="$t('suppliers.country')" width="150">
          <template #default="{ row }">
            <el-select 
              v-model="row.country_code" 
              filterable 
              allow-create
              size="small"
              :placeholder="$t('suppliers.selectCountry')"
              style="width: 100%"
            >
              <el-option v-for="item in allCountries" :key="item.code" :label="`${item.name} (${item.code})`" :value="item.code" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column :label="$t('suppliers.resourceType')" width="110">
          <template #default="{ row }">
            <el-select 
              v-model="row.resource_type" 
              filterable 
              allow-create
              size="small"
              :placeholder="$t('suppliers.type')"
              style="width: 100%"
            >
              <el-option v-for="item in getResourceTypeOptions(row.business_type)" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column :label="$t('suppliers.businessScope')" width="100">
          <template #default="{ row }">
            <el-select 
              v-model="row.business_scope" 
              filterable 
              allow-create
              size="small"
              :placeholder="$t('suppliers.scope')"
              style="width: 100%"
            >
              <el-option v-for="item in businessScopeOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column :label="$t('suppliers.cost')" width="100">
          <template #default="{ row }">
            <el-input-number v-model="row.cost_price" :min="0" :precision="6" :step="0.001" size="small" :controls="false" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column :label="$t('suppliers.sellPrice')" width="100">
          <template #default="{ row }">
            <el-input-number v-model="row.sell_price" :min="0" :precision="6" :step="0.001" size="small" :controls="false" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column :label="$t('suppliers.notes')" min-width="100">
          <template #default="{ row }">
            <el-input v-model="row.remark" size="small" :placeholder="$t('suppliers.notes')" />
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="60" align="center">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="removeBatchRow($index)">{{ $t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="batch-actions">
        <el-button size="small" @click="addBatchRow">
          <el-icon><Plus /></el-icon>
          {{ $t('suppliers.addRow') }}
        </el-button>
        <el-button size="small" @click="addBatchRows(5)">{{ $t('suppliers.add5Rows') }}</el-button>
        <el-button size="small" @click="addBatchRows(10)">{{ $t('suppliers.add10Rows') }}</el-button>
      </div>

      <template #footer>
        <el-button @click="batchDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="batchSubmitting" @click="submitBatchRates">
          {{ $t('suppliers.batchSave') }} ({{ validBatchCount }} {{ $t('suppliers.items') }})
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Refresh, Search, CircleCheck, OfficeBuilding, Message, Phone, DocumentAdd, Download, Upload, Connection, Grid } from '@element-plus/icons-vue'
import {
  getSuppliers, createSupplier, updateSupplier, deleteSupplier as deleteSupplierApi,
  type Supplier
} from '@/api/supplier'

const { t } = useI18n()

// 映射函数 - 使用 i18n
const getBusinessTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    sms: t('suppliers.sms'),
    voice: t('suppliers.voice'),
    data: t('suppliers.data')
  }
  return map[type] || type
}

const getResourceTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    // SMS
    card: t('suppliers.smsCard'),
    direct: t('suppliers.smsDirect'),
    ws_bulk: t('suppliers.smsWsBulk'),
    two_way: t('suppliers.smsTwoWay'),
    rcs: t('suppliers.smsRcs'),
    // Voice
    passthrough: t('suppliers.voicePassthrough'),
    local_display: t('suppliers.voiceLocalDisplay'),
    international: t('suppliers.voiceInternational'),
    // Data
    credential_stuffing: t('suppliers.dataCredentialStuffing'),
    penetration: t('suppliers.dataPenetration'),
    social_db: t('suppliers.dataSocialDb'),
    bc_recall: t('suppliers.dataBcRecall'),
    telemarketing: t('suppliers.dataTelemarketing'),
  }
  return map[type] || type
}

const getBusinessScopeLabel = (scope: string) => {
  const map: Record<string, string> = {
    marketing: t('suppliers.scopeMarketing'),
    otp: t('suppliers.scopeOtp'),
    gambling: t('suppliers.scopeGambling'),
    parttime: t('suppliers.scopeParttime'),
    stock: t('suppliers.scopeStock'),
    dating: t('suppliers.scopeDating'),
  }
  return map[scope] || scope
}

const businessTypeTag = (type: string) => {
  const map: Record<string, string> = {
    sms: 'primary',
    voice: 'success',
    data: 'warning'
  }
  return map[type] || ''
}

const formatCost = (value: number | undefined) => {
  return (value || 0).toFixed(4)
}

// 数据
const loading = ref(false)
const suppliers = ref<Supplier[]>([])
const stats = reactive({
  active_count: 0,
  total_count: 0,
  sms_count: 0,
  voice_count: 0
})
const filters = reactive({
  keyword: '',
  status: ''
})
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

// 供应商表单
const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const currentSupplier = ref<Supplier | null>(null)

const form = reactive({
  supplier_code: '',
  supplier_name: '',
  supplier_group: '',
  cost_currency: 'USD',
  contact_person: '',
  contact_phone: '',
  contact_email: '',
  status: 'active',
  notes: ''
})

const rules = computed<FormRules>(() => ({
  supplier_name: [{ required: true, message: t('suppliers.pleaseEnterSupplierName'), trigger: 'blur' }],
  business_type: [{ required: true, message: t('suppliers.pleaseSelectBusinessType'), trigger: 'change' }]
}))

// 方法
const loadSuppliers = async () => {
  loading.value = true
  try {
    const res: any = await getSuppliers({
      page: pagination.page,
      page_size: pagination.pageSize,
      status: filters.status || undefined,
      keyword: filters.keyword || undefined
    })
    if (res.success) {
      suppliers.value = res.suppliers
      pagination.total = res.total
      // 计算统计
      stats.total_count = res.total
      stats.active_count = suppliers.value.filter(s => s.status === 'active').length
      // 以下统计将基于报价数据，暂时显示有报价的供应商数
      stats.sms_count = suppliers.value.filter(s => s.rate_count > 0).length
      stats.voice_count = suppliers.value.filter(s => s.country_count > 0).length
    }
  } catch (error) {
    console.error('Failed to load suppliers:', error)
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  filters.keyword = ''
  filters.business_type = ''
  filters.resource_type = ''
  filters.status = ''
  pagination.page = 1
  loadSuppliers()
}

const generateCode = () => {
  return 'SP' + Date.now().toString(36).toUpperCase()
}

const showCreateDialog = () => {
  isEdit.value = false
  Object.assign(form, {
    supplier_code: generateCode(),
    supplier_name: '',
    supplier_group: '',
    cost_currency: 'USD',
    contact_person: '',
    contact_phone: '',
    contact_email: '',
    status: 'active',
    notes: ''
  })
  dialogVisible.value = true
}

const editSupplier = (row: Supplier) => {
  isEdit.value = true
  currentSupplier.value = row
  Object.assign(form, {
    supplier_code: row.supplier_code,
    supplier_name: row.supplier_name,
    supplier_group: row.supplier_group || '',
    cost_currency: row.cost_currency || 'USD',
    contact_person: row.contact_person || '',
    contact_phone: row.contact_phone || '',
    contact_email: row.contact_email || '',
    status: row.status,
    notes: row.notes || ''
  })
  dialogVisible.value = true
}

const submitForm = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      if (isEdit.value && currentSupplier.value) {
        await updateSupplier(currentSupplier.value.id, form)
        ElMessage.success(t('suppliers.updateSuccess'))
      } else {
        await createSupplier(form)
        ElMessage.success(t('suppliers.createSuccess'))
      }
      dialogVisible.value = false
      loadSuppliers()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('common.failed'))
    } finally {
      submitting.value = false
    }
  })
}

const deleteSupplier = async (row: Supplier) => {
  try {
    await deleteSupplierApi(row.id)
    ElMessage.success(t('suppliers.deleteSuccess'))
    loadSuppliers()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.failed'))
  }
}

// ========== 报价表相关 ==========
import request from '@/api/index'

interface SupplierRate {
  id: number
  supplier_id: number
  business_type: string
  country_code: string
  resource_type: string
  business_scope: string
  cost_price: number
  sell_price: number
  remark: string
  status: string
}

const ratesDialogVisible = ref(false)
const ratesLoading = ref(false)
const supplierRates = ref<SupplierRate[]>([])
const ratesBusinessType = ref('all')  // 业务类型筛选
const rateFormDialogVisible = ref(false)
const rateSubmitting = ref(false)
const isEditRate = ref(false)
const currentRateId = ref<number | null>(null)
const rateFormRef = ref<FormInstance>()

// 国家代码列表
const countryCodes = [
  'CN', 'US', 'GB', 'JP', 'KR', 'SG', 'HK', 'TW', 'MO', 'TH', 'VN', 'MY',
  'ID', 'PH', 'IN', 'PK', 'BD', 'MM', 'KH', 'LA', 'NP', 'LK', 'AU', 'NZ',
  'CA', 'MX', 'BR', 'AR', 'CL', 'CO', 'PE', 'VE', 'DE', 'FR', 'IT', 'ES',
  'PT', 'NL', 'BE', 'CH', 'AT', 'SE', 'NO', 'DK', 'FI', 'PL', 'CZ', 'HU',
  'GR', 'TR', 'RU', 'UA', 'RO', 'BG', 'AE', 'SA', 'IL', 'EG', 'ZA', 'NG',
  'KE', 'MA', 'GH', 'QA', 'KW', 'BH', 'OM', 'JO', 'LB', 'IQ', 'IR', 'AF',
  'IE', 'SK', 'SI', 'HR', 'RS', 'LT', 'LV', 'EE', 'BY', 'KZ', 'UZ', 'MN',
]

// 完整国家列表 - 使用计算属性以支持 i18n
const allCountries = computed(() => 
  countryCodes.map(code => ({ code, name: t(`countries.${code}`) }))
)

// 获取国家名称
const getCountryName = (code: string) => {
  return t(`countries.${code}`, code)
}

// 按业务类型分组的资源类型选项（发送方式/技术类型）
const smsResourceTypes = computed(() => [
  { value: 'card', label: t('suppliers.smsCard') },
  { value: 'direct', label: t('suppliers.smsDirect') },
  { value: 'ws_bulk', label: t('suppliers.smsWsBulk') },
  { value: 'two_way', label: t('suppliers.smsTwoWay') },
  { value: 'rcs', label: t('suppliers.smsRcs') },
])

const voiceResourceTypes = computed(() => [
  { value: 'card', label: t('suppliers.voiceCard') },
  { value: 'direct', label: t('suppliers.voiceDirect') },
  { value: 'passthrough', label: t('suppliers.voicePassthrough') },
  { value: 'local_display', label: t('suppliers.voiceLocalDisplay') },
  { value: 'international', label: t('suppliers.voiceInternational') },
])

const dataResourceTypes = computed(() => [
  { value: 'credential_stuffing', label: t('suppliers.dataCredentialStuffing') },
  { value: 'penetration', label: t('suppliers.dataPenetration') },
  { value: 'social_db', label: t('suppliers.dataSocialDb') },
  { value: 'bc_recall', label: t('suppliers.dataBcRecall') },
  { value: 'telemarketing', label: t('suppliers.dataTelemarketing') },
])

// 业务范围选项（内容类型，通用于所有业务）
const businessScopeOptions = computed(() => [
  { value: 'marketing', label: t('suppliers.scopeMarketing') },
  { value: 'otp', label: t('suppliers.scopeOtp') },
  { value: 'gambling', label: t('suppliers.scopeGambling') },
  { value: 'parttime', label: t('suppliers.scopeParttime') },
  { value: 'stock', label: t('suppliers.scopeStock') },
  { value: 'dating', label: t('suppliers.scopeDating') },
])

// 根据业务类型获取资源类型选项
const getResourceTypeOptions = (businessType: string) => {
  switch (businessType) {
    case 'voice':
      return voiceResourceTypes.value
    case 'data':
      return dataResourceTypes.value
    default:
      return smsResourceTypes.value
  }
}

// 当前表单的资源类型选项（基于rateForm.business_type）
const resourceTypeOptions = computed(() => getResourceTypeOptions(rateForm.business_type))

const resourceTypeTagMap: Record<string, string> = {
  // SMS
  otp: 'success',
  marketing: 'warning',
  notification: 'primary',
  international: 'danger',
  transactional: 'success',
  promotional: 'warning',
  alert: 'danger',
  bulk: '',
  // Voice
  domestic: 'success',
  callback: 'primary',
  ivr: 'warning',
  wholesale: '',
  // Data
  receive: 'success',
  number: 'primary',
  traffic: 'warning',
  virtual: '',
}

const rateForm = reactive({
  business_type: 'sms',
  country_code: '',
  resource_type: 'card',
  business_scope: 'otp',
  cost_price: 0,
  sell_price: 0,
  remark: ''
})

// 当业务类型变化时，重置资源类型为该业务的第一个选项
const onBusinessTypeChange = (businessType: string) => {
  const options = getResourceTypeOptions(businessType)
  if (options.length > 0) {
    rateForm.resource_type = options[0].value
  }
}

const rateRules = computed<FormRules>(() => ({
  business_type: [{ required: true, message: t('suppliers.pleaseSelectBusinessType'), trigger: 'change' }],
  country_code: [{ required: true, message: t('suppliers.pleaseSelectCountry'), trigger: 'change' }],
  resource_type: [{ required: true, message: t('suppliers.pleaseSelectResourceType'), trigger: 'change' }],
  cost_price: [{ required: true, message: t('suppliers.pleaseEnterCost'), trigger: 'blur' }]
}))

const showRatesDialog = async (row: Supplier) => {
  currentSupplier.value = row
  ratesBusinessType.value = 'all'
  ratesDialogVisible.value = true
  await loadSupplierRates(row.id)
}

const loadSupplierRates = async (supplierId?: number) => {
  const id = supplierId || currentSupplier.value?.id
  if (!id) return
  
  ratesLoading.value = true
  try {
    const params: Record<string, string> = {}
    if (ratesBusinessType.value && ratesBusinessType.value !== 'all') {
      params.business_type = ratesBusinessType.value
    }
    const res = await request.get(`/admin/suppliers/${id}/rates`, { params })
    if (res.success) {
      supplierRates.value = res.rates || []
    }
  } catch (error) {
    console.error('Failed to load rates:', error)
    supplierRates.value = []
  } finally {
    ratesLoading.value = false
  }
}

const showAddRateDialog = () => {
  isEditRate.value = false
  currentRateId.value = null
  // 默认使用当前筛选的业务类型
  const defaultBusinessType = ratesBusinessType.value !== 'all' ? ratesBusinessType.value : 'sms'
  const defaultResourceType = getResourceTypeOptions(defaultBusinessType)[0]?.value || 'card'
  Object.assign(rateForm, {
    business_type: defaultBusinessType,
    country_code: '',
    resource_type: defaultResourceType,
    business_scope: 'otp',
    cost_price: 0,
    sell_price: 0,
    remark: ''
  })
  rateFormDialogVisible.value = true
}

const editRate = (row: SupplierRate) => {
  isEditRate.value = true
  currentRateId.value = row.id
  Object.assign(rateForm, {
    business_type: row.business_type || 'sms',
    country_code: row.country_code,
    resource_type: row.resource_type,
    business_scope: row.business_scope || 'otp',
    cost_price: row.cost_price,
    sell_price: row.sell_price,
    remark: row.remark || ''
  })
  rateFormDialogVisible.value = true
}

const submitRateForm = async () => {
  if (!rateFormRef.value) return
  await rateFormRef.value.validate(async (valid) => {
    if (!valid) return
    rateSubmitting.value = true
    try {
      const supplierId = currentSupplier.value?.id
      if (!supplierId) return

      if (isEditRate.value && currentRateId.value) {
        await request.put(`/admin/suppliers/${supplierId}/rates/${currentRateId.value}`, rateForm)
        ElMessage.success(t('suppliers.rateUpdateSuccess'))
      } else {
        await request.post(`/admin/suppliers/${supplierId}/rates`, rateForm)
        ElMessage.success(t('suppliers.rateAddSuccess'))
      }
      rateFormDialogVisible.value = false
      await loadSupplierRates(supplierId)
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('common.failed'))
    } finally {
      rateSubmitting.value = false
    }
  })
}

const deleteRate = async (row: SupplierRate) => {
  try {
    const supplierId = currentSupplier.value?.id
    if (!supplierId) return
    await request.delete(`/admin/suppliers/${supplierId}/rates/${row.id}`)
    ElMessage.success(t('suppliers.deleteSuccess'))
    await loadSupplierRates(supplierId)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.failed'))
  }
}

// ========== 批量添加报价 ==========
interface BatchRateRow {
  business_type: string
  country_code: string
  resource_type: string
  business_scope: string
  cost_price: number
  sell_price: number
  remark: string
}

const batchDialogVisible = ref(false)
const batchSubmitting = ref(false)
const batchRates = ref<BatchRateRow[]>([])

const createEmptyBatchRow = (): BatchRateRow => {
  const defaultBusinessType = ratesBusinessType.value !== 'all' ? ratesBusinessType.value : 'sms'
  const defaultResourceType = getResourceTypeOptions(defaultBusinessType)[0]?.value || 'card'
  return {
    business_type: defaultBusinessType,
    country_code: '',
    resource_type: defaultResourceType,
    business_scope: 'otp',
    cost_price: 0,
    sell_price: 0,
    remark: ''
  }
}

const validBatchCount = computed(() => {
  return batchRates.value.filter(r => r.country_code && r.cost_price > 0).length
})

const showBatchAddDialog = () => {
  batchRates.value = Array(5).fill(null).map(() => createEmptyBatchRow())
  batchDialogVisible.value = true
}

const addBatchRow = () => {
  batchRates.value.push(createEmptyBatchRow())
}

const addBatchRows = (count: number) => {
  for (let i = 0; i < count; i++) {
    batchRates.value.push(createEmptyBatchRow())
  }
}

const removeBatchRow = (index: number) => {
  batchRates.value.splice(index, 1)
}

const submitBatchRates = async () => {
  const validRates = batchRates.value.filter(r => r.country_code && r.cost_price > 0)
  if (validRates.length === 0) {
    ElMessage.warning(t('suppliers.pleaseEnterAtLeastOneRate'))
    return
  }

  const supplierId = currentSupplier.value?.id
  if (!supplierId) return

  batchSubmitting.value = true
  try {
    await request.post(`/admin/suppliers/${supplierId}/rates/batch`, {
      rates: validRates
    })
    ElMessage.success(t('suppliers.batchAddSuccess', { count: validRates.length }))
    batchDialogVisible.value = false
    await loadSupplierRates(supplierId)
    await loadSuppliers() // 刷新主列表的统计
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('suppliers.batchAddFailed'))
  } finally {
    batchSubmitting.value = false
  }
}

// ========== 模板导入功能 ==========
const uploadRef = ref()

const downloadTemplate = () => {
  // 生成CSV模板内容 - 增加业务类型列
  const headers = [t('suppliers.csvBusinessType'), t('suppliers.csvCountryCode'), t('suppliers.csvResourceType'), t('suppliers.csvCost'), t('suppliers.csvSellPrice'), t('suppliers.csvRemark')]
  const examples = [
    ['sms', 'CN', 'otp', '0.001', '0.002', t('suppliers.csvExampleOtp')],
    ['sms', 'US', 'marketing', '0.005', '0.008', t('suppliers.csvExampleMarketing')],
    ['voice', 'JP', 'international', '0.010', '0.015', t('suppliers.csvExampleVoice')],
    ['data', 'PH', 'otp', '0.002', '0.003', t('suppliers.csvExampleData')],
  ]
  
  // 添加BOM以支持Excel正确识别UTF-8
  const BOM = '\uFEFF'
  const csvContent = BOM + headers.join(',') + '\n' + examples.map(row => row.join(',')).join('\n')
  
  // 创建下载链接
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = t('suppliers.templateFileName')
  link.click()
  URL.revokeObjectURL(url)
  
  ElMessage.success(t('suppliers.templateDownloadSuccess'))
}

const handleFileChange = async (file: any) => {
  if (!file || !file.raw) return
  
  const supplierId = currentSupplier.value?.id
  if (!supplierId) {
    ElMessage.error(t('suppliers.pleaseSelectSupplierFirst'))
    return
  }

  const reader = new FileReader()
  reader.onload = async (e) => {
    try {
      const content = e.target?.result as string
      const rates = parseCSV(content)
      
      if (rates.length === 0) {
        ElMessage.warning(t('suppliers.noValidDataParsed'))
        return
      }
      
      // 显示确认对话框
      const confirmed = await ElMessageBox.confirm(
        t('suppliers.confirmImportMessage', { count: rates.length }),
        t('suppliers.confirmImport'),
        { confirmButtonText: t('common.import'), cancelButtonText: t('common.cancel'), type: 'info' }
      ).catch(() => false)
      
      if (!confirmed) return
      
      // 批量导入
      await request.post(`/admin/suppliers/${supplierId}/rates/batch`, { rates })
      ElMessage.success(t('suppliers.importSuccess', { count: rates.length }))
      await loadSupplierRates(supplierId)
      await loadSuppliers()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('suppliers.importFailed') + ': ' + error.message)
    }
  }
  reader.readAsText(file.raw, 'UTF-8')
  
  // 清空文件选择，允许重复选择同一文件
  if (uploadRef.value) {
    uploadRef.value.clearFiles()
  }
}

const parseCSV = (content: string): BatchRateRow[] => {
  const lines = content.trim().split('\n')
  if (lines.length < 2) return []
  
  const rates: BatchRateRow[] = []
  
  // 跳过标题行
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim()
    if (!line) continue
    
    // 处理CSV格式（支持引号包裹的字段）
    const cols = line.split(',').map(col => col.trim().replace(/^"|"$/g, ''))
    
    // 新格式：业务类型,国家代码,资源类型,成本价,售价,备注
    if (cols.length >= 4 && cols[1] && parseFloat(cols[3]) > 0) {
      const businessType = cols[0].toLowerCase()
      rates.push({
        business_type: ['sms', 'voice', 'data'].includes(businessType) ? businessType : 'sms',
        country_code: cols[1].toUpperCase(),
        resource_type: cols[2] || 'otp',
        cost_price: parseFloat(cols[3]) || 0,
        sell_price: parseFloat(cols[4]) || 0,
        remark: cols[5] || ''
      })
    }
  }
  
  return rates
}

import { ElMessageBox } from 'element-plus'

onMounted(() => {
  loadSuppliers()
})
</script>

<style scoped>
.page-container {
  width: 100%;
  padding: 8px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.header-left {
  flex: 1;
}

.header-right {
  display: flex;
  gap: 12px;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 6px;
}

.page-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 12px;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
}

.stat-icon.active {
  background: rgba(103, 194, 58, 0.12);
  color: #67c23a;
}

.stat-icon.total {
  background: rgba(102, 126, 234, 0.12);
  color: #667eea;
}

.stat-icon.sms {
  background: rgba(64, 158, 255, 0.12);
  color: #409eff;
}

.stat-icon.voice {
  background: rgba(230, 162, 60, 0.12);
  color: #e6a23c;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

/* 筛选器 */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

/* 表格 */
.table-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 16px;
}

.supplier-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.supplier-name {
  font-weight: 500;
  color: var(--text-primary);
}

.cost-text {
  font-family: monospace;
  font-weight: 600;
  color: var(--primary);
}

.notes-text {
  font-size: 13px;
  color: var(--text-secondary);
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
  
  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }
  
  .filter-bar > * {
    width: 100% !important;
  }
}

/* 报价表样式 */
.rates-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}

.rates-table {
  width: 100%;
}

.sell-text {
  color: #67c23a;
  font-weight: 500;
}

.cost-text {
  color: #e6a23c;
  font-weight: 500;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.no-rate {
  color: #909399;
  font-size: 12px;
}

/* 批量添加样式 */
.batch-tips {
  margin-bottom: 16px;
}

.batch-table {
  width: 100%;
}

.batch-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}

.rates-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
  gap: 8px;
}
</style>
