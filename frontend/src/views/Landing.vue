<template>
  <div class="landing-site" :class="{ 'is-light': !isDark, 'is-dark': isDark }">
    <!-- ===== 顶部导航 ===== -->
    <header class="hd" :class="{ fixed: scrolled }">
      <div class="w hd-inner">
        <a href="/" class="hd-logo" aria-label="考拉出海 首页">
          <img src="/favicon.svg" alt="" class="hd-logo-icon" width="32" height="32" />
          <span class="hd-logo-text">Kao<em>lach</em></span>
        </a>
        <nav class="hd-nav" :class="{ show: mobileMenu }" aria-label="主导航">
          <a href="#" class="hd-nav-item" @click.prevent="scrollTop">{{ $t('landing.nav.home') }}</a>
          <div class="hd-nav-item hd-drop">
            <span>{{ $t('landing.nav.smsProducts') }} <i class="arrow-d" aria-hidden="true"></i></span>
            <div class="hd-drop-menu">
              <a href="#products" @click="mobileMenu=false">
                <strong>{{ $t('landing.nav.intlSms') }}</strong>
                <small>{{ $t('landing.nav.intlSmsDesc') }}</small>
              </a>
              <a href="#products" @click="mobileMenu=false">
                <strong>{{ $t('landing.nav.verifySms') }}</strong>
                <small>{{ $t('landing.nav.verifySmsDesc') }}</small>
              </a>
              <a href="#products" @click="mobileMenu=false">
                <strong>{{ $t('landing.nav.marketingSms') }}</strong>
                <small>{{ $t('landing.nav.marketingSmsDesc') }}</small>
              </a>
              <a href="#products" @click="mobileMenu=false">
                <strong>{{ $t('landing.nav.smsApi') }}</strong>
                <small>{{ $t('landing.nav.smsApiDesc') }}</small>
              </a>
            </div>
          </div>
          <a href="#solutions" class="hd-nav-item" @click="mobileMenu=false">{{ $t('landing.nav.solutions') }}</a>
          <a href="#pricing" class="hd-nav-item" @click="mobileMenu=false">{{ $t('landing.nav.pricing') }}</a>
          <div class="hd-nav-item hd-drop">
            <span>{{ $t('landing.nav.support') }} <i class="arrow-d" aria-hidden="true"></i></span>
            <div class="hd-drop-menu">
              <a href="#faq" @click="mobileMenu=false">{{ $t('landing.nav.faq') }}</a>
              <a href="#flow" @click="mobileMenu=false">{{ $t('landing.nav.flow') }}</a>
              <a href="#contact" @click="mobileMenu=false">{{ $t('landing.nav.contact') }}</a>
            </div>
          </div>
          <a href="#about" class="hd-nav-item" @click="mobileMenu=false">{{ $t('landing.nav.about') }}</a>
        </nav>
        <div class="hd-right">
          <button type="button" class="hd-pill" @click="toggleTheme" :title="isDark ? 'Light' : 'Dark'" aria-label="切换主题">
            <svg v-if="isDark" width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="3.2" stroke="currentColor" stroke-width="1.4"/><path d="M8 1.5v1.8M8 12.7v1.8M1.5 8h1.8M12.7 8h1.8M3.4 3.4l1.3 1.3M11.3 11.3l1.3 1.3M3.4 12.6l1.3-1.3M11.3 4.7l1.3-1.3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
            <svg v-else width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M13.6 9.8A6 6 0 0 1 6.2 2.4a6 6 0 1 0 7.4 7.4Z" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <button type="button" class="hd-pill" @click="toggleLang">{{ currentLang === 'zh-CN' ? $t('language.shortEn') : $t('language.zh') }}</button>
          <router-link to="/login" class="hd-btn-test">{{ $t('landing.nav.freeTest') }}</router-link>
          <button type="button" class="hd-burger" @click="mobileMenu=!mobileMenu" aria-label="打开菜单" aria-expanded="false" :aria-expanded="mobileMenu"><span/><span/><span/></button>
        </div>
      </div>
    </header>

    <!-- ===== Hero Banner ===== -->
    <section class="hero">
      <div class="hero-bg">
        <div class="hero-glow g1"></div>
        <div class="hero-glow g2"></div>
        <div class="hero-glow g3"></div>
      </div>
      <div class="w hero-inner">
        <div class="hero-left">
          <div class="hero-glass">
            <div class="hero-kw">
              <span>{{ $t('brand.name') }}</span>
              <span>Bulk</span>
              <span>SMS</span>
            </div>
            <h1 class="hero-title">{{ $t('landing.hero.title') }}<em>{{ $t('landing.hero.titleHighlight') }}</em>{{ $t('landing.hero.titleSuffix') }}</h1>
            <p class="hero-subtitle">{{ $t('landing.hero.subtitle') }}</p>
            <p class="hero-desc">{{ $t('landing.hero.desc') }}</p>
            <div class="hero-btns">
              <router-link to="/login" class="btn-main btn-glass">{{ $t('landing.hero.freeTest') }}</router-link>
              <a href="#contact" class="btn-outline btn-glass-outline">{{ $t('landing.hero.contact') }}</a>
            </div>
            <div class="hero-tags">
              <span class="htag htag-blue">{{ $t('landing.hero.tag1') }}</span>
              <span class="htag">{{ $t('landing.hero.tag2') }}</span>
              <span class="htag">{{ $t('landing.hero.tag3') }}</span>
            </div>
            <p class="hero-trust">{{ $t('landing.hero.trust', { n: '20,000+' }) }}</p>
          </div>
        </div>
        <div class="hero-right">
          <div class="hero-phone">
            <div class="phone-frame">
              <div class="phone-notch"></div>
              <div class="phone-screen">
                <div class="phone-msg phone-msg-in">{{ $t('landing.phoneMsg1') }}</div>
                <div class="phone-msg phone-msg-in">{{ $t('landing.phoneMsg2') }}</div>
                <div class="phone-msg phone-msg-out">{{ $t('landing.phoneMsg3') }}</div>
                <div class="phone-msg phone-msg-in">{{ $t('landing.phoneMsg4') }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== SMS 解决方案 ===== -->
    <section id="solutions" class="sec">
      <div class="w">
        <p class="sec-label">{{ $t('landing.sections.solutions') }}</p>
        <h2 class="sec-title">{{ $t('landing.sections.solutionsTitle') }}</h2>
        <p class="sec-desc">{{ $t('landing.solutionsDesc') }}</p>
        <div class="sec-actions">
          <router-link to="/login" class="btn-main">{{ $t('landing.ctaOpenAccount') }}</router-link>
          <a href="#faq" class="btn-outline">{{ $t('landing.ctaOnlineConsult') }}</a>
        </div>
        <div class="sol-grid">
          <div class="sol-card" v-for="s in solutions" :key="s.title">
            <h4>{{ s.title }}</h4>
            <p>{{ s.desc }}</p>
            <a href="#products" class="sol-link">{{ $t('landing.solLink') }} →</a>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== SMS 产品 ===== -->
    <section id="products" class="sec sec-dark">
      <div class="w">
        <p class="sec-label">{{ $t('landing.sections.products') }}</p>
        <h2 class="sec-title">{{ $t('landing.sections.productsTitle') }}</h2>
        <p class="sec-desc">{{ $t('landing.productsDesc') }}</p>
        <div class="prod-tabs">
          <button v-for="(p,i) in products" :key="i" :class="['ptab', {active: prodIdx===i}]" @click="prodIdx=i" type="button">
            <span class="ptab-icon" aria-hidden="true"><component :is="p.icon" /></span>
            <span class="ptab-text">{{ p.label }}</span>
          </button>
        </div>
        <div class="prod-body">
          <div class="prod-info">
            <div class="prod-item" v-for="(item,j) in products[prodIdx].items" :key="j">
              <h4>{{ item.title }}</h4>
              <p>{{ item.desc }}</p>
            </div>
            <div class="prod-btns">
              <router-link to="/login" class="btn-main btn-sm">{{ $t('landing.ctaTryNow') }}</router-link>
              <a href="#pricing" class="btn-outline btn-sm">{{ $t('landing.ctaLearnMore') }}</a>
            </div>
          </div>
          <div class="prod-visual">
            <div class="prod-card-visual">
              <div class="pcv-item" v-for="(item,j) in products[prodIdx].items" :key="j">
                <span class="pcv-dot"></span>
                {{ item.title }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 优势 ===== -->
    <section id="advantages" class="sec">
      <div class="w">
        <p class="sec-label">{{ $t('landing.sections.advantages') }}</p>
        <h2 class="sec-title">{{ $t('landing.sections.advantagesTitle') }}</h2>
        <p class="sec-desc">{{ $t('landing.advantagesDesc') }}</p>
        <div class="adv-grid">
          <div class="adv-card" v-for="a in advantages" :key="a.title">
            <div class="adv-icon" aria-hidden="true"><component :is="a.icon" /></div>
            <h4>{{ a.title }}</h4>
            <p>{{ a.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 覆盖范围 & 定价 ===== -->
    <section id="pricing" class="sec sec-dark">
      <div class="w">
        <p class="sec-label">{{ $t('landing.sections.pricingLabel') }}</p>
        <h2 class="sec-title">{{ $t('landing.sections.pricingTitle') }}</h2>
        <p class="sec-desc">{{ $t('landing.pricingDesc') }}</p>
        <div class="coverage-nums">
          <div class="cn"><span class="cn-val">190+</span><span class="cn-label">{{ $t('landing.coverageLabels.countries') }}</span></div>
          <div class="cn"><span class="cn-val">800+</span><span class="cn-label">{{ $t('landing.coverageLabels.operators') }}</span></div>
          <div class="cn"><span class="cn-val">95%+</span><span class="cn-label">{{ $t('landing.coverageLabels.delivery') }}</span></div>
          <div class="cn"><span class="cn-val">3min</span><span class="cn-label">{{ $t('landing.coverageLabels.viewTime') }}</span></div>
        </div>
        <div class="price-cards">
          <div class="price-card" v-for="p in priceFeatures" :key="p.title">
            <h4>{{ p.title }}</h4>
            <p>{{ p.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== FAQ ===== -->
    <section id="faq" class="sec">
      <div class="w">
        <p class="sec-label">{{ $t('landing.sections.faq') }}</p>
        <h2 class="sec-title">{{ $t('landing.sections.faqTitle') }}</h2>
        <p class="sec-desc">{{ $t('landing.faqDesc') }}</p>
        <div class="sec-actions">
          <router-link to="/login" class="btn-main btn-sm">{{ $t('landing.ctaSupport') }}</router-link>
          <a href="#contact" class="btn-outline btn-sm">{{ $t('landing.nav.contact') }}</a>
        </div>
        <div class="faq-list">
          <details class="faq-item" v-for="f in faqs" :key="f.q">
            <summary>{{ f.q }}</summary>
            <p>{{ f.a }}</p>
          </details>
        </div>
      </div>
    </section>

    <!-- ===== 使用流程 ===== -->
    <section id="flow" class="sec sec-dark">
      <div class="w">
        <p class="sec-label">{{ $t('landing.sections.flow') }}</p>
        <h2 class="sec-title">{{ $t('landing.sections.flowTitle') }}</h2>
        <p class="sec-desc">{{ $t('landing.flowDesc') }}</p>
        <div class="flow-row">
          <div class="flow-step" v-for="(s,i) in flowSteps" :key="i">
            <span class="flow-badge">step {{ i+1 }}</span>
            <h4>{{ s.title }}</h4>
            <p>{{ s.desc }}</p>
          </div>
        </div>
        <div class="sec-actions">
          <router-link to="/login" class="btn-main">{{ $t('landing.ctaTryNow') }}</router-link>
          <a href="#products" class="btn-outline">{{ $t('landing.ctaViewSteps') }}</a>
        </div>
      </div>
    </section>

    <!-- ===== 联系我们 - Telegram 联系卡片 ===== -->
    <section id="contact" class="sec sec-contact">
      <div class="w">
        <p class="sec-label">{{ $t('landing.nav.contact') }}</p>
        <h2 class="sec-title">{{ $t('landing.contact.sectionTitle') }}</h2>
        <div class="contact-card">
          <div class="contact-logo">
            <img src="/logo.svg" alt="考拉出海" class="contact-logo-img" />
          </div>
          <h3 class="contact-title">{{ $t('landing.contact.title') }}</h3>
          <p class="contact-username">@kaolachbot</p>
          <p class="contact-desc">{{ $t('landing.contact.line1') }}</p>
          <p class="contact-desc">{{ $t('landing.contact.line2') }}</p>
          <p class="contact-desc">{{ $t('landing.contact.line3') }}</p>
          <a href="https://t.me/kaolachbot" target="_blank" rel="noopener noreferrer" class="contact-btn">{{ $t('landing.contact.sendMessage') }}</a>
        </div>
      </div>
    </section>

    <!-- ===== 数字事实 ===== -->
    <section class="sec sec-facts">
      <div class="w">
        <h3 class="sec-title" style="font-size:1.4rem">{{ $t('landing.factsTitle') }}</h3>
        <div class="facts-grid">
          <div class="fact-item" v-for="(f, i) in $tm('landing.facts')" :key="i"><span class="fact-val">{{ f.val }}</span><span class="fact-lbl">{{ f.lbl }}</span></div>
        </div>
      </div>
    </section>

    <!-- ===== CTA ===== -->
    <section id="about" class="sec sec-cta">
      <div class="w cta-box">
        <h2>{{ $t('landing.ctaTitle') }}</h2>
        <router-link to="/login" class="btn-main btn-lg">{{ $t('landing.cta') }}</router-link>
      </div>
    </section>

    <!-- ===== Footer ===== -->
    <footer class="ft">
      <div class="w ft-inner">
        <div class="ft-brand">
          <span class="hd-logo-text" style="font-size:1.5rem">Kao<em>lach</em></span>
          <p>{{ $t('landing.footerDesc') }}</p>
        </div>
        <div class="ft-col">
          <h5>{{ $t('landing.footerProducts') }}</h5>
          <a href="#products">{{ $t('landing.nav.intlSms') }}</a>
          <a href="#products">{{ $t('landing.nav.verifySms') }}</a>
          <a href="#products">{{ $t('landing.nav.marketingSms') }}</a>
          <a href="#products">{{ $t('landing.nav.smsApi') }}</a>
          <a href="#pricing">{{ $t('landing.nav.pricing') }}</a>
          <a href="#flow">{{ $t('landing.nav.flow') }}</a>
          <a href="#faq">{{ $t('landing.nav.faq') }}</a>
        </div>
        <div class="ft-col">
          <h5>{{ $t('landing.footerAbout') }}</h5>
          <a href="#contact">{{ $t('landing.footerContact') }}</a>
          <a href="#about">{{ $t('landing.footerAboutUs') }}</a>
        </div>
      </div>
      <div class="w ft-bottom">
        <p>© 2024 - {{ new Date().getFullYear() }} {{ $t('brand.name') }}. All Rights Reserved.</p>
        <div class="ft-links">
          <a href="#faq">{{ $t('landing.footerSupport') }}</a>
          <a href="#about">{{ $t('landing.footerTerms') }}</a>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { setLocale, getLocale } from '@/i18n'

const { t, locale } = useI18n()
const isDark = ref(true)
const currentLang = ref<string>(locale.value)
const scrolled = ref(false)
const iconProps = {
  class: 'landing-svg-icon',
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: '1.8',
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': 'true'
}
const IconGlobe = () => h('svg', iconProps, [h('path', { d: 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z' }), h('path', { d: 'M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z' })])
const IconPhone = () => h('svg', iconProps, [h('path', { d: 'M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z' })])
const IconPlug = () => h('svg', iconProps, [h('path', { d: 'M12 22v-5M9 9V2M15 9V2M6 12H2v4a2 2 0 0 0 2 2h2M18 12h4v4a2 2 0 0 1-2 2h-2M6 5h12a2 2 0 0 1 2 2v3H4V7a2 2 0 0 1 2-2z' })])
const IconGlobeAlt = () => h('svg', iconProps, [h('circle', { cx: '12', cy: '12', r: '10' }), h('path', { d: 'M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z' }), h('path', { d: 'M2 12h20' })])
const IconEnvelope = () => h('svg', iconProps, [h('path', { d: 'M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z' }), h('path', { d: 'm22 6-10 7L2 6' })])
const IconBolt = () => h('svg', iconProps, [h('path', { d: 'M13 2L3 14h9l-1 8 10-12h-9l1-8z' })])
const IconChartBar = () => h('svg', iconProps, [h('path', { d: 'M12 20V10M18 20V4M6 20v-4' })])

const mobileMenu = ref(false)
const prodIdx = ref(0)

function onScroll() { scrolled.value = window.scrollY > 20 }
function scrollTop() { window.scrollTo({ top: 0, behavior: 'smooth' }); mobileMenu.value = false }

function toggleTheme() {
  isDark.value = !isDark.value
  const theme = isDark.value ? 'dark' : 'light'
  document.documentElement.setAttribute('data-theme', theme)
  document.documentElement.classList.toggle('dark', isDark.value)
  localStorage.setItem('theme', theme)
}

function toggleLang() {
  const newLang = currentLang.value === 'zh-CN' ? 'en-US' : 'zh-CN'
  currentLang.value = newLang
  setLocale(newLang as 'zh-CN' | 'en-US')
}

watch(locale, () => { document.title = t('landing.pageTitle') })
onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  document.title = t('landing.pageTitle')
  const savedTheme = localStorage.getItem('theme') || 'dark'
  isDark.value = savedTheme === 'dark'
  document.documentElement.setAttribute('data-theme', savedTheme)
  document.documentElement.classList.toggle('dark', isDark.value)
  const saved = getLocale()
  currentLang.value = saved
})
onUnmounted(() => window.removeEventListener('scroll', onScroll))

const solutionKeys = ['finance', 'invest', 'ecommerce', 'sports', 'entertainment', 'game'] as const
const solutions = computed(() => solutionKeys.map(k => ({
  title: t(`landing.solutions.${k}.title`),
  desc: t(`landing.solutions.${k}.desc`),
})))

const products = computed(() => [
  { icon: IconGlobe, label: t('landing.productLabels.intl'), items: [
    { title: t('landing.productIntl.0.title'), desc: t('landing.productIntl.0.desc') },
    { title: t('landing.productIntl.1.title'), desc: t('landing.productIntl.1.desc') },
  ]},
  { icon: IconPhone, label: t('landing.productLabels.verify'), items: [
    { title: t('landing.productVerify.0.title'), desc: t('landing.productVerify.0.desc') },
    { title: t('landing.productVerify.1.title'), desc: t('landing.productVerify.1.desc') },
    { title: t('landing.productVerify.2.title'), desc: t('landing.productVerify.2.desc') },
  ]},
  { icon: IconPlug, label: t('landing.productLabels.api'), items: [
    { title: t('landing.productApi.0.title'), desc: t('landing.productApi.0.desc') },
    { title: t('landing.productApi.1.title'), desc: t('landing.productApi.1.desc') },
  ]},
])

const advKeys = ['coverage', 'industry', 'channel', 'report'] as const
const advantages = computed(() => [
  { icon: IconGlobeAlt, title: t(`landing.advantages.${advKeys[0]}.title`), desc: t(`landing.advantages.${advKeys[0]}.desc`) },
  { icon: IconEnvelope, title: t(`landing.advantages.${advKeys[1]}.title`), desc: t(`landing.advantages.${advKeys[1]}.desc`) },
  { icon: IconBolt, title: t(`landing.advantages.${advKeys[2]}.title`), desc: t(`landing.advantages.${advKeys[2]}.desc`) },
  { icon: IconChartBar, title: t(`landing.advantages.${advKeys[3]}.title`), desc: t(`landing.advantages.${advKeys[3]}.desc`) },
])

const priceFeatures = computed(() => [
  { title: t('landing.priceFeatures.0.title'), desc: t('landing.priceFeatures.0.desc') },
  { title: t('landing.priceFeatures.1.title'), desc: t('landing.priceFeatures.1.desc') },
  { title: t('landing.priceFeatures.2.title'), desc: t('landing.priceFeatures.2.desc') },
])

const faqs = computed(() => [
  { q: t('landing.faqs.0.q'), a: t('landing.faqs.0.a') },
  { q: t('landing.faqs.1.q'), a: t('landing.faqs.1.a') },
  { q: t('landing.faqs.2.q'), a: t('landing.faqs.2.a') },
  { q: t('landing.faqs.3.q'), a: t('landing.faqs.3.a') },
  { q: t('landing.faqs.4.q'), a: t('landing.faqs.4.a') },
  { q: t('landing.faqs.5.q'), a: t('landing.faqs.5.a') },
])

const flowSteps = computed(() => [
  { title: t('landing.flowSteps.0.title'), desc: t('landing.flowSteps.0.desc') },
  { title: t('landing.flowSteps.1.title'), desc: t('landing.flowSteps.1.desc') },
  { title: t('landing.flowSteps.2.title'), desc: t('landing.flowSteps.2.desc') },
  { title: t('landing.flowSteps.3.title'), desc: t('landing.flowSteps.3.desc') },
])
</script>

<style>
/* ============================================================
   考拉出海 Landing — 完全模仿 GoTone SMS 风格（非 scoped 以确保样式生效）
   ============================================================ */
.landing-site {
  --blue: #3478f6;
  --blue2: #2563eb;
  --blue-glow: rgba(52,120,246,.35);
  --purple: #7c3aed;
  --dark: #0b0d1a;
  --dark2: #10122a;
  --card: rgba(255,255,255,.04);
  --border: rgba(255,255,255,.08);
  --t1: #f0f1f5;
  --t2: rgba(240,241,245,.7);
  --t3: rgba(240,241,245,.52);
  --radius: 12px;
  background: var(--dark);
  color: var(--t1);
  font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
  scroll-behavior: smooth;
  overflow-x: hidden;
  min-height: 100vh;
}
.landing-site.is-light {
  --dark: #f5f5f7;
  --dark2: #e8e8ed;
  --card: rgba(0,0,0,.04);
  --border: rgba(0,0,0,.08);
  --t1: #1d1d1f;
  --t2: rgba(29,29,31,.72);
  --t3: rgba(29,29,31,.52);
  background: var(--dark);
  color: var(--t1);
}
.landing-site.is-light .hd.fixed { background: rgba(245,245,247,.92); border-color: rgba(0,0,0,.06); }
.landing-site.is-light .hd-logo-text { color: #1d1d1f; }
.landing-site.is-light .hd-logo-text em { color: var(--blue); }
.landing-site.is-light .hd-nav-item { color: var(--t2); }
.landing-site.is-light .hd-nav-item:hover { color: var(--t1); }
.landing-site.is-light .hd-pill { background: rgba(0,0,0,.06); border-color: rgba(0,0,0,.1); color: var(--t2); }
.landing-site.is-light .hd-pill:hover { background: rgba(0,0,0,.1); color: var(--t1); }
.landing-site.is-light .hero-glass { background: rgba(255,255,255,.7); border-color: rgba(0,0,0,.08); }
.landing-site.is-light .hero-title { color: #1d1d1f; }
.landing-site.is-light .sec-dark { background: var(--dark2); }
.landing-site.is-light .g1 { background: radial-gradient(circle, rgba(52,120,246,.15) 0%, rgba(52,120,246,.04) 50%, transparent 70%); }
.landing-site.is-light .g2, .landing-site.is-light .g3 { opacity: 0.6; }

/* 明亮模式：下拉菜单、按钮、卡片等 */
.landing-site.is-light .hd-drop-menu { background: rgba(255,255,255,.96); border-color: rgba(0,0,0,.08); box-shadow: 0 12px 40px rgba(0,0,0,.12); }
.landing-site.is-light .hd-drop-menu a { color: var(--t2); }
.landing-site.is-light .hd-drop-menu a:hover { background: rgba(0,0,0,.04); color: var(--t1); }
.landing-site.is-light .hd-drop-menu a strong { color: var(--t1); }
.landing-site.is-light .hd-drop-menu a small { color: var(--t3); }

.landing-site.is-light .btn-outline { border-color: rgba(0,0,0,.15); color: var(--t2); }
.landing-site.is-light .btn-outline:hover { border-color: rgba(0,0,0,.25); color: var(--t1); background: rgba(0,0,0,.04); }

.landing-site.is-light .hero-kw span { background: rgba(52,120,246,.1); border-color: rgba(52,120,246,.25); }
.landing-site.is-light .htag { background: rgba(0,0,0,.04); border-color: rgba(0,0,0,.1); color: var(--t2); }
.landing-site.is-light .htag:hover { border-color: rgba(0,0,0,.15); background: rgba(0,0,0,.06); }
.landing-site.is-light .htag-blue { background: rgba(52,120,246,.1); border-color: rgba(52,120,246,.25); }
.landing-site.is-light .htag-blue:hover { border-color: rgba(52,120,246,.35); background: rgba(52,120,246,.15); }

.landing-site.is-light .sol-card,
.landing-site.is-light .adv-card,
.landing-site.is-light .price-card,
.landing-site.is-light .flow-step,
.landing-site.is-light .fact-item,
.landing-site.is-light .faq-item { background: rgba(255,255,255,.8); border-color: rgba(0,0,0,.08); box-shadow: 0 2px 12px rgba(0,0,0,.06); }
.landing-site.is-light .sol-card:hover,
.landing-site.is-light .adv-card:hover,
.landing-site.is-light .price-card:hover,
.landing-site.is-light .flow-step:hover,
.landing-site.is-light .fact-item:hover { border-color: rgba(52,120,246,.3); box-shadow: 0 4px 20px rgba(0,0,0,.08); }
.landing-site.is-light .faq-item:hover,
.landing-site.is-light .faq-item[open] { border-color: rgba(52,120,246,.2); background: rgba(52,120,246,.04); }

.landing-site.is-light .cn { background: rgba(255,255,255,.8); border-color: rgba(0,0,0,.08); }
.landing-site.is-light .cn:hover { border-color: rgba(52,120,246,.25); }

.landing-site.is-light .ptab { background: rgba(0,0,0,.04); border-color: rgba(0,0,0,.1); }
.landing-site.is-light .ptab:hover { border-color: rgba(52,120,246,.3); }
.landing-site.is-light .ptab.active { background: rgba(52,120,246,.1); border-color: var(--blue); }

.landing-site.is-light .prod-card-visual { background: rgba(255,255,255,.7); border-color: rgba(0,0,0,.08); }
.landing-site.is-light .pcv-item { background: rgba(52,120,246,.06); border-color: rgba(52,120,246,.12); color: var(--t1); }
.landing-site.is-light .pcv-item:hover { border-color: rgba(52,120,246,.2); background: rgba(52,120,246,.1); }

.landing-site.is-light .phone-frame { background: linear-gradient(160deg,#e8e8ed,#d8d8e0); border-color: rgba(0,0,0,.12); }
.landing-site.is-light .phone-notch { background: #e8e8ed; }
.landing-site.is-light .phone-msg-in { background: rgba(52,120,246,.12); border-color: rgba(52,120,246,.2); color: var(--t1); }
.landing-site.is-light .phone-msg-out { background: rgba(0,0,0,.06); border-color: rgba(0,0,0,.1); color: var(--t2); }

.landing-site.is-light .contact-card { background: rgba(255,255,255,.98); border-color: rgba(0,0,0,.08); box-shadow: 0 16px 40px rgba(0,0,0,.12); }
.landing-site.is-light .contact-title { color: #1d1d1f; }
.landing-site.is-light .contact-username { color: #6e6e73; }
.landing-site.is-light .contact-desc { color: #424245; }

.landing-site.is-light .sec-facts { background: linear-gradient(135deg, rgba(52,120,246,.06), rgba(34,197,94,.03)); }
.landing-site.is-light .cta-box { background: rgba(255,255,255,.8); border-color: rgba(0,0,0,.08); }
.landing-site.is-light .ft { border-top-color: rgba(0,0,0,.06); }
.landing-site.is-light .ft-col h5 { color: var(--t1); }
@media (prefers-reduced-motion: reduce) {
  .landing-site { scroll-behavior: auto; }
  .landing-site .hd, .landing-site .sol-card, .landing-site .adv-card, .landing-site .ptab,
  .landing-site .btn-main, .landing-site .btn-outline, .landing-site .hd-nav-item,
  .landing-site .hd-drop-menu a, .landing-site .faq-item summary,
  .landing-site .price-card, .landing-site .flow-step, .landing-site .fact-item, .landing-site .cn { transition: none; }
}
.landing-site *, .landing-site *::before, .landing-site *::after { box-sizing: border-box; margin: 0; padding: 0; }
.landing-site .w { max-width: 1180px; margin: 0 auto; padding: 0 24px; }
.landing-site [id] { scroll-margin-top: 80px; }
.landing-site a { color: inherit; text-decoration: none; }

/* ===== Header ===== */
.landing-site .hd { position: fixed; top: 0; left: 0; right: 0; z-index: 300; transition: background .3s, border-color .3s, box-shadow .3s; background: transparent; }
.landing-site .hd.fixed { background: rgba(11,13,26,.92); backdrop-filter: blur(16px); border-bottom: 1px solid var(--border); box-shadow: 0 2px 20px rgba(0,0,0,.3); }
.landing-site .hd-inner { display: flex; align-items: center; height: 68px; }
.landing-site .hd-logo { display: flex; align-items: center; gap: 8px; flex-shrink: 0; cursor: pointer; }
.landing-site .hd-logo-icon { flex-shrink: 0; border-radius: 6px; }
.landing-site .hd-logo:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; border-radius: 6px; }
.landing-site .hd-logo-text { font-size: 1.4rem; font-weight: 800; color: #fff; letter-spacing: -.02em; }
.landing-site .hd-logo-text em { font-style: normal; color: var(--blue); }

.landing-site .hd-nav { display: flex; align-items: center; gap: 4px; margin-left: 36px; }
.landing-site .hd-nav-item { position: relative; padding: 8px 14px; font-size: .88rem; font-weight: 500; color: var(--t2); cursor: pointer; white-space: nowrap; transition: color .2s; }
.landing-site .hd-nav-item:hover { color: #fff; }
.landing-site .hd-nav-item:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; border-radius: 6px; }
.landing-site .arrow-d { display: inline-block; width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 4px solid currentColor; margin-left: 4px; vertical-align: middle; }

.landing-site .hd-drop-menu { display: none; position: absolute; top: 100%; left: 0; min-width: 220px; background: rgba(16,18,42,.97); backdrop-filter: blur(16px); border: 1px solid var(--border); border-radius: var(--radius); padding: 8px; box-shadow: 0 12px 40px rgba(0,0,0,.4); z-index: 10; }
.landing-site .hd-drop:hover .hd-drop-menu { display: block; }
.landing-site .hd-drop-menu a { display: block; padding: 10px 14px; border-radius: 8px; font-size: .85rem; color: var(--t2); transition: background .15s, color .15s; cursor: pointer; }
.landing-site .hd-drop-menu a:hover { background: rgba(255,255,255,.06); color: #fff; }
.landing-site .hd-drop-menu a:focus-visible { outline: 2px solid var(--blue); outline-offset: 1px; }
.landing-site .hd-drop-menu a strong { display: block; font-size: .88rem; color: var(--t1); font-weight: 600; }
.landing-site .hd-drop-menu a small { font-size: .78rem; color: var(--t3); }
.landing-site .hd-drop-menu-grid { display: grid; grid-template-columns: 1fr 1fr; min-width: 280px; }

.landing-site .hd-right { display: flex; align-items: center; gap: 10px; margin-left: auto; }
.landing-site .hd-pill {
  display: inline-flex; align-items: center; justify-content: center;
  width: 36px; height: 36px; min-width: 36px;
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1);
  border-radius: 10px; color: var(--t2); cursor: pointer;
  transition: background .2s, color .2s, border-color .2s;
}
.landing-site .hd-pill:hover { background: rgba(255,255,255,.1); color: #fff; }
.landing-site .hd-pill:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }
.landing-site .hd-pill + .hd-pill { width: auto; min-width: 44px; padding: 0 12px; font-size: .8rem; font-weight: 600; }
.landing-site .hd-btn-test { padding: 8px 20px; background: linear-gradient(135deg, var(--blue), var(--blue2)); color: #fff; font-size: .85rem; font-weight: 600; border-radius: 8px; transition: box-shadow .2s, filter .2s; cursor: pointer; }
.landing-site .hd-btn-test:hover { box-shadow: 0 4px 20px var(--blue-glow); filter: brightness(1.08); }
.landing-site .hd-btn-test:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }

.landing-site .hd-burger { display: none; background: none; border: none; width: 24px; height: 18px; flex-direction: column; justify-content: space-between; cursor: pointer; padding: 0; }
.landing-site .hd-burger:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; border-radius: 4px; }
.landing-site .hd-burger span { display: block; height: 2px; background: var(--t2); border-radius: 2px; }

/* ===== Buttons ===== */
.landing-site .btn-main { display: inline-flex; align-items: center; justify-content: center; padding: 12px 28px; background: linear-gradient(135deg, var(--blue), var(--blue2)); color: #fff; font-weight: 600; font-size: .92rem; border-radius: 8px; border: none; cursor: pointer; transition: box-shadow .2s, filter .2s; }
.landing-site .btn-main:hover { box-shadow: 0 6px 28px var(--blue-glow); filter: brightness(1.08); }
.landing-site .btn-main:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }
.landing-site .btn-main.btn-sm { padding: 9px 20px; font-size: .85rem; }
.landing-site .btn-main.btn-lg { padding: 16px 36px; font-size: 1rem; }
.landing-site .btn-outline { display: inline-flex; align-items: center; justify-content: center; padding: 12px 28px; background: transparent; color: var(--t2); border: 1px solid rgba(255,255,255,.2); font-weight: 600; font-size: .92rem; border-radius: 8px; cursor: pointer; transition: color .2s, border-color .2s, background .2s; }
.landing-site .btn-outline:hover { color: #fff; border-color: rgba(255,255,255,.4); background: rgba(255,255,255,.04); }
.landing-site .btn-outline:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }
.landing-site .btn-outline.btn-sm { padding: 9px 20px; font-size: .85rem; }

/* ===== Hero ===== */
.landing-site .hero { position: relative; min-height: 100vh; display: flex; align-items: center; padding: 100px 0 60px; overflow: hidden; }
.landing-site .hero-bg { position: absolute; inset: 0; pointer-events: none; }
.landing-site .hero-glow { position: absolute; border-radius: 50%; filter: blur(100px); opacity: 0.85; }
.landing-site .g1 { width:  min(80vw, 720px); height: min(80vw, 720px); background: radial-gradient(circle, rgba(52,120,246,.28) 0%, rgba(52,120,246,.08) 50%, transparent 70%); top: -25%; left: -15%; }
.landing-site .g2 { width:  min(60vw, 520px); height: min(60vw, 520px); background: radial-gradient(circle, rgba(34,197,94,.12) 0%, rgba(34,197,94,.04) 50%, transparent 70%); bottom: -15%; right: -10%; }
.landing-site .g3 { width:  min(50vw, 400px); height: min(50vw, 400px); background: radial-gradient(circle, rgba(56,189,248,.15) 0%, transparent 60%); top: 40%; right: 10%; }

.landing-site .hero-inner { position: relative; display: grid; grid-template-columns: 1fr 380px; gap: 48px; align-items: center; }
.landing-site .hero-glass {
  background: rgba(255,255,255,.03);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,.08);
  border-radius: 24px;
  padding: 40px 40px 36px;
  max-width: 600px;
  box-shadow: 0 24px 48px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.04);
}
.landing-site .hero-kw { display: flex; gap: 10px; margin-bottom: 24px; }
.landing-site .hero-kw span { padding: 8px 18px; background: rgba(52,120,246,.08); border: 1px solid rgba(52,120,246,.2); border-radius: 999px; font-size: .8rem; font-weight: 700; color: var(--blue); letter-spacing: .02em; }
.landing-site .hero-title { font-family: 'Plus Jakarta Sans', sans-serif; font-size: clamp(1.85rem, 4vw, 2.6rem); font-weight: 800; line-height: 1.25; margin-bottom: 8px; color: #fff; letter-spacing: -0.02em; }
.landing-site .hero-title em { font-style: normal; background: linear-gradient(135deg, #60a5fa, var(--blue)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.landing-site .hero-subtitle { font-size: 1.15rem; font-weight: 600; color: var(--blue); margin-bottom: 20px; letter-spacing: .02em; }
.landing-site .hero-desc { font-size: 1rem; color: var(--t2); line-height: 1.75; margin-bottom: 28px; max-width: 520px; }
.landing-site .hero-btns { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 24px; }
.landing-site .hero-tags { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 20px; }
.landing-site .htag { padding: 8px 16px; background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.12); border-radius: 999px; font-size: .78rem; font-weight: 600; color: var(--t2); transition: border-color .2s, background .2s; }
.landing-site .htag:hover { border-color: rgba(255,255,255,.2); background: rgba(255,255,255,.08); }
.landing-site .htag-blue { background: rgba(52,120,246,.12); border-color: rgba(52,120,246,.3); color: var(--blue); }
.landing-site .htag-blue:hover { border-color: rgba(52,120,246,.45); background: rgba(52,120,246,.18); }
.landing-site .hero-trust { font-size: .88rem; color: var(--t3); }
.landing-site .hero-trust b { color: var(--t1); }

/* Hero 玻璃按钮 */
.landing-site .btn-glass { background: linear-gradient(135deg, rgba(52,120,246,.95), rgba(37,99,235,.95)); box-shadow: 0 4px 24px rgba(52,120,246,.35), inset 0 1px 0 rgba(255,255,255,.2); }
.landing-site .btn-glass:hover { box-shadow: 0 8px 32px rgba(52,120,246,.45), inset 0 1px 0 rgba(255,255,255,.25); }
.landing-site .btn-glass-outline { border-color: rgba(255,255,255,.25); background: rgba(255,255,255,.03); }
.landing-site .btn-glass-outline:hover { border-color: rgba(255,255,255,.4); background: rgba(255,255,255,.06); }

/* 手机模型 */
.landing-site .hero-phone { display: flex; justify-content: center; }
.landing-site .phone-frame { width: 280px; background: linear-gradient(160deg,#1a1d35,#0f1125); border: 2px solid rgba(255,255,255,.1); border-radius: 32px; padding: 12px; position: relative; box-shadow: 0 20px 60px rgba(0,0,0,.4), inset 0 1px 0 rgba(255,255,255,.05); }
.landing-site .phone-notch { width: 100px; height: 24px; background: #0b0d1a; border-radius: 0 0 14px 14px; margin: 0 auto 12px; }
.landing-site .phone-screen { display: flex; flex-direction: column; gap: 10px; padding: 8px; min-height: 340px; }
.landing-site .phone-msg { padding: 10px 14px; border-radius: 14px; font-size: .82rem; line-height: 1.5; max-width: 88%; animation: landingMsgIn .6s ease both; }
.landing-site .phone-msg-in { background: rgba(52,120,246,.15); border: 1px solid rgba(52,120,246,.2); color: var(--t1); align-self: flex-start; }
.landing-site .phone-msg-out { background: rgba(255,255,255,.08); border: 1px solid var(--border); color: var(--t2); align-self: flex-end; }
.landing-site .phone-msg:nth-child(2) { animation-delay: .2s; }
.landing-site .phone-msg:nth-child(3) { animation-delay: .4s; }
.landing-site .phone-msg:nth-child(4) { animation-delay: .6s; }
@keyframes landingMsgIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

/* ===== Section 通用 ===== */
.landing-site .sec { padding: 80px 0; position: relative; }
.landing-site .sec-dark { background: var(--dark2); }
.landing-site .sec-label { text-align: center; font-size: .72rem; font-weight: 700; letter-spacing: .18em; text-transform: uppercase; color: var(--blue); margin-bottom: 12px; opacity: .95; }
.landing-site .sec-title { text-align: center; font-size: 1.9rem; font-weight: 800; margin-bottom: 16px; line-height: 1.25; letter-spacing: -0.02em; }
.landing-site .sec-desc { text-align: center; color: var(--t2); max-width: 620px; margin: 0 auto 40px; line-height: 1.75; font-size: .95rem; }
.landing-site .sec-actions { display: flex; justify-content: center; gap: 14px; margin-bottom: 40px; flex-wrap: wrap; }

/* ===== Solutions ===== */
.landing-site .sol-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 24px; }
.landing-site .sol-card {
  background: rgba(255,255,255,.03);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,.08);
  border-radius: 16px;
  padding: 32px 28px;
  transition: border-color .25s, box-shadow .25s, background .25s;
  box-shadow: 0 4px 24px rgba(0,0,0,.15), inset 0 1px 0 rgba(255,255,255,.03);
}
.landing-site .sol-card:hover { border-color: rgba(52,120,246,.4); box-shadow: 0 12px 40px rgba(0,0,0,.25), 0 0 0 1px rgba(52,120,246,.15); }
.landing-site .sol-card h4 { font-size: 1.08rem; font-weight: 700; margin-bottom: 12px; }
.landing-site .sol-card p { font-size: .88rem; color: var(--t2); line-height: 1.65; margin-bottom: 16px; }
.landing-site .sol-link { font-size: .85rem; font-weight: 600; color: var(--blue); cursor: pointer; transition: color .2s; }
.landing-site .sol-link:hover { text-decoration: underline; color: #60a5fa; }
.landing-site .sol-link:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; border-radius: 4px; }

/* ===== Products ===== */
.landing-site .prod-tabs { display: flex; justify-content: center; gap: 12px; margin-bottom: 40px; flex-wrap: wrap; }
.landing-site .ptab {
  display: flex; align-items: center; gap: 10px; padding: 14px 24px;
  background: rgba(255,255,255,.04); backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,.1); border-radius: 12px;
  color: var(--t2); font-size: .88rem; font-weight: 600; cursor: pointer;
  transition: border-color .25s, color .25s, background .25s;
}
.landing-site .ptab:hover { border-color: rgba(52,120,246,.35); color: #fff; }
.landing-site .ptab.active { background: rgba(52,120,246,.12); border-color: var(--blue); color: #fff; box-shadow: 0 0 0 1px rgba(52,120,246,.2); }
.landing-site .ptab:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }
.landing-site .ptab-icon { display: inline-flex; width: 24px; height: 24px; align-items: center; justify-content: center; flex-shrink: 0; }
.landing-site .ptab-icon .landing-svg-icon { width: 22px; height: 22px; }

.landing-site .prod-body { display: grid; grid-template-columns: 1fr 320px; gap: 40px; align-items: start; }
.landing-site .prod-item { margin-bottom: 24px; }
.landing-site .prod-item h4 { font-size: 1.05rem; font-weight: 600; margin-bottom: 8px; }
.landing-site .prod-item p { font-size: .9rem; color: var(--t2); line-height: 1.7; }
.landing-site .prod-btns { display: flex; gap: 12px; margin-top: 8px; }

.landing-site .prod-visual { position: sticky; top: 100px; }
.landing-site .prod-card-visual {
  background: rgba(255,255,255,.04); backdrop-filter: blur(16px);
  border: 1px solid rgba(255,255,255,.08); border-radius: 20px;
  padding: 28px 24px; display: flex; flex-direction: column; gap: 14px;
  box-shadow: 0 8px 32px rgba(0,0,0,.2), inset 0 1px 0 rgba(255,255,255,.04);
}
.landing-site .pcv-item { display: flex; align-items: center; gap: 12px; padding: 16px 18px; background: rgba(52,120,246,.08); border: 1px solid rgba(52,120,246,.15); border-radius: 12px; font-size: .88rem; font-weight: 500; color: var(--t1); transition: border-color .2s, background .2s; }
.landing-site .pcv-item:hover { border-color: rgba(52,120,246,.25); background: rgba(52,120,246,.12); }
.landing-site .pcv-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--blue); flex-shrink: 0; }

/* ===== Advantages ===== */
.landing-site .adv-grid { display: grid; grid-template-columns: repeat(2,1fr); gap: 24px; }
.landing-site .adv-card {
  background: rgba(255,255,255,.03);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,.08);
  border-radius: 16px;
  padding: 36px 32px;
  transition: border-color .25s, box-shadow .25s;
  box-shadow: 0 4px 24px rgba(0,0,0,.15), inset 0 1px 0 rgba(255,255,255,.03);
}
.landing-site .adv-card:hover { border-color: rgba(52,120,246,.4); box-shadow: 0 12px 40px rgba(0,0,0,.25), 0 0 0 1px rgba(52,120,246,.15); }
.landing-site .adv-icon { display: flex; align-items: center; justify-content: center; width: 52px; height: 52px; margin-bottom: 18px; color: var(--blue); background: rgba(52,120,246,.1); border-radius: 14px; }
.landing-site .adv-icon .landing-svg-icon { width: 28px; height: 28px; }
.landing-site .adv-card h4 { font-size: 1.12rem; font-weight: 700; margin-bottom: 12px; }
.landing-site .adv-card p { font-size: .9rem; color: var(--t2); line-height: 1.7; }

/* ===== Coverage & Pricing ===== */
.landing-site .coverage-nums { display: flex; justify-content: center; gap: 48px; flex-wrap: wrap; margin-bottom: 56px; }
.landing-site .cn {
  text-align: center; padding: 28px 36px;
  background: rgba(255,255,255,.03); backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,.08); border-radius: 16px;
  min-width: 140px; transition: border-color .25s, box-shadow .25s;
  box-shadow: 0 4px 24px rgba(0,0,0,.12), inset 0 1px 0 rgba(255,255,255,.03);
}
.landing-site .cn:hover { border-color: rgba(52,120,246,.3); box-shadow: 0 8px 32px rgba(0,0,0,.2); }
.landing-site .cn-val { display: block; font-size: 2.5rem; font-weight: 800; background: linear-gradient(135deg,#60a5fa,var(--blue)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; letter-spacing: -0.02em; }
.landing-site .cn-label { font-size: .82rem; color: var(--t3); margin-top: 6px; }
.landing-site .price-cards { display: grid; grid-template-columns: repeat(3,1fr); gap: 24px; }
.landing-site .price-card {
  background: rgba(255,255,255,.03);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,.08);
  border-radius: 16px;
  padding: 32px 28px;
  transition: border-color .25s, box-shadow .25s;
  box-shadow: 0 4px 24px rgba(0,0,0,.15), inset 0 1px 0 rgba(255,255,255,.03);
}
.landing-site .price-card:hover { border-color: rgba(52,120,246,.3); box-shadow: 0 8px 32px rgba(0,0,0,.2); }
.landing-site .price-card h4 { font-size: 1.08rem; font-weight: 700; margin-bottom: 12px; }
.landing-site .price-card p { font-size: .88rem; color: var(--t2); line-height: 1.65; }

/* ===== FAQ ===== */
.landing-site .faq-list { max-width: 760px; margin: 0 auto; }
.landing-site .faq-item {
  background: rgba(255,255,255,.02);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,.06);
  border-radius: 12px;
  margin-bottom: 12px;
  overflow: hidden;
  transition: border-color .25s, background .25s;
}
.landing-site .faq-item:hover { border-color: rgba(255,255,255,.1); background: rgba(255,255,255,.03); }
.landing-site .faq-item[open] { border-color: rgba(52,120,246,.25); background: rgba(52,120,246,.04); }
.landing-site .faq-item summary { padding: 20px 24px; font-size: .95rem; font-weight: 600; cursor: pointer; list-style: none; display: flex; align-items: center; justify-content: space-between; color: var(--t1); transition: color .2s; }
.landing-site .faq-item summary:hover { color: #fff; }
.landing-site .faq-item summary:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; border-radius: 8px; }
.landing-site .faq-item summary::after { content: '+'; font-size: 1.2rem; color: var(--t3); transition: color .2s; }
.landing-site .faq-item[open] summary::after { content: '−'; color: var(--blue); }
.landing-site .faq-item p { padding: 0 24px 20px; font-size: .9rem; color: var(--t2); line-height: 1.7; }

/* ===== Flow ===== */
.landing-site .flow-row { display: grid; grid-template-columns: repeat(4,1fr); gap: 24px; margin-bottom: 48px; }
.landing-site .flow-step {
  background: rgba(255,255,255,.03);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,.08);
  border-radius: 16px;
  padding: 32px 24px;
  text-align: center;
  transition: border-color .25s, box-shadow .25s;
  box-shadow: 0 4px 24px rgba(0,0,0,.15), inset 0 1px 0 rgba(255,255,255,.03);
}
.landing-site .flow-step:hover { border-color: rgba(52,120,246,.35); box-shadow: 0 8px 32px rgba(0,0,0,.2); }
.landing-site .flow-badge { display: inline-block; padding: 6px 16px; background: rgba(52,120,246,.15); border: 1px solid rgba(52,120,246,.25); border-radius: 999px; font-size: .7rem; font-weight: 700; color: var(--blue); text-transform: uppercase; letter-spacing: .08em; margin-bottom: 16px; }
.landing-site .flow-step h4 { font-size: 1.08rem; font-weight: 700; margin-bottom: 8px; }
.landing-site .flow-step p { font-size: .82rem; color: var(--t3); line-height: 1.55; }

/* ===== 联系我们 - Telegram 联系卡片 ===== */
.landing-site .sec-contact { padding: 72px 0; }
.landing-site .contact-card {
  max-width: 420px; margin: 0 auto;
  background: rgba(255,255,255,.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,.2);
  border-radius: 24px;
  padding: 48px 40px;
  text-align: center;
  box-shadow: 0 24px 48px rgba(0,0,0,.25), 0 0 0 1px rgba(255,255,255,.1);
}
.landing-site.is-dark .contact-card {
  background: rgba(255,255,255,.06);
  border-color: rgba(255,255,255,.1);
  box-shadow: 0 24px 48px rgba(0,0,0,.4), inset 0 1px 0 rgba(255,255,255,.06);
}
.landing-site .contact-logo { margin-bottom: 24px; }
.landing-site .contact-logo-img {
  width: 140px; height: auto; display: block; margin: 0 auto;
  border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,.2);
}
.landing-site .contact-logo-ring {
  display: inline-flex; flex-direction: column; align-items: center; justify-content: center;
  width: 88px; height: 88px;
  background: linear-gradient(135deg, #4c1d95, #7c3aed);
  border-radius: 50%;
  box-shadow: 0 8px 24px rgba(124,58,237,.4);
}
.landing-site .contact-logo-icon { font-size: .7rem; font-weight: 800; color: rgba(255,255,255,.95); letter-spacing: .05em; }
.landing-site .contact-logo-label { font-size: .55rem; font-weight: 600; color: rgba(255,255,255,.8); letter-spacing: .1em; margin-top: 2px; }
.landing-site .contact-title { font-size: 1.35rem; font-weight: 700; color: var(--t1); margin-bottom: 8px; }
.landing-site.is-dark .contact-title { color: #fff; }
.landing-site .contact-username { font-size: .95rem; color: var(--t3); margin-bottom: 20px; }
.landing-site.is-dark .contact-username { color: rgba(255,255,255,.6); }
.landing-site .contact-desc { font-size: .88rem; color: var(--t2); line-height: 1.6; margin-bottom: 8px; }
.landing-site.is-dark .contact-desc { color: rgba(255,255,255,.75); }
.landing-site .contact-btn {
  display: inline-block; margin-top: 28px; padding: 14px 40px;
  background: #0088cc; color: #fff; font-size: .95rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
  border-radius: 12px; text-decoration: none; transition: background .2s, transform .15s;
}
.landing-site .contact-btn:hover { background: #0099dd; transform: translateY(-1px); }
.landing-site .contact-btn:focus-visible { outline: 2px solid #0088cc; outline-offset: 3px; }

/* ===== Facts ===== */
.landing-site .sec-facts { background: linear-gradient(135deg, rgba(52,120,246,.08), rgba(34,197,94,.04)); padding: 72px 0; }
.landing-site .sec-facts .sec-title { font-size: 1.35rem; font-weight: 700; max-width: 800px; margin-left: auto; margin-right: auto; }
.landing-site .facts-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 24px; margin-top: 48px; }
.landing-site .fact-item {
  background: rgba(255,255,255,.04);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,.08);
  border-radius: 16px;
  padding: 32px 24px;
  text-align: center;
  transition: border-color .25s, box-shadow .25s;
  box-shadow: 0 4px 24px rgba(0,0,0,.1), inset 0 1px 0 rgba(255,255,255,.04);
}
.landing-site .fact-item:hover { border-color: rgba(52,120,246,.3); box-shadow: 0 8px 32px rgba(0,0,0,.15); }
.landing-site .fact-val { display: block; font-size: 2.4rem; font-weight: 800; color: var(--blue); margin-bottom: 8px; letter-spacing: -0.02em; }
.landing-site .fact-lbl { font-size: .85rem; color: var(--t3); line-height: 1.5; }

/* ===== CTA ===== */
.landing-site .sec-cta { padding: 96px 0; background: linear-gradient(180deg, rgba(52,120,246,.1), var(--dark)); position: relative; overflow: hidden; }
.landing-site .sec-cta::before { content: ''; position: absolute; inset: 0; background: radial-gradient(ellipse 80% 50% at 50% 100%, rgba(52,120,246,.12), transparent); pointer-events: none; }
.landing-site .cta-box {
  position: relative;
  text-align: center;
  background: rgba(255,255,255,.03);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,.08);
  border-radius: 24px;
  padding: 56px 48px;
  box-shadow: 0 24px 48px rgba(0,0,0,.2), inset 0 1px 0 rgba(255,255,255,.04);
}
.landing-site .cta-box h2 { font-size: 1.85rem; font-weight: 800; margin-bottom: 32px; line-height: 1.35; letter-spacing: -0.02em; }

/* ===== Footer ===== */
.landing-site .ft { background: var(--dark2); border-top: 1px solid rgba(255,255,255,.06); padding-top: 56px; }
.landing-site .ft-inner { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 48px; padding-bottom: 48px; }
.landing-site .ft-brand .hd-logo-text { font-size: 1.5rem; }
.landing-site .ft-brand p { color: var(--t3); font-size: .88rem; line-height: 1.7; margin-top: 16px; max-width: 360px; }
.landing-site .ft-col { display: flex; flex-direction: column; gap: 12px; }
.landing-site .ft-col h5 { font-size: .9rem; font-weight: 700; margin-bottom: 8px; color: var(--t1); }
.landing-site .ft-col a { color: var(--t3); font-size: .85rem; transition: color .2s; cursor: pointer; }
.landing-site .ft-col a:hover { color: var(--blue); }
.landing-site .ft-col a:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; border-radius: 4px; }
.landing-site .ft-bottom { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; border-top: 1px solid var(--border); padding: 20px 24px; }
.landing-site .ft-bottom p { font-size: .82rem; color: var(--t3); }
.landing-site .ft-links { display: flex; gap: 20px; }
.landing-site .ft-links a { font-size: .82rem; color: var(--t3); cursor: pointer; transition: color .2s; }
.landing-site .ft-links a:hover { color: var(--t2); }
.landing-site .ft-links a:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; border-radius: 4px; }

/* ===== 响应式 ===== */
@media(max-width:1024px) {
  .landing-site .hero-inner { grid-template-columns: 1fr; }
  .landing-site .hero-right { display: none; }
  .landing-site .sol-grid { grid-template-columns: repeat(2,1fr); }
  .landing-site .prod-body { grid-template-columns: 1fr; }
  .landing-site .prod-visual { display: none; }
  .landing-site .adv-grid { grid-template-columns: 1fr; }
  .landing-site .price-cards { grid-template-columns: 1fr; }
  .landing-site .flow-row { grid-template-columns: repeat(2,1fr); }
  .landing-site .contact-card { padding: 36px 28px; }
  .landing-site .facts-grid { grid-template-columns: repeat(2,1fr); }
  .landing-site .ft-inner { grid-template-columns: 1fr; }
  .landing-site .coverage-nums { gap: 20px; }
  .landing-site .cn { min-width: 120px; padding: 20px 24px; }
}
@media(max-width:768px) {
  .landing-site .hd-nav { display: none; position: fixed; top: 68px; left: 0; right: 0; bottom: 0; background: rgba(11,13,26,.98); backdrop-filter: blur(16px); flex-direction: column; padding: 24px; gap: 0; overflow-y: auto; z-index: 200; }
  .landing-site .hd-nav.show { display: flex; }
  .landing-site .hd-nav-item { padding: 14px 0; border-bottom: 1px solid var(--border); }
  .landing-site .hd-drop-menu { position: static; display: block; background: none; border: none; box-shadow: none; padding: 0 0 0 16px; }
  .landing-site .hd-drop-menu-grid { grid-template-columns: 1fr; }
  .landing-site .hd-burger { display: flex; }
  .landing-site .hero-glass { padding: 28px 24px 24px; }
  .landing-site .hero-title { font-size: 1.75rem; }
  .landing-site .hero-subtitle { font-size: 1rem; }
  .landing-site .sol-grid { grid-template-columns: 1fr; }
  .landing-site .flow-row { grid-template-columns: 1fr; }
  .landing-site .contact-card { padding: 32px 24px; max-width: 100%; }
  .landing-site .contact-title { font-size: 1.15rem; }
  .landing-site .facts-grid { grid-template-columns: repeat(2,1fr); }
  .landing-site .coverage-nums { gap: 16px; }
  .landing-site .cn { min-width: 100px; padding: 16px 20px; }
  .landing-site .cn-val { font-size: 2rem; }
  .landing-site .cta-box { padding: 40px 24px; }
  .landing-site .cta-box h2 { font-size: 1.45rem; }
}
</style>
