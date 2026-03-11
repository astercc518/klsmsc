<template>
  <div class="settlements-page">
    <div class="page-header">
      <h2 class="page-title">{{ $t('menu.settlementManage') }}</h2>
      <el-button type="primary" @click="showGenerateDialog">
        <el-icon><Plus /></el-icon>
        {{ $t('settlements.generate') }}
      </el-button>
    </div>

    <!-- 标签页 -->
    <el-tabs v-model="activeTab" class="main-tabs">
      <!-- 供应商结算 -->
      <el-tab-pane :label="$t('settlements.supplierSettlement')" name="supplier">
        <!-- 汇总卡片 -->
        <div class="summary-grid" v-if="settlementSummary">
          <div class="summary-card">
            <div class="summary-label">{{ $t('settlements.totalSettlements') }}</div>
            <div class="summary-value">{{ settlementSummary.total_count }}</div>
          </div>
          <div class="summary-card">
            <div class="summary-label">{{ $t('settlements.totalAmount') }}</div>
            <div class="summary-value">{{ formatMoney(settlementSummary.total_amount) }}</div>
          </div>
          <div class="summary-card">
            <div class="summary-label">{{ $t('settlements.draftCount') }}</div>
            <div class="summary-value text-info">{{ settlementSummary.draft_count }}</div>
          </div>
          <div class="summary-card">
            <div class="summary-label">{{ $t('settlements.paidCount') }}</div>
            <div class="summary-value text-success">{{ settlementSummary.paid_count }}</div>
          </div>
        </div>

        <!-- 搜索筛选 -->
        <el-card class="filter-card">
          <el-form :inline="true" :model="filters" class="filter-form">
            <el-form-item :label="$t('settlements.supplier')">
              <el-select v-model="filters.supplier_id" :placeholder="$t('common.all')" clearable>
                <el-option v-for="s in supplierOptions" :key="s.id" :label="s.supplier_name" :value="s.id" />
              </el-select>
            </el-form-item>
            <el-form-item :label="$t('settlements.status')">
              <el-select v-model="filters.status" :placeholder="$t('common.all')" clearable>
                <el-option :label="$t('settlements.draft')" value="draft" />
                <el-option :label="$t('settlements.pending')" value="pending" />
                <el-option :label="$t('settlements.confirmed')" value="confirmed" />
                <el-option :label="$t('settlements.paid')" value="paid" />
                <el-option :label="$t('settlements.cancelled')" value="cancelled" />
              </el-select>
            </el-form-item>
            <el-form-item :label="$t('settlements.dateRange')">
              <el-date-picker
                v-model="filters.dateRange"
                type="daterange"
                :range-separator="$t('profit.to')"
                value-format="YYYY-MM-DD"
                clearable
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadSettlements">{{ $t('common.search') }}</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 结算单列表 -->
        <el-card class="table-card">
          <el-table :data="settlements" v-loading="loading" stripe class="responsive-table">
            <el-table-column prop="settlement_no" :label="$t('settlements.settlementNo')" width="200" />
            <el-table-column prop="supplier_name" :label="$t('settlements.supplier')" width="150" />
            <el-table-column :label="$t('settlements.period')" width="200">
              <template #default="{ row }">
                {{ formatDate(row.period_start) }} ~ {{ formatDate(row.period_end) }}
              </template>
            </el-table-column>
            <el-table-column prop="total_sms_count" :label="$t('settlements.smsCount')" width="100" />
            <el-table-column prop="total_cost" :label="$t('settlements.costAmount')" width="120">
              <template #default="{ row }">
                {{ row.currency }} {{ formatMoney(row.total_cost) }}
              </template>
            </el-table-column>
            <el-table-column prop="adjustment_amount" :label="$t('settlements.adjustment')" width="100">
              <template #default="{ row }">
                <span :class="{ 'text-success': row.adjustment_amount > 0, 'text-danger': row.adjustment_amount < 0 }">
                  {{ row.adjustment_amount > 0 ? '+' : '' }}{{ formatMoney(row.adjustment_amount) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="final_amount" :label="$t('settlements.finalAmount')" width="120">
              <template #default="{ row }">
                <strong>{{ row.currency }} {{ formatMoney(row.final_amount) }}</strong>
              </template>
            </el-table-column>
            <el-table-column prop="status" :label="$t('settlements.status')" width="100">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">
                  {{ statusMap[row.status] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" :label="$t('common.createdAt')" width="160">
              <template #default="{ row }">
                {{ formatTime(row.created_at) }}
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.action')" width="180" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="viewSettlement(row)">{{ $t('common.detail') }}</el-button>
                <el-button
                  v-if="row.status === 'draft'"
                  type="success"
                  link
                  size="small"
                  @click="handleConfirm(row)"
                >{{ $t('common.confirm') }}</el-button>
                <el-button
                  v-if="row.status === 'confirmed'"
                  type="primary"
                  link
                  size="small"
                  @click="handlePay(row)"
                >{{ $t('settlements.paid') }}</el-button>
                <el-button
                  v-if="['draft', 'pending', 'confirmed'].includes(row.status)"
                  type="danger"
                  link
                  size="small"
                  @click="handleCancel(row)"
                >{{ $t('common.cancel') }}</el-button>
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
              @size-change="loadSettlements"
              @current-change="loadSettlements"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <!-- 利润报表 -->
      <el-tab-pane :label="$t('profit.title')" name="profit">
        <el-card class="filter-card">
          <el-form :inline="true" :model="profitFilters" class="filter-form">
            <el-form-item :label="$t('profit.dateRange')">
              <el-date-picker
                v-model="profitFilters.dateRange"
                type="daterange"
                :range-separator="$t('profit.to')"
                :start-placeholder="$t('profit.startDate')"
                :end-placeholder="$t('profit.endDate')"
                value-format="YYYY-MM-DD"
              />
            </el-form-item>
            <el-form-item :label="$t('profit.groupBy')">
              <el-select v-model="profitFilters.group_by">
                <el-option :label="$t('profit.byDate')" value="day" />
                <el-option :label="$t('profit.bySupplier')" value="supplier" />
                <el-option :label="$t('profit.byCountry')" value="country" />
                <el-option :label="$t('profit.byChannel')" value="channel" />
              </el-select>
            </el-form-item>
            <el-form-item :label="$t('settlements.supplier')">
              <el-select v-model="profitFilters.supplier_id" :placeholder="$t('common.all')" clearable>
                <el-option
                  v-for="s in supplierOptions"
                  :key="s.id"
                  :label="s.supplier_name"
                  :value="s.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadProfitReport">{{ $t('smsRecords.query') }}</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 汇总卡片 -->
        <div class="summary-grid" v-if="profitSummary">
          <div class="summary-card">
            <div class="summary-label">{{ $t('profit.totalCost') }}</div>
            <div class="summary-value text-danger">{{ formatMoney(profitSummary.total_cost) }}</div>
          </div>
          <div class="summary-card">
            <div class="summary-label">{{ $t('profit.totalRevenue') }}</div>
            <div class="summary-value text-success">{{ formatMoney(profitSummary.total_revenue) }}</div>
          </div>
          <div class="summary-card">
            <div class="summary-label">{{ $t('profit.grossProfit') }}</div>
            <div class="summary-value" :class="profitSummary.total_profit >= 0 ? 'text-success' : 'text-danger'">
              {{ formatMoney(profitSummary.total_profit) }}
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-label">{{ $t('profit.profitMargin') }}</div>
            <div class="summary-value">{{ profitSummary.overall_margin }}%</div>
          </div>
        </div>

        <el-card class="table-card">
          <el-table :data="profitData" v-loading="profitLoading" stripe class="responsive-table">
            <el-table-column v-if="profitFilters.group_by === 'day'" prop="date" :label="$t('profit.date')" width="120" />
            <el-table-column v-if="profitFilters.group_by === 'supplier'" prop="supplier_name" :label="$t('settlements.supplier')" width="150" />
            <el-table-column v-if="profitFilters.group_by === 'country'" prop="country_code" :label="$t('profit.countryCode')" width="100" />
            <el-table-column v-if="profitFilters.group_by === 'channel'" prop="channel_name" :label="$t('channels.channel')" width="150" />
            <el-table-column prop="total_count" :label="$t('profit.totalSms')" width="100" />
            <el-table-column prop="success_count" :label="$t('profit.successCount')" width="100" />
            <el-table-column prop="total_cost" :label="$t('profit.cost')" width="120">
              <template #default="{ row }">
                {{ formatMoney(row.total_cost) }}
              </template>
            </el-table-column>
            <el-table-column prop="total_revenue" :label="$t('profit.revenue')" width="120">
              <template #default="{ row }">
                {{ formatMoney(row.total_revenue) }}
              </template>
            </el-table-column>
            <el-table-column prop="profit" :label="$t('profit.profit')" width="120">
              <template #default="{ row }">
                <span :class="row.profit >= 0 ? 'text-success' : 'text-danger'">
                  {{ formatMoney(row.profit) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="profit_margin" :label="$t('profit.profitMargin')" width="100">
              <template #default="{ row }">
                {{ row.profit_margin }}%
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- 销售佣金 -->
      <el-tab-pane :label="$t('settlements.salesCommission')" name="commission">
        <div class="tab-header">
          <el-button type="primary" @click="showCommissionGenerateDialog">
            <el-icon><Plus /></el-icon>
            {{ $t('settlements.generateCommission') }}
          </el-button>
        </div>
        <div class="summary-grid" v-if="commissionSummary">
          <div class="summary-card">
            <div class="summary-label">{{ $t('settlements.totalSettlements') }}</div>
            <div class="summary-value">{{ commissionSummary.total_count }}</div>
          </div>
          <div class="summary-card">
            <div class="summary-label">{{ $t('settlements.totalAmount') }}</div>
            <div class="summary-value">{{ formatMoney(commissionSummary.total_amount) }}</div>
          </div>
          <div class="summary-card">
            <div class="summary-label">{{ $t('settlements.draftCount') }}</div>
            <div class="summary-value text-info">{{ commissionSummary.draft_count }}</div>
          </div>
          <div class="summary-card">
            <div class="summary-label">{{ $t('settlements.paidCount') }}</div>
            <div class="summary-value text-success">{{ commissionSummary.paid_count }}</div>
          </div>
        </div>
        <el-card class="filter-card">
          <el-form :inline="true" :model="commissionFilters" class="filter-form">
            <el-form-item :label="$t('settlements.sales')">
              <el-select v-model="commissionFilters.sales_id" :placeholder="$t('common.all')" clearable filterable>
                <el-option v-for="s in salesOptions" :key="s.id" :label="s.real_name || s.username" :value="s.id" />
              </el-select>
            </el-form-item>
            <el-form-item :label="$t('settlements.status')">
              <el-select v-model="commissionFilters.status" :placeholder="$t('common.all')" clearable>
                <el-option :label="$t('settlements.draft')" value="draft" />
                <el-option :label="$t('settlements.confirmed')" value="confirmed" />
                <el-option :label="$t('settlements.paid')" value="paid" />
                <el-option :label="$t('settlements.cancelled')" value="cancelled" />
              </el-select>
            </el-form-item>
            <el-form-item :label="$t('settlements.dateRange')">
              <el-date-picker
                v-model="commissionFilters.dateRange"
                type="daterange"
                :range-separator="$t('profit.to')"
                value-format="YYYY-MM-DD"
                clearable
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadCommissionSettlements">{{ $t('common.search') }}</el-button>
            </el-form-item>
          </el-form>
        </el-card>
        <el-card class="table-card">
          <el-table :data="commissionSettlements" v-loading="commissionLoading" stripe class="responsive-table">
            <el-table-column prop="settlement_no" :label="$t('settlements.settlementNo')" width="200" />
            <el-table-column prop="sales_name" :label="$t('settlements.sales')" width="120" />
            <el-table-column :label="$t('settlements.period')" width="200">
              <template #default="{ row }">
                {{ formatDate(row.period_start) }} ~ {{ formatDate(row.period_end) }}
              </template>
            </el-table-column>
            <el-table-column prop="total_revenue" :label="$t('settlements.revenueAmount')" width="120">
              <template #default="{ row }">{{ formatMoney(row.total_revenue) }}</template>
            </el-table-column>
            <el-table-column prop="commission_rate" :label="$t('settlements.commissionRate')" width="100">
              <template #default="{ row }">{{ row.commission_rate }}%</template>
            </el-table-column>
            <el-table-column prop="commission_amount" :label="$t('settlements.commissionAmount')" width="120">
              <template #default="{ row }">
                <strong>{{ formatMoney(row.commission_amount) }}</strong>
              </template>
            </el-table-column>
            <el-table-column prop="status" :label="$t('settlements.status')" width="100">
              <template #default="{ row }">
                <el-tag :type="commissionStatusTagType(row.status)" size="small">
                  {{ commissionStatusMap[row.status] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.action')" width="180" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="viewCommissionSettlement(row)">{{ $t('common.detail') }}</el-button>
                <el-button v-if="row.status === 'draft'" type="success" link size="small" @click="handleConfirmCommission(row)">{{ $t('common.confirm') }}</el-button>
                <el-button v-if="row.status === 'confirmed'" type="primary" link size="small" @click="handlePayCommission(row)">{{ $t('settlements.paid') }}</el-button>
                <el-button v-if="['draft', 'confirmed'].includes(row.status)" type="danger" link size="small" @click="handleCancelCommission(row)">{{ $t('common.cancel') }}</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="commissionPagination.page"
              v-model:page-size="commissionPagination.pageSize"
              :total="commissionPagination.total"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next"
              @size-change="loadCommissionSettlements"
              @current-change="loadCommissionSettlements"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <!-- 客户账单 -->
      <el-tab-pane :label="$t('settlements.customerBilling')" name="bills">
        <div class="tab-header">
          <el-button type="primary" @click="showBillGenerateDialog">
            <el-icon><Plus /></el-icon>
            {{ $t('settlements.generateCustomerBill') }}
          </el-button>
        </div>
        <el-card class="filter-card">
          <el-form :inline="true" :model="billFilters" class="filter-form">
            <el-form-item :label="$t('settlements.customer')">
              <el-select v-model="billFilters.account_id" :placeholder="$t('common.all')" clearable filterable>
                <el-option v-for="a in accountOptions" :key="a.id" :label="a.account_name" :value="a.id" />
              </el-select>
            </el-form-item>
            <el-form-item :label="$t('settlements.status')">
              <el-select v-model="billFilters.status" :placeholder="$t('common.all')" clearable>
                <el-option :label="$t('settlements.draft')" value="draft" />
                <el-option :label="$t('settlements.sent')" value="sent" />
                <el-option :label="$t('settlements.paid')" value="paid" />
                <el-option :label="$t('settlements.partial')" value="partial" />
                <el-option :label="$t('settlements.overdue')" value="overdue" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadBills">{{ $t('common.search') }}</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card class="table-card">
          <el-table :data="bills" v-loading="billsLoading" stripe class="responsive-table">
            <el-table-column prop="bill_no" :label="$t('settlements.billNo')" width="200" />
            <el-table-column prop="account_name" :label="$t('settlements.customer')" width="120" />
            <el-table-column :label="$t('settlements.billingPeriod')" width="200">
              <template #default="{ row }">
                {{ formatDate(row.period_start) }} ~ {{ formatDate(row.period_end) }}
              </template>
            </el-table-column>
            <el-table-column prop="total_sms_count" :label="$t('settlements.smsCount')" width="100" />
            <el-table-column prop="total_amount" :label="$t('settlements.amountDue')" width="120">
              <template #default="{ row }">
                {{ formatMoney(row.total_amount) }}
              </template>
            </el-table-column>
            <el-table-column prop="paid_amount" :label="$t('settlements.paidAmount')" width="120">
              <template #default="{ row }">
                {{ formatMoney(row.paid_amount) }}
              </template>
            </el-table-column>
            <el-table-column prop="outstanding_amount" :label="$t('settlements.outstandingAmount')" width="120">
              <template #default="{ row }">
                <span :class="{ 'text-danger': row.outstanding_amount > 0 }">
                  {{ formatMoney(row.outstanding_amount) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="status" :label="$t('settlements.status')" width="100">
              <template #default="{ row }">
                <el-tag :type="billStatusTagType(row.status)" size="small">
                  {{ billStatusMap[row.status] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="due_date" :label="$t('settlements.dueDate')" width="120">
              <template #default="{ row }">
                {{ formatDate(row.due_date) }}
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.action')" width="150" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="viewBill(row)">{{ $t('common.detail') }}</el-button>
                <el-button
                  v-if="row.outstanding_amount > 0"
                  type="success"
                  link
                  size="small"
                  @click="openBillPay(row)"
                >{{ $t('settlements.recordPayment') }}</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="billPagination.page"
              v-model:page-size="billPagination.pageSize"
              :total="billPagination.total"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next"
              @size-change="loadBills"
              @current-change="loadBills"
            />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 生成结算单对话框 -->
    <el-dialog v-model="generateDialogVisible" :title="$t('settlements.generateSettlement')" width="500px">
      <el-form ref="generateFormRef" :model="generateForm" :rules="generateRules" label-width="100px">
        <el-form-item :label="$t('settlements.supplier')" prop="supplier_id">
          <el-select v-model="generateForm.supplier_id" :placeholder="$t('settlements.selectSupplier')" style="width: 100%">
            <el-option
              v-for="s in supplierOptions"
              :key="s.id"
              :label="s.supplier_name"
              :value="s.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('settlements.period')" prop="period">
          <el-date-picker
            v-model="generateForm.period"
            type="daterange"
            :range-separator="$t('profit.to')"
            :start-placeholder="$t('profit.startDate')"
            :end-placeholder="$t('profit.endDate')"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item :label="$t('common.notes')">
          <el-input v-model="generateForm.notes" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="generateDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="generating" @click="submitGenerate">{{ $t('settlements.generate') }}</el-button>
      </template>
    </el-dialog>

    <!-- 支付对话框 -->
    <el-dialog v-model="payDialogVisible" :title="$t('settlements.paySettlement')" width="500px">
      <el-form ref="payFormRef" :model="payForm" :rules="payRules" label-width="100px">
        <el-form-item :label="$t('settlements.paymentMethod')" prop="payment_method">
          <el-select v-model="payForm.payment_method" :placeholder="$t('settlements.selectPaymentMethod')" style="width: 100%">
            <el-option :label="$t('settlements.bankTransfer')" value="bank_transfer" />
            <el-option label="PayPal" value="paypal" />
            <el-option label="USDT" value="usdt" />
            <el-option :label="$t('common.other')" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('settlements.paymentReference')">
          <el-input v-model="payForm.payment_reference" :placeholder="$t('settlements.transactionNumber')" />
        </el-form-item>
        <el-form-item :label="$t('common.notes')">
          <el-input v-model="payForm.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="payDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="paying" @click="submitPay">{{ $t('settlements.confirmPayment') }}</el-button>
      </template>
    </el-dialog>

    <!-- 结算单详情抽屉 -->
    <el-drawer v-model="detailDrawerVisible" :title="$t('settlements.settlementDetail')" size="700px">
      <div v-if="currentSettlement" class="settlement-detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="$t('settlements.settlementNo')">{{ currentSettlement.settlement_no }}</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.supplier')">{{ currentSettlement.supplier_name }}</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.period')">
            {{ formatDate(currentSettlement.period_start) }} ~ {{ formatDate(currentSettlement.period_end) }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.status')">
            <el-tag :type="statusTagType(currentSettlement.status)" size="small">
              {{ statusMap[currentSettlement.status] }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.totalSmsCount')">{{ currentSettlement.total_sms_count }}</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.successCount')">{{ currentSettlement.total_success_count }}</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.costAmount')">
            {{ currentSettlement.currency }} {{ formatMoney(currentSettlement.total_cost) }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.adjustment')">
            {{ formatMoney(currentSettlement.adjustment_amount) }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.finalAmount')">
            <strong>{{ currentSettlement.currency }} {{ formatMoney(currentSettlement.final_amount) }}</strong>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.paymentMethod')">{{ currentSettlement.payment_method || '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-divider>{{ $t('settlements.details') }}</el-divider>
        <el-table :data="currentSettlement.details" size="small" max-height="300">
          <el-table-column prop="country_code" :label="$t('profit.countryCode')" width="100" />
          <el-table-column prop="sms_count" :label="$t('settlements.smsCount')" width="80" />
          <el-table-column prop="success_count" :label="$t('settlements.successCount')" width="80" />
          <el-table-column prop="unit_cost" :label="$t('settlements.unitCost')" width="100">
            <template #default="{ row }">
              {{ row.unit_cost.toFixed(6) }}
            </template>
          </el-table-column>
          <el-table-column prop="total_cost" :label="$t('settlements.subtotal')" width="100">
            <template #default="{ row }">
              {{ formatMoney(row.total_cost) }}
            </template>
          </el-table-column>
        </el-table>

        <div class="detail-actions" v-if="['draft', 'pending'].includes(currentSettlement.status)">
          <el-button type="warning" size="small" @click="showAdjustDialog">{{ $t('settlements.adjustAmount') }}</el-button>
        </div>

        <el-divider>{{ $t('settlements.operationLog') }}</el-divider>
        <el-timeline>
          <el-timeline-item
            v-for="log in currentSettlement.logs"
            :key="log.id"
            :timestamp="formatTime(log.created_at)"
            placement="top"
          >
            <p><strong>{{ log.operator_name }}</strong> {{ log.description }}</p>
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-drawer>

    <!-- 调整金额对话框 -->
    <el-dialog v-model="adjustDialogVisible" :title="$t('settlements.adjustAmount')" width="450px">
      <el-form ref="adjustFormRef" :model="adjustForm" :rules="adjustRules" label-width="100px">
        <el-form-item :label="$t('settlements.adjustment')" prop="adjustment_amount">
          <el-input-number v-model="adjustForm.adjustment_amount" :precision="4" :step="10" />
          <span class="form-hint">{{ $t('settlements.adjustmentHint') }}</span>
        </el-form-item>
        <el-form-item :label="$t('settlements.reason')" prop="reason">
          <el-input v-model="adjustForm.reason" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adjustDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="adjusting" @click="submitAdjust">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 生成客户账单对话框 -->
    <el-dialog v-model="billGenerateVisible" :title="$t('settlements.generateCustomerBill')" width="500px">
      <el-form ref="billGenerateFormRef" :model="billGenerateForm" :rules="billGenerateRules" label-width="100px">
        <el-form-item :label="$t('settlements.customer')" prop="account_id">
          <el-select v-model="billGenerateForm.account_id" :placeholder="$t('settlements.selectCustomer')" filterable style="width: 100%">
            <el-option v-for="a in accountOptions" :key="a.id" :label="`${a.account_name} (${a.email})`" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('settlements.period')" prop="period">
          <el-date-picker
            v-model="billGenerateForm.period"
            type="daterange"
            :range-separator="$t('profit.to')"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item :label="$t('settlements.dueDays')">
          <el-input-number v-model="billGenerateForm.due_days" :min="1" :max="90" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="billGenerateVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="billGenerating" @click="submitBillGenerate">{{ $t('settlements.generate') }}</el-button>
      </template>
    </el-dialog>

    <!-- 客户账单详情抽屉 -->
    <el-drawer v-model="billDetailVisible" :title="$t('settlements.billDetail')" size="600px">
      <div v-if="currentBill" class="bill-detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="$t('settlements.billNo')">{{ currentBill.bill_no }}</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.customer')">{{ currentBill.account_name }}</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.billingPeriod')">
            {{ formatDate(currentBill.period_start) }} ~ {{ formatDate(currentBill.period_end) }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.status')">
            <el-tag :type="billStatusTagType(currentBill.status)" size="small">{{ billStatusMap[currentBill.status] }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.amountDue')">{{ formatMoney(currentBill.total_amount) }}</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.paidAmount')">{{ formatMoney(currentBill.paid_amount) }}</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.outstandingAmount')">
            <strong :class="{ 'text-danger': currentBill.outstanding_amount > 0 }">{{ formatMoney(currentBill.outstanding_amount) }}</strong>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.dueDate')">{{ formatDate(currentBill.due_date) }}</el-descriptions-item>
        </el-descriptions>
        <el-divider>{{ $t('settlements.details') }}</el-divider>
        <el-table :data="currentBill.details" size="small" max-height="250">
          <el-table-column prop="country_code" :label="$t('profit.countryCode')" width="100" />
          <el-table-column prop="sms_count" :label="$t('settlements.smsCount')" width="80" />
          <el-table-column prop="total_amount" :label="$t('settlements.subtotal')" width="100">
            <template #default="{ row }">{{ formatMoney(row.total_amount) }}</template>
          </el-table-column>
        </el-table>
        <div class="detail-actions" v-if="currentBill.outstanding_amount > 0">
          <el-button type="primary" size="small" @click="showBillPayDialog">{{ $t('settlements.recordPayment') }}</el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 生成销售佣金结算单对话框 -->
    <el-dialog v-model="commissionGenerateVisible" :title="$t('settlements.generateCommission')" width="450px">
      <el-form ref="commissionGenerateFormRef" :model="commissionGenerateForm" :rules="commissionGenerateRules" label-width="100px">
        <el-form-item :label="$t('settlements.sales')" prop="sales_id">
          <el-select v-model="commissionGenerateForm.sales_id" :placeholder="$t('settlements.selectSales')" filterable style="width: 100%">
            <el-option v-for="s in salesOptions" :key="s.id" :label="`${s.real_name || s.username} (${s.commission_rate || 0}%)`" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('settlements.settlementMonth')" prop="period">
          <el-date-picker
            v-model="commissionGenerateForm.period"
            type="month"
            value-format="YYYY-MM"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="commissionGenerateVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="commissionGenerating" @click="submitCommissionGenerate">{{ $t('settlements.generate') }}</el-button>
      </template>
    </el-dialog>

    <!-- 销售佣金结算单详情抽屉 -->
    <el-drawer v-model="commissionDetailVisible" :title="$t('settlements.commissionDetail')" size="600px">
      <div v-if="currentCommissionSettlement" class="commission-detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="$t('settlements.settlementNo')">{{ currentCommissionSettlement.settlement_no }}</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.sales')">{{ currentCommissionSettlement.sales_name }}</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.period')">
            {{ formatDate(currentCommissionSettlement.period_start) }} ~ {{ formatDate(currentCommissionSettlement.period_end) }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.status')">
            <el-tag :type="commissionStatusTagType(currentCommissionSettlement.status)" size="small">
              {{ commissionStatusMap[currentCommissionSettlement.status] }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.revenueAmount')">{{ formatMoney(currentCommissionSettlement.total_revenue) }}</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.commissionRate')">{{ currentCommissionSettlement.commission_rate }}%</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.commissionAmount')">
            <strong>{{ formatMoney(currentCommissionSettlement.commission_amount) }}</strong>
          </el-descriptions-item>
        </el-descriptions>
        <el-divider>{{ $t('settlements.details') }}</el-divider>
        <el-table :data="currentCommissionSettlement.details" size="small" max-height="250">
          <el-table-column prop="account_name" :label="$t('settlements.customer')" width="120" />
          <el-table-column prop="total_sms_count" :label="$t('settlements.smsCount')" width="80" />
          <el-table-column prop="total_revenue" :label="$t('settlements.revenueAmount')" width="100">
            <template #default="{ row }">{{ formatMoney(row.total_revenue) }}</template>
          </el-table-column>
          <el-table-column prop="commission_amount" :label="$t('settlements.commissionAmount')" width="100">
            <template #default="{ row }">{{ formatMoney(row.commission_amount) }}</template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>

    <!-- 销售佣金支付对话框 -->
    <el-dialog v-model="commissionPayVisible" :title="$t('settlements.payCommission')" width="450px">
      <el-form ref="commissionPayFormRef" :model="commissionPayForm" :rules="commissionPayRules" label-width="100px">
        <el-form-item :label="$t('settlements.paymentMethod')" prop="payment_method">
          <el-select v-model="commissionPayForm.payment_method" :placeholder="$t('settlements.selectPaymentMethod')" style="width: 100%">
            <el-option :label="$t('settlements.bankTransfer')" value="bank_transfer" />
            <el-option label="PayPal" value="paypal" />
            <el-option label="USDT" value="usdt" />
            <el-option :label="$t('common.other')" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('settlements.paymentReference')">
          <el-input v-model="commissionPayForm.payment_reference" :placeholder="$t('settlements.transactionNumber')" />
        </el-form-item>
        <el-form-item :label="$t('common.notes')">
          <el-input v-model="commissionPayForm.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="commissionPayVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="commissionPaying" @click="submitCommissionPay">{{ $t('settlements.confirmPayment') }}</el-button>
      </template>
    </el-dialog>

    <!-- 客户账单收款对话框 -->
    <el-dialog v-model="billPayVisible" :title="$t('settlements.recordPayment')" width="450px">
      <el-form ref="billPayFormRef" :model="billPayForm" :rules="billPayRules" label-width="100px">
        <el-form-item :label="$t('settlements.amount')" prop="amount">
          <el-input-number v-model="billPayForm.amount" :min="0.01" :max="currentBill?.outstanding_amount || 999999" :precision="4" style="width: 100%" />
          <span class="form-hint">{{ $t('settlements.outstandingAmount') }}: {{ formatMoney(currentBill?.outstanding_amount || 0) }}</span>
        </el-form-item>
        <el-form-item :label="$t('settlements.paymentMethod')">
          <el-select v-model="billPayForm.payment_method" :placeholder="$t('common.optional')" clearable style="width: 100%">
            <el-option :label="$t('settlements.bankTransfer')" value="bank_transfer" />
            <el-option label="PayPal" value="paypal" />
            <el-option label="USDT" value="usdt" />
            <el-option :label="$t('common.other')" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('settlements.paymentReference')">
          <el-input v-model="billPayForm.payment_reference" :placeholder="$t('settlements.transactionNumber')" />
        </el-form-item>
        <el-form-item :label="$t('common.notes')">
          <el-input v-model="billPayForm.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="billPayVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="billPaying" @click="submitBillPay">{{ $t('settlements.confirmPayment') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  getSettlements, getSettlementsSummary, generateSettlement, getSettlementDetail,
  confirmSettlement, paySettlement, cancelSettlement, adjustSettlement,
  getProfitReport, getCustomerBills, getCustomerBillDetail, payCustomerBill, generateCustomerBill,
  getCommissionSummary, getCommissionSettlements, generateCommissionSettlement,
  getCommissionSettlementDetail, confirmCommissionSettlement, payCommissionSettlement, cancelCommissionSettlement,
  type Settlement
} from '@/api/settlement'
import { getSuppliers } from '@/api/supplier'
import { getAccountsAdmin } from '@/api/admin'
import { request } from '@/api/index'

const { t } = useI18n()

// 映射
const statusMap = computed(() => ({
  draft: t('settlements.draft'),
  pending: t('settlements.pending'),
  confirmed: t('settlements.confirmed'),
  paid: t('settlements.paid'),
  cancelled: t('settlements.cancelled')
}))

const billStatusMap = computed(() => ({
  draft: t('settlements.draft'),
  sent: t('settlements.sent'),
  paid: t('settlements.paid'),
  partial: t('settlements.partial'),
  overdue: t('settlements.overdue')
}))

const statusTagType = (status: string) => {
  const map: Record<string, string> = {
    draft: 'info',
    pending: 'warning',
    confirmed: 'primary',
    paid: 'success',
    cancelled: 'danger'
  }
  return map[status] || 'info'
}

const billStatusTagType = (status: string) => {
  const map: Record<string, string> = {
    draft: 'info',
    sent: 'warning',
    paid: 'success',
    partial: 'primary',
    overdue: 'danger'
  }
  return map[status] || 'info'
}

const commissionStatusMap = computed(() => ({
  draft: t('settlements.draft'),
  confirmed: t('settlements.confirmed'),
  paid: t('settlements.paid'),
  cancelled: t('settlements.cancelled')
}))

const commissionStatusTagType = (status: string) => {
  const map: Record<string, string> = {
    draft: 'info',
    confirmed: 'primary',
    paid: 'success',
    cancelled: 'danger'
  }
  return map[status] || 'info'
}

const formatMoney = (value: number) => value?.toFixed(2) || '0.00'
const formatDate = (date?: string) => date ? date.split('T')[0] : '-'
const formatTime = (time?: string) => time ? new Date(time).toLocaleString('zh-CN') : '-'

// 获取本月日期范围 [月初, 月末]
const getCurrentMonthRange = (): [string, string] => {
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth(), 1)
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0)
  return [
    start.toISOString().slice(0, 10),
    end.toISOString().slice(0, 10)
  ]
}

// 数据
const activeTab = ref('supplier')
const loading = ref(false)
const settlements = ref<Settlement[]>([])
const supplierOptions = ref<any[]>([])
const filters = reactive({
  supplier_id: null as number | null,
  status: '',
  dateRange: [...getCurrentMonthRange()]
})
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

// 结算单汇总
const settlementSummary = ref<{
  total_count: number
  total_amount: number
  draft_count: number
  pending_count?: number
  paid_count: number
} | null>(null)

// 生成
const generateDialogVisible = ref(false)
const generating = ref(false)
const generateFormRef = ref<FormInstance>()
const generateForm = reactive({
  supplier_id: null as number | null,
  period: [] as string[],
  notes: ''
})
const generateRules = computed<FormRules>(() => ({
  supplier_id: [{ required: true, message: t('settlements.selectSupplierRequired'), trigger: 'change' }],
  period: [{ required: true, message: t('settlements.selectPeriodRequired'), trigger: 'change' }]
}))

// 支付
const payDialogVisible = ref(false)
const paying = ref(false)
const payFormRef = ref<FormInstance>()
const payingSettlement = ref<Settlement | null>(null)
const payForm = reactive({
  payment_method: '',
  payment_reference: '',
  notes: ''
})
const payRules = computed<FormRules>(() => ({
  payment_method: [{ required: true, message: t('settlements.selectPaymentMethodRequired'), trigger: 'change' }]
}))

// 详情
const detailDrawerVisible = ref(false)
const currentSettlement = ref<any>(null)

// 调整金额
const adjustDialogVisible = ref(false)
const adjusting = ref(false)
const adjustFormRef = ref<FormInstance>()
const adjustForm = reactive({
  adjustment_amount: 0,
  reason: ''
})
const adjustRules = computed<FormRules>(() => ({
  adjustment_amount: [{ required: true, message: t('settlements.enterAdjustment'), trigger: 'blur' }],
  reason: [{ required: true, message: t('settlements.enterReason'), trigger: 'blur' }]
}))

// 利润报表
const profitLoading = ref(false)
const profitFilters = reactive({
  dateRange: [...getCurrentMonthRange()],
  group_by: 'day',
  supplier_id: null as number | null
})
const profitSummary = ref<any>(null)
const profitData = ref<any[]>([])

// 客户账单
const billsLoading = ref(false)
const billFilters = reactive({
  account_id: null as number | null,
  status: ''
})
const bills = ref<any[]>([])
const billPagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})
const accountOptions = ref<{ id: number; account_name: string; email: string }[]>([])

// 生成客户账单
const billGenerateVisible = ref(false)
const billGenerating = ref(false)
const billGenerateFormRef = ref<FormInstance>()
const billGenerateForm = reactive({
  account_id: null as number | null,
  period: [] as string[],
  due_days: 30
})
const billGenerateRules = computed<FormRules>(() => ({
  account_id: [{ required: true, message: t('settlements.selectCustomerRequired'), trigger: 'change' }],
  period: [{ required: true, message: t('settlements.selectPeriodRequired'), trigger: 'change' }]
}))

// 客户账单详情
const billDetailVisible = ref(false)
const currentBill = ref<any>(null)

// 客户账单收款
const billPayVisible = ref(false)
const billPaying = ref(false)
const billPayFormRef = ref<FormInstance>()
const billPayForm = reactive({
  amount: 0,
  payment_method: '',
  payment_reference: '',
  notes: ''
})
const billPayRules = computed<FormRules>(() => ({
  amount: [
    { required: true, message: t('settlements.enterAmount'), trigger: 'blur' },
    { type: 'number', min: 0.01, message: t('settlements.amountMin'), trigger: 'blur' }
  ]
}))

// 销售佣金
const commissionLoading = ref(false)
const commissionSummary = ref<any>(null)
const commissionSettlements = ref<any[]>([])
const commissionFilters = reactive({
  sales_id: null as number | null,
  status: '',
  dateRange: [...getCurrentMonthRange()]
})
const commissionPagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})
const salesOptions = ref<any[]>([])
const commissionGenerateVisible = ref(false)
const commissionGenerating = ref(false)
const commissionGenerateFormRef = ref<FormInstance>()
const commissionGenerateForm = reactive({
  sales_id: null as number | null,
  period: '' as string
})
const commissionGenerateRules = computed<FormRules>(() => ({
  sales_id: [{ required: true, message: t('settlements.selectSalesRequired'), trigger: 'change' }],
  period: [{ required: true, message: t('settlements.selectMonthRequired'), trigger: 'change' }]
}))
const commissionDetailVisible = ref(false)
const currentCommissionSettlement = ref<any>(null)
const commissionPayVisible = ref(false)
const commissionPaying = ref(false)
const payingCommissionSettlement = ref<any>(null)
const commissionPayFormRef = ref<FormInstance>()
const commissionPayForm = reactive({
  payment_method: '',
  payment_reference: '',
  notes: ''
})
const commissionPayRules = computed<FormRules>(() => ({
  payment_method: [{ required: true, message: t('settlements.selectPaymentMethodRequired'), trigger: 'change' }]
}))

// 方法
const loadSuppliers = async () => {
  try {
    const res = await getSuppliers({ page_size: 100 })
    if (res?.success) {
      supplierOptions.value = res.suppliers || []
    }
  } catch (error) {
    console.error('Failed to load suppliers:', error)
  }
}

const loadSettlementsSummary = async () => {
  try {
    const res = await getSettlementsSummary({
      supplier_id: filters.supplier_id || undefined,
      status: filters.status || undefined,
      start_date: filters.dateRange?.[0],
      end_date: filters.dateRange?.[1]
    })
    if (res?.success && res?.summary) {
      settlementSummary.value = res.summary
    }
  } catch (error) {
    console.error('Failed to load settlements summary:', error)
  }
}

const loadSettlements = async () => {
  loading.value = true
  try {
    const res = await getSettlements({
      page: pagination.page,
      page_size: pagination.pageSize,
      supplier_id: filters.supplier_id || undefined,
      status: filters.status || undefined,
      start_date: filters.dateRange?.[0],
      end_date: filters.dateRange?.[1]
    })
    if (res?.success) {
      settlements.value = res.settlements || []
      pagination.total = res.total ?? 0
    }
    await loadSettlementsSummary()
  } catch (error) {
    console.error('Failed to load settlements:', error)
  } finally {
    loading.value = false
  }
}

const showAdjustDialog = () => {
  if (!currentSettlement.value) return
  adjustForm.adjustment_amount = currentSettlement.value.adjustment_amount || 0
  adjustForm.reason = ''
  adjustDialogVisible.value = true
}

const submitAdjust = async () => {
  if (!adjustFormRef.value || !currentSettlement.value) return
  await adjustFormRef.value.validate(async (valid) => {
    if (!valid) return

    adjusting.value = true
    try {
      const res = await adjustSettlement(currentSettlement.value.id, {
        adjustment_amount: adjustForm.adjustment_amount,
        reason: adjustForm.reason
      })
      if (res?.success) {
        ElMessage.success(t('settlements.adjustSuccess'))
        adjustDialogVisible.value = false
        await viewSettlement(currentSettlement.value)
        loadSettlements()
      }
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('common.operationFailed'))
    } finally {
      adjusting.value = false
    }
  })
}

const showGenerateDialog = () => {
  generateForm.supplier_id = null
  generateForm.period = []
  generateForm.notes = ''
  generateDialogVisible.value = true
}

const submitGenerate = async () => {
  if (!generateFormRef.value) return
  await generateFormRef.value.validate(async (valid) => {
    if (!valid) return

    generating.value = true
    try {
      const res = await generateSettlement({
        supplier_id: generateForm.supplier_id!,
        period_start: generateForm.period[0] + 'T00:00:00',
        period_end: generateForm.period[1] + 'T23:59:59',
        notes: generateForm.notes || undefined
      })
      if (res?.success) {
        ElMessage.success(t('settlements.generateSuccess', { count: res.total_sms_count ?? 0, amount: (res.total_cost ?? 0).toFixed(2) }))
        generateDialogVisible.value = false
        loadSettlements()
      }
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('settlements.generateFailed'))
    } finally {
      generating.value = false
    }
  })
}

const viewSettlement = async (row: Settlement) => {
  try {
    const res = await getSettlementDetail(row.id)
    if (res?.success) {
      currentSettlement.value = res.settlement
      detailDrawerVisible.value = true
    }
  } catch (error) {
    ElMessage.error(t('settlements.loadDetailFailed'))
  }
}

const handleConfirm = async (row: Settlement) => {
  try {
    await ElMessageBox.confirm(t('settlements.confirmSettlementPrompt'), t('common.confirm'), { type: 'warning' })
    await confirmSettlement(row.id)
    ElMessage.success(t('settlements.settlementConfirmed'))
    loadSettlements()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || t('common.operationFailed'))
    }
  }
}

const handlePay = (row: Settlement) => {
  payingSettlement.value = row
  payForm.payment_method = ''
  payForm.payment_reference = ''
  payForm.notes = ''
  payDialogVisible.value = true
}

const submitPay = async () => {
  if (!payFormRef.value || !payingSettlement.value) return
  await payFormRef.value.validate(async (valid) => {
    if (!valid) return

    paying.value = true
    try {
      await paySettlement(payingSettlement.value!.id, payForm)
      ElMessage.success(t('settlements.paymentSuccess'))
      payDialogVisible.value = false
      loadSettlements()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('settlements.paymentFailed'))
    } finally {
      paying.value = false
    }
  })
}

const handleCancel = async (row: Settlement) => {
  try {
    const { value } = await ElMessageBox.prompt(t('settlements.enterCancelReason'), t('settlements.cancelSettlement'), {
      inputPattern: /.+/,
      inputErrorMessage: t('settlements.enterCancelReason')
    })
    await cancelSettlement(row.id, value)
    ElMessage.success(t('settlements.settlementCancelled'))
    loadSettlements()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || t('common.operationFailed'))
    }
  }
}

const loadProfitReport = async () => {
  if (!profitFilters.dateRange || profitFilters.dateRange.length !== 2) {
    ElMessage.warning(t('profit.selectDateRange'))
    return
  }

  profitLoading.value = true
  try {
    const res = await getProfitReport({
      start_date: profitFilters.dateRange[0],
      end_date: profitFilters.dateRange[1],
      group_by: profitFilters.group_by as any,
      supplier_id: profitFilters.supplier_id || undefined
    })
    if (res?.success) {
      profitSummary.value = res.summary
      profitData.value = res.data || []
    }
  } catch (error) {
    console.error('Failed to load profit report:', error)
  } finally {
    profitLoading.value = false
  }
}

const loadAccountOptions = async () => {
  try {
    const res = await getAccountsAdmin({ limit: 200 })
    if (res?.success && res?.accounts) {
      accountOptions.value = res.accounts.map((a: any) => ({
        id: a.id,
        account_name: a.account_name || a.email || '-',
        email: a.email || ''
      }))
    }
  } catch (error) {
    console.error('Failed to load accounts:', error)
  }
}

const showBillGenerateDialog = () => {
  billGenerateForm.account_id = null
  billGenerateForm.period = []
  billGenerateForm.due_days = 30
  billGenerateVisible.value = true
}

const submitBillGenerate = async () => {
  if (!billGenerateFormRef.value) return
  await billGenerateFormRef.value.validate(async (valid) => {
    if (!valid) return

    billGenerating.value = true
    try {
      const res = await generateCustomerBill({
        account_id: billGenerateForm.account_id!,
        period_start: billGenerateForm.period[0] + 'T00:00:00',
        period_end: billGenerateForm.period[1] + 'T23:59:59',
        due_days: billGenerateForm.due_days
      })
      if (res?.success) {
        ElMessage.success(t('settlements.billGenerateSuccess'))
        billGenerateVisible.value = false
        loadBills()
      }
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('settlements.billGenerateFailed'))
    } finally {
      billGenerating.value = false
    }
  })
}

const viewBill = async (row: any) => {
  try {
    const res = await getCustomerBillDetail(row.id)
    if (res?.success && res?.bill) {
      currentBill.value = res.bill
      billDetailVisible.value = true
    }
  } catch (error) {
    ElMessage.error(t('settlements.loadBillDetailFailed'))
  }
}

const openBillPay = (row: any) => {
  currentBill.value = row
  billPayForm.amount = row.outstanding_amount || 0
  billPayForm.payment_method = ''
  billPayForm.payment_reference = ''
  billPayForm.notes = ''
  billPayVisible.value = true
}

const showBillPayDialog = () => {
  if (!currentBill.value) return
  billPayForm.amount = currentBill.value.outstanding_amount || 0
  billPayForm.payment_method = ''
  billPayForm.payment_reference = ''
  billPayForm.notes = ''
  billPayVisible.value = true
}

const submitBillPay = async () => {
  if (!billPayFormRef.value || !currentBill.value) return
  await billPayFormRef.value.validate(async (valid) => {
    if (!valid) return

    billPaying.value = true
    try {
      const res = await payCustomerBill(currentBill.value.id, {
        amount: billPayForm.amount,
        payment_method: billPayForm.payment_method || undefined,
        payment_reference: billPayForm.payment_reference || undefined,
        notes: billPayForm.notes || undefined
      })
      if (res?.success) {
        ElMessage.success(t('settlements.paymentSuccess'))
        billPayVisible.value = false
        loadBills()
        if (billDetailVisible.value) {
          await viewBill(currentBill.value)
        }
      }
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('settlements.paymentFailed'))
    } finally {
      billPaying.value = false
    }
  })
}

const loadBills = async () => {
  billsLoading.value = true
  try {
    const res = await getCustomerBills({
      page: billPagination.page,
      page_size: billPagination.pageSize,
      account_id: billFilters.account_id || undefined,
      status: billFilters.status || undefined
    })
    if (res?.success) {
      bills.value = res.bills || []
      billPagination.total = res.total ?? 0
    }
  } catch (error) {
    console.error('Failed to load bills:', error)
  } finally {
    billsLoading.value = false
  }
}

const loadSalesOptions = async () => {
  try {
    const res = await request.get('/admin/users?role=sales')
    if (res?.success && res?.users) {
      salesOptions.value = res.users
    }
  } catch (error) {
    console.error('Failed to load sales:', error)
  }
}

const loadCommissionSummary = async () => {
  try {
    const res = await getCommissionSummary({
      sales_id: commissionFilters.sales_id || undefined,
      status: commissionFilters.status || undefined,
      start_date: commissionFilters.dateRange?.[0],
      end_date: commissionFilters.dateRange?.[1]
    })
    if (res?.success && res?.summary) {
      commissionSummary.value = res.summary
    }
  } catch (error) {
    console.error('Failed to load commission summary:', error)
  }
}

const loadCommissionSettlements = async () => {
  commissionLoading.value = true
  try {
    const res = await getCommissionSettlements({
      page: commissionPagination.page,
      page_size: commissionPagination.pageSize,
      sales_id: commissionFilters.sales_id || undefined,
      status: commissionFilters.status || undefined,
      start_date: commissionFilters.dateRange?.[0],
      end_date: commissionFilters.dateRange?.[1]
    })
    if (res?.success) {
      commissionSettlements.value = res.settlements || []
      commissionPagination.total = res.total ?? 0
    }
    await loadCommissionSummary()
  } catch (error) {
    console.error('Failed to load commission settlements:', error)
  } finally {
    commissionLoading.value = false
  }
}

const showCommissionGenerateDialog = () => {
  commissionGenerateForm.sales_id = null
  commissionGenerateForm.period = ''
  commissionGenerateVisible.value = true
}

const submitCommissionGenerate = async () => {
  if (!commissionGenerateFormRef.value) return
  await commissionGenerateFormRef.value.validate(async (valid) => {
    if (!valid) return

    commissionGenerating.value = true
    try {
      const [year, month] = commissionGenerateForm.period.split('-').map(Number)
      const res = await generateCommissionSettlement({
        sales_id: commissionGenerateForm.sales_id!,
        year,
        month
      })
      if (res?.success) {
        ElMessage.success(t('settlements.commissionGenerateSuccess'))
        commissionGenerateVisible.value = false
        loadCommissionSettlements()
      }
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('settlements.commissionGenerateFailed'))
    } finally {
      commissionGenerating.value = false
    }
  })
}

const viewCommissionSettlement = async (row: any) => {
  try {
    const res = await getCommissionSettlementDetail(row.id)
    if (res?.success && res?.settlement) {
      currentCommissionSettlement.value = res.settlement
      commissionDetailVisible.value = true
    }
  } catch (error) {
    ElMessage.error(t('settlements.loadDetailFailed'))
  }
}

const handleConfirmCommission = async (row: any) => {
  try {
    await ElMessageBox.confirm(t('settlements.confirmCommissionPrompt'), t('common.confirm'), { type: 'warning' })
    await confirmCommissionSettlement(row.id)
    ElMessage.success(t('settlements.commissionConfirmed'))
    loadCommissionSettlements()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || t('common.operationFailed'))
    }
  }
}

