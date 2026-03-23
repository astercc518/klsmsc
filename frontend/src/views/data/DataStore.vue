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

                <!-- 评分展示 -->
                <div class="product-rating" v-if="product.rating" @click="openRatingDetail(product)">
                  <div class="rating-stars-row">
                    <span v-for="s in 5" :key="s" class="mini-star" :class="{ filled: s <= Math.round(product.rating.avg) }">★</span>
                    <span class="rating-avg">{{ product.rating.avg > 0 ? product.rating.avg : '-' }}</span>
                    <span class="rating-count" v-if="product.rating.total">({{ product.rating.total }}条)</span>
                  </div>
                  <div class="rating-meta" v-if="product.rating.total > 0">
                    <span class="rating-badge recent" v-if="product.rating.recent_avg > 0">
                      近期 {{ product.rating.recent_avg }}分
                    </span>
                    <span class="rating-badge best">
                      最高 {{ product.rating.max }}星
                    </span>
                  </div>
                </div>

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

        <el-form-item :label="t('dataPool.smsContent')" v-if="buyMode === 'send'">
          <el-input v-model="form.message" type="textarea" rows="4" :placeholder="t('dataPool.smsContentPlaceholder')" />
        </el-form-item>

        <el-form-item :label="t('dataPool.estimatedCost')">
          <span style="color: var(--el-color-danger); font-size: 18px; font-weight: bold;">
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

    <!-- 评分详情弹窗 -->
    <el-dialog v-model="ratingDetailVisible" title="商品评分详情" width="480px">
      <div v-loading="ratingDetailLoading" class="rating-detail">
        <div class="rating-overview">
          <div class="rating-big-score">
            <span class="big-num">{{ ratingDetail.avg_rating }}</span>
            <div class="big-stars">
              <span v-for="s in 5" :key="s" class="star-lg" :class="{ filled: s <= Math.round(ratingDetail.avg_rating) }">★</span>
            </div>
            <span class="rating-total-text">{{ ratingDetail.total_ratings }} 条评分</span>
          </div>
          <div class="rating-summary-cards">
            <div class="summary-card">
              <span class="sc-label">近30天均分</span>
              <span class="sc-value recent">{{ ratingDetail.recent_avg || '-' }}</span>
            </div>
            <div class="summary-card">
              <span class="sc-label">历史最高</span>
              <span class="sc-value best">{{ ratingDetail.max_rating || '-' }}★</span>
            </div>
            <div class="summary-card">
              <span class="sc-label">近期最高</span>
              <span class="sc-value">{{ ratingDetail.recent_max || '-' }}★</span>
            </div>
          </div>
        </div>

        <div class="rating-my" v-if="ratingDetail.my_rating">
          <span class="my-tag">我的评分</span>
          <span v-for="s in 5" :key="s" class="star-sm" :class="{ filled: s <= ratingDetail.my_rating.rating }">★</span>
          <span class="my-comment" v-if="ratingDetail.my_rating.comment">{{ ratingDetail.my_rating.comment }}</span>
        </div>

        <div class="rating-recent-list" v-if="ratingDetail.recent_ratings?.length">
          <h4>近期评价</h4>
          <div v-for="(r, idx) in ratingDetail.recent_ratings" :key="idx" class="recent-item">
            <div class="recent-header">
              <span v-for="s in 5" :key="s" class="star-xs" :class="{ filled: s <= r.rating }">★</span>
              <span class="recent-time">{{ fmtTime(r.created_at) }}</span>
            </div>
            <div class="recent-comment" v-if="r.comment">{{ r.comment }}</div>
          </div>
        </div>
        <el-empty v-else-if="!ratingDetailLoading" description="暂无评分" :image-size="60" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  getDataProducts, buyAndSend, buyToStock, buyCombo,
  previewDataSelection, getProductRatings, type DataProduct
} from '@/api/data'
import { ElMessage } from 'element-plus'

const { t } = useI18n()
const products = ref<(DataProduct & { rating?: any })[]>([])
const dialogVisible = ref(false)
const loading = ref(false)
const activeTab = ref('products')
const buyMode = ref<'send' | 'stock' | 'combo'>('stock')

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

const sourceFilter = ref('')
const purposeFilter = ref('')
const freshnessFilter = ref('')
const filteredProducts = computed(() => products.value)
const selectedProduct = ref<DataProduct | null>(null)

const customFilter = reactive({ country: '', carrier: '', tag: '', source: '' })
const customStock = ref<number | null>(null)
const customSamples = ref([])
const form = reactive({ quantity: 1000, message: '' })

