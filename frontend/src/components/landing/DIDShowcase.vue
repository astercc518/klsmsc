<template>
  <div class="did-showcase animate-slide-up">
    <div class="showcase-header">
      <div class="header-left">
        <h3 class="tactile-text">{{ $t('landing.didShowcase.title') }}</h3>
        <p>{{ $t('landing.didShowcase.subtitle') }}</p>
      </div>
      <div class="search-wrapper soft-inset">
        <el-input
          v-model="searchQuery"
          :placeholder="$t('landing.didShowcase.searchPlaceholder')"
          prefix-icon="Search"
          class="did-search"
        />
      </div>
    </div>

    <div class="did-grid">
      <div 
        v-for="(country, index) in filteredCountries" 
        :key="country.code" 
        class="did-card soft-card soft-card-hover animate-scale"
        :style="{ animationDelay: (index * 0.05) + 's' }"
      >
        <div class="card-flag">{{ getFlagEmoji(country.code) }}</div>
        <div class="card-info">
          <div class="country-name">{{ $t('landing.didShowcase.countries.' + country.code) }}</div>
          <div class="did-type">{{ country.type }} {{ $t('landing.didShowcase.typeSuffix') }}</div>
          <div class="did-price">
            <span class="currency">$</span>
            <span class="amount">{{ country.price }}</span>
            <span class="period">/mo</span>
          </div>
        </div>
        <div class="card-action">
          <button class="soft-button buy-btn">{{ $t('landing.didShowcase.rentNow') }}</button>
        </div>
      </div>
    </div>
    
    <div class="showcase-footer">
      <button class="btn-text">{{ $t('landing.didShowcase.exploreMore') }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Search } from '@element-plus/icons-vue'

interface CountryDID {
  name: string
  code: string
  price: string
  type: string
}

const searchQuery = ref('')

const countries = ref<CountryDID[]>([
  { name: 'United States', code: 'US', price: '0.85', typeKey: 'local' },
  { name: 'United Kingdom', code: 'GB', price: '1.20', typeKey: 'national' },
  { name: 'Thailand', code: 'TH', price: '4.50', typeKey: 'local' },
  { name: 'Vietnam', code: 'VN', price: '5.00', typeKey: 'mobile' },
  { name: 'Indonesia', code: 'ID', price: '3.80', typeKey: 'national' },
  { name: 'Philippines', code: 'PH', price: '6.50', typeKey: 'mobile' },
  { name: 'Cambodia', code: 'KH', price: '8.00', typeKey: 'local' },
  { name: 'Malaysia', code: 'MY', price: '2.50', typeKey: 'national' },
])

const filteredCountries = computed(() => {
  if (!searchQuery.value) return countries.value.slice(0, 8)
  const q = searchQuery.value.toLowerCase()
  return countries.value.filter(c => 
    c.name.toLowerCase().includes(q) || c.code.toLowerCase().includes(q)
  )
})

const getFlagEmoji = (countryCode: string) => {
  const codePoints = countryCode
    .toUpperCase()
    .split('')
    .map(char =>  127397 + char.charCodeAt(0))
  return String.fromCodePoint(...codePoints)
}
</script>

<style scoped>
.did-showcase {
  margin-top: 40px;
  width: 100%;
}

.showcase-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 32px;
  gap: 24px;
  flex-wrap: wrap;
}

.header-left h3 {
  font-size: 1.75rem;
  font-weight: 800;
  color: var(--t1);
  margin-bottom: 8px;
}

.header-left p {
  color: var(--t3);
  font-size: 0.95rem;
}

.search-wrapper {
  min-width: 280px;
  padding: 4px;
}

:deep(.did-search .el-input__wrapper) {
  background: transparent !important;
  box-shadow: none !important;
  height: 40px;
}

.did-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 20px;
}

.did-card {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card-flag {
  font-size: 2.5rem;
  filter: drop-shadow(0 4px 8px rgba(0,0,0,0.3));
}

.card-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.country-name {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--t1);
}

.did-type {
  font-size: 0.8rem;
  color: var(--t3);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.did-price {
  margin-top: 12px;
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.did-price .currency { font-size: 1rem; color: var(--primary); font-weight: 700; }
.did-price .amount { font-size: 1.75rem; color: var(--t1); font-weight: 800; }
.did-price .period { font-size: 0.85rem; color: var(--t3); }

.buy-btn {
  width: 100%;
  padding: 12px;
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.showcase-footer {
  margin-top: 32px;
  display: flex;
  justify-content: center;
}

.btn-text {
  background: none;
  border: none;
  color: var(--t3);
  font-weight: 600;
  cursor: pointer;
  transition: color 0.2s;
}

.btn-text:hover {
  color: var(--primary);
}

@media (max-width: 768px) {
  .showcase-header {
    flex-direction: column;
    align-items: flex-start;
  }
  .search-wrapper {
    width: 100%;
  }
}
</style>
