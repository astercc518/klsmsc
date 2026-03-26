<template>
  <div class="settlements-page">
    <div class="page-header">
      <h2 class="page-title">{{ $t('menu.settlementManage') }}</h2>
      <el-button type="success" plain :loading="autoGenerating" @click="runAutoGenerateMonth">
        {{ $t('settlements.autoGenerateMonth') }}
      </el-button>
    </div>

    <!-- 标签页 -->
    <el-tabs v-model="activeTab" class="main-tabs">
      <!-- 供应商结算 -->
      <el-tab-pane :label="$t('settlements.supplierSettlement')" name="supplier">
        <!-- 筛选：结算月 + 供应商名称 + 查询 -->
        <el-card class="filter-card supplier-filter-card">
          <el-form :inline="true" :model="filters" class="filter-form supplier-filter-form">
            <el-form-item :label="$t('settlements.settlementMonth')">
              <el-date-picker
                v-model="filters.settlementMonth"
                type="month"
                value-format="YYYY-MM"
                :placeholder="$t('settlements.selectSettlementMonth')"
                clearable
                class="supplier-month-picker"
              />
            </el-form-item>
            <el-form-item :label="$t('settlements.supplierName')">
              <el-input
                v-model="filters.supplierKeyword"
                clearable
                :placeholder="$t('settlements.supplierNamePlaceholder')"
                class="supplier-name-input"
                @keyup.enter="loadSettlements"
              />
            </el-form-item>
            <el-form-item :label="$t('settlements.status')">
              <el-select v-model="filters.status" :placeholder="$t('common.all')" clearable style="width: 140px">
                <el-option :label="$t('settlements.draft')" value="draft" />
                <el-option :label="$t('settlements.pending')" value="pending" />
                <el-option :label="$t('settlements.confirmed')" value="confirmed" />
                <el-option :label="$t('settlements.paid')" value="paid" />
                <el-option :label="$t('settlements.cancelled')" value="cancelled" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadSettlements">{{ $t('common.search') }}</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 主操作：创建账单、导出 -->
        <div class="supplier-toolbar">
          <el-button type="primary" @click="showGenerateDialog">
            <el-icon><Plus /></el-icon>
            {{ $t('settlements.createBill') }}
          </el-button>
          <el-button @click="exportSupplierSettlementsCsv">
            <el-icon><Download /></el-icon>
            {{ $t('settlements.exportBill') }}
          </el-button>
        </div>

        <!-- 结算单列表 -->
        <el-card class="table-card">
          <el-table
            :data="settlements"
            v-loading="loading"
            stripe
            class="responsive-table supplier-settlement-table"
            @sort-change="onSupplierSortChange"
            @selection-change="onSupplierSelectionChange"
          >
            <el-table-column type="selection" width="48" fixed />
            <el-table-column prop="settlement_month" :label="$t('settlements.settlementMonth')" width="100" />
            <el-table-column prop="supplier_name" :label="$t('settlements.supplierName')" min-width="140" show-overflow-tooltip />
            <el-table-column prop="channel_count" :label="$t('settlements.channelCount')" width="92" align="center" />
            <el-table-column
              prop="total_sms_count"
              :label="$t('settlements.orderCount')"
              width="112"
              sortable="custom"
              align="right"
            />
            <el-table-column
              prop="final_amount"
              :label="$t('settlements.orderAmountCny')"
              width="140"
              sortable="custom"
              align="right"
            >
              <template #default="{ row }">
                {{ formatMoneyHighPrecision(row.final_amount) }}
              </template>
            </el-table-column>
            <el-table-column prop="notes" :label="$t('settlements.remarks')" min-width="120" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.notes || '—' }}
              </template>
            </el-table-column>
            <el-table-column prop="status" :label="$t('settlements.status')" width="100">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">
                  {{ statusMap[row.status] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.action')" min-width="268" fixed="right">
              <template #default="{ row }">
                <div class="settlement-table-actions">
                  <el-button type="primary" link size="small" @click="viewSettlement(row)">{{ $t('settlements.actionBill') }}</el-button>
                  <el-button type="primary" link size="small" @click="viewSettlement(row)">{{ $t('settlements.actionDetails') }}</el-button>
                  <el-button type="primary" link size="small" @click="exportOneSettlementRow(row)">{{ $t('settlements.actionDownload') }}</el-button>
                  <el-dropdown trigger="click" class="settlement-more-dropdown" @command="(cmd: string) => onSupplierRowMore(cmd, row)">
                    <span class="settlement-more-trigger">
                      <el-button type="primary" link size="small">
                        {{ $t('settlements.moreActions') }} <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                      </el-button>
                    </span>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item v-if="row.status === 'draft'" command="confirm">{{ $t('common.confirm') }}</el-dropdown-item>
                        <el-dropdown-item v-if="row.status === 'confirmed'" command="pay">{{ $t('settlements.paid') }}</el-dropdown-item>
                        <el-dropdown-item v-if="['draft', 'pending', 'confirmed'].includes(row.status)" command="cancel" divided>{{ $t('common.cancel') }}</el-dropdown-item>
                        <el-dropdown-item
                          v-if="['draft', 'pending', 'cancelled'].includes(row.status)"
                          command="delete"
                          divided
                        >
                          {{ $t('common.delete') }}
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
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

      <!-- 员工结算（原销售佣金） -->
      <el-tab-pane :label="$t('settlements.employeeSettlement')" name="employee">
        <el-card class="filter-card supplier-filter-card">
          <el-form :inline="true" :model="employeeFilters" class="filter-form supplier-filter-form">
            <el-form-item :label="$t('settlements.settlementMonth')">
              <el-date-picker
                v-model="employeeFilters.settlementMonth"
                type="month"
                value-format="YYYY-MM"
                :placeholder="$t('settlements.selectSettlementMonth')"
                clearable
                class="supplier-month-picker"
              />
            </el-form-item>
            <el-form-item :label="$t('settlements.employeeName')">
              <el-input
                v-model="employeeFilters.salesKeyword"
                clearable
                :placeholder="$t('settlements.employeeNamePlaceholder')"
                class="supplier-name-input"
                @keyup.enter="loadCommissionSettlements"
              />
            </el-form-item>
            <el-form-item :label="$t('settlements.status')">
              <el-select v-model="employeeFilters.status" :placeholder="$t('common.all')" clearable style="width: 140px">
                <el-option :label="$t('settlements.draft')" value="draft" />
                <el-option :label="$t('settlements.confirmed')" value="confirmed" />
                <el-option :label="$t('settlements.paid')" value="paid" />
                <el-option :label="$t('settlements.cancelled')" value="cancelled" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadCommissionSettlements">{{ $t('common.search') }}</el-button>
            </el-form-item>
          </el-form>
        </el-card>
        <div class="supplier-toolbar">
          <el-button type="primary" @click="showCommissionGenerateDialog">
            <el-icon><Plus /></el-icon>
            {{ $t('settlements.createBill') }}
          </el-button>
          <el-button @click="exportEmployeeSettlementsCsv">
            <el-icon><Download /></el-icon>
            {{ $t('settlements.exportBill') }}
          </el-button>
        </div>
        <el-card class="table-card">
          <el-table
            :data="commissionSettlements"
            v-loading="commissionLoading"
            stripe
            class="responsive-table supplier-settlement-table"
            @sort-change="onEmployeeSortChange"
            @selection-change="onEmployeeSelectionChange"
          >
            <el-table-column type="selection" width="48" fixed />
            <el-table-column prop="settlement_month" :label="$t('settlements.settlementMonth')" width="100" />
            <el-table-column prop="sales_name" :label="$t('settlements.employeeName')" min-width="120" show-overflow-tooltip />
            <el-table-column prop="customer_count" :label="$t('settlements.clientCount')" width="92" align="center" />
            <el-table-column
              prop="total_sms_count"
              :label="$t('settlements.orderCount')"
              width="112"
              sortable="custom"
              align="right"
            />
            <el-table-column
              prop="total_cost"
              :label="$t('settlements.employeeCustomerCost')"
              width="120"
              sortable="custom"
              align="right"
            >
              <template #default="{ row }">{{ formatMoneyHighPrecision(row.total_cost ?? 0) }}</template>
            </el-table-column>
            <el-table-column
              prop="commission_amount"
              :label="$t('settlements.settlementAmount')"
              width="140"
              sortable="custom"
              align="right"
            >
              <template #default="{ row }">{{ formatMoneyHighPrecision(row.commission_amount) }}</template>
            </el-table-column>
            <el-table-column prop="notes" :label="$t('settlements.remarks')" min-width="100" show-overflow-tooltip>
              <template #default="{ row }">{{ row.notes || '—' }}</template>
            </el-table-column>
            <el-table-column prop="status" :label="$t('settlements.status')" width="100">
              <template #default="{ row }">
                <el-tag :type="commissionStatusTagType(row.status)" size="small">{{ commissionStatusMap[row.status] }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.action')" min-width="268" fixed="right">
              <template #default="{ row }">
                <div class="settlement-table-actions">
                  <el-button type="primary" link size="small" @click="viewCommissionSettlement(row)">{{ $t('settlements.actionBill') }}</el-button>
                  <el-button type="primary" link size="small" @click="viewCommissionSettlement(row)">{{ $t('settlements.actionDetails') }}</el-button>
                  <el-button type="primary" link size="small" @click="exportOneEmployeeRow(row)">{{ $t('settlements.actionDownload') }}</el-button>
                  <el-dropdown trigger="click" class="settlement-more-dropdown" @command="(cmd: string) => onEmployeeRowMore(cmd, row)">
                    <span class="settlement-more-trigger">
                      <el-button type="primary" link size="small">
                        {{ $t('settlements.moreActions') }} <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                      </el-button>
                    </span>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item v-if="row.status === 'draft'" command="confirm">{{ $t('common.confirm') }}</el-dropdown-item>
                        <el-dropdown-item v-if="row.status === 'confirmed'" command="pay">{{ $t('settlements.paid') }}</el-dropdown-item>
                        <el-dropdown-item v-if="['draft', 'confirmed'].includes(row.status)" command="cancel" divided>{{ $t('common.cancel') }}</el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
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

      <!-- 客户结算（原客户账单） -->
      <el-tab-pane :label="$t('settlements.customerSettlement')" name="customer">
        <el-card class="filter-card supplier-filter-card">
          <el-form :inline="true" :model="billFilters" class="filter-form supplier-filter-form">
            <el-form-item :label="$t('settlements.settlementMonth')">
              <el-date-picker
                v-model="billFilters.settlementMonth"
                type="month"
                value-format="YYYY-MM"
                :placeholder="$t('settlements.selectSettlementMonth')"
                clearable
                class="supplier-month-picker"
              />
            </el-form-item>
            <el-form-item :label="$t('settlements.customerNameCol')">
              <el-input
                v-model="billFilters.customerKeyword"
                clearable
                :placeholder="$t('settlements.customerNamePlaceholder')"
                class="supplier-name-input"
                @keyup.enter="loadBills"
              />
            </el-form-item>
            <el-form-item :label="$t('settlements.status')">
              <el-select v-model="billFilters.status" :placeholder="$t('common.all')" clearable style="width: 140px">
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
        <div class="supplier-toolbar">
          <el-button type="primary" @click="showBillGenerateDialog">
            <el-icon><Plus /></el-icon>
            {{ $t('settlements.createBill') }}
          </el-button>
          <el-button @click="exportCustomerBillsCsv">
            <el-icon><Download /></el-icon>
            {{ $t('settlements.exportBill') }}
          </el-button>
        </div>
        <el-card class="table-card">
          <el-table
            :data="bills"
            v-loading="billsLoading"
            stripe
            class="responsive-table supplier-settlement-table"
            @sort-change="onCustomerSortChange"
            @selection-change="onCustomerSelectionChange"
          >
            <el-table-column type="selection" width="48" fixed />
            <el-table-column prop="settlement_month" :label="$t('settlements.settlementMonth')" width="100" />
            <el-table-column prop="account_name" :label="$t('settlements.customerNameCol')" min-width="120" show-overflow-tooltip />
            <el-table-column prop="country_count" :label="$t('settlements.countryCount')" width="92" align="center" />
            <el-table-column
              prop="total_sms_count"
              :label="$t('settlements.orderCount')"
              width="112"
              sortable="custom"
              align="right"
            />
            <el-table-column
              prop="total_amount"
              :label="$t('settlements.settlementAmount')"
              width="140"
              sortable="custom"
              align="right"
            >
              <template #default="{ row }">{{ formatMoneyHighPrecision(row.total_amount) }}</template>
            </el-table-column>
            <el-table-column prop="notes" :label="$t('settlements.remarks')" min-width="100" show-overflow-tooltip>
              <template #default="{ row }">{{ row.notes || '—' }}</template>
            </el-table-column>
            <el-table-column prop="status" :label="$t('settlements.status')" width="100">
              <template #default="{ row }">
                <el-tag :type="billStatusTagType(row.status)" size="small">{{ billStatusMap[row.status] }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="$t('common.action')" width="200" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="viewBill(row)">{{ $t('settlements.actionBill') }}</el-button>
                <el-button type="primary" link size="small" @click="viewBill(row)">{{ $t('settlements.actionDetails') }}</el-button>
                <el-button type="primary" link size="small" @click="exportOneCustomerBillRow(row)">{{ $t('settlements.actionDownload') }}</el-button>
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
          <el-descriptions-item :label="$t('settlements.commissionRevenue')">{{ formatMoney(currentCommissionSettlement.total_revenue) }}</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.employeeCustomerCost')">{{ formatMoney(currentCommissionSettlement.total_cost ?? 0) }}</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.grossProfitForCommission')">{{ formatMoney((currentCommissionSettlement.total_revenue ?? 0) - (currentCommissionSettlement.total_cost ?? 0)) }}</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.commissionRate')">{{ currentCommissionSettlement.commission_rate }}%</el-descriptions-item>
          <el-descriptions-item :label="$t('settlements.commissionAmount')">
            <strong>{{ formatMoney(currentCommissionSettlement.commission_amount) }}</strong>
          </el-descriptions-item>
        </el-descriptions>
        <el-divider>{{ $t('settlements.details') }}</el-divider>
        <el-table :data="currentCommissionSettlement.details" size="small" max-height="250">
          <el-table-column prop="account_name" :label="$t('settlements.customer')" width="120" />
          <el-table-column prop="total_sms_count" :label="$t('settlements.smsCount')" width="80" />
          <el-table-column prop="total_cost" :label="$t('settlements.employeeCustomerCost')" width="100">
            <template #default="{ row }">{{ formatMoney(row.total_cost ?? 0) }}</template>
          </el-table-column>
          <el-table-column prop="total_revenue" :label="$t('settlements.commissionRevenue')" width="100">
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
import { Plus, Download, ArrowDown } from '@element-plus/icons-vue'
import {
  getSettlements, generateSettlement, getSettlementDetail,
  confirmSettlement, paySettlement, cancelSettlement, adjustSettlement, deleteSettlement,
  getCustomerBills, getCustomerBillDetail, payCustomerBill, generateCustomerBill,
  getCommissionSettlements, generateCommissionSettlement,
  getCommissionSettlementDetail, confirmCommissionSettlement, payCommissionSettlement, cancelCommissionSettlement,
  autoGenerateMonthSettlements,
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
/** 订单金额等展示 5 位小数（与参考样式一致） */
const formatMoneyHighPrecision = (value: number) => {
  const n = Number(value)
  if (Number.isNaN(n)) return '0.00000'
  return n.toFixed(5)
}
const formatDate = (date?: string) => date ? date.split('T')[0] : '-'
const formatTime = (time?: string) => time ? new Date(time).toLocaleString('zh-CN') : '-'

/** 本月 [月初, 月末]，按本地时区日历；勿用 toISOString()（UTC）否则东八区等会出现跨月错位 */
const getCurrentMonthRange = (): [string, string] => {
  const now = new Date()
  const y = now.getFullYear()
  const m = now.getMonth()
  const pad = (n: number) => String(n).padStart(2, '0')
  const start = new Date(y, m, 1)
  const end = new Date(y, m + 1, 0)
  const fmt = (d: Date) =>
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  return [fmt(start), fmt(end)]
}

/** 当前年月 YYYY-MM（用于供应商结算默认筛选） */
const getCurrentMonthYyyyMm = (): string => {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`
}

/** YYYY-MM -> [月初, 月末] 字符串，供生成结算单日期范围 */
const monthYmToDateRange = (ym: string): string[] => {
  const parts = ym.split('-')
  const y = parseInt(parts[0], 10)
  const m = parseInt(parts[1], 10)
  if (!y || !m) return [...getCurrentMonthRange()]
  const pad = (n: number) => String(n).padStart(2, '0')
  const lastDay = new Date(y, m, 0).getDate()
  return [`${y}-${pad(m)}-01`, `${y}-${pad(m)}-${pad(lastDay)}`]
}

// 数据
const activeTab = ref('supplier')
const loading = ref(false)
/** 一键批量生成当月结算（供应商+员工+客户） */
const autoGenerating = ref(false)
const settlements = ref<Settlement[]>([])
const supplierOptions = ref<any[]>([])
const filters = reactive({
  /** 结算月 YYYY-MM */
  settlementMonth: getCurrentMonthYyyyMm(),
  supplierKeyword: '',
  status: '',
})
const supplierTableSort = reactive({
  sort_by: 'created_at' as 'created_at' | 'total_sms_count' | 'final_amount',
  sort_order: 'desc' as 'asc' | 'desc',
})
const selectedSupplierRows = ref<Settlement[]>([])
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

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

// 客户账单
const billsLoading = ref(false)
const billFilters = reactive({
  settlementMonth: getCurrentMonthYyyyMm(),
  customerKeyword: '',
  status: '',
})
const bills = ref<any[]>([])
const billPagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})
const customerTableSort = reactive({
  sort_by: 'created_at' as 'created_at' | 'total_sms_count' | 'total_amount',
  sort_order: 'desc' as 'asc' | 'desc',
})
const selectedCustomerRows = ref<any[]>([])
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

// 员工结算（销售佣金）
const commissionLoading = ref(false)
const commissionSettlements = ref<any[]>([])
const employeeFilters = reactive({
  settlementMonth: getCurrentMonthYyyyMm(),
  salesKeyword: '',
  status: '',
})
const employeeTableSort = reactive({
  sort_by: 'created_at' as 'created_at' | 'total_sms_count' | 'commission_amount' | 'total_cost',
  sort_order: 'desc' as 'asc' | 'desc',
})
const selectedEmployeeRows = ref<any[]>([])
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

const loadSettlements = async () => {
  loading.value = true
  try {
    const res = await getSettlements({
      page: pagination.page,
      page_size: pagination.pageSize,
      settlement_month: filters.settlementMonth || undefined,
      supplier_keyword: filters.supplierKeyword?.trim() || undefined,
      status: filters.status || undefined,
      sort_by: supplierTableSort.sort_by,
      sort_order: supplierTableSort.sort_order,
    })
    if (res?.success) {
      settlements.value = res.settlements || []
      pagination.total = res.total ?? 0
    }
  } catch (error) {
    console.error('Failed to load settlements:', error)
  } finally {
    loading.value = false
  }
}

/** 表格排序（后端排序） */
const onSupplierSortChange = (payload: { prop: string; order: string | null }) => {
  const { prop, order } = payload
  if (!order) {
    supplierTableSort.sort_by = 'created_at'
    supplierTableSort.sort_order = 'desc'
  } else {
    const map: Record<string, 'created_at' | 'total_sms_count' | 'final_amount'> = {
      total_sms_count: 'total_sms_count',
      final_amount: 'final_amount',
    }
    supplierTableSort.sort_by = map[prop] || 'created_at'
    supplierTableSort.sort_order = order === 'ascending' ? 'asc' : 'desc'
  }
  pagination.page = 1
  loadSettlements()
}

const onSupplierSelectionChange = (rows: Settlement[]) => {
  selectedSupplierRows.value = rows
}

const csvEscape = (s: string) => {
  if (s.includes(',') || s.includes('"') || s.includes('\n') || s.includes('\r')) {
    return `"${s.replace(/"/g, '""')}"`
  }
  return s
}

/** 导出当前列表或勾选行为 CSV */
const exportSupplierSettlementsCsv = () => {
  const rows =
    selectedSupplierRows.value.length > 0 ? selectedSupplierRows.value : settlements.value
  if (!rows.length) {
    ElMessage.warning(t('settlements.exportEmpty'))
    return
  }
  const headers = [
    t('settlements.settlementMonth'),
    t('settlements.supplierName'),
    t('settlements.channelCount'),
    t('settlements.orderCount'),
    t('settlements.orderAmountCny'),
    t('settlements.remarks'),
    t('settlements.status'),
    t('settlements.settlementNo'),
  ]
  const lines = rows.map((r) =>
    [
      r.settlement_month || '',
      csvEscape(r.supplier_name || ''),
      String(r.channel_count ?? ''),
      String(r.total_sms_count ?? ''),
      formatMoneyHighPrecision(r.final_amount),
      csvEscape(r.notes || ''),
      csvEscape(String(statusMap.value[r.status] || r.status)),
      r.settlement_no || '',
    ].join(',')
  )
  const bom = '\ufeff'
  const csv = bom + headers.join(',') + '\n' + lines.join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `supplier_settlements_${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success(t('settlements.exportCsvSuccess'))
}

const exportOneSettlementRow = (row: Settlement) => {
  const prev = selectedSupplierRows.value
  selectedSupplierRows.value = [row]
  exportSupplierSettlementsCsv()
  selectedSupplierRows.value = prev
}

const onSupplierRowMore = (cmd: string, row: Settlement) => {
  if (cmd === 'confirm') handleConfirm(row)
  else if (cmd === 'pay') handlePay(row)
  else if (cmd === 'cancel') handleCancel(row)
  else if (cmd === 'delete') handleDeleteSupplierSettlement(row)
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
  generateForm.notes = ''
  const ym = filters.settlementMonth || getCurrentMonthYyyyMm()
  generateForm.period = monthYmToDateRange(ym)
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

/** 删除供应商结算单（草稿/待确认/已取消） */
const handleDeleteSupplierSettlement = async (row: Settlement) => {
  try {
    await ElMessageBox.confirm(
      t('settlements.deleteSettlementConfirm', { no: row.settlement_no || row.id }),
      t('common.delete'),
      { type: 'warning', confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel') }
    )
  } catch {
    return
  }
  try {
    const res = await deleteSettlement(row.id) as { success?: boolean }
    if (res?.success) {
      ElMessage.success(t('settlements.deleteSettlementSuccess'))
      loadSettlements()
      if (currentSettlement.value?.id === row.id) {
        detailDrawerVisible.value = false
      }
    }
  } catch (error: any) {
    const msg = error?.response?.data?.detail
    ElMessage.error(typeof msg === 'string' ? msg : t('common.operationFailed'))
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
  billGenerateForm.due_days = 30
  const ym = billFilters.settlementMonth || getCurrentMonthYyyyMm()
  billGenerateForm.period = monthYmToDateRange(ym)
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
      settlement_month: billFilters.settlementMonth || undefined,
      account_keyword: billFilters.customerKeyword?.trim() || undefined,
      status: billFilters.status || undefined,
      sort_by: customerTableSort.sort_by,
      sort_order: customerTableSort.sort_order,
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

/** 一键为当前自然月批量生成供应商/员工/客户结算（后端已存在或无数据则跳过） */
const runAutoGenerateMonth = async () => {
  try {
    await ElMessageBox.confirm(
      t('settlements.autoGenerateMonthConfirm'),
      t('settlements.autoGenerateMonth'),
      { type: 'warning', confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel') }
    )
  } catch {
    return
  }
  autoGenerating.value = true
  try {
    const now = new Date()
    const res = (await autoGenerateMonthSettlements({
      year: now.getFullYear(),
      month: now.getMonth() + 1,
    })) as {
      success?: boolean
      suppliers?: { created: number; skipped: number; failed: number }
      employees?: { created: number; skipped: number; failed: number }
      customers?: { created: number; skipped: number; failed: number }
    }
    if (res?.success) {
      const s = res.suppliers || { created: 0, skipped: 0, failed: 0 }
      const e = res.employees || { created: 0, skipped: 0, failed: 0 }
      const c = res.customers || { created: 0, skipped: 0, failed: 0 }
      ElMessage.success(
        t('settlements.autoGenerateMonthResult', {
          sy: s.created,
          sn: s.skipped,
          sf: s.failed,
          ey: e.created,
          en: e.skipped,
          ef: e.failed,
          cy: c.created,
          cn: c.skipped,
          cf: c.failed,
        })
      )
      await loadSettlements()
      await loadCommissionSettlements()
      await loadBills()
    }
  } catch (error) {
    console.error(error)
    ElMessage.error(t('common.operationFailed'))
  } finally {
    autoGenerating.value = false
  }
}

const onCustomerSortChange = (payload: { prop: string; order: string | null }) => {
  const { prop, order } = payload
  if (!order) {
    customerTableSort.sort_by = 'created_at'
    customerTableSort.sort_order = 'desc'
  } else {
    const map: Record<string, 'created_at' | 'total_sms_count' | 'total_amount'> = {
      total_sms_count: 'total_sms_count',
      total_amount: 'total_amount',
    }
    customerTableSort.sort_by = map[prop] || 'created_at'
    customerTableSort.sort_order = order === 'ascending' ? 'asc' : 'desc'
  }
  billPagination.page = 1
  loadBills()
}

const onCustomerSelectionChange = (rows: any[]) => {
  selectedCustomerRows.value = rows
}

const exportCustomerBillsCsv = () => {
  const rows = selectedCustomerRows.value.length > 0 ? selectedCustomerRows.value : bills.value
  if (!rows.length) {
    ElMessage.warning(t('settlements.exportEmpty'))
    return
  }
  const headers = [
    t('settlements.settlementMonth'),
    t('settlements.customerNameCol'),
    t('settlements.countryCount'),
    t('settlements.orderCount'),
    t('settlements.settlementAmount'),
    t('settlements.remarks'),
    t('settlements.status'),
    t('settlements.billNo'),
  ]
  const lines = rows.map((r) =>
    [
      r.settlement_month || '',
      csvEscape(r.account_name || ''),
      String(r.country_count ?? ''),
      String(r.total_sms_count ?? ''),
      formatMoneyHighPrecision(r.total_amount),
      csvEscape(r.notes || ''),
      csvEscape(String(billStatusMap.value[r.status] || r.status)),
      r.bill_no || '',
    ].join(',')
  )
  const bom = '\ufeff'
  const csv = bom + headers.join(',') + '\n' + lines.join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `customer_bills_${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success(t('settlements.exportCsvSuccess'))
}

const exportOneCustomerBillRow = (row: any) => {
  const prev = selectedCustomerRows.value
  selectedCustomerRows.value = [row]
  exportCustomerBillsCsv()
  selectedCustomerRows.value = prev
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

const loadCommissionSettlements = async () => {
  commissionLoading.value = true
  try {
    const res = await getCommissionSettlements({
      page: commissionPagination.page,
      page_size: commissionPagination.pageSize,
      settlement_month: employeeFilters.settlementMonth || undefined,
      sales_keyword: employeeFilters.salesKeyword?.trim() || undefined,
      status: employeeFilters.status || undefined,
      sort_by: employeeTableSort.sort_by,
      sort_order: employeeTableSort.sort_order,
    })
    if (res?.success) {
      commissionSettlements.value = res.settlements || []
      commissionPagination.total = res.total ?? 0
    }
  } catch (error) {
    console.error('Failed to load commission settlements:', error)
  } finally {
    commissionLoading.value = false
  }
}

const onEmployeeSortChange = (payload: { prop: string; order: string | null }) => {
  const { prop, order } = payload
  if (!order) {
    employeeTableSort.sort_by = 'created_at'
    employeeTableSort.sort_order = 'desc'
  } else {
    const map: Record<string, 'created_at' | 'total_sms_count' | 'commission_amount' | 'total_cost'> = {
      total_sms_count: 'total_sms_count',
      commission_amount: 'commission_amount',
      total_cost: 'total_cost',
    }
    employeeTableSort.sort_by = map[prop] || 'created_at'
    employeeTableSort.sort_order = order === 'ascending' ? 'asc' : 'desc'
  }
  commissionPagination.page = 1
  loadCommissionSettlements()
}

const onEmployeeSelectionChange = (rows: any[]) => {
  selectedEmployeeRows.value = rows
}

const exportEmployeeSettlementsCsv = () => {
  const rows =
    selectedEmployeeRows.value.length > 0 ? selectedEmployeeRows.value : commissionSettlements.value
  if (!rows.length) {
    ElMessage.warning(t('settlements.exportEmpty'))
    return
  }
  const headers = [
    t('settlements.settlementMonth'),
    t('settlements.employeeName'),
    t('settlements.clientCount'),
    t('settlements.orderCount'),
    t('settlements.employeeCustomerCost'),
    t('settlements.settlementAmount'),
    t('settlements.remarks'),
    t('settlements.status'),
    t('settlements.settlementNo'),
  ]
  const lines = rows.map((r) =>
    [
      r.settlement_month || '',
      csvEscape(r.sales_name || ''),
      String(r.customer_count ?? ''),
      String(r.total_sms_count ?? ''),
      formatMoneyHighPrecision(r.total_cost ?? 0),
      formatMoneyHighPrecision(r.commission_amount),
      csvEscape(r.notes || ''),
      csvEscape(String(commissionStatusMap.value[r.status] || r.status)),
      r.settlement_no || '',
    ].join(',')
  )
  const bom = '\ufeff'
  const csv = bom + headers.join(',') + '\n' + lines.join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `employee_settlements_${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success(t('settlements.exportCsvSuccess'))
}

const exportOneEmployeeRow = (row: any) => {
  const prev = selectedEmployeeRows.value
  selectedEmployeeRows.value = [row]
  exportEmployeeSettlementsCsv()
  selectedEmployeeRows.value = prev
}

const onEmployeeRowMore = (cmd: string, row: any) => {
  if (cmd === 'confirm') handleConfirmCommission(row)
  else if (cmd === 'pay') handlePayCommission(row)
  else if (cmd === 'cancel') handleCancelCommission(row)
}

const showCommissionGenerateDialog = () => {
  commissionGenerateForm.sales_id = null
  const ym = employeeFilters.settlementMonth || getCurrentMonthYyyyMm()
  commissionGenerateForm.period = ym
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
  if (tab === 'customer') loadBills()
  if (tab === 'employee') loadCommissionSettlements()
})

onMounted(() => {
  loadSuppliers()
  loadSettlements()
  loadAccountOptions()
  loadSalesOptions()
})
</script>

<style scoped>
.settlements-page {
  width: 100%;
}

.supplier-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.supplier-filter-card {
  margin-bottom: 12px;
}

.supplier-name-input {
  min-width: 200px;
}

.supplier-month-picker {
  min-width: 160px;
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

/* 操作列：flex 间距 + 取消 link 按钮默认负边距，避免「下载」与「更多」重叠 */
.settlement-table-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
}
.settlement-table-actions :deep(.el-button.is-link) {
  margin-left: 0 !important;
  margin-right: 0 !important;
  padding-left: 4px;
  padding-right: 4px;
}
.settlement-more-trigger {
  display: inline-flex;
  align-items: center;
}
.settlement-table-actions :deep(.settlement-more-dropdown) {
  flex-shrink: 0;
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