const pricePerNumber = computed(() =>
  selectedProduct.value ? selectedProduct.value.price_per_number : '0.001'
)
const customSummary = computed(() =>
  `${customFilter.country || 'Any'} | ${customFilter.carrier || 'Any'} | ${customFilter.tag || 'Any'}`
)

function productTypeTagType(type: DataProduct['product_type']): '' | 'success' | 'warning' {
  return ({ data_only: '', combo: 'success', data_and_send: 'warning' } as any)[type] ?? ''
}
function productTypeLabel(type: DataProduct['product_type']): string {
  return ({ data_only: t('dataPool.typeDataOnly'), combo: t('dataPool.typeCombo'), data_and_send: t('dataPool.typeDataAndSend') })[type] ?? type
}
function sourceLabel(val: string) {
  return t(SOURCE_OPTIONS.find(o => o.value === val)?.labelKey || val)
}
function purposeLabel(val: string) {
  return t(PURPOSE_OPTIONS.find(o => o.value === val)?.labelKey || val)
}
function freshnessLabel(val: string) {
  return t(FRESHNESS_OPTIONS.find(o => o.value === val)?.labelKey || val)
}
function originalPrice(product: DataProduct): string {
  return (Number(product.price_per_number) * (product.sms_quota ?? 0) + Number(product.price_per_number)).toFixed(2)
}

const buyDialogTitle = computed(() => {
  if (buyMode.value === 'combo') return t('dataPool.buyCombo')
  if (buyMode.value === 'send') return t('dataPool.buyAndSend')
  return t('dataPool.buyToStock')
})
const buyConfirmText = computed(() => {
  if (buyMode.value === 'combo') return t('dataPool.confirmBuyCombo')
  if (buyMode.value === 'send') return t('dataPool.confirmPayAndSend')
  return t('dataPool.confirmPay')
})
const estimatedCost = computed(() => {
  if (selectedProduct.value?.product_type === 'combo')
    return (Number(selectedProduct.value.bundle_price) * form.quantity).toFixed(2)
  return (Number(pricePerNumber.value) * form.quantity).toFixed(2)
})

// ---- 评分详情 ----
const ratingDetailVisible = ref(false)
const ratingDetailLoading = ref(false)
const ratingDetail = ref<any>({})

async function openRatingDetail(product: any) {
  ratingDetailVisible.value = true
  ratingDetailLoading.value = true
  ratingDetail.value = {}
  try {
    const res = await getProductRatings(product.id)
    ratingDetail.value = res
  } catch {
    ratingDetail.value = {}
  } finally {
    ratingDetailLoading.value = false
  }
}

function fmtTime(d: string) {
  if (!d) return ''
  const dt = new Date(d)
  const now = new Date()
  const diff = now.getTime() - dt.getTime()
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  if (diff < 2592000000) return `${Math.floor(diff / 86400000)}天前`
  return dt.toLocaleDateString('zh-CN')
}

// ---- 列表与购买 ----
const refreshList = async () => {
  try {
    const res = await getDataProducts({
      source: sourceFilter.value || undefined,
      purpose: purposeFilter.value || undefined,
      freshness: freshnessFilter.value || undefined,
    })
    products.value = res.items || res.data
  } catch (error) { console.error(error) }
}

const checkCustomStock = async () => {
  const criteria = {
    country: customFilter.country || undefined,
    carrier: customFilter.carrier || undefined,
    tags: customFilter.tag ? [customFilter.tag] : undefined,
    source: customFilter.source || undefined,
  }
  const res = await previewDataSelection(criteria)
  if (res.success) {
    customStock.value = res.total_count
    customSamples.value = res.samples
  }
}

const openBuyDialog = (product: DataProduct, mode: 'send' | 'stock' | 'combo') => {
  selectedProduct.value = product; buyMode.value = mode
  form.quantity = 1000; form.message = ''; dialogVisible.value = true
}
const openCustomBuy = (mode: 'send' | 'stock') => {
  selectedProduct.value = null; buyMode.value = mode
  form.quantity = 1000; form.message = ''; dialogVisible.value = true
}

