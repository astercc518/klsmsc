<template>
  <div class="page-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">{{ pageTitle }}</h1>
        <p class="page-desc">{{ pageDesc }}</p>
      </div>
      <div class="header-right">
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
          <span class="stat-value">{{ activeCount }}</span>
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
          <span class="stat-value">{{ boundSalesCount }}</span>
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
        <el-table-column :label="$t('customers.protocol')" min-width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="row.protocol === 'SMPP' ? 'warning' : 'primary'" size="small" effect="plain">
              {{ row.protocol || 'HTTP' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('customers.channel')" min-width="120">
          <template #default="{ row }">
            <template v-if="row.channels?.length">
              <el-tag v-for="ch in row.channels" :key="ch.id" size="small" type="info" effect="plain" style="margin-right: 4px; margin-bottom: 2px">
                {{ ch.channel_code }}
              </el-tag>
            </template>
            <span v-else class="text-muted" title="未指定默认通道，可用全部通道（走全局路由）">*</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('customers.payment')" min-width="60" align="center">
          <template #default="{ row }">
            <el-tag :type="row.payment_type === 'prepaid' ? 'success' : 'warning'" size="small" effect="plain">
              {{ row.payment_type === 'prepaid' ? $t('customers.prepaid') : $t('customers.postpaid') }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 通用列：单价 -->
        <el-table-column :label="$t('customers.unitPrice')" min-width="80" align="right">
          <template #default="{ row }">
            <span v-if="row.unit_price === null || row.unit_price === undefined" class="unit-price" title="未设统一价，按账户国家路由与报价计价">*</span>
            <span v-else class="unit-price">{{ row.currency === 'CNY' ? '¥' : '$' }}{{ Number(row.unit_price).toFixed(4) }}</span>
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
        <el-table-column min-width="110" align="right">
          <template #header>
            <el-tooltip :content="$t('customers.remainingMessagesHint')" placement="top">
              <span class="col-hint">{{ $t('customers.remainingMessages') }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="remaining-msgs">{{ formatRemainingMessages(row) }}</span>
          </template>
        </el-table-column>

        <!-- 通用列：创建时间 -->
        <el-table-column prop="created_at" :label="$t('customers.createdAt')" min-width="90">
          <template #default="{ row }">
            <span class="time-text">{{ formatDate(row.created_at) }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column :label="$t('common.action')" :width="isSalesRole ? 360 : 200" fixed="right" align="center">
          <template #default="{ row }">
            <div class="action-btns">
              <template v-if="isSalesRole">
                <el-button link type="warning" size="small" @click="impersonateAccount(row)" :disabled="row.status !== 'active'">{{ $t('customers.login') }}</el-button>
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
                <el-button link type="success" size="small" @click="openSalesRecharge(row)">{{ $t('customers.recharge') }}</el-button>
                <el-button link type="primary" size="small" @click="openResetPasswordDialog(row)">{{ $t('customers.resetLoginPassword') }}</el-button>
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
                      <el-dropdown-item @click="openCountryRoutes(row)">国家路由与报价</el-dropdown-item>
                      <el-dropdown-item @click="openLogs(row)">{{ $t('customers.balance') }}</el-dropdown-item>
                      <el-dropdown-item @click="openResetPasswordDialog(row)">{{ $t('customers.resetLoginPassword') }}</el-dropdown-item>
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
            <el-option label="📊 数据 Data" value="data" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('customers.country')">
          <el-select v-model="form.country_code" :placeholder="$t('customers.selectCountry')" filterable clearable style="width: 100%">
            <el-option label="* 全部国家（不限）" value="" />
            <el-option v-for="c in countryList" :key="c.code" :label="`${c.name} (${c.code})`" :value="c.code" />
          </el-select>
          <div class="hint">选「* 全部国家」=不限国家（按账户国家路由控制可发国家）</div>
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
            <el-input-number v-model="form.unit_price" :min="0" :max="10" :precision="4" :step="0.01" :value-on-clear="null" style="width: 150px" />
            <span style="margin-left: 8px; color: #909399">{{ form.currency }}/{{ $t('customers.perMessage') }}</span>
            <el-button link type="primary" size="small" style="margin-left: 8px" @click="form.unit_price = null">清空</el-button>
            <span v-if="form.unit_price === null || form.unit_price === undefined" style="margin-left: 6px; color: #67c23a; font-size: 12px">已清空 · 将按账户「国家路由与报价」计价</span>
          </el-form-item>
          
          <!-- 风控限制 -->
          <el-divider content-position="left">{{ $t('customers.riskControl') }}</el-divider>
          <el-form-item :label="$t('customers.sendRateLimit')">
            <el-input-number v-model="form.rate_limit" :min="1" :max="10000" style="width: 150px" />
            <span style="margin-left: 8px; color: #909399">{{ $t('customers.messagesPerSecond') }}</span>
          </el-form-item>
          <el-form-item v-if="form.protocol === 'SMPP'" :label="$t('customers.maxConnections')">
            <el-input-number v-model="form.smpp_max_binds" :min="1" :max="50" style="width: 150px" />
            <span style="margin-left: 8px; color: #909399">{{ $t('customers.smppConnHint') }}</span>
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
          <el-switch v-model="useAllChannels" active-text="全部通道 (*)" inline-prompt style="margin-bottom: 6px" />
          <el-select v-if="!useAllChannels" v-model="form.channel_ids" :placeholder="$t('customers.selectChannel')" multiple clearable filterable style="width: 100%" :loading="channelLoading">
            <el-option v-for="ch in channelList" :key="ch.id" :label="`${ch.channel_name} (${ch.channel_code})`" :value="ch.id">
              <span>{{ ch.channel_name }}</span>
              <span style="color: #8492a6; font-size: 12px; margin-left: 8px">{{ ch.protocol }}</span>
            </el-option>
          </el-select>
          <div v-if="useAllChannels" class="hint" style="color:#67c23a">可用全部通道（走全局路由），列表显示 *；按国家专属通道仍在「国家路由与报价」单独配置</div>
          <div v-else class="hint">{{ $t('customers.channelPriorityHint') }}</div>
        </el-form-item>

        <!-- 客户门户显示控制（仅编辑）：部分销售要求对其客户隐藏价格/TG -->
        <template v-if="isEdit">
          <el-divider content-position="left">{{ $t('customers.portalDisplay') }}</el-divider>
          <el-form-item :label="$t('customers.hidePrice')">
            <el-switch v-model="form.hide_price" />
            <span class="hint" style="margin-left: 12px">{{ $t('customers.hidePriceHint') }}</span>
          </el-form-item>
          <el-form-item :label="$t('customers.hideTg')">
            <el-switch v-model="form.hide_tg" />
            <span class="hint" style="margin-left: 12px">{{ $t('customers.hideTgHint') }}</span>
          </el-form-item>
        </template>

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
          <el-input-number v-model="adjustForm.amount" :precision="4" :min="0" style="width: 100%" />
          <div class="hint">{{ adjustForm.change_type === 'withdraw' ? $t('customers.amountHintWithdraw') : $t('customers.amountHintDeposit') }}</div>
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

    <!-- 销售授信充值 -->
    <el-dialog v-model="salesRechargeVisible" :title="$t('customers.salesRecharge')" width="480px" :close-on-click-modal="false">
      <el-form :model="salesRechargeForm" label-width="96px">
        <el-form-item :label="$t('customers.account')">
          <el-tag type="info" effect="plain">{{ current?.account_name }} (#{{ current?.id }})</el-tag>
        </el-form-item>
        <el-form-item :label="$t('customers.creditAvailable')">
          <span :class="myCredit.credit_available > 0 ? 'credit-ok' : 'credit-none'">
            {{ myCredit.credit_available.toFixed(2) }}
          </span>
          <span class="hint" style="margin-left:8px">{{ $t('customers.creditOf') }} {{ myCredit.credit_limit.toFixed(2) }}</span>
        </el-form-item>
        <el-form-item :label="$t('customers.amount')" required>
          <el-input-number v-model="salesRechargeForm.amount" :precision="4" :min="0" :max="myCredit.credit_available" style="width: 100%" />
          <div class="hint">{{ $t('customers.salesRechargeHint') }}</div>
        </el-form-item>
        <el-form-item :label="$t('customers.description')">
          <el-input v-model="salesRechargeForm.description" type="textarea" rows="2" :placeholder="$t('customers.optional')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="salesRechargeVisible=false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="salesRecharging" :disabled="myCredit.credit_available <= 0" @click="submitSalesRecharge">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 余额日志 -->
    <el-dialog v-model="logsVisible" :title="$t('customers.balanceLogs')" width="960px" :close-on-click-modal="false">
      <el-table :data="logs" stripe v-loading="logsLoading" size="small" :empty-text="$t('customers.balanceLogEmpty')">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column :label="$t('customers.changeType')" width="100">
          <template #default="{ row }">
            <el-tag :type="changeTypeTagType(row.change_type)" size="small" effect="light">
              {{ changeTypeLabel(row.change_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('customers.amount')" width="120" align="right">
          <template #default="{ row }">
            <span :class="Number(row.amount) >= 0 ? 'pos' : 'neg'">
              {{ formatAmount(row.amount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('customers.balanceBefore')" width="130" align="right">
          <template #default="{ row }">{{ formatBalance(row.balance_before) }}</template>
        </el-table-column>
        <el-table-column :label="$t('customers.balanceAfter')" width="130" align="right">
          <template #default="{ row }">{{ formatBalance(row.balance_after) }}</template>
        </el-table-column>
        <el-table-column prop="description" :label="$t('common.description')" min-width="220" show-overflow-tooltip />
        <el-table-column :label="$t('customers.time')" width="170">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="logsVisible=false">{{ $t('common.close') }}</el-button>
      </template>
    </el-dialog>

    <!-- 国家路由与报价（每账户每国家：通道 + 销售价） -->
    <el-dialog v-model="crVisible" :title="`国家路由与报价 · ${crAccount?.account_name || ''}`" width="760px" :close-on-click-modal="false">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
        <template #title>
          为该账户按目的国家分别指定「上游通道」与「销售单价」。未在此配置的国家将回退到账户的全国默认通道与统一/全局价格；若该账户只配置了部分国家且无全国默认通道，则未配置国家会被拒绝发送。
        </template>
      </el-alert>
      <div v-loading="crLoading">
        <el-table :data="crList" size="small" border>
          <el-table-column label="国家" min-width="220">
            <template #default="{ row }">
              <el-select v-model="row.country_code" filterable placeholder="选择国家" style="width: 100%">
                <el-option
                  v-for="c in COUNTRY_LIST"
                  :key="c.iso"
                  :label="`${c.name || c.en} (${c.iso} +${c.dial})`"
                  :value="c.iso"
                />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="路由通道" min-width="240">
            <template #default="{ row }">
              <el-select v-model="row.channel_id" filterable placeholder="选择通道" style="width: 100%" :loading="channelLoading">
                <el-option
                  v-for="ch in channelList"
                  :key="ch.id"
                  :label="`${ch.channel_name} (${ch.channel_code})`"
                  :value="ch.id"
                />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="销售单价(USD/条)" width="170">
            <template #default="{ row }">
              <el-input-number v-model="row.price" :min="0" :precision="4" :step="0.001" controls-position="right" placeholder="可留空" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" @click="crList.splice($index, 1)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button text type="primary" :icon="Plus" style="margin-top: 10px" @click="addCrRow">添加国家</el-button>
      </div>
      <template #footer>
        <el-button @click="crVisible=false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="crSaving" @click="saveCountryRoutes">{{ $t('common.save') }}</el-button>
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
                <template v-else>
                  <span class="text-placeholder">{{ $t('customers.notGenerated') }}</span>
                  <el-button type="primary" link size="small" style="margin-left: 8px" @click="handleGeneratePassword">
                    {{ $t('customers.generateNow') }}
                  </el-button>
                </template>
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
              <el-descriptions-item :label="$t('customers.maxConnections')">{{ summaryData.smpp_max_binds ?? 5 }} {{ $t('customers.perConnection') }}</el-descriptions-item>
              <el-descriptions-item :label="$t('customers.ipWhitelist')">
                {{ (summaryData.ip_whitelist && summaryData.ip_whitelist.length) ? summaryData.ip_whitelist.join(', ') : $t('customers.noRestriction') }}
              </el-descriptions-item>
            </el-descriptions>
          </template>
        </template>
        <el-empty v-else-if="!summaryLoading" :description="$t('customers.noCredentials')" />
      </div>
      <template #footer>
        <el-button :loading="apiDocDownloading" @click="downloadApiDoc">{{ $t('customers.downloadApiDoc') }}</el-button>
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
  salesRechargeAccount,
  getMyCredit,
  resetAccountApiKey,
  resetAccountPassword,
  generateAccountPassword,
  getAccountBalanceLogs,
  getAccountCountryRoutes,
  setAccountCountryRoutes,
  type AdminAccount,
} from '@/api/admin'
import request from '@/api/index'
import { COUNTRY_LIST, findCountryByIso, findCountryByDial, searchCountries } from '@/constants/countries'

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
  if (props.defaultBusinessType === 'data') return t('menu.dataAccounts')
  return t('customers.title')
})

const pageDesc = computed(() => {
  return t('customers.pageDesc')
})

// 全表统计（来自接口，按当前筛选条件，不受分页影响）
const totalBalance = ref(0)
const activeCount = ref(0)
const boundSalesCount = ref(0)

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
    totalBalance.value = res.total_balance || 0
    activeCount.value = res.active_count || 0
    boundSalesCount.value = res.bound_sales_count || 0
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

// 国家列表：直接走全量 COUNTRY_LIST（135 国），按当前语言显示名称排序。
// 之前是固定 26 国白名单，开新市场（如智利、哥伦比亚等）就要改代码；现已解耦。
// el-select :filterable 已支持搜索（中文/英文/ISO 都能匹配 label）。
const countryList = computed(() => {
  const isZh = locale.value.startsWith('zh')
  const items = COUNTRY_LIST.map(c => ({ code: c.iso, name: isZh ? c.name : c.en }))
  items.sort((a, b) => a.name.localeCompare(b.name, isZh ? 'zh-CN' : 'en'))
  return items
})

/** 列表中国家列：支持 ISO 代码和电话区号，按当前语言显示国家名称 */
function formatAccountCountry(code: string | null | undefined): string {
  // 空/通配 = 不限国家，显示 *
  if (!code || String(code).trim() === '*') return '*'
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
  smpp_max_binds: 5,
  low_balance_threshold: 100,
  // 客户门户显示控制
  hide_price: false,
  hide_tg: false,
})

const openCreate = () => {
  isEdit.value = false
  current.value = null
  useAllChannels.value = false
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
    smpp_max_binds: 5,
    low_balance_threshold: 100,
    // 绑定配置
    sales_id: null,
    channel_ids: [],
    // 客户门户显示控制
    hide_price: false,
    hide_tg: false,
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
    // 账户无统一单价(NULL)时保持为空，避免误回填 0.01 又存回去；空=走账户国家定价/全局价
    unit_price: (row as any).unit_price ?? accountDetail.unit_price ?? undefined,
    status: row.status,
    currency: row.currency,
    rate_limit: row.rate_limit ?? 1000,
    smpp_max_binds: (row as any).smpp_max_binds ?? 5,
    low_balance_threshold: row.low_balance_threshold ?? 100,
    sales_id: (row as any).sales_id || accountDetail.sales_id || null,
    channel_ids: accountDetail.channel_ids || [],
    // 客户门户显示控制（以详情为准，回退 false=照常展示）
    hide_price: !!(accountDetail.hide_price ?? (row as any).hide_price),
    hide_tg: !!(accountDetail.hide_tg ?? (row as any).hide_tg),
  })
  // 无"全国默认"通道绑定 = 全部通道(*)
  useAllChannels.value = !(accountDetail.channel_ids && accountDetail.channel_ids.length)
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
      // 显式发送（含空串），以便编辑时可"清空国家限制"=改为多国/不限；否则 undefined 会被后端跳过无法清空
      country_code: form.country_code || '',
      business_type: form.business_type,
      // 接入协议
      protocol: form.protocol,
      smpp_password: form.protocol === 'SMPP' ? (form.smpp_password || undefined) : undefined,
      // 计费配置
      payment_type: form.payment_type,
      // 显式发送（含 null）：清空统一单价=回退到账户国家定价；undefined 会被后端忽略无法清空
      unit_price: form.unit_price ?? null,
      status: form.status,
      currency: form.currency,
      // 风控配置
      rate_limit: form.rate_limit,
      smpp_max_binds: form.smpp_max_binds,
      low_balance_threshold: form.low_balance_threshold,
      ip_whitelist: normalizeWhitelist(),
      // 绑定配置
      sales_id: form.sales_id || undefined,
      // 全部通道(*)=发空数组让后端清空"全国默认"绑定；否则发所选；未选则不改动
      channel_ids: useAllChannels.value ? [] : (form.channel_ids?.length ? form.channel_ids : undefined),
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
      // 客户门户显示控制仅在编辑时提交（新增接口不接收这两个开关）
      payload.hide_price = form.hide_price
      payload.hide_tg = form.hide_tg
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

// ===== 销售授信充值 =====
const myCredit = reactive<{ applicable: boolean; credit_limit: number; credit_used: number; credit_available: number }>({
  applicable: false, credit_limit: 0, credit_used: 0, credit_available: 0,
})
const salesRechargeVisible = ref(false)
const salesRecharging = ref(false)
const salesRechargeForm = reactive<{ amount: number; description: string }>({ amount: 0, description: '' })
let salesRechargeIdemKey = ''

const refreshMyCredit = async () => {
  try {
    const res = await getMyCredit()
    myCredit.applicable = !!res.applicable
    myCredit.credit_limit = res.credit_limit || 0
    myCredit.credit_used = res.credit_used || 0
    myCredit.credit_available = res.credit_available || 0
  } catch (e) {
    // 忽略：非销售或接口异常时保持 0
  }
}

const genIdemKey = () => {
  try {
    if (typeof crypto !== 'undefined' && (crypto as any).randomUUID) return (crypto as any).randomUUID()
  } catch (e) { /* noop */ }
  return `sr-${Date.now()}-${Math.floor(Math.random() * 1e9)}`
}

const openSalesRecharge = async (row: AdminAccount) => {
  current.value = row
  Object.assign(salesRechargeForm, { amount: 0, description: '' })
  salesRechargeIdemKey = genIdemKey()  // 每次打开生成新幂等键，重试同一次充值不会重复扣款
  await refreshMyCredit()
  salesRechargeVisible.value = true
}

const submitSalesRecharge = async () => {
  if (!current.value) return
  const amt = Number(salesRechargeForm.amount)
  if (!amt || amt <= 0) {
    ElMessage.warning(t('customers.pleaseEnterAmount'))
    return
  }
  if (amt > myCredit.credit_available) {
    ElMessage.warning(t('customers.creditInsufficient'))
    return
  }
  salesRecharging.value = true
  try {
    const res = await salesRechargeAccount(current.value.id, {
      amount: amt,
      description: salesRechargeForm.description || undefined,
      idempotency_key: salesRechargeIdemKey,
    })
    myCredit.credit_limit = res.credit_limit_after ?? myCredit.credit_limit
    myCredit.credit_used = res.credit_used_after ?? myCredit.credit_used
    myCredit.credit_available = res.credit_available ?? myCredit.credit_available
    ElMessage.success(t('customers.operationSuccess'))
    salesRechargeVisible.value = false
    await loadAccounts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('customers.operationFailed'))
  } finally {
    salesRecharging.value = false
  }
}

// 账号摘要
const summaryVisible = ref(false)
const summaryLoading = ref(false)
const summaryData = ref<any>(null)
const apiDocDownloading = ref(false)

// 知识库中「SMS Gateway HTTP与SMPP接口文档」文章 ID（固定）；按 article 取附件，附件 ID 变动不影响入口
const API_DOC_ARTICLE_ID = 12

const downloadApiDoc = async () => {
  if (apiDocDownloading.value) return
  apiDocDownloading.value = true
  try {
    const detail: any = await request.get(`/admin/knowledge/${API_DOC_ARTICLE_ID}`)
    const atts: any[] = detail?.article?.attachments || []
    const pdf = atts.find((a) => (a.file_name || '').toLowerCase().endsWith('.pdf')) || atts[0]
    if (!pdf) {
      ElMessage.error(t('customers.apiDocNotFound'))
      return
    }
    const base = import.meta.env.VITE_API_BASE_URL ? `${import.meta.env.VITE_API_BASE_URL}/api/v1` : '/api/v1'
    const token = localStorage.getItem('admin_token')
    const res = await fetch(`${base}/admin/knowledge/attachment/${pdf.id}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = pdf.file_name || 'SMS_API_接口文档.pdf'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('customers.apiDocDownloadFailed'))
  } finally {
    apiDocDownloading.value = false
  }
}

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

const handleGeneratePassword = async () => {
  if (!summaryData.value) return
  try {
    const res = await generateAccountPassword(summaryData.value.id)
    ElMessage.success(t('customers.resetSuccess'))
    const detail = await getAccountAdminDetail(summaryData.value.id)
    summaryData.value = detail.account
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('customers.operationFailed'))
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
    if (res.success && res.login_url) {
      window.open(res.login_url, '_blank')
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

const CHANGE_TYPE_TAG: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
  charge: 'danger',
  withdraw: 'warning',
  deposit: 'success',
  recharge: 'success',
  refund: '',
  refund_recharge: '',
  adjustment: 'info',
}

const changeTypeTagType = (type: string): '' | 'success' | 'warning' | 'info' | 'danger' => {
  return CHANGE_TYPE_TAG[type] ?? 'info'
}

const changeTypeLabel = (type: string): string => {
  if (!type) return '-'
  const map: Record<string, string> = {
    charge: 'customers.changeTypeCharge',
    deposit: 'customers.changeTypeDeposit',
    withdraw: 'customers.changeTypeWithdraw',
    adjustment: 'customers.changeTypeAdjustment',
    refund: 'customers.changeTypeRefund',
    recharge: 'customers.changeTypeRecharge',
    refund_recharge: 'customers.changeTypeRefundRecharge',
  }
  const key = map[type]
  return key ? t(key) : type
}

const formatAmount = (v: any): string => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '-'
  const sign = n > 0 ? '+' : ''
  return sign + n.toFixed(4)
}

const formatBalance = (v: any): string => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '-'
  return n.toFixed(4)
}

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
// 通道「全部(*)」开关：ON=可用全部通道(清空全国默认绑定，走全局路由)
const useAllChannels = ref(false)

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

// 国家路由与报价（每账户每国家：通道 + 销售价）
interface CrRow { country_code: string; channel_id: number | null; price: number | null }
const crVisible = ref(false)
const crLoading = ref(false)
const crSaving = ref(false)
const crAccount = ref<AdminAccount | null>(null)
const crList = ref<CrRow[]>([])

const openCountryRoutes = async (row: AdminAccount) => {
  crAccount.value = row
  crVisible.value = true
  crList.value = []
  crLoading.value = true
  try {
    if (!channelList.value.length) await loadChannelList()
    const res = await getAccountCountryRoutes(row.id)
    crList.value = (res.routes || []).map((r: any) => ({
      country_code: r.country_code,
      channel_id: r.channel_id,
      price: r.price ?? null,
    }))
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载失败')
  } finally {
    crLoading.value = false
  }
}

const addCrRow = () => {
  crList.value.push({ country_code: '', channel_id: null, price: null })
}

const saveCountryRoutes = async () => {
  if (!crAccount.value) return
  const seen = new Set<string>()
  for (const r of crList.value) {
    if (!r.country_code || !r.channel_id) {
      ElMessage.warning('每行都需选择国家和通道')
      return
    }
    if (seen.has(r.country_code)) {
      ElMessage.warning(`国家重复：${r.country_code}`)
      return
    }
    seen.add(r.country_code)
  }
  crSaving.value = true
  try {
    const res = await setAccountCountryRoutes(
      crAccount.value.id,
      crList.value.map(r => ({ country_code: r.country_code, channel_id: r.channel_id as number, price: r.price })),
    )
    ElMessage.success(res.message || '已保存')
    crVisible.value = false
    loadAccounts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    crSaving.value = false
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
    const res = await request.get('/admin/users', {
      params: { role: 'sales', status: 'active', include_monthly_stats: false },
    })
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
    const res = await request.get('/admin/users', {
      params: { role: 'sales', status: 'active', include_monthly_stats: false },
    })
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
  if (isSalesRole.value) refreshMyCredit()
})
</script>

<style scoped>
.page-container {
  width: 100%;
  padding: 8px;
}

.credit-ok {
  color: #67c23a;
  font-weight: 600;
  font-size: 16px;
}

.credit-none {
  color: #f56c6c;
  font-weight: 600;
  font-size: 16px;
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

/* 操作按钮（允许换行） */
.action-btns {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 8px 12px;
  max-width: 100%;
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

