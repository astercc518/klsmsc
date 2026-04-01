<template>
  <div class="data-store-container">
    <div class="header">
      <h2>{{ t('dataPool.publicPool') }}</h2>
      <div class="header-right">
        <el-button @click="$router.push('/data/my-numbers')">{{ t('dataPool.myPrivatePool') }}</el-button>
        <el-button type="primary" @click="refreshList">{{ t('dataPool.refreshList') }}</el-button>
      </div>
    </div>

    <!-- 统一筛选栏 -->
    <div class="filter-bar">
      <el-select v-model="sourceFilter" :placeholder="t('dataPool.allSource')" clearable @change="refreshList" style="width: 140px;">
        <el-option v-for="opt in SOURCE_OPTIONS" :key="opt.value" :label="t(opt.labelKey)" :value="opt.value" />
      </el-select>
      <el-select v-model="purposeFilter" :placeholder="t('dataPool.allPurpose')" clearable @change="refreshList" style="width: 140px;">
        <el-option v-for="opt in PURPOSE_OPTIONS" :key="opt.value" :label="t(opt.labelKey)" :value="opt.value" />
      </el-select>
      <el-select v-model="freshnessFilter" :placeholder="t('dataPool.allFreshness')" clearable @change="refreshList" style="width: 140px;">
        <el-option v-for="opt in FRESHNESS_OPTIONS" :key="opt.value" :label="t(opt.labelKey)" :value="opt.value" />
      </el-select>
      <el-select v-model="carrierFilter" :placeholder="t('dataPool.allCarrier')" clearable @change="refreshList" style="width: 150px;">
        <el-option v-for="c in availableCarriers" :key="c.name" :label="c.name + ' (' + c.count + ')'" :value="c.name" />
      </el-select>
      
      <el-select v-model="countryFilter" :placeholder="t('dataPool.country')" 
        clearable filterable @change="refreshList" style="width: 180px;">
        <el-option v-for="c in countryOptions" :key="c.iso" :label="c.displayName" :value="c.iso" />
      </el-select>
      <el-input v-model="tagFilter" :placeholder="t('dataPool.tag')" clearable @change="refreshList" style="width: 140px;" />
    </div>

    <!-- 商品列表 -->
    <div class="products-section">
      <el-row :gutter="20">
        <el-col :span="8" v-for="product in products" :key="product.id">
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
              <p class="description">{{ product.description }}</p>
              
              <div class="stock-info">
                <div class="stock-item">
                  <span class="stock-label">{{ t('dataPool.unsold') }}</span>
                  <span class="stock-value">{{ product.stock_count }}</span>
                </div>
                <div class="stock-item">
                  <span class="stock-label">{{ t('dataPool.sold') }}</span>
                  <span class="stock-value sold">{{ product.total_sold || 0 }}</span>
                </div>
              </div>

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

              <div class="criteria-tags">
                <el-tag v-if="product.filter_criteria?.country" size="small" type="primary">
                  {{ findCountryByIso(product.filter_criteria.country)?.name || product.filter_criteria.country }}
                </el-tag>
                <el-tag v-if="product.filter_criteria?.carrier" size="small" type="info">{{ product.filter_criteria.carrier }}</el-tag>
                <el-tag v-if="product.filter_criteria?.source" size="small" type="danger">{{ t('dataPool.source') }}: {{ sourceLabel(product.filter_criteria.source) }}</el-tag>
                <el-tag v-if="product.filter_criteria?.purpose" size="small" type="warning">{{ t('dataPool.purpose') }}: {{ purposeLabel(product.filter_criteria.purpose) }}</el-tag>
                <el-tag v-if="product.filter_criteria?.freshness" size="small" type="success">{{ t('dataPool.freshness') }}: {{ freshnessLabel(product.filter_criteria.freshness) }}</el-tag>
                <el-tag v-for="tag in product.filter_criteria?.tags || []" :key="tag" size="small" type="warning">{{ tag }}</el-tag>
              </div>

              <!-- 运营商分布 -->
              <div class="carrier-dist" v-if="product.carriers?.length">
                <div class="dist-label">{{ t('dataPool.carrierDistribution') }}:</div>
                <div class="dist-list">
                  <el-tag 
                    v-for="c in product.carriers" 
                    :key="c.name" 
                    size="small" 
                    :type="carrierFilter === c.name ? 'primary' : 'info'"
                    :effect="carrierFilter === c.name ? 'dark' : 'plain'"
                    class="dist-tag"
                  >
                    {{ c.name }}: {{ c.count }}
                  </el-tag>
                </div>
              </div>

              <div class="actions">
                <template v-if="product.product_type === 'data_only'">
                  <el-button type="primary" @click="openBuyDialog(product, 'stock')">{{ t('dataPool.buyToStock') }}</el-button>
                </template>
                <template v-else-if="product.product_type === 'combo'">
                  <el-button type="success" @click="openBuyDialog(product, 'combo')">{{ t('dataPool.buyCombo') }}</el-button>
                </template>
                <template v-else-if="product.product_type === 'data_and_send'">
                  <el-button type="warning" @click="openBuyDialog(product, 'send')">{{ t('dataPool.buyAndSend') }}</el-button>
                </template>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- 购买弹窗 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="400px">
      <el-form :model="buyForm" label-width="80px">
        <el-form-item :label="t('dataPool.product')">
          <span style="font-weight: bold;">{{ currentProduct?.product_name }}</span>
        </el-form-item>
        <el-form-item :label="t('dataPool.quantity')">
          <el-input-number v-model="buyForm.quantity" :min="100" />
        </el-form-item>
        <el-form-item :label="t('common.message')" v-if="buyMode === 'send'">
          <el-input v-model="buyForm.message" type="textarea" rows="3" />
        </el-form-item>
        <div class="cost-summary">
          <span>{{ t('dataPool.estimatedCost') }}: </span>
          <span class="cost-value">${{ estimatedCost }}</span>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="handleBuyConfirm" :loading="loading">{{ confirmButtonText }}</el-button>
      </template>
    </el-dialog>

    <!-- 评分详情弹窗 -->
    <el-dialog v-model="ratingDialogVisible" :title="t('dataPool.ratingDetail')" width="400px">
      <div v-for="r in ratingList" :key="r.id" class="rating-item">
        <div class="rating-header">
          <span v-for="s in 5" :key="s" class="mini-star" :class="{ filled: s <= r.rating }">★</span>
          <span class="rating-time">{{ r.created_at }}</span>
        </div>
        <div class="rating-comment">{{ r.comment || t('common.noComment') }}</div>
      </div>
      <el-empty v-if="!ratingList.length" :description="t('common.noData')" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  getDataProducts, buyAndSend, buyToStock, buyCombo,
  getProductRatings
} from '@/api/data'
import { COUNTRY_LIST, findCountryByIso } from '@/constants/countries'
import { ElMessage } from 'element-plus'