const handlePayCommission = (row: any) => {
  payingCommissionSettlement.value = row
  commissionPayForm.payment_method = ''
  commissionPayForm.payment_reference = ''
  commissionPayForm.notes = ''
  commissionPayVisible.value = true
}

const submitCommissionPay = async () => {
  if (!commissionPayFormRef.value || !payingCommissionSettlement.value) return
  await commissionPayFormRef.value.validate(async (valid) => {
    if (!valid) return

    commissionPaying.value = true
    try {
      await payCommissionSettlement(payingCommissionSettlement.value!.id, commissionPayForm)
      ElMessage.success(t('settlements.paymentSuccess'))
      commissionPayVisible.value = false
      loadCommissionSettlements()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || t('settlements.paymentFailed'))
    } finally {
      commissionPaying.value = false
    }
  })
}

const handleCancelCommission = async (row: any) => {
  try {
    const { value } = await ElMessageBox.prompt(t('settlements.enterCancelReason'), t('settlements.cancelSettlement'), {
      inputPattern: /.+/,
      inputErrorMessage: t('settlements.enterCancelReason')
    })
    await cancelCommissionSettlement(row.id, value)
    ElMessage.success(t('settlements.settlementCancelled'))
    loadCommissionSettlements()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || t('common.operationFailed'))
    }
  }
}

