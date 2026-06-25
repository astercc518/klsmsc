<template>
<div class="dashboard">
    <!-- 顶部状态栏 -->
    <div class="dashboard-header">
      <div class="header-left">
        <h1 class="page-title">
          {{ getDashboardTitle() }}
        </h1>
        <span class="role-badge" :class="roleClass">{{ getRoleLabel() }}</span>
        <span class="last-update">{{ $t('dashboard.lastUpdate') }}: {{ lastUpdateTime }}</span>
        <!-- 构建戳：便于确认线上是否已部署含「关闭短信总览」的前端包；强刷或禁用 CDN 缓存 index.html 后应对更新 -->
        <span v-if="isStaff && !showStaffSmsOverview" class="build-stamp">{{ appBuildStamp }}</span>
      </div>
      <div class="header-right">
        <button class="refresh-btn" @click="refreshData" :disabled="loading">
          <svg :class="{ spinning: loading }" width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M14 8C14 11.3137 11.3137 14 8 14C4.68629 14 2 11.3137 2 8C2 4.68629 4.68629 2 8 2C10.5 2 12.5 3.5 13.5 5.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M11 5.5H14V2.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          {{ $t('dashboard.refreshData') }}
        </button>
      </div>
    </div>

    <!-- ========== 管理员/员工视图 ========== -->
      <!-- 核心指标 hero 卡（新版仪表盘） -->
      <div class="hero-grid">
        <div class="hero-card soft-card animate-scale" v-if="permissions.view_finance" style="animation-delay: 0.05s">
          <div class="hero-icon balance">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <rect x="2.5" y="5" width="19" height="14" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
              <path d="M2.5 9.5H21.5" stroke="currentColor" stroke-width="1.8"/>
              <circle cx="17" cy="14.5" r="1.2" fill="currentColor"/>
            </svg>
          </div>
          <div class="hero-meta">
            <span class="hero-label">{{ $t('dashboard.systemBalance') }}</span>
            <span class="hero-value"><span class="hero-cur">$</span>{{ formatNumber(totalBalance) }}</span>
          </div>
        </div>
        <div class="hero-card soft-card animate-scale" v-if="permissions.view_finance" style="animation-delay: 0.1s">
          <div class="hero-icon cost">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8"/>
              <path d="M14.5 9.2C14.5 8 13.3 7.2 12 7.2C10.7 7.2 9.5 8 9.5 9.3C9.5 12 14.5 11 14.5 14C14.5 15.3 13.3 16.2 12 16.2C10.7 16.2 9.5 15.3 9.5 14M12 6V7.2M12 16.2V18" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
            </svg>
          </div>
          <div class="hero-meta">
            <span class="hero-label">{{ $t('dashboard.todayCost') }}</span>
            <span class="hero-value"><span class="hero-cur">$</span>{{ formatNumber(todayCost) }}</span>
          </div>
        </div>
        <div class="hero-card soft-card animate-scale" v-if="permissions.view_channels" style="animation-delay: 0.15s">
          <div class="hero-icon channels">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <circle cx="6" cy="12" r="3" stroke="currentColor" stroke-width="1.8"/>
              <circle cx="18" cy="6" r="3" stroke="currentColor" stroke-width="1.8"/>
              <circle cx="18" cy="18" r="3" stroke="currentColor" stroke-width="1.8"/>
              <path d="M9 12H15M15 6L9 12M15 18L9 12" stroke="currentColor" stroke-width="1.8"/>
            </svg>
          </div>
          <div class="hero-meta">
            <span class="hero-label">{{ $t('dashboard.activeChannels') }}</span>
            <span class="hero-value">{{ formatNumber(availableChannels) }}</span>
          </div>
        </div>
        <div class="hero-card soft-card animate-scale" v-if="permissions.view_customers" style="animation-delay: 0.2s">
          <div class="hero-icon customers">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="8" r="3.4" stroke="currentColor" stroke-width="1.8"/>
              <path d="M5 19C5 15.7 8.1 13.4 12 13.4C15.9 13.4 19 15.7 19 19" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            </svg>
          </div>
          <div class="hero-meta">
            <span class="hero-label">{{ isSales ? $t('dashboard.myCustomers') : $t('dashboard.activeCustomers') }}</span>
            <span class="hero-value">{{ formatNumber(activeAccounts) }}</span>
          </div>
        </div>
      </div>

      <!-- 业绩概览 -->
      <div class="card perf-card soft-card">
        <div class="card-header">
          <h2 class="card-title">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M2 14L6 9L10 11L16 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M12 4H16V8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            {{ $t('dashboard.performanceOverview') }}
          </h2>
          <div class="period-tabs">
            <button
              v-for="p in periodOptions"
              :key="p.key"
              type="button"
              class="period-tab"
              :class="{ active: perfPeriod === p.key }"
              @click="perfPeriod = p.key"
            >{{ p.label }}</button>
          </div>
        </div>
        <div class="perf-body">
          <div class="perf-metrics">
            <div class="perf-metric">
              <span class="perf-metric-label">{{ $t('dashboard.sent') }}</span>
              <span class="perf-metric-value">{{ formatNumber(currentPerf.sent) }}<i class="perf-unit">{{ $t('dashboard.items') }}</i></span>
            </div>
            <div class="perf-metric" v-if="permissions.view_finance">
              <span class="perf-metric-label">{{ $t('dashboard.revenue') }}</span>
              <span class="perf-metric-value money"><span class="perf-cur">$</span>{{ formatNumber(currentPerf.revenue) }}</span>
            </div>
            <div class="perf-metric" v-if="permissions.view_finance">
              <span class="perf-metric-label">{{ $t('dashboard.cost') }}</span>
              <span class="perf-metric-value"><span class="perf-cur">$</span>{{ formatNumber(currentPerf.cost) }}</span>
            </div>
            <div class="perf-metric" v-if="permissions.view_finance">
              <span class="perf-metric-label">{{ $t('dashboard.profit') }}</span>
              <span class="perf-metric-value profit" :class="{ positive: currentPerf.profit > 0 }"><span class="perf-cur">$</span>{{ formatNumber(currentPerf.profit) }}</span>
            </div>
          </div>
          <div class="perf-spark">
            <div class="perf-spark-head">
              <span class="perf-spark-title">{{ $t('dashboard.last7days') }}</span>
              <a class="perf-detail-link" @click="$router.push('/reports')" v-if="permissions.view_finance || permissions.view_global">{{ $t('dashboard.viewMore') }} →</a>
            </div>
            <svg v-if="sparkPath" class="spark-svg" :viewBox="`0 0 ${SPARK_W} ${SPARK_H}`" preserveAspectRatio="none">
              <defs>
                <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="rgba(102,126,234,0.35)"/>
                  <stop offset="100%" stop-color="rgba(102,126,234,0)"/>
                </linearGradient>
              </defs>
              <path :d="sparkArea" fill="url(#sparkFill)" stroke="none"/>
              <path :d="sparkPath" fill="none" stroke="var(--primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <div v-else class="spark-empty">{{ $t('dashboard.noData') }}</div>
          </div>
        </div>
      </div>

