<template>
  <div class="data-store-container">
    <div class="header">
      <h2>{{ t('dataPool.publicPool') }}</h2>
      <div class="header-right">
        <el-button @click="$router.push('/data/my-numbers')">{{ t('dataPool.myPrivatePool') }}</el-button>
        <el-button type="primary" @click="refreshList">{{ t('dataPool.refreshList') }}</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane :label="t('dataPool.products')" name="products">
        <!-- 来源/用途/时效筛选 -->
        <div class="type-filter">
          <el-select v-model="sourceFilter" :placeholder="t('dataPool.allSource')" clearable @change="refreshList" style="width: 160px; margin-right: 12px;">
            <el-option v-for="opt in SOURCE_OPTIONS" :key="opt.value" :label="t(opt.labelKey)" :value="opt.value" />
          </el-select>
          <el-select v-model="purposeFilter" :placeholder="t('dataPool.allPurpose')" clearable @change="refreshList" style="width: 160px; margin-right: 12px;">
            <el-option v-for="opt in PURPOSE_OPTIONS" :key="opt.value" :label="t(opt.labelKey)" :value="opt.value" />
          </el-select>
          <el-select v-model="freshnessFilter" :placeholder="t('dataPool.allFreshness')" clearable @change="refreshList" style="width: 160px;">
            <el-option v-for="opt in FRESHNESS_OPTIONS" :key="opt.value" :label="t(opt.labelKey)" :value="opt.value" />
          </el-select>
        </div>

        <el-row :gutter="20">
          <el-col :span="8" v-for="product in filteredProducts" :key="product.id">
            <el-card class="box-card" shadow="hover">
              <template #header>
                <div class="card-header">
                  <span>{{ product.product_name }}</span>
                  <div class="card-header-tags">
                    <el-tag :type="productTypeTagType(product.product_type)" size="small">
                      {{ productTypeLabel(product.product_type) }}
                    </el-tag>
                    <el-tag type="success">${{ product.price_per_number }}{{ t('dataPool.pricePerNumber') }}</el-tag>
                  </div>
                </div>
              </template>
              <div class="text item">
                <p>{{ product.description }}</p>
                <p><strong>{{ t('dataPool.stock') }}:</strong> {{ product.stock_count }}</p>

                <!-- 组合套餐额外信息 -->
                <div v-if="product.product_type === 'combo'" class="combo-info">
                  <p>
                    <strong>{{ t('dataPool.smsQuota') }}:</strong> {{ product.sms_quota }}
                  </p>
                  <p class="price-compare">
                    <span class="original-price">${{ originalPrice(product) }}</span>
                    <span class="bundle-price">${{ product.bundle_price }}</span>
                    <el-tag type="danger" size="small" v-if="product.bundle_discount">
                      -{{ product.bundle_discount }}%
                    </el-tag>
                  </p>
                </div>

                <div class="criteria-tags">
                  <el-tag v-if="product.filter_criteria?.country" size="small">{{ product.filter_criteria.country }}</el-tag>
                  <el-tag v-if="product.filter_criteria?.carrier" size="small" type="info">{{ product.filter_criteria.carrier }}</el-tag>
                  <el-tag v-if="product.filter_criteria?.source" size="small" type="danger">{{ t('dataPool.source') }}: {{ sourceLabel(product.filter_criteria.source) }}</el-tag>
                  <el-tag v-if="product.filter_criteria?.purpose" size="small" type="warning">{{ t('dataPool.purpose') }}: {{ purposeLabel(product.filter_criteria.purpose) }}</el-tag>
                  <el-tag v-if="product.filter_criteria?.freshness" size="small" type="success">{{ t('dataPool.freshness') }}: {{ freshnessLabel(product.filter_criteria.freshness) }}</el-tag>
                  <el-tag v-for="tag in product.filter_criteria?.tags || []" :key="tag" size="small" type="warning">{{ tag }}</el-tag>
                </div>

                <div class="actions">
                  <template v-if="product.product_type === 'data_only'">
                    <el-button type="primary" @click="openBuyDialog(product, 'stock')">
                      {{ t('dataPool.buyToStock') }}
                    </el-button>
                  </template>
                  <template v-else-if="product.product_type === 'combo'">
                    <el-button type="success" @click="openBuyDialog(product, 'combo')">
                      {{ t('dataPool.buyCombo') }}
                    </el-button>
                  </template>
                  <template v-else-if="product.product_type === 'data_and_send'">
                    <el-button type="warning" @click="openBuyDialog(product, 'send')">
                      {{ t('dataPool.buyAndSend') }}
                    </el-button>
                  </template>
                </div>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <el-tab-pane :label="t('dataPool.customPick')" name="custom">
        <el-card>
          <el-form :inline="true" :model="customFilter" class="demo-form-inline">
            <el-form-item :label="t('dataPool.country')">
              <el-input v-model="customFilter.country" placeholder="Country Code" />
            </el-form-item>
            <el-form-item :label="t('dataPool.carrier')">
              <el-input v-model="customFilter.carrier" placeholder="Carrier" />
            </el-form-item>
            <el-form-item :label="t('dataPool.tag')">
              <el-input v-model="customFilter.tag" placeholder="Tag" />
            </el-form-item>
            <el-form-item :label="t('dataPool.source')">
              <el-input v-model="customFilter.source" placeholder="Source" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="checkCustomStock">{{ t('dataPool.checkStock') }}</el-button>
            </el-form-item>
          </el-form>

          <div v-if="customStock !== null" class="stock-result">
            <h3>{{ t('dataPool.availableStock') }}: <span class="highlight">{{ customStock }}</span></h3>
            <div class="actions" v-if="customStock > 0">
              <el-button type="success" @click="openCustomBuy('stock')">{{ t('dataPool.buyToStock') }}</el-button>
              <el-button type="primary" @click="openCustomBuy('send')">{{ t('dataPool.buyAndSend') }}</el-button>
            </div>
          </div>

          <div class="sample-list" v-if="customSamples.length">
            <h4>{{ t('dataPool.sampleData') }}:</h4>
            <el-table :data="customSamples" size="small" style="width: 100%">
              <el-table-column prop="country_code" :label="t('dataPool.country')" width="100" />
              <el-table-column prop="tags" :label="t('dataPool.tag')">
                <template #default="scope">{{ scope.row.tags?.join(', ') }}</template>
              </el-table-column>
              <el-table-column prop="status" :label="t('common.status')" width="100" />
            </el-table>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 购买弹窗 -->
    <el-dialog v-model="dialogVisible" :title="buyDialogTitle" width="50%">
      <el-form :model="form" label-width="120px">
        <el-form-item :label="t('dataPool.productFilter')">
          <span v-if="selectedProduct">{{ selectedProduct.product_name }}</span>
          <span v-else>{{ t('dataPool.customFilter') }} ({{ customSummary }})</span>
        </el-form-item>

        <!-- 组合套餐：展示包含的短信条数与折扣 -->
        <template v-if="selectedProduct?.product_type === 'combo'">
          <el-form-item :label="t('dataPool.smsQuota')">
            <span>{{ selectedProduct.sms_quota }} {{ t('dataPool.smsUnit') }}</span>
          </el-form-item>
          <el-form-item :label="t('dataPool.discount')">
            <el-tag type="danger" v-if="selectedProduct.bundle_discount">
              {{ t('dataPool.savePct', { pct: selectedProduct.bundle_discount }) }}
            </el-tag>
            <span v-else>-</span>
          </el-form-item>
        </template>

        <el-form-item :label="t('dataPool.unitPrice')">
          <span v-if="selectedProduct?.product_type === 'combo'">
            ${{ selectedProduct.bundle_price }} / {{ t('dataPool.perBundle') }}
          </span>
          <span v-else>${{ pricePerNumber }}</span>
        </el-form-item>

        <el-form-item :label="t('dataPool.quantity')">
          <el-input-number v-model="form.quantity" :min="100" :max="selectedProduct?.stock_count || customStock || 10000" />
        </el-form-item>

        <!-- 买即发类型需要短信内容 -->
        <el-form-item :label="t('dataPool.smsContent')" v-if="buyMode === 'send'">
          <el-input v-model="form.message" type="textarea" rows="4" :placeholder="t('dataPool.smsContentPlaceholder')" />
        </el-form-item>

        <el-form-item :label="t('dataPool.estimatedCost')">
          <span style="color: red; font-size: 18px; font-weight: bold;">
            ${{ estimatedCost }}
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" @click="handleBuyConfirm" :loading="loading">
            {{ buyConfirmText }}
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  getDataProducts, buyAndSend, buyToStock, buyCombo,
  previewDataSelection, type DataProduct
} from '@/api/data'
import { ElMessage } from 'element-plus'

