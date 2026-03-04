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
        <!-- 搜索筛选 -->
        <el-card class="filter-card">
          <el-form :inline="true" :model="filters" class="filter-form">
            <el-form-item :label="$t('settlements.supplier')">
              <el-select v-model="filters.supplier_id" :placeholder="$t('common.all')" clearable>
                <el-option
                  v-for="s in supplierOptions"
                  :key="s.id"
                  :label="s.supplier_name"
                  :value="s.id"
                />
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
            <el-form-item>
              <el-button type="primary" @click="loadSettlements">{{ $t('common.search') }}</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 结算单列表 -->
        <el-card class="table-card">
          <el-table :data="settlements" v-loading="loading" stripe>
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
          <el-table :data="profitData" v-loading="profitLoading" stripe>
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

      <!-- 客户账单 -->
      <el-tab-pane :label="$t('settlements.customerBilling')" name="bills">
        <el-card class="filter-card">
          <el-form :inline="true" :model="billFilters" class="filter-form">
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
          <el-table :data="bills" v-loading="billsLoading" stripe>
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
          </el-table>
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  getSettlements, generateSettlement, getSettlementDetail,
  confirmSettlement, paySettlement, cancelSettlement,
  getProfitReport, getCustomerBills,
  type Settlement
} from '@/api/settlement'
import { getSuppliers } from '@/api/supplier'

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

const formatMoney = (value: number) => value?.toFixed(2) || '0.00'
const formatDate = (date?: string) => date ? date.split('T')[0] : '-'
const formatTime = (time?: string) => time ? new Date(time).toLocaleString('zh-CN') : '-'

// 数据
const activeTab = ref('supplier')
const loading = ref(false)
const settlements = ref<Settlement[]>([])
const supplierOptions = ref<any[]>([])
const filters = reactive({
  supplier_id: null as number | null,
  status: ''
})
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

// 利润报表
const profitLoading = ref(false)
const profitFilters = reactive({
  dateRange: [] as string[],
  group_by: 'day',
  supplier_id: null as number | null
})
const profitSummary = ref<any>(null)
const profitData = ref<any[]>([])

// 客户账单
const billsLoading = ref(false)
const billFilters = reactive({
  status: ''
})
const bills = ref<any[]>([])

// 方法
const loadSuppliers = async () => {
  try {
    const res = await getSuppliers({ page_size: 100 })
    if (res.data.success) {
      supplierOptions.value = res.data.suppliers
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
      supplier_id: filters.supplier_id || undefined,
      status: filters.status || undefined
    })
    if (res.data.success) {
      settlements.value = res.data.settlements
      pagination.total = res.data.total
    }
  } catch (error) {
    console.error('Failed to load settlements:', error)
  } finally {
    loading.value = false
  }
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
      if (res.data.success) {
        ElMessage.success(t('settlements.generateSuccess', { count: res.data.total_sms_count, amount: res.data.total_cost.toFixed(2) }))
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
    if (res.data.success) {
      currentSettlement.value = res.data.settlement
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
    if (res.data.success) {
      profitSummary.value = res.data.summary
      profitData.value = res.data.data
    }
  } catch (error) {
    console.error('Failed to load profit report:', error)
  } finally {
    profitLoading.value = false
  }
}

const loadBills = async () => {
  billsLoading.value = true
  try {
    const res = await getCustomerBills({
      status: billFilters.status || undefined
    })
    if (res.data.success) {
      bills.value = res.data.bills
    }
  } catch (error) {
    console.error('Failed to load bills:', error)
  } finally {
    billsLoading.value = false
  }
}

onMounted(() => {
  loadSuppliers()
  loadSettlements()
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
</style>