<!-- 核心指标卡片 - 管理员（showStaffSmsOverview 为 false 时不展示） -->
      <div
        v-if="showStaffSmsOverview"
        class="metrics-grid"
        :class="{ 'metrics-6': permissions.view_finance }"
      >
        <!-- 今日发送 -->
        <div class="metric-card soft-card soft-card-hover animate-scale" style="animation-delay: 0.1s">
          <div class="metric-header">
            <div class="metric-icon sent">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M18 2L9 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                <path d="M18 2L12 18L9 11L2 8L18 2Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
              </svg>
            </div>
            <span class="metric-label">{{ $t('dashboard.todaySent') }}</span>
          </div>
          <div class="metric-body">
            <span class="metric-value">{{ formatNumber(todaySent) }}</span>
            <span class="metric-unit">{{ $t('dashboard.items') }}</span>
          </div>
          <div class="metric-footer" v-if="yesterdayStats.sent > 0 || todaySent > 0">
            <span :class="['metric-change', sentChange.dir]">{{ sentChange.pct }}%</span>
          </div>
        </div>

        <!-- 送达成功 -->
        <div class="metric-card soft-card soft-card-hover animate-scale" style="animation-delay: 0.2s">
          <div class="metric-header">
            <div class="metric-icon success">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5"/>
                <path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
            <span class="metric-label">{{ $t('dashboard.delivered') }}</span>
          </div>
          <div class="metric-body">
            <span class="metric-value">{{ formatNumber(todayDelivered) }}</span>
            <span class="metric-unit">{{ $t('dashboard.items') }}</span>
          </div>
          <div class="metric-footer">
            <span class="metric-rate success">{{ formatRate(successRate) }}%</span>
          </div>
        </div>

        <!-- 发送失败 -->
        <div class="metric-card soft-card soft-card-hover animate-scale" style="animation-delay: 0.3s">
          <div class="metric-header">
            <div class="metric-icon failed">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5"/>
                <path d="M8 8L12 12M12 8L8 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
            </div>
            <span class="metric-label">{{ $t('dashboard.failed') }}</span>
          </div>
          <div class="metric-body">
            <span class="metric-value">{{ formatNumber(todayFailed) }}</span>
            <span class="metric-unit">{{ $t('dashboard.items') }}</span>
          </div>
          <div class="metric-footer">
            <span class="metric-rate failed">{{ formatRate(failRate) }}%</span>
          </div>
        </div>

        <!-- 活跃客户 (销售/管理员) -->
        <div class="metric-card soft-card soft-card-hover animate-scale" v-if="permissions.view_customers" style="animation-delay: 0.4s">
          <div class="metric-header">
            <div class="metric-icon customers">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <circle cx="10" cy="6" r="3" stroke="currentColor" stroke-width="1.5"/>
                <path d="M4 17C4 14 6.5 12 10 12C13.5 12 16 14 16 17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
            </div>
            <span class="metric-label">{{ isSales ? $t('dashboard.myCustomers') : $t('dashboard.activeCustomers') }}</span>
          </div>
          <div class="metric-body">
            <span class="metric-value">{{ formatNumber(activeAccounts) }}</span>
            <span class="metric-unit">{{ $t('dashboard.units') }}</span>
          </div>
        </div>

        <!-- 今日收入 (财务可见) -->
        <div class="metric-card soft-card soft-card-hover animate-scale" v-if="permissions.view_finance" style="animation-delay: 0.5s">
          <div class="metric-header">
            <div class="metric-icon revenue">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M10 2V18M14 6H8C6.34 6 5 7.34 5 9C5 10.66 6.34 12 8 12H12C13.66 12 15 13.34 15 15C15 16.66 13.66 18 12 18H6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
            </div>
            <span class="metric-label">{{ $t('dashboard.todayRevenue') }}</span>
          </div>
          <div class="metric-body">
            <span class="metric-currency">$</span>
            <span class="metric-value">{{ formatNumber(todayRevenue) }}</span>
          </div>
        </div>

        <!-- 今日利润 (财务可见) -->
        <div class="metric-card profit soft-card soft-card-hover animate-scale" v-if="permissions.view_finance" style="animation-delay: 0.6s">
          <div class="metric-header">
            <div class="metric-icon profit">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M3 17L8 12L11 15L17 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M13 9H17V13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
            <span class="metric-label">{{ $t('dashboard.todayProfit') }}</span>
          </div>
          <div class="metric-body">
            <span class="metric-currency">$</span>
            <span class="metric-value" :class="{ positive: todayProfit > 0 }">{{ formatNumber(todayProfit) }}</span>
          </div>
        </div>
      </div>

      <!-- 服务器性能与服务状态（超级管理员 / 管理员 / 运维） -->
      <div class="system-monitor-row" v-if="showSystemMonitor">
        <div class="card server-health-card soft-card">
          <div class="card-header">
            <h2 class="card-title">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <rect x="2" y="3" width="14" height="11" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
                <path d="M5 14H13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                <path d="M7 6H11M7 9H11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
              {{ $t('dashboard.serverPerformance') }}
            </h2>
          </div>
          <div class="server-health-body">
            <template v-if="serverMetrics && !serverMetrics.error">
              <p v-if="serverMetrics.hostname" class="host-line">
                <span class="host-label">{{ $t('dashboard.hostName') }}</span>
                <span class="host-value">{{ serverMetrics.hostname }}</span>
              </p>
              <div class="perf-row">
                <div class="perf-label-row">
                  <span>{{ $t('dashboard.cpuUsage') }}</span>
                  <span class="perf-pct">{{ formatRate(Number(serverMetrics.cpu_percent) || 0) }}%</span>
                </div>
                <div class="perf-bar-track">
                  <div
                    class="perf-bar-fill cpu"
                    :style="{ width: `${Math.min(100, Number(serverMetrics.cpu_percent) || 0)}%` }"
                  />
                </div>
              </div>
              <div class="perf-row">
                <div class="perf-label-row">
                  <span>{{ $t('dashboard.memoryUsage') }}</span>
                  <span class="perf-pct">{{ formatRate(Number(serverMetrics.memory_percent) || 0) }}%</span>
                </div>
                <div class="perf-bar-track">
                  <div
                    class="perf-bar-fill memory"
                    :style="{ width: `${Math.min(100, Number(serverMetrics.memory_percent) || 0)}%` }"
                  />
                </div>
                <p class="perf-sub">
                  {{ formatNumber(Number(serverMetrics.memory_used_gb) || 0) }} / {{ formatNumber(Number(serverMetrics.memory_total_gb) || 0) }} GB
                </p>
              </div>
              <div class="perf-row">
                <div class="perf-label-row">
                  <span>{{ $t('dashboard.diskUsage') }}</span>
                  <span class="perf-pct">{{ formatRate(Number(serverMetrics.disk_percent) || 0) }}%</span>
                </div>
                <div class="perf-bar-track">
                  <div
                    class="perf-bar-fill disk"
                    :style="{ width: `${Math.min(100, Number(serverMetrics.disk_percent) || 0)}%` }"
                  />
                </div>
                <p class="perf-sub">
                  {{ $t('dashboard.diskFree') }}: {{ formatNumber(Number(serverMetrics.disk_free_gb) || 0) }} GB
                  / {{ formatNumber(Number(serverMetrics.disk_total_gb) || 0) }} GB
                </p>
              </div>
              <p v-if="serverMetrics.load_avg && serverMetrics.load_avg.length" class="load-line">
                {{ $t('dashboard.loadAvg') }}: {{ serverMetrics.load_avg.map((n) => Number(n).toFixed(2)).join(' / ') }}
              </p>
            </template>
            <div v-else-if="serverMetrics && serverMetrics.error" class="metrics-error">{{ serverMetrics.error }}</div>
            <div v-else-if="dashboardLoading" class="empty-state subtle">{{ $t('common.loading') }}</div>
            <div v-else class="empty-state subtle">{{ $t('dashboard.systemMonitorNoBackend') }}</div>
          </div>
        </div>
        <!-- 今日各国发送 Top -->
        <div class="card country-top-card soft-card">
          <div class="card-header">
            <h2 class="card-title">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="7" stroke="currentColor" stroke-width="1.5"/>
                <path d="M2 9H16M9 2C11 4.5 11 13.5 9 16C7 13.5 7 4.5 9 2Z" stroke="currentColor" stroke-width="1.3"/>
              </svg>
              {{ $t('dashboard.topCountries') }}
            </h2>
          </div>
          <div class="ch-stats-list">
            <div v-if="dashboardLoading && !topCountries.length" class="empty-state subtle">{{ $t('common.loading') }}</div>
            <div v-else-if="!topCountries.length" class="empty-state subtle">{{ $t('dashboard.noActivityToday') }}</div>
            <div v-else v-for="c in topCountries" :key="c.country_code" class="ch-stat-row">
              <span class="ch-stat-name">{{ c.country_code }}</span>
              <div class="ch-stat-bar-wrap">
                <div class="ch-stat-bar" :class="c.rate >= 90 ? 'good' : c.rate >= 60 ? 'warn' : 'bad'" :style="{ width: `${c.rate}%` }"></div>
              </div>
              <span class="ch-stat-pct">{{ c.rate }}%</span>
              <span class="ch-stat-cnt">{{ c.sent.toLocaleString() }}{{ $t('dashboard.items') }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 日环比指示器（嵌入指标卡片下方） -->
      <div class="compare-row" v-if="showStaffSmsOverview && (yesterdayStats.sent > 0 || todaySent > 0)">
        <div class="compare-chip" :class="sentChange.dir">
          <span class="compare-label">{{ $t('dashboard.todaySent') }}</span>
          <span class="compare-val">{{ sentChange.pct }}%</span>
          <span class="compare-hint">{{ $t('dashboard.yesterdayCompare') }}</span>
        </div>
        <div class="compare-chip" :class="deliveredChange.dir">
          <span class="compare-label">{{ $t('dashboard.delivered') }}</span>
          <span class="compare-val">{{ deliveredChange.pct }}%</span>
          <span class="compare-hint">{{ $t('dashboard.yesterdayCompare') }}</span>
        </div>
        <div class="compare-chip" :class="revenueChange.dir" v-if="permissions.view_finance">
          <span class="compare-label">{{ $t('dashboard.todayRevenue') }}</span>
          <span class="compare-val">{{ revenueChange.pct }}%</span>
          <span class="compare-hint">{{ $t('dashboard.yesterdayCompare') }}</span>
        </div>
      </div>

      <!-- 数据可视化行 -->
      <div class="viz-row" v-if="showStaffSmsOverview && (dailyTrend.length > 0 || topCustomers.length > 0)">
        <!-- 7日发送趋势 -->
        <div class="card trend-card soft-card" v-if="dailyTrend.length > 0">
          <div class="card-header">
            <h2 class="card-title">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M2 14L6 9L10 11L16 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M12 4H16V8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              {{ $t('dashboard.dailyTrend') }}
            </h2>
          </div>
          <div class="trend-chart">
            <div class="trend-bars">
              <div
                v-for="day in dailyTrend"
                :key="day.date"
                class="trend-bar-group"
              >
                <div class="trend-bar-wrapper">
                  <div
                    class="trend-bar sent-bar"
                    :style="{ height: `${Math.max(4, day.sent / trendMaxSent * 100)}%` }"
                  >
                    <span class="trend-bar-tooltip">{{ day.sent.toLocaleString() }}</span>
                  </div>
                  <div
                    class="trend-bar delivered-bar"
                    :style="{ height: `${Math.max(2, day.delivered / trendMaxSent * 100)}%` }"
                  />
                </div>
                <span class="trend-date">{{ day.date.slice(5) }}</span>
              </div>
            </div>
            <div class="trend-legend">
              <span class="legend-item"><span class="legend-dot sent"></span>{{ $t('dashboard.sent') }}</span>
              <span class="legend-item"><span class="legend-dot delivered"></span>{{ $t('dashboard.deliveredCount') }}</span>
            </div>
          </div>
        </div>

        <!-- 客户发送 TOP -->
        <div class="card top-card soft-card" v-if="topCustomers.length > 0 && (permissions.view_customers || permissions.view_global)">
          <div class="card-header">
            <h2 class="card-title">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M9 2L11.5 7H15L12 10L13 15L9 12L5 15L6 10L3 7H6.5L9 2Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
              </svg>
              {{ $t('dashboard.topCustomers') }}
            </h2>
          </div>
          <div class="top-list">
            <div
              v-for="(cust, idx) in topCustomers"
              :key="cust.account_name"
              class="top-item"
            >
              <span class="top-rank" :class="{ gold: idx === 0, silver: idx === 1, bronze: idx === 2 }">{{ idx + 1 }}</span>
              <span class="top-name">{{ cust.account_name }}</span>
              <span class="top-sent">{{ cust.sent.toLocaleString() }}</span>
              <span class="top-rate" v-if="cust.sent > 0">{{ ((cust.delivered / cust.sent) * 100).toFixed(1) }}%</span>
              <span class="top-revenue" v-if="permissions.view_finance">${{ formatNumber(cust.revenue) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 批次 & 通道统计行 -->
      <div class="viz-row" v-if="showStaffSmsOverview && (batchOverview.total > 0 || channelStats.length > 0)">
        <!-- 批次概览 -->
        <div class="card batch-card soft-card" v-if="batchOverview.total > 0">
          <div class="card-header">
            <h2 class="card-title">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <rect x="3" y="2" width="12" height="14" rx="2" stroke="currentColor" stroke-width="1.5"/>
                <path d="M6 6H12M6 9H12M6 12H9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
              {{ $t('dashboard.batchOverview') }}
            </h2>
          </div>
          <div class="batch-stats">
            <div class="batch-stat-item total">
              <span class="batch-num">{{ batchOverview.total }}</span>
              <span class="batch-label">{{ $t('dashboard.totalBatches') }}</span>
            </div>
            <div class="batch-stat-item processing" v-if="batchOverview.processing > 0">
              <span class="batch-num">{{ batchOverview.processing }}</span>
              <span class="batch-label">{{ $t('dashboard.processingBatches') }}</span>
            </div>
            <div class="batch-stat-item completed">
              <span class="batch-num">{{ batchOverview.completed }}</span>
              <span class="batch-label">{{ $t('dashboard.completedBatches') }}</span>
            </div>
            <div class="batch-stat-item failed" v-if="batchOverview.failed > 0">
              <span class="batch-num">{{ batchOverview.failed }}</span>
              <span class="batch-label">{{ $t('dashboard.failedBatches') }}</span>
            </div>
          </div>
        </div>

        <!-- 通道发送统计 -->
        <div class="card channel-stats-card soft-card" v-if="channelStats.length > 0">
          <div class="card-header">
            <h2 class="card-title">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="5" cy="9" r="2.5" stroke="currentColor" stroke-width="1.5"/>
                <circle cx="13" cy="5" r="2.5" stroke="currentColor" stroke-width="1.5"/>
                <circle cx="13" cy="13" r="2.5" stroke="currentColor" stroke-width="1.5"/>
                <path d="M7.5 9H10.5M10.5 5L7.5 9M10.5 13L7.5 9" stroke="currentColor" stroke-width="1.5"/>
              </svg>
              {{ $t('dashboard.channelPerformance') }}
            </h2>
          </div>
          <div class="ch-stats-list">
            <div
              v-for="ch in channelStats"
              :key="ch.channel_name"
              class="ch-stat-row"
            >
              <span class="ch-stat-name">{{ ch.channel_name }}</span>
              <div class="ch-stat-bar-wrap">
                <div class="ch-stat-bar" :style="{ width: `${ch.rate}%` }" :class="ch.rate >= 90 ? 'good' : ch.rate >= 60 ? 'warn' : 'bad'"></div>
              </div>
              <span class="ch-stat-pct">{{ ch.rate }}%</span>
              <span class="ch-stat-cnt">{{ ch.sent.toLocaleString() }}{{ $t('dashboard.items') }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 主内容区 - 管理员 -->
      <div class="content-grid admin-grid">
        <!-- 左侧 -->
        <div class="content-left">
          <!-- 异常 / 进行中批次 -->
          <div class="card active-batch-card" v-if="permissions.view_global || permissions.view_channels || isSales">
            <div class="card-header">
              <h2 class="card-title">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <path d="M9 2L16 14H2L9 2Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
                  <path d="M9 7V10M9 12V12.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                </svg>
                {{ $t('dashboard.activeBatches') }}
              </h2>
              <button class="view-all-btn" @click="$router.push('/admin/sms/tasks')">
                {{ $t('dashboard.viewAllTasks') }}
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M5 3L9 7L5 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
            </div>
            <div class="active-batch-list">
              <div v-if="!activeBatches.length" class="empty-state"><span>{{ $t('dashboard.activeBatchesEmpty') }}</span></div>
              <div
                v-else
                v-for="b in activeBatches"
                :key="b.id"
                class="active-batch-item"
                @click="$router.push('/admin/sms/tasks')"
              >
                <span class="ab-status" :class="b.status">{{ batchStatusText(b.status) }}</span>
                <span class="ab-name">#{{ b.id }} {{ b.batch_name }}</span>
                <span class="ab-acct">{{ b.account_name }}</span>
                <span class="ab-progress">{{ b.progress }}%</span>
              </div>
            </div>
          </div>

          <!-- 通道送达率异常榜 -->
          <div class="card ch-worst-card" v-if="permissions.view_channels && worstChannels.length > 0">
            <div class="card-header">
              <h2 class="card-title">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <path d="M2 4L7 9L10 6L16 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M16 8V12H12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                {{ $t('dashboard.worstChannels') }}
              </h2>
            </div>
            <div class="ch-stats-list">
              <div v-for="ch in worstChannels" :key="ch.channel_name" class="ch-stat-row">
                <span class="ch-stat-name">{{ ch.channel_name }}</span>
                <div class="ch-stat-bar-wrap">
                  <div class="ch-stat-bar" :class="ch.rate >= 90 ? 'good' : ch.rate >= 60 ? 'warn' : 'bad'" :style="{ width: `${ch.rate}%` }"></div>
                </div>
                <span class="ch-stat-pct">{{ ch.rate }}%</span>
                <span class="ch-stat-cnt">{{ ch.sent.toLocaleString() }}{{ $t('dashboard.items') }}</span>
              </div>
            </div>
          </div>
        </div>


        <!-- 右侧 -->
        <div class="content-right">
          <!-- 我的客户 (销售专属) -->
          <div class="card customers-card" v-if="isSales && recentCustomers.length > 0">
            <div class="card-header">
              <h2 class="card-title">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <circle cx="9" cy="5" r="3" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M3 16C3 13 5.5 11 9 11C12.5 11 15 13 15 16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
                {{ $t('dashboard.myCustomers') }}
              </h2>
              <button class="view-all-btn" @click="$router.push('/admin/accounts')">
                {{ $t('dashboard.viewAll') }}
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M5 3L9 7L5 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
            </div>
            <div class="customers-list">
              <div 
                v-for="customer in recentCustomers" 
                :key="customer.id" 
                class="customer-item"
              >
                <div class="customer-info">
                  <span class="customer-name">{{ customer.account_name }}</span>
                  <span :class="['customer-status', customer.status]">
                    {{ customer.status === 'active' ? $t('common.active') : $t('common.inactive') }}
                  </span>
                </div>
                <div class="customer-meta">
                  <span class="customer-balance">${{ formatNumber(customer.balance) }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 客户动态 (今日发送客户) -->
          <div class="card activity-card" v-if="permissions.view_customers || permissions.view_global">
            <div class="card-header">
              <h2 class="card-title">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <path d="M2 9H5L7 4L11 14L13 9H16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                {{ $t('dashboard.customerActivity') }}
              </h2>
              <button class="view-all-btn" @click="$router.push('/admin/accounts')" v-if="permissions.view_customers">
                {{ $t('dashboard.viewAll') }}
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M5 3L9 7L5 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
            </div>
            <div class="activity-list">
              <div v-if="topCustomers.length === 0" class="empty-state">
                <span>{{ $t('dashboard.noActivityToday') }}</span>
              </div>
              <div
                v-else
                v-for="(cust, idx) in topCustomers.slice(0, 6)"
                :key="cust.account_name"
                class="activity-item"
              >
                <span class="activity-rank" :class="{ gold: idx === 0, silver: idx === 1, bronze: idx === 2 }">{{ idx + 1 }}</span>
                <span class="activity-name">{{ cust.account_name }}</span>
                <span class="activity-rate" v-if="cust.sent > 0">{{ ((cust.delivered / cust.sent) * 100).toFixed(0) }}%</span>
                <span class="activity-sent">{{ cust.sent.toLocaleString() }}{{ $t('dashboard.items') }}</span>
              </div>
            </div>
          </div>

          <!-- 余额不足客户预警 -->
          <div class="card low-balance-card" v-if="permissions.view_global || isSales">
            <div class="card-header">
              <h2 class="card-title">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <rect x="2" y="4" width="14" height="10" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M2 7H16" stroke="currentColor" stroke-width="1.5"/>
                  <circle cx="12.5" cy="10.5" r="1" fill="currentColor"/>
                </svg>
                {{ $t('dashboard.lowBalanceAlert') }}
              </h2>
              <span class="channel-count alert" v-if="lowBalanceAccounts.length">{{ lowBalanceAccounts.length }}</span>
            </div>
            <div class="lowbal-list">
              <div v-if="!lowBalanceAccounts.length" class="empty-state"><span>{{ $t('dashboard.lowBalanceEmpty') }}</span></div>
              <div
                v-else
                v-for="a in lowBalanceAccounts"
                :key="a.id"
                class="lowbal-item"
                @click="$router.push('/admin/accounts')"
              >
                <span class="lowbal-name">{{ a.account_name }}</span>
                <span class="lowbal-bal" :class="{ neg: a.balance <= 0 }">{{ a.currency }} {{ formatNumber(a.balance) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
</template>

<script setup lang='ts'>

import { ref, onMounted, computed, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getAccountInfo, type AccountInfo } from '@/api/account'
import { getChannels } from '@/api/channel'
import { getStatistics } from '@/api/reports'
import { getAdminDashboard, type AdminServerMetrics, type AdminServiceStatusItem } from '@/api/admin'
import { getSMSRecords } from '@/api/sms'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

/**
 * 员工视图：是否展示短信运营总览（顶部 KPI、日环比、7 日趋势、客户 TOP、批次与通道统计）。
 * 固定为 false；若需恢复展示，改为 true 后重新构建并部署前端。
 */
const showStaffSmsOverview = false

/** 与 vite.config define 一致，用于页头展示以核对部署版本 */
const appBuildStamp = typeof __APP_BUILD_STAMP__ !== 'undefined' ? __APP_BUILD_STAMP__ : ''

const loading = ref(false)
const balance = ref<number>(0)
const todaySent = ref<number>(0)
/** 客户仪表盘：本周 / 本月发送条数 */
const weekSent = ref<number>(0)
const monthSent = ref<number>(0)
const customerAccountInfo = ref<AccountInfo | null>(null)
const todayDelivered = ref<number>(0)
const todayFailed = ref<number>(0)
const successRate = ref<number>(0)
const failRate = ref<number>(0)
const todayCost = ref<number>(0)
const todayRevenue = ref<number>(0)
const todayProfit = ref<number>(0)
const availableChannels = ref<number>(0)
const totalChannels = ref<number>(0)
const activeAccounts = ref<number>(0)
const totalBalance = ref<number>(0)
const accountId = ref('')
const isStaff = ref(false)
const isSales = ref(false)
const adminRole = ref('')
const lastUpdateTime = ref('')
const channels = ref<any[]>([])
const recentRecords = ref<any[]>([])
const recentCustomers = ref<any[]>([])
const permissions = ref({
  view_global: false,
  view_finance: false,
  view_channels: false,
  view_customers: false,
  view_system_monitor: false
})

const serverMetrics = ref<AdminServerMetrics | null>(null)
const serviceStatus = ref<AdminServiceStatusItem[]>([])

const yesterdayStats = ref<{ sent: number; delivered: number; failed: number; revenue: number }>({ sent: 0, delivered: 0, failed: 0, revenue: 0 })
const dailyTrend = ref<{ date: string; sent: number; delivered: number; revenue: number }[]>([])
const topCustomers = ref<{ account_name: string; sent: number; delivered: number; revenue: number }[]>([])
const batchOverview = ref<{ total: number; processing: number; completed: number; failed: number }>({ total: 0, processing: 0, completed: 0, failed: 0 })
const channelStats = ref<{ channel_name: string; sent: number; delivered: number; rate: number }[]>([])
const topCountries = ref<{ country_code: string; sent: number; delivered: number; rate: number }[]>([])
const lowBalanceAccounts = ref<{ id: number; account_name: string; balance: number; currency: string; threshold: number }[]>([])
const activeBatches = ref<{ id: number; batch_name: string; status: string; account_name: string; total: number; progress: number }[]>([])
// 通道送达率异常榜：后端单独取今日有量通道按送达率升序（最差排前，sent>=30）
const worstChannels = ref<{ channel_name: string; sent: number; delivered: number; rate: number }[]>([])

/** 业绩概览：今日 / 本周 / 本月 切换 + 聚合数据 */
type PerfStat = { sent: number; cost: number; revenue: number; profit: number }
const emptyPerf: PerfStat = { sent: 0, cost: 0, revenue: 0, profit: 0 }
const perfPeriod = ref<'today' | 'week' | 'month'>('today')
const periodStats = ref<Record<'today' | 'week' | 'month', PerfStat>>({
  today: { ...emptyPerf },
  week: { ...emptyPerf },
  month: { ...emptyPerf },
})
const periodOptions = computed(() => [
  { key: 'today' as const, label: t('dashboard.periodToday') },
  { key: 'week' as const, label: t('dashboard.periodWeek') },
  { key: 'month' as const, label: t('dashboard.periodMonth') },
])
const currentPerf = computed<PerfStat>(() => periodStats.value[perfPeriod.value] || emptyPerf)

/** 近 7 日发送量迷你折线（SVG path），无数据时返回空串由模板兜底 */
const SPARK_W = 168
const SPARK_H = 44
const sparkPath = computed(() => {
  const vals = dailyTrend.value.map((d) => Number(d.sent) || 0)
  if (!vals.length) return ''
  const max = Math.max(...vals, 1)
  const n = vals.length
  const step = n > 1 ? SPARK_W / (n - 1) : 0
  return vals
    .map((v, i) => {
      const x = (i * step).toFixed(1)
      const y = (SPARK_H - (v / max) * (SPARK_H - 6) - 3).toFixed(1)
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
    })
    .join(' ')
})
const sparkArea = computed(() => {
  if (!sparkPath.value) return ''
  return `${sparkPath.value} L ${SPARK_W} ${SPARK_H} L 0 ${SPARK_H} Z`
})

/** 是否展示服务器监控区（与权限同步，供模板使用） */
const showSystemMonitor = computed(() => permissions.value.view_system_monitor)

/** 员工仪表盘加载中（用于监控卡片内占位，避免误判为「无数据」） */
const dashboardLoading = computed(() => loading.value && isStaff.value)

const accountName = ref(localStorage.getItem('account_name') || 'User')
const apiKey = ref(sessionStorage.getItem('api_key') || localStorage.getItem('api_key') || '')

const maskedApiKey = computed(() => {
  if (!apiKey.value) return '-'
  return apiKey.value.substring(0, 8) + '••••' + apiKey.value.substring(apiKey.value.length - 4)
})

const customerDisplayName = computed(() => {
  const c = customerAccountInfo.value
  if (!c) return accountName.value
  const name = (c.client_name || c.company_name || c.account_name || '').trim()
  return name || accountName.value
})

const customerAccountStatusLabel = computed(() => {
  const s = customerAccountInfo.value?.status || ''
  if (s === 'active') return t('common.active')
  if (s === 'suspended') return t('dashboard.accountSuspended')
  if (s === 'closed') return t('dashboard.accountClosed')
  return s || '—'
})

const customerAccountStatusClass = computed(() => {
  const s = customerAccountInfo.value?.status || ''
  if (s === 'active') return 'active'
  if (s === 'suspended') return 'warning'
  if (s === 'closed') return 'inactive'
  return 'inactive'
})

/** Telegram 展示为 @username */
function formatTgHandle(raw?: string | null): string {
  if (raw == null || String(raw).trim() === '') return '—'
  const u = String(raw).trim().replace(/^@+/, '')
  return u ? `@${u}` : '—'
}

/** 国家代码展示（可后续接完整国家库） */
function countryDisplay(code?: string | null): string {
  if (code == null || String(code).trim() === '') return '—'
  const c = String(code).trim().toUpperCase()
  const map: Record<string, string> = {
    CN: '中国',
    US: '美国',
    GB: '英国',
    BR: '巴西',
    BD: '孟加拉国',
    IN: '印度',
    ID: '印度尼西亚',
    MX: '墨西哥',
    PH: '菲律宾',
    VN: '越南',
    TH: '泰国',
    MY: '马来西亚',
    JP: '日本',
    KR: '韩国',
  }
  return map[c] || code
}

const roleClass = computed(() => {
  if (adminRole.value === 'super_admin' || adminRole.value === 'admin') return 'admin'
  if (adminRole.value === 'sales') return 'sales'
  if (adminRole.value === 'finance') return 'finance'
  if (adminRole.value === 'tech') return 'tech'
  return 'customer'
})

const getDashboardTitle = () => {
  if (adminRole.value === 'super_admin' || adminRole.value === 'admin') return t('dashboard.adminConsole')
  if (adminRole.value === 'sales') return t('dashboard.salesWorkbench')
  if (adminRole.value === 'finance') return t('dashboard.financeCenter')
  if (adminRole.value === 'tech') return t('dashboard.techMonitor')
  return t('dashboard.myConsole')
}

const getRoleLabel = () => {
  const roles: Record<string, string> = {
    'super_admin': t('roles.superAdmin'),
    'admin': t('roles.admin'),
    'sales': t('roles.sales'),
    'finance': t('roles.finance'),
    'tech': t('roles.tech'),
  }
  return roles[adminRole.value] || t('roles.customer')
}

const calcChange = (today: number, yesterday: number): { pct: string; dir: 'up' | 'down' | 'flat' } => {
  if (yesterday === 0 && today === 0) return { pct: '0', dir: 'flat' }
  if (yesterday === 0) return { pct: '+∞', dir: 'up' }
  const pct = ((today - yesterday) / yesterday * 100).toFixed(1)
  if (today > yesterday) return { pct: `+${pct}`, dir: 'up' }
  if (today < yesterday) return { pct: pct, dir: 'down' }
  return { pct: '0', dir: 'flat' }
}

const sentChange = computed(() => calcChange(todaySent.value, yesterdayStats.value.sent))
const deliveredChange = computed(() => calcChange(todayDelivered.value, yesterdayStats.value.delivered))
const revenueChange = computed(() => calcChange(todayRevenue.value, yesterdayStats.value.revenue))

const trendMaxSent = computed(() => Math.max(...dailyTrend.value.map(d => d.sent), 1))

const formatNumber = (num: number) => {
  const n = Number(num) || 0
  return n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

/** 短信单价：与账户设置页 AccountOverviewPanel.fmtNum 一致，最多 4 位小数，避免仪表盘误显示为 0.01 */
const formatUnitPrice = (num: number) => {
  const n = Number(num) || 0
  return n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 4 })
}

const formatRate = (rate: number) => {
  const r = Number(rate) || 0
  return r.toFixed(1)
}

const getCountryFlag = (code: string) => {
  const flags: Record<string, string> = {
    '86': '🇨🇳', '1': '🇺🇸', '44': '🇬🇧', '81': '🇯🇵', '82': '🇰🇷',
    '63': '🇵🇭', '84': '🇻🇳', '66': '🇹🇭', '62': '🇮🇩', '60': '🇲🇾',
    '52': '🇲🇽', '55': '🇧🇷', '91': '🇮🇳', '49': '🇩🇪', '33': '🇫🇷',
  }
  return flags[code] || '🌍'
}

const batchStatusText = (status: string) => {
  const map: Record<string, string> = {
    processing: '处理中',
    paused: '已暂停',
    failed: '失败',
    pending: '待处理',
    completed: '已完成',
    cancelled: '已取消',
  }
  return map[status] || status
}

const getStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    'pending': 'pending', 'sent': 'sent', 'delivered': 'delivered', 'failed': 'failed',
  }
  const key = statusMap[status] || status
  return t(`smsStatus.${key}`)
}

const truncateMessage = (msg: string) => {
  if (!msg) return '-'
  return msg.length > 25 ? msg.substring(0, 25) + '...' : msg
}

const formatTime = (time: string) => {
  if (!time) return '-'
  const date = new Date(time)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  if (diff < 60000) return t('time.justNow')
  if (diff < 3600000) return t('time.minutesAgo', { n: Math.floor(diff / 60000) })
  if (diff < 86400000) return t('time.hoursAgo', { n: Math.floor(diff / 3600000) })
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const updateLastTime = () => {
  lastUpdateTime.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

/** 统一仪表盘监控字段（兼容 snake_case / camelCase） */
function normalizeServerMetrics(raw: unknown): AdminServerMetrics | null {
  if (raw == null || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  if (typeof o.error === 'string') return { error: o.error }
  const arr = o.load_avg ?? o.loadAvg
  return {
    hostname: typeof o.hostname === 'string' ? o.hostname : undefined,
    cpu_percent: Number(o.cpu_percent ?? o.cpuPercent) || 0,
    memory_percent: Number(o.memory_percent ?? o.memoryPercent) || 0,
    memory_used_gb: Number(o.memory_used_gb ?? o.memoryUsedGb) || 0,
    memory_total_gb: Number(o.memory_total_gb ?? o.memoryTotalGb) || 0,
    disk_percent: Number(o.disk_percent ?? o.diskPercent) || 0,
    disk_free_gb: Number(o.disk_free_gb ?? o.diskFreeGb) || 0,
    disk_total_gb: Number(o.disk_total_gb ?? o.diskTotalGb) || 0,
    load_avg: Array.isArray(arr) ? (arr as number[]) : null
  }
}

function normalizeServiceStatus(raw: unknown): AdminServiceStatusItem[] {
  if (!Array.isArray(raw)) return []
  return raw.map((item) => {
    const o = item as Record<string, unknown>
    return {
      id: String(o.id ?? ''),
      status: o.status === 'ok' ? 'ok' : 'error',
      message: typeof o.message === 'string' ? o.message : undefined
    }
  })
}

const loadStaffData = async () => {
  try {
    const res = await getAdminDashboard()
    if (res.success) {
      accountName.value = res.admin_name
      adminRole.value = res.admin_role
      isSales.value = res.admin_role === 'sales'
      
      todaySent.value = Number(res.statistics.today_sent) || 0
      todayDelivered.value = Number(res.statistics.today_delivered) || 0
      todayFailed.value = Number(res.statistics.today_failed) || 0
      successRate.value = Number(res.statistics.today_success_rate) || 0
      failRate.value = todaySent.value > 0 ? (todayFailed.value / todaySent.value * 100) : 0
      todayCost.value = Number(res.statistics.today_cost) || 0
      todayRevenue.value = Number(res.statistics.today_revenue) || 0
      todayProfit.value = Number(res.statistics.today_profit) || 0
      availableChannels.value = Number(res.statistics.active_channels) || 0
      activeAccounts.value = Number(res.statistics.active_accounts) || 0
      totalBalance.value = Number(res.statistics.total_balance) || 0
      
      const perm = (res.permissions || {}) as Record<string, unknown>
      const roleMonitors = ['super_admin', 'admin', 'tech'].includes(res.admin_role || '')
      let viewSystemMonitor: boolean
      if (typeof perm.view_system_monitor === 'boolean') {
        viewSystemMonitor = perm.view_system_monitor
      } else if (typeof perm.viewSystemMonitor === 'boolean') {
        viewSystemMonitor = perm.viewSystemMonitor
      } else {
        // 旧版后端未返回该字段时，超级管理员 / 管理员 / 运维仍展示监控区（数据可能为空，见文案提示）
        viewSystemMonitor = roleMonitors
      }
      permissions.value = {
        view_global: false,
        view_finance: false,
        view_channels: false,
        view_customers: false,
        ...(res.permissions || {}),
        view_system_monitor: viewSystemMonitor,
      }
      // 业绩概览：优先用后端 period_stats；旧后端未返回时，本周/本月回退为今日值以免显示空白
      const todayPerf: PerfStat = {
        sent: todaySent.value,
        cost: todayCost.value,
        revenue: todayRevenue.value,
        profit: todayProfit.value,
      }
      const ps = (res.period_stats || {}) as Partial<Record<'today' | 'week' | 'month', PerfStat>>
      const pick = (p?: PerfStat): PerfStat =>
        p
          ? {
              sent: Number(p.sent) || 0,
              cost: Number(p.cost) || 0,
              revenue: Number(p.revenue) || 0,
              profit: Number(p.profit) || 0,
            }
          : { ...todayPerf }
      periodStats.value = {
        today: ps.today ? pick(ps.today) : todayPerf,
        week: pick(ps.week),
        month: pick(ps.month),
      }
      yesterdayStats.value = res.yesterday_stats || { sent: 0, delivered: 0, failed: 0, revenue: 0 }
      dailyTrend.value = res.daily_trend || []
      topCustomers.value = res.top_customers || []
      batchOverview.value = res.batch_overview || { total: 0, processing: 0, completed: 0, failed: 0 }
      channelStats.value = res.channel_stats || []
      worstChannels.value = res.worst_channels || []
      topCountries.value = res.top_countries || []
      lowBalanceAccounts.value = res.low_balance_accounts || []
      activeBatches.value = res.active_batches || []
      recentCustomers.value = res.recent_customers || []
      if (viewSystemMonitor) {
        const r = res as Record<string, unknown>
        serverMetrics.value = normalizeServerMetrics(r.server_metrics ?? r.serverMetrics)
        serviceStatus.value = normalizeServiceStatus(r.service_status ?? r.serviceStatus)
      } else {
        serverMetrics.value = null
        serviceStatus.value = []
      }
      
      // 加载通道
      if (permissions.value.view_channels) {
        try {
          const channelsRes = await getChannels()
          channels.value = channelsRes.channels || []
        } catch {
          channels.value = []
        }
      }
    }
  } catch (error) {
    console.error('Failed to load staff data:', error)
  }
}

const loadCustomerData = async () => {
  try {
    const infoRes = await getAccountInfo()
    customerAccountInfo.value = infoRes
    balance.value = Number(infoRes.balance) || 0
    accountId.value = String(infoRes.id)
    if (infoRes.account_name) {
      accountName.value = infoRes.account_name
      try {
        localStorage.setItem('account_name', infoRes.account_name)
      } catch {
        /* ignore */
      }
    }

    const todayStr = new Date().toISOString().split('T')[0]
    try {
      const statsRes = await getStatistics(todayStr, todayStr)
      todaySent.value = Number(statsRes.total_sent) || 0
    } catch {
      todaySent.value = 0
    }

    const now = new Date()
    const dow = now.getDay()
    const diffToMonday = dow === 0 ? -6 : 1 - dow
    const weekStart = new Date(now)
    weekStart.setDate(now.getDate() + diffToMonday)
    weekStart.setHours(0, 0, 0, 0)
    const weekStartStr = weekStart.toISOString().split('T')[0]
    try {
      const weekStats = await getStatistics(weekStartStr, todayStr)
      weekSent.value = Number(weekStats.total_sent) || 0
    } catch {
      weekSent.value = 0
    }

    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1)
    const monthStartStr = monthStart.toISOString().split('T')[0]
    try {
      const monthStats = await getStatistics(monthStartStr, todayStr)
      monthSent.value = Number(monthStats.total_sent) || 0
    } catch {
      monthSent.value = 0
    }

    todayDelivered.value = 0
    todayFailed.value = 0
    successRate.value = 0
    failRate.value = 0

    try {
      const recordsRes = await getSMSRecords({ page: 1, page_size: 5 })
      recentRecords.value = recordsRes.records || []
    } catch {
      recentRecords.value = []
    }
  } catch (error) {
    console.error('Failed to load customer data:', error)
  }
}

const loadData = async () => {
  loading.value = true
  try {
    const isImpersonateMode = sessionStorage.getItem('impersonate_mode') === '1'
    const adminToken = localStorage.getItem('admin_token')
    
    if (!isImpersonateMode && adminToken) {
      isStaff.value = true
      await loadStaffData()
    } else {
      isStaff.value = false
      adminRole.value = ''
      await loadCustomerData()
    }
    updateLastTime()
  } finally {
    loading.value = false
  }
}

const refreshData = () => {
  loadData()
  ElMessage.success(t('dashboard.dataRefreshed'))
}

const copyApiKey = async () => {
  if (!apiKey.value) return
  try {
    await navigator.clipboard.writeText(apiKey.value)
    ElMessage.success(t('common.copied'))
  } catch {
    ElMessage.error(t('common.error'))
  }
}

let refreshInterval: number

onMounted(() => {
  loadData()
  refreshInterval = window.setInterval(() => loadData(), 60000)
})

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval)
})

</script>

<style scoped>

.dashboard {
  width: 100%;
  min-height: 100%;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* 头部 */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.role-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.role-badge.admin {
  background: linear-gradient(135deg, rgba(255, 77, 79, 0.15), rgba(255, 120, 117, 0.1));
  color: #ff4d4f;
}

.role-badge.sales {
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.15), rgba(118, 75, 162, 0.1));
  color: var(--primary);
}

.role-badge.finance {
  background: linear-gradient(135deg, rgba(255, 210, 0, 0.15), rgba(247, 151, 30, 0.1));
  color: var(--warning);
}

.role-badge.tech {
  background: linear-gradient(135deg, rgba(79, 172, 254, 0.15), rgba(0, 242, 254, 0.1));
  color: var(--info);
}

.role-badge.customer {
  background: linear-gradient(135deg, rgba(56, 239, 125, 0.15), rgba(17, 153, 142, 0.1));
  color: var(--success);
}

.last-update {
  font-size: 12px;
  color: var(--text-quaternary);
  margin-left: 8px;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: rgba(102, 126, 234, 0.1);
  border: 1px solid rgba(102, 126, 234, 0.2);
  border-radius: 10px;
  color: var(--primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover:not(:disabled) {
  background: rgba(102, 126, 234, 0.15);
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.refresh-btn svg.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 核心指标 */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
  margin-bottom: 32px;
}

.metrics-grid.metrics-4 {
  grid-template-columns: repeat(4, 1fr);
}

.metrics-grid.metrics-6 {
  grid-template-columns: repeat(6, 1fr);
}

/* 服务器性能与服务状态 */
.system-monitor-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 32px;
}

.server-health-card {
  height: auto;
}

.server-health-body {
  padding: 16px 20px 20px;
}

.host-line {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0 0 16px;
}

.host-label {
  opacity: 0.85;
}

.host-value {
  color: var(--text-primary);
  font-weight: 500;
}

.perf-row {
  margin-bottom: 14px;
}

.perf-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.perf-pct {
  font-weight: 600;
  color: var(--text-primary);
}

.perf-bar-track {
  height: 6px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 4px;
  overflow: hidden;
}

.perf-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.35s ease;
}

.perf-bar-fill.cpu {
  background: linear-gradient(90deg, #667eea, #764ba2);
}

.perf-bar-fill.memory {
  background: linear-gradient(90deg, #4facfe, #00f2fe);
}

.perf-bar-fill.disk {
  background: linear-gradient(90deg, #56ab2f, #a8e063);
}

.perf-sub {
  font-size: 11px;
  color: var(--text-quaternary);
  margin: 6px 0 0;
}

.load-line {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 12px 0 0;
}

.metrics-error {
  font-size: 13px;
  color: var(--error);
  line-height: 1.5;
}

.empty-state.subtle {
  text-align: left;
  color: var(--text-quaternary);
  font-size: 13px;
}

@media (max-width: 960px) {
  .system-monitor-row {
    grid-template-columns: 1fr;
  }
}

.metric-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  padding: 18px;
  transition: all 0.2s;
}

.metric-card.clickable {
  cursor: pointer;
}


.metric-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.metric-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.metric-icon.sent { background: linear-gradient(135deg, rgba(102, 126, 234, 0.2), rgba(118, 75, 162, 0.15)); color: var(--primary); }
.metric-icon.success { background: linear-gradient(135deg, rgba(56, 239, 125, 0.2), rgba(17, 153, 142, 0.15)); color: var(--success); }
.metric-icon.failed { background: linear-gradient(135deg, rgba(255, 77, 79, 0.2), rgba(255, 120, 117, 0.15)); color: var(--error); }
.metric-icon.balance { background: linear-gradient(135deg, rgba(255, 210, 0, 0.2), rgba(247, 151, 30, 0.15)); color: var(--warning); }
.metric-icon.customers { background: linear-gradient(135deg, rgba(79, 172, 254, 0.2), rgba(0, 242, 254, 0.15)); color: var(--info); }
.metric-icon.revenue { background: linear-gradient(135deg, rgba(56, 239, 125, 0.2), rgba(17, 153, 142, 0.15)); color: var(--success); }
.metric-icon.profit { background: linear-gradient(135deg, rgba(240, 147, 251, 0.2), rgba(245, 87, 108, 0.15)); color: #F093FB; }

.metric-label {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.metric-body {
  display: flex;
  align-items: baseline;
  gap: 2px;
  margin-bottom: 6px;
}

.metric-currency {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-secondary);
}

.metric-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.metric-value.positive {
  color: var(--success);
}

.metric-unit {
  font-size: 13px;
  color: var(--text-quaternary);
  margin-left: 2px;
}

.metric-footer {
  display: flex;
  align-items: center;
  gap: 6px;
}

.metric-rate {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
}

.metric-rate.success { background: rgba(56, 239, 125, 0.1); color: var(--success); }
.metric-rate.failed { background: rgba(255, 77, 79, 0.1); color: var(--error); }

.metric-compare {
  font-size: 11px;
  color: var(--text-quaternary);
}

.metric-link {
  font-size: 12px;
  color: var(--primary);
  font-weight: 500;
}

/* 内容网格 */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.content-grid.admin-grid {
  grid-template-columns: 1.2fr 1fr;
}

.content-grid.customer-grid {
  grid-template-columns: 1.5fr 1fr;
}

.content-left, .content-right {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 卡片通用 */
.card {
  border-radius: var(--radius-xl);
  overflow: hidden;
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-title svg {
  color: var(--text-tertiary);
}

/* 快速操作 */
.actions-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  padding: 16px;
}

.actions-grid.admin-actions {
  grid-template-columns: repeat(4, 1fr);
}

.action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 18px 14px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  transform: translateY(-2px);
}

.action-btn.primary { background: linear-gradient(135deg, rgba(102, 126, 234, 0.15), rgba(118, 75, 162, 0.1)); }
.action-btn.primary .action-icon { color: var(--primary); }
.action-btn.success { background: linear-gradient(135deg, rgba(56, 239, 125, 0.15), rgba(17, 153, 142, 0.1)); }
.action-btn.success .action-icon { color: var(--success); }
.action-btn.warning { background: linear-gradient(135deg, rgba(255, 210, 0, 0.15), rgba(247, 151, 30, 0.1)); }
.action-btn.warning .action-icon { color: var(--warning); }
.action-btn.info { background: linear-gradient(135deg, rgba(79, 172, 254, 0.15), rgba(0, 242, 254, 0.1)); }
.action-btn.info .action-icon { color: var(--info); }
.action-btn.stats { background: linear-gradient(135deg, rgba(167, 139, 250, 0.18), rgba(139, 92, 246, 0.1)); }
.action-btn.stats .action-icon { color: #a78bfa; }

.action-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
}

/* 列表通用样式 */
.view-all-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: var(--text-tertiary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.view-all-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 30px 20px;
  color: var(--text-quaternary);
  font-size: 13px;
}

/* 通道状态 */
.channel-count {
  font-size: 12px;
  color: var(--success);
  font-weight: 500;
}


/* 客户列表 (销售专属) */
.customers-list {
  padding: 8px 16px 16px;
}

.customer-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.customer-item:last-child {
  border-bottom: none;
}

.customer-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.customer-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.customer-status {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
}

.customer-status.active {
  background: rgba(56, 239, 125, 0.1);
  color: var(--success);
}

.customer-balance {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

/* 系统概览 */
.overview-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  padding: 16px;
}

.overview-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 10px;
}

.overview-label {
  font-size: 11px;
  color: var(--text-quaternary);
}

.overview-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

/* 发送记录 */
.records-list {
  padding: 8px;
  max-height: 260px;
  overflow-y: auto;
}

.record-item {
  display: grid;
  grid-template-columns: 130px 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 10px;
  border-radius: 10px;
  transition: background 0.15s;
}

.record-item:hover {
  background: rgba(255, 255, 255, 0.03);
}

.record-phone {
  display: flex;
  align-items: center;
  gap: 6px;
}

.phone-flag {
  font-size: 14px;
}

.phone-number {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  font-family: 'SF Mono', Monaco, monospace;
}

.record-message {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.record-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.record-status {
  font-size: 10px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 4px;
}

.record-status.delivered { background: rgba(56, 239, 125, 0.1); color: var(--success); }
.record-status.sent { background: rgba(102, 126, 234, 0.1); color: var(--primary); }
.record-status.pending { background: rgba(255, 210, 0, 0.1); color: var(--warning); }
.record-status.failed { background: rgba(255, 77, 79, 0.1); color: var(--error); }

.record-time {
  font-size: 10px;
  color: var(--text-quaternary);
  white-space: nowrap;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 6px;
}

.status-badge.active {
  background: rgba(56, 239, 125, 0.1);
  color: var(--success);
}

.status-badge.warning {
  background: rgba(255, 193, 7, 0.12);
  color: var(--warning);
}

.status-badge.inactive {
  background: rgba(148, 163, 184, 0.15);
  color: var(--text-tertiary);
}

.status-badge .status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 8px currentColor;
  animation: status-pulse 2s infinite ease-in-out;
}

@keyframes status-pulse {
  0% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.3); opacity: 0.7; }
  100% { transform: scale(1); opacity: 1; }
}

.api-key-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.api-key {
  font-family: 'SF Mono', Monaco, monospace;
  font-size: 11px;
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.04);
  padding: 4px 10px;
  border-radius: 6px;
}

.copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: var(--text-quaternary);
  cursor: pointer;
  transition: all 0.15s;
}