const { t } = useI18n()
const products = ref<DataProduct[]>([])
const dialogVisible = ref(false)
const loading = ref(false)
const activeTab = ref('products')
const buyMode = ref<'send' | 'stock' | 'combo'>('stock')

// 筛选常量
const SOURCE_OPTIONS = [
  { value: 'credential', labelKey: 'dataPool.credential' },
  { value: 'penetration', labelKey: 'dataPool.penetration' },
  { value: 'social_eng', labelKey: 'dataPool.socialEng' },
  { value: 'telemarketing', labelKey: 'dataPool.telemarketing' },
  { value: 'otp', labelKey: 'dataPool.otp' },
]

const PURPOSE_OPTIONS = [
  { value: 'bc', labelKey: 'dataPool.bc' },
  { value: 'part_time', labelKey: 'dataPool.partTime' },
  { value: 'dating', labelKey: 'dataPool.dating' },
  { value: 'finance', labelKey: 'dataPool.financeUse' },
  { value: 'stock', labelKey: 'dataPool.stockUse' },
]

const FRESHNESS_OPTIONS = [
  { value: '3day', labelKey: 'dataPool.threeDay' },
  { value: '7day', labelKey: 'dataPool.sevenDay' },
  { value: '30day', labelKey: 'dataPool.thirtyDay' },
  { value: 'history', labelKey: 'dataPool.historical' },
]

