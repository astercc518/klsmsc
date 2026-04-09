<template>
  <div class="data-send-page">
    <div class="page-header">
      <div class="header-left">
        <h1>{{ $t('dataSend.title') }}</h1>
        <p class="subtitle">{{ $t('dataSend.subtitle') }}</p>
      </div>
    </div>

    <div class="main-content">
      <!-- 左侧：数据包选择 -->
      <div class="products-section">
        <h2 class="section-title">
          <el-icon><ShoppingCart /></el-icon>
          {{ $t('dataSend.selectDataPackage') }}
        </h2>

        <div class="products-list" v-loading="loadingProducts">
          <div
            v-for="product in products"
            :key="product.id"
            class="product-item"
            :class="{ selected: selectedProduct?.id === product.id }"
            @click="selectProduct(product)"
          >
            <div class="product-info">
              <h3>{{ product.product_name }}</h3>
              <p class="desc">{{ product.description || $t('dataSend.noDescription') }}</p>
              <div class="meta">
                <span class="stock">
                  <el-icon><User /></el-icon>
                  {{ $t('dataSend.stock') }} {{ product.stock_count?.toLocaleString() }}
                </span>
                <span class="price">${{ product.price_per_number }}/条</span>
              </div>
            </div>
            <div class="product-check" v-if="selectedProduct?.id === product.id">
              <el-icon><Check /></el-icon>
            </div>
          </div>

          <el-empty v-if="products.length === 0 && !loadingProducts" :description="$t('dataSend.noDataPackages')" />
        </div>

        <!-- 自定义筛选 -->
        <div class="custom-filter">
          <h3>
            <el-icon><Filter /></el-icon>
            {{ $t('dataSend.orCustomFilter') }}
          </h3>
          <div class="filter-form">
            <div class="filter-row">
              <label>{{ $t('dataSend.targetCountry') }}</label>
              <el-input v-model="customFilter.country" :placeholder="$t('dataSend.countryPlaceholder')" />
            </div>
            <div class="filter-row">
              <label>{{ $t('dataSend.includeTags') }}</label>
              <el-select v-model="customFilter.tags" multiple filterable allow-create :placeholder="$t('dataSend.selectTags')" style="width: 100%">
                <el-option v-for="tag in commonTags" :key="tag" :label="tag" :value="tag" />
              </el-select>
            </div>
            <div class="filter-row">
              <label>{{ $t('dataSend.excludeUsed') }}</label>
              <el-input-number v-model="customFilter.exclude_used_days" :min="0" /> {{ $t('dataSend.days') }}
            </div>
            <el-button @click="previewCustomFilter" :loading="previewing">
              <el-icon><Search /></el-icon>
              {{ $t('dataSend.previewResult') }}
            </el-button>
          </div>
          <div v-if="previewResult" class="preview-result">
            <p>{{ $t('dataSend.matchingNumbers') }}: <strong>{{ previewResult.total_count?.toLocaleString() }}</strong></p>
          </div>
        </div>
      </div>

      <!-- 右侧：发送配置 -->
      <div class="send-section">
        <h2 class="section-title">
          <el-icon><Message /></el-icon>
          {{ $t('dataSend.sendConfig') }}
        </h2>

        <el-form label-position="top" class="send-form">
          <el-form-item :label="$t('dataSend.purchaseQuantity')">
            <el-input-number
              v-model="orderForm.quantity"
              :min="selectedProduct?.min_purchase || 100"
              :max="maxQuantity"
              :step="100"
              style="width: 100%"
            />
            <div class="quantity-hint">
              <span v-if="selectedProduct">
                {{ $t('dataSend.range') }}: {{ selectedProduct.min_purchase?.toLocaleString() }} - {{ selectedProduct.max_purchase?.toLocaleString() }}
              </span>
            </div>
          </el-form-item>

          <el-form-item :label="$t('dataSend.smsContent')">
            <!-- 变量插入工具栏 -->
            <div class="sms-toolbar">
              <div class="toolbar-group">
                <span class="toolbar-label">变量:</span>
                <el-tooltip v-for="v in MAIN_VARS" :key="v.tag" :content="v.tip" placement="top" :show-after="400">
                  <el-button size="small" @click="insertVariable(v.tag)">{{ v.label }}</el-button>
                </el-tooltip>
                <el-dropdown trigger="click" @command="insertVariable">
                  <el-button size="small">更多 ▾</el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item v-for="v in MORE_VARS" :key="v.tag" :command="v.tag">
                        {{ v.label }} <span style="color:var(--el-text-color-placeholder);font-size:11px;margin-left:6px">{{ v.tip }}</span>
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
              <div class="toolbar-group">
                <el-button size="small" type="success" @click="showTemplateEngine = true">
                  <el-icon><MagicStick /></el-icon>
                  智能生成
                </el-button>
                <el-button v-if="aiEnabled" size="small" type="primary" @click="showAiDialog = true">
                  <el-icon><MagicStick /></el-icon>
                  AI 生成
                </el-button>
              </div>
            </div>

            <el-input
              ref="smsInputRef"
              v-model="orderForm.smsContent"
              type="textarea"
              :rows="5"
              :placeholder="$t('dataSend.smsContentPlaceholder')"
              maxlength="500"
              show-word-limit
              @focus="saveCursorPos"
              @click="saveCursorPos"
              @keyup="saveCursorPos"
            />

            <!-- 变量预览 -->
            <div v-if="hasVariables" class="sms-preview">
              <span class="preview-label">预览效果:</span>
              <div class="preview-text">{{ previewSms }}</div>
            </div>
          </el-form-item>

          <el-form-item :label="$t('dataSend.sendChannel')">
            <el-select v-model="orderForm.channelId" :placeholder="$t('dataSend.selectChannel')" style="width: 100%">
              <el-option v-for="ch in channels" :key="ch.id" :label="ch.name" :value="ch.id" />
            </el-select>
          </el-form-item>

          <!-- 费用预估 -->
          <div class="cost-estimate">
            <h3>{{ $t('dataSend.costEstimate') }}</h3>
            <div class="cost-row">
              <span>{{ $t('dataSend.dataFee') }}</span>
              <span>${{ dataFee }}</span>
            </div>
            <div class="cost-row">
              <span>{{ $t('dataSend.smsFee') }}</span>
              <span>${{ smsFee }}</span>
            </div>
            <div class="cost-row total">
              <span>{{ $t('dataSend.totalFee') }}</span>
              <span>${{ totalFee }}</span>
            </div>
          </div>

          <el-button type="primary" size="large" @click="submitOrder" :loading="submitting" :disabled="!canSubmit">
            <el-icon><Promotion /></el-icon>
            {{ $t('dataSend.createSendTask') }}
          </el-button>
        </el-form>
      </div>
    </div>

    <!-- 我的订单 -->
    <div class="orders-section">
      <h2 class="section-title">
        <el-icon><List /></el-icon>
        {{ $t('dataSend.myDataOrders') }}
      </h2>
      <el-table :data="myOrders" v-loading="loadingOrders" stripe>
        <el-table-column prop="order_no" :label="$t('dataSend.orderNo')" min-width="180">
          <template #default="{ row }">
            <span class="order-no">{{ row.order_no }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="product_name" :label="$t('dataSend.dataPackage')" min-width="150" />
        <el-table-column prop="quantity" :label="$t('dataPool.quantity')" width="100" align="right">
          <template #default="{ row }">{{ row.quantity?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column :label="$t('smsRecords.cost')" width="100" align="right">
          <template #default="{ row }">
            <span class="price">${{ row.total_price }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="$t('common.status')" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">{{ getStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="$t('common.createdAt')" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ========== 前端模板引擎对话框 ========== -->
    <el-dialog v-model="showTemplateEngine" title="智能生成短信文案" width="600px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="文案类型">
          <el-select v-model="tplForm.type" style="width: 100%">
            <el-option v-for="opt in TPL_TYPES" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="语言">
          <el-select v-model="tplForm.language" style="width: 100%">
            <el-option v-for="lang in LANG_OPTIONS" :key="lang.value" :label="lang.label" :value="lang.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="补充关键词（可选）">
          <el-input v-model="tplForm.keywords" placeholder="如：优惠、限时、注册奖励" />
        </el-form-item>
        <el-button type="primary" @click="generateFromTemplateEngine" :loading="tplGenerating">
          生成 {{ tplForm.count }} 条文案
        </el-button>
      </el-form>

      <div v-if="tplResults.length" class="gen-results">
        <div
          v-for="(msg, idx) in tplResults"
          :key="idx"
          class="gen-result-item"
          :class="{ selected: selectedTplIdx === idx }"
          @click="selectedTplIdx = idx"
        >
          <span class="gen-idx">{{ idx + 1 }}</span>
          <span class="gen-text">{{ msg }}</span>
        </div>
      </div>

      <template #footer>
        <el-button @click="showTemplateEngine = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :disabled="selectedTplIdx < 0" @click="applyTplResult">
          {{ t('smsSend.applySelectedText') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ========== AI 生成对话框 ========== -->
    <el-dialog v-model="showAiDialog" title="AI 智能生成短信文案" width="600px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="描述你的需求">
          <el-input
            v-model="aiForm.prompt"
            type="textarea"
            :rows="3"
            placeholder="如：巴西博彩推广短信，吸引用户注册，风格热情"
          />
        </el-form-item>
        <div style="display: flex; gap: 12px">
          <el-form-item label="语言" style="flex: 1">
            <el-select v-model="aiForm.language" style="width: 100%">
              <el-option v-for="lang in LANG_OPTIONS" :key="lang.value" :label="lang.label" :value="lang.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="生成条数" style="flex: 1">
            <el-input-number v-model="aiForm.count" :min="1" :max="20" style="width: 100%" />
          </el-form-item>
        </div>
        <el-button type="primary" @click="generateFromAi" :loading="aiGenerating" :disabled="!aiForm.prompt.trim()">
          <el-icon><MagicStick /></el-icon>
          调用 AI 生成
        </el-button>
      </el-form>

      <div v-if="aiResults.length" class="gen-results">
        <div
          v-for="(msg, idx) in aiResults"
          :key="idx"
          class="gen-result-item"
          :class="{ selected: selectedAiIdx === idx }"
          @click="selectedAiIdx = idx"
        >
          <span class="gen-idx">{{ idx + 1 }}</span>
          <span class="gen-text">{{ msg }}</span>
        </div>
      </div>

      <template #footer>
        <el-button @click="showAiDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :disabled="selectedAiIdx < 0" @click="applyAiResult">
          {{ t('smsSend.applySelectedText') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ShoppingCart, User, Check, Filter, Search, Message, Promotion, List, MagicStick } from '@element-plus/icons-vue'
import { getDataProducts, buyAndSend, previewDataSelection, getMyOrders, type DataProduct } from '@/api/data'
import { getAiConfig, generateSmsContent } from '@/api/ai'
import request from '@/api/index'

const { t } = useI18n()

// ============ 变量定义 ============

const MAIN_VARS = [
  { tag: '{序号}', label: '序号', tip: '批次内序号，从1递增' },
  { tag: '{号码}', label: '号码', tip: '接收方手机号码' },
  { tag: '{国家}', label: '国家', tip: '目标国家代码（如 BR、IN）' },
  { tag: '{日期}', label: '日期', tip: '当天日期 YYYY-MM-DD' },
  { tag: '{随机码}', label: '随机码', tip: '6位随机数字' },
]
const MORE_VARS = [
  { tag: '{时间}', label: '时间', tip: '当前时间 HH:MM' },
  { tag: '{随机码4}', label: '随机码4', tip: '4位随机数字' },
  { tag: '{随机码8}', label: '随机码8', tip: '8位随机数字' },
  { tag: '{随机字母}', label: '随机字母', tip: '6位随机大写字母' },
]
const VARIABLES = [...MAIN_VARS, ...MORE_VARS]

const TPL_TYPES = [
  { value: 'marketing', label: '营销推广' },
  { value: 'notification', label: '通知提醒' },
  { value: 'verification', label: '验证码' },
  { value: 'greeting', label: '节日问候' },
  { value: 'promotion', label: '优惠活动' },
  { value: 'invitation', label: '邀请注册' },
]

const LANG_OPTIONS = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
  { value: 'pt', label: 'Português' },
  { value: 'es', label: 'Español' },
  { value: 'vi', label: 'Tiếng Việt' },
  { value: 'th', label: 'ภาษาไทย' },
  { value: 'id', label: 'Bahasa Indonesia' },
]

// ============ 内置文案模板库 ============

const TEMPLATE_POOL: Record<string, Record<string, string[]>> = {
  marketing: {
    zh: [
      '🔥 限时特惠！立即注册即可获得丰厚奖励，机会不容错过！',
      '💰 新用户专属福利来了！首次注册即送大礼包，快来领取！',
      '🎯 您的专属邀请已生效！点击链接开启全新体验，好礼等你拿！',
      '⭐ 精选好物推荐！超值优惠限时开放，先到先得！',
      '🎁 恭喜您获得VIP体验资格！立即激活享受尊贵服务！',
      '📢 重磅福利！邀请好友一起参与，双倍奖励等你赢！',
      '🚀 开启财富之旅！注册即享新手礼包，机会稍纵即逝！',
    ],
    en: [
      '🔥 Limited offer! Register now and claim your exclusive bonus!',
      '💰 Special welcome package waiting for you! Sign up today!',
      '🎯 Your VIP invitation is ready! Click to start winning big!',
      '⭐ Exclusive deal just for you! Don\'t miss this chance!',
      '🎁 Congratulations! You\'ve been selected for a special reward!',
      '🚀 Start your journey today! Register and get instant rewards!',
    ],
    pt: [
      '🔥 Oferta limitada! Cadastre-se agora e ganhe bônus exclusivo!',
      '💰 Pacote de boas-vindas especial esperando por você! Inscreva-se hoje!',
      '🎯 Seu convite VIP está pronto! Clique para começar a ganhar!',
      '⭐ Promoção exclusiva só para você! Não perca esta chance!',
      '🎁 Parabéns! Você foi selecionado para uma recompensa especial!',
      '🚀 Comece sua jornada hoje! Registre-se e ganhe recompensas instantâneas!',
    ],
    es: [
      '🔥 ¡Oferta limitada! ¡Regístrate ahora y reclama tu bono exclusivo!',
      '💰 ¡Paquete de bienvenida especial esperándote! ¡Inscríbete hoy!',
      '🎯 ¡Tu invitación VIP está lista! ¡Haz clic para empezar a ganar!',
      '⭐ ¡Oferta exclusiva solo para ti! ¡No pierdas esta oportunidad!',
      '🎁 ¡Felicidades! ¡Has sido seleccionado para una recompensa especial!',
    ],
    vi: [
      '🔥 Ưu đãi có hạn! Đăng ký ngay để nhận thưởng độc quyền!',
      '💰 Gói chào mừng đặc biệt đang chờ bạn! Đăng ký ngay hôm nay!',
      '🎯 Lời mời VIP của bạn đã sẵn sàng! Nhấp để bắt đầu!',
      '⭐ Ưu đãi độc quyền dành riêng cho bạn! Đừng bỏ lỡ!',
    ],
    th: [
      '🔥 ข้อเสนอจำกัด! สมัครเลยรับโบนัสพิเศษ!',
      '💰 แพ็คเกจต้อนรับพิเศษรอคุณอยู่! สมัครวันนี้!',
      '🎯 คำเชิญ VIP ของคุณพร้อมแล้ว! คลิกเพื่อเริ่มต้น!',
    ],
    id: [
      '🔥 Penawaran terbatas! Daftar sekarang dan dapatkan bonus eksklusif!',
      '💰 Paket selamat datang spesial menunggu Anda! Daftar hari ini!',
      '🎯 Undangan VIP Anda sudah siap! Klik untuk mulai menang!',
    ],
  },
  notification: {
    zh: [
      '📢 您的账户有新的重要通知，请及时查看！',
      '⏰ 温馨提醒：您的服务即将到期，请尽快续费！',
      '📋 系统升级通知：我们将于近期进行系统优化，届时服务可能短暂中断。',
      '🔔 安全提醒：检测到您的账户在新设备上登录，如非本人操作请立即修改密码。',
    ],
    en: [
      '📢 Important notification for your account. Please check now!',
      '⏰ Reminder: Your service is about to expire. Please renew soon!',
      '📋 System update notice: We will perform maintenance shortly.',
      '🔔 Security alert: New login detected on your account.',
    ],
    pt: [
      '📢 Notificação importante para sua conta. Verifique agora!',
      '⏰ Lembrete: Seu serviço está prestes a expirar. Renove em breve!',
    ],
    es: [
      '📢 Notificación importante para su cuenta. ¡Revise ahora!',
      '⏰ Recordatorio: Su servicio está a punto de expirar. ¡Renueve pronto!',
    ],
    vi: [
      '📢 Thông báo quan trọng cho tài khoản của bạn. Hãy kiểm tra ngay!',
    ],
    th: ['📢 แจ้งเตือนสำคัญสำหรับบัญชีของคุณ กรุณาตรวจสอบ!'],
    id: ['📢 Pemberitahuan penting untuk akun Anda. Silakan periksa sekarang!'],
  },
  verification: {
    zh: [
      '您的验证码是：{随机码}，5分钟内有效，请勿泄露给他人。',
      '【验证码】{随机码}，此验证码用于身份验证，请在5分钟内使用。',
      '验证码 {随机码}，您正在进行身份验证操作，如非本人操作请忽略。',
    ],
    en: [
      'Your verification code is: {code}. Valid for 5 minutes. Do not share.',
      'Code: {code}. Use this to verify your identity. Expires in 5 min.',
    ],
    pt: [
      'Seu código de verificação é: {code}. Válido por 5 minutos.',
    ],
    es: [
      'Su código de verificación es: {code}. Válido por 5 minutos.',
    ],
    vi: ['Mã xác minh của bạn là: {code}. Có hiệu lực trong 5 phút.'],
    th: ['รหัสยืนยันของคุณคือ: {code} ใช้ได้ภายใน 5 นาที'],
    id: ['Kode verifikasi Anda: {code}. Berlaku selama 5 menit.'],
  },
  greeting: {
    zh: [
      '🎉 节日快乐！感谢您一直以来的支持和信赖，祝您万事如意！',
      '🌟 祝您新年快乐！新的一年，新的开始，愿好运常伴！',
      '🎊 感恩有您！祝您节日愉快，幸福美满！',
    ],
    en: [
      '🎉 Happy holidays! Thank you for your continued support!',
      '🌟 Wishing you a wonderful new year! May good fortune be with you!',
    ],
    pt: ['🎉 Boas festas! Obrigado pelo seu apoio contínuo!'],
    es: ['🎉 ¡Felices fiestas! ¡Gracias por su continuo apoyo!'],
    vi: ['🎉 Chúc mừng ngày lễ! Cảm ơn sự ủng hộ của bạn!'],
    th: ['🎉 สุขสันต์วันหยุด! ขอบคุณสำหรับการสนับสนุนของคุณ!'],
    id: ['🎉 Selamat hari raya! Terima kasih atas dukungan Anda!'],
  },
  promotion: {
    zh: [
      '🎊 限时优惠！全场商品低至3折，错过再等一年！',
      '💎 会员专属：今日充值享双倍积分，立即行动！',
      '🔥 爆款活动！前100名注册即送超值大礼包！',
      '🎯 独家折扣码已为您生成，立即使用享最高50%优惠！',
    ],
    en: [
      '🎊 Flash sale! Up to 70% off everything. Don\'t miss out!',
      '💎 Members exclusive: Double points on all purchases today!',
      '🔥 Hot deal! First 100 sign-ups get a special bonus package!',
    ],
    pt: [
      '🎊 Venda relâmpago! Até 70% de desconto em tudo!',
      '💎 Exclusivo para membros: pontos em dobro hoje!',
    ],
    es: [
      '🎊 ¡Venta flash! ¡Hasta 70% de descuento en todo!',
      '💎 Exclusivo para miembros: ¡puntos dobles hoy!',
    ],
    vi: ['🎊 Flash sale! Giảm đến 70% tất cả sản phẩm!'],
    th: ['🎊 Flash sale! ลดสูงสุด 70% ทุกรายการ!'],
    id: ['🎊 Flash sale! Diskon hingga 70% untuk semua produk!'],
  },
  invitation: {
    zh: [
      '👋 您的好友邀请您加入，新用户注册即享专属礼包！点击链接开始！',
      '🤝 诚挚邀请您注册体验！专属邀请码已为您生成，享新人福利！',
      '🎁 好友推荐：立即注册，您和好友各获奖励，快来参与吧！',
    ],
    en: [
      '👋 You\'ve been invited! Register now and get an exclusive welcome bonus!',
      '🤝 Join us today! Your special invitation code is ready. Claim rewards now!',
    ],
    pt: [
      '👋 Você foi convidado! Registre-se agora e ganhe um bônus exclusivo!',
    ],
    es: [
      '👋 ¡Has sido invitado! ¡Regístrate ahora y obtén un bono exclusivo!',
    ],
    vi: ['👋 Bạn được mời! Đăng ký ngay và nhận thưởng!'],
    th: ['👋 คุณได้รับเชิญ! สมัครเลยรับโบนัสต้อนรับ!'],
    id: ['👋 Anda diundang! Daftar sekarang dan dapatkan bonus eksklusif!'],
  },
}

// ============ State ============

const loadingProducts = ref(false)
const loadingOrders = ref(false)
const previewing = ref(false)
const submitting = ref(false)

const products = ref<DataProduct[]>([])
const myOrders = ref<any[]>([])
const channels = ref<any[]>([])
const selectedProduct = ref<DataProduct | null>(null)
const previewResult = ref<any>(null)

const commonTags = ref(['crypto', 'finance', 'shopping', 'gaming', 'social'])

const customFilter = ref({
  country: '',
  tags: [] as string[],
  exclude_used_days: 0,
})

const orderForm = ref({
  quantity: 1000,
  smsContent: '',
  channelId: null as number | null,
})

const smsInputRef = ref<any>(null)
const cursorPos = ref(0)

const aiEnabled = ref(false)

// 模板引擎
const showTemplateEngine = ref(false)
const tplForm = ref({ type: 'marketing', language: 'zh', keywords: '', count: 5 })
const tplGenerating = ref(false)
const tplResults = ref<string[]>([])
const selectedTplIdx = ref(-1)

// AI
const showAiDialog = ref(false)
const aiForm = ref({ prompt: '', language: 'zh', count: 5 })
const aiGenerating = ref(false)
const aiResults = ref<string[]>([])
const selectedAiIdx = ref(-1)

// ============ Computed ============

const maxQuantity = computed(() => {
  if (selectedProduct.value) {
    return Math.min(selectedProduct.value.max_purchase, selectedProduct.value.stock_count)
  }
  return previewResult.value?.total_count || 100000
})

const unitPrice = computed(() => {
  return selectedProduct.value?.price_per_number || '0.001'
})

const dataFee = computed(() => {
  return (parseFloat(unitPrice.value) * orderForm.value.quantity).toFixed(2)
})

const smsFee = computed(() => {
  return (0.01 * orderForm.value.quantity).toFixed(2)
})

const totalFee = computed(() => {
  return (parseFloat(dataFee.value) + parseFloat(smsFee.value)).toFixed(2)
})

const canSubmit = computed(() => {
  return (selectedProduct.value || (customFilter.value.country && previewResult.value))
    && orderForm.value.quantity > 0
    && orderForm.value.smsContent.trim()
})

const hasVariables = computed(() => {
  const msg = orderForm.value.smsContent
  if (/\{(序号|国家|日期|时间|随机码|号码|随机字母|index|country|date|time|code|phone|letters)\}/.test(msg)) return true
  return /\{(随机码|code|随机字母|letters)\d{1,2}\}/.test(msg)
})

function _previewRandDigits(n: number): string {
  return Array.from({ length: n }, () => Math.floor(Math.random() * 10)).join('')
}
function _previewRandLetters(n: number): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
  return Array.from({ length: n }, () => chars[Math.floor(Math.random() * 26)]).join('')
}

const previewSms = computed(() => {
  let msg = orderForm.value.smsContent
  const now = new Date()
  const today = now.toISOString().slice(0, 10)
  const time = now.toTimeString().slice(0, 5)
  msg = msg.replace(/\{序号\}/g, '1').replace(/\{index\}/g, '1')
  msg = msg.replace(/\{国家\}/g, 'BR').replace(/\{country\}/g, 'BR')
  msg = msg.replace(/\{日期\}/g, today).replace(/\{date\}/g, today)
  msg = msg.replace(/\{时间\}/g, time).replace(/\{time\}/g, time)
  msg = msg.replace(/\{随机码\}/g, '385921').replace(/\{code\}/g, '385921')
  msg = msg.replace(/\{号码\}/g, '5511999887766').replace(/\{phone\}/g, '5511999887766')
  msg = msg.replace(/\{随机字母\}/g, 'AXKPMZ').replace(/\{letters\}/g, 'AXKPMZ')
  msg = msg.replace(/\{随机码(\d{1,2})\}/g, (_, n) => _previewRandDigits(parseInt(n)))
  msg = msg.replace(/\{code(\d{1,2})\}/g, (_, n) => _previewRandDigits(parseInt(n)))
  msg = msg.replace(/\{随机字母(\d{1,2})\}/g, (_, n) => _previewRandLetters(parseInt(n)))
  msg = msg.replace(/\{letters(\d{1,2})\}/g, (_, n) => _previewRandLetters(parseInt(n)))
  return msg
})

// ============ 变量插入 ============

function saveCursorPos() {
  nextTick(() => {
    const textarea = smsInputRef.value?.$el?.querySelector?.('textarea') || smsInputRef.value?.ref
    if (textarea) {
      cursorPos.value = textarea.selectionStart ?? orderForm.value.smsContent.length
    }
  })
}

function insertVariable(tag: string) {
  const content = orderForm.value.smsContent
  const pos = cursorPos.value
  orderForm.value.smsContent = content.slice(0, pos) + tag + content.slice(pos)
  cursorPos.value = pos + tag.length
  nextTick(() => {
    const textarea = smsInputRef.value?.$el?.querySelector?.('textarea')
    if (textarea) {
      textarea.focus()
      textarea.setSelectionRange(cursorPos.value, cursorPos.value)
    }
  })
}

// ============ 前端模板引擎 ============

function generateFromTemplateEngine() {
  tplGenerating.value = true
  selectedTplIdx.value = -1

  setTimeout(() => {
    const pool = TEMPLATE_POOL[tplForm.value.type] || TEMPLATE_POOL.marketing
    let langPool = pool[tplForm.value.language] || pool.en || pool.zh || []

    if (langPool.length === 0) {
      langPool = pool.zh || []
    }

    // 随机选取并打乱
    const shuffled = [...langPool].sort(() => Math.random() - 0.5)
    let results = shuffled.slice(0, Math.min(tplForm.value.count, shuffled.length))

    // 用关键词做简单增强：在文案末尾附加关键词
    if (tplForm.value.keywords.trim()) {
      const kws = tplForm.value.keywords.split(/[,，、\s]+/).filter(Boolean)
      results = results.map((msg, i) => {
        const kw = kws[i % kws.length]
        if (kw && !msg.includes(kw)) {
          return msg.replace(/[!！。]?\s*$/, `，${kw}！`)
        }
        return msg
      })
    }

    tplResults.value = results
    tplGenerating.value = false
  }, 300)
}

function applyTplResult() {
  if (selectedTplIdx.value >= 0 && tplResults.value[selectedTplIdx.value]) {
    orderForm.value.smsContent = tplResults.value[selectedTplIdx.value]
    showTemplateEngine.value = false
  }
}

// ============ AI 生成 ============

async function generateFromAi() {
  if (!aiForm.value.prompt.trim()) return
  aiGenerating.value = true
  selectedAiIdx.value = -1
  aiResults.value = []

  try {
    const res = await generateSmsContent({
      prompt: aiForm.value.prompt,
      count: aiForm.value.count,
      language: aiForm.value.language,
    })
    if (res.success && res.messages?.length) {
      aiResults.value = res.messages
    } else {
      ElMessage.warning('AI 未返回有效文案，请尝试修改描述')
    }
  } catch (e: any) {
    ElMessage.error(e.message || 'AI 生成失败')
    // fallback 到模板引擎
    tplForm.value.type = 'marketing'
    tplForm.value.language = aiForm.value.language
    tplForm.value.keywords = aiForm.value.prompt
    generateFromTemplateEngine()
    aiResults.value = tplResults.value
    if (aiResults.value.length) {
      ElMessage.info('已使用内置模板引擎生成替代文案')
    }
  } finally {
    aiGenerating.value = false
  }
}

function applyAiResult() {
  if (selectedAiIdx.value >= 0 && aiResults.value[selectedAiIdx.value]) {
    orderForm.value.smsContent = aiResults.value[selectedAiIdx.value]
    showAiDialog.value = false
  }
}

// ============ 数据加载 ============

const loadProducts = async () => {
  loadingProducts.value = true
  try {
    const res = await getDataProducts({})
    if (res.success) {
      products.value = res.items
    }
  } catch (error) {
    console.error('Failed to load products:', error)
  } finally {
    loadingProducts.value = false
  }
}

const loadMyOrders = async () => {
  loadingOrders.value = true
  try {
    const res = await getMyOrders({ page: 1, page_size: 10 })
    if (res.success) {
      myOrders.value = res.items
    }
  } catch (error) {
    console.error('Failed to load orders:', error)
  } finally {
    loadingOrders.value = false
  }
}

const loadChannels = async () => {
  try {
    const res = await request.get('/channels')
    if (res.success) {
      channels.value = res.channels || res.data || []
    }
  } catch (error) {
    console.error('Failed to load channels:', error)
  }
}

const checkAiConfig = async () => {
  try {
    const cfg = await getAiConfig()
    aiEnabled.value = cfg.ai_enabled
  } catch {
    aiEnabled.value = false
  }
}

const selectProduct = (product: DataProduct) => {
  selectedProduct.value = product
  previewResult.value = null
  customFilter.value = { country: '', tags: [], exclude_used_days: 0 }
  orderForm.value.quantity = Math.max(product.min_purchase, 1000)
}

const previewCustomFilter = async () => {
  if (!customFilter.value.country && customFilter.value.tags.length === 0) {
    ElMessage.warning(t('dataSend.pleaseSetFilter'))
    return
  }

  previewing.value = true
  try {
    const res = await previewDataSelection(customFilter.value)
    if (res.success) {
      previewResult.value = res
      selectedProduct.value = null
      ElMessage.success(t('dataSend.foundNumbers', { count: res.total_count?.toLocaleString() }))
    }
  } catch {
    ElMessage.error(t('common.previewFailed'))
  } finally {
    previewing.value = false
  }
}

const submitOrder = async () => {
  try {
    await ElMessageBox.confirm(
      t('dataSend.confirmOrderMessage', { quantity: orderForm.value.quantity.toLocaleString(), cost: totalFee.value }),
      t('dataSend.confirmOrder'),
      { type: 'warning' },
    )
  } catch {
    return
  }

  submitting.value = true
  try {
    const payload: any = { quantity: orderForm.value.quantity }

    if (selectedProduct.value) {
      payload.product_id = selectedProduct.value.id
    } else {
      payload.filter_criteria = customFilter.value
    }

    const res = await buyAndSend({ ...payload, message: orderForm.value.smsContent })
    if (res.success) {
      ElMessage.success(`订单创建成功! 订单号: ${res.order_no}`)
      loadMyOrders()
      orderForm.value.quantity = 1000
    }
  } catch (error: any) {
    ElMessage.error(error.message || t('dataSend.orderCreatedFailed'))
  } finally {
    submitting.value = false
  }
}

// ============ Helpers ============

const getStatusType = (status: string) => {
  const types: Record<string, string> = {
    pending: 'warning',
    processing: 'primary',
    completed: 'success',
    cancelled: 'info',
    expired: 'danger',
  }
  return types[status] || 'info'
}

const getStatusLabel = (status: string) => {
  const statusKeys: Record<string, string> = {
    pending: 'dataSend.statusPending',
    processing: 'dataSend.statusProcessing',
    completed: 'dataSend.statusCompleted',
    cancelled: 'dataSend.statusCancelled',
    expired: 'dataSend.statusExpired',
  }
  return statusKeys[status] ? t(statusKeys[status]) : status
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString()
}

// ============ Init ============

onMounted(() => {
  loadProducts()
  loadMyOrders()
  loadChannels()
  checkAiConfig()
})
</script>

<style scoped>
.data-send-page {
  width: 100%;
}

.page-header {
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

.main-content {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 24px;
  margin-bottom: 40px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 16px 0;
}

.products-section,
.send-section {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 20px;
}

.products-list {
  max-height: 300px;
  overflow-y: auto;
  margin-bottom: 20px;
}

.product-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.product-item:hover {
  border-color: var(--el-color-primary-light-5);
}

.product-item.selected {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.product-info h3 {
  font-size: 16px;
  margin: 0 0 4px 0;
}

.product-info .desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin: 0 0 8px 0;
}

.product-info .meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
}

.product-info .stock {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--el-text-color-secondary);
}

.product-info .price {
  font-weight: 600;
  color: var(--el-color-success);
}

.product-check {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
}

.custom-filter {
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 16px;
}

.custom-filter h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  margin: 0 0 12px 0;
}

.filter-form {
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

.filter-row label {
  min-width: 80px;
  font-size: 14px;
}

.preview-result {
  margin-top: 12px;
  padding: 12px;
  background: var(--el-color-success-light-9);
  border-radius: 8px;
  color: var(--el-color-success);
}

.send-form {
  margin-top: 20px;
}

.quantity-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

/* 变量工具栏 */
.sms-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px 8px 0 0;
  border: 1px solid var(--el-border-color-lighter);
  border-bottom: none;
}

.toolbar-group {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.toolbar-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.var-group-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  font-weight: 500;
}

/* 短信预览 */
.sms-preview {
  margin-top: 8px;
  padding: 10px 12px;
  background: var(--el-color-info-light-9);
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
}

.preview-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-right: 8px;
}