.copy-btn:hover {
  background: rgba(102, 126, 234, 0.1);
  border-color: var(--primary);
  color: var(--primary);
}

/* ========== 日环比对比行 ========== */
.compare-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.compare-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
}
.compare-chip.up { background: rgba(16, 185, 129, 0.08); border-color: rgba(16, 185, 129, 0.2); }
.compare-chip.down { background: rgba(239, 68, 68, 0.08); border-color: rgba(239, 68, 68, 0.2); }
.compare-label { color: var(--text-tertiary); }
.compare-val { font-weight: 700; }
.compare-chip.up .compare-val { color: #10b981; }
.compare-chip.down .compare-val { color: #ef4444; }
.compare-chip.flat .compare-val { color: var(--text-secondary); }
.compare-hint { color: var(--text-quaternary); font-size: 11px; }

.metric-change {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
}
.metric-change.up { color: #10b981; background: rgba(16, 185, 129, 0.1); }
.metric-change.down { color: #ef4444; background: rgba(239, 68, 68, 0.1); }
.metric-change.flat { color: var(--text-tertiary); }

/* ========== 可视化行 ========== */
.viz-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 20px;
}

/* 7日趋势 */
.trend-chart {
  padding: 16px;
}
.trend-bars {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  height: 140px;
  padding-bottom: 4px;
}
.trend-bar-group {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  height: 100%;
}
.trend-bar-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  align-items: center;
  width: 100%;
  position: relative;
}
.trend-bar {
  width: 60%;
  min-height: 4px;
  border-radius: 4px 4px 0 0;
  position: relative;
  transition: height 0.5s ease;
}
.sent-bar { background: linear-gradient(180deg, rgba(102, 126, 234, 0.8), rgba(102, 126, 234, 0.4)); }
.delivered-bar {
  background: linear-gradient(180deg, rgba(16, 185, 129, 0.8), rgba(16, 185, 129, 0.4));
  width: 40%;
  position: absolute;
  bottom: 0;
  border-radius: 4px 4px 0 0;
}
.trend-bar-tooltip {
  display: none;
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.8);
  color: #fff;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  white-space: nowrap;
}
.trend-bar-group:hover .trend-bar-tooltip { display: block; }
.trend-date { font-size: 11px; color: var(--text-quaternary); }
.trend-legend {
  display: flex;
  gap: 16px;
  justify-content: center;
  margin-top: 10px;
  font-size: 12px;
  color: var(--text-tertiary);
}
.legend-item { display: flex; align-items: center; gap: 4px; }
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.legend-dot.sent { background: rgba(102, 126, 234, 0.8); }
.legend-dot.delivered { background: rgba(16, 185, 129, 0.8); }

/* 客户TOP */
.top-list { padding: 8px 16px; }
.top-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  font-size: 13px;
}
.top-item:last-child { border-bottom: none; }
.top-rank {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-weight: 700;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-tertiary);
}
.top-rank.gold { background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; }
.top-rank.silver { background: linear-gradient(135deg, #94a3b8, #64748b); color: #fff; }
.top-rank.bronze { background: linear-gradient(135deg, #c2884e, #a0693c); color: #fff; }
.top-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); }
.top-sent { font-weight: 700; color: var(--primary); min-width: 60px; text-align: right; }
.top-rate { color: #10b981; font-weight: 600; min-width: 52px; text-align: right; }
.top-revenue { color: var(--text-secondary); min-width: 60px; text-align: right; }

/* 批次概览 */
.batch-stats {
  display: flex;
  gap: 16px;
  padding: 20px 16px;
  justify-content: center;
}
.batch-stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 20px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
}
.batch-stat-item.total { border-left: 3px solid var(--primary); }
.batch-stat-item.processing { border-left: 3px solid #3b82f6; }
.batch-stat-item.completed { border-left: 3px solid #10b981; }
.batch-stat-item.failed { border-left: 3px solid #ef4444; }
.batch-num { font-size: 24px; font-weight: 800; color: var(--text-primary); }
.batch-label { font-size: 12px; color: var(--text-tertiary); }

/* 通道统计 */
.ch-stats-list { padding: 8px 16px; }
.ch-stat-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  font-size: 13px;
}
.ch-stat-row:last-child { border-bottom: none; }
.ch-stat-name { width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); }
.ch-stat-bar-wrap {
  flex: 1;
  height: 6px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 3px;
  overflow: hidden;
}
.ch-stat-bar { height: 100%; border-radius: 3px; transition: width 0.6s ease; }
.ch-stat-bar.good { background: linear-gradient(90deg, #10b981, #34d399); }
.ch-stat-bar.warn { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
.ch-stat-bar.bad { background: linear-gradient(90deg, #ef4444, #f87171); }
.ch-stat-pct { font-weight: 700; min-width: 44px; text-align: right; }
.ch-stat-row .ch-stat-pct { color: var(--text-secondary); }
.ch-stat-cnt { color: var(--text-quaternary); min-width: 70px; text-align: right; }

/* 余额不足预警 */
.channel-count.alert { color: var(--danger, #ef4444); background: rgba(239, 68, 68, 0.12); padding: 1px 8px; border-radius: 10px; }
.lowbal-list { padding: 6px 16px 12px; }
.lowbal-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  font-size: 13px;
  cursor: pointer;
}
.lowbal-item:last-child { border-bottom: none; }
.lowbal-item:hover { background: rgba(255, 255, 255, 0.03); }
.lowbal-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); }
.lowbal-bal { font-weight: 700; color: var(--warning, #f59e0b); white-space: nowrap; }
.lowbal-bal.neg { color: var(--danger, #ef4444); }

/* 异常/进行中批次 */
.active-batch-list { padding: 6px 16px 12px; }
.active-batch-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  font-size: 13px;
  cursor: pointer;
}
.active-batch-item:last-child { border-bottom: none; }
.active-batch-item:hover { background: rgba(255, 255, 255, 0.03); }
.ab-status { flex-shrink: 0; min-width: 48px; text-align: center; font-size: 11px; font-weight: 600; padding: 2px 6px; border-radius: 6px; }
.ab-status.processing { color: #3b82f6; background: rgba(59, 130, 246, 0.14); }
.ab-status.paused { color: #f59e0b; background: rgba(245, 158, 11, 0.14); }
.ab-status.failed { color: #ef4444; background: rgba(239, 68, 68, 0.14); }
.ab-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); }
.ab-acct { color: var(--text-quaternary); max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ab-progress { font-weight: 700; min-width: 48px; text-align: right; color: var(--text-secondary); }

/* 响应式 */
@media (max-width: 1400px) {
  .metrics-grid.metrics-6 {
    grid-template-columns: repeat(3, 1fr);
  }
  
  .actions-grid.admin-actions {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 1024px) {
  .metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .content-grid {
    grid-template-columns: 1fr;
  }
  
  .viz-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .dashboard-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  
  .header-left {
    flex-wrap: wrap;
  }
  
  .metrics-grid {
    grid-template-columns: 1fr;
  }
  
  .record-item {
    grid-template-columns: 1fr;
    gap: 6px;
  }
}

/* 亮色主题 */
[data-theme="light"] .metric-card,
[data-theme="light"] .card {
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(20px);
  border: 0.5px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

[data-theme="light"] .card-header {
  border-bottom-color: rgba(0, 0, 0, 0.05);
}

[data-theme="light"] .channel-item,
[data-theme="light"] .customer-item,
[data-theme="light"] .account-row {
  border-bottom-color: rgba(0, 0, 0, 0.05);
}

[data-theme="light"] .channel-protocol {
  background: rgba(0, 0, 0, 0.04);
}

[data-theme="light"] .overview-item {
  background: rgba(0, 0, 0, 0.02);
}

[data-theme="light"] .api-key {
  background: rgba(0, 0, 0, 0.04);
}

[data-theme="light"] .record-item:hover {
  background: rgba(0, 0, 0, 0.02);
}

[data-theme="light"] .compare-chip {
  background: rgba(0, 0, 0, 0.03);
  border-color: rgba(0, 0, 0, 0.06);
}

[data-theme="light"] .top-item,
[data-theme="light"] .ch-stat-row {
  border-bottom-color: rgba(0, 0, 0, 0.05);
}

[data-theme="light"] .batch-stat-item {
  background: rgba(0, 0, 0, 0.02);
}

[data-theme="light"] .ch-stat-bar-wrap {
  background: rgba(0, 0, 0, 0.06);
}

[data-theme="light"] .top-rank {
  background: rgba(0, 0, 0, 0.05);
}

/* ========== 新版仪表盘：hero 卡 ========== */
.hero-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-bottom: 20px;
}
.hero-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 22px;
  border-radius: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  transition: transform 0.2s, box-shadow 0.2s;
}
.hero-card:hover { transform: translateY(-2px); }
.hero-icon {
  flex-shrink: 0;
  width: 46px;
  height: 46px;
  border-radius: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.hero-icon.balance { background: linear-gradient(135deg, rgba(102,126,234,0.2), rgba(118,75,162,0.14)); color: var(--primary); }
.hero-icon.cost { background: linear-gradient(135deg, rgba(255,210,0,0.2), rgba(247,151,30,0.14)); color: var(--warning); }
.hero-icon.channels { background: linear-gradient(135deg, rgba(79,172,254,0.2), rgba(0,242,254,0.14)); color: var(--info); }
.hero-icon.customers { background: linear-gradient(135deg, rgba(56,239,125,0.2), rgba(17,153,142,0.14)); color: var(--success); }
.hero-meta { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.hero-label { font-size: 12px; color: var(--text-tertiary); font-weight: 500; }
.hero-value { font-size: 26px; font-weight: 800; color: var(--text-primary); line-height: 1; letter-spacing: -0.5px; }
.hero-cur { font-size: 17px; font-weight: 700; color: var(--text-secondary); margin-right: 1px; }

/* ========== 业绩概览 ========== */
.perf-card { margin-bottom: 20px; }
.period-tabs {
  display: inline-flex;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 9px;
  padding: 3px;
  gap: 2px;
}
.period-tab {
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 600;
  padding: 5px 14px;
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.18s;
}
.period-tab:hover { color: var(--text-secondary); }
.period-tab.active {
  background: rgba(102, 126, 234, 0.18);
  color: var(--primary);
}
.perf-body {
  display: grid;
  grid-template-columns: 1fr 220px;
  gap: 24px;
  padding: 22px 20px;
  align-items: center;
}
.perf-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.perf-metric {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 0;
}
.perf-metric-label { font-size: 12px; color: var(--text-quaternary); }
.perf-metric-value { font-size: 22px; font-weight: 700; color: var(--text-primary); line-height: 1; }
.perf-metric-value.money { color: var(--text-primary); }
.perf-metric-value.profit.positive { color: var(--success); }
.perf-cur { font-size: 14px; font-weight: 600; color: var(--text-secondary); margin-right: 1px; }
.perf-unit { font-size: 12px; font-weight: 500; color: var(--text-quaternary); font-style: normal; margin-left: 3px; }
.perf-spark {
  border-left: 1px solid rgba(255, 255, 255, 0.06);
  padding-left: 22px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 10px;
}
.perf-spark-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-tertiary);
}
.perf-detail-link { color: var(--primary); cursor: pointer; font-weight: 500; }
.perf-detail-link:hover { text-decoration: underline; }
.spark-svg { width: 100%; height: 44px; display: block; }
.spark-empty { font-size: 12px; color: var(--text-quaternary); height: 44px; display: flex; align-items: center; }


/* ========== 客户动态 ========== */
.activity-list { padding: 8px 16px 14px; }
.activity-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  font-size: 13px;
}
.activity-item:last-child { border-bottom: none; }
.activity-rank {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-weight: 700;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-tertiary);
}
.activity-rank.gold { background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; }
.activity-rank.silver { background: linear-gradient(135deg, #94a3b8, #64748b); color: #fff; }
.activity-rank.bronze { background: linear-gradient(135deg, #c2884e, #a0693c); color: #fff; }
.activity-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); }
.activity-rate { color: var(--success); font-weight: 600; min-width: 40px; text-align: right; }
.activity-sent { font-weight: 700; color: var(--primary); min-width: 70px; text-align: right; }

/* 亮色主题（新版块） */
[data-theme="light"] .hero-card { background: rgba(255,255,255,0.82); border: 0.5px solid rgba(0,0,0,0.08); box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
[data-theme="light"] .period-tabs { background: rgba(0,0,0,0.04); border-color: rgba(0,0,0,0.06); }
[data-theme="light"] .perf-spark { border-left-color: rgba(0,0,0,0.07); }
[data-theme="light"] .action-row:hover { background: rgba(0,0,0,0.03); }
[data-theme="light"] .activity-item { border-bottom-color: rgba(0,0,0,0.05); }
[data-theme="light"] .activity-rank { background: rgba(0,0,0,0.05); }

/* 响应式（新版块） */
@media (max-width: 1200px) {
  .hero-grid { grid-template-columns: repeat(2, 1fr); }
  .perf-body { grid-template-columns: 1fr; }
  .perf-spark { border-left: none; border-top: 1px solid rgba(255,255,255,0.06); padding-left: 0; padding-top: 16px; }
}
@media (max-width: 640px) {
  .hero-grid { grid-template-columns: 1fr; }
  .perf-metrics { grid-template-columns: repeat(2, 1fr); }
}

</style>