// 来源/用途/时效筛选
const sourceFilter = ref('')
const purposeFilter = ref('')
const freshnessFilter = ref('')

const filteredProducts = computed(() => products.value)

// 选中的商品
const selectedProduct = ref<DataProduct | null>(null)

// 自定义筛选
const customFilter = reactive({
  country: '',
  carrier: '',
  tag: '',
  source: ''
})
const customStock = ref<number | null>(null)
const customSamples = ref([])

const form = reactive({
  quantity: 1000,
  message: ''
})

const pricePerNumber = computed(() => {
  return selectedProduct.value ? selectedProduct.value.price_per_number : '0.001'
})

const customSummary = computed(() => {
  return `${customFilter.country || 'Any'} | ${customFilter.carrier || 'Any'} | ${customFilter.tag || 'Any'}`
})

// 根据商品类型返回 tag 的颜色类型
function productTypeTagType(type: DataProduct['product_type']): '' | 'success' | 'warning' {
  const map: Record<string, '' | 'success' | 'warning'> = {
    data_only: '',
    combo: 'success',
    data_and_send: 'warning'
  }
  return map[type] ?? ''
}

// 根据商品类型返回展示标签文字
function productTypeLabel(type: DataProduct['product_type']): string {
  const map: Record<string, string> = {
    data_only: t('dataPool.typeDataOnly'),
    combo: t('dataPool.typeCombo'),
    data_and_send: t('dataPool.typeDataAndSend')
  }
  return map[type] ?? type
}

function sourceLabel(val: string): string {
  const opt = SOURCE_OPTIONS.find(o => o.value === val)
  return opt ? t(opt.labelKey) : val
}

function purposeLabel(val: string): string {
  const opt = PURPOSE_OPTIONS.find(o => o.value === val)
  return opt ? t(opt.labelKey) : val
}

function freshnessLabel(val: string): string {
  const opt = FRESHNESS_OPTIONS.find(o => o.value === val)
  return opt ? t(opt.labelKey) : val
}

// 组合套餐的原始总价（数据单价 × 短信条数 + 数据价格）
function originalPrice(product: DataProduct): string {
  const dataTotal = Number(product.price_per_number) * (product.sms_quota ?? 0)
    + Number(product.price_per_number)
  return dataTotal.toFixed(2)
}

// 弹窗标题
const buyDialogTitle = computed(() => {
  if (buyMode.value === 'combo') return t('dataPool.buyCombo')
  if (buyMode.value === 'send') return t('dataPool.buyAndSend')
  return t('dataPool.buyToStock')
})

