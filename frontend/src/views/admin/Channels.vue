<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">{{ $t('channels.title') }}</h1>
        <p class="page-desc">{{ $t('channels.pageDesc') }}</p>
      </div>
      <div class="header-right">
        <el-button @click="loadChannels" :icon="Refresh">{{ $t('common.refresh') }}</el-button>
        <el-button type="primary" @click="showCreateDialog = true">
          <el-icon><Plus /></el-icon>
          {{ $t('channels.addChannel') }}
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon total">
          <el-icon><Connection /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">{{ $t('channels.totalChannels') }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon active">
          <el-icon><CircleCheck /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.active }}</div>
          <div class="stat-label">{{ $t('channels.activeChannels') }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon smpp">
          <el-icon><Promotion /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.smpp }}</div>
          <div class="stat-label">{{ $t('channels.smppChannels') }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon http">
          <el-icon><Link /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.http }}</div>
          <div class="stat-label">{{ $t('channels.httpChannels') }}</div>
        </div>
      </div>
    </div>

    <!-- 搜索筛选 -->
    <div class="filter-bar">
      <el-input 
        v-model="filters.keyword" 
        :placeholder="$t('channels.searchPlaceholder')" 
        clearable 
        style="width: 200px"
        @keyup.enter="loadChannels"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="filters.protocol" :placeholder="$t('channels.protocolType')" clearable style="width: 120px" @change="loadChannels">
        <el-option label="SMPP" value="SMPP" />
        <el-option label="HTTP" value="HTTP" />
      </el-select>
      <el-select v-model="filters.status" :placeholder="$t('common.status')" clearable style="width: 100px" @change="loadChannels">
        <el-option :label="$t('channels.active')" value="active" />
        <el-option :label="$t('channels.inactive')" value="inactive" />
        <el-option :label="$t('channels.maintenance')" value="maintenance" />
      </el-select>
      <el-button @click="resetFilters">{{ $t('common.reset') }}</el-button>
    </div>
    
    <!-- 通道列表 -->
    <div class="table-card">
      <el-table :data="filteredChannels" v-loading="loading" class="data-table">
        <el-table-column prop="channel_code" :label="$t('channels.channelCode')" width="160">
          <template #default="{ row }">
            <div class="channel-code">
              <span class="code-text">{{ row.channel_code }}</span>
              <el-tag :type="row.protocol === 'SMPP' ? 'primary' : 'success'" size="small" effect="plain">
                {{ row.protocol }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="channel_name" :label="$t('channels.channelName')" min-width="200">
          <template #default="{ row }">
            <div class="channel-info">
              <span class="channel-name">{{ row.channel_name }}</span>
              <span class="channel-host" v-if="row.host">
                {{ row.host }}:{{ row.port }}
                <el-tag v-if="row.protocol === 'SMPP'" size="small" effect="plain" type="info" style="margin-left:4px">
                  {{ (row.smpp_bind_mode || 'transceiver').toUpperCase() }}
                </el-tag>
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('channels.channelStatus')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="cost_rate" :label="$t('channels.costPrice')" width="100" align="right">
          <template #default="{ row }">
            <span class="cost-text">${{ (row.cost_rate || 0).toFixed(4) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priority" :label="$t('channels.priority')" width="80" align="center">
          <template #default="{ row }">
            <el-tag type="info" size="small" effect="plain">{{ row.priority }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="weight" :label="$t('channels.weight')" width="80" align="center" />
        <el-table-column prop="default_sender_id" :label="$t('channels.defaultSid')" width="120">
          <template #default="{ row }">
            {{ row.default_sender_id || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="supplier" :label="$t('channels.supplier')" width="140">
          <template #default="{ row }">
            <span v-if="row.supplier">{{ row.supplier.supplier_name }}</span>
            <span v-else style="color: var(--text-tertiary)">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="280" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="handleEdit(row)">{{ $t('common.edit') }}</el-button>
            <el-button type="success" link size="small" @click="manageCountries(row)">{{ $t('channels.countries') }}</el-button>
            <el-button type="warning" link size="small" @click="manageSids(row)">SID</el-button>
            <el-button 
              :type="row.status === 'active' ? 'info' : 'success'"
              link
              size="small"
              @click="handleToggleStatus(row)"
            >
              {{ row.status === 'active' ? $t('common.disable') : $t('common.enable') }}
            </el-button>
            <el-popconfirm :title="$t('channels.confirmDelete')" @confirm="handleDelete(row)">
              <template #reference>
                <el-button type="danger" link size="small">{{ $t('common.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>
    
    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingChannel ? $t('channels.editChannel') : $t('channels.addChannel')"
      width="650px"
      destroy-on-close
      @open="onChannelDialogOpen"
    >
      <el-form :model="channelForm" label-width="100px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="$t('channels.channelCode')" required>
              <el-input v-model="channelForm.channel_code" :disabled="!!editingChannel" :placeholder="$t('channels.channelCodePlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('channels.protocolType')" required>
              <el-select v-model="channelForm.protocol" style="width: 100%">
                <el-option label="SMPP" value="SMPP" />
                <el-option label="HTTP" value="HTTP" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item :label="$t('channels.channelName')" required>
          <el-input v-model="channelForm.channel_name" :placeholder="$t('channels.channelNamePlaceholder')" />
        </el-form-item>
        
        <!-- SMPP协议配置 -->
        <template v-if="channelForm.protocol === 'SMPP'">
          <el-divider content-position="left">{{ $t('channels.smppConnectionConfig') }}</el-divider>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item :label="$t('channels.serverAddress')" required>
                <el-input v-model="channelForm.host" :placeholder="$t('channels.hostPlaceholder')" />
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item :label="$t('channels.port')" required>
                <el-input-number v-model="channelForm.port" :min="1" :max="65535" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="Bind Mode">
                <el-select v-model="channelForm.smpp_bind_mode" style="width: 100%">
                  <el-option label="Transceiver (TX+RX)" value="transceiver" />
                  <el-option label="Transmitter (TX)" value="transmitter" />
                  <el-option label="Receiver (RX)" value="receiver" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item :label="$t('channels.username')" required>
                <el-input v-model="channelForm.username" placeholder="System ID" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="$t('channels.password')" required>
                <el-input v-model="channelForm.password" type="password" show-password :placeholder="$t('channels.password')" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="System Type">
                <el-input v-model="channelForm.smpp_system_type" placeholder="(可选)" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>
        
        <!-- HTTP协议配置 -->
        <template v-if="channelForm.protocol === 'HTTP'">
          <el-divider content-position="left">{{ $t('channels.httpInterfaceConfig') }}</el-divider>
          <el-form-item :label="$t('channels.apiUrl')" required>
            <el-input v-model="channelForm.api_url" :placeholder="$t('channels.apiUrlPlaceholder')" />
          </el-form-item>
          <el-form-item :label="$t('channels.apiCredentials')">
            <el-input 
              v-model="channelForm.api_key" 
              type="textarea"
              :rows="2"
              :placeholder="$t('channels.apiCredentialsPlaceholder')" 
            />
          </el-form-item>
        </template>

        <el-divider content-position="left">{{ $t('channels.channelParams') }}</el-divider>
        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item :label="$t('channels.costPrice')">
              <el-input-number v-model="channelForm.cost_rate" :min="0" :precision="4" :step="0.001" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="$t('channels.priority')">
              <el-input-number v-model="channelForm.priority" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="$t('channels.weight')">
              <el-input-number v-model="channelForm.weight" :min="1" :max="1000" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="$t('channels.defaultSid')">
          <el-input v-model="channelForm.default_sender_id" :placeholder="$t('channels.defaultSidPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('channels.supplier')">
          <el-select
            v-model="channelForm.supplier_id"
            :placeholder="$t('channels.selectSupplierPlaceholder')"
            clearable
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="s in suppliers"
              :key="s.id"
              :label="`${s.supplier_name} (${s.supplier_code})`"
              :value="s.id"
            />
          </el-select>
        </el-form-item>
        <el-divider content-position="left">违禁词管理</el-divider>
        <el-form-item label="全局违禁词">
          <el-input
            v-model="channelForm.banned_words"
            type="textarea"
            :rows="3"
            placeholder="该通道所有国家通用的违禁词，每行一个或逗号分隔"
            resize="vertical"
          />
          <div style="font-size: 11px; color: var(--el-text-color-placeholder); margin-top: 4px;">
            此处配置对该通道所有国家生效。如需按国家单独配置，请在「路由规则」中为每个国家设置专属违禁词。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="handleSave">{{ $t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 国家管理对话框 -->
    <el-dialog
      v-model="showCountriesDialog"
      :title="$t('channels.countryConfig')"
      width="800px"
      destroy-on-close
    >
      <div class="dialog-header-actions">
        <el-button type="primary" size="small" @click="showAddCountryDialog = true">
          <el-icon><Plus /></el-icon>
          {{ $t('channels.addCountry') }}
        </el-button>
      </div>
      <el-table :data="channelCountries" v-loading="countriesLoading" class="data-table">
        <el-table-column prop="country_code" :label="$t('channels.countryCode')" width="100" />
        <el-table-column prop="country_name" :label="$t('channels.countryName')" min-width="150">
          <template #default="{ row }">
            {{ countryNameMap[row.country_code] || row.country_name || row.country_code }}
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('common.status')" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
              {{ row.status === 'active' ? $t('common.enable') : $t('common.disable') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="priority" :label="$t('channels.priority')" width="80" align="center" />
        <el-table-column :label="$t('common.action')" width="150" align="center">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="editCountry(row)">{{ $t('common.edit') }}</el-button>
            <el-popconfirm :title="$t('channels.confirmDeleteCountry')" @confirm="removeCountry(row)">
              <template #reference>
                <el-button type="danger" link size="small">{{ $t('common.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- 添加/编辑国家对话框 -->
      <el-dialog
        v-model="showAddCountryDialog"
        :title="editingCountry ? $t('channels.editCountry') : $t('channels.addCountry')"
        width="450px"
        append-to-body
      >
        <el-form :model="countryForm" label-width="80px">
          <el-form-item :label="$t('channels.country')" required>
            <el-select 
              v-model="countryForm.country_code" 
              filterable
              allow-create
              :placeholder="$t('channels.selectOrInputCountry')"
              style="width: 100%"
              :disabled="!!editingCountry"
            >
              <el-option v-for="item in allCountries" :key="item.code" :label="`${item.name} (${item.code})`" :value="item.code" />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('common.status')">
            <el-select v-model="countryForm.status" style="width: 100%">
              <el-option :label="$t('common.enable')" value="active" />
              <el-option :label="$t('common.disable')" value="inactive" />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('channels.priority')">
            <el-input-number v-model="countryForm.priority" :min="0" style="width: 100%" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showAddCountryDialog = false">{{ $t('common.cancel') }}</el-button>
          <el-button type="primary" @click="saveCountry">{{ $t('common.save') }}</el-button>
        </template>
      </el-dialog>
    </el-dialog>

    <!-- SID管理对话框 -->
    <el-dialog
      v-model="showSidsDialog"
      :title="$t('channels.sidManagement')"
      width="900px"
      destroy-on-close
    >
      <div class="sids-filter">
        <el-select v-model="selectedCountryForSid" :placeholder="$t('channels.selectCountry')" @change="loadSids" style="width: 200px">
          <el-option
            v-for="country in channelCountries"
            :key="country.country_code"
            :label="`${countryNameMap[country.country_code] || country.country_code}`"
            :value="country.country_code"
          />
        </el-select>
        <el-button type="primary" size="small" @click="showAddSidDialog = true" :disabled="!selectedCountryForSid">
          <el-icon><Plus /></el-icon>
          {{ $t('channels.addSid') }}
        </el-button>
      </div>
      <el-table :data="channelSids" v-loading="sidsLoading" class="data-table" style="margin-top: 16px">
        <el-table-column prop="sender_id" :label="$t('channels.senderId')" width="150" />
        <el-table-column prop="sid_type" :label="$t('channels.type')" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ getSidTypeLabel(row.sid_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('common.status')" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="getSidStatusType(row.status)" size="small">
              {{ getSidStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_default" :label="$t('channels.default')" width="70" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="success" size="small">{{ $t('common.yes') }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="150" align="center">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="editSid(row)">{{ $t('common.edit') }}</el-button>
            <el-popconfirm :title="$t('channels.confirmDeleteSid')" @confirm="removeSid(row)">
              <template #reference>
                <el-button type="danger" link size="small">{{ $t('common.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- 添加/编辑SID对话框 -->
      <el-dialog
        v-model="showAddSidDialog"
        :title="editingSid ? $t('channels.editSid') : $t('channels.addSid')"
        width="450px"
        append-to-body
      >
        <el-form :model="sidForm" label-width="80px">
          <el-form-item :label="$t('channels.senderId')" required>
            <el-input v-model="sidForm.sender_id" :placeholder="$t('channels.senderIdPlaceholder')" :disabled="!!editingSid" />
          </el-form-item>
          <el-form-item :label="$t('channels.type')">
            <el-select v-model="sidForm.sid_type" style="width: 100%">
              <el-option :label="$t('channels.alpha')" value="alpha" />
              <el-option :label="$t('channels.numeric')" value="numeric" />
              <el-option :label="$t('channels.shortcode')" value="shortcode" />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('common.status')">
            <el-select v-model="sidForm.status" style="width: 100%">
              <el-option :label="$t('common.enable')" value="active" />
              <el-option :label="$t('common.disable')" value="inactive" />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('channels.setAsDefault')">
            <el-switch v-model="sidForm.is_default" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showAddSidDialog = false">{{ $t('common.cancel') }}</el-button>
          <el-button type="primary" @click="saveSid">{{ $t('common.save') }}</el-button>
        </template>
      </el-dialog>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search, Connection, CircleCheck, Promotion, Link } from '@element-plus/icons-vue'
import { getChannelsAdmin, createChannel, updateChannel, deleteChannel, getChannelAdmin } from '@/api/admin'
import { getSuppliers } from '@/api/supplier'
import request from '@/api/index'

const { t } = useI18n()

// 状态标签函数
const getStatusLabel = (status: string) => {
  const map: Record<string, string> = {
    active: t('channels.statusOnline'),
    inactive: t('channels.statusOffline'),
    maintenance: t('channels.maintenance')
  }
  return map[status] || status
}

const statusTagType = (status: string) => {
  const map: Record<string, string> = { active: 'success', inactive: 'danger', maintenance: 'warning' }
  return map[status] || 'info'
}

// SID类型标签函数
const getSidTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    alpha: t('channels.alpha'),
    numeric: t('channels.numeric'),
    shortcode: t('channels.shortcode')
  }
  return map[type] || type
}

// SID状态标签函数
const getSidStatusLabel = (status: string) => {
  const map: Record<string, string> = {
    active: t('common.enable'),
    inactive: t('common.inactive'),
    pending: t('channels.pending'),
    rejected: t('channels.rejected')
  }
  return map[status] || status
}

const getSidStatusType = (status: string) => {
  const map: Record<string, string> = { active: 'success', inactive: 'info', pending: 'warning', rejected: 'danger' }
  return map[status] || ''
}

// 国家列表 - 使用国际化
const countryCodes = ['CN', 'US', 'GB', 'JP', 'KR', 'SG', 'HK', 'TW', 'TH', 'VN', 'MY', 'ID', 'PH', 'IN', 'AU', 'CA', 'DE', 'FR', 'BR', 'MX', 'RU']

const allCountries = computed(() => 
  countryCodes.map(code => ({ code, name: t(`countries.${code}`) }))
)

const countryNameMap = computed(() => 
  Object.fromEntries(allCountries.value.map(c => [c.code, c.name]))
)

// 数据
const loading = ref(false)
const channels = ref<any[]>([])
const showCreateDialog = ref(false)
const editingChannel = ref<any>(null)

// 筛选
const filters = reactive({ keyword: '', protocol: '', status: '' })
const resetFilters = () => {
  filters.keyword = ''
  filters.protocol = ''
  filters.status = ''
}

// 统计
const stats = computed(() => {
  const total = channels.value.length
  const active = channels.value.filter(c => c.status === 'active').length
  const smpp = channels.value.filter(c => c.protocol === 'SMPP').length
  const http = channels.value.filter(c => c.protocol === 'HTTP').length
  return { total, active, smpp, http }
})

// 过滤后的通道
const filteredChannels = computed(() => {
  return channels.value.filter(c => {
    if (filters.keyword && !c.channel_code.toLowerCase().includes(filters.keyword.toLowerCase()) 
        && !c.channel_name.toLowerCase().includes(filters.keyword.toLowerCase())) return false
    if (filters.protocol && c.protocol !== filters.protocol) return false
    if (filters.status && c.status !== filters.status) return false
    return true
  })
})

// 国家管理相关
const showCountriesDialog = ref(false)
const countriesLoading = ref(false)
const channelCountries = ref<any[]>([])
const showAddCountryDialog = ref(false)
const editingCountry = ref<any>(null)
const currentChannelId = ref<number | null>(null)
const countryForm = ref({ country_code: '', country_name: '', status: 'active', priority: 0 })

// SID管理相关
const showSidsDialog = ref(false)
const sidsLoading = ref(false)
const channelSids = ref<any[]>([])
const showAddSidDialog = ref(false)
const editingSid = ref<any>(null)
const selectedCountryForSid = ref('')
const sidForm = ref({ sender_id: '', sid_type: 'alpha', status: 'active', is_default: false, reject_reason: '' })

const suppliers = ref<any[]>([])
const channelForm = ref({
  channel_code: '',
  channel_name: '',
  protocol: 'SMPP',
  host: '',
  port: 2775,
  username: '',
  password: '',
  smpp_bind_mode: 'transceiver',
  smpp_system_type: '',
  api_url: '',
  api_key: '',
  cost_rate: 0,
  priority: 0,
  weight: 100,
  default_sender_id: '',
  supplier_id: null as number | null,
  banned_words: '',
})

const loadChannels = async () => {
  loading.value = true
  try {
    const res = await getChannelsAdmin()
    if (res.success) {
      channels.value = res.channels || []
    }
  } catch (error) {
    ElMessage.error(t('channels.loadFailed'))
  } finally {
    loading.value = false
  }
}

const handleEdit = async (channel: any) => {
  editingChannel.value = channel
  try {
    const res = await getChannelAdmin(channel.id)
    if (res.success && res.channel) {
      const ch = res.channel
      channelForm.value = {
        channel_code: ch.channel_code,
        channel_name: ch.channel_name,
        protocol: ch.protocol,
        host: ch.host || '',
        port: ch.port || 2775,
        username: ch.username || '',
        password: ch.password || '',
        smpp_bind_mode: ch.smpp_bind_mode || 'transceiver',
        smpp_system_type: ch.smpp_system_type || '',
        api_url: ch.api_url || '',
        api_key: ch.api_key || '',
        cost_rate: channel.cost_rate || 0,
        priority: ch.priority || 0,
        weight: ch.weight || 100,
        default_sender_id: ch.default_sender_id || '',
        supplier_id: ch.supplier_id ?? null,
        banned_words: ch.banned_words ?? '',
      }
    } else {
      channelForm.value = {
        ...channelForm.value,
        channel_code: channel.channel_code,
        channel_name: channel.channel_name,
        protocol: channel.protocol,
        host: channel.host || '',
        port: channel.port || 2775,
        username: channel.username || '',
        password: channel.password || '',
        smpp_bind_mode: channel.smpp_bind_mode || 'transceiver',
        smpp_system_type: channel.smpp_system_type || '',
        api_url: channel.api_url || '',
        api_key: channel.api_key || '',
        cost_rate: channel.cost_rate || 0,
        priority: channel.priority || 0,
        weight: channel.weight || 100,
        default_sender_id: channel.default_sender_id || '',
        supplier_id: channel.supplier?.id ?? null,
        banned_words: channel.banned_words ?? '',
      }
    }
  } catch {
    channelForm.value = {
      ...channelForm.value,
      channel_code: channel.channel_code,
      channel_name: channel.channel_name,
      protocol: channel.protocol,
      host: channel.host || '',
      port: channel.port || 2775,
      username: channel.username || '',
      password: channel.password || '',
      smpp_bind_mode: channel.smpp_bind_mode || 'transceiver',
      smpp_system_type: channel.smpp_system_type || '',
      api_url: channel.api_url || '',
      api_key: channel.api_key || '',
      cost_rate: channel.cost_rate || 0,
      priority: channel.priority || 0,
      weight: channel.weight || 100,
      default_sender_id: channel.default_sender_id || '',
      supplier_id: channel.supplier?.id ?? null,
      banned_words: channel.banned_words ?? '',
    }
  }
  showCreateDialog.value = true
}

const onChannelDialogOpen = async () => {
  try {
    const res = await getSuppliers({ status: 'active', page_size: 500 })
    suppliers.value = res.suppliers || res.items || []
  } catch {
    suppliers.value = []
  }
}

const handleSave = async () => {
  if (!channelForm.value.channel_code || !channelForm.value.channel_name) {
    ElMessage.warning(t('channels.pleaseEnterRequired'))
    return
  }
  const payload = { ...channelForm.value }
  if (payload.supplier_id === null) payload.supplier_id = undefined
  try {
    if (editingChannel.value) {
      await updateChannel(editingChannel.value.id, payload)
      ElMessage.success(t('channels.updateSuccess'))
    } else {
      await createChannel(payload)
      ElMessage.success(t('channels.createSuccess'))
    }
    showCreateDialog.value = false
    editingChannel.value = null
    resetChannelForm()
    await loadChannels()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.failed'))
  }
}

const handleToggleStatus = async (channel: any) => {
  const newStatus = channel.status === 'active' ? 'inactive' : 'active'
  try {
    await updateChannel(channel.id, { status: newStatus })
    ElMessage.success(newStatus === 'active' ? t('channels.enabled') : t('channels.disabled'))
    await loadChannels()
  } catch (error) {
    ElMessage.error(t('common.failed'))
  }
}

const handleDelete = async (channel: any) => {
  try {
    await deleteChannel(channel.id)
    ElMessage.success(t('channels.deleteSuccess'))
    await loadChannels()
  } catch (error) {
    ElMessage.error(t('common.failed'))
  }
}

const resetChannelForm = () => {
  channelForm.value = {
    channel_code: '',
    channel_name: '',
    protocol: 'SMPP',
    host: '',
    port: 2775,
    username: '',
    password: '',
    smpp_bind_mode: 'transceiver',
    smpp_system_type: '',
    api_url: '',
    api_key: '',
    cost_rate: 0,
    priority: 0,
    weight: 100,
    default_sender_id: '',
    supplier_id: null,
    banned_words: '',
  }
}

// 国家管理
const manageCountries = async (channel: any) => {
  currentChannelId.value = channel.id
  showCountriesDialog.value = true
  await loadCountries(channel.id)
}

const loadCountries = async (channelId: number) => {
  countriesLoading.value = true
  try {
    const res = await request.get(`/admin/channel-relations/channels/${channelId}/countries`)
    if (res.success) {
      channelCountries.value = res.items || []
    }
  } catch (error: any) {
    ElMessage.error(t('channels.loadCountriesFailed'))
  } finally {
    countriesLoading.value = false
  }
}

const editCountry = (country: any) => {
  editingCountry.value = country
  countryForm.value = {
    country_code: country.country_code,
    country_name: country.country_name || '',
    status: country.status,
    priority: country.priority
  }
  showAddCountryDialog.value = true
}

const saveCountry = async () => {
  if (!countryForm.value.country_code) {
    ElMessage.warning(t('channels.pleaseSelectCountry'))
    return
  }
  try {
    if (editingCountry.value) {
      await request.put(
        `/admin/channel-relations/channels/${currentChannelId.value}/countries/${editingCountry.value.id}`,
        countryForm.value
      )
      ElMessage.success(t('channels.updateSuccess'))
    } else {
      await request.post(
        `/admin/channel-relations/channels/${currentChannelId.value}/countries`,
        { channel_id: currentChannelId.value, ...countryForm.value }
      )
      ElMessage.success(t('channels.addSuccess'))
    }
    showAddCountryDialog.value = false
    editingCountry.value = null
    countryForm.value = { country_code: '', country_name: '', status: 'active', priority: 0 }
    await loadCountries(currentChannelId.value!)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.failed'))
  }
}

const removeCountry = async (country: any) => {
  try {
    await request.delete(`/admin/channel-relations/channels/${currentChannelId.value}/countries/${country.id}`)
    ElMessage.success(t('channels.deleteSuccess'))
    await loadCountries(currentChannelId.value!)
  } catch (error: any) {
    ElMessage.error(t('common.failed'))
  }
}

// SID管理
const manageSids = async (channel: any) => {
  currentChannelId.value = channel.id
  showSidsDialog.value = true
  await loadCountries(channel.id)
  if (channelCountries.value.length > 0) {
    selectedCountryForSid.value = channelCountries.value[0].country_code
    await loadSids()
  }
}

const loadSids = async () => {
  if (!currentChannelId.value || !selectedCountryForSid.value) return
  sidsLoading.value = true
  try {
    const res = await request.get(
      `/admin/channel-relations/channels/${currentChannelId.value}/countries/${selectedCountryForSid.value}/sids`
    )
    if (res.success) {
      channelSids.value = res.items || []
    }
  } catch (error: any) {
    ElMessage.error(t('channels.loadSidsFailed'))
  } finally {
    sidsLoading.value = false
  }
}

const editSid = (sid: any) => {
  editingSid.value = sid
  sidForm.value = {
    sender_id: sid.sender_id,
    sid_type: sid.sid_type,
    status: sid.status,
    is_default: sid.is_default,
    reject_reason: sid.reject_reason || ''
  }
  showAddSidDialog.value = true
}

const saveSid = async () => {
  if (!sidForm.value.sender_id) {
    ElMessage.warning(t('channels.pleaseEnterSenderId'))
    return
  }
  try {
    if (editingSid.value) {
      await request.put(
        `/admin/channel-relations/channels/${currentChannelId.value}/countries/${selectedCountryForSid.value}/sids/${editingSid.value.id}`,
        sidForm.value
      )
      ElMessage.success(t('channels.updateSuccess'))
    } else {
      await request.post(
        `/admin/channel-relations/channels/${currentChannelId.value}/countries/${selectedCountryForSid.value}/sids`,
        { channel_id: currentChannelId.value, country_code: selectedCountryForSid.value, ...sidForm.value }
      )
      ElMessage.success(t('channels.addSuccess'))
    }
    showAddSidDialog.value = false
    editingSid.value = null
    sidForm.value = { sender_id: '', sid_type: 'alpha', status: 'active', is_default: false, reject_reason: '' }
    await loadSids()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.failed'))
  }
}

const removeSid = async (sid: any) => {
  try {
    await request.delete(
      `/admin/channel-relations/channels/${currentChannelId.value}/countries/${selectedCountryForSid.value}/sids/${sid.id}`
    )
    ElMessage.success(t('channels.deleteSuccess'))
    await loadSids()
  } catch (error: any) {
    ElMessage.error(t('common.failed'))
  }
}

onMounted(() => {
  loadChannels()
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

.header-left { flex: 1; }
.header-right { display: flex; gap: 12px; }

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

.stat-icon.total { background: rgba(102, 126, 234, 0.12); color: #667eea; }
.stat-icon.active { background: rgba(103, 194, 58, 0.12); color: #67c23a; }
.stat-icon.smpp { background: rgba(64, 158, 255, 0.12); color: #409eff; }
.stat-icon.http { background: rgba(230, 162, 60, 0.12); color: #e6a23c; }

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

.channel-code {
  display: flex;
  align-items: center;
  gap: 8px;
}

.code-text {
  font-family: monospace;
  font-weight: 500;
}

.channel-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.channel-name {
  font-weight: 500;
  color: var(--text-primary);
}

.channel-host {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: monospace;
}

.cost-text {
  color: #e6a23c;
  font-weight: 500;
}

.dialog-header-actions {
  margin-bottom: 16px;
}

.sids-filter {
  display: flex;
  gap: 12px;
  align-items: center;
}

@media (max-width: 1200px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 768px) {
  .stats-grid { grid-template-columns: 1fr; }
  .filter-bar { flex-direction: column; align-items: stretch; }
  .filter-bar > * { width: 100% !important; }
}
</style>
