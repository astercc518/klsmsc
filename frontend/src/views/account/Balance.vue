<template>
  <div class="balance-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <h1 class="page-title">{{ $t('balance.title') }}</h1>
      <p class="page-desc">{{ $t('balance.pageDesc') }}</p>
    </div>
    
    <div class="balance-grid">
      <!-- 余额卡片 -->
      <div class="balance-card" v-loading="loading">
        <div class="card-bg"></div>
        <div class="card-glow"></div>
        <div class="card-shine"></div>
        
        <div class="card-content">
          <div class="balance-header">
            <div class="balance-icon">
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                <rect x="2" y="5" width="24" height="18" rx="4" stroke="currentColor" stroke-width="2"/>
                <path d="M2 11H26" stroke="currentColor" stroke-width="2"/>
                <circle cx="20" cy="17" r="3" stroke="currentColor" stroke-width="2"/>
              </svg>
            </div>
            <span class="balance-label">{{ $t('balance.currentBalance') }}</span>
          </div>
          
          <div class="balance-display">
            <span class="currency">$</span>
            <span class="amount">{{ balance.toFixed(2) }}</span>
          </div>
          
          <div class="balance-status">
            <div class="status-badge" :class="balance < lowBalanceThreshold ? 'warning' : 'success'">
              <svg v-if="balance < lowBalanceThreshold" width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M7 1L1 12H13L7 1Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
                <path d="M7 5V8M7 10V10.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
              <svg v-else width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="5.5" stroke="currentColor" stroke-width="1.5"/>
                <path d="M5 7L6.5 8.5L9 5.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <span>{{ balance < lowBalanceThreshold ? $t('balance.lowBalance') : $t('balance.sufficientBalance') }}</span>
            </div>
          </div>
          
          <div class="balance-info">
            <div class="info-item">
              <span class="info-label">{{ $t('balance.accountId') }}</span>
              <span class="info-value">{{ accountId || '-' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('balance.lowBalanceThreshold') }}</span>
              <span class="info-value">{{ lowBalanceThreshold }} {{ currency }}</span>
            </div>
          </div>
          
          <button type="button" class="recharge-btn" @click="openSalesTelegram">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <circle cx="9" cy="9" r="7" stroke="currentColor" stroke-width="1.5"/>
              <path d="M9 6V12M6 9H12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            {{ $t('balance.contactSales') }}
          </button>
        </div>
      </div>
      
      <!-- 充值说明 -->
      <div class="info-card">
        <div class="info-card-header">
          <div class="info-card-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2"/>
              <path d="M12 8V12M12 16V16.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </div>
          <h3 class="info-card-title">{{ $t('balance.rechargeInfo') }}</h3>
        </div>
        
        <div class="info-card-content">
          <div class="info-alert">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <circle cx="9" cy="9" r="7" stroke="currentColor" stroke-width="1.5"/>
              <path d="M9 6V10M9 12.5V13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            <p>{{ $t('balance.rechargeHint') }}</p>
          </div>
          
          <div class="info-section">
            <h4 class="section-title">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2 14V4C2 3.45 2.45 3 3 3H13C13.55 3 14 3.45 14 4V14L11 12L8 14L5 12L2 14Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
              </svg>
              {{ $t('balance.rateInfo') }}
            </h4>
            <ul class="info-list">
              <li>
                <span class="list-dot"></span>
                {{ $t('balance.rateDesc1') }}
              </li>
              <li>
                <span class="list-dot"></span>
                {{ $t('balance.rateDesc2') }}
              </li>
              <li>
                <span class="list-dot"></span>
                {{ $t('balance.rateDesc3') }}
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 近期交易（预留） -->
    <div class="transactions-section">
      <div class="section-header">
        <h2 class="section-title">近期交易</h2>
      </div>
      <div class="empty-transactions">
        <div class="empty-icon">
          <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
            <rect x="6" y="10" width="28" height="20" rx="3" stroke="currentColor" stroke-width="2"/>
            <path d="M6 16H34" stroke="currentColor" stroke-width="2"/>
            <path d="M12 24H20" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </div>
        <p class="empty-text">暂无交易记录</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { getBalance, getAccountInfo } from '@/api/account'

const { t } = useI18n()
const loading = ref(false)
const balance = ref(0)
const currency = ref('USD')
const lowBalanceThreshold = ref(100)
const accountId = ref('')
/** 归属商务 Telegram 用户名（不含 @），来自 /account/info */
const salesTgUsername = ref<string | null>(null)

