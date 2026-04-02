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

    <!-- ===== Hero Banner (Portal-Centric) ===== -->
    <section class="hero">
      <div class="hero-bg">
        <div class="hero-glow g1"></div>
        <div class="hero-glow g2"></div>
        <div class="hero-mesh" v-if="!isDark"></div>
      </div>
      <div class="w hero-inner">
        <div class="hero-left animate-fade-left">
          <div class="hero-tag animate-slide-up">{{ $t('landing.hero.subtitle') }}</div>
          <h1 class="hero-title animate-slide-up" style="animation-delay: 0.1s">
            <span class="text-gradient tactile-text">{{ $t('brand.name') }}</span>
            <br />
            <span class="text-secondary">{{ $t('landing.hero.titleHighlight') }}</span>
          </h1>
          <p class="hero-desc animate-slide-up" style="animation-delay: 0.2s">
            {{ $t('landing.hero.desc') }}
            <br /><br />
            <span class="text-tertiary font-sm">{{ $t('landing.hero.portalDesc') || 'Automated SMS & Data Management in one single interface.' }}</span>
          </p>
          <div class="hero-btns animate-slide-up" style="animation-delay: 0.3s">
            <router-link to="/login" class="btn-main-lg soft-button">
              <span>{{ $t('landing.hero.freeTest') }}</span>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" class="mg-l-xs"><path d="M5 12h14m-7-7 7 7-7 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </router-link>
            <a href="#solutions" class="btn-glass soft-button">{{ $t('landing.hero.explore') || 'Explore Solutions' }}</a>
          </div>
          
          <div class="hero-stats-mini animate-slide-up" style="animation-delay: 0.4s">
            <div class="hstat-mini">
              <strong>99.9%</strong>
              <span>{{ $t('landing.hero.stats.uptime') }}</span>
            </div>
            <div class="hstat-divider"></div>
            <div class="hstat-mini">
              <strong>1ms</strong>
              <span>{{ $t('landing.hero.stats.latency') }}</span>
            </div>
          </div>
        </div>
        
        <div class="hero-right animate-fade-right">
          <div class="portal-preview-wrapper portal-card">
            <div class="portal-header">
              <div class="portal-dots"><span></span><span></span><span></span></div>
              <div class="portal-title">Rates Explorer</div>
            </div>
            <RateSearch />
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 信任指标（Stripe 风格大数字） ===== -->
    <section class="sec sec-stats">
      <div class="w stats-wrapper">
        <p class="stats-trusted">{{ $t('landing.trustedBy') }}</p>
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-val">190+</span>
            <span class="stat-label">{{ $t('landing.coverageLabels.countries') }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-val">800+</span>
            <span class="stat-label">{{ $t('landing.coverageLabels.operators') }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-val">95%+</span>
            <span class="stat-label">{{ $t('landing.coverageLabels.delivery') }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-val">&lt;3min</span>
            <span class="stat-label">{{ $t('landing.coverageLabels.viewTime') }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== Industry Solutions (illyvoip style) ===== -->
    <section id="solutions" class="sec sec-solutions">
      <div class="w">
        <div class="sec-header animate-slide-up">
          <p class="sec-tag">{{ $t('landing.sections.solutions') }}</p>
          <h2 class="sec-title">{{ $t('landing.sections.solutionsTitle') || 'Tailored Solutions for Industry Leaders' }}</h2>
          <p class="sec-desc">{{ $t('landing.solutionsDesc') }}</p>
        </div>
        
        <div class="industry-grid">
          <div class="industry-card soft-card soft-card-hover animate-scale" style="animation-delay: 0.1s">
            <div class="industry-icon"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg></div>
            <h3>{{ $t('landing.industries.finance.title') }}</h3>
            <p>{{ $t('landing.industries.finance.desc') }}</p>
            <ul class="industry-list">
              <li v-for="f in $tm('landing.industries.finance.features')" :key="f"><span class="dot"></span> {{ f }}</li>
            </ul>
          </div>
          
          <div class="industry-card soft-card soft-card-hover animate-scale" style="animation-delay: 0.2s">
            <div class="industry-icon"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4H6zM3 6h18M16 10a4 4 0 0 1-8 0"/></svg></div>
            <h3>{{ $t('landing.industries.retail.title') }}</h3>
            <p>{{ $t('landing.industries.retail.desc') }}</p>
            <ul class="industry-list">
              <li v-for="f in $tm('landing.industries.retail.features')" :key="f"><span class="dot"></span> {{ f }}</li>
            </ul>
          </div>
          
          <div class="industry-card soft-card soft-card-hover animate-scale" style="animation-delay: 0.3s">
            <div class="industry-icon"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M1 3h15v13H1zM16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg></div>
            <h3>{{ $t('landing.industries.logistics.title') }}</h3>
            <p>{{ $t('landing.industries.logistics.desc') }}</p>
            <ul class="industry-list">
              <li v-for="f in $tm('landing.industries.logistics.features')" :key="f"><span class="dot"></span> {{ f }}</li>
            </ul>
          </div>
        </div>

        <div class="sec-footer-actions animate-slide-up">
          <router-link to="/login" class="btn-main-lg soft-button">
            <span>{{ $t('landing.ctaOpenAccount') }}</span>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M13 7l5 5m0 0l-5 5m5-5H6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </router-link>
          <a href="#contact" class="btn-glass soft-button">{{ $t('landing.ctaOnlineConsult') }}</a>
        </div>
      </div>
    </section>

    <!-- ===== DID / Virtual Number Showcase (illyvoip style) ===== -->
    <section id="numbers" class="sec sec-did">
      <div class="did-bg-image">
        <img src="/global_comm.png" alt="Global Communication" />
      </div>
      <div class="w">
        <div class="sec-header animate-slide-up">
          <p class="sec-tag">{{ $t('landing.sections.did') || 'VIRTUAL NUMBERS' }}</p>
          <h2 class="sec-title">{{ $t('landing.sections.didTitle') || 'Establish Your Presence Worldwide' }}</h2>
        </div>
        <DIDShowcase />
      </div>
    </section>

    <!-- ===== SMS 产品 ===== -->
    <section id="products" class="sec sec-dark-gradient">
      <div class="w">
        <div class="sec-header animate-slide-up">
          <p class="sec-tag">{{ $t('landing.sections.products') }}</p>
          <h2 class="sec-title">{{ $t('landing.sections.productsTitle') }}</h2>
          <p class="sec-desc">{{ $t('landing.productsDesc') }}</p>
        </div>

        <div class="prod-container animate-slide-up">
          <div class="prod-tabs-modern">
            <button v-for="(p,i) in products" :key="i" :class="['ptab-modern', {active: prodIdx===i}]" @click="prodIdx=i" type="button">
              <span class="ptab-icon"><component :is="p.icon" /></span>
              <span class="ptab-text">{{ p.label }}</span>
            </button>
          </div>
          
          <div class="prod-content-modern glass-card">
            <div class="prod-info-modern">
              <div class="prod-item-modern" v-for="(item,j) in products[prodIdx].items" :key="j">
                <div class="prod-item-header">
                  <span class="prod-item-dot"></span>
                  <h4>{{ item.title }}</h4>
                </div>
                <p>{{ item.desc }}</p>
              </div>
              <div class="prod-btns-modern">
                <router-link to="/login" class="btn-main-lg">{{ $t('landing.ctaTryNow') }}</router-link>
                <a href="#pricing" class="btn-glass">{{ $t('landing.ctaLearnMore') }}</a>
              </div>
            </div>
            <div class="prod-visual-modern">
              <div class="visual-mockup">
                <div class="mockup-header">
                  <span class="dot-r"></span><span class="dot-y"></span><span class="dot-g"></span>
                  <div class="mockup-url">api.kaolach.com/v1/sms/send</div>
                </div>
                <div class="mockup-body">
                  <pre><code>{
  "to": "+1234567890",
  "message": "Hello from Kaolach!",
  "type": "marketing"
}</code></pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 优势 ===== -->
    <section id="advantages" class="sec">
      <div class="w">
        <div class="sec-header animate-slide-up">
          <p class="sec-tag">{{ $t('landing.sections.advantages') }}</p>
          <h2 class="sec-title">{{ $t('landing.sections.advantagesTitle') }}</h2>
          <p class="sec-desc">{{ $t('landing.advantagesDesc') }}</p>
        </div>
        <div class="adv-grid">
          <div class="adv-card soft-card soft-card-hover animate-slide-up" v-for="(a, index) in advantages" :key="a.title" :style="{ animationDelay: (index * 0.1) + 's' }">
            <div class="adv-icon-wrapper">
              <component :is="a.icon" />
            </div>
            <h4>{{ a.title }}</h4>
            <p>{{ a.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 覆盖范围 & 定价 ===== -->
    <section id="pricing" class="sec sec-dark-gradient">
      <div class="w">
        <div class="sec-header animate-slide-up">
          <p class="sec-tag">{{ $t('landing.sections.pricingLabel') }}</p>
          <h2 class="sec-title">{{ $t('landing.sections.pricingTitle') }}</h2>
          <p class="sec-desc">{{ $t('landing.pricingDesc') }}</p>
        </div>
        
        <div class="pricing-stats animate-slide-up">
          <div class="pstat-item"><span class="pstat-val">190+</span><span class="pstat-lbl">{{ $t('landing.coverageLabels.countries') }}</span></div>
          <div class="pstat-item"><span class="pstat-val">800+</span><span class="pstat-lbl">{{ $t('landing.coverageLabels.operators') }}</span></div>
          <div class="pstat-item"><span class="pstat-val">95%+</span><span class="pstat-lbl">{{ $t('landing.coverageLabels.delivery') }}</span></div>
          <div class="pstat-item"><span class="pstat-val">3min</span><span class="pstat-lbl">{{ $t('landing.coverageLabels.viewTime') }}</span></div>
        </div>

        <div class="price-cards-modern animate-slide-up">
          <div class="price-card-glass soft-card soft-card-hover" v-for="p in priceFeatures" :key="p.title">
            <div class="pcard-header">
              <div class="pcard-dot"></div>
              <h4>{{ p.title }}</h4>
            </div>
            <p>{{ p.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== FAQ ===== -->
    <section id="faq" class="sec">
      <div class="w">
        <div class="sec-header animate-slide-up">
          <p class="sec-tag">{{ $t('landing.sections.faq') }}</p>
          <h2 class="sec-title">{{ $t('landing.sections.faqTitle') }}</h2>
          <p class="sec-desc">{{ $t('landing.faqDesc') }}</p>
        </div>
        
        <div class="faq-list-modern animate-slide-up">
          <details class="faq-item-modern glass-card" v-for="f in faqs" :key="f.q">
            <summary>
              <span>{{ f.q }}</span>
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" class="faq-arrow">
                <path d="M6 8L10 12L14 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </summary>
            <div class="faq-ans">
              <p>{{ f.a }}</p>
            </div>
          </details>
        </div>
      </div>
    </section>

    <!-- ===== 联系我们 ===== -->
    <section id="contact" class="sec sec-dark-gradient">
      <div class="w">
        <div class="sec-header animate-slide-up">
          <p class="sec-tag">{{ $t('landing.nav.contact') }}</p>
          <h2 class="sec-title">{{ $t('landing.contact.sectionTitle') }}</h2>
        </div>
        
        <div class="contact-grid-modern animate-slide-up">
          <!-- Official Bot -->
          <div class="contact-card-modern glass-card">
            <div class="contact-icon-box bot">
              <img src="/logo.svg" alt="Kaolach" />
            </div>
            <h3>{{ $t('landing.contact.title') }}</h3>
            <p class="contact-handle">@kaolachbot</p>
            <div class="contact-features">
              <span>{{ $t('landing.contact.line1') }}</span>
              <span>{{ $t('landing.contact.line2') }}</span>
              <span>{{ $t('landing.contact.line3') }}</span>
            </div>
            <a href="https://t.me/kaolachbot" target="_blank" class="btn-main-lg w-full">
              {{ $t('landing.contact.sendMessage') }}
            </a>
          </div>

          <!-- Business Manager -->
          <div class="contact-card-modern glass-card">
            <div class="contact-icon-box manager">
              <img src="/wechat-qr-business.png" alt="Manager" />
            </div>
            <h3>{{ $t('landing.contact.businessManagerTitle') }}</h3>
            <p class="contact-handle">TG @jack9967</p>
            <div class="contact-features">
              <span>{{ $t('landing.contact.businessManagerWx') }}: JackSMS</span>
              <span>{{ $t('landing.contact.businessManagerDesc') }}</span>
            </div>
            <a href="https://t.me/jack9967" target="_blank" class="btn-glass w-full">
              {{ $t('landing.contact.sendMessage') }}
            </a>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== CTA ===== -->
    <section class="sec sec-cta-modern">
      <div class="w">
        <div class="cta-banner glass-card animate-slide-up">
          <div class="cta-content">
            <h2>{{ $t('landing.ctaTitle') }}</h2>
            <p>{{ $t('landing.ctaSub') }}</p>
            <div class="cta-actions">
              <router-link to="/login" class="btn-main-lg">{{ $t('landing.cta') }}</router-link>
              <a href="#contact" class="btn-glass">{{ $t('landing.ctaContact') }}</a>
            </div>
          </div>
          <div class="cta-visual">
            <div class="visual-orb"></div>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== Footer ===== -->
    <footer class="footer-modern">
      <div class="w footer-inner">
        <div class="footer-brand">
          <div class="f-logo">Kao<span>lach</span></div>
          <p>{{ $t('landing.footerDesc') }}</p>
        </div>
        
        <div class="footer-links-grid">
          <div class="f-col">
            <h5>{{ $t('landing.footerProducts') }}</h5>
            <a href="#products">{{ $t('landing.nav.intlSms') }}</a>
            <a href="#products">{{ $t('landing.nav.verifySms') }}</a>
            <a href="#pricing">{{ $t('landing.nav.pricing') }}</a>
          </div>
          <div class="f-col">
            <h5>{{ $t('landing.footerAbout') }}</h5>
            <a href="#contact">{{ $t('landing.footerContact') }}</a>
            <a href="#about">{{ $t('landing.footerAboutUs') }}</a>
          </div>
        </div>
      </div>
      <div class="w footer-bottom">
        <p>© {{ new Date().getFullYear() }} {{ $t('brand.name') }}. All Rights Reserved.</p>
        <div class="f-bottom-links">
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
import RateSearch from '@/components/landing/RateSearch.vue'
import DIDShowcase from '@/components/landing/DIDShowcase.vue'

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
  const savedTheme = localStorage.getItem('theme') || 'light'
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
   考拉出海 Landing — 现代化 B2B SaaS 风格（参考 Twilio / Stripe / MessageBird）
   ============================================================ */
.landing-site {
  --primary: #2563eb;
  --primary-hover: #1d4ed8;
  --primary-muted: rgba(37,99,235,.08);
  --dark: #0f172a;
  --dark-muted: #475569;
  --dark-subtle: #64748b;
  --bg: #fafbfc;
  --bg-alt: #f1f5f9;
  --card: #ffffff;
  --border: rgba(15,23,42,.08);
  --border-hover: rgba(37,99,235,.2);
  --t1: #0f172a;
  --t2: #475569;
  --t3: #64748b;
  --radius: 12px;
  --radius-lg: 16px;
  --shadow-sm: 0 1px 2px rgba(15,23,42,.04);
  --shadow-md: 0 4px 12px rgba(15,23,42,.06);
  --shadow-lg: 0 12px 40px rgba(15,23,42,.08);
  --gradient-primary: linear-gradient(135deg, #3B82F6 0%, #2DD4BF 100%);
  --ease-out: cubic-bezier(0.25, 0.46, 0.45, 0.94);
  --ease-default: cubic-bezier(0.4, 0, 0.2, 1);
  --duration-normal: 0.3s;
  background: var(--bg);
  color: var(--t1);
  font-family: 'Inter', 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  -webkit-font-smoothing: antialiased;
  scroll-behavior: smooth;
  overflow-x: hidden;
  min-height: 100vh;
  scroll-behavior: smooth !important;
}
/* 浅色模式（默认 B2B SaaS 风格） */
.landing-site.is-light {
  --bg: #f8fafc;
  --bg-alt: #f1f5f9;
  --card: #ffffff;
  --border: rgba(15,23,42,.08);
  --t1: #0f172a;
  --t2: #475569;
  --t3: #64748b;
  background: var(--bg);
  color: var(--t1);
}
.landing-site.is-light .hero { background: linear-gradient(180deg, #f0f7ff 0%, #f8fafc 50%); }
/* 深色模式覆盖 */
.landing-site.is-dark {
  --bg: #0b0d17;
  --bg-alt: #10122a;
  --card: rgba(255,255,255,.04);
  --border: rgba(255,255,255,.08);
  --t1: #f1f5f9;
  --t2: rgba(241,245,249,.8);
  --t3: rgba(241,245,249,.6);
  background: var(--bg);
  color: var(--t1);
}
.landing-site.is-light .hd.fixed { background: rgba(255,255,255,.92); backdrop-filter: blur(12px); border-color: var(--border); box-shadow: var(--shadow-sm); }
.landing-site.is-dark .hd.fixed { background: rgba(11,13,23,.95); backdrop-filter: blur(16px); border-color: rgba(255,255,255,.08); }
.landing-site.is-dark .hd-logo-text { color: #fff; }
.landing-site.is-dark .hd-logo-text em { color: #60a5fa; }
.landing-site.is-dark .hd-nav-item { color: var(--t2); }
.landing-site.is-dark .hd-nav-item:hover { color: #fff; }
.landing-site.is-light .hd-logo-text { color: var(--t1); }
.landing-site.is-light .hd-logo-text em { color: var(--primary); }
.landing-site.is-light .hd-nav-item { color: var(--t2); }
.landing-site.is-light .hd-nav-item:hover { color: var(--t1); }
.landing-site.is-light .hd-pill { background: rgba(0,0,0,.06); border-color: rgba(0,0,0,.1); color: var(--t2); }
.landing-site.is-light .hd-pill:hover { background: rgba(0,0,0,.1); color: var(--t1); }
.landing-site.is-light .hero-title { color: var(--t1); }
.landing-site.is-light .sec-dark { background: var(--bg-alt); }
.landing-site.is-dark .sec-dark { background: rgba(16,18,42,.6); }
.landing-site.is-dark .sec-stats { background: rgba(16,18,42,.5); border-color: rgba(255,255,255,.06); }
.landing-site.is-dark .stat-val { color: #60a5fa; }
.landing-site.is-light .hero-glow { opacity: 0.4; }
.landing-site.is-light .g1 { background: radial-gradient(circle, rgba(52,120,246,.1) 0%, rgba(52,120,246,.02) 50%, transparent 70%); }
.landing-site.is-light .g2 { background: radial-gradient(circle, rgba(34,197,94,.08) 0%, rgba(34,197,94,.02) 50%, transparent 70%); opacity: 0.6; }

/* 明亮模式：下拉菜单、按钮、卡片等 */
.landing-site.is-light .hd-drop-menu { background: rgba(255,255,255,.96); border-color: rgba(0,0,0,.08); box-shadow: 0 12px 40px rgba(0,0,0,.12); }
.landing-site.is-light .hd-drop-menu a { color: var(--t2); }
.landing-site.is-light .hd-drop-menu a:hover { background: rgba(0,0,0,.04); color: var(--t1); }
.landing-site.is-light .hd-drop-menu a strong { color: var(--t1); }
.landing-site.is-light .hd-drop-menu a small { color: var(--t3); }

.landing-site.is-light .btn-outline { border-color: rgba(0,0,0,.15); color: var(--t2); }
.landing-site.is-light .btn-outline:hover { border-color: rgba(0,0,0,.25); color: var(--t1); background: rgba(0,0,0,.04); }


.landing-site.is-light .phone-frame { 
  background: linear-gradient(160deg,#ffffff,#e8eaf0); 
  border: 2px solid rgba(0,0,0,.08); 
  box-shadow: 0 25px 50px -12px rgba(37,99,235,.2), 0 0 0 1px rgba(0,0,0,.04);
}
.landing-site.is-light .phone-notch { background: #e8eaf0; }
.landing-site.is-light .phone-msg-in { background: rgba(52,120,246,.12); border-color: rgba(52,120,246,.2); color: var(--t1); }
.landing-site.is-light .phone-msg-out { background: rgba(0,0,0,.06); border-color: rgba(0,0,0,.1); color: var(--t2); }

.landing-site.is-light .contact-title { color: #1d1d1f; }
.landing-site.is-light .contact-username { color: #6e6e73; }
.landing-site.is-light .contact-desc { color: #424245; }

.landing-site.is-light .ft-col h5 { color: var(--t1); }
@keyframes heroFadeIn { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
.landing-site .hero-animate { animation: heroFadeIn .7s ease-out both; }
.landing-site .hero-right.hero-animate { animation-delay: .15s; }
@media (prefers-reduced-motion: reduce) {
  .landing-site { scroll-behavior: auto; }
  .landing-site .hero-animate { animation: none; }
  .landing-site .hd, .landing-site .sol-card, .landing-site .adv-card, .landing-site .ptab,
  .landing-site .btn-main, .landing-site .btn-outline, .landing-site .hd-nav-item,
  .landing-site .hd-drop-menu a, .landing-site .faq-item summary,
  .landing-site .price-card, .landing-site .flow-step, .landing-site .fact-item, .landing-site .cn { transition: none; }
  .landing-site .phone-float { animation: none; }
}
.landing-site *, .landing-site *::before, .landing-site *::after { box-sizing: border-box; margin: 0; padding: 0; }
.landing-site .w { max-width: 1200px; margin: 0 auto; padding: 0 24px; }
.landing-site [id] { scroll-margin-top: 80px; }
.landing-site a { color: inherit; text-decoration: none; }

/* ===== Header ===== */
.landing-site .hd { position: fixed; top: 0; left: 0; right: 0; z-index: 300; transition: background .3s, border-color .3s, box-shadow .3s; background: transparent; }
.landing-site .hd.fixed { border-bottom: 1px solid var(--border); }
.landing-site .hd:not(.fixed) { border-bottom-color: transparent; }
.landing-site .hd-inner { display: flex; align-items: center; height: 68px; }
.landing-site .hd-logo { display: flex; align-items: center; gap: 8px; flex-shrink: 0; cursor: pointer; }
.landing-site .hd-logo-icon { flex-shrink: 0; border-radius: 6px; }
.landing-site .hd-logo:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; border-radius: 6px; }
.landing-site .hd-logo-text { font-size: 1.35rem; font-weight: 700; color: var(--t1); letter-spacing: -.02em; }
.landing-site .hd-logo-text em { font-style: normal; color: var(--primary); }

.landing-site .hd-nav { display: flex; align-items: center; gap: 4px; margin-left: 36px; }
.landing-site .hd-nav-item { position: relative; padding: 8px 14px; font-size: .88rem; font-weight: 500; color: var(--t2); cursor: pointer; white-space: nowrap; transition: color .2s; }
.landing-site .hd-nav-item:hover { color: var(--t1); }
.landing-site .hd-nav-item:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; border-radius: 6px; }
.landing-site .arrow-d { display: inline-block; width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 4px solid currentColor; margin-left: 4px; vertical-align: middle; }

.landing-site .hd-drop-menu { display: none; position: absolute; top: 100%; left: 0; min-width: 220px; background: rgba(16,18,42,.97); backdrop-filter: blur(16px); border: 1px solid var(--border); border-radius: var(--radius); padding: 8px; box-shadow: 0 12px 40px rgba(0,0,0,.4); z-index: 10; }
.landing-site .hd-drop:hover .hd-drop-menu { display: block; }
.landing-site .hd-drop-menu a { display: block; padding: 10px 14px; border-radius: 8px; font-size: .85rem; color: var(--t2); transition: background .15s, color .15s; cursor: pointer; }
.landing-site .hd-drop-menu a:hover { background: rgba(255,255,255,.06); color: #fff; }
.landing-site .hd-drop-menu a:focus-visible { outline: 2px solid var(--primary); outline-offset: 1px; }
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
.landing-site .hd-pill:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.landing-site .hd-pill + .hd-pill { width: auto; min-width: 44px; padding: 0 12px; font-size: .8rem; font-weight: 600; }
.landing-site .hd-btn-test { padding: 10px 22px; background: var(--primary); color: #fff; font-size: .9rem; font-weight: 600; border-radius: 8px; transition: background .2s; cursor: pointer; }
.landing-site .hd-btn-test:hover { background: var(--primary-hover); }
.landing-site .hd-btn-test:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }

.landing-site .hd-burger { display: none; background: none; border: none; width: 24px; height: 18px; flex-direction: column; justify-content: space-between; cursor: pointer; padding: 0; }
.landing-site .hd-burger:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; border-radius: 4px; }
.landing-site .hd-burger span { display: block; height: 2px; background: var(--t2); border-radius: 2px; }

/* ===== Buttons ===== */
.landing-site .btn-main-lg {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 16px 36px;
  background: var(--gradient-primary);
  color: #fff;
  font-weight: 700;
  font-size: 1.1rem;
  border-radius: var(--radius-lg);
  border: none;
  cursor: pointer;
  transition: all var(--duration-normal) var(--ease-default);
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.4);
}

.landing-site .btn-main-lg:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px rgba(59, 130, 246, 0.5);
  filter: brightness(1.1);
}

.landing-site .btn-glass {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 16px 36px;
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  color: var(--t1);
  border: 1px solid rgba(255, 255, 255, 0.1);
  font-weight: 600;
  font-size: 1.1rem;
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--duration-normal) var(--ease-default);
}

.landing-site .btn-glass:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
  transform: translateY(-2px);
}

/* ===== Hero（Modernized） ===== */
.landing-site .hero {
  position: relative;
  min-height: 90vh;
  display: flex;
  align-items: center;
  padding: 140px 0 100px;
  overflow: hidden;
}

.landing-site .hero-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
  z-index: 0;
}

.landing-site .hero-mesh {
  position: absolute;
  inset: 0;
  background: 
    radial-gradient(ellipse 100% 80% at 50% -30%, rgba(59, 130, 246, 0.15) 0%, transparent 70%),
    radial-gradient(ellipse 60% 40% at 100% 60%, rgba(45, 212, 191, 0.1) 0%, transparent 60%);
}

.landing-site .hero-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(120px);
  opacity: 0.6;
}

.landing-site .g1 {
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.2) 0%, transparent 70%);
  top: -100px;
  left: -100px;
}

.landing-site .g2 {
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, rgba(45, 212, 191, 0.15) 0%, transparent 70%);
  bottom: -50px;
  right: -50px;
}

.landing-site .hero-inner {
  position: relative;
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 80px;
  align-items: center;
  z-index: 1;
}

.landing-site .hero-tag {
  display: inline-block;
  padding: 6px 14px;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.2);
  color: var(--primary);
  font-size: 0.875rem;
  font-weight: 600;
  border-radius: 100px;
  margin-bottom: 24px;
  letter-spacing: 0.02em;
}

.landing-site .hero-title {
  font-size: clamp(2.5rem, 5vw, 4.5rem);
  line-height: 1.1;
  font-weight: 800;
  margin-bottom: 24px;
  letter-spacing: -0.03em;
  color: var(--t1);
}

.landing-site .hero-desc {
  font-size: 1.25rem;
  color: var(--t2);
  max-width: 540px;
  margin-bottom: 40px;
  line-height: 1.6;
}

.landing-site .hero-btns {
  display: flex;
  gap: 20px;
  margin-bottom: 48px;
}

.landing-site .hero-trust-mini {
  display: flex;
  align-items: center;
  gap: 16px;
  color: var(--t3);
  font-size: 0.9375rem;
}

.landing-site .trust-avatars {
  display: flex;
  align-items: center;
}

.landing-site .trust-avatars img {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 2px solid var(--bg);
  margin-left: -12px;
}

.landing-site .trust-avatars img:first-child {
  margin-left: 0;
}

/* Animations */
.animate-slide-up {
  opacity: 0;
  transform: translateY(20px);
  animation: slideUp 0.6s var(--ease-out) forwards;
}

/* New Hero Styles (illyvoip style) */
.hero-stats-mini {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-top: 48px;
}
.hstat-mini {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.hstat-mini strong { font-size: 1.5rem; font-weight: 800; color: var(--primary); letter-spacing: -0.02em; }
.hstat-mini span { font-size: 0.8rem; color: var(--t3); font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; }
.hstat-divider { width: 1px; height: 32px; background: rgba(255,255,255,0.1); }

.portal-preview-wrapper {
  padding: 1px;
  overflow: hidden;
  transition: all 0.5s var(--ease-default);
}
.portal-header {
  padding: 12px 20px;
  background: rgba(255,255,255,0.03);
  border-bottom: 1px solid rgba(255,255,255,0.05);
  display: flex;
  align-items: center;
  gap: 16px;
}
.portal-dots { display: flex; gap: 6px; }
.portal-dots span { width: 8px; height: 8px; border-radius: 50%; background: rgba(255,255,255,0.1); }
.portal-dots span:nth-child(1) { background: #ff5f56; }
.portal-dots span:nth-child(2) { background: #ffbd2e; }
.portal-dots span:nth-child(3) { background: #27c93f; }
.portal-title { font-size: 0.75rem; font-weight: 600; color: var(--t3); text-transform: uppercase; letter-spacing: 0.05em; }

/* Industry Grid Styles (illyvoip style) */
.sec-solutions { background: linear-gradient(to bottom, transparent, rgba(59, 130, 246, 0.03)); }
.industry-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 32px;
  margin-top: 60px;
}
.industry-card {
  padding: 40px 32px;
  display: flex;
  flex-direction: column;
  height: 100%;
}
.industry-icon {
  width: 64px;
  height: 64px;
  background: var(--bg-primary);
  box-shadow: var(--shadow-soft-in);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary);
  margin-bottom: 24px;
}
.industry-card h3 { font-size: 1.5rem; font-weight: 700; color: #fff; margin-bottom: 16px; }
.industry-card p { font-size: 0.95rem; color: var(--t2); line-height: 1.6; margin-bottom: 24px; flex-grow: 1; }

.industry-list {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border-top: 1px solid rgba(255,255,255,0.05);
  padding-top: 24px;
}
.industry-list li {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--t3);
}
.industry-list .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
  box-shadow: 0 0 10px var(--primary);
}

/* DID Showcase Styles (illyvoip style) */
.sec-did {
  position: relative;
  overflow: hidden;
  background: #05070a;
  padding: 120px 0;
}
.did-bg-image {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 100%;
  height: 100%;
  opacity: 0.15;
  filter: blur(2px) grayscale(100%) contrast(1.5);
  pointer-events: none;
}
.did-bg-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.sec-did .w {
  position: relative;
  z-index: 2;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(30px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes fadeInLeft {
  from { opacity: 0; transform: translateX(-40px); }
  to { opacity: 1; transform: translateX(0); }
}
@keyframes fadeInRight {
  from { opacity: 0; transform: translateX(40px); }
  to { opacity: 1; transform: translateX(0); }
}
@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.9); }
  to { opacity: 1; transform: scale(1); }
}

.animate-fade-left { opacity: 0; animation: fadeInLeft 0.8s var(--ease-soft) forwards; }
.animate-fade-right { opacity: 0; animation: fadeInRight 0.8s var(--ease-soft) forwards; }
.animate-scale { opacity: 0; animation: scaleIn 0.8s var(--ease-soft) forwards; }
.landing-site .hero-title em { font-style: normal; background: var(--gradient-primary); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.landing-site .hero-desc { font-size: 1.25rem; color: var(--t2); max-width: 540px; margin-bottom: 40px; line-height: 1.6; }
/* ===== Section Universal ===== */
.landing-site .sec { padding: 120px 0; position: relative; }
.landing-site .sec-dark-gradient { 
  background: radial-gradient(circle at 100% 100%, rgba(59, 130, 246, 0.03) 0%, transparent 40%),
              radial-gradient(circle at 0% 0%, rgba(45, 212, 191, 0.03) 0%, transparent 40%);
}

.landing-site .sec-header { text-align: center; margin-bottom: 80px; }
.landing-site .sec-tag {
  display: inline-block; padding: 6px 14px; background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.2);
  color: var(--primary); font-size: 0.8125rem; font-weight: 700; border-radius: 100px; margin-bottom: 20px; letter-spacing: 0.05em; text-transform: uppercase;
}
.landing-site .sec-title { font-size: 2.75rem; font-weight: 800; margin-bottom: 20px; letter-spacing: -0.03em; color: var(--t1); }
.landing-site .sec-desc { font-size: 1.125rem; color: var(--t2); max-width: 640px; margin: 0 auto; line-height: 1.6; }

/* ===== Solutions ===== */
.landing-site .sol-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 32px; }
.landing-site .sol-card { padding: 40px; }
.landing-site .sol-icon-wrapper { width: 44px; height: 12px; margin-bottom: 24px; position: relative; }
.landing-site .sol-dot { display: block; width: 12px; height: 12px; border-radius: 50%; background: var(--gradient-primary); box-shadow: 0 0 12px var(--primary); }
.landing-site .sol-card h4 { font-size: 1.25rem; font-weight: 700; margin-bottom: 16px; color: var(--t1); }
.landing-site .sol-card p { font-size: 1rem; color: var(--t2); line-height: 1.6; margin-bottom: 24px; }
.landing-site .sol-link { display: inline-flex; align-items: center; gap: 8px; color: var(--primary); font-weight: 600; text-decoration: none; transition: gap 0.3s; }
.landing-site .sol-link:hover { gap: 12px; }

/* ===== Products ===== */
.landing-site .prod-container { max-width: 1100px; margin: 0 auto; }
.landing-site .prod-tabs-modern { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 40px; }
.landing-site .ptab-modern {
  display: flex; align-items: center; justify-content: center; gap: 12px; padding: 20px;
  background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: var(--radius-lg);
  color: var(--t2); font-weight: 600; cursor: pointer; transition: all 0.3s;
}
.landing-site .ptab-modern.active { background: rgba(59, 130, 246, 0.1); border-color: var(--primary); color: var(--primary); }
.landing-site .prod-content-modern { display: grid; grid-template-columns: 1.2fr 1fr; gap: 60px; padding: 60px; align-items: center; }
.landing-site .prod-item-modern { margin-bottom: 32px; }
.landing-site .prod-item-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.landing-site .prod-item-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--primary); }
.landing-site .prod-item-modern h4 { font-size: 1.125rem; font-weight: 700; color: var(--t1); }
.landing-site .prod-item-modern p { color: var(--t2); line-height: 1.6; font-size: 0.9375rem; }
.landing-site .prod-btns-modern { display: flex; gap: 20px; margin-top: 40px; }

.landing-site .visual-mockup {
  background: #0f111a; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.1); overflow: hidden;
  box-shadow: 0 30px 60px rgba(0,0,0,0.3);
}
.landing-site .mockup-header { padding: 12px 16px; background: rgba(255, 255, 255, 0.03); display: flex; align-items: center; gap: 6px; border-bottom: 1px solid rgba(255, 255, 255, 0.1); }
.landing-site .dot-r { width: 8px; height: 8px; border-radius: 50%; background: #ff5f56; }
.landing-site .dot-y { width: 8px; height: 8px; border-radius: 50%; background: #ffbd2e; }
.landing-site .dot-g { width: 8px; height: 8px; border-radius: 50%; background: #27c93f; }
.landing-site .mockup-url { font-family: monospace; font-size: 11px; color: var(--t3); margin-left: 10px; background: rgba(255, 255, 255, 0.05); padding: 2px 10px; border-radius: 4px; }
.landing-site .mockup-body { padding: 20px; }
.landing-site .mockup-body pre { margin: 0; color: #a5b4fc; font-size: 13px; font-family: 'Fira Code', 'Roboto Mono', monospace; }

/* ===== Advantages & Pricing ===== */
.landing-site .adv-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px; }
.landing-site .adv-card { padding: 40px 32px; }
.landing-site .adv-icon-wrapper { width: 44px; height: 44px; border-radius: 12px; background: rgba(59, 130, 246, 0.1); display: flex; align-items: center; justify-content: center; color: var(--primary); margin-bottom: 24px; }
.landing-site .adv-icon-wrapper :deep(svg) { width: 24px; height: 24px; }
.landing-site .pricing-stats { display: flex; justify-content: center; gap: 80px; margin-bottom: 80px; flex-wrap: wrap; }
.landing-site .pstat-item { text-align: center; }
.landing-site .pstat-val { display: block; font-size: 3rem; font-weight: 800; color: var(--primary); letter-spacing: -0.05em; }
.landing-site .pstat-lbl { font-size: 0.875rem; color: var(--t3); font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; }
.landing-site .price-cards-modern { display: grid; grid-template-columns: repeat(3, 1fr); gap: 32px; }
.landing-site .pcard-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.landing-site .pcard-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--gradient-primary); }

/* ===== Flow & FAQ ===== */
.landing-site .flow-steps-modern { display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px; margin-bottom: 60px; }
.landing-site .fstep-card { padding: 40px 32px; position: relative; }
.landing-site .fstep-num { font-size: 3rem; font-weight: 900; color: rgba(59, 130, 246, 0.1); position: absolute; top: 10px; right: 20px; }
.landing-site .faq-list-modern { max-width: 800px; margin: 0 auto; }
.landing-site .faq-item-modern { margin-bottom: 16px; padding: 0; overflow: hidden; }
.landing-site .faq-item-modern summary { padding: 24px 32px; display: flex; align-items: center; justify-content: space-between; font-weight: 700; font-size: 1.125rem; cursor: pointer; list-style: none; }
.landing-site .faq-ans { padding: 0 32px 24px; color: var(--t2); line-height: 1.6; }
.landing-site .faq-arrow { transition: transform 0.3s; }
.landing-site .faq-item-modern[open] .faq-arrow { transform: rotate(180deg); }

/* ===== Contact & CTA ===== */
.landing-site .contact-grid-modern { display: grid; grid-template-columns: repeat(2, 1fr); gap: 40px; max-width: 1000px; margin: 0 auto; }
.landing-site .contact-card-modern { padding: 60px 48px; text-align: center; }
.landing-site .contact-icon-box { width: 100px; height: 100px; border-radius: 50%; margin: 0 auto 32px; display: flex; align-items: center; justify-content: center; background: rgba(59, 130, 246, 0.1); }
.landing-site .contact-icon-box.manager { background: rgba(45, 212, 191, 0.1); }
.landing-site .contact-icon-box img { width: 60%; height: auto; border-radius: 8px; }
.landing-site .contact-handle { font-size: 1.25rem; font-weight: 700; color: var(--primary); margin-bottom: 24px; }
.landing-site .contact-features { display: flex; flex-direction: column; gap: 12px; margin-bottom: 40px; color: var(--t2); }
.landing-site .w-full { width: 100%; box-sizing: border-box; }

.landing-site .sec-cta-modern { padding: 120px 0; }
.landing-site .cta-banner { padding: 80px 100px; display: grid; grid-template-columns: 1.5fr 1fr; align-items: center; overflow: hidden; position: relative; }
.landing-site .cta-content h2 { font-size: 3rem; font-weight: 800; margin-bottom: 20px; line-height: 1.1; }
.landing-site .cta-content p { font-size: 1.25rem; color: var(--t2); margin-bottom: 40px; }
.landing-site .cta-actions { display: flex; gap: 20px; }
.landing-site .visual-orb { position: absolute; right: -100px; top: -100px; width: 400px; height: 400px; background: radial-gradient(circle, rgba(59, 130, 246, 0.15) 0%, transparent 70%); border-radius: 50%; }

/* ===== Footer ===== */
.landing-site .footer-modern { padding: 100px 0 40px; border-top: 1px solid rgba(255, 255, 255, 0.05); }
.landing-site .footer-inner { display: flex; justify-content: space-between; margin-bottom: 80px; }
.landing-site .f-logo { font-size: 2rem; font-weight: 800; color: var(--t1); margin-bottom: 24px; letter-spacing: -0.04em; }
.landing-site .f-logo span { color: var(--primary); }
.landing-site .footer-brand p { color: var(--t3); max-width: 320px; line-height: 1.6; }
.landing-site .footer-links-grid { display: flex; gap: 100px; }
.landing-site .f-col h5 { font-size: 1rem; font-weight: 700; color: var(--t1); margin-bottom: 24px; }
.landing-site .f-col a { display: block; color: var(--t3); text-decoration: none; margin-bottom: 16px; transition: color 0.3s; }
.landing-site .f-col a:hover { color: var(--primary); }
.landing-site .footer-bottom { display: flex; justify-content: space-between; align-items: center; border-top: 1px solid rgba(255, 255, 255, 0.05); padding-top: 40px; color: var(--t3); font-size: 0.875rem; }
.landing-site .f-bottom-links { display: flex; gap: 32px; }
.landing-site .f-bottom-links a { color: var(--t3); text-decoration: none; }

/* ===== Media Queries ===== */
@media (max-width: 1024px) {
  .landing-site .hero-inner, .landing-site .prod-content-modern, .landing-site .cta-banner { grid-template-columns: 1fr; text-align: center; }
  .landing-site .hero-desc, .landing-site .sec-desc, .landing-site .footer-brand p { margin-left: auto; margin-right: auto; }
  .landing-site .hero-btns, .landing-site .hero-trust-mini, .landing-site .prod-btns-modern, .landing-site .cta-actions { justify-content: center; }
  .landing-site .sol-grid, .landing-site .adv-grid, .landing-site .price-cards-modern, .landing-site .flow-steps-modern { grid-template-columns: repeat(2, 1fr); }
  .landing-site .footer-inner { flex-direction: column; gap: 60px; }
  .landing-site .footer-links-grid { gap: 40px; }
}

@media (max-width: 640px) {
  .landing-site .sol-grid, .landing-site .adv-grid, .landing-site .price-cards-modern, .landing-site .flow-steps-modern, .landing-site .contact-grid-modern { grid-template-columns: 1fr; }
  .landing-site .prod-tabs-modern { grid-template-columns: 1fr; }
  .landing-site .pricing-stats { gap: 40px; }
  .landing-site .cta-banner { padding: 60px 40px; }
}
</style>
