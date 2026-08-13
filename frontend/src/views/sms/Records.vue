<template>
  <div class="records-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">{{ $t('smsRecords.title') }}</h1>
        <p class="page-desc">{{ $t('smsRecords.pageDesc') }}</p>
        <p class="status-explain">{{ $t('smsRecords.statusExplain') }}</p>
      </div>
      <div class="header-actions">
        <el-popover v-if="!isMobile" placement="bottom-end" :width="320" trigger="click" popper-class="col-popover">
          <template #reference>
            <button class="action-btn columns">
              <el-icon><Grid /></el-icon>
              {{ $t('smsRecords.columns') }}
              <span class="col-count">{{ visibleColumns.length }}/{{ availableColumns.length }}</span>
            </button>
          </template>
          <div class="col-panel">
            <div class="col-panel-head">
              <span class="col-panel-title">{{ $t('smsRecords.columnsTitle') }}</span>
              <div class="col-panel-ops">
                <a class="col-op" @click="selectAllColumns">{{ $t('smsRecords.columnsAll') }}</a>
                <a class="col-op" @click="resetColumns">{{ $t('smsRecords.columnsReset') }}</a>
              </div>
            </div>
            <el-checkbox-group v-model="visibleColumns" class="col-list">
              <el-checkbox
                v-for="c in availableColumns"
                :key="c.key"
                :value="c.key"
                :label="c.key"
                :disabled="visibleColumns.length === 1 && colVisible(c.key)"
              >
                {{ columnLabel(c) }}
              </el-checkbox>
            </el-checkbox-group>
          </div>
        </el-popover>
        <button v-if="isAdmin" class="action-btn download" @click="openExport">
          <el-icon><Download /></el-icon>
          {{ $t('smsRecords.exportTitle') }}
        </button>
        <button class="action-btn refresh" @click="loadRecords">
          <el-icon><Refresh /></el-icon>
          {{ $t('common.refresh') }}
        </button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-chip">
        <span class="stat-chip-label">{{ $t('smsRecords.totalRecords') }}</span>
        <span class="stat-chip-value">{{ totalApproximate ? '约 ' + pagination.total.toLocaleString() : pagination.total.toLocaleString() }}</span>
      </div>
      <div class="stat-chip sent">
        <span class="stat-chip-dot"></span>
        <span class="stat-chip-label">{{ $t('smsRecords.sent') }}</span>
        <span class="stat-chip-value">{{ statusCounts.sent }}</span>
      </div>
      <div class="stat-chip delivered">
        <span class="stat-chip-dot"></span>
        <span class="stat-chip-label">{{ $t('smsRecords.delivered') }}</span>
        <span class="stat-chip-value">{{ statusCounts.delivered }}</span>
      </div>
      <div class="stat-chip failed">
        <span class="stat-chip-dot"></span>
        <span class="stat-chip-label">{{ $t('smsRecords.failed') }}</span>
        <span class="stat-chip-value">{{ statusCounts.failed }}</span>
      </div>
      <div class="stat-chip expired">
        <span class="stat-chip-dot"></span>
        <span class="stat-chip-label">{{ $t('smsRecords.expired') }}</span>
        <span class="stat-chip-value">{{ statusCounts.expired }}</span>
      </div>
    </div>

    <!-- 筛选栏（移动端折叠为抽屉） -->
    <MobileFilterDrawer
      :active-count="activeFilterCount"
      @apply="handleSearch"
      @reset="handleReset"
    >
      <div class="filter-content">
        <div class="filter-item" v-if="isAdmin">
          <label class="filter-label">{{ $t('smsRecords.customerAccount') }}</label>
          <el-select v-model="searchForm.account_id" :placeholder="$t('smsRecords.allAccounts')" clearable size="large" class="filter-select">
            <el-option v-for="acc in accounts" :key="acc.id" :label="`${acc.account_name} (${acc.id})`" :value="acc.id" />
          </el-select>
        </div>

        <div class="filter-item">
          <label class="filter-label">手机号码</label>
          <el-input v-model="searchForm.phone_number" placeholder="搜索号码" clearable size="large" class="filter-input" @keyup.enter="handleSearch" />
        </div>

        <div class="filter-item">
          <label class="filter-label">{{ $t('smsRecords.messageId') }}</label>
          <el-input
            v-model="searchForm.message_id"
            :placeholder="$t('smsRecords.messageIdPlaceholder')"
            clearable
            size="large"
            class="filter-input"
            @keyup.enter="handleSearch"
          />
        </div>

        <div class="filter-item">
          <label class="filter-label">{{ $t('smsRecords.statusFilter') }}</label>
          <el-select v-model="searchForm.status" :placeholder="$t('smsRecords.allStatus')" clearable size="large" class="filter-select">
            <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value">
              <div class="status-option"><span class="status-dot" :class="s.value"></span>{{ s.label }}</div>
            </el-option>
          </el-select>
        </div>

        <div class="filter-item">
          <label class="filter-label">通道</label>
          <el-select v-model="searchForm.channel_id" placeholder="全部通道" clearable size="large" class="filter-select">
            <el-option v-for="ch in channels" :key="ch.id" :label="ch.channel_code ?? ch.code" :value="ch.id" />
          </el-select>
        </div>

        <div class="filter-item">
          <label class="filter-label">国家</label>
          <el-select v-model="searchForm.country_code" :placeholder="$t('smsRecords.allCountries')" clearable size="large" class="filter-select">
            <el-option v-for="c in countryOptions" :key="c.dial" :label="c.name" :value="c.dial" />
          </el-select>
        </div>

        <div class="filter-item" v-if="searchForm.batch_id">
          <label class="filter-label">任务ID</label>
          <el-input-number
            v-model="searchForm.batch_id"
            :min="1"
            placeholder="任务ID"
            size="large"
            class="filter-input"
            controls-position="right"
            style="width: 130px"
          />
        </div>

        <div class="filter-item">
          <label class="filter-label">日期范围</label>
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="~"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            size="large"
            class="filter-date"
            :shortcuts="dateShortcuts"
          />
        </div>

        <div class="filter-actions">
          <button class="filter-btn search" @click="handleSearch">
            <el-icon><Search /></el-icon>
            {{ $t('smsRecords.query') }}
          </button>
          <button class="filter-btn reset" @click="handleReset">{{ $t('common.reset') }}</button>
        </div>
      </div>
    </MobileFilterDrawer>

    <!-- 数据表格 -->
    <div class="table-card">
      <!-- 移动端：卡片列表 -->
      <div class="mobile-card-list" v-if="isMobile" v-loading="loading">
        <div
          v-for="row in records"
          :key="row.id"
          class="record-card"
          :class="row.status"
          @click="handleViewDetail(row)"
        >
          <div class="rc-row rc-row-top">
            <span class="rc-phone">{{ row.phone_number }}</span>
            <span class="status-badge" :class="row.status">{{ getStatusText(row.status) }}</span>
          </div>
          <div class="rc-message">{{ truncate(row.message, 80) }}</div>
          <div class="rc-row rc-row-meta">
            <span class="rc-meta-item">
              <span class="rc-flag">{{ countryDisplay(row.country_code) }}</span>
              <el-tag v-if="row.channel_code" size="small" effect="plain">{{ row.channel_code }}</el-tag>
            </span>
            <span class="rc-time">{{ formatTime(row.submit_time) }}</span>
          </div>
          <div class="rc-row rc-row-bottom" v-if="isAdmin && row.account_name">
            <span class="rc-account">{{ row.account_name }}</span>
            <span class="rc-cost" v-if="row.selling_price != null">{{ row.selling_price?.toFixed(4) }}</span>
          </div>
          <div class="rc-row rc-row-bottom" v-else-if="!isAdmin && row.selling_price != null">
            <span class="rc-cost">{{ row.selling_price?.toFixed(4) }} {{ row.currency }}</span>
          </div>
          <div class="rc-error" v-if="shouldShowErrorMessage(row)">
            <span v-if="friendlyError(row.error_message)">{{ friendlyError(row.error_message)!.title }}</span>
            <span v-else>{{ row.error_message }}</span>
          </div>
        </div>
        <div v-if="!records.length && !loading" class="rc-empty">{{ $t('common.noData') || '暂无记录' }}</div>
      </div>

      <!-- 桌面端：表格 -->
      <div class="table-wrapper" v-else v-loading="loading">
        <el-table :data="records" class="records-table" :row-class-name="tableRowClassName" @row-click="handleViewDetail" empty-text="暂无记录" stripe>
          <el-table-column v-if="colVisible('id')" prop="id" label="ID" width="110">
            <template #default="{ row }">
              <span class="mono-text">{{ row.id }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('account_name')" prop="account_name" label="客户" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="account-cell">
                <span class="account-name-text">{{ row.account_name || '-' }}</span>
                <span v-if="row.sales_name && !colVisible('sales_name')" class="sales-tag">{{ row.sales_name }}</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('account_id')" prop="account_id" label="客户ID" width="90" align="center">
            <template #default="{ row }">
              <span class="mono-text">{{ row.account_id }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('sales_name')" prop="sales_name" label="归属员工" width="110" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.sales_name || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('message_id')" prop="message_id" :label="$t('smsRecords.messageId')" width="140">
            <template #default="{ row }">
              <el-tooltip :content="row.message_id" placement="top">
                <span class="mono-text clickable">{{ row.message_id?.substring(0, 12) }}...</span>
              </el-tooltip>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('upstream_message_id')" prop="upstream_message_id" label="上游消息ID" width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="mono-text">{{ row.upstream_message_id || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('batch_id')" prop="batch_id" label="任务ID" width="90" align="center">
            <template #default="{ row }">
              <span class="mono-text">{{ row.batch_id || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('phone_number')" prop="phone_number" label="手机号码" width="150">
            <template #default="{ row }">
              <span class="phone-text">{{ row.phone_number }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('country_code')" prop="country_code" :label="$t('smsRecords.country')" width="90" align="center">
            <template #default="{ row }">
              <span>{{ countryDisplay(row.country_code) }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('channel_code')" prop="channel_code" label="通道" width="140">
            <template #default="{ row }">
              <el-tag v-if="row.channel_code" size="small" :type="row.channel_code?.includes('SMPP') ? 'primary' : 'success'" effect="plain">
                {{ row.channel_code }}
              </el-tag>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('sender_id')" prop="sender_id" label="发送ID(SID)" width="120" align="center">
            <template #default="{ row }">
              <span v-if="row.sender_id">{{ row.sender_id }}</span>
              <span v-else class="text-muted">默认</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('message')" prop="message" label="内容" min-width="200">
            <template #default="{ row }">
              <el-tooltip :content="row.message" placement="top" :show-after="500">
                <span class="message-preview">{{ truncate(row.message, 40) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('message_count')" prop="message_count" label="条数" width="70" align="center">
            <template #default="{ row }">
              <span>{{ row.message_count || 1 }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('status')" prop="status" label="状态" width="100" align="center">
            <template #default="{ row }">
              <span class="status-badge" :class="row.status">{{ getStatusText(row.status) }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('status_code')" prop="status" label="状态码" width="100" align="center">
            <template #default="{ row }">
              <span class="mono-text">{{ row.status }}</span>
            </template>
          </el-table-column>

          <el-table-column
            v-if="colVisible('error_message')"
            prop="error_message"
            :label="$t('smsRecords.errorMsg')"
            min-width="160"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <template v-if="shouldShowErrorMessage(row)">
                <span v-if="friendlyError(row.error_message)" class="error-preview-friendly">
                  {{ friendlyError(row.error_message)!.title }}
                </span>
                <span v-else class="error-preview">{{ row.error_message }}</span>
              </template>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('selling_price')" prop="selling_price" label="售价" width="110" align="right">
            <template #default="{ row }">
              <span class="cost-selling">{{ row.selling_price?.toFixed(4) }}<template v-if="!colVisible('currency')"> {{ row.currency }}</template></span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('cost_price')" prop="cost_price" label="成本价" width="100" align="right">
            <template #default="{ row }">
              <span class="cost-detail">{{ row.cost_price?.toFixed(4) }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('profit')" prop="profit" label="利润" width="100" align="right">
            <template #default="{ row }">
              <span :class="row.profit >= 0 ? 'profit-positive' : 'profit-negative'">{{ row.profit?.toFixed(4) }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('currency')" prop="currency" label="币种" width="80" align="center">
            <template #default="{ row }">
              <span>{{ row.currency || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('submit_time')" prop="submit_time" label="提交时间" width="170">
            <template #default="{ row }">
              <span class="time-text">{{ formatTime(row.submit_time) }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('sent_time')" prop="sent_time" :label="$t('smsRecords.sentTime')" width="170">
            <template #default="{ row }">
              <span class="time-text">{{ formatTime(row.sent_time) || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('delivery_time')" prop="delivery_time" :label="$t('smsRecords.deliveryTime')" width="170">
            <template #default="{ row }">
              <span class="time-text">{{ formatTime(row.delivery_time) || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="colVisible('refunded_at')" prop="refunded_at" label="退款时间" width="170">
            <template #default="{ row }">
              <span class="time-text">{{ formatTime(row.refunded_at) || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="" width="50" align="center" fixed="right">
            <template #default="{ row }">
              <el-icon class="detail-icon" @click.stop="handleViewDetail(row)"><View /></el-icon>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 分页（键集翻页：上一页/下一页恒定 O(page_size)，深翻页不退化） -->
      <div class="pagination-wrapper keyset" v-if="records.length > 0 || pagination.page > 1">
        <span class="pg-total">
          {{ totalApproximate ? '约 ' + pagination.total.toLocaleString() + ' 条' : '共 ' + pagination.total.toLocaleString() + ' 条' }}
        </span>
        <el-select v-model="pagination.pageSize" size="small" class="pg-size" @change="handleSizeChange">
          <el-option v-for="s in [20, 50, 100, 200]" :key="s" :label="s + ' 条/页'" :value="s" />
        </el-select>
        <el-button-group class="pg-nav">
          <el-button size="small" :disabled="!pageCursors.has_prev || loading" @click="goPrev">上一页</el-button>
          <el-button size="small" disabled>第 {{ pagination.page }} 页</el-button>
          <el-button size="small" :disabled="!pageCursors.has_next || loading" @click="goNext">下一页</el-button>
        </el-button-group>
      </div>
    </div>

    <!-- 下载对话框（仅管理员） -->
    <el-dialog v-model="exportVisible" :title="$t('smsRecords.exportTitle')" width="560px" class="export-dialog">
      <div class="export-body">
        <div class="export-row">
          <span class="export-label">{{ $t('smsRecords.exportFormat') }}</span>
          <el-radio-group v-model="exportForm.fmt">
            <el-radio-button value="csv">{{ $t('smsRecords.exportFormatCsv') }}</el-radio-button>
            <el-radio-button value="txt">{{ $t('smsRecords.exportFormatTxt') }}</el-radio-button>
          </el-radio-group>
        </div>
        <div class="export-row" v-if="exportForm.fmt === 'csv'">
          <span class="export-label">{{ $t('smsRecords.exportColumns') }}</span>
          <el-radio-group v-model="exportForm.columnMode">
            <el-radio-button value="visible">
              {{ $t('smsRecords.exportColumnsVisible', { n: visibleColumns.length }) }}
            </el-radio-button>
            <el-radio-button value="all">{{ $t('smsRecords.exportColumnsAll') }}</el-radio-button>
          </el-radio-group>
        </div>

        <div class="export-row">
          <span class="export-label">{{ $t('smsRecords.exportLimit') }}</span>
          <el-select v-model="exportForm.limit" style="width: 180px">
            <el-option
              v-for="n in [10000, 50000, 100000, 200000]"
              :key="n"
              :label="$t('smsRecords.exportRows', { n: n.toLocaleString() })"
              :value="n"
            />
          </el-select>
        </div>
        <div class="export-row export-scope">
          <span class="export-label">{{ $t('smsRecords.exportScope') }}</span>
          <div class="export-tags">
            <el-tag v-for="(tag, i) in exportSummary" :key="i" size="small" effect="plain">{{ tag }}</el-tag>
          </div>
        </div>
        <p class="export-hint">{{ $t('smsRecords.exportHint') }}</p>
      </div>
      <template #footer>
        <el-button @click="exportVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="exporting" @click="doExport">
          {{ exporting ? $t('smsRecords.exporting') : $t('smsRecords.exportConfirm') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 详情对话框 -->
    <el-dialog v-model="detailVisible" title="短信详情" width="640px" class="detail-dialog" destroy-on-close>
      <div class="detail-content" v-if="currentRecord">
        <!-- 状态横幅 -->
        <div class="status-banner" :class="currentRecord.status">
          <span class="status-badge lg" :class="currentRecord.status">{{ getStatusText(currentRecord.status) }}</span>
          <span class="status-time" v-if="currentRecord.sent_time">{{ formatTime(currentRecord.sent_time) }}</span>
        </div>

        <!-- 客户信息（仅管理员可见） -->
        <div class="detail-grid-3" v-if="isAdmin && (currentRecord.account_name || currentRecord.account_id)">
          <div class="detail-card">
            <span class="dc-label">客户账号</span>
            <span class="dc-value">{{ currentRecord.account_name || '-' }}</span>
          </div>
          <div class="detail-card">
            <span class="dc-label">客户ID</span>
            <span class="dc-value mono">{{ currentRecord.account_id }}</span>
          </div>
          <div class="detail-card" v-if="currentRecord.sales_name">
            <span class="dc-label">归属员工</span>
            <span class="dc-value">{{ currentRecord.sales_name }}</span>
          </div>
        </div>

        <div class="detail-grid-3">
          <div class="detail-card">
            <span class="dc-label">{{ $t('smsRecords.messageId') }}</span>
            <span class="dc-value mono">{{ currentRecord.message_id }}</span>
          </div>
          <div class="detail-card" v-if="currentRecord.upstream_message_id">
            <span class="dc-label">上游消息ID</span>
            <span class="dc-value mono">{{ currentRecord.upstream_message_id }}</span>
          </div>
          <div class="detail-card">
            <span class="dc-label">手机号码</span>
            <span class="dc-value">{{ currentRecord.phone_number }}</span>
          </div>
          <div class="detail-card">
            <span class="dc-label">{{ $t('smsRecords.country') }}</span>
            <span class="dc-value">{{ countryDisplay(currentRecord.country_code) }}</span>
          </div>
          <div class="detail-card" v-if="currentRecord.channel_code">
            <span class="dc-label">发送通道</span>
            <el-tag size="small" effect="plain">{{ currentRecord.channel_code }}</el-tag>
          </div>
          <div class="detail-card">
            <span class="dc-label">发送ID(SID)</span>
            <span class="dc-value mono">{{ currentRecord.sender_id || '默认' }}</span>
          </div>
          <div class="detail-card">
            <span class="dc-label">{{ $t('smsRecords.upstreamHandoffLabel') }}</span>
            <el-tooltip v-if="currentRecord.status === 'delivered'" placement="top" :content="$t('smsRecords.upstreamHandoffTipDelivered')">
              <el-tag size="small" type="success" effect="plain">{{ $t('smsStatus.delivered') }}</el-tag>
            </el-tooltip>
            <el-tooltip v-else-if="currentRecord.status === 'failed'" placement="top" :content="$t('smsRecords.upstreamHandoffTipFailed')">
              <el-tag size="small" type="danger" effect="plain">{{ $t('smsStatus.failed') }}</el-tag>
            </el-tooltip>
            <el-tooltip
              v-else-if="currentRecord.upstream_message_id"
              placement="top"
              :content="$t('smsRecords.upstreamHandoffTipAccepted')"
            >
              <el-tag size="small" type="info" effect="plain">{{ $t('smsRecords.upstreamAcceptedShort') }}</el-tag>
            </el-tooltip>
            <span v-else class="text-muted">-</span>
          </div>
          <div class="detail-card">
            <span class="dc-label">短信条数</span>
            <span class="dc-value">{{ currentRecord.message_count || 1 }}</span>
          </div>
        </div>

        <div class="detail-section">
          <h4 class="section-title">短信内容</h4>
          <div class="message-box">{{ currentRecord.message }}</div>
        </div>

        <div class="detail-section" v-if="isAdmin">
          <h4 class="section-title">费用信息</h4>
          <div class="detail-grid-3">
            <div class="detail-card">
              <span class="dc-label">售价</span>
              <span class="dc-value highlight">{{ currentRecord.selling_price?.toFixed(4) }} {{ currentRecord.currency }}</span>
            </div>
            <div class="detail-card">
              <span class="dc-label">成本</span>
              <span class="dc-value">{{ currentRecord.cost_price?.toFixed(4) }} {{ currentRecord.currency }}</span>
            </div>
            <div class="detail-card">
              <span class="dc-label">利润</span>
              <span class="dc-value" :class="currentRecord.profit >= 0 ? 'profit-positive' : 'profit-negative'">
                {{ currentRecord.profit?.toFixed(4) }} {{ currentRecord.currency }}
              </span>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <h4 class="section-title">时间线</h4>
          <div class="timeline">
            <div class="timeline-item active">
              <div class="tl-dot"></div>
              <div class="tl-content">
                <span class="tl-label">提交</span>
                <span class="tl-time">{{ formatTime(currentRecord.submit_time) }}</span>
              </div>
            </div>
            <div class="timeline-item" :class="{ active: currentRecord.sent_time }">
              <div class="tl-dot"></div>
              <div class="tl-content">
                <span class="tl-label">发送</span>
                <span class="tl-time">{{ formatTime(currentRecord.sent_time) || $t('common.waiting') }}</span>
              </div>
            </div>
            <div class="timeline-item" :class="{ active: currentRecord.delivery_time }">
              <div class="tl-dot"></div>
              <div class="tl-content">
                <span class="tl-label">送达</span>
                <span class="tl-time">{{ formatTime(currentRecord.delivery_time) || $t('common.waiting') }}</span>
              </div>
            </div>
          </div>
          <p v-if="showDlrExplainHint" class="dlr-explain-hint">{{ $t('smsRecords.dlrTerminalHint') }}</p>
        </div>

        <div class="detail-section" v-if="currentRecord.error_message && shouldShowErrorMessage(currentRecord)">
          <h4 class="section-title error-title">{{ $t('smsRecords.errorMsg') }}</h4>
          <div v-if="friendlyError(currentRecord.error_message)" class="error-explain">
            <el-alert :type="friendlyError(currentRecord.error_message).type" :closable="false" show-icon>
              <template #title>{{ friendlyError(currentRecord.error_message).title }}</template>
              <template #default>{{ friendlyError(currentRecord.error_message).desc }}</template>
            </el-alert>
          </div>
          <div class="error-box">{{ currentRecord.error_message }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download, Grid, Refresh, Search, View } from '@element-plus/icons-vue'
import { getSMSRecords, exportSMSRecords } from '@/api/sms'
import { getAccountsAdmin, getChannelsAdmin } from '@/api/admin'
import { getChannels } from '@/api/channel'
import { COUNTRY_LIST, findCountryByDial, findCountryByIso } from '@/constants/countries'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useFilterPersist } from '@/composables/useFilterPersist'
import MobileFilterDrawer from '@/components/MobileFilterDrawer.vue'

const { isMobile } = useBreakpoint()

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

/** 国家列/详情：支持电话国码(如 880)或 ISO(如 BD)，与后台 country_code 存储一致 */
function countryDisplay(code: string | null | undefined): string {
  if (!code) return '-'
  const raw = String(code).trim()
  const byDial = findCountryByDial(raw)
  if (byDial) return byDial.name
  const iso = raw.length <= 3 ? raw.toUpperCase() : raw
  const byIso = findCountryByIso(iso)
  if (byIso) return byIso.name
  return raw
}

// 国家筛选选项（按中文名排序）
const countryOptions = [...COUNTRY_LIST].sort((a, b) => a.name.localeCompare(b.name))
const loading = ref(false)
const detailVisible = ref(false)
const currentRecord = ref<any>(null)

const isAdmin = computed(() => {
  if (sessionStorage.getItem('impersonate_mode') === '1') return false
  return !!localStorage.getItem('admin_token')
})

const accounts = ref<any[]>([])
const channels = ref<any[]>([])

/** 本地日期 → YYYY-MM-DD（不能用 toISOString：那是 UTC，东八区凌晨会退成前一天） */
const toDateStr = (d: Date) => {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** 本周起点按周一（国内习惯），周日归到本周最后一天 */
const startOfWeek = (base: Date) => {
  const d = new Date(base)
  const offset = (d.getDay() + 6) % 7
  d.setDate(d.getDate() - offset)
  return d
}

const todayRange = (): [string, string] => {
  const d = toDateStr(new Date())
  return [d, d]
}

// 默认只看今天：sms_logs 千万级，默认拉 30 天窗口既慢又不是日常关注的范围
const dateRange = ref<string[] | null>(todayRange())

const searchForm = ref({
  phone_number: '',
  message_id: '',
  status: '',
  account_id: null as number | null,
  channel_id: null as number | null,
  country_code: '' as string,
  batch_id: null as number | null,
})

const pagination = ref({ page: 1, pageSize: 20, total: 0 })
// 全量浏览(无筛选)时后端返回优化器估算的近似总数，展示"约 N 条"
const totalApproximate = ref(false)
// 键集翻页游标：来自上次响应。pendingCursor 为本次请求要带的游标(消费一次即清空)
const pageCursors = ref<{ next_cursor: any; prev_cursor: any; has_next: boolean; has_prev: boolean }>(
  { next_cursor: null, prev_cursor: null, has_next: false, has_prev: false }
)
let pendingCursor: { time: string; id: number; direction: 'next' | 'prev' } | null = null
const records = ref<any[]>([])

/** 已生效的筛选项个数 — 用于移动端「筛选」按钮上的徽标 */
const activeFilterCount = computed(() => {
  const f = searchForm.value
  let n = 0
  if (f.phone_number) n++
  if (f.message_id) n++
  if (f.status) n++
  if (f.account_id) n++
  if (f.channel_id) n++
  if (f.country_code) n++
  if (f.batch_id) n++
  if (dateRange.value && dateRange.value.length === 2) n++
  return n
})

// ---------------- 显示列 ----------------
// 单一清单：表格列与导出列共用同一套 key 和顺序，"按显示列下载"才能严格一一对应。
// key 必须与后端 /sms/records/export?columns= 的白名单一致。
type ColumnDef = { key: string; label: string; labelEn: string; adminOnly?: boolean; default?: boolean }

const ALL_COLUMNS: ColumnDef[] = [
  { key: 'id', label: 'ID', labelEn: 'ID' },
  { key: 'account_name', label: '客户名称', labelEn: 'Customer', adminOnly: true, default: true },
  { key: 'account_id', label: '客户ID', labelEn: 'Customer ID', adminOnly: true },
  { key: 'sales_name', label: '归属员工', labelEn: 'Owner', adminOnly: true },
  { key: 'message_id', label: '消息ID', labelEn: 'Message ID', default: true },
  { key: 'upstream_message_id', label: '上游消息ID', labelEn: 'Upstream ID' },
  { key: 'batch_id', label: '任务ID', labelEn: 'Task ID' },
  { key: 'phone_number', label: '手机号码', labelEn: 'Phone', default: true },
  { key: 'country_code', label: '国家', labelEn: 'Country', default: true },
  { key: 'channel_code', label: '通道', labelEn: 'Channel', default: true },
  { key: 'sender_id', label: '发送ID(SID)', labelEn: 'Sender ID', default: true },
  { key: 'message', label: '内容', labelEn: 'Content', default: true },
  { key: 'message_count', label: '条数', labelEn: 'Parts' },
  { key: 'status', label: '状态', labelEn: 'Status', default: true },
  { key: 'status_code', label: '状态码', labelEn: 'Status code' },
  { key: 'error_message', label: '错误信息', labelEn: 'Error', default: true },
  { key: 'selling_price', label: '售价', labelEn: 'Price', default: true },
  { key: 'cost_price', label: '成本价', labelEn: 'Cost', adminOnly: true, default: true },
  { key: 'profit', label: '利润', labelEn: 'Profit', adminOnly: true },
  { key: 'currency', label: '币种', labelEn: 'Currency' },
  { key: 'submit_time', label: '提交时间', labelEn: 'Submitted', default: true },
  { key: 'sent_time', label: '发送时间', labelEn: 'Sent' },
  { key: 'delivery_time', label: '送达时间', labelEn: 'Delivered', default: true },
  { key: 'refunded_at', label: '退款时间', labelEn: 'Refunded', adminOnly: true },
]

const availableColumns = computed(() => ALL_COLUMNS.filter(c => isAdmin.value || !c.adminOnly))
const columnLabel = (c: ColumnDef) => (locale.value.startsWith('en') ? c.labelEn : c.label)
const defaultColumnKeys = () => availableColumns.value.filter(c => c.default).map(c => c.key)

const visibleColumns = ref<string[]>(defaultColumnKeys())
const colVisible = (key: string) => visibleColumns.value.includes(key)

const selectAllColumns = () => { visibleColumns.value = availableColumns.value.map(c => c.key) }
const resetColumns = () => { visibleColumns.value = defaultColumnKeys() }

// 列配置持久化（按账号隔离）。恢复时按清单过滤，避免旧配置里已下线的 key
// 或越权列（客户端拿到管理员列）残留。
const COLUMNS_STORAGE_KEY = `sms-records-columns:${localStorage.getItem('account_id') || 'anon'}`
try {
  const raw = localStorage.getItem(COLUMNS_STORAGE_KEY)
  if (raw) {
    const saved = JSON.parse(raw)
    if (Array.isArray(saved)) {
      const allowed = new Set(availableColumns.value.map(c => c.key))
      const restored = saved.filter((k: any) => typeof k === 'string' && allowed.has(k))
      if (restored.length) visibleColumns.value = restored
    }
  }
} catch { /* 存储不可用/JSON 坏掉：用默认列 */ }

watch(visibleColumns, (v) => {
  try {
    // 保持清单顺序，避免勾选先后打乱列序
    const order = ALL_COLUMNS.map(c => c.key)
    const sorted = [...v].sort((a, b) => order.indexOf(a) - order.indexOf(b))
    if (sorted.join(',') !== v.join(',')) {
      visibleColumns.value = sorted
      return
    }
    localStorage.setItem(COLUMNS_STORAGE_KEY, JSON.stringify(sorted))
  } catch { /* quota 等：忽略 */ }
}, { deep: true })

const statusCounts = computed(() => {
  const map: Record<string, number> = { sent: 0, delivered: 0, failed: 0, pending: 0, queued: 0, expired: 0 }
  records.value.forEach(r => { if (map[r.status] !== undefined) map[r.status]++ })
  return map
})

const statusOptions = computed(() => [
  { value: 'pending', label: t('smsStatus.pending') },
  { value: 'queued', label: t('smsStatus.queued') },
  { value: 'sent', label: t('smsStatus.sent') },
  { value: 'delivered', label: t('smsStatus.delivered') },
  { value: 'failed', label: t('smsStatus.failed') },
  { value: 'expired', label: t('smsStatus.expired') },
])

const dateShortcuts = computed(() => [
  { text: t('smsRecords.dateToday'), value: () => { const d = new Date(); return [d, d] } },
  { text: t('smsRecords.dateYesterday'), value: () => { const d = new Date(); d.setDate(d.getDate() - 1); return [d, d] } },
  { text: t('smsRecords.dateThisWeek'), value: () => [startOfWeek(new Date()), new Date()] },
  { text: t('smsRecords.dateThisMonth'), value: () => { const s = new Date(); s.setDate(1); return [s, new Date()] } },
  { text: t('smsRecords.dateLast7Days'), value: () => { const e = new Date(); const s = new Date(); s.setDate(s.getDate() - 6); return [s, e] } },
  { text: t('smsRecords.dateLast30Days'), value: () => { const e = new Date(); const s = new Date(); s.setDate(s.getDate() - 29); return [s, e] } },
])

const truncate = (s: string | null, n: number) => {
  if (!s) return '-'
  return s.length > n ? s.substring(0, n) + '...' : s
}

/** 已提交上游但尚无终端送达时间时，提示 DLR 与界面含义 */
const showDlrExplainHint = computed(() => {
  const r = currentRecord.value
  if (!r) return false
  return (
    (r.status === 'sent' || r.status === 'pending' || r.status === 'queued') &&
    !!r.sent_time &&
    !r.delivery_time
  )
})

const formatTime = (iso: string | null) => {
  if (!iso) return ''
  return iso.replace('T', ' ').substring(0, 19)
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    pending: t('smsStatus.pending'),
    queued: t('smsStatus.queued'),
    sent: t('smsStatus.sent'),
    delivered: t('smsStatus.delivered'),
    failed: t('smsStatus.failed'),
    expired: t('smsStatus.expired'),
  }
  return map[status] || status
}

const tableRowClassName = ({ row }: { row: any }) => {
  if (row.status === 'failed') return 'row-failed'
  if (row.status === 'expired') return 'row-expired'
  return ''
}

/** 仅筛选条件（不含分页/游标）：列表与导出共用，保证「下载的就是列表里筛出来的」 */
const buildFilterParams = () => {
  const params: any = {}
  if (searchForm.value.status) params.status = searchForm.value.status
  if (searchForm.value.phone_number) params.phone_number = searchForm.value.phone_number
  if (searchForm.value.message_id) params.message_id = searchForm.value.message_id
  if (isAdmin.value && searchForm.value.account_id) params.account_id = searchForm.value.account_id
  if (searchForm.value.channel_id) params.channel_id = searchForm.value.channel_id
  if (searchForm.value.country_code) params.country_code = searchForm.value.country_code
  if (searchForm.value.batch_id) params.batch_id = searchForm.value.batch_id
  if (dateRange.value && dateRange.value.length === 2) {
    params.start_date = dateRange.value[0]
    params.end_date = dateRange.value[1]
  }
  return params
}

const buildParams = () => {
  const params: any = { page_size: pagination.value.pageSize, ...buildFilterParams() }
  // 有待消费游标 → 键集翻页；否则按 page 偏移(首屏/筛选重置 page=1)
  if (pendingCursor) {
    params.cursor_time = pendingCursor.time
    params.cursor_id = pendingCursor.id
    params.direction = pendingCursor.direction
  } else {
    params.page = pagination.value.page
  }
  return params
}

const loadRecords = async () => {
  loading.value = true
  try {
    const res: any = await getSMSRecords(buildParams())
    if (res?.success) {
      records.value = res.records || []
      pagination.value.total = res.total || 0
      totalApproximate.value = !!res.total_approximate
      pageCursors.value = {
        next_cursor: res.next_cursor || null,
        prev_cursor: res.prev_cursor || null,
        has_next: !!res.has_next,
        has_prev: !!res.has_prev,
      }
    }
  } catch (error: any) {
    ElMessage.error('加载记录失败')
    records.value = []
  } finally {
    pendingCursor = null  // 游标消费完毕(无论成败)，避免卡死在某页
    loading.value = false
  }
}

// 筛选/重置/改每页数：回到首屏(偏移 page=1)，清空游标
const handleSearch = () => {
  pendingCursor = null
  pagination.value.page = 1
  loadRecords()
}

const handleSizeChange = () => {
  pendingCursor = null
  pagination.value.page = 1
  loadRecords()
}

const goNext = () => {
  if (!pageCursors.value.has_next || !pageCursors.value.next_cursor) return
  pendingCursor = { ...pageCursors.value.next_cursor, direction: 'next' }
  pagination.value.page += 1
  loadRecords()
}

const goPrev = () => {
  if (pagination.value.page <= 1) return
  if (pagination.value.page === 2) {
    // 回到第 1 页直接用偏移，保证与首屏完全一致
    handleSearch()
    return
  }
  if (!pageCursors.value.has_prev || !pageCursors.value.prev_cursor) return
  pendingCursor = { ...pageCursors.value.prev_cursor, direction: 'prev' }
  pagination.value.page -= 1
  loadRecords()
}

const handleReset = () => {
  searchForm.value = { phone_number: '', message_id: '', status: '', account_id: null, channel_id: null, country_code: '', batch_id: null }
  dateRange.value = todayRange()
  if (route.query.batch_id) {
    router.replace({ query: { ...route.query, batch_id: undefined } })
  }
  handleSearch()
}

// ---------------- 下载（仅管理员） ----------------
const exportVisible = ref(false)
const exporting = ref(false)
const exportForm = ref<{ fmt: string; limit: number; columnMode: string }>({
  fmt: 'csv',
  limit: 50000,
  columnMode: 'visible',
})

/** 弹窗里回显本次下载覆盖的筛选，避免「以为导全部、其实只导了某天」 */
const exportSummary = computed(() => {
  const f = searchForm.value
  const tags: string[] = []
  tags.push(
    dateRange.value && dateRange.value.length === 2
      ? `${dateRange.value[0]} ~ ${dateRange.value[1]}`
      : t('smsRecords.exportDefaultRange'),
  )
  if (f.account_id) {
    const acc = accounts.value.find((a: any) => a.id === f.account_id)
    tags.push(`${t('smsRecords.customerAccount')}: ${acc?.account_name || f.account_id}`)
  }
  if (f.status) tags.push(`${t('smsRecords.status')}: ${getStatusText(f.status)}`)
  if (f.channel_id) {
    const ch = channels.value.find((c: any) => c.id === f.channel_id)
    tags.push(`${t('smsRecords.channel')}: ${ch?.channel_code ?? ch?.code ?? f.channel_id}`)
  }
  if (f.country_code) tags.push(`${t('smsRecords.country')}: ${countryDisplay(f.country_code)}`)
  if (f.phone_number) tags.push(`${t('smsRecords.phoneNumber')}: ${f.phone_number}`)
  if (f.message_id) tags.push(`${t('smsRecords.messageId')}: ${f.message_id}`)
  if (f.batch_id) tags.push(`ID: ${f.batch_id}`)
  return tags
})

const openExport = () => {
  exportVisible.value = true
}

/** blob 响应下出错时，后端的 JSON detail 也在 blob 里，需读出来才能给出可读提示 */
const readBlobError = async (e: any): Promise<string> => {
  const data = e?.response?.data
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text())
      return parsed?.detail || parsed?.error?.message || ''
    } catch { /* 非 JSON：忽略 */ }
  }
  return data?.detail || ''
}

const doExport = async () => {
  exporting.value = true
  try {
    const params: any = {
      ...buildFilterParams(),
      fmt: exportForm.value.fmt,
      limit: exportForm.value.limit,
    }
    // 「按显示列」：把当前勾选的列（顺序即表格列序）交给后端，导出的表头与列表所见一致
    if (exportForm.value.fmt === 'csv' && exportForm.value.columnMode === 'visible') {
      params.columns = visibleColumns.value.join(',')
    }
    const blob = await exportSMSRecords(params)
    // txt 无数据时 body 为空；csv 至少有表头，不做空判断
    if (!blob || (exportForm.value.fmt === 'txt' && blob.size === 0)) {
      ElMessage.warning(t('smsRecords.exportEmpty'))
      return
    }
    const ts = toDateStr(new Date()).replace(/-/g, '') + '_' + new Date().toTimeString().slice(0, 8).replace(/:/g, '')
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `sms_records_${ts}.${exportForm.value.fmt}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(link.href)
    ElMessage.success(t('smsRecords.exportStarted'))
    exportVisible.value = false
  } catch (e: any) {
    ElMessage.error((await readBlobError(e)) || t('smsRecords.exportFailed'))
  } finally {
    exporting.value = false
  }
}

const handleViewDetail = (row: any) => {
  currentRecord.value = row
  detailVisible.value = true
}

/** 已送达却仍带历史「批次兜底/Worker」脏文案时不在界面展示，避免与成功状态矛盾（库中可能未清空 error_message） */
const STALE_SUCCESS_ERROR_PATTERNS = [
  /worker restart/i,
  /simulated task lost/i,
  /待发任务未完成调度/,
  /后台\s*worker\s*重启/,
]

const shouldShowErrorMessage = (row: { status?: string; error_message?: string | null }) => {
  const msg = (row.error_message || '').trim()
  if (!msg) return false
  if (row.status === 'delivered' && STALE_SUCCESS_ERROR_PATTERNS.some((re) => re.test(msg))) {
    return false
  }
  return true
}

const friendlyError = (msg: string | null | undefined): { title: string; desc: string; type: 'warning' | 'error' | 'info' } | null => {
  if (!msg) return null
  if (msg.includes('UNDELIV')) {
    return {
      type: 'warning',
      title: '运营商拒绝投递（UNDELIVERABLE）',
      desc: '短信已提交至运营商，但被目标运营商拒绝投递。常见原因：号码关机/停机、运营商内容过滤拦截、号码加入了免打扰名单(DND)、号码不存在或已注销。',
    }
  }
  if (msg.includes('REJECTD') || msg.includes('REJECTED')) {
    return {
      type: 'error',
      title: '运营商拒绝（REJECTED）',
      desc: '短信被运营商直接拒绝，未尝试投递。可能原因：发送内容违规、发送号码被列入黑名单、目标运营商策略限制。',
    }
  }
  if (msg.includes('EXPIRED')) {
    return {
      type: 'warning',
      title: '短信过期（EXPIRED）',
      desc: '短信在运营商网络中等待投递超时。通常因为接收方设备长时间不在线（关机/无信号）。',
    }
  }
  // 上游限流（ESME_RTHROTTLED=88）：通道瞬时拥塞，非号码问题。
  // 注意：UNDELIV/EXPIRED 等回执分支在前已 return，此处只会命中 SubmitSMResp 的 88。
  if (msg.includes('throttled') || /SMPP Error:\s*88(\b|\s|$)/.test(msg)) {
    return {
      type: 'warning',
      title: '通道繁忙（限流）',
      desc: '上游通道瞬时拥塞被限流，本条短信未发出。这是通道容量问题，与您的号码或内容无关，稍后重发即可。',
    }
  }
  if (msg.includes('different loop')) {
    return {
      type: 'error',
      title: '系统内部错误',
      desc: '发送过程中出现系统内部异常，该条短信未被发出。可联系管理员安排重发。',
    }
  }
  if (msg.includes('No available channel')) {
    return {
      type: 'error',
      title: '无可用通道',
      desc: '当前没有匹配该目标国家的可用发送通道，请联系管理员检查通道配置。',
    }
  }
  if (/SMPP.*提交被拒.*129/.test(msg)) {
    return {
      type: 'error',
      title: '无效目标号码',
      desc: '目标手机号码格式错误或不存在，请检查号码是否正确（含国家码）。',
    }
  }
  if (msg.includes('connection failed') || msg.includes('Connection') || msg.includes('timeout')) {
    return {
      type: 'error',
      title: '通道连接异常',
      desc: '与上游通道的网络连接失败或超时，系统会自动重试。若持续出现请联系管理员。',
    }
  }
  return null
}

const loadAccounts = async () => {
  if (!isAdmin.value) return
  try {
    const res: any = await getAccountsAdmin({ page: 1, page_size: 200 })
    accounts.value = res?.accounts || []
  } catch { /* ignore */ }
}

const loadChannels = async () => {
  try {
    if (isAdmin.value) {
      const res: any = await getChannelsAdmin()
      channels.value = (res?.channels || []).filter((c: any) => c.status === 'active')
    } else {
      const res: any = await getChannels()
      channels.value = res?.channels || []
    }
  } catch { /* ignore */ }
}

// 持久化筛选条件（按账号 ID 隔离，避免共用浏览器时串号）
// 日期范围刻意不持久化：进页面恒为「今日」，否则第二天打开还停在昨天那一天，
// 会被误读成「今天没量」。
useFilterPersist(`sms-records:${localStorage.getItem('account_id') || 'anon'}`, {
  searchForm,
})

onMounted(() => {
  // URL ?batch_id=... 优先级最高（来自"发送任务"页跳转），覆盖恢复的筛选
  const qBatchId = route.query.batch_id
  if (qBatchId) {
    const bid = Number(qBatchId)
    if (Number.isFinite(bid) && bid > 0) {
      searchForm.value.batch_id = bid
      // 按批次查逐条记录时放开日期：跨天的批次不能被「今日」默认挡掉
      dateRange.value = null
    }
  }
  loadAccounts()
  loadChannels()
  loadRecords()
})
</script>

<style scoped>
.records-page {
  width: 100%;
  animation: fadeIn 0.4s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 头部 */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
}
.header-content {
  flex: 1;
  min-width: 0;
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
.status-explain {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.55;
  margin: 10px 0 0;
  max-width: 920px;
  opacity: 0.92;
}
.header-actions {
  display: flex;
  gap: 10px;
}
.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid var(--border-default);
  background: var(--bg-input);
  color: var(--text-secondary);
}
.action-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 统计行 */
.stats-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.stat-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  font-size: 13px;
}
.stat-chip-label { color: var(--text-tertiary); }
.stat-chip-value { font-weight: 600; color: var(--text-primary); }
.stat-chip-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.stat-chip.sent .stat-chip-dot { background: var(--primary); }
.stat-chip.delivered .stat-chip-dot { background: var(--success); }
.stat-chip.failed .stat-chip-dot { background: var(--danger); }
.stat-chip.expired .stat-chip-dot { background: #909399; }

/* 筛选 */
.filter-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  padding: 18px 20px;
  margin-bottom: 16px;
}
.filter-content {
  display: flex;
  gap: 16px;
  align-items: flex-end;
  flex-wrap: wrap;
}
.filter-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 160px;
}
.filter-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-quaternary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
:deep(.filter-select .el-input__wrapper),
:deep(.filter-input .el-input__wrapper) {
  border-radius: 10px !important;
}
:deep(.filter-date) {
  --el-date-editor-width: 260px;
}
.status-option {
  display: flex;
  align-items: center;
  gap: 8px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.status-dot.pending { background: var(--info); }
.status-dot.queued { background: var(--warning); }
.status-dot.sent { background: var(--primary); }
.status-dot.delivered { background: var(--success); }
.status-dot.failed { background: var(--danger); }
.status-dot.expired { background: #909399; }
.filter-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}
.filter-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}
.filter-btn.search {
  background: linear-gradient(135deg, #2997FF 0%, #0071E3 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(41, 151, 255, 0.3);
}
.filter-btn.search:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(41, 151, 255, 0.4);
}
.filter-btn.reset {
  background: var(--bg-input);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

/* 表格 */
.table-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  overflow: hidden;
}
.table-wrapper {
  min-height: 300px;
}
:deep(.records-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: var(--bg-input);
  --el-table-border-color: var(--border-subtle);
}
:deep(.records-table .el-table__header th) {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-quaternary);
}
:deep(.records-table .el-table__row) {
  cursor: pointer;
  transition: background 0.15s;
}
:deep(.records-table .el-table__row:hover > td) {
  background: rgba(41, 151, 255, 0.04) !important;
}
:deep(.records-table .row-failed > td) {
  background: rgba(255, 69, 58, 0.03) !important;
}
.mono-text {
  font-family: 'SF Mono', Monaco, monospace;
  font-size: 12px;
  color: var(--text-tertiary);
}
.clickable { cursor: pointer; }
.phone-text { font-weight: 500; color: var(--text-primary); }
.account-cell { display: flex; flex-direction: column; gap: 2px; line-height: 1.3; }
.account-name-text { font-size: 13px; font-weight: 500; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sales-tag { font-size: 11px; color: var(--text-quaternary); }
.text-muted { color: var(--text-quaternary); font-size: 12px; }
.error-preview {
  color: var(--el-color-danger);
  font-size: 12px;
}
.error-preview-friendly {
  color: var(--el-color-warning-dark-2);
  font-size: 12px;
  font-weight: 500;
}
.message-preview {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-tertiary);
  font-size: 13px;
  max-width: 300px;
}
.status-badge {
  display: inline-flex;
  padding: 3px 10px;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 500;
}
.status-badge.pending { background: rgba(100, 210, 255, 0.15); color: var(--info); }
.status-badge.queued { background: rgba(255, 159, 10, 0.15); color: var(--warning); }
.status-badge.sent { background: rgba(41, 151, 255, 0.15); color: var(--primary); }
.status-badge.delivered { background: rgba(50, 215, 75, 0.15); color: var(--success); }
.status-badge.failed { background: rgba(255, 69, 58, 0.15); color: var(--danger); }
.status-badge.expired { background: rgba(144, 147, 153, 0.15); color: #909399; }
.status-badge.lg { font-size: 14px; padding: 6px 16px; }
.cost-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cost-selling { font-weight: 500; color: var(--text-primary); font-size: 13px; }
.cost-detail { font-size: 11px; color: var(--text-quaternary); }
.time-text { font-size: 13px; color: var(--text-tertiary); }
.detail-icon {
  cursor: pointer;
  color: var(--text-quaternary);
  font-size: 18px;
  transition: color 0.2s;
}
.detail-icon:hover { color: var(--primary); }

/* 分页 */
.pagination-wrapper {
  padding: 16px 20px;
  border-top: 1px solid var(--border-subtle);
  display: flex;
  justify-content: flex-end;
}
.pagination-wrapper.keyset {
  align-items: center;
  gap: 14px;
}
.pagination-wrapper.keyset .pg-total {
  color: var(--text-tertiary);
  font-size: 13px;
}
.pagination-wrapper.keyset .pg-size { width: 110px; }

/* 列设置 */
.action-btn .col-count {
  font-size: 12px;
  color: var(--text-quaternary);
  font-variant-numeric: tabular-nums;
}
.col-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 8px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}
.col-panel-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.col-panel-ops { display: flex; gap: 12px; }
.col-op {
  font-size: 12px;
  color: var(--primary);
  cursor: pointer;
}
.col-op:hover { text-decoration: underline; }
.col-list {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px 8px;
  max-height: 320px;
  overflow-y: auto;
}
.col-list :deep(.el-checkbox) {
  margin-right: 0;
  height: 28px;
}
.col-list :deep(.el-checkbox__label) {
  font-size: 13px;
  padding-left: 6px;
}

/* 下载弹窗 */
.export-body { display: flex; flex-direction: column; gap: 18px; }
.export-row { display: flex; align-items: center; gap: 14px; }
.export-row.export-scope { align-items: flex-start; }
.export-label {
  flex: 0 0 84px;
  font-size: 13px;
  color: var(--text-tertiary);
}
.export-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.export-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-quaternary);
}

/* 详情弹窗 */
.detail-content { padding: 0 4px; }
.status-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-radius: 12px;
  margin-bottom: 20px;
}
.status-banner.sent { background: rgba(41, 151, 255, 0.08); }
.status-banner.delivered { background: rgba(50, 215, 75, 0.08); }
.status-banner.failed { background: rgba(255, 69, 58, 0.08); }
.status-banner.pending { background: rgba(100, 210, 255, 0.08); }
.status-banner.queued { background: rgba(255, 159, 10, 0.08); }
.status-banner.expired { background: rgba(144, 147, 153, 0.08); }
.status-time { font-size: 13px; color: var(--text-tertiary); }

.detail-grid-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}
.detail-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: var(--bg-input);
  border-radius: 10px;
}
.dc-label { font-size: 11px; color: var(--text-quaternary); text-transform: uppercase; letter-spacing: 0.04em; }
.dc-value { font-size: 14px; font-weight: 500; color: var(--text-primary); word-break: break-all; }
.dc-value.mono { font-family: 'SF Mono', Monaco, monospace; font-size: 11px; }
.dc-value.highlight { color: var(--primary); font-weight: 600; }
.profit-positive { color: var(--success) !important; }
.profit-negative { color: var(--danger) !important; }

.detail-section { margin-bottom: 20px; }
.section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 12px;
}
.error-title { color: var(--danger); }
.message-box {
  background: var(--bg-input);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 14px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
}
.error-explain {
  margin-bottom: 10px;
}
.error-explain :deep(.el-alert__description) {
  font-size: 12px;
  line-height: 1.6;
  margin-top: 4px;
}
.error-box {
  background: rgba(255, 69, 58, 0.08);
  border: 1px solid rgba(255, 69, 58, 0.2);
  border-radius: 10px;
  padding: 14px;
  font-size: 12px;
  color: var(--danger);
  font-family: 'SF Mono', 'Fira Code', monospace;
  word-break: break-all;
}

/* 时间线 */
.timeline { display: flex; flex-direction: column; gap: 0; }
.timeline-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 0;
  position: relative;
}
.timeline-item::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 26px;
  bottom: -10px;
  width: 2px;
  background: var(--border-default);
}
.timeline-item:last-child::before { display: none; }
.tl-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--border-default);
  flex-shrink: 0;
  margin-top: 2px;
}
.timeline-item.active .tl-dot { background: var(--primary); box-shadow: 0 0 0 4px rgba(41, 151, 255, 0.15); }
.timeline-item.active::before { background: var(--primary); opacity: 0.3; }
.tl-content { display: flex; justify-content: space-between; flex: 1; }
.tl-label { font-size: 14px; font-weight: 500; color: var(--text-secondary); }
.tl-time { font-size: 13px; color: var(--text-tertiary); }
.timeline-item:not(.active) .tl-label { color: var(--text-quaternary); }
.timeline-item:not(.active) .tl-time { color: var(--text-quaternary); font-style: italic; }

.dlr-explain-hint {
  margin: 12px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-tertiary);
}

@media (max-width: 1024px) {
  .filter-content { flex-direction: column; align-items: stretch; }
  .filter-item { min-width: auto; }
  .filter-actions { margin-left: 0; }
  .detail-grid-3 { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 640px) {
  .page-header { flex-direction: column; gap: 12px; align-items: flex-start; }
  .stats-row { flex-direction: row; flex-wrap: wrap; gap: 8px; }
  .stat-chip { flex: 1 1 calc(50% - 4px); }
  .detail-grid-3 { grid-template-columns: 1fr; }
  .detail-dialog { width: 92vw !important; }
}

/* 移动端卡片列表 */
.mobile-card-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 4px;
  min-height: 200px;
}
.record-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  background: var(--bg-secondary, #fff);
  border: 1px solid var(--border-default, rgba(0,0,0,0.08));
  border-left: 3px solid var(--border-default, rgba(0,0,0,0.12));
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s, transform 0.05s;
}
.record-card:active { transform: scale(0.995); background: var(--bg-hover, rgba(0,0,0,0.04)); }
.record-card.delivered { border-left-color: #34b1a2; }
.record-card.sent      { border-left-color: #2f6df0; }
.record-card.failed    { border-left-color: #f56c6c; }
.record-card.expired   { border-left-color: #909399; }

.rc-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.rc-row-top .rc-phone {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #0a1425);
}
.rc-message {
  font-size: 13px;
  color: var(--text-secondary, #5f6c7c);
  line-height: 1.4;
  word-break: break-word;
}
.rc-row-meta {
  font-size: 12px;
  color: var(--text-tertiary, #8a96a6);
}
.rc-meta-item { display: inline-flex; align-items: center; gap: 6px; }
.rc-flag { font-size: 12px; }
.rc-time { font-variant-numeric: tabular-nums; }
.rc-row-bottom {
  font-size: 12px;
  color: var(--text-tertiary, #8a96a6);
  padding-top: 4px;
  border-top: 1px dashed var(--border-default, rgba(0,0,0,0.06));
}
.rc-account { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 60%; }
.rc-cost {
  font-family: 'SF Mono', 'Consolas', monospace;
  color: var(--text-primary, #0a1425);
  font-weight: 600;
}
.rc-error {
  font-size: 12px;
  color: #f56c6c;
  padding: 4px 8px;
  background: rgba(245, 108, 108, 0.08);
  border-radius: 6px;
}
.rc-empty {
  text-align: center;
  padding: 40px 16px;
  color: var(--text-tertiary, #8a96a6);
}

/* 移动端分页器精简：仅保留页码切换 */
@media (max-width: 768px) {
  .pagination-wrapper :deep(.el-pagination__sizes),
  .pagination-wrapper :deep(.el-pagination__jump) {
    display: none;
  }
  .pagination-wrapper :deep(.el-pagination) {
    flex-wrap: wrap;
    justify-content: center;
  }
}
</style>