// 弹窗确认按钮文字
const buyConfirmText = computed(() => {
  if (buyMode.value === 'combo') return t('dataPool.confirmBuyCombo')
  if (buyMode.value === 'send') return t('dataPool.confirmPayAndSend')
  return t('dataPool.confirmPay')
})

// 预估费用
const estimatedCost = computed(() => {
  if (selectedProduct.value?.product_type === 'combo') {
    return (Number(selectedProduct.value.bundle_price) * form.quantity).toFixed(2)
  }
  return (Number(pricePerNumber.value) * form.quantity).toFixed(2)
})

const refreshList = async () => {
  try {
    const res = await getDataProducts({
      source: sourceFilter.value || undefined,
      purpose: purposeFilter.value || undefined,
      freshness: freshnessFilter.value || undefined,
    })
    products.value = res.items || res.data
  } catch (error) {
    console.error(error)
  }
}

const checkCustomStock = async () => {
  const criteria = {
    country: customFilter.country || undefined,
    carrier: customFilter.carrier || undefined,
    tags: customFilter.tag ? [customFilter.tag] : undefined,
    source: customFilter.source || undefined
  }
  const res = await previewDataSelection(criteria)
  if (res.success) {
    customStock.value = res.total_count
    customSamples.value = res.samples
  }
}

const openBuyDialog = (product: DataProduct, mode: 'send' | 'stock' | 'combo') => {
  selectedProduct.value = product
  buyMode.value = mode
  form.quantity = 1000
  form.message = ''
  dialogVisible.value = true
}

const openCustomBuy = (mode: 'send' | 'stock') => {
  selectedProduct.value = null
  buyMode.value = mode
  form.quantity = 1000
  form.message = ''
  dialogVisible.value = true
}

const handleBuyConfirm = async () => {
  if (buyMode.value === 'send' && !form.message) {
    ElMessage.warning(t('dataPool.pleaseEnterSmsContent'))
    return
  }

  loading.value = true
  try {
    if (buyMode.value === 'combo') {
      // 组合套餐购买
      await buyCombo({
        product_id: selectedProduct.value!.id,
        quantity: form.quantity
      })
    } else if (buyMode.value === 'send') {
      // 买即发
      await buyAndSend({
        product_id: selectedProduct.value?.id,
        filter_criteria: !selectedProduct.value ? {
          country: customFilter.country || undefined,
          carrier: customFilter.carrier || undefined,
          tags: customFilter.tag ? [customFilter.tag] : undefined,
          source: customFilter.source || undefined
        } : undefined,
        quantity: form.quantity,
        message: form.message
      })
    } else {
      // 纯数据购买到私库
      await buyToStock({
        product_id: selectedProduct.value?.id,
        filter_criteria: !selectedProduct.value ? {
          country: customFilter.country || undefined,
          carrier: customFilter.carrier || undefined,
          tags: customFilter.tag ? [customFilter.tag] : undefined,
          source: customFilter.source || undefined
        } : undefined,
        quantity: form.quantity
      })
    }

    ElMessage.success(t('common.success'))
    dialogVisible.value = false
    refreshList()
  } catch (error: any) {
    ElMessage.error(error.message || t('common.failed'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refreshList()
})
</script>

<style scoped>
.data-store-container { width: 100%; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.type-filter { margin-bottom: 20px; }
.box-card { margin-bottom: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-header-tags { display: flex; gap: 6px; align-items: center; }
.criteria-tags { margin: 10px 0; display: flex; gap: 5px; flex-wrap: wrap; }
.actions { margin-top: 15px; display: flex; gap: 10px; justify-content: flex-end; }
.stock-result { margin-top: 20px; padding: 20px; background: #f0f9eb; border-radius: 8px; }
.stock-result h3 { margin: 0; color: #67c23a; }
.highlight { font-size: 24px; font-weight: bold; }
.sample-list { margin-top: 20px; }

.combo-info {
  background: #f0f9eb;
  border-radius: 6px;
  padding: 8px 12px;
  margin: 8px 0;
}
.price-compare {
  display: flex;
  align-items: center;
  gap: 8px;
}
.original-price {
  text-decoration: line-through;
  color: #999;
  font-size: 14px;
}
.bundle-price {
  color: #e6a23c;
  font-size: 18px;
  font-weight: bold;
}
</style>
