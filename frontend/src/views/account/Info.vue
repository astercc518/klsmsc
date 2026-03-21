<template>
  <div class="account-info">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <span>{{ $t('accountInfo.title') }}</span>
        </div>
      </template>
      
      <el-descriptions :column="2" border v-if="accountInfo">
        <el-descriptions-item :label="$t('accountInfo.accountId')">{{ accountInfo.id }}</el-descriptions-item>
        <el-descriptions-item :label="$t('accountInfo.accountName')">{{ accountInfo.account_name }}</el-descriptions-item>
        <el-descriptions-item :label="$t('accountInfo.email')">{{ accountInfo.email }}</el-descriptions-item>
        <el-descriptions-item :label="$t('accountInfo.companyName')">{{ accountInfo.company_name || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="$t('accountInfo.contactPerson')">{{ accountInfo.contact_person || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="$t('accountInfo.balance')">
          {{ accountInfo.balance }} {{ accountInfo.currency }}
        </el-descriptions-item>
        <el-descriptions-item :label="$t('accountInfo.accountStatus')">
          <el-tag :type="accountInfo.status === 'active' ? 'success' : 'danger'">
            {{ accountInfo.status === 'active' ? $t('accountInfo.normal') : $t('accountInfo.abnormal') }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('accountInfo.rateLimit')">
          {{ accountInfo.rate_limit || 1000 }} {{ $t('accountInfo.requestsPerMin') }}
        </el-descriptions-item>
        <el-descriptions-item :label="$t('common.createdAt')" :span="2">
          {{ accountInfo.created_at }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>
    
    <el-card style="margin-top: 20px">
      <template #header>
        <div class="card-header">
          <span>{{ $t('accountInfo.apiKey') }}</span>
        </div>
      </template>
      
      <el-form label-width="120px">
        <el-form-item label="API Key">
          <el-input :value="maskedApiKey" readonly>
            <template #append>
              <el-button @click="copyApiKey">
                <el-icon><CopyDocument /></el-icon>
                {{ $t('accountInfo.copy') }}
              </el-button>
            </template>
          </el-input>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { getAccountInfo } from '@/api/account'

const { t } = useI18n()
const loading = ref(false)
const accountInfo = ref<any>(null)
const apiKey = ref(localStorage.getItem('api_key') || '')

const maskedApiKey = computed(() => {
  if (!apiKey.value) return ''
  return apiKey.value.substring(0, 10) + '****' + apiKey.value.substring(apiKey.value.length - 4)
})

const loadData = async () => {
  loading.value = true
  try {
    accountInfo.value = await getAccountInfo()
  } catch (error: any) {
    ElMessage.error(t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

const copyApiKey = () => {
  navigator.clipboard.writeText(apiKey.value)
  ElMessage.success(t('common.copiedToClipboard'))
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.account-info {
  width: 100%;
}

.card-header {
  font-weight: bold;
}
</style>

