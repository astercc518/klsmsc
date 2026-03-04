<template>
  <div class="data-products-page">
    <div class="page-header">
      <div class="header-left">
        <h1>{{ t('dataPool.productsTitle') }}</h1>
        <p class="subtitle">{{ t('dataPool.productsDesc') }}</p>
      </div>
      <div class="header-right">
        <el-button type="primary" @click="openCreateDialog">
          <el-icon><Plus /></el-icon>
          {{ t('dataPool.createProduct') }}
        </el-button>
      </div>
    </div>

    <!-- 商品列表 -->
    <div class="products-grid">
      <div v-for="product in products" :key="product.id" class="product-card">
        <div class="product-header">
          <span class="product-code">{{ product.product_code }}</span>
          <el-tag :type="getStatusType(product.status)" size="small">
            {{ getStatusLabel(product.status) }}
          </el-tag>
        </div>
        <h3 class="product-name">{{ product.product_name }}</h3>
        <p class="product-desc">{{ product.description || t('dataPool.noDescription') }}</p>
        
        <div class="product-filter">
          <el-icon><Filter /></el-icon>
          <span>{{ t('dataPool.filterCriteria') }}:</span>
          <code>{{ JSON.stringify(product.filter_criteria) }}</code>
        </div>

        <div class="product-stats">
          <div class="stat-item">
            <span class="label">{{ t('dataPool.stock') }}</span>
            <span class="value">{{ product.stock_count?.toLocaleString() }}</span>
          </div>
          <div class="stat-item">
            <span class="label">{{ t('dataPool.unitPrice') }}</span>
            <span class="value">${{ product.price_per_number }}</span>
          </div>
          <div class="stat-item">
            <span class="label">{{ t('dataPool.totalSold') }}</span>
            <span class="value">{{ product.total_sold?.toLocaleString() }}</span>
          </div>
        </div>

        <div class="product-limits">
          <span>{{ t('dataPool.purchaseRange') }}: {{ product.min_purchase }} - {{ product.max_purchase }}</span>
        </div>

        <div class="product-actions">
          <el-button size="small" @click="refreshStock(product)">
            <el-icon><Refresh /></el-icon>
            {{ t('dataPool.refreshStock') }}
          </el-button>
          <el-button size="small" @click="openEditDialog(product)">
            <el-icon><Edit /></el-icon>
            {{ t('common.edit') }}
          </el-button>
          <el-button size="small" type="danger" @click="deleteProduct(product)">
            <el-icon><Delete /></el-icon>
            {{ t('common.delete') }}
          </el-button>
        </div>
      </div>

      <div v-if="products.length === 0 && !loading" class="empty-state">
        <el-empty :description="t('dataPool.noProducts')">
          <el-button type="primary" @click="openCreateDialog">{{ t('dataPool.createFirstProduct') }}</el-button>
        </el-empty>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pagination-wrapper" v-if="pagination.total > pagination.pageSize">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[12, 24, 48]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadData"
        @current-change="loadData"
      />
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingProduct ? t('dataPool.editProduct') : t('dataPool.createProduct')" width="600px">
      <el-form :model="form" label-width="100px" :rules="rules" ref="formRef">
        <el-form-item :label="t('dataPool.productCode')" prop="product_code" v-if="!editingProduct">
          <el-input v-model="form.product_code" :placeholder="t('dataPool.productCodeExample')" />
        </el-form-item>
        <el-form-item :label="t('dataPool.productName')" prop="product_name">
          <el-input v-model="form.product_name" :placeholder="t('dataPool.productNameExample')" />
        </el-form-item>
        <el-form-item :label="t('dataPool.productDescription')">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item :label="t('dataPool.priceUsd')" prop="price_per_number">
          <el-input v-model="form.price_per_number" placeholder="0.001">
            <template #prepend>$</template>
          </el-input>
        </el-form-item>
        <el-form-item :label="t('dataPool.purchaseLimit')">
          <div style="display: flex; gap: 10px; align-items: center;">
            <el-input-number v-model="form.min_purchase" :min="1" />
            <span>{{ t('dataPool.to') }}</span>
            <el-input-number v-model="form.max_purchase" :min="form.min_purchase" />
          </div>
        </el-form-item>
        <el-form-item :label="t('dataPool.filterCriteria')" prop="filter_criteria">
          <div class="filter-builder">
            <div class="filter-row">
              <label>{{ t('dataPool.countryCode') }}:</label>
              <el-input v-model="filterBuilder.country" :placeholder="t('dataPool.countryCodeExample')" style="width: 150px" />
            </div>
            <div class="filter-row">
              <label>{{ t('dataPool.includeTags') }}:</label>
              <el-select v-model="filterBuilder.tags" multiple filterable allow-create :placeholder="t('dataPool.selectOrEnterTags')" style="width: 100%">
                <el-option v-for="tag in commonTags" :key="tag" :label="tag" :value="tag" />
              </el-select>
            </div>
            <div class="filter-row">
              <label>{{ t('dataPool.excludeDays') }}:</label>
              <el-input-number v-model="filterBuilder.exclude_used_days" :min="0" />
              <span class="tip">{{ t('dataPool.daysUsedNumbers') }}</span>
            </div>
          </div>
        </el-form-item>
        <el-form-item :label="t('common.status')" v-if="editingProduct">
          <el-select v-model="form.status">
            <el-option :label="t('dataPool.listed')" value="active" />
            <el-option :label="t('dataPool.unlisted')" value="inactive" />
            <el-option :label="t('dataPool.soldOut')" value="sold_out" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">
          {{ editingProduct ? t('common.save') : t('common.create') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete, Refresh, Filter } from '@element-plus/icons-vue'
import request from '@/api/index'

const { t } = useI18n()

const loading = ref(false)
const submitting = ref(false)
const products = ref([])
const dialogVisible = ref(false)
const editingProduct = ref(null)
const formRef = ref(null)

const pagination = ref({
  page: 1,
  pageSize: 12,
  total: 0
})

const commonTags = ref(['crypto', 'finance', 'shopping', 'gaming', 'social', 'news', 'education'])

const form = ref({
  product_code: '',
  product_name: '',
  description: '',
  price_per_number: '0.001',
  min_purchase: 100,
  max_purchase: 100000,
  status: 'active'
})

const filterBuilder = ref({
  country: '',
  tags: [],
  exclude_used_days: 0
})

const rules = computed(() => ({
  product_code: [{ required: true, message: t('dataPool.pleaseEnterProductCode'), trigger: 'blur' }],
  product_name: [{ required: true, message: t('dataPool.pleaseEnterProductName'), trigger: 'blur' }],
  price_per_number: [{ required: true, message: t('dataPool.pleaseEnterPrice'), trigger: 'blur' }]
}))

// 构建筛选条件对象
const buildFilterCriteria = () => {
  const criteria = {}
  if (filterBuilder.value.country) criteria.country = filterBuilder.value.country
  if (filterBuilder.value.tags.length > 0) criteria.tags = filterBuilder.value.tags
  if (filterBuilder.value.exclude_used_days > 0) criteria.exclude_used_days = filterBuilder.value.exclude_used_days
  return criteria
}

// 解析筛选条件到builder
const parseFilterCriteria = (criteria) => {
  filterBuilder.value = {
    country: criteria.country || '',
    tags: criteria.tags || [],
    exclude_used_days: criteria.exclude_used_days || 0
  }
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await request.get('/admin/data/products', {
      params: {
        page: pagination.value.page,
        page_size: pagination.value.pageSize
      }
    })
    if (res.success) {
      products.value = res.items
      pagination.value.total = res.total
    }
  } catch (error) {
    ElMessage.error(t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

const openCreateDialog = () => {
  editingProduct.value = null
  form.value = {
    product_code: '',
    product_name: '',
    description: '',
    price_per_number: '0.001',
    min_purchase: 100,
    max_purchase: 100000,
    status: 'active'
  }
  filterBuilder.value = { country: '', tags: [], exclude_used_days: 0 }
  dialogVisible.value = true
}

const openEditDialog = (product) => {
  editingProduct.value = product
  form.value = {
    product_code: product.product_code,
    product_name: product.product_name,
    description: product.description || '',
    price_per_number: product.price_per_number,
    min_purchase: product.min_purchase,
    max_purchase: product.max_purchase,
    status: product.status
  }
  parseFilterCriteria(product.filter_criteria || {})
  dialogVisible.value = true
}

const handleSubmit = async () => {
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    const filterCriteria = buildFilterCriteria()
    
    if (editingProduct.value) {
      // Update
      await request.put(`/admin/data/products/${editingProduct.value.id}`, {
        product_name: form.value.product_name,
        description: form.value.description,
        price_per_number: form.value.price_per_number,
        min_purchase: form.value.min_purchase,
        max_purchase: form.value.max_purchase,
        filter_criteria: filterCriteria,
        status: form.value.status
      })
      ElMessage.success(t('common.updateSuccess'))
    } else {
      // Create
      await request.post('/admin/data/products', {
        product_code: form.value.product_code,
        product_name: form.value.product_name,
        description: form.value.description,
        price_per_number: form.value.price_per_number,
        min_purchase: form.value.min_purchase,
        max_purchase: form.value.max_purchase,
        filter_criteria: filterCriteria
      })
      ElMessage.success(t('common.createSuccess'))
    }
    
    dialogVisible.value = false
    loadData()
  } catch (error) {
    ElMessage.error(error.message || t('common.operationFailed'))
  } finally {
    submitting.value = false
  }
}

const refreshStock = async (product) => {
  try {
    const res = await request.post(`/admin/data/products/${product.id}/refresh-stock`)
    if (res.success) {
      product.stock_count = res.stock_count
      ElMessage.success(t('dataPool.stockUpdated', { count: res.stock_count }))
    }
  } catch (error) {
    ElMessage.error(t('dataPool.refreshFailed'))
  }
}

const deleteProduct = async (product) => {
  try {
    await ElMessageBox.confirm(
      t('dataPool.confirmDeleteProductMsg', { name: product.product_name }),
      t('common.confirmDelete'),
      { type: 'warning' }
    )
    
    await request.delete(`/admin/data/products/${product.id}`)
    ElMessage.success(t('common.deleteSuccess'))
    loadData()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(t('common.deleteFailed'))
    }
  }
}

const getStatusType = (status) => {
  const types = { active: 'success', inactive: 'info', sold_out: 'warning' }
  return types[status] || 'info'
}

const getStatusLabel = (status) => {
  const labels = { 
    active: t('dataPool.listedStatus'), 
    inactive: t('dataPool.unlistedStatus'), 
    sold_out: t('dataPool.soldOutStatus') 
  }
  return labels[status] || status
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.data-products-page {
  width: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 24px;
  font-weight: 600;
  margin: 0;
}

.subtitle {
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  font-size: 14px;
}

.products-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 20px;
}

.product-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 20px;
  transition: all 0.3s;
}

.product-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.product-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.product-code {
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.product-name {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px 0;
}

.product-desc {
  color: var(--el-text-color-secondary);
  font-size: 14px;
  margin-bottom: 16px;
  line-height: 1.5;
}

.product-filter {
  background: var(--el-fill-color-light);
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 12px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.product-filter code {
  background: var(--el-fill-color);
  padding: 2px 6px;
  border-radius: 4px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-stats {
  display: flex;
  gap: 20px;
  margin-bottom: 12px;
}

.stat-item {
  display: flex;
  flex-direction: column;
}

.stat-item .label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.stat-item .value {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-color-primary);
}

.product-limits {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 16px;
}

.product-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pagination-wrapper {
  margin-top: 24px;
  display: flex;
  justify-content: center;
}

.empty-state {
  grid-column: 1 / -1;
  padding: 60px 0;
}

.filter-builder {
  background: var(--el-fill-color-light);
  padding: 16px;
  border-radius: 8px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.filter-row:last-child {
  margin-bottom: 0;
}

.filter-row label {
  min-width: 80px;
  font-size: 14px;
}

.filter-row .tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