watch(activeTab, (tab) => {
  if (tab === 'bills') loadBills()
  if (tab === 'commission') {
    loadCommissionSettlements()
    loadSalesOptions()
  }
})

onMounted(() => {
  loadSuppliers()
  loadSettlements()
  loadAccountOptions()
})
</script>

<style scoped>
.settlements-page {
  width: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.main-tabs {
  margin-top: 20px;
}

.filter-card {
  margin-bottom: 20px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.table-card {
  margin-bottom: 20px;
}

.table-card :deep(.el-card__body) {
  overflow-x: auto;
}

.responsive-table {
  min-width: 800px;
}


.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.text-success {
  color: var(--el-color-success);
}

.text-danger {
  color: var(--el-color-danger);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.summary-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 20px;
  text-align: center;
  border: 1px solid var(--border-default);
}

.summary-label {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.summary-value {
  font-size: 24px;
  font-weight: 600;
}

.settlement-detail {
  padding: 10px;
}

.tab-header {
  display: flex;
  margin-bottom: 16px;
}

/* 自适应布局 */
@media (max-width: 1200px) {
  .summary-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .summary-grid {
    grid-template-columns: 1fr;
  }

  .summary-value {
    font-size: 20px;
  }

  .filter-form :deep(.el-form-item) {
    margin-right: 0;
    margin-bottom: 8px;
  }

  .filter-form :deep(.el-form-item) {
    width: 100%;
  }

  .filter-form :deep(.el-form-item .el-select),
  .filter-form :deep(.el-form-item .el-date-editor) {
    width: 100% !important;
    min-width: 100%;
  }

  .table-card :deep(.el-table) {
    font-size: 12px;
  }

  .pagination-wrapper {
    justify-content: center;
  }
}

@media (max-width: 480px) {
  .page-title {
    font-size: 18px;
  }

  .summary-card {
    padding: 16px;
  }

  .summary-value {
    font-size: 18px;
  }
}
</style>
