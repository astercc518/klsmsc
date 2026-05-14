<template>
  <div class="short-link-domains">
    <!-- ======== Per-domain 证书上传对话框 ======== -->
    <el-dialog
      v-model="certUploadVisible"
      :title="certUploadTarget ? `上传 / 更新「${certUploadTarget.domain}」专属证书` : '上传证书'"
      width="780px"
      destroy-on-close
      :close-on-click-modal="false"
    >
      <el-alert
        v-if="certUploadTarget"
        type="info"
        :closable="false"
        show-icon
        :title="`证书必须覆盖 ${certUploadTarget.domain}（含 *.${certUploadTarget.domain} 通配）`"
        description="生成路径：Cloudflare Dashboard → 该域名 → SSL/TLS → Origin Server → Create Certificate；Hostnames 列表填该域名 + *.通配子域名；有效期建议 15 年。"
        style="margin-bottom: 16px"
      />

      <el-form label-position="top">
        <el-form-item label="Origin Certificate (PEM)">
          <el-input
            v-model="uploadForm.cert_pem"
            type="textarea"
            :rows="8"
            placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
            class="mono-textarea"
          />
        </el-form-item>
        <el-form-item label="Private Key">
          <el-input
            v-model="uploadForm.key_pem"
            type="textarea"
            :rows="8"
            placeholder="-----BEGIN PRIVATE KEY-----&#10;...&#10;-----END PRIVATE KEY-----"
            class="mono-textarea"
          />
        </el-form-item>
      </el-form>

      <div v-if="uploadResult" class="upload-result" :class="uploadResult.success ? 'success' : 'fail'">
        <div class="result-line" v-if="uploadResult.success">✅ 上传成功</div>
        <div class="result-line" v-else>❌ {{ uploadResult.message }}</div>
      </div>

      <template #footer>
        <el-button @click="certUploadVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="uploading"
          :disabled="!canSubmitUpload"
          @click="submitCertUpload"
        >
          保存并 reload nginx
        </el-button>
      </template>
    </el-dialog>

    <div class="header-bar">
      <div class="header-text">
        <h3>短链域名</h3>
        <p class="hint">维护可供「发送短信 → 短链转换」选用的域名列表。仅 super_admin 可增删改。</p>
      </div>
      <div class="header-actions">
        <el-input
          v-model="filter.keyword"
          placeholder="搜索域名"
          size="small"
          clearable
          style="width: 200px"
          @keyup.enter="loadDomains"
        />
        <el-select
          v-model="filter.status"
          placeholder="全部状态"
          size="small"
          clearable
          style="width: 130px"
          @change="loadDomains"
        >
          <el-option label="启用" value="active" />
          <el-option label="停用" value="disabled" />
        </el-select>
        <el-button size="small" @click="loadDomains">刷新</el-button>
        <el-button type="primary" size="small" @click="openCreate">新增域名</el-button>
      </div>
    </div>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="domain" label="域名" min-width="200" />
      <el-table-column prop="scheme" label="协议" width="80" />
      <el-table-column prop="base_path" label="路径前缀" width="110" />
      <el-table-column label="完整 base_url" min-width="240">
        <template #default="{ row }">
          <div class="base-url-cell">
            <code>{{ row.base_url }}</code>
            <el-tooltip content="复制" placement="top">
              <el-button
                link
                size="small"
                :icon="DocumentCopy"
                class="copy-btn"
                @click="copyText(row.base_url)"
              />
            </el-tooltip>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="link_count" label="已生成短链" width="116" align="right">
        <template #default="{ row }">
          <span :class="{ 'stat-zero': !row.link_count }">{{ formatNumber(row.link_count) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="total_clicks" label="累计点击" width="100" align="right">
        <template #default="{ row }">
          <span :class="{ 'stat-zero': !row.total_clicks }" :style="row.total_clicks ? 'color: var(--el-color-success); font-weight: 600' : ''">
            {{ formatNumber(row.total_clicks) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="最近使用" width="170">
        <template #default="{ row }">
          <span v-if="row.last_used_at" class="time-text">{{ formatTime(row.last_used_at) }}</span>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
      <el-table-column prop="sort_order" label="排序" width="76" />
      <el-table-column label="证书" width="160">
        <template #default="{ row }">
          <div class="cert-cell" v-if="domainCerts[row.id]">
            <template v-if="domainCerts[row.id].configured">
              <el-tag
                v-if="domainCerts[row.id].expired"
                type="danger"
                size="small"
              >已过期</el-tag>
              <el-tag
                v-else-if="(domainCerts[row.id].days_until_expiry ?? 9999) < 30"
                type="warning"
                size="small"
              >{{ domainCerts[row.id].days_until_expiry }}天后过期</el-tag>
              <el-tag
                v-else
                type="success"
                size="small"
              >✓ 已配置</el-tag>
              <span class="cert-cell-hint" v-if="!domainCerts[row.id].expired">
                {{ domainCerts[row.id].days_until_expiry }} 天有效
              </span>
            </template>
            <template v-else>
              <el-tag type="info" size="small">未配置</el-tag>
            </template>
          </div>
          <el-tag v-else type="info" size="small" effect="plain">…</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">
            {{ row.status === 'active' ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="340" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openCertUpload(row)">
            {{ domainCerts[row.id]?.configured ? '更新证书' : '上传证书' }}
          </el-button>
          <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button
            v-if="(row.total_clicks || 0) > 0"
            link type="success" size="small"
            @click="openDownloadDialog(row)"
          >下载号码</el-button>
          <el-button
            link
            :type="row.status === 'active' ? 'warning' : 'success'"
            size="small"
            @click="toggleStatus(row)"
          >
            {{ row.status === 'active' ? '停用' : '启用' }}
          </el-button>
          <el-button link type="danger" size="small" @click="confirmDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编辑对话框 -->
    <el-dialog
      v-model="formVisible"
      :title="formMode === 'create' ? '新增短链域名' : '编辑短链域名'"
      width="520px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="formData" :rules="formRules" label-position="top">
        <el-form-item label="域名" prop="domain">
          <el-input v-model="formData.domain" placeholder="如 go.kaolach.com" />
        </el-form-item>
        <el-form-item label="协议" prop="scheme">
          <el-select v-model="formData.scheme" style="width: 100%">
            <el-option label="https" value="https" />
            <el-option label="http" value="http" />
          </el-select>
        </el-form-item>
        <el-form-item label="路径前缀" prop="base_path">
          <el-input v-model="formData.base_path" placeholder="/s（留空 = 无前缀，最省字符）" clearable />
          <div class="hint">默认 /s。营销短信推荐填空字符串，每条短信节省 2 字符</div>
        </el-form-item>
        <el-form-item label="短信里省略 https://">
          <el-switch v-model="formData.omit_scheme" />
          <div class="hint">
            开启后短信里看到 <code>klsms.com/Ab3Xz7q</code>（17 字符）；
            关闭则 <code>https://klsms.com/s/Ab3Xz7q</code>（26 字符）。
            <strong>有些运营商对 https:// 短链拦截严格，开启可显著提升投递率</strong>
          </div>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="formData.remark" placeholder="可填用途、归属等" />
        </el-form-item>
        <el-form-item label="排序权重">
          <el-input-number v-model="formData.sort_order" :min="0" :max="10000" />
          <span class="hint" style="margin-left: 8px">数字越大越靠前</span>
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="formData.status">
            <el-radio value="active">启用</el-radio>
            <el-radio value="disabled">停用</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- 实时预览：完整 base_url + 示例短链 -->
        <el-form-item label="预览效果">
          <div class="preview-wrap">
            <div class="preview-line">
              <span class="preview-label">base_url：</span>
              <code class="preview-url">{{ previewBaseUrl || '请填写域名' }}</code>
            </div>
            <div class="preview-line">
              <span class="preview-label">短链示例：</span>
              <code class="preview-url">{{ previewExample || '—' }}</code>
            </div>
            <div v-if="previewLengthHint" class="preview-hint">{{ previewLengthHint }}</div>
            <div class="preview-hint">客户在「短链转换」对话框看到的就是 base_url；用户实际收到的短信里是「短链示例」格式</div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 下载点击号码对话框 -->
    <el-dialog
      v-model="downloadVisible"
      title="下载点击号码"
      width="500px"
      destroy-on-close
      @opened="onDownloadOpened"
    >
      <div v-if="downloadTarget" class="download-form">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="域名">{{ downloadTarget.domain }}</el-descriptions-item>
          <el-descriptions-item label="累计点击">{{ formatNumber(downloadTarget.total_clicks) }}</el-descriptions-item>
        </el-descriptions>

        <el-form label-width="100px" style="margin-top: 16px">
          <el-form-item label="国家">
            <el-select
              v-model="downloadCountry"
              filterable
              placeholder="全部国家"
              clearable
              style="width: 100%"
              :loading="downloadCountriesLoading"
            >
              <el-option label="全部国家" value="" />
              <el-option
                v-for="c in downloadCountries"
                :key="c.country_code"
                :value="c.country_code"
                :label="`${countryLabel(c.country_code)} — ${formatNumber(c.count)} 条`"
              />
            </el-select>
            <div v-if="downloadCountries.length === 0 && !downloadCountriesLoading" class="download-hint">
              该域名暂无点击记录，无法导出。
            </div>
          </el-form-item>
          <el-form-item label="格式">
            <el-radio-group v-model="downloadFmt">
              <el-radio-button value="txt">TXT（一行一号）</el-radio-button>
              <el-radio-button value="csv">CSV（含点击维度）</el-radio-button>
            </el-radio-group>
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="downloadVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="downloading"
          :disabled="downloadCountries.length === 0"
          @click="submitDownload"
        >下载</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DocumentCopy } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import {
  adminListShortLinkDomains,
  adminCreateShortLinkDomain,
  adminUpdateShortLinkDomain,
  adminDeleteShortLinkDomain,
  adminGetDomainCert,
  adminUploadDomainCert,
  listClickedCountries,
  exportShortLinkClickedPhones,
  type ShortLinkDomain,
  type DomainCertInfo,
  type ClickedCountryItem,
} from '../../api/short-link'
import { findCountryByIso } from '@/constants/countries'

const loading = ref(false)
const saving = ref(false)
const rows = ref<ShortLinkDomain[]>([])
const filter = reactive({ keyword: '', status: '' })

const formVisible = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const formData = reactive({
  domain: '',
  scheme: 'https',
  base_path: '/s',
  omit_scheme: false,
  remark: '',
  status: 'active' as 'active' | 'disabled',
  sort_order: 0,
})

const formRules: FormRules = {
  domain: [
    { required: true, message: '请输入域名', trigger: 'blur' },
    {
      pattern: /^[a-z0-9.\-]+$/i,
      message: '域名仅允许字母数字、点和短横线',
      trigger: 'blur',
    },
  ],
  scheme: [{ required: true }],
  // base_path 允许空（最省字符），所以不强制 required
}

async function loadDomains() {
  loading.value = true
  try {
    const params: Record<string, string | boolean> = { with_stats: true }
    if (filter.keyword) params.keyword = filter.keyword
    if (filter.status) params.status = filter.status
    const resp: any = await adminListShortLinkDomains(params)
    rows.value = (resp?.data?.data || resp?.data || []) as ShortLinkDomain[]
  } catch (e: any) {
    ElMessage.error(`加载失败：${e?.message || e}`)
  } finally {
    loading.value = false
  }
}

// ========== 预览 / 复制 / 格式化 ==========

const previewBaseUrl = computed(() => {
  const d = (formData.domain || '').trim().toLowerCase()
  if (!d) return ''
  const scheme = (formData.scheme || 'https').replace(/[:/]+/g, '')
  const rawPath = (formData.base_path || '').trim().replace(/^\/+|\/+$/g, '')
  const netpath = rawPath ? `${d}/${rawPath}` : d
  return formData.omit_scheme ? netpath : `${scheme}://${netpath}`
})

const previewExample = computed(() => {
  if (!previewBaseUrl.value) return ''
  return `${previewBaseUrl.value}/Ab3Xz7q`
})

const previewLengthHint = computed(() => {
  const ex = previewExample.value
  if (!ex) return ''
  return `共 ${ex.length} 字符（每条短信节省的字符数 = 26 − ${ex.length}）`
})

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制')
  } catch {
    // fallback
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    try { document.execCommand('copy'); ElMessage.success('已复制') }
    catch { ElMessage.error('复制失败，请手动选中') }
    finally { document.body.removeChild(ta) }
  }
}

function formatNumber(n: number | undefined | null): string {
  const v = Number(n || 0)
  if (!v) return '0'
  return v.toLocaleString('en-US')
}

function formatTime(s: string | null | undefined): string {
  if (!s) return '—'
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return s
  // YYYY-MM-DD HH:mm
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function openCreate() {
  formMode.value = 'create'
  editingId.value = null
  Object.assign(formData, {
    domain: '',
    scheme: 'https',
    base_path: '',         // 默认无前缀（最省字符）
    omit_scheme: true,     // 默认省略 https://（更短 + 绕拦截）
    remark: '',
    status: 'active',
    sort_order: 0,
  })
  formVisible.value = true
}

function openEdit(row: ShortLinkDomain) {
  formMode.value = 'edit'
  editingId.value = row.id
  Object.assign(formData, {
    domain: row.domain,
    scheme: row.scheme,
    base_path: row.base_path || '',
    omit_scheme: !!row.omit_scheme,
    remark: row.remark || '',
    status: row.status,
    sort_order: row.sort_order,
  })
  formVisible.value = true
}

async function submitForm() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    saving.value = true
    try {
      const payload = { ...formData }
      if (formMode.value === 'create') {
        await adminCreateShortLinkDomain(payload)
        ElMessage.success('已新增')
      } else if (editingId.value) {
        await adminUpdateShortLinkDomain(editingId.value, payload)
        ElMessage.success('已保存')
      }
      formVisible.value = false
      loadDomains()
    } catch (e: any) {
      ElMessage.error(`保存失败：${e?.response?.data?.detail || e?.message || e}`)
    } finally {
      saving.value = false
    }
  })
}

async function toggleStatus(row: ShortLinkDomain) {
  try {
    const newStatus = row.status === 'active' ? 'disabled' : 'active'
    await adminUpdateShortLinkDomain(row.id, { status: newStatus })
    ElMessage.success(newStatus === 'active' ? '已启用' : '已停用')
    loadDomains()
  } catch (e: any) {
    ElMessage.error(`操作失败：${e?.response?.data?.detail || e?.message || e}`)
  }
}

async function confirmDelete(row: ShortLinkDomain) {
  try {
    await ElMessageBox.confirm(
      `确认删除域名 ${row.domain} ？已发送短信中的短链不会受影响（继续按已记录的 URL 跳转）。`,
      '删除确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await adminDeleteShortLinkDomain(row.id)
    ElMessage.success('已删除')
    loadDomains()
  } catch (e: any) {
    ElMessage.error(`删除失败：${e?.response?.data?.detail || e?.message || e}`)
  }
}

// ========== Per-domain 证书 ==========
const domainCerts = ref<Record<number, DomainCertInfo>>({})
const certUploadVisible = ref(false)
const certUploadTarget = ref<ShortLinkDomain | null>(null)
const uploading = ref(false)
const uploadForm = reactive({ cert_pem: '', key_pem: '' })
const uploadResult = ref<{ success: boolean; message: string } | null>(null)

const canSubmitUpload = computed(() => {
  return uploadForm.cert_pem.includes('BEGIN CERTIFICATE')
    && uploadForm.key_pem.includes('PRIVATE KEY')
})

async function loadAllDomainCerts() {
  // 并发拉取每个域名的证书状态；失败的不阻塞其他
  const ids = rows.value.map((r) => r.id)
  const results = await Promise.allSettled(
    ids.map((id) => adminGetDomainCert(id)),
  )
  const map: Record<number, DomainCertInfo> = {}
  results.forEach((r, idx) => {
    if (r.status === 'fulfilled') {
      const data: any = r.value?.data
      map[ids[idx]] = (data?.data || data || { configured: false, domain_id: ids[idx] }) as DomainCertInfo
    } else {
      map[ids[idx]] = { configured: false, domain_id: ids[idx], reason: '加载失败' }
    }
  })
  domainCerts.value = map
}

function openCertUpload(row: ShortLinkDomain) {
  certUploadTarget.value = row
  uploadForm.cert_pem = ''
  uploadForm.key_pem = ''
  uploadResult.value = null
  certUploadVisible.value = true
}

async function submitCertUpload() {
  if (!certUploadTarget.value) return
  uploading.value = true
  uploadResult.value = null
  try {
    const resp: any = await adminUploadDomainCert(
      certUploadTarget.value.id,
      uploadForm.cert_pem,
      uploadForm.key_pem,
    )
    const reloadOk = resp?.data?.data?.reload?.success
    if (reloadOk) {
      uploadResult.value = { success: true, message: '已写入并 reload nginx' }
      ElMessage.success(`${certUploadTarget.value.domain} 证书已生效`)
    } else {
      const reloadErr = resp?.data?.data?.reload?.error || JSON.stringify(resp?.data?.data?.reload)
      uploadResult.value = {
        success: false,
        message: `证书写入成功，但 nginx reload 失败：${reloadErr}`,
      }
      ElMessage.warning('证书已写入但 nginx reload 失败，请稍后再试')
    }
    certUploadVisible.value = false
    await loadAllDomainCerts()
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || String(e)
    uploadResult.value = { success: false, message: detail }
    ElMessage.error(`上传失败：${detail}`)
  } finally {
    uploading.value = false
  }
}

// 列表加载完成后自动刷新证书状态
async function loadAllAndCerts() {
  await loadDomains()
  await loadAllDomainCerts()
}

onMounted(loadAllAndCerts)

// ---------- 下载点击号码 ----------

const downloadVisible = ref(false)
const downloadTarget = ref<ShortLinkDomain | null>(null)
const downloadCountries = ref<ClickedCountryItem[]>([])
const downloadCountriesLoading = ref(false)
const downloadCountry = ref<string>('')
const downloadFmt = ref<'txt' | 'csv'>('txt')
const downloading = ref(false)

function countryLabel(iso: string): string {
  if (!iso || iso === 'UNKNOWN') return '未知国家'
  const c = findCountryByIso(iso)
  return c ? `${c.name} (${iso})` : iso
}

function openDownloadDialog(row: ShortLinkDomain) {
  downloadTarget.value = row
  downloadCountries.value = []
  downloadCountry.value = ''
  downloadFmt.value = 'txt'
  downloadVisible.value = true
}

async function onDownloadOpened() {
  if (!downloadTarget.value) return
  downloadCountriesLoading.value = true
  try {
    const res = await listClickedCountries(downloadTarget.value.id)
    downloadCountries.value = res.items || []
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载国家列表失败')
    downloadCountries.value = []
  } finally {
    downloadCountriesLoading.value = false
  }
}

async function submitDownload() {
  if (!downloadTarget.value) return
  downloading.value = true
  try {
    const blob = await exportShortLinkClickedPhones(downloadTarget.value.id, {
      country_code: downloadCountry.value || undefined,
      fmt: downloadFmt.value,
    })
    if (!blob || (blob as Blob).size === 0) {
      ElMessage.warning('该筛选条件下无点击号码')
      return
    }
    const suffix = downloadCountry.value || 'all'
    const ts = new Date().toISOString().replace(/[-:T.Z]/g, '').slice(0, 14)
    const filename = `clicked_phones_${downloadTarget.value.domain}_${suffix}_${ts}.${downloadFmt.value}`
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob as Blob)
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(link.href)
    ElMessage.success('下载已开始')
    downloadVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '下载失败')
  } finally {
    downloading.value = false
  }
}
</script>