const handleBuyConfirm = async () => {
  if (buyMode.value === 'send' && !form.message) {
    ElMessage.warning(t('dataPool.pleaseEnterSmsContent')); return
  }
  loading.value = true
  try {
    if (buyMode.value === 'combo') {
      await buyCombo({ product_id: selectedProduct.value!.id, quantity: form.quantity })
    } else if (buyMode.value === 'send') {
      await buyAndSend({
        product_id: selectedProduct.value?.id,
        filter_criteria: !selectedProduct.value ? {
          country: customFilter.country || undefined, carrier: customFilter.carrier || undefined,
          tags: customFilter.tag ? [customFilter.tag] : undefined, source: customFilter.source || undefined,
        } : undefined,
        quantity: form.quantity, message: form.message,
      })
    } else {
      await buyToStock({
        product_id: selectedProduct.value?.id,
        filter_criteria: !selectedProduct.value ? {
          country: customFilter.country || undefined, carrier: customFilter.carrier || undefined,
          tags: customFilter.tag ? [customFilter.tag] : undefined, source: customFilter.source || undefined,
        } : undefined,
        quantity: form.quantity,
      })
    }
    ElMessage.success(t('common.success'))
    dialogVisible.value = false
    refreshList()
  } catch (error: any) {
    ElMessage.error(error.message || t('common.failed'))
  } finally { loading.value = false }
}

onMounted(() => { refreshList() })
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
.stock-result { margin-top: 20px; padding: 20px; background: var(--el-color-success-light-9); border-radius: 8px; }
.stock-result h3 { margin: 0; color: var(--el-color-success); }
.highlight { font-size: 24px; font-weight: bold; }
.sample-list { margin-top: 20px; }
.combo-info { background: var(--el-color-success-light-9); border-radius: 6px; padding: 8px 12px; margin: 8px 0; }
.price-compare { display: flex; align-items: center; gap: 8px; }
.original-price { text-decoration: line-through; color: var(--el-text-color-placeholder); font-size: 14px; }
.bundle-price { color: var(--el-color-warning); font-size: 18px; font-weight: bold; }

/* ---- 商品卡片评分区域（使用主题变量适配亮暗模式）---- */
.product-rating {
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 8px 12px;
  margin: 10px 0;
  cursor: pointer;
  transition: box-shadow 0.2s;
}
.product-rating:hover {
  box-shadow: 0 2px 8px rgba(247, 186, 42, 0.2);
}
.rating-stars-row {
  display: flex;
  align-items: center;
  gap: 4px;
}
.mini-star {
  font-size: 14px;
  color: var(--el-text-color-placeholder);
}
.mini-star.filled { color: var(--el-color-warning); }
.rating-avg {
  font-size: 15px;
  font-weight: 700;
  color: var(--el-color-warning);
  margin-left: 4px;
}
.rating-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.rating-meta {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
.rating-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 500;
}
.rating-badge.recent {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}
.rating-badge.best {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

/* ---- 评分详情弹窗（使用主题变量）---- */
.rating-detail { min-height: 120px; }
.rating-overview {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.rating-big-score {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 100px;
}
.big-num {
  font-size: 36px;
  font-weight: 700;
  color: var(--el-color-warning);
  line-height: 1;
}
.big-stars { margin: 4px 0; }
.star-lg { font-size: 18px; color: var(--el-text-color-placeholder); }
.star-lg.filled { color: var(--el-color-warning); }
.rating-total-text { font-size: 12px; color: var(--el-text-color-secondary); }
.rating-summary-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  flex: 1;
}
.summary-card {
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 10px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 90px;
}
.sc-label { font-size: 12px; color: var(--el-text-color-secondary); }
.sc-value { font-size: 18px; font-weight: 700; color: var(--el-text-color-primary); }
.sc-value.recent { color: var(--el-color-primary); }
.sc-value.best { color: var(--el-color-danger); }

.rating-my {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.my-tag {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}
.star-sm { font-size: 16px; color: var(--el-text-color-placeholder); }
.star-sm.filled { color: var(--el-color-warning); }
.my-comment { font-size: 13px; color: var(--el-text-color-regular); margin-left: 8px; }

.rating-recent-list h4 {
  font-size: 14px;
  color: var(--el-text-color-regular);
  margin: 12px 0 8px;
}
.recent-item {
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.recent-item:last-child { border-bottom: none; }
.recent-header {
  display: flex;
  align-items: center;
  gap: 4px;
}
.star-xs { font-size: 12px; color: #dcdfe6; }
.star-xs.filled { color: #f7ba2a; }
.recent-time { font-size: 11px; color: #c0c4cc; margin-left: auto; }
.recent-comment { font-size: 13px; color: #606266; margin-top: 4px; line-height: 1.5; }
</style>