const { t } = useI18n()

// ---- 状态 ----
const products = ref<any[]>([])
const availableCarriers = ref<any[]>([])
const availableCountries = ref<string[]>([])
const dialogVisible = ref(false)
const loading = ref(false)
const buyMode = ref<'send' | 'stock' | 'combo'>('stock')

const sourceFilter = ref('')
const purposeFilter = ref('')
const freshnessFilter = ref('')
const carrierFilter = ref('')
const countryFilter = ref('')
const tagFilter = ref('')
const isFirstLoad = ref(true)

const currentProduct = ref<any>(null)
const buyForm = reactive({
  quantity: 100,
  message: '',
})

// ---- 选项常量 ----
const SOURCE_OPTIONS = [
  { value: 'api', labelKey: 'common.source_api' },
  { value: 'web', labelKey: 'common.source_web' },
  { value: 'manual', labelKey: 'common.source_manual' },
]

const PURPOSE_OPTIONS = [
  { value: 'marketing', labelKey: 'common.purpose_marketing' },
  { value: 'notification', labelKey: 'common.purpose_notification' },
  { value: 'verification', labelKey: 'common.purpose_verification' },
]

const FRESHNESS_OPTIONS = [
  { value: 'realtime', labelKey: 'common.freshness_realtime' },
  { value: '1h', labelKey: 'common.freshness_1h' },
  { value: '24h', labelKey: 'common.freshness_24h' },
  { value: 'old', labelKey: 'common.freshness_old' },
]

// ---- 计算属性 ----
const countryOptions = computed(() => {
  const options = availableCountries.value.map(iso => {
    const c = findCountryByIso(iso)
    return {
      iso,
      displayName: c ? `${c.name} (+${c.dial})` : iso,
      searchKeys: c ? `${c.name} ${c.dial} ${iso}`.toLowerCase() : iso.toLowerCase()
    }
  })
  // 添加“全部国家”选项
  options.unshift({ 
    iso: 'all', 
    displayName: t('dataPool.allCountries'), 
    searchKeys: 'all 全部 global' 
  })
  return options
})

const dialogTitle = computed(() => {
  if (buyMode.value === 'combo') return t('dataPool.buyCombo')
  return buyMode.value === 'send' ? t('dataPool.buyAndSend') : t('dataPool.buyToStock')
})

const confirmButtonText = computed(() => t('common.confirm'))

const estimatedCost = computed(() => {
  const price = currentProduct.value?.product_type === 'combo' 
    ? Number(currentProduct.value.bundle_price) 
    : Number(currentProduct.value?.price_per_number || 0)
  return (price * buyForm.quantity).toFixed(2)
})

// ---- 工具函数 ----
function productTypeTagType(type: string) {
  return ({ data_only: '', combo: 'success', data_and_send: 'warning' } as any)[type] ?? ''
}

