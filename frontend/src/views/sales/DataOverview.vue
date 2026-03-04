<template>
  <div class="sales-data-overview">
    <div class="page-header">
      <h1>{{ t('salesData.title') }}</h1>
      <p class="subtitle">{{ t('salesData.subtitle') }}</p>
    </div>

    <el-tabs v-model="activeTab">
      <!-- 数据商品 -->
      <el-tab-pane :label="t('salesData.products')" name="products">
        <div class="toolbar">
          <el-select v-model="productTypeFilter" :placeholder="t('salesData.allTypes')" clearable style="width: 160px">
            <el-option label="纯数据" value="data_only" />
            <el-option label="组合套餐" value="combo" />
            <el-option label="买即发" value="data_and_send" />
          </el-select>
          <el-button @click="loadProducts">{{ t('common.refresh') }}</el-button>
        </div>
        <el-table :data="products" v-loading="loadingProducts" stripe>
          <el-table-column prop="product_code" :label="t('salesData.productCode')" width="120" />
          <el-table-column prop="product_name" :label="t('salesData.productName')" min-width="150" />
          <el-table-column :label="t('salesData.productType')" width="110">
            <template #default="{ row }">
              <el-tag :type="typeTagMap[row.product_type]?.type || 'info'" size="small">
                {{ typeTagMap[row.product_type]?.label || row.product_type }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="price_per_number" :label="t('salesData.unitPrice')" width="100" />
          <el-table-column prop="stock_count" :label="t('salesData.stock')" width="100" />
          <el-table-column :label="t('salesData.smsQuota')" width="100">
            <template #default="{ row }">{{ row.sms_quota || '-' }}</template>
          </el-table-column>
          <el-table-column :label="t('salesData.bundlePrice')" width="100">
            <template #default="{ row }">{{ row.bundle_price || '-' }}</template>
          </el-table-column>
          <el-table-column prop="total_sold" :label="t('salesData.totalSold')" width="100" />
        </el-table>
      </el-tab-pane>

      <!-- 客户订单 -->
      <el-tab-pane :label="t('salesData.orders')" name="orders">
        <div class="toolbar">
          <el-input v-model="orderAccountId" :placeholder="t('salesData.accountId')" clearable style="width: 140px" />
          <el-select v-model="orderStatus" :placeholder="t('salesData.allStatus')" clearable style="width: 120px">
            <el-option label="待处理" value="pending" />
            <el-option label="已完成" value="completed" />
            <el-option label="已取消" value="cancelled" />
          </el-select>
          <el-button type="primary" @click="loadOrders">{{ t('common.search') }}</el-button>
        </div>
        <el-table :data="orders" v-loading="loadingOrders" stripe>
          <el-table-column prop="order_no" :label="t('salesData.orderNo')" min-width="180">
            <template #default="{ row }"><span style="font-family: monospace; font-size: 12px">{{ row.order_no }}</span></template>
          </el-table-column>
          <el-table-column prop="account_name" :label="t('salesData.customer')" width="120" />
          <el-table-column prop="product_name" :label="t('salesData.product')" width="150" />
          <el-table-column :label="t('salesData.orderType')" width="110">
            <template #default="{ row }">
              <el-tag :type="typeTagMap[row.order_type]?.type || 'info'" size="small">
                {{ typeTagMap[row.order_type]?.label || row.order_type }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="quantity" :label="t('salesData.quantity')" width="80" />
          <el-table-column prop="total_price" :label="t('salesData.totalPrice')" width="100" />
          <el-table-column prop="status" :label="t('common.status')" width="90">
            <template #default="{ row }">
              <el-tag :type="statusMap[row.status] || 'info'" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" :label="t('salesData.createdAt')" width="160">
            <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}</template>
          </el-table-column>
        </el-table>
        <div class="pagination-wrapper">
          <el-pagination v-model:current-page="orderPage" :page-size="20" :total="orderTotal"
            layout="total, prev, pager, next" @current-change="loadOrders" />
        </div>
      </el-tab-pane>

      <!-- 客户概况 -->
      <el-tab-pane :label="t('salesData.customers')" name="customers">
        <el-button @click="loadCustomers" style="margin-bottom: 16px">{{ t('common.refresh') }}</el-button>
        <el-table :data="customers" v-loading="loadingCustomers" stripe>
          <el-table-column prop="account_id" :label="t('salesData.accountId')" width="100" />
          <el-table-column prop="account_name" :label="t('salesData.accountName')" min-width="150" />
          <el-table-column prop="email" :label="t('salesData.email')" min-width="180" />
          <el-table-column prop="order_count" :label="t('salesData.orderCount')" width="100" />
          <el-table-column prop="total_numbers" :label="t('salesData.totalNumbers')" width="120" />
        </el-table>
        <div class="pagination-wrapper">
          <el-pagination v-model:current-page="customerPage" :page-size="20" :total="customerTotal"
            layout="total, prev, pager, next" @current-change="loadCustomers" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { getSalesProducts, getSalesOrders, getSalesCustomers } from '@/api/data-sales'

const { t } = useI18n()

const activeTab = ref('products')

const typeTagMap: Record<string, { type: string; label: string }> = {
  data_only: { type: '', label: '纯数据' },
  combo: { type: 'success', label: '组合套餐' },
  data_and_send: { type: 'warning', label: '买即发' },
}

const statusMap: Record<string, string> = {
  pending: 'warning',
  completed: 'success',
  cancelled: 'info',
  expired: 'danger',
}

// 商品
const loadingProducts = ref(false)
const products = ref<any[]>([])
const productTypeFilter = ref('')

async function loadProducts() {
  loadingProducts.value = true
  try {
    const res = await getSalesProducts({
      page: 1, page_size: 100,
      product_type: productTypeFilter.value || undefined,
    })
    products.value = res.items || []
  } catch (e) {
    console.error(e)
  } finally {
    loadingProducts.value = false
  }
}

// 订单
const loadingOrders = ref(false)
const orders = ref<any[]>([])
const orderPage = ref(1)
const orderTotal = ref(0)
const orderAccountId = ref('')
const orderStatus = ref('')

async function loadOrders() {
  loadingOrders.value = true
  try {
    const res = await getSalesOrders({
      page: orderPage.value, page_size: 20,
      status: orderStatus.value || undefined,
      account_id: orderAccountId.value ? parseInt(orderAccountId.value) : undefined,
    })
    orders.value = res.items || []
    orderTotal.value = res.total || 0
  } catch (e) {
    console.error(e)
  } finally {
    loadingOrders.value = false
  }
}

// 客户概况
const loadingCustomers = ref(false)
const customers = ref<any[]>([])
const customerPage = ref(1)
const customerTotal = ref(0)

async function loadCustomers() {
  loadingCustomers.value = true
  try {
    const res = await getSalesCustomers({ page: customerPage.value, page_size: 20 })
    customers.value = res.items || []
    customerTotal.value = res.total || 0
  } catch (e) {
    console.error(e)
  } finally {
    loadingCustomers.value = false
  }
}

onMounted(() => {
  loadProducts()
  loadOrders()
  loadCustomers()
})
</script>

<style scoped>
.sales-data-overview { width: 100%; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 600; margin: 0; }
.subtitle { color: var(--el-text-color-secondary); margin-top: 4px; font-size: 14px; }
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
.pagination-wrapper { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
