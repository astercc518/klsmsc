<template>
  <div class="invites-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>{{ $t('botAudit.inviteManage') }}</span>
          <el-button type="primary" @click="showCreateDialog">{{ $t('botAudit.generateCode') }}</el-button>
        </div>
      </template>

      <!-- 筛选器 -->
      <el-form :inline="true" class="filter-form" style="margin-bottom: 20px">
        <el-form-item :label="$t('common.status')">
          <el-select v-model="filters.status" clearable :placeholder="$t('systemConfig.all')" style="width: 150px">
            <el-option :label="$t('botAudit.unused')" value="unused" />
            <el-option :label="$t('botAudit.used')" value="used" />
            <el-option :label="$t('botAudit.expired')" value="expired" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">{{ $t('smsRecords.query') }}</el-button>
          <el-button @click="resetFilters">{{ $t('common.reset') }}</el-button>
        </el-form-item>
      </el-form>

      <!-- 列表 -->
      <el-table :data="invites" v-loading="loading" style="width: 100%">
        <el-table-column prop="code" :label="$t('botAudit.inviteCode')" width="150">
          <template #default="scope">
            <el-tag size="large" @click="copyCode(scope.row.code)" style="cursor: pointer">
              {{ scope.row.code }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="sales_name" :label="$t('botAudit.sales')" width="120" />
        <el-table-column :label="$t('botAudit.configDetails')">
          <template #default="scope">
            <div v-if="scope.row.config">
              <el-tag type="info" size="small">{{ scope.row.config.country }}</el-tag>
              <span class="price-tag">${{ scope.row.config.price }}</span>
              <el-tag type="warning" size="small">{{ scope.row.config.business_type }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('common.status')" width="100">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">
              {{ getStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="$t('botAudit.generateTime')" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="200">
          <template #default="scope">
            <el-button link type="primary" @click="viewDetail(scope.row.code)">{{ $t('botAudit.detail') }}</el-button>
            <el-button link type="primary" @click="copyLink(scope.row.code)">{{ $t('botAudit.copyLink') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          :page-size="limit"
          :total="total"
          @current-change="loadData"
          layout="total, prev, pager, next"
        />
      </div>
    </el-card>

    <!-- 生成弹窗 -->
    <el-dialog v-model="dialogVisible" :title="$t('botAudit.createInvite')" width="500px">
      <el-form :model="form" label-width="100px">
        <el-form-item :label="$t('botAudit.businessType')">
          <el-radio-group v-model="form.business_type">
            <el-radio label="sms">{{ $t('botAudit.sms') }}</el-radio>
            <el-radio label="voice">{{ $t('botAudit.voice') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="$t('botAudit.countryCode')">
          <el-input v-model="form.country" :placeholder="$t('botAudit.countryCodePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('botAudit.contractPrice')">
          <el-input-number v-model="form.price" :precision="4" :step="0.001" :min="0" />
          <div class="tip">{{ $t('botAudit.referencePrice') }}</div>
        </el-form-item>
        <el-form-item :label="$t('botAudit.validPeriod')">
          <el-radio-group v-model="form.valid_hours">
            <el-radio :label="24">{{ $t('botAudit.hours24') }}</el-radio>
            <el-radio :label="48">{{ $t('botAudit.hours48') }}</el-radio>
            <el-radio :label="720">{{ $t('botAudit.days30') }}</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitCreate" :loading="submitting">{{ $t('botAudit.generate') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getInvites, createInvite } from '@/api/bot'
import { ElMessage } from 'element-plus'

const { t } = useI18n()
const invites = ref([])
const loading = ref(false)
const page = ref(1)
const limit = ref(20)
const total = ref(0)

const filters = ref({
  status: ''
})

const dialogVisible = ref(false)
const submitting = ref(false)
const form = reactive({
  country: 'CN',
  price: 0.06,
  business_type: 'sms',
  valid_hours: 24
})

const loadData = async () => {
  loading.value = true
  try {
    const res = await getInvites({ 
      page: page.value, 
      limit: limit.value,
      status: filters.value.status || undefined
    })
    invites.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  filters.value.status = ''
  page.value = 1
  loadData()
}

const copyCode = (code: string) => {
  navigator.clipboard.writeText(code)
  ElMessage.success(t('botAudit.inviteCodeCopied'))
}

const viewDetail = async (code: string) => {
  // TODO: 显示详情对话框
  ElMessage.info(t('botAudit.detailDeveloping'))
}

const showCreateDialog = () => {
  dialogVisible.value = true
}

const submitCreate = async () => {
  submitting.value = true
  try {
    await createInvite(form)
    ElMessage.success(t('botAudit.generateSuccess'))
    dialogVisible.value = false
    loadData()
  } catch (e) {
    // error handled by interceptor
  } finally {
    submitting.value = false
  }
}

const copyLink = (code: string) => {
  // 需要配置 Bot Username，这里暂时用 placeholder
  const link = `https://t.me/MySmscBot?start=${code}`
  navigator.clipboard.writeText(link)
  ElMessage.success(t('botAudit.linkCopied'))
}

const formatDate = (str: string) => {
  return new Date(str).toLocaleString()
}

const getStatusType = (status: string) => {
  const map: Record<string, string> = {
    unused: 'success',
    used: 'info',
    expired: 'danger'
  }
  return map[status] || ''
}

const getStatusText = (status: string) => {
  const keyMap: Record<string, string> = {
    unused: 'unused',
    used: 'used',
    expired: 'expired'
  }
  return keyMap[status] ? t(`botAudit.${keyMap[status]}`) : status
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.invites-container {
  width: 100%;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.price-tag {
  color: #f56c6c;
  font-weight: bold;
  margin: 0 8px;
}
.tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
