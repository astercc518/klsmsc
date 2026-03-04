<template>
  <div class="packages">
    <el-tabs v-model="activeTab">
      <el-tab-pane :label="$t('packages.market')" name="market">
        <el-row :gutter="20">
          <el-col :span="6" v-for="pkg in packages" :key="pkg.id">
            <el-card class="package-card" :class="{ featured: pkg.is_featured }">
              <div class="package-header">
                <h3>{{ pkg.package_name }}</h3>
                <el-tag v-if="pkg.is_featured" type="warning" size="small">{{ $t('common.recommended') }}</el-tag>
              </div>
              <div class="package-price">
                <span class="currency">$</span>
                <span class="amount">{{ parseFloat(pkg.price).toFixed(0) }}</span>
                <span class="unit">USD</span>
              </div>
              <div class="package-features">
                <div class="feature-item">
                  <i class="el-icon-message"></i>
                  <span>{{ $t('packages.smsCount', { count: pkg.sms_quota }) }}</span>
                </div>
                <div class="feature-item">
                  <i class="el-icon-time"></i>
                  <span>{{ $t('packages.validityDays', { days: pkg.validity_days }) }}</span>
                </div>
                <div v-if="pkg.description" class="feature-item description">
                  {{ pkg.description }}
                </div>
              </div>
              <el-button 
                type="primary" 
                style="width: 100%; margin-top: 20px"
                @click="purchasePackage(pkg)"
                :loading="purchasing === pkg.id"
              >
                {{ $t('packages.purchase') }}
              </el-button>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <el-tab-pane :label="$t('packages.myPackages')" name="my-packages">
        <el-table :data="myPackages" v-loading="loadingMyPackages" style="width: 100%">
          <el-table-column prop="package_name" :label="$t('packages.packageName')" min-width="150" />
          <el-table-column :label="$t('packages.purchasePrice')" width="120">
            <template #default="{ row }">
              ${{ parseFloat(row.purchase_price || 0).toFixed(2) }}
            </template>
          </el-table-column>
          <el-table-column :label="$t('packages.usage')" width="200">
            <template #default="{ row }">
              <el-progress 
                :percentage="calculateUsagePercent(row)" 
                :color="getProgressColor(row)"
              />
              <div style="margin-top: 5px; font-size: 12px; color: #909399">
                {{ $t('packages.usedRemaining', { used: row.sms_used, remaining: row.sms_remaining || 0 }) }}
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('packages.validity')" width="250">
            <template #default="{ row }">
              <div>{{ formatDateTime(row.start_date) }}</div>
              <div style="color: #909399">{{ $t('packages.to') }} {{ formatDateTime(row.end_date) }}</div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.status')" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.is_active" type="success">{{ $t('packages.active') }}</el-tag>
              <el-tag v-else type="info">{{ $t('packages.expired') }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('packages.purchaseTime')" width="180">
            <template #default="{ row }">
              {{ formatDateTime(row.created_at) }}
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 购买确认对话框 -->
    <el-dialog v-model="purchaseDialogVisible" :title="$t('packages.confirmPurchase')" width="400px">
      <div v-if="selectedPackage" class="purchase-confirm">
        <div class="confirm-item">
          <span class="label">{{ $t('packages.packageName') }}：</span>
          <span class="value">{{ selectedPackage.package_name }}</span>
        </div>
        <div class="confirm-item">
          <span class="label">{{ $t('packages.packageContent') }}：</span>
          <span class="value">{{ $t('packages.smsCount', { count: selectedPackage.sms_quota }) }}</span>
        </div>
        <div class="confirm-item">
          <span class="label">{{ $t('packages.validity') }}：</span>
          <span class="value">{{ $t('packages.days', { days: selectedPackage.validity_days }) }}</span>
        </div>
        <div class="confirm-item" style="margin-top: 20px; font-size: 18px; font-weight: bold">
          <span class="label">{{ $t('packages.paymentAmount') }}：</span>
          <span class="value" style="color: #f56c6c">
            ${{ parseFloat(selectedPackage.price).toFixed(2) }} USD
          </span>
        </div>
        <el-alert 
          :title="$t('packages.deductFromBalance')" 
          type="warning" 
          :closable="false"
          style="margin-top: 20px"
        />
      </div>
      <template #footer>
        <el-button @click="purchaseDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="confirmPurchase" :loading="submitting">{{ $t('packages.confirmPayment') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { packageApi } from '@/api/package'

const { t } = useI18n()
const activeTab = ref('market')
const loadingMyPackages = ref(false)
const purchasing = ref(0)
const submitting = ref(false)
const purchaseDialogVisible = ref(false)
const selectedPackage = ref<any>(null)

const packages = ref<any[]>([])
const myPackages = ref<any[]>([])

const formatDateTime = (dateStr: string) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const calculateUsagePercent = (row: any) => {
  const total = row.sms_used + (row.sms_remaining || 0)
  if (total === 0) return 0
  return Math.round((row.sms_used / total) * 100)
}

const getProgressColor = (row: any) => {
  const percent = calculateUsagePercent(row)
  if (percent < 50) return '#67c23a'
  if (percent < 80) return '#e6a23c'
  return '#f56c6c'
}

const loadPackages = async () => {
  try {
    const res = await packageApi.list({ page: 1, page_size: 100, is_featured: undefined })
    packages.value = res.data.items
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('packages.loadPackagesFailed'))
  }
}

const loadMyPackages = async () => {
  loadingMyPackages.value = true
  try {
    const res = await packageApi.getMyPackages()
    myPackages.value = res.data
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('packages.loadMyPackagesFailed'))
  } finally {
    loadingMyPackages.value = false
  }
}

const purchasePackage = (pkg: any) => {
  selectedPackage.value = pkg
  purchaseDialogVisible.value = true
}

const confirmPurchase = async () => {
  if (!selectedPackage.value) return

  submitting.value = true
  try {
    await packageApi.purchase(selectedPackage.value.id, {})
    ElMessage.success(t('packages.purchaseSuccess'))
    purchaseDialogVisible.value = false
    loadMyPackages()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('packages.purchaseFailed'))
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadPackages()
  loadMyPackages()
})
</script>

<style scoped>
.packages {
  width: 100%;
}

.package-card {
  margin-bottom: 20px;
  transition: all 0.3s;
}

.package-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

.package-card.featured {
  border: 2px solid #e6a23c;
}

.package-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.package-header h3 {
  margin: 0;
  font-size: 20px;
  color: #303133;
}

.package-price {
  text-align: center;
  margin: 30px 0;
}

.package-price .currency {
  font-size: 20px;
  color: #909399;
}

.package-price .amount {
  font-size: 48px;
  font-weight: bold;
  color: #303133;
  margin: 0 5px;
}

.package-price .unit {
  font-size: 16px;
  color: #909399;
}

.package-features {
  min-height: 120px;
}

.feature-item {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  color: #606266;
}

.feature-item i {
  margin-right: 8px;
  color: #409eff;
}

.feature-item.description {
  color: #909399;
  font-size: 13px;
  margin-top: 15px;
  display: block;
}

.purchase-confirm .confirm-item {
  display: flex;
  justify-content: space-between;
  margin-bottom: 15px;
}

.purchase-confirm .label {
  color: #909399;
}

.purchase-confirm .value {
  font-weight: bold;
  color: #303133;
}
</style>