.preview-text {
  font-size: 13px;
  color: var(--el-text-color-primary);
  margin-top: 4px;
  line-height: 1.5;
  word-break: break-all;
}

/* 费用区域 */
.cost-estimate {
  background: var(--el-fill-color-light);
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 20px;
}

.cost-estimate h3 {
  font-size: 14px;
  margin: 0 0 12px 0;
}

.cost-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  font-size: 14px;
}

.cost-row.total {
  border-top: 1px solid var(--el-border-color-lighter);
  margin-top: 8px;
  padding-top: 12px;
  font-weight: 600;
  font-size: 16px;
}

.orders-section {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 20px;
}

.order-no {
  font-family: monospace;
  font-size: 12px;
}

.price {
  font-weight: 600;
  color: var(--el-color-success);
}

/* 生成结果列表 */
.gen-results {
  margin-top: 16px;
  max-height: 300px;
  overflow-y: auto;
}

.gen-result-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.gen-result-item:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}

.gen-result-item.selected {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.gen-idx {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--el-fill-color);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.gen-result-item.selected .gen-idx {
  background: var(--el-color-primary);
  color: white;
}

.gen-text {
  font-size: 13px;
  line-height: 1.5;
}

@media (max-width: 1024px) {
  .main-content {
    grid-template-columns: 1fr;
  }
}
</style>
