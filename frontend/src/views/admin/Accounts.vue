<template>
  <div class="page-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">{{ pageTitle }}</h1>
        <p class="page-desc">{{ pageDesc }}</p>
      </div>
      <div class="header-right">
        <el-button v-if="isVoiceTab && !isSalesRole" type="warning" :loading="okccSyncing" @click="handleOkccSync">
          <el-icon><Refresh /></el-icon>
          同步OKCC
        </el-button>
        <el-button v-if="!isSalesRole" type="primary" @click="openCreate" class="add-btn">
          <el-icon><Plus /></el-icon>
          {{ $t('customers.createAccount') }}
        </el-button>
      </div>
    </div>

    <!-- 业务类型 Tab -->
    <div class="biz-tabs">
      <div
        class="biz-tab" :class="{ active: businessTypeFilter === '' }"
        @click="switchBizType('')"
      >
        <span class="tab-label">全部客户</span>
        <span class="tab-count">{{ total }}</span>
      </div>
      <div
        class="biz-tab sms" :class="{ active: businessTypeFilter === 'sms' }"
        @click="switchBizType('sms')"
      >
        <span class="tab-icon">💬</span>
        <span class="tab-label">短信客户</span>
      </div>
      <div
        class="biz-tab voice" :class="{ active: businessTypeFilter === 'voice' }"
        @click="switchBizType('voice')"
      >
        <span class="tab-icon">📞</span>
        <span class="tab-label">语音客户</span>
      </div>
      <div
        class="biz-tab data" :class="{ active: businessTypeFilter === 'data' }"
        @click="switchBizType('data')"
      >
        <span class="tab-icon">📊</span>
        <span class="tab-label">数据客户</span>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon blue">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" stroke="currentColor" stroke-width="2"/><circle cx="9" cy="7" r="4" stroke="currentColor" stroke-width="2"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" stroke="currentColor" stroke-width="2"/></svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ total }}</span>
          <span class="stat-label">{{ $t('customers.totalCustomers') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon green">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M22 4 12 14.01l-3-3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ accounts.filter(a => a.status === 'active').length }}</span>
          <span class="stat-label">{{ $t('customers.activeAccounts') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon purple">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">${{ totalBalance.toFixed(2) }}</span>
          <span class="stat-label">{{ $t('customers.totalBalance') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon orange">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" stroke="currentColor" stroke-width="2"/></svg>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ accounts.filter(a => a.sales).length }}</span>
          <span class="stat-label">{{ $t('customers.boundSales') }}</span>
        </div>
      </div>
    </div>

    <!-- 主卡片 -->
    <div class="main-card">
      <div class="card-header">
        <div class="filter-section">
          <el-input
            v-model="keyword"
            :placeholder="$t('customers.searchPlaceholder')"
            class="filter-input-wide"
            @keyup.enter="runAccountSearch"
            clearable
            :prefix-icon="Search"
          />
          <el-input
            v-model="tgUsernameFilter"
            :placeholder="$t('customers.searchTgUsername')"
            class="filter-input-medium"
            clearable
            @keyup.enter="runAccountSearch"
          />
          <el-input
            v-model="countryQueryFilter"
            :placeholder="$t('customers.filterCountryQuery')"
            class="filter-input-wide"
            clearable
            @keyup.enter="runAccountSearch"
          />
          <el-input
            v-model="channelKeywordFilter"
            :placeholder="$t('customers.searchChannelKeyword')"
            class="filter-input-medium"
            clearable
            @keyup.enter="runAccountSearch"
          />
          <el-select
            v-if="!isSalesRole"
            v-model="salesIdFilter"
            :placeholder="$t('customers.filterSalesStaff')"
            clearable
            filterable
            class="filter-select-sales"
            @change="runAccountSearch"
          >
            <el-option
              v-for="s in filterSalesStaffList"
              :key="s.id"
              :label="`${s.real_name || s.username} (${s.username})`"
              :value="s.id"
            />
          </el-select>
          <!-- 业务类型已通过顶部 Tab 切换，此处隐藏 -->
          <el-select v-model="statusFilter" :placeholder="$t('customers.allStatus')" clearable style="width: 130px" @change="runAccountSearch">
            <el-option :label="$t('common.active')" value="active" />
            <el-option :label="$t('common.inactive')" value="suspended" />
            <el-option :label="$t('common.disable')" value="closed" />
          </el-select>
          <el-button type="primary" :icon="Search" @click="runAccountSearch">{{ $t('common.search') }}</el-button>
          <el-button @click="loadAccounts" :icon="Refresh">{{ $t('common.refresh') }}</el-button>
        </div>
      </div>

      <!-- 数据表格 -->
      <el-table :data="accounts" v-loading="loading" class="data-table" :table-layout="'auto'">
        <!-- 通用列：客户名称 -->
        <el-table-column prop="account_name" :label="$t('customers.customerName')" min-width="120">
          <template #default="{ row }">
            <div class="account-cell">
              <div class="avatar">{{ (row.account_name || 'A').charAt(0).toUpperCase() }}</div>
              <span class="account-name">{{ row.account_name }}</span>
            </div>
          </template>
        </el-table-column>

        <!-- 通用列：TG 账号 -->
        <el-table-column :label="$t('customers.tgAccount')" min-width="100">
          <template #default="{ row }">
            <span v-if="row.tg_username" class="tg-username">@{{ row.tg_username }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>

        <!-- 通用列：国家 -->
        <el-table-column :label="$t('customers.country')" min-width="100" align="center" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ formatAccountCountry(row.country_code) }}</span>
          </template>
        </el-table-column>

        <!-- === SMS 专属列 === -->
        <el-table-column v-if="!isVoiceTab" :label="$t('customers.protocol')" min-width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="row.protocol === 'SMPP' ? 'warning' : 'primary'" size="small" effect="plain">
              {{ row.protocol || 'HTTP' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="!isVoiceTab" :label="$t('customers.channel')" min-width="120">
          <template #default="{ row }">
            <template v-if="row.channels?.length">
              <el-tag v-for="ch in row.channels" :key="ch.id" size="small" type="info" effect="plain" style="margin-right: 4px; margin-bottom: 2px">
                {{ ch.channel_code }}
              </el-tag>
            </template>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isVoiceTab" :label="$t('customers.payment')" min-width="60" align="center">
          <template #default="{ row }">
            <el-tag :type="row.payment_type === 'prepaid' ? 'success' : 'warning'" size="small" effect="plain">
              {{ row.payment_type === 'prepaid' ? $t('customers.prepaid') : $t('customers.postpaid') }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- === 语音专属列 === -->
        <el-table-column v-if="isVoiceTab" label="坐席范围" min-width="140">
          <template #default="{ row }">
            <template v-if="row.supplier_credentials?.sip_range">
              <code class="voice-code">{{ row.supplier_credentials.sip_range }}</code>
              <span class="sip-count">({{ row.supplier_credentials.sip_count || '-' }}个)</span>
            </template>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isVoiceTab" label="SIP域名" min-width="160">
          <template #default="{ row }">
            <code v-if="row.supplier_credentials?.sip_domain" class="voice-code">{{ row.supplier_credentials.sip_domain }}</code>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isVoiceTab" label="资费套餐" min-width="160">
          <template #default="{ row }">
            <span v-if="row.supplier_credentials?.billing_package" class="pkg-name">{{ row.supplier_credentials.billing_package }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>

        <!-- 通用列：单价 -->
        <el-table-column :label="$t('customers.unitPrice')" min-width="80" align="right">
          <template #default="{ row }">
            <span class="unit-price">{{ row.currency === 'CNY' ? '¥' : '$' }}{{ (row.unit_price ?? 0.01).toFixed(4) }}</span>
          </template>
        </el-table-column>

        <!-- 通用列：员工 -->
        <el-table-column :label="$t('customers.salesPerson')" min-width="80">
          <template #default="{ row }">
            <span v-if="row.sales" class="sales-name">{{ row.sales.real_name || row.sales.username }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>

        <!-- 通用列：状态 -->
        <el-table-column prop="status" :label="$t('common.status')" min-width="60" align="center">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small" effect="light">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>

        <!-- 通用列：余额 -->
        <el-table-column :label="$t('customers.balance')" min-width="100" align="right">
          <template #default="{ row }">
            <span class="balance" :class="{ 'low-balance': row.balance < (row.low_balance_threshold || 100) }">
              {{ row.currency === 'CNY' ? '¥' : '$' }}{{ row.balance.toFixed(2) }}
            </span>
          </template>
        </el-table-column>

        <!-- SMS 专属列：剩余条数 -->
        <el-table-column v-if="!isVoiceTab" min-width="110" align="right">
          <template #header>
            <el-tooltip :content="$t('customers.remainingMessagesHint')" placement="top">
              <span class="col-hint">{{ $t('customers.remainingMessages') }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="remaining-msgs">{{ formatRemainingMessages(row) }}</span>
          </template>
        </el-table-column>

        <!-- 语音专属列：OKCC 余额 -->
        <el-table-column v-if="isVoiceTab" label="OKCC余额" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row.supplier_credentials?.okcc_balance !== undefined && row.supplier_credentials?.okcc_balance !== null">
              <span :class="['balance-text', row.supplier_credentials.okcc_balance < 0 ? 'negative' : 'positive']">
                ¥{{ Number(row.supplier_credentials.okcc_balance).toFixed(2) }}
              </span>
            </template>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>

        <!-- 通用列：创建时间 -->
        <el-table-column prop="created_at" :label="$t('customers.createdAt')" min-width="90">
          <template #default="{ row }">
            <span class="time-text">{{ formatDate(row.created_at) }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column :label="$t('common.action')" :width="isVoiceTab ? 160 : (isSalesRole ? 280 : 200)" fixed="right" align="center">
          <template #default="{ row }">
            <div class="action-btns">
              <template v-if="isVoiceTab && !isSalesRole">
                <el-button link type="primary" size="small" @click="showVoiceDetail(row)">详情</el-button>
                <el-button link type="primary" size="small" @click="openEdit(row)">{{ $t('common.edit') }}</el-button>
                <el-button link type="danger" size="small" @click="handleDelete(row)">{{ $t('common.delete') }}</el-button>
              </template>
              <template v-else-if="isSalesRole">
                <el-button v-if="isVoiceTab" link type="primary" size="small" @click="showVoiceDetail(row)">详情</el-button>
                <el-button v-else link type="warning" size="small" @click="impersonateAccount(row)" :disabled="row.status !== 'active'">{{ $t('customers.login') }}</el-button>
                <el-button
                  v-if="row.status === 'active'"
                  link type="danger" size="small"
                  @click="salesSetStatus(row, 'suspended')"
                >{{ $t('customers.salesSuspend') }}</el-button>
                <el-button
                  v-else-if="row.status === 'suspended'"
                  link type="success" size="small"
                  @click="salesSetStatus(row, 'active')"
                >{{ $t('customers.salesActivate') }}</el-button>
                <el-button v-if="!isVoiceTab" link type="primary" size="small" @click="openResetPasswordDialog(row)">{{ $t('customers.resetLoginPassword') }}</el-button>
              </template>
              <template v-else>
                <el-button link type="primary" size="small" @click="openEdit(row)">{{ $t('common.edit') }}</el-button>
                <el-button link type="success" size="small" @click="openAdjust(row)">{{ $t('customers.recharge') }}</el-button>
                <el-button link type="warning" size="small" @click="impersonateAccount(row)" :disabled="row.status !== 'active'">{{ $t('customers.login') }}</el-button>
                <el-dropdown trigger="click">
                  <el-button link type="primary" size="small">{{ $t('common.more') }}</el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item @click="openSummary(row)">{{ $t('customers.accountSummary') }}</el-dropdown-item>
                      <el-dropdown-item @click="bindSales(row)">{{ $t('customers.assignedSales') }}</el-dropdown-item>
                      <el-dropdown-item @click="openLogs(row)">{{ $t('customers.balance') }}</el-dropdown-item>
                      <el-dropdown-item @click="handleResetKey(row)">{{ $t('dashboard.apiKey') }}</el-dropdown-item>
                      <el-dropdown-item divided @click="handleDelete(row)" style="color: #f56c6c">{{ $t('common.delete') }}</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next, sizes"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="(p:number)=>{ page=p; loadAccounts() }"
          @size-change="(s:number)=>{ pageSize=s; page=1; loadAccounts() }"
        />
      </div>
    </div>

    <!-- 创建/编辑 -->
    <el-dialog v-model="formVisible" :title="isEdit ? $t('customers.editCustomer') : $t('customers.createAccount')" width="520px" :close-on-click-modal="false">
      <el-form :model="form" label-width="100px" class="account-form" label-position="left">
        
        <!-- 基本信息 -->
        <el-divider content-position="left">{{ $t('customers.basicInfo') }}</el-divider>
        <el-form-item :label="$t('customers.accountName')" required>
          <el-input v-model="form.account_name" :placeholder="$t('customers.accountNamePlaceholder')" />
        </el-form-item>
        <el-form-item v-if="!isEdit" :label="$t('customers.loginPassword')" required>
          <el-input v-model="form.password" type="password" show-password :placeholder="$t('customers.passwordPlaceholder')" />
        </el-form-item>
        <el-form-item v-if="isEdit" :label="$t('common.status')">
          <el-select v-model="form.status" style="width: 100%">
            <el-option :label="$t('customers.statusActive')" value="active" />
            <el-option :label="$t('customers.statusSuspended')" value="suspended" />
            <el-option :label="$t('customers.statusClosed')" value="closed" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('customers.bizTypeLabel')">
          <el-select v-model="form.business_type" style="width: 100%">
            <el-option label="💬 短信 SMS" value="sms" />
            <el-option label="📞 语音 Voice" value="voice" />
            <el-option label="📊 数据 Data" value="data" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('customers.country')">
          <el-select v-model="form.country_code" :placeholder="$t('customers.selectCountry')" filterable clearable style="width: 100%">
            <el-option v-for="c in countryList" :key="c.code" :label="`${c.name} (${c.code})`" :value="c.code" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('customers.tgAccount')">
          <el-input v-model="form.tg_username" :placeholder="$t('customers.tgPlaceholder')" />
        </el-form-item>
        
        <!-- SMS/通用：接入与计费 -->
        <template v-if="form.business_type === 'sms' || !form.business_type">
          <el-divider content-position="left">{{ $t('customers.accessAndBilling') }}</el-divider>
          <el-form-item :label="$t('customers.accessMethod')" required>
            <el-select v-model="form.protocol" style="width: 160px">
              <el-option label="HTTP API" value="HTTP" />
              <el-option :label="$t('customers.smppDirect')" value="SMPP" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="form.protocol === 'SMPP'" :label="$t('customers.smppPassword')">
            <el-input v-model="form.smpp_password" :placeholder="$t('customers.leaveBlankAuto')" />
          </el-form-item>
          <el-form-item :label="$t('customers.paymentMode')">
            <el-select v-model="form.payment_type" style="width: 120px">
              <el-option :label="$t('customers.prepaid')" value="prepaid" />
              <el-option :label="$t('customers.postpaid')" value="postpaid" />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('customers.smsUnitPrice')">
            <el-input-number v-model="form.unit_price" :min="0" :max="10" :precision="4" :step="0.01" style="width: 150px" />
            <span style="margin-left: 8px; color: #909399">{{ form.currency }}/{{ $t('customers.perMessage') }}</span>
          </el-form-item>
          
          <!-- 风控限制 -->
          <el-divider content-position="left">{{ $t('customers.riskControl') }}</el-divider>
          <el-form-item :label="$t('customers.sendRateLimit')">
            <el-input-number v-model="form.rate_limit" :min="1" :max="1000" style="width: 150px" />
            <span style="margin-left: 8px; color: #909399">{{ $t('customers.messagesPerSecond') }}</span>
          </el-form-item>
          <el-form-item :label="$t('customers.balanceAlert')">
            <el-input-number v-model="form.low_balance_threshold" :min="0" :precision="2" style="width: 150px" />
            <span style="margin-left: 8px; color: #909399">{{ form.currency }}</span>
          </el-form-item>
          <el-form-item :label="$t('customers.ipWhitelist')">
            <el-input v-model="whitelistText" type="textarea" rows="2" :placeholder="$t('customers.ipWhitelistPlaceholder')" />
          </el-form-item>
        </template>

        <!-- 语音/数据：计费信息（简化） -->
        <template v-else>
          <el-divider content-position="left">计费信息</el-divider>
          <el-form-item label="单价 (¥/分钟)">
            <el-input-number v-model="form.unit_price" :min="0" :max="100" :precision="4" :step="0.01" style="width: 150px" />
            <span style="margin-left: 8px; color: #909399">CNY/分钟</span>
          </el-form-item>
        </template>

        <!-- 绑定配置 -->
        <el-divider content-position="left">{{ $t('customers.bindConfig') }}</el-divider>
        <el-form-item :label="$t('customers.assignStaff')">
          <el-select v-model="form.sales_id" :placeholder="$t('customers.selectStaff')" clearable filterable style="width: 100%" :loading="salesLoading">
            <el-option v-for="s in salesList" :key="s.id" :label="`${s.real_name || s.username}`" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.business_type === 'sms' || !form.business_type" :label="$t('customers.assignChannel')">
          <el-select v-model="form.channel_ids" :placeholder="$t('customers.selectChannel')" multiple clearable filterable style="width: 100%" :loading="channelLoading">
            <el-option v-for="ch in channelList" :key="ch.id" :label="`${ch.channel_name} (${ch.channel_code})`" :value="ch.id">
              <span>{{ ch.channel_name }}</span>
              <span style="color: #8492a6; font-size: 12px; margin-left: 8px">{{ ch.protocol }}</span>
            </el-option>
          </el-select>
          <div class="hint">{{ $t('customers.channelPriorityHint') }}</div>
        </el-form-item>

        <!-- HTTP API 凭证 -->
        <el-alert
          v-if="createdCreds.api_key && createdCreds.protocol === 'HTTP'"
          type="success"
          :closable="false"
          show-icon
          :title="$t('customers.httpApiCredentialsGenerated')"
          class="creds-alert"
        >
          <div class="creds">
            <div class="row">
              <span class="label">API Key</span>
              <span class="mono">{{ createdCreds.api_key }}</span>
              <el-button link size="small" @click="copyText(createdCreds.api_key)">{{ $t('common.copy') }}</el-button>
            </div>
            <div class="row">
              <span class="label">API Secret</span>
              <span class="mono">{{ createdCreds.api_secret }}</span>
              <el-button link size="small" @click="copyText(createdCreds.api_secret)">{{ $t('common.copy') }}</el-button>
            </div>
          </div>
        </el-alert>
        
        <!-- SMPP 凭证 -->
        <el-alert
          v-if="createdCreds.smpp_system_id && createdCreds.protocol === 'SMPP'"
          type="success"
          :closable="false"
          show-icon
          :title="$t('customers.smppCredentialsGenerated')"
          class="creds-alert"
        >
          <div class="creds">
            <div class="row">
              <span class="label">System ID</span>
              <span class="mono">{{ createdCreds.smpp_system_id }}</span>
              <el-button link size="small" @click="copyText(createdCreds.smpp_system_id)">{{ $t('common.copy') }}</el-button>
            </div>
            <div class="row">
              <span class="label">Password</span>
              <span class="mono">{{ createdCreds.smpp_password }}</span>
              <el-button link size="small" @click="copyText(createdCreds.smpp_password)">{{ $t('common.copy') }}</el-button>
            </div>
          </div>
        </el-alert>
      </el-form>

      <template #footer>
        <el-button @click="formVisible=false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">{{ $t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 余额调整 -->
    <el-dialog v-model="adjustVisible" :title="$t('customers.balanceAdjustment')" width="520px" :close-on-click-modal="false">
      <el-form :model="adjustForm" label-width="110px">
        <el-form-item :label="$t('customers.account')">
          <el-tag type="info" effect="plain">{{ current?.account_name }} (#{{ current?.id }})</el-tag>
        </el-form-item>
        <el-form-item :label="$t('customers.amount')" required>
          <el-input-number v-model="adjustForm.amount" :precision="4" style="width: 100%" />
          <div class="hint">{{ $t('customers.amountHint') }}</div>
        </el-form-item>
        <el-form-item :label="$t('customers.type')">
          <el-select v-model="adjustForm.change_type" style="width: 100%" :placeholder="$t('customers.autoDetect')">
            <el-option :label="$t('customers.autoDetect')" value="" />
            <el-option :label="$t('customers.depositType')" value="deposit" />
            <el-option :label="$t('customers.withdrawType')" value="withdraw" />
            <el-option :label="$t('customers.refundRechargeType')" value="refund_recharge" />
            <el-option :label="$t('customers.adjustmentType')" value="adjustment" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('customers.description')">
          <el-input v-model="adjustForm.description" type="textarea" rows="3" :placeholder="$t('customers.optional')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adjustVisible=false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="adjusting" @click="submitAdjust">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 余额日志 -->
    <el-dialog v-model="logsVisible" :title="$t('customers.balanceLogs')" width="860px" :close-on-click-modal="false">
      <el-table :data="logs" stripe v-loading="logsLoading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="change_type" :label="$t('customers.type')" width="120" />
        <el-table-column prop="amount" :label="$t('customers.amount')" width="140">
          <template #default="{ row }">
            <span :class="row.amount >= 0 ? 'pos' : 'neg'">{{ row.amount }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="balance_before" :label="$t('customers.balanceBefore')" width="140" />
        <el-table-column prop="balance_after" :label="$t('customers.balanceAfter')" width="140" />
        <el-table-column prop="description" :label="$t('customers.description')" min-width="220" />
        <el-table-column prop="created_at" :label="$t('customers.time')" width="180">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="logsVisible=false">{{ $t('common.close') }}</el-button>
      </template>
    </el-dialog>

    <!-- 账号摘要 -->
    <el-dialog v-model="summaryVisible" :title="$t('customers.accountSummary')" width="680px" :close-on-click-modal="false">
      <div v-loading="summaryLoading">
        <template v-if="summaryData">
          <div class="summary-header">
            <el-tag effect="dark" :type="summaryData.protocol === 'SMPP' ? 'warning' : 'primary'" size="large">
              {{ summaryData.protocol }}
            </el-tag>
            <span class="summary-account-name">{{ summaryData.account_name }} (#{{ summaryData.id }})</span>
          </div>

          <!-- HTTP 凭证未生成警告 -->
          <el-alert
            v-if="summaryData.protocol === 'HTTP' && !summaryData.api_key"
            type="warning" :closable="false" show-icon style="margin-bottom: 16px"
          >
            <template #title>{{ $t('customers.credentialsNotGenerated') }}</template>
            <template #default>
              {{ $t('customers.credentialsNotGeneratedHint') }}
              <el-button type="primary" size="small" style="margin-left: 12px" @click="resetAndRefreshSummary">
                {{ $t('customers.generateNow') }}
              </el-button>
            </template>
          </el-alert>

          <!-- SMPP 凭证未生成警告 -->
          <el-alert
            v-if="summaryData.protocol === 'SMPP' && !summaryData.smpp_system_id"
            type="warning" :closable="false" show-icon style="margin-bottom: 16px"
          >
            <template #title>{{ $t('customers.credentialsNotGenerated') }}</template>
            <template #default>{{ $t('customers.smppCredentialsNotGeneratedHint') }}</template>
          </el-alert>

          <!-- HTTP 对接信息 -->
          <template v-if="summaryData.protocol === 'HTTP'">
            <!-- 认证方式一：API Key -->
            <div class="summary-section-title">{{ $t('customers.authMethodApiKey') }}</div>
            <el-descriptions :column="1" border class="summary-desc">
              <el-descriptions-item label="API Key">
                <template v-if="summaryData.api_key">
                  <code class="mono-val">{{ summaryData.api_key }}</code>
                  <el-button link size="small" @click="copyText(summaryData.api_key)">{{ $t('common.copy') }}</el-button>
                </template>
                <span v-else class="text-placeholder">{{ $t('customers.notGenerated') }}</span>
              </el-descriptions-item>
              <el-descriptions-item :label="$t('customers.requestUrl')">
                <code class="mono-val">{{ summaryData.api_base_url }}/sms/send?api_key={{ summaryData.api_key || 'YOUR_API_KEY' }}</code>
              </el-descriptions-item>
            </el-descriptions>

            <!-- 认证方式二：Basic Auth -->
            <div class="summary-section-title">{{ $t('customers.authMethodBasicAuth') }}</div>
            <el-descriptions :column="1" border class="summary-desc">
              <el-descriptions-item :label="$t('customers.basicAuthUsername')">
                <code class="mono-val">{{ summaryData.account_name || summaryData.email || '-' }}</code>
                <el-button link size="small" @click="copyText(summaryData.account_name || summaryData.email || '')">{{ $t('common.copy') }}</el-button>
              </el-descriptions-item>
              <el-descriptions-item :label="$t('customers.interfacePassword')">
                <template v-if="summaryData.api_secret">
                  <code class="mono-val">{{ summaryData.api_secret }}</code>
                  <el-button link size="small" @click="copyText(summaryData.api_secret)">{{ $t('common.copy') }}</el-button>
                </template>
                <span v-else class="text-placeholder">{{ $t('customers.notGenerated') }}</span>
              </el-descriptions-item>
              <el-descriptions-item :label="$t('customers.requestUrl')">
                <code class="mono-val">{{ summaryData.api_base_url }}/sms/send</code>
              </el-descriptions-item>
            </el-descriptions>

            <!-- 接口地址 -->
            <div class="summary-section-title">{{ $t('customers.apiEndpoints') }}</div>
            <el-descriptions :column="1" border class="summary-desc">
              <el-descriptions-item label="API Base">
                <code class="mono-val">{{ summaryData.api_base_url }}</code>
                <el-button link size="small" @click="copyText(summaryData.api_base_url)">{{ $t('common.copy') }}</el-button>
              </el-descriptions-item>
              <el-descriptions-item :label="$t('customers.httpSendUrl')">
                <code class="mono-val">POST {{ summaryData.api_base_url }}/sms/send</code>
              </el-descriptions-item>
              <el-descriptions-item label="Batch URL">
                <code class="mono-val">POST {{ summaryData.api_base_url }}/sms/batch</code>
              </el-descriptions-item>
              <el-descriptions-item :label="$t('customers.httpStatusUrl')">
                <code class="mono-val">GET {{ summaryData.api_base_url }}/sms/status/{'{message_id}'}</code>
              </el-descriptions-item>
              <el-descriptions-item :label="$t('customers.httpBalanceUrl')">
                <code class="mono-val">GET {{ summaryData.api_base_url }}/account/balance</code>
              </el-descriptions-item>
            </el-descriptions>

            <!-- 限制 -->
            <div class="summary-section-title">{{ $t('customers.restrictions') }}</div>
            <el-descriptions :column="1" border class="summary-desc">
              <el-descriptions-item :label="$t('customers.maxThroughput')">
                {{ summaryData.rate_limit || 100 }} {{ $t('customers.perSecond') }}
              </el-descriptions-item>
              <el-descriptions-item :label="$t('customers.ipWhitelist')">
                {{ (summaryData.ip_whitelist && summaryData.ip_whitelist.length) ? summaryData.ip_whitelist.join(', ') : $t('customers.noRestriction') }}
              </el-descriptions-item>
            </el-descriptions>
          </template>

          <!-- SMPP 对接信息 -->
          <template v-else-if="summaryData.protocol === 'SMPP'">
            <el-descriptions :column="1" border class="summary-desc">
              <el-descriptions-item :label="$t('customers.accessMethod')">SMPP</el-descriptions-item>
              <el-descriptions-item :label="$t('customers.serverAddress')">
                <code class="mono-val">{{ summaryData.smpp_server_host }}</code>
                <el-button link size="small" @click="copyText(summaryData.smpp_server_host)">{{ $t('common.copy') }}</el-button>
              </el-descriptions-item>
              <el-descriptions-item :label="$t('customers.serverPort')">
                <code class="mono-val">{{ summaryData.smpp_server_port }}</code>
              </el-descriptions-item>
              <el-descriptions-item label="System ID">
                <template v-if="summaryData.smpp_system_id">
                  <code class="mono-val">{{ summaryData.smpp_system_id }}</code>
                  <el-button link size="small" @click="copyText(summaryData.smpp_system_id)">{{ $t('common.copy') }}</el-button>
                </template>
                <span v-else class="text-placeholder">{{ $t('customers.notGenerated') }}</span>
              </el-descriptions-item>
              <el-descriptions-item :label="$t('customers.interfacePassword')">
                <template v-if="summaryData.smpp_password">
                  <code class="mono-val">{{ summaryData.smpp_password }}</code>
                  <el-button link size="small" @click="copyText(summaryData.smpp_password)">{{ $t('common.copy') }}</el-button>
                </template>
                <span v-else class="text-placeholder">{{ $t('customers.notGenerated') }}</span>
              </el-descriptions-item>
              <el-descriptions-item :label="$t('customers.maxThroughput')">
                {{ summaryData.rate_limit || 100 }} {{ $t('customers.perSecond') }}
              </el-descriptions-item>
              <el-descriptions-item :label="$t('customers.maxConnections')">1</el-descriptions-item>
              <el-descriptions-item :label="$t('customers.ipWhitelist')">
                {{ (summaryData.ip_whitelist && summaryData.ip_whitelist.length) ? summaryData.ip_whitelist.join(', ') : $t('customers.noRestriction') }}
              </el-descriptions-item>
            </el-descriptions>
          </template>
        </template>
        <el-empty v-else-if="!summaryLoading" :description="$t('customers.noCredentials')" />
      </div>
      <template #footer>
        <el-button v-if="summaryData && ((summaryData.protocol === 'HTTP' && summaryData.api_key) || (summaryData.protocol === 'SMPP' && summaryData.smpp_system_id))" @click="copySummaryAll" type="primary">{{ $t('customers.copyAll') }}</el-button>
        <el-button @click="summaryVisible=false">{{ $t('common.close') }}</el-button>
      </template>
    </el-dialog>

    <!-- 销售绑定对话框 -->
    <el-dialog v-model="salesBindVisible" :title="$t('customers.bindSales')" width="500px">
      <div v-if="currentAccountSales" class="current-sales">
        <el-alert type="info" :closable="false" style="margin-bottom: 16px">
          <template #title>
            <div>{{ $t('customers.currentSales') }}: <strong>{{ currentAccountSales.real_name || currentAccountSales.username }}</strong></div>
            <div style="font-size: 12px; margin-top: 4px; color: #909399">
              {{ currentAccountSales.email || '' }}
            </div>
          </template>
        </el-alert>
        <el-button type="danger" @click="unbindSales" :loading="unbinding">{{ $t('customers.unbindSales') }}</el-button>
      </div>
      <el-form v-else label-width="100px">
        <el-form-item :label="$t('customers.selectSalesLabel')" required>
          <el-select
            v-model="selectedSalesId"
            :placeholder="$t('customers.selectSalesPlaceholder')"
            filterable
            style="width: 100%"
            :loading="salesLoading"
          >
            <el-option
              v-for="sales in salesList"
              :key="sales.id"
              :label="`${sales.real_name || sales.username} (${sales.username})`"
              :value="sales.id"
            >
              <div>
                <div>{{ sales.real_name || sales.username }}</div>
                <div style="font-size: 12px; color: #909399">{{ sales.email || sales.username }}</div>
              </div>
            </el-option>
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="salesBindVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button v-if="!currentAccountSales" type="primary" @click="submitBindSales" :loading="binding">
          {{ $t('customers.confirmBind') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 销售重置客户登录密码 -->
    <el-dialog v-model="resetPwdVisible" :title="$t('customers.resetLoginPassword')" width="420px" :close-on-click-modal="false" append-to-body>
      <el-form label-width="100px">
        <el-form-item :label="$t('customers.account')">
          <span>{{ resetPwdRow?.account_name }}</span>
        </el-form-item>
        <el-form-item :label="$t('customers.newPassword')" required>
          <el-input v-model="resetPwdForm.password" type="password" show-password :placeholder="$t('customers.passwordMinLength')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetPwdVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="resetPwdLoading" @click="submitResetPassword">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 语音客户详情弹窗 -->
    <el-dialog v-model="voiceDetailVisible" title="语音客户详情" width="600px" :close-on-click-modal="true">
      <template v-if="voiceDetailRow">
        <div class="voice-detail-card">
          <div class="voice-section">
            <div class="voice-section-title"><span class="voice-icon">🏢</span> 企业客户登录</div>
            <div class="voice-info-grid">
              <div class="voice-info-row">
                <span class="voice-label">客户名:</span>
                <code class="voice-value">{{ voiceDetailRow.supplier_credentials?.client_name || voiceDetailRow.account_name }}</code>
                <el-button link size="small" @click="copyText(voiceDetailRow.supplier_credentials?.client_name || voiceDetailRow.account_name)">复制</el-button>
              </div>
              <div class="voice-info-row">
                <span class="voice-label">用户名:</span>
                <code class="voice-value">{{ voiceDetailRow.supplier_credentials?.username || 'admin' }}</code>
              </div>
              <div class="voice-info-row">
                <span class="voice-label">密码:</span>
                <code class="voice-value">{{ voiceDetailRow.supplier_credentials?.password || '-' }}</code>
                <el-button v-if="voiceDetailRow.supplier_credentials?.password" link size="small" @click="copyText(voiceDetailRow.supplier_credentials.password)">复制</el-button>
              </div>
              <div class="voice-info-row">
                <span class="voice-label">登录地址:</span>
                <a v-if="voiceDetailRow.supplier_url" :href="voiceDetailRow.supplier_url" target="_blank" class="voice-link">{{ voiceDetailRow.supplier_url }}</a>
                <span v-else class="text-muted">-</span>
              </div>
            </div>
          </div>

          <div class="voice-section">
            <div class="voice-section-title"><span class="voice-icon">📞</span> 坐席注册</div>
            <div class="voice-info-grid">
              <div class="voice-info-row">
                <span class="voice-label">坐席号:</span>
                <code class="voice-value">{{ voiceDetailRow.supplier_credentials?.sip_range || voiceDetailRow.supplier_credentials?.agent_range || '-' }}</code>
                <el-button v-if="voiceDetailRow.supplier_credentials?.sip_range" link size="small" @click="copyText(voiceDetailRow.supplier_credentials.sip_range)">复制</el-button>
              </div>
              <div class="voice-info-row">
                <span class="voice-label">口令:</span>
                <code class="voice-value">{{ voiceDetailRow.supplier_credentials?.sip_password || '-' }}</code>
                <el-button v-if="voiceDetailRow.supplier_credentials?.sip_password" link size="small" @click="copyText(voiceDetailRow.supplier_credentials.sip_password)">复制</el-button>
              </div>
              <div class="voice-info-row">
                <span class="voice-label">域名:</span>
                <code class="voice-value">{{ voiceDetailRow.supplier_credentials?.sip_domain || voiceDetailRow.supplier_credentials?.domain || '-' }}</code>
                <el-button v-if="voiceDetailRow.supplier_credentials?.sip_domain" link size="small" @click="copyText(voiceDetailRow.supplier_credentials.sip_domain)">复制</el-button>
              </div>
              <div class="voice-info-row">
                <span class="voice-label">坐席数:</span>
                <span>{{ voiceDetailRow.supplier_credentials?.sip_count || '-' }} 个</span>
              </div>
            </div>
          </div>

          <div class="voice-section">
            <div class="voice-section-title"><span class="voice-icon">👤</span> 坐席登录</div>
            <div class="voice-info-grid">
              <div class="voice-info-row">
                <span class="voice-label">客户名:</span>
                <code class="voice-value">{{ voiceDetailRow.supplier_credentials?.client_name || voiceDetailRow.account_name }}</code>
              </div>
              <div class="voice-info-row">
                <span class="voice-label">用户名:</span>
                <code class="voice-value">{{ voiceDetailRow.supplier_credentials?.sip_range || '-' }}</code>
              </div>
              <div class="voice-info-row">
                <span class="voice-label">密码:</span>
                <code class="voice-value">{{ voiceDetailRow.supplier_credentials?.sip_range || '-' }}</code>
              </div>
            </div>
          </div>

          <div class="voice-section">
            <div class="voice-section-title"><span class="voice-icon">💰</span> 计费信息</div>
            <div class="voice-info-grid">
              <div class="voice-info-row">
                <span class="voice-label">资费套餐:</span>
                <span>{{ voiceDetailRow.supplier_credentials?.billing_package || '-' }}</span>
              </div>
              <div class="voice-info-row">
                <span class="voice-label">单价:</span>
                <span class="unit-price">¥{{ (voiceDetailRow.unit_price ?? 0).toFixed(4) }}/分钟</span>
              </div>
              <div class="voice-info-row">
                <span class="voice-label">平台余额:</span>
                <span class="balance">¥{{ (voiceDetailRow.balance ?? 0).toFixed(2) }}</span>
              </div>
              <div class="voice-info-row" v-if="voiceDetailRow.supplier_credentials?.okcc_balance !== undefined">
                <span class="voice-label">OKCC余额:</span>
                <span :class="['balance-text', (voiceDetailRow.supplier_credentials?.okcc_balance ?? 0) < 0 ? 'negative' : 'positive']">
                  ¥{{ Number(voiceDetailRow.supplier_credentials?.okcc_balance ?? 0).toFixed(2) }}
                </span>
              </div>
              <div class="voice-info-row">
                <span class="voice-label">国家:</span>
                <span>{{ formatAccountCountry(voiceDetailRow.country_code) }}</span>
              </div>
              <div class="voice-info-row">
                <span class="voice-label">员工:</span>
                <span>{{ voiceDetailRow.sales?.real_name || voiceDetailRow.sales?.username || '-' }}</span>
              </div>
            </div>
          </div>

          <div class="voice-section" v-if="voiceDetailRow.supplier_credentials?.raw_reply">
            <div class="voice-section-title"><span class="voice-icon">📋</span> 技术原始回复</div>
            <pre class="voice-raw-reply">{{ voiceDetailRow.supplier_credentials.raw_reply }}</pre>
          </div>
        </div>
      </template>
      <template #footer>
        <el-button @click="voiceDetailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Refresh } from '@element-plus/icons-vue'
import {
  getAccountsAdmin,
  getAccountAdminDetail,
  createAccountAdmin,
  updateAccountAdmin,
  adjustAccountBalance,
  resetAccountApiKey,
  resetAccountPassword,
  getAccountBalanceLogs,
  syncOkccBalances,
  type AdminAccount,
} from '@/api/admin'
import request from '@/api/index'
import { findCountryByIso, findCountryByDial, searchCountries } from '@/constants/countries'

const { t, locale } = useI18n()

/** 销售角色：仅能登录、停用/启用、重置密码 */
const adminRole = ref('')
const isSalesRole = computed(() => adminRole.value === 'sales')

// Props
const props = defineProps<{
  defaultBusinessType?: string
}>()

const route = useRoute()

// 页面标题
const pageTitle = computed(() => {
  if (props.defaultBusinessType === 'sms') return t('menu.smsAccounts')
  if (props.defaultBusinessType === 'voice') return t('menu.voiceAccounts')
  if (props.defaultBusinessType === 'data') return t('menu.dataAccounts')
  return t('customers.title')
})

const pageDesc = computed(() => {
  return t('customers.pageDesc')
})

// 计算总余额
const totalBalance = computed(() => {
  return accounts.value.reduce((sum, a) => sum + (parseFloat(String(a.balance)) || 0), 0)
})

const loading = ref(false)
const accounts = ref<AdminAccount[]>([])
const total = ref(0)
let page = 1
let pageSize = 20

const keyword = ref('')
const tgUsernameFilter = ref('')
const countryQueryFilter = ref('')
const channelKeywordFilter = ref('')
const statusFilter = ref('')
const businessTypeFilter = ref(props.defaultBusinessType || '')
const isVoiceTab = computed(() => businessTypeFilter.value === 'voice')
const salesIdFilter = ref<number | undefined>(undefined)
const filterSalesStaffList = ref<any[]>([])

/** 国家名称/国码/区号前缀 → 逗号分隔 ISO，供列表接口 country_codes */
function resolveCountryCodesForAccounts(raw: string): string | undefined {
  const q = raw.trim()
  if (!q) return undefined
  const hits = searchCountries(q)
  if (hits.length > 0) {
    const seen = new Set<string>()
    const codes: string[] = []
    for (const c of hits) {
      if (!seen.has(c.iso)) {
        seen.add(c.iso)
        codes.push(c.iso)
      }
    }
    return codes.join(',')
  }
  if (/^[A-Za-z]{2}$/.test(q)) return q.toUpperCase()
  return undefined
}

const switchBizType = (type: string) => {
  businessTypeFilter.value = type
  page = 1
  loadAccounts()
}

const runAccountSearch = () => {
  page = 1
  loadAccounts()
}

const loadAccounts = async () => {
  loading.value = true
  try {
    const countryCodes = resolveCountryCodesForAccounts(countryQueryFilter.value || '')
    const res = await getAccountsAdmin({
      keyword: keyword.value || undefined,
      status: statusFilter.value || undefined,
      business_type: businessTypeFilter.value || undefined,
      sales_id: !isSalesRole.value && salesIdFilter.value != null ? salesIdFilter.value : undefined,
      tg_username: tgUsernameFilter.value?.trim() || undefined,
      country_codes: countryCodes,
      channel_keyword: channelKeywordFilter.value?.trim() || undefined,
      limit: pageSize,
      offset: (page - 1) * pageSize,
    })
    accounts.value = res.accounts || []
    total.value = res.total || 0
  } catch (e: any) {
    ElMessage.error(e?.message || t('customers.loadFailed'))
  } finally {
    loading.value = false
  }
}

const maskApiKey = (key?: string | null) => {
  if (!key) return '-'
  if (key.length <= 10) return key
  return `${key.slice(0, 6)}...${key.slice(-4)}`
}

const statusType = (s: string) => {
  const map: Record<string, any> = { active: 'success', suspended: 'warning', closed: 'info' }
  return map[s] || 'info'
}
const statusText = (s: string) => {
  const map: Record<string, string> = { 
    active: t('customers.statusActive'), 
    suspended: t('customers.statusSuspended'), 
    closed: t('customers.statusClosed') 
  }
  return map[s] || s
}

const businessTypeText = (type: string) => {
  const map: Record<string, string> = { 
    sms: t('customers.smsBusiness'), 
    voice: t('customers.voiceBusiness'),
    data: t('customers.dataBusiness') 
  }
  return map[type] || type || t('customers.smsBusiness')
}
const businessTypeTag = (bt: string) => {
  const map: Record<string, any> = { sms: 'primary', voice: 'success', data: 'warning' }
  return map[bt] || 'primary'
}

const formatDate = (dateStr: string | null) => {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear().toString().slice(-2)}`
}

const getActivityLevel = (row: any) => {
  // 使用后端计算的活跃度分数
  const score = row.activity_score ?? 100
  
  if (score === 0) {
    return { type: 'danger', text: '0', class: 'activity-zero' }
  } else if (score < 50) {
    return { type: 'warning', text: String(score), class: 'activity-low' }
  } else if (score > 200) {
    return { type: '', text: String(score), class: 'activity-gold' }
  } else if (score > 100) {
    return { type: 'success', text: String(score), class: 'activity-high' }
  } else {
    return { type: 'info', text: String(score), class: 'activity-normal' }
  }
}

const copyText = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(t('customers.copied'))
  } catch {
    ElMessage.warning(t('customers.copyFailed'))
  }
}

// Create / Edit
const formVisible = ref(false)
const submitting = ref(false)
const isEdit = ref(false)
const current = ref<AdminAccount | null>(null)
const whitelistText = ref('')

const createdCreds = reactive<{ api_key: string; api_secret: string }>({ api_key: '', api_secret: '' })

// 国家列表（按语言显示名称）
const COUNTRY_CODES = ['PH', 'ID', 'MY', 'TH', 'VN', 'SG', 'IN', 'PK', 'BD', 'CN', 'HK', 'TW', 'JP', 'KR', 'US', 'GB', 'AU', 'DE', 'FR', 'BR', 'MX', 'NG', 'ZA', 'AE', 'SA']
const countryList = computed(() => {
  const isZh = locale.value.startsWith('zh')
  return COUNTRY_CODES.map(code => {
    const c = findCountryByIso(code)
    const name = c ? (isZh ? c.name : c.en) : code
    return { code, name }
  })
})

/** 列表中国家列：支持 ISO 代码和电话区号，按当前语言显示国家名称 */
function formatAccountCountry(code: string | null | undefined): string {
  if (!code) return '-'
  const raw = String(code).trim()
  const iso = raw.toUpperCase()
  let c = findCountryByIso(iso)
  if (!c) {
    const dial = raw.replace(/^0+/, '')
    c = findCountryByDial(dial)
  }
  if (!c) return raw
  const isZh = locale.value.startsWith('zh')
  return isZh ? c.name : c.en
}

/** 剩余条数：余额 ÷ 单价（向下取整）；单价无效时显示 — */
function formatRemainingMessages(row: { balance?: number; unit_price?: number }) {
  const price = Number(row.unit_price ?? 0)
  const bal = Number(row.balance ?? 0)
  if (!Number.isFinite(price) || !Number.isFinite(bal) || price <= 0) return '—'
  const n = Math.floor(bal / price)
  return n.toLocaleString()
}

const form = reactive<any>({
  id: 0,
  account_name: '',
  tg_username: '',
  password: '',
  country_code: '',
  business_type: 'sms',
  // 接入协议
  protocol: 'HTTP',
  smpp_password: '',
  // 计费配置
  payment_type: 'prepaid',
  unit_price: 0.05,
  status: 'active',
  currency: 'USD',
  // 风控配置
  rate_limit: 30,
  low_balance_threshold: 100,
})

const openCreate = () => {
  isEdit.value = false
  current.value = null
  // 重置凭证显示
  Object.assign(createdCreds, { protocol: 'HTTP', api_key: '', api_secret: '', smpp_system_id: '', smpp_password: '' })
  whitelistText.value = ''
  Object.assign(form, {
    id: 0,
    account_name: '',
    tg_username: '',
    password: '',
    country_code: '',
    business_type: props.defaultBusinessType || 'sms',
    // 接入协议
    protocol: 'HTTP',
    smpp_password: '',
    // 计费配置
    payment_type: 'prepaid',
    unit_price: 0.05,
    status: 'active',
    currency: 'USD',
    // 风控配置
    rate_limit: 30,
    low_balance_threshold: 100,
    // 绑定配置
    sales_id: null,
    channel_ids: [],
  })
  // 加载员工和通道列表
  loadSalesList()
  loadChannelList()
  formVisible.value = true
}

const openEdit = async (row: AdminAccount) => {
  isEdit.value = true
  current.value = row
  createdCreds.api_key = ''
  createdCreds.api_secret = ''
  whitelistText.value = (row.ip_whitelist || []).join('\n')
  
  // 加载员工和通道列表
  loadSalesList()
  loadChannelList()
  
  // 获取账户详情（包含通道绑定信息）
  let accountDetail: any = row
  try {
    const res = await request.get(`/admin/accounts/${row.id}`)
    if (res.account) {
      accountDetail = res.account
    }
  } catch (e) {
    console.error('Failed to get account details', e)
  }
  
  Object.assign(form, {
    id: row.id,
    account_name: row.account_name,
    tg_username: (row as any).tg_username || '',
    password: '',
    country_code: (row as any).country_code || accountDetail.country_code || '',
    business_type: (row as any).business_type || 'sms',
    payment_type: (row as any).payment_type || accountDetail.payment_type || 'prepaid',
    unit_price: (row as any).unit_price ?? accountDetail.unit_price ?? 0.01,
    status: row.status,
    currency: row.currency,
    rate_limit: row.rate_limit ?? 1000,
    low_balance_threshold: row.low_balance_threshold ?? 100,
    sales_id: (row as any).sales_id || accountDetail.sales_id || null,
    channel_ids: accountDetail.channel_ids || [],
  })
  formVisible.value = true
}

const normalizeWhitelist = () => {
  const lines = whitelistText.value
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)
  return lines.length ? lines : []
}

const submitForm = async () => {
  if (!form.account_name) {
    ElMessage.warning(t('customers.pleaseEnterAccountName'))
    return
  }
  if (!isEdit.value && (!form.password || String(form.password).length < 6)) {
    ElMessage.warning(t('customers.passwordMinLength'))
    return
  }
  submitting.value = true
  try {
    const payload: any = {
      account_name: form.account_name,
      tg_username: form.tg_username || undefined,
      country_code: form.country_code || undefined,
      business_type: form.business_type,
      // 接入协议
      protocol: form.protocol,
      smpp_password: form.protocol === 'SMPP' ? (form.smpp_password || undefined) : undefined,
      // 计费配置
      payment_type: form.payment_type,
      unit_price: form.unit_price,
      status: form.status,
      currency: form.currency,
      // 风控配置
      rate_limit: form.rate_limit,
      low_balance_threshold: form.low_balance_threshold,
      ip_whitelist: normalizeWhitelist(),
      // 绑定配置
      sales_id: form.sales_id || undefined,
      channel_ids: form.channel_ids?.length ? form.channel_ids : undefined,
    }
    if (!isEdit.value) {
      payload.password = form.password
      const res = await createAccountAdmin(payload)
      // 保存返回的凭证
      createdCreds.protocol = res.protocol || 'HTTP'
      if (res.protocol === 'SMPP') {
        createdCreds.smpp_system_id = res.smpp_system_id || ''
        createdCreds.smpp_password = res.smpp_password || ''
        createdCreds.api_key = ''
        createdCreds.api_secret = ''
      } else {
        createdCreds.api_key = res.api_key || ''
        createdCreds.api_secret = res.api_secret || ''
        createdCreds.smpp_system_id = ''
        createdCreds.smpp_password = ''
      }
      ElMessage.success(t('customers.createSuccess'))
      await loadAccounts()
    } else {
      await updateAccountAdmin(form.id, payload)
      ElMessage.success(t('customers.saveSuccess'))
      formVisible.value = false
      await loadAccounts()
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('customers.saveFailed'))
  } finally {
    submitting.value = false
  }
}

// Balance adjust
const adjustVisible = ref(false)
const adjusting = ref(false)
const adjustForm = reactive<{ amount: number; change_type: string; description: string }>({
  amount: 0,
  change_type: '',
  description: '',
})

const openAdjust = (row: AdminAccount) => {
  current.value = row
  Object.assign(adjustForm, { amount: 0, change_type: '', description: '' })
  adjustVisible.value = true
}

const submitAdjust = async () => {
  if (!current.value) return
  if (!adjustForm.amount) {
    ElMessage.warning(t('customers.pleaseEnterAmount'))
    return
  }
  adjusting.value = true
  try {
    await adjustAccountBalance(current.value.id, {
      amount: adjustForm.amount,
      change_type: adjustForm.change_type || undefined,
      description: adjustForm.description || undefined,
    })
    ElMessage.success(t('customers.operationSuccess'))
    adjustVisible.value = false
    await loadAccounts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('customers.operationFailed'))
  } finally {
    adjusting.value = false
  }
}

// 账号摘要
const summaryVisible = ref(false)
const summaryLoading = ref(false)
const summaryData = ref<any>(null)

const openSummary = async (row: AdminAccount) => {
  summaryVisible.value = true
  summaryLoading.value = true
  summaryData.value = null
  try {
    const res = await getAccountAdminDetail(row.id)
    summaryData.value = res.account
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('customers.loadFailed'))
  } finally {
    summaryLoading.value = false
  }
}

const resetAndRefreshSummary = async () => {
  if (!summaryData.value) return
  try {
    await ElMessageBox.confirm(
      t('customers.generateCredentialsConfirm'),
      t('customers.accountSummary'),
      { confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), type: 'warning' }
    )
    const res = await resetAccountApiKey(summaryData.value.id)
    ElMessage.success(t('customers.resetSuccess'))
    const detail = await getAccountAdminDetail(summaryData.value.id)
    summaryData.value = detail.account
    await loadAccounts()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.detail || e?.message || t('customers.operationFailed'))
    }
  }
}

const copySummaryAll = async () => {
  if (!summaryData.value) return
  const d = summaryData.value
  let lines: string[] = []
  lines.push(`${t('customers.accountSummary')} - ${d.account_name} (#${d.id})`)
  lines.push(`${t('customers.accessMethod')}: ${d.protocol}`)
  lines.push('')
  if (d.protocol === 'HTTP') {
    lines.push(`=== ${t('customers.authMethodApiKey')} ===`)
    lines.push(`API Key: ${d.api_key || '-'}`)
    lines.push(`${t('customers.requestUrl')}: ${d.api_base_url}/sms/send?api_key=${d.api_key || 'YOUR_API_KEY'}`)
    lines.push('')
    lines.push(`=== ${t('customers.authMethodBasicAuth')} ===`)
    lines.push(`${t('customers.basicAuthUsername')}: ${d.account_name || d.email || '-'}`)
    lines.push(`${t('customers.interfacePassword')}: ${d.api_secret || '-'}`)
    lines.push(`${t('customers.requestUrl')}: ${d.api_base_url}/sms/send`)
    lines.push('')
    lines.push(`=== ${t('customers.apiEndpoints')} ===`)
    lines.push(`API Base: ${d.api_base_url}`)
    lines.push(`${t('customers.httpSendUrl')}: POST ${d.api_base_url}/sms/send`)
    lines.push(`Batch URL: POST ${d.api_base_url}/sms/batch`)
    lines.push(`${t('customers.httpStatusUrl')}: GET ${d.api_base_url}/sms/status/{message_id}`)
    lines.push(`${t('customers.httpBalanceUrl')}: GET ${d.api_base_url}/account/balance`)
  } else if (d.protocol === 'SMPP') {
    lines.push(`${t('customers.serverAddress')}: ${d.smpp_server_host}`)
    lines.push(`${t('customers.serverPort')}: ${d.smpp_server_port}`)
    lines.push(`System ID: ${d.smpp_system_id || '-'}`)
    lines.push(`Password: ${d.smpp_password || '-'}`)
  }
  lines.push('')
  lines.push(`${t('customers.maxThroughput')}: ${d.rate_limit || 100} ${t('customers.perSecond')}`)
  try {
    await navigator.clipboard.writeText(lines.join('\n'))
    ElMessage.success(t('customers.copyAllSuccess'))
  } catch {
    ElMessage.warning(t('customers.copyFailed'))
  }
}

// Reset API key
const handleResetKey = async (row: AdminAccount) => {
  try {
    await ElMessageBox.confirm(t('customers.resetApiKeyConfirm'), t('customers.confirmReset'), {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'warning'
    })
    const res = await resetAccountApiKey(row.id)
    createdCreds.api_key = res.api_key || ''
    createdCreds.api_secret = res.api_secret || ''
    formVisible.value = true
    isEdit.value = true
    current.value = row
    ElMessage.success(t('customers.credentialsReset'))
    await loadAccounts()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.detail || e?.message || t('customers.resetFailed'))
    }
  }
}

// 模拟登录客户账户
const impersonateAccount = async (row: AdminAccount) => {
  try {
    await ElMessageBox.confirm(
      t('customers.impersonateConfirm', { name: row.account_name }),
      t('customers.impersonateLogin'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning'
      }
    )
    
    const res = await request.post(`/admin/accounts/${row.id}/impersonate`)
    if (res.success && res.api_key) {
      const loginUrl =
        res.login_url ||
        `${window.location.origin}/login?impersonate=1&api_key=${encodeURIComponent(res.api_key)}&account_id=${res.account_id}&account_name=${encodeURIComponent(res.account_name)}`
      window.open(loginUrl, '_blank')
      ElMessage.success(t('customers.clientOpened', { name: row.account_name }))
    } else {
      ElMessage.error(t('customers.getCredentialsFailed'))
    }
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.detail || e?.message || t('customers.operationFailed'))
    }
  }
}

// Logs
const logsVisible = ref(false)
const logsLoading = ref(false)
const logs = ref<any[]>([])

const openLogs = async (row: AdminAccount) => {
  current.value = row
  logsVisible.value = true
  logsLoading.value = true
  try {
    const res = await getAccountBalanceLogs(row.id, { limit: 100, offset: 0 })
    logs.value = res.logs || []
  } catch (e: any) {
    ElMessage.error(e?.message || t('customers.loadFailed'))
  } finally {
    logsLoading.value = false
  }
}

// 通道列表
const channelList = ref<any[]>([])
const channelLoading = ref(false)

const loadChannelList = async () => {
  channelLoading.value = true
  try {
    const res = await request.get('/admin/channels')
    channelList.value = res.channels || []
  } catch (e: any) {
    console.error('Failed to load channel list:', e)
  } finally {
    channelLoading.value = false
  }
}

// 销售绑定
const salesBindVisible = ref(false)
const currentAccountId = ref<number | null>(null)
const currentAccountSales = ref<any>(null)
const salesList = ref<any[]>([])
const salesLoading = ref(false)
const selectedSalesId = ref<number | null>(null)
const binding = ref(false)
const unbinding = ref(false)

const bindSales = async (row: AdminAccount) => {
  currentAccountId.value = row.id
  salesBindVisible.value = true
  selectedSalesId.value = null
  
  // 加载当前销售信息
  try {
    const res = await request.get(`/admin/channel-relations/accounts/${row.id}/sales`)
    if (res.success && res.sales) {
      currentAccountSales.value = res.sales
    } else {
      currentAccountSales.value = null
    }
  } catch (e: any) {
    currentAccountSales.value = null
  }
  
  // 加载销售列表
  await loadSalesList()
}

const loadSalesList = async () => {
  salesLoading.value = true
  try {
    // 获取所有销售角色的管理员
    const res = await request.get('/admin/users', { params: { role: 'sales', status: 'active' } })
    if (res.success) {
      salesList.value = res.users || res.items || []
    }
  } catch (e: any) {
    console.error('Failed to load sales list:', e)
  } finally {
    salesLoading.value = false
  }
}

const submitBindSales = async () => {
  if (!selectedSalesId.value) {
    ElMessage.warning(t('customers.pleaseSelectSales'))
    return
  }
  binding.value = true
  try {
    await request.put(`/admin/channel-relations/accounts/${currentAccountId.value}/sales/${selectedSalesId.value}`)
    ElMessage.success(t('customers.bindSuccess'))
    salesBindVisible.value = false
    await loadAccounts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || t('customers.bindFailed'))
  } finally {
    binding.value = false
  }
}

const unbindSales = async () => {
  unbinding.value = true
  try {
    await request.delete(`/admin/channel-relations/accounts/${currentAccountId.value}/sales`)
    ElMessage.success(t('customers.unbindSuccess'))
    currentAccountSales.value = null
    await loadAccounts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || t('customers.unbindFailed'))
  } finally {
    unbinding.value = false
  }
}

// 删除账户
const handleDelete = async (row: AdminAccount) => {
  try {
    await ElMessageBox.confirm(t('customers.deleteConfirm', { name: row.account_name }), t('customers.confirmDelete'), {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'warning'
    })
    await request.delete(`/admin/accounts/${row.id}`)
    ElMessage.success(t('customers.accountDeleted'))
    await loadAccounts()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.detail || t('customers.deleteFailed'))
    }
  }
}

async function salesSetStatus(row: AdminAccount, status: 'active' | 'suspended') {
  const msg =
    status === 'suspended'
      ? t('customers.confirmSuspend', { name: row.account_name })
      : t('customers.confirmActivate', { name: row.account_name })
  try {
    await ElMessageBox.confirm(msg, t('common.tip'), {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'warning',
    })
    await updateAccountAdmin(row.id, { status })
    ElMessage.success(t('customers.saveSuccess'))
    await loadAccounts()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.detail || e?.message || t('customers.saveFailed'))
    }
  }
}

const resetPwdVisible = ref(false)
const resetPwdLoading = ref(false)
const resetPwdRow = ref<AdminAccount | null>(null)
const resetPwdForm = reactive({ password: '' })

const voiceDetailVisible = ref(false)
const voiceDetailRow = ref<any>(null)
function showVoiceDetail(row: any) {
  voiceDetailRow.value = row
  voiceDetailVisible.value = true
}

const okccSyncing = ref(false)
async function handleOkccSync() {
  okccSyncing.value = true
  try {
    const res = await syncOkccBalances()
    const s = res?.stats || {}
    ElMessage.success(`OKCC同步完成：已同步 ${s.synced ?? 0} 个，新增 ${s.created ?? 0} 个`)
    await loadAccounts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '同步失败')
  } finally {
    okccSyncing.value = false
  }
}

function openResetPasswordDialog(row: AdminAccount) {
  resetPwdRow.value = row
  resetPwdForm.password = ''
  resetPwdVisible.value = true
}

async function submitResetPassword() {
  if (!resetPwdRow.value) return
  if (!resetPwdForm.password || resetPwdForm.password.length < 6) {
    ElMessage.warning(t('customers.passwordMinLength'))
    return
  }
  resetPwdLoading.value = true
  try {
    await resetAccountPassword(resetPwdRow.value.id, resetPwdForm.password)
    ElMessage.success(t('customers.resetPasswordSuccess'))
    resetPwdVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('customers.operationFailed'))
  } finally {
    resetPwdLoading.value = false
  }
}

const loadFilterSalesStaff = async () => {
  if (localStorage.getItem('admin_role') === 'sales') return
  try {
    const res = await request.get('/admin/users', { params: { role: 'sales', status: 'active' } })
    if (res.success) {
      filterSalesStaffList.value = res.users || res.items || []
    }
  } catch {
    /* 忽略筛选条销售列表失败 */
  }
}

onMounted(() => {
  adminRole.value = localStorage.getItem('admin_role') || ''
  loadFilterSalesStaff()
  loadAccounts()
})
</script>

<style scoped>
.page-container {
  width: 100%;
  padding: 8px;
}

/* 页面头部 */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.header-left {
  flex: 1;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 6px;
  letter-spacing: -0.02em;
}

.page-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

.add-btn {
  height: 40px;
  padding: 0 20px;
  font-weight: 500;
}

/* 统计卡片 */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: all 0.2s ease;
}

.stat-card:hover {
  border-color: var(--primary);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-icon.blue {
  background: rgba(102, 126, 234, 0.12);
  color: #667eea;
}

.stat-icon.green {
  background: rgba(56, 239, 125, 0.12);
  color: #38ef7d;
}

.stat-icon.purple {
  background: rgba(118, 75, 162, 0.12);
  color: #764ba2;
}

.stat-icon.orange {
  background: rgba(255, 154, 63, 0.12);
  color: #ff9a3f;
}

.stat-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1;
}

.stat-label {
  font-size: 13px;
  color: var(--text-tertiary);
}

/* 主卡片 */
.main-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  overflow: hidden;
}

.card-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.filter-section {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.filter-input-wide {
  width: 200px;
  max-width: 100%;
}
.filter-input-medium {
  width: 160px;
  max-width: 100%;
}
.filter-select-sales {
  width: 200px;
  max-width: 100%;
}

/* 表格样式 */
.data-table {
  --el-table-header-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
}

.data-table :deep(.el-table__header th) {
  background: var(--bg-secondary) !important;
  font-weight: 600;
  font-size: 13px;
  color: var(--text-secondary);
  padding: 14px 0;
}

.data-table :deep(.el-table__body td) {
  padding: 12px 0;
}

/* 账户单元格 */
.account-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.avatar {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 16px;
  font-weight: 600;
  flex-shrink: 0;
}

.account-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.account-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.account-email {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sales-name {
  font-size: 13px;
  color: var(--text-secondary);
}

.tg-username {
  font-size: 13px;
  color: #0088cc;
}

/* 活跃度标签 */
.activity-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.activity-zero {
  background: #fef0f0;
  color: #f56c6c;
  border: 1px solid #fbc4c4;
}

.activity-low {
  background: #fdf6ec;
  color: #e6a23c;
  border: 1px solid #f5dab1;
}

.activity-normal {
  background: #f4f4f5;
  color: #909399;
  border: 1px solid #d3d4d6;
}

.activity-high {
  background: #f0f9eb;
  color: #67c23a;
  border: 1px solid #b3e19d;
}

.activity-gold {
  background: linear-gradient(135deg, #ffd700, #ffb800);
  color: #fff;
  border: none;
  text-shadow: 0 1px 2px rgba(0,0,0,0.2);
}

/* 余额 */
.balance {
  font-size: 14px;
  font-weight: 600;
  color: #38ef7d;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.balance small {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 400;
}

/* API Key */
.api-key-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.api-key {
  font-size: 12px;
  background: var(--bg-secondary);
  padding: 4px 8px;
  border-radius: 6px;
  color: var(--text-secondary);
}

.text-muted {
  color: var(--text-quaternary);
  font-size: 13px;
}

.time-text {
  font-size: 13px;
  color: var(--text-tertiary);
}

/* 操作按钮 */
.action-btns {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

/* 分页 */
.pager {
  display: flex;
  justify-content: flex-end;
  padding: 16px 20px;
  border-top: 1px solid var(--border-default);
}

/* 对话框样式 */
.hint {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 6px;
}

.creds-alert {
  margin-top: 16px;
}

.creds .row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
}

.creds .label {
  width: 90px;
  color: #cbd5e1;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.pos {
  color: #22c55e;
}

.neg {
  color: #ef4444;
}

.current-sales {
  padding: 16px 0;
}

/* 业务类型 Tab */
.biz-tabs {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.biz-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: 8px;
  cursor: pointer;
  background: var(--el-bg-color);
  border: 1.5px solid var(--el-border-color-lighter);
  transition: all 0.2s;
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.biz-tab:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}

.biz-tab.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}

.biz-tab.sms.active {
  border-color: #409eff;
  background: rgba(64, 158, 255, 0.08);
  color: #409eff;
}

.biz-tab.voice.active {
  border-color: #67c23a;
  background: rgba(103, 194, 58, 0.08);
  color: #529b2e;
}

.biz-tab.data.active {
  border-color: #a855f7;
  background: rgba(168, 85, 247, 0.08);
  color: #7c3aed;
}

.tab-icon {
  font-size: 16px;
}

.tab-label {
  font-size: 14px;
}

.tab-count {
  font-size: 13px;
  background: var(--el-fill-color);
  padding: 1px 8px;
  border-radius: 10px;
  min-width: 24px;
  text-align: center;
}

/* 语音专属列样式 */
.voice-code {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: var(--el-color-primary);
  background: var(--el-fill-color-light);
  padding: 1px 6px;
  border-radius: 3px;
}
.sip-count {
  font-size: 11px;
  color: #909399;
  margin-left: 4px;
}
.pkg-name {
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.balance-text.positive { color: #67c23a; font-weight: 600; }
.balance-text.negative { color: #f56c6c; font-weight: 600; }

/* 语音客户详情弹窗 */
.voice-detail-card {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.voice-section {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 16px;
  background: var(--el-fill-color-blank);
}
.voice-section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.voice-icon { font-size: 16px; }
.voice-info-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.voice-info-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.voice-label {
  color: var(--el-text-color-secondary);
  min-width: 80px;
  flex-shrink: 0;
}
.voice-value {
  font-family: 'Courier New', monospace;
  font-size: 13px;
  color: var(--el-text-color-primary);
  background: var(--el-fill-color-light);
  padding: 2px 8px;
  border-radius: 4px;
  word-break: break-all;
}
.voice-link {
  color: var(--el-color-primary);
  text-decoration: none;
}
.voice-link:hover { text-decoration: underline; }
.voice-raw-reply {
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--el-text-color-regular);
  margin-top: 8px;
  max-height: 200px;
  overflow-y: auto;
}

/* 响应式 */
@media (max-width: 1200px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-row {
    grid-template-columns: 1fr;
  }
  
  .page-header {
    flex-direction: column;
    gap: 16px;
  }
  
  .header-right {
    width: 100%;
  }
  
  .add-btn {
    width: 100%;
  }
  
  .filter-section {
    flex-wrap: wrap;
  }
}

/* 账号摘要弹窗 */
.summary-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-default, rgba(255,255,255,0.08));
}
.summary-account-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}
.summary-section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 16px 0 8px;
  padding-left: 4px;
}
.summary-section-title:first-of-type {
  margin-top: 0;
}
.summary-desc {
  margin-bottom: 4px;
}
.mono-val {
  font-family: 'SF Mono', Monaco, 'Cascadia Code', Consolas, monospace;
  font-size: 13px;
  color: var(--text-primary);
  background: var(--bg-input, rgba(255,255,255,0.03));
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--border-subtle, rgba(255,255,255,0.04));
  word-break: break-all;
}
.text-placeholder {
  color: var(--text-quaternary, #c0c4cc);
  font-style: italic;
  font-size: 13px;
}
.text-hint {
  color: var(--text-tertiary, #909399);
  font-size: 13px;
}
</style>

