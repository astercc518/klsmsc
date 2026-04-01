<template>
  <div class="rate-search-container soft-card pd-lg animate-slide-up">
    <div class="search-header">
      <h3 class="text-gradient tactile-text">{{ $t('landing.rateSearch.title') || 'Real-time SMS Rates' }}</h3>
      <p class="text-secondary">{{ $t('landing.rateSearch.subtitle') || 'Search by country or region' }}</p>
    </div>
    
    <div class="search-box mg-t-md">
      <div v-if="isLoading" class="loading-placeholder soft-inset-wrapper">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span class="mg-l-sm">Fetching real-time rates...</span>
      </div>
      <div v-else class="soft-inset-wrapper" :class="{ 'is-focused': isSearching }">
        <el-select
          v-model="searchQuery"
          filterable
          remote
          :remote-method="filterCountries"
          :placeholder="$t('landing.rateSearch.placeholder') || 'Enter country name...'"
          class="search-input-modern"
          popper-class="rate-select-popper"
          :teleported="false"
          @focus="isSearching = true"
          @blur="isSearching = false"
          @change="handleSelect"
        >
          <template #prefix>
            <el-icon class="search-icon-gradient"><Search /></el-icon>
          </template>
          <el-option
            v-for="item in filteredCountries"
            :key="item.code"
            :label="item.name"
            :value="item.code"
          >
            <div class="country-option">
              <span class="opt-flag">{{ item.flag }}</span>
              <div class="opt-details">
                <span class="name">{{ item.name }}</span>
                <span class="code text-quaternary">(+{{ item.dial_code }})</span>
              </div>
            </div>
          </el-option>
        </el-select>
      </div>
    </div>

    <div v-if="selectedRate" class="rate-result mg-t-lg animate-bounce-in">
      <div class="rate-card-modern soft-card shimmer-effect">
        <div class="rate-card-inner">
          <div class="country-info-modern">
            <div class="flag-avatar soft-button">
              <span class="flag-large">{{ selectedRate.flag }}</span>
            </div>
            <div class="country-details">
              <h4>{{ selectedRate.name }}</h4>
              <p class="text-tertiary">Global Standard Route</p>
            </div>
          </div>
          <div class="price-display">
            <p class="price-label">Starting from</p>
            <div class="price-value">
              <span class="currency">$</span>
              <span class="amount text-gradient underline-glow">{{ selectedRate.price }}</span>
              <span class="unit">/sms</span>
            </div>
          </div>
        </div>
      </div>
      
      <div class="rate-actions mg-t-md">
        <div class="flex-center gap-sm">
          <button class="btn-main-lg soft-button w-100 tactile-text" @click="goToLogin">
            {{ $t('landing.rateSearch.cta') || 'Start Sending Now' }}
          </button>
          <button class="soft-button btn-icon-lg" @click="selectedRate = null">
            <el-icon><ArrowLeft /></el-icon>
          </button>
        </div>
      </div>
    </div>
    
    <div v-else class="popular-countries mg-t-lg">
      <p class="text-tertiary mg-b-sm font-sm uppercase-tracking">{{ $t('landing.rateSearch.popular') || 'Popular Destinations' }}</p>
      <div class="popular-grid">
        <div 
          v-for="(c, index) in popularCountries" 
          :key="c.code" 
          class="popular-item-modern soft-button animate-slide-up"
          :style="{ animationDelay: (index * 0.05) + 's' }"
          @click="selectCountry(c)"
        >
          <span class="pop-flag">{{ c.flag }}</span>
          <span class="pop-name">{{ c.name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Loading, ArrowLeft } from '@element-plus/icons-vue'
import { request } from '@/api'

const router = useRouter()
const isSearching = ref(false)
const isLoading = ref(true)

interface Country {
  name: string
  code: string
  dial_code: string
  flag: string
  price: string
}

const countries = ref<Country[]>([])
const filteredCountries = ref<Country[]>([])
const selectedRate = ref<Country | null>(null)
const searchQuery = ref('')

const countryData: Record<string, { flag: string; dial: string }> = {
  'CN': { flag: '🇨🇳', dial: '86' },
  'US': { flag: '🇺🇸', dial: '1' },
  'GB': { flag: '🇬🇧', dial: '44' },
  'VN': { flag: '🇻🇳', dial: '84' },
  'TH': { flag: '🇹🇭', dial: '66' },
  'ID': { flag: '🇮🇩', dial: '62' },
  'PH': { flag: '🇵🇭', dial: '63' },
  'MY': { flag: '🇲🇾', dial: '60' },
  'BR': { flag: '🇧🇷', dial: '55' },
  'MX': { flag: '🇲🇽', dial: '52' },
  'RU': { flag: '🇷🇺', dial: '7' },
  'IN': { flag: '🇮🇳', dial: '91' },
  'JP': { flag: '🇯🇵', dial: '81' },
  'KR': { flag: '🇰🇷', dial: '82' },
  'DE': { flag: '🇩🇪', dial: '49' },
  'FR': { flag: '🇫🇷', dial: '33' },
  'SG': { flag: '🇸🇬', dial: '65' },
  'AE': { flag: '🇦🇪', dial: '971' },
  'SA': { flag: '🇸🇦', dial: '966' },
  'TR': { flag: '🇹🇷', dial: '90' },
}

const getFlag = (code: string) => countryData[code]?.flag || '🌐'
const getDialCode = (code: string) => countryData[code]?.dial || ''

const fetchRates = async () => {
  try {
    isLoading.value = true
    const res: any = await request.get('/sms/public/rates')
    if (res.success && res.data) {
      countries.value = res.data.map((item: any) => ({
        ...item,
        flag: getFlag(item.code),
        dial_code: getDialCode(item.code) || item.dial_code || '---',
        price: item.price.toFixed(3)
      }))
      filteredCountries.value = countries.value
    }
  } catch (error) {
    console.error('Failed to fetch rates:', error)
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  fetchRates()
})

const popularCountries = computed(() => {
  // If we have dynamic countries, take common ones or first 4
  const popularCodes = ['CN', 'US', 'GB', 'VN']
  const sorted = countries.value.filter(c => popularCodes.includes(c.code))
  return sorted.length >= 4 ? sorted : countries.value.slice(0, 4)
})

const filterCountries = (query: string) => {
  if (query) {
    filteredCountries.value = countries.value.filter(c => 
      c.name.toLowerCase().includes(query.toLowerCase()) || 
      c.code.toLowerCase().includes(query.toLowerCase())
    )
  } else {
    filteredCountries.value = countries.value
  }
}

const handleSelect = (code: string) => {
  const country = countries.value.find(c => c.code === code)
  if (country) {
    selectedRate.value = country
  }
}

const selectCountry = (c: Country) => {
  searchQuery.value = c.code
  selectedRate.value = c
}

const goToLogin = () => {
  router.push('/login')
}
</script>

<style scoped>
.rate-search-container {
  width: 100%;
  max-width: 440px;
  position: relative;
  z-index: 10;
}

.pd-lg { padding: 32px; }
.mg-t-md { margin-top: 16px; }
.mg-t-lg { margin-top: 24px; }
.mg-b-sm { margin-bottom: 12px; }

.search-header h3 {
  font-size: 1.5rem;
  font-weight: 800;
  margin-bottom: 6px;
}

.search-header p {
  font-size: 0.95rem;
  opacity: 0.7;
}

.soft-inset-wrapper {
  position: relative;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-soft-in);
  padding: 0;
  background: rgba(0,0,0,0.3);
  transition: all 0.3s var(--ease-default);
  border: 1px solid rgba(255,255,255,0.05);
}