const loadData = async () => {
  loading.value = true
  try {
    const res = await getBalance()
    balance.value = res.balance
    currency.value = res.currency
    lowBalanceThreshold.value = res.low_balance_threshold || 100
    accountId.value = String(res.account_id)

    try {
      const info = await getAccountInfo()
      salesTgUsername.value = info.sales_tg_username?.trim() || null
    } catch {
      salesTgUsername.value = null
    }
  } catch (error: any) {
    ElMessage.error(t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

/** 打开归属商务的 Telegram，便于客户联系充值 */
function openSalesTelegram() {
  const raw = salesTgUsername.value
  if (!raw) {
    ElMessage.warning(t('balance.noSalesTg'))
    return
  }
  const u = raw.replace(/^@+/, '').trim()
  if (!u) {
    ElMessage.warning(t('balance.noSalesTg'))
    return
  }
  window.open(`https://t.me/${encodeURIComponent(u)}`, '_blank', 'noopener,noreferrer')
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.balance-page {
  width: 100%;
  animation: fadeIn 0.5s var(--ease-default);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ========== 页面头部 ========== */
.page-header {
  margin-bottom: 32px;
}

.page-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
  letter-spacing: -0.02em;
}

.page-desc {
  font-size: 15px;
  color: var(--text-tertiary);
  margin: 0;
}

/* ========== 余额网格 ========== */
.balance-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-bottom: 32px;
}

/* ========== 余额卡片 ========== */
.balance-card {
  position: relative;
  background: var(--bg-card);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid var(--border-default);
  border-radius: 28px;
  padding: 32px;
  overflow: hidden;
}

.card-bg {
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(41, 151, 255, 0.1) 0%, transparent 50%);
  pointer-events: none;
}

.card-glow {
  position: absolute;
  width: 250px;
  height: 250px;
  border-radius: 50%;
  background: rgba(41, 151, 255, 0.25);
  filter: blur(80px);
  top: -100px;
  right: -50px;
  opacity: 0.6;
  pointer-events: none;
}

.card-shine {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.3) 50%, transparent 100%);
}

.card-content {
  position: relative;
  z-index: 2;
}

.balance-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}

.balance-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: linear-gradient(135deg, #2997FF 0%, #0071E3 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  box-shadow: 0 8px 24px rgba(41, 151, 255, 0.4);
}

.balance-label {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-tertiary);
}

.balance-display {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 20px;
}

.currency {
  font-size: 32px;
  font-weight: 500;
  color: var(--text-tertiary);
}

.amount {
  font-size: 56px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.03em;
  line-height: 1;
}

.balance-status {
  margin-bottom: 24px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 500;
}

.status-badge.success {
  background: rgba(50, 215, 75, 0.12);
  color: var(--success);
}

.status-badge.warning {
  background: rgba(255, 159, 10, 0.12);
  color: var(--warning);
}

.balance-info {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  padding: 20px 0;
  border-top: 1px solid var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: 24px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-quaternary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.info-value {
  font-size: 15px;
  font-weight: 500;
  color: var(--text-primary);
}

.recharge-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 16px;
  background: linear-gradient(135deg, #2997FF 0%, #0071E3 100%);
  border: none;
  border-radius: 14px;
  color: white;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s var(--ease-default);
  box-shadow: 0 8px 24px rgba(41, 151, 255, 0.35);
}

.recharge-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px rgba(41, 151, 255, 0.45);
}

/* ========== 充值说明卡片 ========== */
.info-card {
  background: var(--bg-card);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid var(--border-default);
  border-radius: 28px;
  padding: 32px;
  display: flex;
  flex-direction: column;
}

.info-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}

.info-card-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(135deg, #FF9F0A 0%, #FF8C00 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  box-shadow: 0 6px 20px rgba(255, 159, 10, 0.35);
}

.info-card-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.info-card-content {
  flex: 1;
}

.info-alert {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  background: rgba(100, 210, 255, 0.08);
  border: 1px solid rgba(100, 210, 255, 0.2);
  border-radius: 14px;
  margin-bottom: 24px;
}

.info-alert svg {
  flex-shrink: 0;
  color: var(--info);
  margin-top: 2px;
}

.info-alert p {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

.info-section {
  margin-bottom: 24px;
}

.info-section:last-child {
  margin-bottom: 0;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 12px;
}

.section-title svg {
  color: var(--text-tertiary);
}

.info-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.info-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  font-size: 14px;
  color: var(--text-tertiary);
}

.list-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-quaternary);
}

/* ========== 近期交易 ========== */
.transactions-section {
  background: var(--bg-card);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid var(--border-default);
  border-radius: 24px;
  padding: 24px;
}

.section-header {
  margin-bottom: 20px;
}

.section-header .section-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.empty-transactions {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 20px;
}

.empty-icon {
  color: var(--text-quaternary);
  margin-bottom: 16px;
}

.empty-text {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

/* ========== 响应式 ========== */
@media (max-width: 768px) {
  .balance-grid {
    grid-template-columns: 1fr;
  }
  
  .amount {
    font-size: 44px;
  }
  
  .balance-info {
    grid-template-columns: 1fr;
  }
}

/* ========== 亮色主题 - Apple Style ========== */
[data-theme="light"] .balance-card {
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 0.5px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

[data-theme="light"] .info-card {
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 0.5px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

[data-theme="light"] .transactions-section {
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 0.5px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

[data-theme="light"] .balance-icon {
  background: var(--gradient-primary);
  box-shadow: 0 8px 24px rgba(0, 122, 255, 0.3);
}

[data-theme="light"] .recharge-btn {
  background: var(--gradient-primary);
  box-shadow: 0 8px 24px rgba(0, 122, 255, 0.3);
}

[data-theme="light"] .recharge-btn:hover {
  box-shadow: 0 12px 32px rgba(0, 122, 255, 0.4);
}
</style>