<style scoped>
.short-link-domains {
  padding: 4px 0;
}
.header-bar {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 16px;
  gap: 12px;
  flex-wrap: wrap;
}
.header-text h3 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
}
.header-text .hint {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

/* base_url 单元格：带复制按钮 */
.base-url-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
}
.base-url-cell code {
  background: var(--el-fill-color-light);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 12px;
  word-break: break-all;
}
.copy-btn {
  flex: 0 0 auto;
}

/* 统计数为 0 时灰显 */
.stat-zero {
  color: var(--el-text-color-placeholder);
}
.text-muted {
  color: var(--el-text-color-placeholder);
}
.time-text {
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* 预览面板 */
.preview-wrap {
  width: 100%;
  background: var(--el-fill-color-light);
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  padding: 10px 12px;
}
.preview-line {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.preview-line:last-of-type { margin-bottom: 8px; }
.preview-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  flex: 0 0 auto;
}
.preview-url {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: var(--el-color-primary);
  word-break: break-all;
}
.preview-hint {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

/* ========== 证书面板 ========== */
.cert-panel {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 16px;
}
.cert-panel-ok    { background: var(--el-color-success-light-9); border-color: var(--el-color-success-light-7); }
.cert-panel-warn  { background: var(--el-color-warning-light-9); border-color: var(--el-color-warning-light-7); }
.cert-panel-danger { background: var(--el-color-danger-light-9); border-color: var(--el-color-danger-light-7); }
.cert-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.cert-icon {
  font-size: 28px;
  line-height: 1;
  margin-top: 4px;
}
.cert-meta { flex: 1; min-width: 0; }
.cert-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 6px;
}
.cert-status {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  margin-bottom: 6px;
}
.cert-badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 12px;
  font-weight: 600;
}
.cert-badge-ok      { background: var(--el-color-success); color: #fff; }
.cert-badge-warn    { background: var(--el-color-warning); color: #fff; }
.cert-badge-danger  { background: var(--el-color-danger); color: #fff; }
.cert-reason {
  color: var(--el-text-color-regular);
}
.cert-sans {
  margin-top: 6px;
  font-size: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.sans-label {
  color: var(--el-text-color-secondary);
  margin-right: 4px;
}
.san-tag {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.cert-actions {
  flex: 0 0 auto;
  display: flex;
  gap: 6px;
}

.mono-textarea :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}
.upload-result {
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.upload-result.success {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}
.upload-result.fail {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

/* per-row 证书状态 */
.cert-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.cert-cell-hint {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  white-space: nowrap;
}
.download-form .download-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-color-warning);
}
</style>