.loading-placeholder {
  height: 54px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--t3);
  font-size: 0.95rem;
}

.soft-inset-wrapper.is-focused {
  border-color: var(--primary);
  box-shadow: var(--shadow-soft-in), 0 0 15px rgba(59, 130, 246, 0.2);
  background: rgba(0,0,0,0.4);
}

:deep(.search-input-modern) {
  width: 100%;
}

:deep(.search-input-modern .el-input__wrapper) {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  height: 54px;
  padding: 0 16px !important;
}

:deep(.search-input-modern .el-input__inner) {
  color: var(--t1) !important;
  font-size: 1rem !important;
}

/* Popper Styling */
:deep(.rate-select-popper) {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-default) !important;
  box-shadow: var(--shadow-lg) !important;
  border-radius: var(--radius-lg) !important;
  margin-top: 8px !important;
}

:deep(.el-select-dropdown__list) {
  padding: 8px !important;
  max-height: 300px !important;
}

:deep(.el-select-dropdown__item) {
  border-radius: var(--radius-md) !important;
  margin-bottom: 4px !important;
  height: 44px !important;
  line-height: 44px !important;
  display: flex !important;
  align-items: center !important;
}

.search-icon-gradient {
  color: var(--primary);
  font-size: 20px;
}

.country-option {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.opt-flag { font-size: 1.25rem; flex-shrink: 0; }
.opt-details { display: flex; align-items: baseline; gap: 6px; overflow: hidden; }
.opt-details .name { font-weight: 500; }
.opt-details .code { font-size: 0.8rem; }

.rate-card-modern {
  border: none !important;
  background: linear-gradient(145deg, var(--bg-tertiary), var(--bg-secondary));
}

.rate-card-inner {
  padding: 24px;
}

.country-info-modern {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.flag-avatar {
  width: 54px;
  height: 54px;
  border-radius: 16px;
  background: var(--bg-secondary);
}

.flag-large { font-size: 2.2rem; }

.country-details h4 {
  font-size: 1.25rem;
  font-weight: 700;
  margin: 0;
  color: var(--t1);
}

.country-details p { font-size: 0.85rem; }

.price-display {
  padding-top: 16px;
  border-top: 1px solid rgba(255,255,255,0.05);
}

.price-label {
  font-size: 0.85rem;
  color: var(--t3);
  margin-bottom: 4px;
}

.price-value {
  display: flex;
  align-items: baseline; gap: 4px;
}

.currency {
  font-size: 1.2rem;
  font-weight: 600;
  color: var(--primary);
}

.amount {
  font-size: 2.75rem;
  font-weight: 900;
  line-height: 1;
}

.unit {
  font-size: 1rem;
  color: var(--t3);
  margin-left: 4px;
}

.popular-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.popular-item-modern {
  padding: 12px 16px;
  gap: 12px;
  font-size: 0.95rem;
  font-weight: 600;
  justify-content: flex-start;
  border-radius: var(--radius-lg);
}

.pop-flag { font-size: 1.25rem; }

.flex-center { display: flex; align-items: center; justify-content: center; }
.gap-sm { gap: 8px; }
.btn-icon-lg { width: 54px; height: 54px; border-radius: 16px; flex-shrink: 0; }

/* Effects */
.shimmer-effect {
  position: relative;
  overflow: hidden;
}

.shimmer-effect::before {
  content: "";
  position: absolute;
  top: -50%; left: -50%;
  width: 200%; height: 200%;
  background: linear-gradient(
    45deg,
    transparent 0%,
    rgba(255, 255, 255, 0.03) 45%,
    rgba(255, 255, 255, 0.08) 50%,
    rgba(255, 255, 255, 0.03) 55%,
    transparent 100%
  );
  transform: rotate(25deg);
  animation: shimmer 4s infinite;
}

@keyframes shimmer {
  0% { transform: translateX(-100%) rotate(25deg); }
  100% { transform: translateX(100%) rotate(25deg); }
}

.animate-bounce-in {
  animation: bounceIn 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55);
}

@keyframes bounceIn {
  0% { opacity: 0; scale: 0.8; }
  100% { opacity: 1; scale: 1; }
}

.font-sm { font-size: 0.8rem; }
.uppercase-tracking { text-transform: uppercase; letter-spacing: 0.1em; }
.underline-glow {
  position: relative;
}
.underline-glow::after {
  content: "";
  position: absolute;
  bottom: 4px; left: 0; right: 0;
  height: 8px;
  background: var(--primary);
  opacity: 0.2;
  filter: blur(8px);
  border-radius: 4px;
}

@media (max-width: 480px) {
  .rate-search-container { padding: 20px; }
  .amount { font-size: 2.25rem; }
}
</style>
