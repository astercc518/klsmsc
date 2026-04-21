<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">{{ $t('channels.title') }}</h1>
        <p class="page-desc">{{ $t('channels.pageDesc') }}</p>
      </div>
      <div class="header-right">
        <el-button @click="loadChannels" :icon="Refresh">{{ $t('common.refresh') }}</el-button>
        <el-button type="primary" @click="handleCreate">
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
      <el-select v-model="filters.protocol" :placeholder="$t('channels.protocolType')" clearable style="width: 120px">
        <el-option label="SMPP" value="SMPP" />
        <el-option label="HTTP" value="HTTP" />
        <el-option label="VIRTUAL" value="VIRTUAL" />
      </el-select>
      <el-select v-model="filters.status" :placeholder="$t('common.status')" clearable style="width: 100px">
        <el-option :label="$t('channels.active')" value="active" />
        <el-option :label="$t('channels.inactive')" value="inactive" />
        <el-option :label="$t('channels.maintenance')" value="maintenance" />
      </el-select>
      <el-button @click="resetFilters">{{ $t('common.reset') }}</el-button>
      <el-button type="warning" :loading="checkingAll" :icon="CircleCheck" @click="handleCheckAllStatus">
        {{ $t('channels.checkAllStatus') }}
      </el-button>
    </div>
    
    <!-- 通道列表 -->
    <div class="table-card">
      <el-table :data="filteredChannels" v-loading="loading" stripe class="channel-table" table-layout="auto">
        <el-table-column prop="code" :label="$t('channels.channelCode')" min-width="130">
          <template #default="{ row }">
            <span class="code-text">{{ row.code }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" :label="$t('channels.channelName')" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="name-text">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="protocol" :label="$t('channels.protocol')" min-width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="row.protocol === 'SMPP' ? '' : row.protocol === 'VIRTUAL' ? 'warning' : 'success'" size="small" effect="dark">
              {{ row.protocol }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('channels.serverAddress')" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.protocol === 'SMPP' && row.host" class="server-text">{{ row.host }}:{{ row.port }}</span>
            <span v-else-if="row.protocol === 'HTTP' && row.api_url" class="server-text">{{ row.api_url }}</span>
            <span v-else-if="row.protocol === 'VIRTUAL'" class="server-text" style="color: #f59e0b">虚拟通道</span>
            <span v-else class="empty-text">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="username" :label="$t('channels.username')" min-width="100" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="account-text">{{ row.username || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="connection_status" :label="$t('channels.channelStatus')" min-width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="getConnectionStatusType(row.connection_status)" size="small" effect="light" round>
              {{ getConnectionStatusText(row.connection_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('channels.rateControl')" min-width="140" align="center">
          <template #default="{ row }">
            <div class="rate-info">
              <span class="rate-text">{{ row.max_tps || 100 }} TPS</span>
              <span class="rate-sub">{{ row.concurrency || 1 }}C / {{ row.rate_control_window || 1000 }}ms</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="default_sender_id" :label="$t('channels.defaultSid')" min-width="100" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="sid-text">{{ row.default_sender_id || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('channels.supplier')" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag v-if="row.supplier" type="warning" size="small" effect="plain">
              {{ row.supplier.supplier_name }}
            </el-tag>
            <el-button v-else type="primary" link size="small" @click="openSupplierDialog(row)">
              {{ $t('channels.linkSupplier') }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.actions')" min-width="280" fixed="right" align="center">
          <template #default="{ row }">
            <div class="action-btns">
              <el-button type="primary" link size="small" @click="handleViewDetail(row)">{{ $t('common.details') }}</el-button>
              <el-button type="warning" link size="small" @click="handleEdit(row)">{{ $t('common.edit') }}</el-button>
              <el-button type="info" link size="small" @click="openRouting(row)">{{ $t('channels.routing') }}</el-button>
              <el-button type="success" link size="small" @click="openPricing(row)">{{ $t('channels.pricing') }}</el-button>
              <el-button link size="small" @click="openTestSend(row)">{{ $t('channels.test') }}</el-button>
              <el-button link size="small" @click="handleCheckStatus(row)">{{ $t('channels.checkStatus') }}</el-button>
              <el-popconfirm :title="$t('channels.confirmDeleteChannel')" @confirm="handleDelete(row)">
                <template #reference>
                  <el-button type="danger" link size="small">{{ $t('common.delete') }}</el-button>
                </template>
              </el-popconfirm>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
    
    <!-- 详情对话框 -->
    <el-dialog v-model="detailVisible" :title="$t('channels.channelDetail')" width="600px" class="channel-detail-dialog" :append-to-body="false">
      <el-descriptions :column="2" border v-if="currentChannel">
        <el-descriptions-item :label="$t('channels.channelCode')">{{ currentChannel.code }}</el-descriptions-item>
        <el-descriptions-item :label="$t('channels.protocol')">
          <el-tag :type="currentChannel.protocol === 'SMPP' ? 'primary' : currentChannel.protocol === 'VIRTUAL' ? 'warning' : 'success'" size="small">
            {{ currentChannel.protocol }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('channels.channelName')" :span="2">{{ currentChannel.name }}</el-descriptions-item>
        <el-descriptions-item :label="$t('channels.channelStatus')">
          <el-tag :type="getConnectionStatusType(currentChannel.connection_status)">
            {{ getConnectionStatusText(currentChannel.connection_status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('channels.defaultSid')">
          {{ currentChannel.default_sender_id || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="$t('channels.priority')">{{ currentChannel.priority }}</el-descriptions-item>
        <el-descriptions-item :label="$t('channels.weight')">{{ currentChannel.weight }}</el-descriptions-item>
        <el-descriptions-item v-if="currentChannel.protocol === 'SMPP'" :label="$t('channels.smppAddress')" :span="2">
          {{ currentChannel.host ? `${currentChannel.host}:${currentChannel.port || ''}` : '-' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="currentChannel.protocol === 'SMPP'" :label="$t('channels.systemId')">
          {{ currentChannel.username || '-' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="currentChannel.protocol === 'HTTP'" :label="$t('channels.apiAddress')" :span="2">
          {{ currentChannel.api_url || '-' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="currentChannel.protocol === 'VIRTUAL'" label="虚拟通道" :span="2">
          <span style="color: #f59e0b">模拟回执（不实际发送）</span>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('common.createdAt')">
          {{ currentChannel.created_at ? new Date(currentChannel.created_at).toLocaleString() : '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="$t('common.updatedAt')">
          {{ currentChannel.updated_at ? new Date(currentChannel.updated_at).toLocaleString() : '-' }}
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <!-- 编辑/创建对话框 -->
    <el-dialog 
      v-model="formVisible" 
      :title="isEdit ? $t('channels.editChannel') : $t('channels.createChannel')" 
      width="720px"
      :close-on-click-modal="false"
      destroy-on-close
      class="channel-form-dialog"
      @open="loadFormSuppliers"
    >
      <el-form :model="form" label-width="85px" :rules="rules" ref="formRef" class="channel-form">
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item :label="$t('channels.channelCode')" prop="channel_code">
              <el-input v-model="form.channel_code" :disabled="isEdit" :placeholder="$t('channels.channelCodePlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('channels.protocolType')" prop="protocol">
              <el-select v-model="form.protocol" :disabled="isEdit" style="width: 100%">
                <el-option label="SMPP" value="SMPP" />
                <el-option label="HTTP" value="HTTP" />
                <el-option label="VIRTUAL (虚拟通道)" value="VIRTUAL" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item :label="$t('channels.channelName')" prop="channel_name">
          <el-input v-model="form.channel_name" :placeholder="$t('channels.channelName')" />
        </el-form-item>
        
        <template v-if="form.protocol === 'SMPP'">
          <el-divider content-position="left">{{ $t('channels.smppConnectionConfig') }}</el-divider>
          <el-row :gutter="24">
            <el-col :span="16">
              <el-form-item :label="$t('channels.serverAddress')" prop="host">
                <el-input v-model="form.host" :placeholder="$t('channels.serverAddressPlaceholder')" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="$t('channels.port')" prop="port">
                <el-input-number v-model="form.port" :min="1" :max="65535" controls-position="right" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="24">
            <el-col :span="12">
              <el-form-item :label="$t('channels.username')" prop="username">
                <el-input v-model="form.username" :placeholder="$t('channels.systemIdPlaceholder')" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="$t('channels.password')" prop="password">
                <el-input v-model="form.password" type="password" show-password :placeholder="isEdit ? $t('channels.leaveEmptyNoChange') : $t('channels.password')" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>
        
        <template v-if="form.protocol === 'HTTP'">
          <el-divider content-position="left">{{ $t('channels.httpConfig') }}</el-divider>
          <el-form-item :label="$t('channels.apiUrl')" prop="api_url">
            <el-input v-model="form.api_url" :placeholder="$t('channels.apiUrlPlaceholder')" />
          </el-form-item>
          <el-row :gutter="24">
            <el-col :span="12">
              <el-form-item :label="$t('channels.username')" prop="username">
                <el-input v-model="form.username" :placeholder="$t('channels.httpAccountPlaceholder')" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="$t('channels.password')" prop="password">
                <el-input v-model="form.password" type="password" show-password :placeholder="isEdit ? $t('channels.leaveEmptyNoChange') : $t('channels.password')" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="API Key" prop="api_key">
            <el-input v-model="form.api_key" type="password" show-password :placeholder="isEdit ? $t('channels.leaveEmptyNoChange') : $t('common.optional')" />
          </el-form-item>
        </template>

        <!-- VIRTUAL 虚拟通道配置 -->
        <template v-if="form.protocol === 'VIRTUAL'">
          <el-divider content-position="left">虚拟通道回执配置</el-divider>
          <el-alert type="info" :closable="false" style="margin-bottom: 18px" show-icon>
            虚拟通道不实际发送短信，系统将根据以下配置自动生成模拟回执
          </el-alert>

          <div class="virtual-rate-group">
            <div class="virtual-rate-row">
              <div class="virtual-rate-item">
                <span class="virtual-rate-label success">送达率</span>
                <el-input-number v-model="form.virtual_config.delivery_rate_min" :min="0" :max="100" :step="0.5" :precision="1" controls-position="right" size="small" style="width: 100px" />
                <span class="virtual-rate-sep">~</span>
                <el-input-number v-model="form.virtual_config.delivery_rate_max" :min="0" :max="100" :step="0.5" :precision="1" controls-position="right" size="small" style="width: 100px" />
                <span class="virtual-rate-unit">%</span>
              </div>
              <div class="virtual-rate-item">
                <span class="virtual-rate-label danger">失败率</span>
                <el-input-number v-model="form.virtual_config.fail_rate_min" :min="0" :max="100" :step="0.5" :precision="1" controls-position="right" size="small" style="width: 100px" />
                <span class="virtual-rate-sep">~</span>
                <el-input-number v-model="form.virtual_config.fail_rate_max" :min="0" :max="100" :step="0.5" :precision="1" controls-position="right" size="small" style="width: 100px" />
                <span class="virtual-rate-unit">%</span>
              </div>
              <div class="virtual-rate-item">
                <span class="virtual-rate-label warning">过期率</span>
                <span class="virtual-rate-computed">{{ virtualExpiredRange }}</span>
              </div>
            </div>
            <div class="virtual-rate-hint">
              系统会在区间范围内自然浮动，最终统计呈现真实小数比例（如 89.54%），而非整数。
            </div>
          </div>

          <el-row :gutter="24" style="margin-top: 8px">
            <el-col :span="12">
              <el-form-item label="回执延迟">
                <div style="display:flex;gap:8px;align-items:center">
                  <el-input-number v-model="form.virtual_config.dlr_delay_min" :min="1" :max="3600" controls-position="right" style="width: 110px" />
                  <span style="color: var(--el-text-color-secondary)">~</span>
                  <el-input-number v-model="form.virtual_config.dlr_delay_max" :min="1" :max="3600" controls-position="right" style="width: 110px" />
                  <span style="color: var(--el-text-color-secondary); font-size: 13px">秒</span>
                </div>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="失败错误码">
                <el-select v-model="form.virtual_config.fail_codes" multiple collapse-tags collapse-tags-tooltip style="width: 100%" placeholder="选择模拟错误码">
                  <el-option label="UNDELIV (未送达)" value="UNDELIV" />
                  <el-option label="REJECTD (被拒绝)" value="REJECTD" />
                  <el-option label="UNKNOWN (未知)" value="UNKNOWN" />
                  <el-option label="EXPIRED (过期)" value="EXPIRED" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <el-divider content-position="left">{{ $t('channels.channelParams') }}</el-divider>
        <el-row :gutter="24">
          <el-col :span="8">
            <el-form-item :label="$t('channels.defaultSid')">
              <el-input v-model="form.default_sender_id" :placeholder="$t('channels.senderIdPlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="$t('channels.channelStatus')" prop="status">
              <el-select v-model="form.status" style="width: 100%">
                <el-option :label="$t('channels.active')" value="active" />
                <el-option :label="$t('channels.inactive')" value="inactive" />
                <el-option :label="$t('channels.maintenance')" value="maintenance" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="$t('channels.supplier')">
              <el-select
                v-model="form.supplier_id"
                :placeholder="$t('channels.selectSupplierPlaceholder')"
                clearable
                filterable
                style="width: 100%"
              >
                <el-option
                  v-for="s in formSupplierList"
                  :key="s.id"
                  :label="`${s.supplier_name} (${s.supplier_code})`"
                  :value="s.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">{{ $t('channels.rateControl') }}</el-divider>
        <el-row :gutter="24">
          <el-col :span="8">
            <el-form-item :label="$t('channels.maxTps')" prop="max_tps">
              <el-input-number v-model="form.max_tps" :min="1" :max="10000" controls-position="right" style="width: 100%">
                <template #suffix>{{ $t('channels.perSecond') }}</template>
              </el-input-number>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="$t('channels.concurrency')" prop="concurrency">
              <el-input-number v-model="form.concurrency" :min="1" :max="100" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="$t('channels.rateControlWindow')" prop="rate_control_window">
              <el-input-number v-model="form.rate_control_window" :min="10" :max="600000" :step="10" controls-position="right" style="width: 100%">
                <template #suffix>ms</template>
              </el-input-number>
            </el-form-item>
          </el-col>
        </el-row>
        <div class="form-tip">
          {{ $t('channels.rateControlTip') }}
        </div>

        <el-divider content-position="left">违禁词管理</el-divider>
        <el-form-item label="全局违禁词">
          <el-input
            v-model="form.banned_words"
            type="textarea"
            :rows="3"
            placeholder="该通道所有国家通用的违禁词，每行一个或逗号分隔"
            resize="vertical"
          />
          <div style="font-size: 11px; color: var(--el-text-color-placeholder); margin-top: 4px;">
            此处配置对该通道所有国家生效。如需按国家单独配置，请在「路由规则」中为每个国家设置专属违禁词。
          </div>
        </el-form-item>

        <template v-if="!isEdit">
          <el-divider content-position="left">{{ $t('channels.pricingConfigOptional') }}</el-divider>
          <div class="inline-pricing">
            <div class="inline-pricing-actions">
              <el-button size="small" type="primary" @click="addPricingRow">{{ $t('channels.addPricing') }}</el-button>
              <el-button size="small" @click="clearPricingRows">{{ $t('common.clear') }}</el-button>
            </div>

            <el-table :data="pricingRows" size="small" style="width: 100%" class="pricing-table">
              <el-table-column :label="$t('channels.countryCode')" min-width="90">
                <template #default="{ row }">
                  <el-input v-model="row.country_code" size="small" placeholder="CN" />
                </template>
              </el-table-column>
              <el-table-column :label="$t('channels.countryName')" min-width="130">
                <template #default="{ row }">
                  <el-input v-model="row.country_name" size="small" placeholder="China" />
                </template>
              </el-table-column>
              <el-table-column :label="$t('channels.unitPrice')" min-width="110">
                <template #default="{ row }">
                  <el-input-number v-model="row.price_per_sms" size="small" :min="0" :precision="5" :step="0.001" controls-position="right" style="width: 100%" />
                </template>
              </el-table-column>
              <el-table-column :label="$t('channels.currency')" min-width="85">
                <template #default="{ row }">
                  <el-select v-model="row.currency" size="small" style="width: 100%">
                    <el-option label="USD" value="USD" />
                    <el-option label="CNY" value="CNY" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column :label="$t('common.actions')" width="55" align="center">
                <template #default="{ $index }">
                  <el-button type="danger" link size="small" @click="removePricingRow($index)">{{ $t('common.delete') }}</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </template>
      </el-form>
      
      <template #footer>
        <el-button @click="formVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">
          {{ isEdit ? $t('common.save') : $t('common.create') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 路由规则管理对话框 -->
    <el-dialog
      v-model="routingVisible"
      :title="routingChannel ? `${$t('channels.routingConfig')} - ${routingChannel.name}` : $t('channels.routingConfig')"
      width="800px"
      :close-on-click-modal="false"
    >
      <div class="dialog-toolbar">
        <div class="toolbar-left">
          <el-button size="small" type="primary" @click="openRoutingForm()">{{ $t('channels.addRouting') }}</el-button>
          <el-input
            v-model="routingCountryFilter"
            size="small"
            :placeholder="$t('channels.countryCodeFilter')"
            style="width: 150px"
            @keyup.enter="loadRoutingRules"
          />
          <el-button size="small" @click="loadRoutingRules">{{ $t('common.refresh') }}</el-button>
        </div>
      </div>

      <el-table :data="routingRules" v-loading="routingLoading" class="data-table">
        <el-table-column prop="country_code" :label="$t('channels.countryCode')" width="120">
          <template #default="{ row }">
            {{ routingCountryLabel(row.country_code) }}
          </template>
        </el-table-column>
        <el-table-column prop="priority" :label="$t('channels.priority')" width="100" align="center" />
        <el-table-column prop="is_active" :label="$t('channels.enabled')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? $t('channels.enabled') : $t('channels.disabled') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="违禁词" min-width="100" align="center">
          <template #default="{ row }">
            <template v-if="row.banned_words">
              <el-tooltip :content="row.banned_words" placement="top" :show-after="300">
                <el-tag size="small" type="danger">{{ row.banned_words.split(/[,，\n]/).filter((w: string) => w.trim()).length }} 个</el-tag>
              </el-tooltip>
            </template>
            <span v-else style="color: var(--el-text-color-placeholder)">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" :label="$t('common.updatedAt')" min-width="160">
          <template #default="{ row }">
            {{ row.updated_at ? new Date(row.updated_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.actions')" width="150" align="center">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openRoutingForm(row)">{{ $t('common.edit') }}</el-button>
            <el-popconfirm :title="$t('common.confirmDelete')" @confirm="handleDeleteRouting(row)">
              <template #reference>
                <el-button type="danger" link size="small">{{ $t('common.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 新增/编辑路由规则对话框 -->
    <el-dialog
      v-model="routingFormVisible"
      :title="routingEditing ? $t('channels.editRoutingRule') : $t('channels.addRoutingRule')"
      width="450px"
      :close-on-click-modal="false"
      append-to-body
    >
      <el-form :model="routingForm" label-width="80px">
        <el-form-item :label="$t('channels.countryCode')" required>
          <CountrySelect
            v-model="routingForm.country_code"
            :disabled="!!routingEditing"
            placeholder="选择国家（如泰国TH、菲律宾PH、越南VN）"
          />
        </el-form-item>
        <el-form-item :label="$t('channels.priority')" required>
          <el-input-number v-model="routingForm.priority" :min="0" :max="1000" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="$t('channels.enabled')">
          <el-switch v-model="routingForm.is_active" />
        </el-form-item>
        <el-form-item label="违禁词">
          <el-input
            v-model="routingForm.banned_words"
            type="textarea"
            :rows="4"
            placeholder="该国家专属违禁词，每行一个或逗号分隔"
            resize="vertical"
          />
          <div style="font-size: 11px; color: var(--el-text-color-placeholder); margin-top: 4px;">
            仅对该国家生效，与通道全局违禁词合并检测
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="routingFormVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="routingSubmitting" @click="saveRoutingRule">{{ $t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 费率管理对话框 -->
    <el-dialog
      v-model="pricingVisible"
      :title="pricingChannel ? `${$t('channels.pricingConfig')} - ${pricingChannel.name}` : $t('channels.pricingConfig')"
      width="900px"
      :close-on-click-modal="false"
    >
      <div class="dialog-toolbar">
        <div class="toolbar-left">
          <el-button size="small" type="primary" @click="openPricingForm()">{{ $t('channels.addPricing') }}</el-button>
          <el-input
            v-model="pricingCountryFilter"
            size="small"
            :placeholder="$t('channels.countryCodeFilter')"
            style="width: 150px"
            @keyup.enter="loadPricing"
          />
          <el-button size="small" @click="loadPricing">{{ $t('common.refresh') }}</el-button>
        </div>
      </div>

      <el-table :data="pricingList" v-loading="pricingLoading" class="data-table">
        <el-table-column prop="country_code" :label="$t('channels.countryCode')" width="100" />
        <el-table-column prop="country_name" :label="$t('channels.countryName')" min-width="140" />
        <el-table-column :label="$t('channels.unitPrice')" width="120" align="right">
          <template #default="{ row }">
            <span class="price-text">{{ row.price_per_sms }} {{ row.currency }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="mnc" :label="$t('channels.operatorCode')" width="100" />
        <el-table-column prop="operator_name" :label="$t('channels.operator')" min-width="120" />
        <el-table-column prop="effective_date" :label="$t('channels.effectiveDate')" width="120" />
        <el-table-column :label="$t('common.actions')" width="150" align="center">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openPricingForm(row)">{{ $t('common.edit') }}</el-button>
            <el-popconfirm :title="$t('common.confirmDelete')" @confirm="handleDeletePricing(row)">
              <template #reference>
                <el-button type="danger" link size="small">{{ $t('common.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 新增/编辑费率对话框 -->
    <el-dialog
      v-model="pricingFormVisible"
      :title="pricingEditing ? $t('channels.editPricingRule') : $t('channels.addPricingRule')"
      width="450px"
      :close-on-click-modal="false"
      append-to-body
    >
      <el-form :model="pricingForm" label-width="80px">
        <el-form-item :label="$t('channels.countryName')" required>
          <el-autocomplete
            v-model="pricingForm.country_name"
            :fetch-suggestions="countryQuerySearch"
            :disabled="!!pricingEditing"
            :placeholder="$t('channels.searchCountryPlaceholder')"
            style="width: 100%"
            @select="handleCountrySelect"
            clearable
          >
            <template #default="{ item }">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>{{ item.value }}</span>
                <span style="color: #909399; font-size: 12px;">+{{ item.code }}</span>
              </div>
            </template>
          </el-autocomplete>
        </el-form-item>
        <el-form-item :label="$t('channels.countryCode')" required>
          <el-input v-model="pricingForm.country_code" :disabled="!!pricingEditing" :placeholder="$t('channels.autoFill')" />
        </el-form-item>
        <el-form-item :label="$t('channels.unitPrice')" required>
          <el-input-number v-model="pricingForm.price_per_sms" :min="0" :precision="5" :step="0.001" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="$t('channels.currency')">
          <el-select v-model="pricingForm.currency" style="width: 100%">
            <el-option label="USD" value="USD" />
            <el-option label="CNY" value="CNY" />
            <el-option label="EUR" value="EUR" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('channels.operatorCode')">
          <el-input v-model="pricingForm.mnc" :disabled="!!pricingEditing" :placeholder="$t('common.optional')" />
        </el-form-item>
        <el-form-item :label="$t('channels.operatorName')">
          <el-input v-model="pricingForm.operator_name" :disabled="!!pricingEditing" :placeholder="$t('common.optional')" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="pricingFormVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="pricingSubmitting" @click="savePricing">{{ $t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 测试发送对话框 -->
    <el-dialog
      v-model="testSendVisible"
      :title="`${$t('channels.testSend')} - ${testChannel?.name || ''}`"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form :model="testForm" label-width="80px">
        <el-form-item :label="$t('channels.phoneNumber')" required>
          <el-input v-model="testForm.phone" :placeholder="$t('channels.testPhonePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('channels.content')" required>
          <el-input v-model="testForm.content" type="textarea" :rows="3" :placeholder="$t('channels.testContentPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('channels.senderId')">
          <el-input v-model="testForm.sender_id" :placeholder="testChannel?.default_sender_id || $t('common.optional')" />
        </el-form-item>
      </el-form>

      <!-- 测试结果 -->
      <div v-if="testResult" class="test-result" :class="testResult.success ? 'success' : 'error'">
        <div class="result-header">
          <el-icon v-if="testResult.success"><CircleCheck /></el-icon>
          <el-icon v-else><CircleClose /></el-icon>
          <span>{{ testResult.message }}</span>
        </div>
        <div class="result-details" v-if="testResult.details">
          <div v-for="(value, key) in testResult.details" :key="key" class="detail-row">
            <span class="detail-label">{{ key }}:</span>
            <span class="detail-value">{{ value }}</span>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="testSendVisible = false">{{ $t('common.close') }}</el-button>
        <el-button type="primary" :loading="testSending" @click="handleTestSend">{{ $t('channels.sendTest') }}</el-button>
      </template>
    </el-dialog>

    <!-- 状态检测结果对话框 -->
    <el-dialog
      v-model="statusCheckVisible"
      :title="`${$t('channels.statusCheck')} - ${statusChannel?.name || ''}`"
      width="450px"
    >
      <div v-if="statusChecking" class="status-checking">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>{{ $t('channels.checkingStatus') }}</span>
      </div>
      <div v-else-if="statusResult" class="status-result" :class="statusResult.status">
        <div class="status-icon">
          <el-icon v-if="statusResult.status === 'online'"><CircleCheck /></el-icon>
          <el-icon v-else-if="statusResult.status === 'timeout'"><Clock /></el-icon>
          <el-icon v-else-if="statusResult.status === 'unknown'"><InfoFilled /></el-icon>
          <el-icon v-else><CircleClose /></el-icon>
        </div>
        <div class="status-info">
          <div class="status-text">{{ statusResult.message }}</div>
          <div class="status-details" v-if="statusResult.details">
            <div v-for="(value, key) in statusResult.details" :key="key" class="detail-row">
              <span class="detail-label">{{ key }}:</span>
              <span class="detail-value">{{ value }}</span>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="statusCheckVisible = false">{{ $t('common.close') }}</el-button>
        <el-button type="primary" @click="handleCheckStatus(statusChannel)" :loading="statusChecking">{{ $t('channels.recheck') }}</el-button>
      </template>
    </el-dialog>

    <!-- 供应商关联对话框 -->
    <el-dialog
      v-model="supplierDialogVisible"
      :title="`${$t('channels.linkSupplier')} - ${supplierChannel?.name || ''}`"
      width="500px"
    >
      <el-form label-width="80px">
        <el-form-item :label="$t('channels.selectSupplier')">
          <el-select 
            v-model="selectedSupplierId" 
            :placeholder="$t('channels.selectSupplierPlaceholder')" 
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="s in supplierList"
              :key="s.id"
              :label="`${s.supplier_name} (${s.supplier_code})`"
              :value="s.id"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="supplierDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="linkingSupplier" @click="handleLinkSupplier">{{ $t('channels.confirmLink') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Plus, Refresh, Search, Connection, CircleCheck, Promotion, Link, CircleClose, Loading, Clock, Position, User, Edit, Money, Monitor, More, View, Guide, Delete, ChatDotSquare, ArrowDown, InfoFilled } from '@element-plus/icons-vue'
import CountrySelect from '@/components/CountrySelect.vue'
import { findCountryByDial, findCountryByIso } from '@/constants/countries'
import { getChannels } from '@/api/channel'
import { 
  createChannel, 
  updateChannel, 
  deleteChannel,
  getChannelAdmin,
  getPricingList,
  createPricing,
  updatePricing,
  deletePricing,
  getRoutingRules,
  createRoutingRule,
  updateRoutingRule,
  deleteRoutingRule,
  channelTestSend,
  channelCheckStatus,
  channelCheckAllStatus,
  getSuppliers,
  linkSupplierChannel
} from '@/api/admin'

const { t } = useI18n()
const loading = ref(false)
const detailVisible = ref(false)
const formVisible = ref(false)
const submitting = ref(false)
const isEdit = ref(false)
const currentChannel = ref<any>(null)
const channels = ref<any[]>([])
const formRef = ref()
const pricingRows = ref<any[]>([])

// 测试发送相关
const testSendVisible = ref(false)
const testSending = ref(false)
const testChannel = ref<any>(null)
const testResult = ref<any>(null)
const testForm = reactive({
  phone: '',
  content: '',
  sender_id: ''
})

// 状态检测相关
const statusCheckVisible = ref(false)
const statusChecking = ref(false)
const checkingAll = ref(false)
const statusChannel = ref<any>(null)
const statusResult = ref<any>(null)

// 供应商关联相关
const supplierDialogVisible = ref(false)
const supplierChannel = ref<any>(null)
const supplierList = ref<any[]>([])
const selectedSupplierId = ref<number | null>(null)
const linkingSupplier = ref(false)

// 筛选
const filters = reactive({ keyword: '', protocol: '', status: '' })
const resetFilters = () => {
  filters.keyword = ''
  filters.protocol = ''
  filters.status = ''
}

const virtualExpiredRange = computed(() => {
  const vc = form.virtual_config
  const maxUsed = vc.delivery_rate_max + vc.fail_rate_max
  const minUsed = vc.delivery_rate_min + vc.fail_rate_min
  const expMin = Math.max(0, 100 - maxUsed)
  const expMax = Math.max(0, 100 - minUsed)
  if (expMin === expMax) return `${expMin}%`
  return `${expMin}% ~ ${expMax}%`
})

// 统计
const stats = computed(() => {
  const total = channels.value.length
  const active = channels.value.filter(c => c.connection_status === 'online').length
  const smpp = channels.value.filter(c => c.protocol === 'SMPP').length
  const http = channels.value.filter(c => c.protocol === 'HTTP').length
  const virtual_count = channels.value.filter(c => c.protocol === 'VIRTUAL').length
  return { total, active, smpp, http, virtual_count }
})

// 过滤后的通道
const filteredChannels = computed(() => {
  return channels.value.filter(c => {
    if (filters.keyword && !c.code?.toLowerCase().includes(filters.keyword.toLowerCase()) 
        && !c.name?.toLowerCase().includes(filters.keyword.toLowerCase())) return false
    if (filters.protocol && c.protocol !== filters.protocol) return false
    if (filters.status && c.status !== filters.status) return false
    return true
  })
})

const createEmptyPricingRow = () => ({
  country_code: '',
  country_name: '',
  price_per_sms: 0,
  currency: 'USD',
  mnc: '',
  operator_name: ''
})

const addPricingRow = () => {
  pricingRows.value.push(createEmptyPricingRow())
}

const removePricingRow = (index: number) => {
  pricingRows.value.splice(index, 1)
}

const clearPricingRows = () => {
  pricingRows.value = []
}

// 路由规则管理
const routingVisible = ref(false)
const routingLoading = ref(false)
const routingRules = ref<any[]>([])
const routingChannel = ref<any>(null)
const routingCountryFilter = ref('')
const routingFormVisible = ref(false)
const routingSubmitting = ref(false)
const routingEditing = ref<any>(null)

const routingForm = reactive({
  id: 0,
  country_code: '',
  priority: 0,
  is_active: true,
  banned_words: ''
})

// 费率管理
const pricingVisible = ref(false)
const pricingLoading = ref(false)
const pricingList = ref<any[]>([])
const pricingChannel = ref<any>(null)
const pricingCountryFilter = ref('')
const pricingFormVisible = ref(false)
const pricingSubmitting = ref(false)
const pricingEditing = ref<any>(null)

const pricingForm = reactive({
  id: 0,
  country_code: '',
  country_name: '',
  price_per_sms: 0,
  currency: 'USD',
  mnc: '',
  operator_name: ''
})

// 国家列表（国家名称 -> 国家代码）
const countryList = [
  { name: '阿富汗', code: '93' },
  { name: '阿尔巴尼亚', code: '355' },
  { name: '阿尔及利亚', code: '213' },
  { name: '阿根廷', code: '54' },
  { name: '澳大利亚', code: '61' },
  { name: '奥地利', code: '43' },
  { name: '孟加拉国', code: '880' },
  { name: '比利时', code: '32' },
  { name: '巴西', code: '55' },
  { name: '柬埔寨', code: '855' },
  { name: '加拿大', code: '1' },
  { name: '智利', code: '56' },
  { name: '中国', code: '86' },
  { name: '哥伦比亚', code: '57' },
  { name: '捷克', code: '420' },
  { name: '丹麦', code: '45' },
  { name: '埃及', code: '20' },
  { name: '芬兰', code: '358' },
  { name: '法国', code: '33' },
  { name: '德国', code: '49' },
  { name: '加纳', code: '233' },
  { name: '希腊', code: '30' },
  { name: '香港', code: '852' },
  { name: '匈牙利', code: '36' },
  { name: '印度', code: '91' },
  { name: '印度尼西亚', code: '62' },
  { name: '伊朗', code: '98' },
  { name: '伊拉克', code: '964' },
  { name: '爱尔兰', code: '353' },
  { name: '以色列', code: '972' },
  { name: '意大利', code: '39' },
  { name: '日本', code: '81' },
  { name: '约旦', code: '962' },
  { name: '肯尼亚', code: '254' },
  { name: '韩国', code: '82' },
  { name: '科威特', code: '965' },
  { name: '老挝', code: '856' },
  { name: '黎巴嫩', code: '961' },
  { name: '澳门', code: '853' },
  { name: '马来西亚', code: '60' },
  { name: '墨西哥', code: '52' },
  { name: '摩洛哥', code: '212' },
  { name: '缅甸', code: '95' },
  { name: '尼泊尔', code: '977' },
  { name: '荷兰', code: '31' },
  { name: '新西兰', code: '64' },
  { name: '尼日利亚', code: '234' },
  { name: '挪威', code: '47' },
  { name: '巴基斯坦', code: '92' },
  { name: '秘鲁', code: '51' },
  { name: '菲律宾', code: '63' },
  { name: '波兰', code: '48' },
  { name: '葡萄牙', code: '351' },
  { name: '卡塔尔', code: '974' },
  { name: '罗马尼亚', code: '40' },
  { name: '俄罗斯', code: '7' },
  { name: '沙特阿拉伯', code: '966' },
  { name: '新加坡', code: '65' },
  { name: '南非', code: '27' },
  { name: '西班牙', code: '34' },
  { name: '斯里兰卡', code: '94' },
  { name: '瑞典', code: '46' },
  { name: '瑞士', code: '41' },
  { name: '台湾', code: '886' },
  { name: '泰国', code: '66' },
  { name: '土耳其', code: '90' },
  { name: '阿联酋', code: '971' },
  { name: '英国', code: '44' },
  { name: '乌克兰', code: '380' },
  { name: '美国', code: '1' },
  { name: '越南', code: '84' },
]

// 国家搜索建议
const countryQuerySearch = (queryString: string, cb: (results: any[]) => void) => {
  const results = queryString
    ? countryList.filter(c => 
        c.name.toLowerCase().includes(queryString.toLowerCase()) ||
        c.code.includes(queryString)
      )
    : countryList
  cb(results.map(c => ({ value: c.name, code: c.code })))
}

// 选择国家后自动填充代码
const handleCountrySelect = (item: { value: string, code: string }) => {
  pricingForm.country_name = item.value
  pricingForm.country_code = item.code
}

const formSupplierList = ref<any[]>([])
const defaultVirtualConfig = () => ({
  delivery_rate_min: 80,
  delivery_rate_max: 90,
  fail_rate_min: 5,
  fail_rate_max: 15,
  dlr_delay_min: 3,
  dlr_delay_max: 30,
  fail_codes: ['UNDELIV'] as string[],
})

const form = reactive({
  id: 0,
  channel_code: '',
  channel_name: '',
  protocol: 'SMPP',
  host: '',
  port: 2775,
  username: '',
  password: '',
  api_url: '',
  api_key: '',
  default_sender_id: '',
  status: 'active',
  priority: 0,
  weight: 100,
  max_tps: 100,
  concurrency: 1,
  rate_control_window: 1000,
  supplier_id: null as number | null,
  banned_words: '',
  virtual_config: defaultVirtualConfig(),
})

const rules = computed(() => ({
  channel_code: [{ required: true, message: t('channels.pleaseEnterChannelCode'), trigger: 'blur' }],
  channel_name: [{ required: true, message: t('channels.pleaseEnterChannelName'), trigger: 'blur' }],
  protocol: [{ required: true, message: t('channels.pleaseSelectProtocol'), trigger: 'change' }],
}))

const mapAdminChannel = (ch: any) => ({
  id: ch.id,
  code: ch.channel_code,
  name: ch.channel_name,
  protocol: ch.protocol,
  status: ch.status,
  connection_status: ch.connection_status ?? 'unknown',
  connection_checked_at: ch.connection_checked_at ?? null,
  priority: ch.priority,
  weight: ch.weight,
  host: ch.host,
  port: ch.port,
  username: ch.username,
  api_url: ch.api_url,
  default_sender_id: ch.default_sender_id,
  created_at: ch.created_at,
  updated_at: ch.updated_at,
  banned_words: ch.banned_words ?? '',
  virtual_config: ch.virtual_config ?? null,
})

const loadChannels = async () => {
  loading.value = true
  try {
    const res = await getChannels()
    channels.value = res.channels || []
  } catch (error: any) {
    ElMessage.error(t('channels.loadFailed'))
  } finally {
    loading.value = false
  }
}

const handleViewDetail = async (row: any) => {
  currentChannel.value = { ...row }
  detailVisible.value = true
  
  if (row.id) {
    try {
      const res = await getChannelAdmin(row.id)
      if (res?.channel) {
        currentChannel.value = mapAdminChannel(res.channel)
      }
    } catch (error: any) {
      // ignore
    }
  }
}

const loadFormSuppliers = async () => {
  try {
    // 短信通道仅展示短信业务供应商
    const res = await getSuppliers({ status: 'active', business_type: 'sms', page_size: 500 })
    formSupplierList.value = res?.suppliers || res?.items || []
  } catch (e) {
    console.warn('加载供应商列表失败:', e)
    formSupplierList.value = []
  }
}

const handleCreate = () => {
  isEdit.value = false
  pricingRows.value = [createEmptyPricingRow()]
  Object.assign(form, {
    id: 0,
    channel_code: '',
    channel_name: '',
    protocol: 'SMPP',
    host: '',
    port: 2775,
    username: '',
    password: '',
    api_url: '',
    api_key: '',
    default_sender_id: '',
    status: 'active',
    priority: 0,
    weight: 100,
    max_tps: 100,
    concurrency: 1,
    rate_control_window: 1000,
    supplier_id: null,
    banned_words: '',
    virtual_config: defaultVirtualConfig(),
  })
  formVisible.value = true
}

const handleEdit = async (row: any) => {
  isEdit.value = true
  Object.assign(form, {
    id: row.id,
    channel_code: row.code,
    channel_name: row.name,
    protocol: row.protocol,
    host: row.host || '',
    port: row.port || 2775,
    username: row.username || '',
    password: '',
    api_url: row.api_url || '',
    api_key: '',
    default_sender_id: row.default_sender_id || '',
    status: row.status,
    priority: row.priority ?? 0,
    weight: row.weight ?? 100,
    max_tps: row.max_tps ?? 100,
    concurrency: row.concurrency ?? 1,
    rate_control_window: row.rate_control_window ?? 1000,
    supplier_id: row.supplier?.id ?? null,
    banned_words: row.banned_words ?? '',
    virtual_config: row.virtual_config ? { ...defaultVirtualConfig(), ...row.virtual_config } : defaultVirtualConfig(),
  })
  formVisible.value = true

  try {
    const res = await getChannelAdmin(row.id)
    const ch = res?.channel
    if (ch) {
      Object.assign(form, {
        id: ch.id,
        channel_code: ch.channel_code,
        channel_name: ch.channel_name,
        protocol: ch.protocol,
        host: ch.host || '',
        port: ch.port || 2775,
        username: ch.username || '',
        password: '',
        api_url: ch.api_url || '',
        api_key: '',
        default_sender_id: ch.default_sender_id || '',
        status: ch.status,
        priority: ch.priority ?? 0,
        weight: ch.weight ?? 100,
        max_tps: ch.max_tps ?? 100,
        concurrency: ch.concurrency ?? 1,
        rate_control_window: ch.rate_control_window ?? 1000,
        supplier_id: ch.supplier_id ?? row.supplier?.id ?? null,
        banned_words: ch.banned_words ?? '',
        virtual_config: ch.virtual_config ? { ...defaultVirtualConfig(), ...ch.virtual_config } : defaultVirtualConfig(),
      })
    } else {
      form.supplier_id = row.supplier?.id ?? null
    }
  } catch (error: any) {
    form.supplier_id = row.supplier?.id ?? null
  }
}

const openRouting = async (row: any) => {
  routingChannel.value = row
  routingCountryFilter.value = ''
  routingVisible.value = true
  await loadRoutingRules()
}

const loadRoutingRules = async () => {
  if (!routingChannel.value?.id) return
  routingLoading.value = true
  try {
    const res = await getRoutingRules(
      routingChannel.value.id,
      routingCountryFilter.value || undefined
    )
    routingRules.value = res.rules || []
  } catch (error: any) {
    ElMessage.error(t('channels.loadRoutingFailed'))
  } finally {
    routingLoading.value = false
  }
}

const routingCountryLabel = (code: string) => {
  if (!code) return '-'
  const c = /^\d+$/.test(code) ? findCountryByDial(code) : findCountryByIso(code)
  return c ? `${c.name} (${code})` : code
}

const openRoutingForm = (row?: any) => {
  routingEditing.value = row || null
  // 路由支持国码(66)或ISO(TH)，编辑时若为国码则转为ISO以便CountrySelect显示
  let countryCode = row?.country_code || ''
  if (countryCode && /^\d+$/.test(countryCode)) {
    const c = findCountryByDial(countryCode)
    if (c) countryCode = c.iso
  }
  Object.assign(routingForm, {
    id: row?.id || 0,
    country_code: countryCode,
    priority: row?.priority ?? (routingChannel.value?.priority ?? 0),
    is_active: row?.is_active ?? true,
    banned_words: row?.banned_words ?? ''
  })
  routingFormVisible.value = true
}

const saveRoutingRule = async () => {
  if (!routingChannel.value?.id) return
  if (!routingEditing.value && !routingForm.country_code) {
    ElMessage.warning(t('channels.fillCountryCodeRequired'))
    return
  }

  routingSubmitting.value = true
  try {
    if (routingEditing.value) {
      await updateRoutingRule(routingEditing.value.id, {
        priority: routingForm.priority,
        is_active: routingForm.is_active,
        banned_words: routingForm.banned_words || null
      })
      ElMessage.success(t('channels.routingUpdateSuccess'))
    } else {
      await createRoutingRule({
        channel_id: routingChannel.value.id,
        country_code: routingForm.country_code,
        priority: routingForm.priority,
        is_active: routingForm.is_active,
        banned_words: routingForm.banned_words || null
      })
      ElMessage.success(t('channels.routingCreateSuccess'))
    }

    routingFormVisible.value = false
    routingEditing.value = null
    await loadRoutingRules()
  } catch (error: any) {
    ElMessage.error(error.message || t('common.saveFailed'))
  } finally {
    routingSubmitting.value = false
  }
}

const handleDeleteRouting = async (row: any) => {
  try {
    await deleteRoutingRule(row.id)
    ElMessage.success(t('common.deleteSuccess'))
    await loadRoutingRules()
  } catch (error: any) {
    ElMessage.error(t('common.deleteFailed'))
  }
}

const openPricing = async (row: any) => {
  pricingChannel.value = row
  pricingCountryFilter.value = ''
  pricingVisible.value = true
  await loadPricing()
}

const loadPricing = async () => {
  if (!pricingChannel.value?.id) return
  pricingLoading.value = true
  try {
    const res = await getPricingList(
      pricingChannel.value.id,
      pricingCountryFilter.value || undefined
    )
    pricingList.value = res.pricing || []
  } catch (error: any) {
    ElMessage.error(t('channels.loadPricingFailed'))
  } finally {
    pricingLoading.value = false
  }
}

const openPricingForm = (row?: any) => {
  pricingEditing.value = row || null
  Object.assign(pricingForm, {
    id: row?.id || 0,
    country_code: row?.country_code || '',
    country_name: row?.country_name || '',
    price_per_sms: row?.price_per_sms ?? 0,
    currency: row?.currency || 'USD',
    mnc: row?.mnc || '',
    operator_name: row?.operator_name || ''
  })
  pricingFormVisible.value = true
}

const savePricing = async () => {
  if (!pricingChannel.value?.id) return
  if (!pricingEditing.value) {
    if (!pricingForm.country_code || !pricingForm.country_name) {
      ElMessage.warning(t('channels.fillCountryRequired'))
      return
    }
  }

  pricingSubmitting.value = true
  try {
    if (pricingEditing.value) {
      await updatePricing(pricingEditing.value.id, pricingForm.price_per_sms, pricingForm.currency)
      ElMessage.success(t('channels.pricingUpdateSuccess'))
    } else {
      const res = await createPricing({
        channel_id: pricingChannel.value.id,
        country_code: pricingForm.country_code,
        country_name: pricingForm.country_name,
        price_per_sms: pricingForm.price_per_sms,
        currency: pricingForm.currency,
        mnc: pricingForm.mnc || undefined,
        operator_name: pricingForm.operator_name || undefined
      })
      ElMessage.success(t('channels.pricingCreateSuccess') + (res?.routing_auto_created ? t('channels.routingAutoCreated') : ''))
    }

    pricingFormVisible.value = false
    pricingEditing.value = null
    await loadPricing()
  } catch (error: any) {
    ElMessage.error(error.message || t('common.saveFailed'))
  } finally {
    pricingSubmitting.value = false
  }
}

const handleDeletePricing = async (row: any) => {
  try {
    await deletePricing(row.id)
    ElMessage.success(t('common.deleteSuccess'))
    await loadPricing()
  } catch (error: any) {
    ElMessage.error(t('common.deleteFailed'))
  }
}

const handleDelete = async (row: any) => {
  try {
    await deleteChannel(row.id)
    ElMessage.success(t('common.deleteSuccess'))
    loadChannels()
  } catch (error: any) {
    ElMessage.error(t('common.deleteFailed') + ': ' + (error.message || t('common.unknownError')))
  }
}

/** 从 Axios 错误中解析后端 detail（含 FastAPI 422 数组），用于保存失败提示 */
const formatRequestErrorMessage = (error: any): string => {
  const d = error?.response?.data?.detail
  if (Array.isArray(d)) {
    return d
      .map((it: any) => {
        if (typeof it?.msg === 'string') {
          const loc = Array.isArray(it.loc) ? it.loc.filter((x: any) => x !== 'body').join('.') : ''
          return loc ? `${loc}: ${it.msg}` : it.msg
        }
        return typeof it === 'string' ? it : JSON.stringify(it)
      })
      .join('; ')
  }
  if (typeof d === 'string') return d
  if (d && typeof d === 'object' && typeof d.message === 'string') return d.message
  return error?.message || t('common.unknownError')
}

const submitForm = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
  } catch {
    ElMessage.warning(t('channels.formValidationFailed'))
    return
  }

  submitting.value = true
  try {
    if (isEdit.value) {
      const updatePayload: any = {
        channel_name: form.channel_name,
        max_tps: form.max_tps,
        concurrency: form.concurrency,
        rate_control_window: form.rate_control_window,
        status: form.status,
        host: form.protocol === 'SMPP' ? form.host : undefined,
        port: form.protocol === 'SMPP' ? form.port : undefined,
        username: form.username || undefined,
        password: form.password || undefined,
        api_url: form.protocol === 'HTTP' ? form.api_url : undefined,
        api_key: form.protocol === 'HTTP' ? (form.api_key || undefined) : undefined,
        default_sender_id: form.default_sender_id || undefined
      }
      updatePayload.supplier_id = form.supplier_id ?? null
      updatePayload.banned_words = form.banned_words || null
      if (form.protocol === 'VIRTUAL') {
        updatePayload.virtual_config = form.virtual_config
      }
      await updateChannel(form.id, updatePayload)
      ElMessage.success(t('common.updateSuccess'))
    } else {
      const nonEmptyRows = pricingRows.value.filter((r: any) => {
        return (
          (r.country_code && r.country_code.trim()) ||
          (r.country_name && r.country_name.trim()) ||
          (typeof r.price_per_sms === 'number' && r.price_per_sms !== 0)
        )
      })
      for (const r of nonEmptyRows) {
        if (!r.country_code || !r.country_name) {
          throw new Error(t('channels.pricingRuleIncomplete'))
        }
      }

      const createPayload: any = {
        channel_code: form.channel_code,
        channel_name: form.channel_name,
        protocol: form.protocol,
        host: form.protocol === 'SMPP' ? form.host : undefined,
        port: form.protocol === 'SMPP' ? form.port : undefined,
        username: form.username || undefined,
        password: form.password || undefined,
        api_url: form.protocol === 'HTTP' ? form.api_url : undefined,
        api_key: form.protocol === 'HTTP' ? form.api_key : undefined,
        default_sender_id: form.default_sender_id,
        status: form.status,
        max_tps: form.max_tps,
        concurrency: form.concurrency,
        rate_control_window: form.rate_control_window,
        priority: 0,
        weight: 100
      }
      if (form.supplier_id) {
        createPayload.supplier_id = form.supplier_id
      }
      if (form.banned_words) {
        createPayload.banned_words = form.banned_words
      }
      if (form.protocol === 'VIRTUAL') {
        createPayload.virtual_config = form.virtual_config
      }
      const created = await createChannel(createPayload)

      const channelId = created?.channel_id
      if (channelId && nonEmptyRows.length > 0) {
        for (const r of nonEmptyRows) {
          try {
            await createPricing({
              channel_id: channelId,
              country_code: r.country_code,
              country_name: r.country_name,
              price_per_sms: r.price_per_sms,
              currency: r.currency || 'USD',
            })
          } catch (e) {
            // ignore
          }
        }
      }

      ElMessage.success(t('common.createSuccess'))
      await loadChannels()
    }
    formVisible.value = false
    if (isEdit.value) {
      await loadChannels()
    }
  } catch (error: any) {
    ElMessage.error(
      (isEdit.value ? t('common.updateFailed') : t('common.createFailed')) +
        ': ' +
        formatRequestErrorMessage(error)
    )
  } finally {
    submitting.value = false
  }
}

const getStatusType = (status: string) => {
  const types: Record<string, any> = {
    active: 'success',
    inactive: 'info',
    maintenance: 'warning',
    fault: 'danger',
  }
  return types[status] || 'info'
}

const getStatusText = (status: string) => {
  const statusKeys: Record<string, string> = {
    active: 'channels.active',
    inactive: 'channels.inactive',
    maintenance: 'channels.maintenance',
    fault: 'channels.fault',
  }
  const key = statusKeys[status]
  return key ? t(key) : status
}

// 连接状态（通道状态列展示实际连通性）
const getConnectionStatusType = (connStatus: string) => {
  const types: Record<string, any> = {
    online: 'success',
    offline: 'danger',
    unknown: 'info',
  }
  return types[connStatus || 'unknown'] || 'info'
}

const getConnectionStatusText = (connStatus: string) => {
  const keys: Record<string, string> = {
    online: 'channels.statusOnline',
    offline: 'channels.statusOffline',
    unknown: 'channels.statusUnknown',
  }
  const key = keys[connStatus || 'unknown']
  return key ? t(key) : (connStatus || t('channels.statusUnknown'))
}

// 测试发送
const openTestSend = (row: any) => {
  testChannel.value = row
  testResult.value = null
  testForm.phone = ''
  testForm.content = 'This is a test SMS message.'
  testForm.sender_id = row.default_sender_id || ''
  testSendVisible.value = true
}

const handleTestSend = async () => {
  if (!testForm.phone) {
    ElMessage.warning(t('channels.enterPhoneNumber'))
    return
  }
  if (!testForm.content) {
    ElMessage.warning(t('channels.enterTestContent'))
    return
  }
  
  testSending.value = true
  testResult.value = null
  
  try {
    const res = await channelTestSend(testChannel.value.id, {
      phone: testForm.phone,
      content: testForm.content,
      sender_id: testForm.sender_id || undefined
    })
    testResult.value = res
    if (res.success) {
      ElMessage.success(t('channels.testSendSuccess'))
    }
  } catch (error: any) {
    testResult.value = {
      success: false,
      message: error.response?.data?.detail || error.message || t('channels.testSendFailed')
    }
  } finally {
    testSending.value = false
  }
}

// 一键检测所有通道
const handleCheckAllStatus = async () => {
  if (channels.value.length === 0) {
    ElMessage.warning(t('channels.noChannelsToCheck'))
    return
  }
  checkingAll.value = true
  try {
    const res = await channelCheckAllStatus()
    if (res?.success) {
      ElMessage.success(res.message || t('channels.checkAllSuccess'))
      await loadChannels()
    } else {
      ElMessage.error(res?.message || t('channels.checkAllFailed'))
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.message || t('channels.checkAllFailed'))
  } finally {
    checkingAll.value = false
  }
}

// 状态检测（单个）
const handleCheckStatus = async (row: any) => {
  statusChannel.value = row
  statusResult.value = null
  statusCheckVisible.value = true
  statusChecking.value = true

  try {
    const res = await channelCheckStatus(row.id)
    statusResult.value = res
    if (res.success) {
      ElMessage.success(t('channels.channelStatusNormal'))
    } else {
      ElMessage.warning(res.message || t('channels.channelStatusAbnormal'))
    }
    // 检测后刷新列表，使通道状态列立即更新
    await loadChannels()
  } catch (error: any) {
    statusResult.value = {
      success: false,
      status: 'error',
      message: error.response?.data?.detail || error.message || t('channels.statusCheckFailed')
    }
  } finally {
    statusChecking.value = false
  }
}

// 供应商关联相关方法
const loadSuppliers = async () => {
  try {
    const res = await getSuppliers({ page_size: 100, status: 'active' })
    supplierList.value = res.suppliers || []
  } catch (error) {
    console.error('Failed to load supplier list', error)
  }
}

const openSupplierDialog = async (row: any) => {
  supplierChannel.value = row
  selectedSupplierId.value = row.supplier?.id || null
  await loadSuppliers()
  supplierDialogVisible.value = true
}

const handleLinkSupplier = async () => {
  if (!selectedSupplierId.value) {
    ElMessage.warning(t('channels.pleaseSelectSupplier'))
    return
  }
  
  linkingSupplier.value = true
  try {
    await linkSupplierChannel(selectedSupplierId.value, supplierChannel.value.id)
    ElMessage.success(t('channels.linkSuccess'))
    supplierDialogVisible.value = false
    loadChannels()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('channels.linkFailed'))
  } finally {
    linkingSupplier.value = false
  }
}

onMounted(() => {
  loadChannels()
})
</script>

<style scoped>
.page-container {
  width: 100%;
  padding: 20px;
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
  font-size: 24px;
  font-weight: 600;
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
  transition: all 0.2s ease;
}

.stat-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
  transform: translateY(-1px);
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

.stat-icon.total { background: linear-gradient(135deg, rgba(102, 126, 234, 0.15), rgba(118, 75, 162, 0.1)); color: #667eea; }
.stat-icon.active { background: linear-gradient(135deg, rgba(103, 194, 58, 0.15), rgba(64, 158, 255, 0.05)); color: #67c23a; }
.stat-icon.smpp { background: linear-gradient(135deg, rgba(64, 158, 255, 0.15), rgba(102, 126, 234, 0.05)); color: #409eff; }
.stat-icon.http { background: linear-gradient(135deg, rgba(230, 162, 60, 0.15), rgba(245, 108, 108, 0.05)); color: #e6a23c; }

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1;
}

.stat-label {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

/* 筛选栏 */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 16px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 10px;
}

/* 表格卡片 */
.table-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

/* 表格样式 */
:deep(.channel-table) {
  --el-table-border-color: transparent;
}

:deep(.channel-table .el-table__header th) {
  background: var(--bg-subtle) !important;
  font-weight: 600;
  font-size: 13px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-default) !important;
  white-space: nowrap;
}

:deep(.channel-table .el-table__header th .cell) {
  white-space: nowrap;
  overflow: visible;
}

:deep(.channel-table .el-table__row:hover > td) {
  background: var(--bg-subtle) !important;
}

:deep(.channel-table td) {
  padding: 14px 0;
}

/* 文字样式 */
.code-text {
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}

.name-text {
  font-weight: 500;
  color: var(--text-primary);
}

.server-text {
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  font-size: 12px;
  color: var(--text-secondary);
}

.account-text {
  font-size: 13px;
  color: var(--text-secondary);
}

.num-text {
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.sid-text {
  font-size: 13px;
  color: var(--text-secondary);
}

.empty-text {
  color: var(--text-quaternary);
}

.price-text {
  color: #e6a23c;
  font-weight: 500;
}

/* 操作按钮 */
.action-btns {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  white-space: nowrap;
}

/* 创建/编辑通道对话框 */
:deep(.channel-form-dialog .el-dialog__body) {
  padding: 20px 24px;
}

.channel-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.channel-form :deep(.el-form-item__label) {
  font-weight: 500;
}

.channel-form :deep(.el-divider) {
  margin: 20px 0 16px;
}

.channel-form :deep(.el-divider__text) {
  font-weight: 600;
  color: var(--text-primary);
}

.channel-form :deep(.el-input-number) {
  width: 100%;
}

.channel-form :deep(.el-input-number .el-input__wrapper) {
  padding-left: 11px;
  padding-right: 40px;
}

.dialog-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.inline-pricing {
  margin-top: 8px;
}

.inline-pricing-actions {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

/* 通道详情弹窗样式 */
:deep(.channel-detail-dialog) .el-descriptions__label {
  font-weight: 600;
  background-color: var(--bg-input) !important;
}

/* 测试结果样式 */
.test-result {
  margin-top: 16px;
  padding: 16px;
  border-radius: 8px;
  border: 1px solid;
}

.test-result.success {
  background: rgba(103, 194, 58, 0.1);
  border-color: rgba(103, 194, 58, 0.3);
}

.test-result.error {
  background: rgba(245, 108, 108, 0.1);
  border-color: rgba(245, 108, 108, 0.3);
}

.result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 12px;
}

.test-result.success .result-header { color: #67c23a; }
.test-result.error .result-header { color: #f56c6c; }

.result-details {
  font-size: 13px;
}

.detail-row {
  display: flex;
  gap: 8px;
  margin-bottom: 4px;
}

.detail-label {
  color: var(--text-tertiary);
  min-width: 100px;
}

.detail-value {
  color: var(--text-primary);
  word-break: break-all;
}

/* 状态检测样式 */
.status-checking {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
  font-size: 14px;
  color: var(--text-secondary);
}

.status-checking .el-icon {
  font-size: 24px;
  color: #409eff;
}

.status-result {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 20px;
  border-radius: 8px;
  border: 1px solid;
}

.status-result.online {
  background: rgba(103, 194, 58, 0.1);
  border-color: rgba(103, 194, 58, 0.3);
}

.status-result.offline,
.status-result.error {
  background: rgba(245, 108, 108, 0.1);
  border-color: rgba(245, 108, 108, 0.3);
}

.status-result.timeout {
  background: rgba(230, 162, 60, 0.1);
  border-color: rgba(230, 162, 60, 0.3);
}

.status-result.unknown {
  background: rgba(144, 147, 153, 0.12);
  border-color: rgba(144, 147, 153, 0.35);
}

.status-icon {
  font-size: 32px;
}

.status-result.online .status-icon { color: #67c23a; }
.status-result.offline .status-icon,
.status-result.error .status-icon { color: #f56c6c; }
.status-result.timeout .status-icon { color: #e6a23c; }
.status-result.unknown .status-icon { color: #909399; }

.status-text {
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 12px;
  color: var(--text-primary);
}

.status-details {
  font-size: 13px;
}

@media (max-width: 1200px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 768px) {
  .stats-grid { grid-template-columns: 1fr; }
  .filter-bar { flex-direction: column; align-items: stretch; }
  .filter-bar > * { width: 100% !important; }
}

.virtual-rate-group {
  padding: 16px 20px;
  background: var(--el-fill-color-lighter, rgba(255, 255, 255, 0.04));
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter, rgba(255, 255, 255, 0.08));
}

.virtual-rate-row {
  display: flex;
  align-items: center;
  gap: 24px;
  flex-wrap: wrap;
}

.virtual-rate-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.virtual-rate-label {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  padding: 2px 10px;
  border-radius: 4px;
  margin-right: 4px;
}

.virtual-rate-label.success {
  color: var(--el-color-success);
  background: rgba(103, 194, 58, 0.1);
}

.virtual-rate-label.danger {
  color: var(--el-color-danger);
  background: rgba(245, 108, 108, 0.1);
}

.virtual-rate-label.warning {
  color: var(--el-color-warning);
  background: rgba(230, 162, 60, 0.1);
}

.virtual-rate-unit {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.virtual-rate-sep {
  font-size: 14px;
  color: var(--el-text-color-placeholder);
}

.virtual-rate-computed {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-color-warning);
}

.virtual-rate-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
