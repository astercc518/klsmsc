<template>
  <div class="license-pane" v-loading="loading">
    <!-- 状态卡片 -->
    <el-card shadow="never" class="lic-card">
      <template #header>
        <div class="card-hd">
          <span>{{ $t('license.statusTitle') }}</span>
          <el-tag :type="stateTag" effect="dark" size="small">{{ stateLabel }}</el-tag>
        </div>
      </template>
      <el-descriptions :column="2" border>
        <el-descriptions-item :label="$t('license.edition')">
          <el-tag v-if="status.edition" size="small">{{ editionLabel(status.edition) }}</el-tag>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('license.customer')">{{ status.customer || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="$t('license.expiresAt')">
          {{ status.expires_at || $t('license.perpetual') }}
          <span v-if="status.days_left !== null && status.days_left !== undefined"
                :class="status.days_left < 15 ? 'days-warn' : 'days-ok'">
            （{{ status.days_left >= 0 ? $t('license.daysLeft', { d: status.days_left }) : $t('license.daysOver', { d: -status.days_left }) }}）
          </span>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('license.message')">{{ status.message }}</el-descriptions-item>
        <el-descriptions-item :label="$t('license.fingerprint')" :span="2">
          <code class="fp">{{ status.fingerprint || '-' }}</code>
          <el-button link type="primary" size="small" @click="copyFp">{{ $t('common.copy') }}</el-button>
          <span class="fp-hint">{{ $t('license.fingerprintHint') }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 上传授权 -->
    <el-card shadow="never" class="lic-card">
      <template #header>{{ $t('license.uploadTitle') }}</template>
      <el-alert :title="$t('license.uploadHint')" type="info" :closable="false" class="mb12" />
      <el-input v-model="blob" type="textarea" :rows="5" :placeholder="$t('license.uploadPlaceholder')" />
      <div class="actions">
        <el-button type="primary" :loading="uploading" :disabled="!blob.trim()" @click="doUpload">
          {{ $t('license.uploadBtn') }}
        </el-button>
      </div>
    </el-card>

    <!-- OEM 白标(仅 edition=oem) -->
    <el-card v-if="status.edition === 'oem'" shadow="never" class="lic-card">
      <template #header>{{ $t('license.brandTitle') }}</template>
      <el-form label-width="90px">
        <el-form-item :label="$t('license.brandName')">
          <el-input v-model="brand.name" maxlength="40" show-word-limit style="max-width:360px" />
        </el-form-item>
        <el-form-item :label="$t('license.brandLogo')">
          <div>
            <img v-if="brand.logo" :src="brand.logo" class="logo-preview" alt="logo" />
            <el-upload :auto-upload="false" :show-file-list="false" accept="image/*" :on-change="onLogoPick">
              <el-button>{{ $t('license.brandLogoPick') }}</el-button>
            </el-upload>
            <div class="fp-hint">{{ $t('license.brandLogoHint') }}</div>
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingBrand" @click="doSaveBrand">{{ $t('common.save') }}</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { getLicenseStatus, uploadLicense, getBrand, setBrand, type LicenseStatus } from '@/api/license'

const { t } = useI18n()
const loading = ref(false)
const uploading = ref(false)
const savingBrand = ref(false)
const blob = ref('')
const status = reactive<LicenseStatus>({} as any)
const brand = reactive<{ name: string; logo: string }>({ name: '', logo: '' })

const stateMap: Record<string, { tag: string; key: string }> = {
  valid: { tag: 'success', key: 'license.s_valid' },
  grace: { tag: 'warning', key: 'license.s_grace' },
  expired: { tag: 'danger', key: 'license.s_expired' },
  invalid: { tag: 'danger', key: 'license.s_invalid' },
  wrong_machine: { tag: 'danger', key: 'license.s_wrong_machine' },
  missing: { tag: 'info', key: 'license.s_missing' },
}
const stateTag = computed(() => stateMap[status.state]?.tag || 'info')
const stateLabel = computed(() => t(stateMap[status.state]?.key || 'license.s_missing'))
function editionLabel(e: string) {
  return { saas: 'SaaS', private: t('license.ed_private'), oem: 'OEM' }[e] || e
}

async function load() {
  loading.value = true
  try {
    const res: any = await getLicenseStatus()
    Object.assign(status, res.license || {})
    if (status.edition === 'oem') {
      const b: any = await getBrand()
      if (b.brand) { brand.name = b.brand.name || ''; brand.logo = b.brand.logo || '' }
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || t('license.loadFail'))
  } finally {
    loading.value = false
  }
}

async function doUpload() {
  uploading.value = true
  try {
    const res: any = await uploadLicense(blob.value.trim())
    ElMessage.success(res.message || t('license.uploadOk'))
    blob.value = ''
    Object.assign(status, res.license || {})
    await load()
  } catch (e: any) {
    const d = e?.response?.data?.detail
    ElMessage.error(typeof d === 'string' ? d : (d?.message || t('license.uploadFail')))
  } finally {
    uploading.value = false
  }
}

function onLogoPick(file: any) {
  const raw = file.raw as File
  if (raw.size > 480 * 1024) { ElMessage.error(t('license.brandLogoTooBig')); return }
  const reader = new FileReader()
  reader.onload = () => { brand.logo = String(reader.result) }
  reader.readAsDataURL(raw)
}

async function doSaveBrand() {
  savingBrand.value = true
  try {
    await setBrand({ name: brand.name, logo: brand.logo })
    ElMessage.success(t('license.brandSaved'))
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || t('license.brandSaveFail'))
  } finally {
    savingBrand.value = false
  }
}

function copyFp() {
  navigator.clipboard?.writeText(status.fingerprint || '')
  ElMessage.success(t('common.copied'))
}

onMounted(load)
</script>

<style scoped>
.lic-card { margin-bottom: 16px; }
.card-hd { display: flex; justify-content: space-between; align-items: center; }
.actions { margin-top: 12px; }
.mb12 { margin-bottom: 12px; }
.fp { background: #f4f4f5; padding: 2px 8px; border-radius: 4px; font-family: monospace; }
.fp-hint { color: #909399; font-size: 12px; margin-left: 8px; }
.days-warn { color: #e6a23c; font-weight: 600; }
.days-ok { color: #67c23a; }
.logo-preview { max-height: 48px; max-width: 200px; display: block; margin-bottom: 8px; border: 1px solid #eee; border-radius: 4px; }
</style>