function productTypeLabel(type: string) {
  const labels: any = { 
    data_only: t('dataPool.typeDataOnly'), 
    combo: t('dataPool.typeCombo'), 
    data_and_send: t('dataPool.typeDataAndSend') 
  }
  return labels[type] ?? type
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

// ---- 数据加载 ----
const refreshList = async () => {
  try {
    const res = await getDataProducts({
      source: sourceFilter.value || undefined,
      purpose: purposeFilter.value || undefined,
      freshness: freshnessFilter.value || undefined,
      carrier: carrierFilter.value || undefined,
      country: countryFilter.value || undefined,
      tag: tagFilter.value || undefined,
    })
    products.value = res.items || []
    availableCarriers.value = res.available_carriers || []
    availableCountries.value = res.available_countries || []
    
    // 首次加载时同步默认国家
    if (isFirstLoad.value && !countryFilter.value && res.country_code) {
      countryFilter.value = res.country_code
    }
    isFirstLoad.value = false
  } catch (error) { console.error(error) }
}

onMounted(() => {
  refreshList()
})

// ---- 购买逻辑 ----
const openBuyDialog = (product: any, mode: 'send' | 'stock' | 'combo' = 'stock') => {
  currentProduct.value = product
  buyMode.value = mode
  buyForm.quantity = product.min_purchase || 100
  buyForm.message = ''
  dialogVisible.value = true
}

const handleBuyConfirm = async () => {
  if (buyMode.value === 'send' && !buyForm.message) {
    ElMessage.warning(t('dataPool.pleaseEnterSmsContent'))
    return
  }
  loading.value = true
  try {
    if (buyMode.value === 'combo') {
      await buyCombo({ product_id: currentProduct.value.id, quantity: buyForm.quantity })
    } else if (buyMode.value === 'send') {
      await buyAndSend({ product_id: currentProduct.value.id, quantity: buyForm.quantity, message: buyForm.message })
    } else {
      await buyToStock({ product_id: currentProduct.value.id, quantity: buyForm.quantity })
    }
    ElMessage.success(t('common.success'))
    dialogVisible.value = false
    refreshList()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.error'))
  } finally { loading.value = false }
}

// ---- 评分详情 ----
const ratingDialogVisible = ref(false)
const ratingList = ref<any[]>([])

const openRatingDetail = async (product: any) => {
  try {
    const res = await getProductRatings(product.id)
    ratingList.value = res.items || []
    ratingDialogVisible.value = true
  } catch (error) { console.error(error) }
}
</script>

<style scoped>
.data-store-container { padding: 20px; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  background: rgba(255, 255, 255, 0.05);
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 24px;
}
.products-section { margin-top: 20px; }
.box-card { margin-bottom: 20px; transition: transform 0.3s; }
.box-card:hover { transform: translateY(-5px); }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-header-tags { display: flex; gap: 8px; }
.description { font-size: 14px; color: #909399; min-height: 40px; }
.stock-info {
  display: flex;
  gap: 20px;
  margin: 12px 0;
  padding: 8px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
}
.stock-item { display: flex; flex-direction: column; }
.stock-label { font-size: 11px; color: #909399; }
.stock-value { font-size: 16px; font-weight: bold; color: #409EFF; }
.stock-value.sold { color: #67C23A; }

.criteria-tags { display: flex; flex-wrap: wrap; gap: 4px; margin: 12px 0; }
.carrier-dist { margin-top: 12px; padding-top: 8px; border-top: 1px dashed rgba(255, 255, 255, 0.1); }
.dist-label { font-size: 11px; color: #909399; margin-bottom: 6px; }
.dist-list { display: flex; flex-wrap: wrap; gap: 4px; }
.dist-tag { font-size: 10px; }

.actions { margin-top: 16px; display: flex; justify-content: flex-end; }

.product-rating {
  margin: 12px 0;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}
.rating-stars-row { display: flex; align-items: center; gap: 4px; }
.mini-star { color: #444; font-size: 14px; }
.mini-star.filled { color: #fadb14; }
.rating-avg { font-weight: bold; color: #fadb14; margin-left: 4px; }
.rating-count { font-size: 11px; color: #666; margin-left: 6px; }
.rating-meta { margin-top: 4px; display: flex; gap: 8px; }
.rating-badge { font-size: 10px; padding: 1px 4px; border-radius: 2px; }
.rating-badge.recent { background: rgba(82, 196, 26, 0.1); color: #52c41a; }
.rating-badge.best { background: rgba(250, 173, 20, 0.1); color: #faad14; }

.cost-summary { margin-top: 16px; text-align: right; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 12px; }
.cost-value { font-size: 20px; font-weight: bold; color: #F56C6C; margin-left: 8px; }

.rating-item { padding: 12px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.05); }
.rating-header { display: flex; justify-content: space-between; margin-bottom: 6px; }
.rating-time { font-size: 12px; color: #666; }
.rating-comment { font-size: 13px; line-height: 1.5; }
</style>
