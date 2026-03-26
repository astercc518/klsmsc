<template>
  <el-card class="overview-card" shadow="never" v-loading="loading">
    <template #header>
      <span class="card-head">{{ $t('accountManage.overview') }}</span>
    </template>
    <el-descriptions v-if="info" :column="2" border>
      <el-descriptions-item :label="$t('dashboard.clientName')">
        {{ info.client_name || info.company_name || info.account_name || '—' }}
      </el-descriptions-item>
      <el-descriptions-item :label="$t('accountInfo.accountName')">{{ info.account_name }}</el-descriptions-item>
      <el-descriptions-item :label="$t('dashboard.tgAccount')">{{ formatTg(info.tg_username) }}</el-descriptions-item>
      <el-descriptions-item :label="$t('dashboard.country')">{{ countryLabel(info.country_code) }}</el-descriptions-item>
      <el-descriptions-item :label="$t('dashboard.unitPrice')">
        <template v-if="info.unit_price != null && info.unit_price > 0">
          {{ info.currency }} {{ fmtNum(info.unit_price) }} / {{ $t('dashboard.perSms') }}
        </template>
        <template v-else>—</template>
      </el-descriptions-item>
      <el-descriptions-item :label="$t('dashboard.balance')">
        {{ info.currency }} {{ fmtNum(info.balance) }}
      </el-descriptions-item>
      <el-descriptions-item :label="$t('dashboard.remainingSms')">
        {{ info.remaining_sms_estimate != null ? fmtNum(info.remaining_sms_estimate) : '—' }}
      </el-descriptions-item>
      <el-descriptions-item :label="$t('dashboard.salesContactTg')">{{ formatTg(info.sales_tg_username) }}</el-descriptions-item>
      <el-descriptions-item :label="$t('accountInfo.accountId')">{{ info.id }}</el-descriptions-item>
      <el-descriptions-item :label="$t('accountInfo.accountStatus')">
        <el-tag :type="statusTag(info.status)" size="small">{{ statusText(info.status) }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item :label="$t('accountInfo.email')" :span="2">{{ info.email || '—' }}</el-descriptions-item>
      <el-descriptions-item :label="$t('accountInfo.companyName')" :span="2">{{ info.company_name || '—' }}</el-descriptions-item>
      <el-descriptions-item :label="$t('accountInfo.contactPerson')" :span="2">{{ info.contact_person || '—' }}</el-descriptions-item>
      <el-descriptions-item :label="$t('accountInfo.rateLimit')" :span="2">
        {{ info.rate_limit ?? 1000 }} {{ $t('accountInfo.requestsPerMin') }}
      </el-descriptions-item>
      <el-descriptions-item :label="$t('common.createdAt')" :span="2">{{ info.created_at }}</el-descriptions-item>
    </el-descriptions>
    <el-empty v-else :description="$t('common.noData')" />
    <div v-if="info && salesTg" class="overview-actions">
      <el-button type="success" plain size="small" @click="openSalesTg">{{ $t('accountManage.contactSalesBtn') }}</el-button>
      <el-button size="small" @click="router.push('/account/balance')">{{ $t('menu.balance') }}</el-button>
      <el-button size="small" @click="router.push('/account/api-keys')">{{ $t('menu.apiKeys') }}</el-button>
      <el-button size="small" @click="router.push('/account/security')">{{ $t('menu.security') }}</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { AccountInfo } from '@/api/account'

const props = defineProps<{
  info: AccountInfo | null
  loading?: boolean
}>()

const router = useRouter()
const { t } = useI18n()

const salesTg = computed(() => {
  const s = props.info?.sales_tg_username?.trim()
  return s ? s.replace(/^@+/, '') : ''
})

function fmtNum(n: number) {
  const x = Number(n) || 0
  return x.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 4 })
}

function formatTg(raw?: string | null) {
  if (raw == null || String(raw).trim() === '') return '—'
  const u = String(raw).trim().replace(/^@+/, '')
  return u ? `@${u}` : '—'
}

function countryLabel(code?: string | null) {
  if (code == null || String(code).trim() === '') return '—'
  const c = String(code).trim().toUpperCase()
  const map: Record<string, string> = {
    CN: '中国',
    US: '美国',
    GB: '英国',
    BR: '巴西',
    BD: '孟加拉国',
    IN: '印度',
    ID: '印度尼西亚',
    MX: '墨西哥',
    PH: '菲律宾',
    VN: '越南',
    TH: '泰国',
    MY: '马来西亚',
    JP: '日本',
    KR: '韩国',
  }
  return map[c] || code
}

function statusTag(s: string) {
  if (s === 'active') return 'success'
  if (s === 'suspended') return 'warning'
  return 'info'
}

function statusText(s: string) {
  if (s === 'active') return t('accountInfo.normal')
  if (s === 'suspended') return t('dashboard.accountSuspended')
  if (s === 'closed') return t('dashboard.accountClosed')
  return s || '—'
}

function openSalesTg() {
  if (!salesTg.value) return
  window.open(`https://t.me/${encodeURIComponent(salesTg.value)}`, '_blank', 'noopener,noreferrer')
}
</script>

<style scoped>
.card-head {
  font-weight: 600;
  font-size: 15px;
}

.overview-actions {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
