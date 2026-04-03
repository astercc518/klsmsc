<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">我的私有库</h2>
      <div class="header-actions">
        <el-button type="success" @click="showUpload = true">上传数据</el-button>
        <el-button @click="openUploadTasksDialog">{{ t('dataMyNumbers.uploadTasksBtn') }}</el-button>
        <el-button type="primary" @click="$router.push('/data/store')">前往商店选购</el-button>
      </div>
    </div>

    <!-- 上传对话框 -->
    <el-dialog
      v-model="showUpload"
      title="上传私有号码数据"
      width="500px"
      class="pl-upload-dialog"
      @closed="resetForm"
    >
      <el-form :model="uploadForm" label-width="100px">
        <el-form-item :label="t('dataMyNumbers.uploadCountryLabel')">
          <el-skeleton v-if="accountCountryLoading" :rows="1" animated />
          <el-alert
            v-else-if="!accountCountryLocked"
            type="warning"
            :closable="false"
            :title="t('dataMyNumbers.uploadNoAccountCountryHint')"
          />
          <el-input
            v-else
            :model-value="`${countryName(accountCountryLocked)} (${accountCountryLocked})`"
            disabled
          />
        </el-form-item>
        <el-form-item label="数据来源">
          <el-select v-model="uploadForm.source" placeholder="请选择来源" style="width: 100%">
            <el-option label="手工上传" value="Manual Upload" />
            <el-option label="客户提供" value="Customer Registry" />
            <el-option label="展会采集" value="Exhibition" />
            <el-option label="社工库" value="social_eng" />
            <el-option label="撞库" value="credential" />
          </el-select>
        </el-form-item>
        <el-form-item label="数据用途">
          <el-select v-model="uploadForm.purpose" placeholder="请选择用途" style="width: 100%">
            <el-option label="营销推广" value="Marketing" />
            <el-option label="社交通知" value="Social" />
            <el-option label="金融互金" value="finance" />
            <el-option label="交友" value="dating" />
            <el-option label="BC/兼职" value="bc" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="uploadForm.remarks" type="textarea" placeholder="请输入备注信息（可选）" />
        </el-form-item>
        <el-form-item
          class="pl-upload-carrier-item"
          :label="t('dataMyNumbers.uploadCarrierDetect')"
        >
          <el-switch v-model="uploadDetectCarrier" />
        </el-form-item>
        <el-form-item label="选择文件">
          <el-upload
            class="upload-demo"
            drag
            action="#"
            :auto-upload="false"
            :on-change="handleFileChange"
            :limit="1"
            :on-exceed="handleExceed"
            ref="uploadRef"
          >
            <el-icon class="el-icon--upload"><upload-filled /></el-icon>
            <div class="el-upload__text">
              将文件拖到此处，或<em>点击上传</em>
            </div>
            <template #tip>
              <div class="el-upload__tip">
                支持 CSV 或 TXT。国家与短信账户一致，不可更改；号码列可为 + 区号或本地号。
                若为「图文」混排，请导出为仅含号码的文本或 CSV，或使用 UTF-8 / GBK 保存。
                {{ t('dataMyNumbers.uploadUseAsyncHint') }}
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUpload = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submitUpload">
          {{ t('dataMyNumbers.uploadSubmitTask') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 上传任务（弹窗查看） -->
    <el-dialog
      v-model="showUploadTasksDialog"
      :title="t('dataMyNumbers.uploadTasksTitle')"
      width="min(960px, 96vw)"
      class="upload-tasks-dialog"
      destroy-on-close
      @opened="onUploadTasksDialogOpened"
    >
      <div class="upload-tasks-toolbar">
        <span class="upload-tasks-hint">{{ t('dataMyNumbers.uploadTasksDialogHint') }}</span>
        <el-button type="primary" link @click="loadUploadTasks" :loading="uploadTasksLoading">
          {{ t('dataMyNumbers.uploadTasksRefresh') }}
        </el-button>
      </div>
      <el-table
        v-loading="uploadTasksLoading"
        :data="uploadTasks"
        size="small"
        stripe
        max-height="420"
        :empty-text="t('dataMyNumbers.uploadTasksEmpty')"
      >
        <el-table-column prop="task_id" :label="t('dataMyNumbers.uploadTasksColTask')" min-width="160" show-overflow-tooltip />
        <el-table-column prop="original_filename" :label="t('dataMyNumbers.uploadTasksColFile')" min-width="120" show-overflow-tooltip />
        <el-table-column :label="t('dataMyNumbers.uploadTasksColStatus')" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="uploadStatusTagType(row.status)">{{ uploadStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('dataMyNumbers.uploadTasksColProgress')" min-width="140">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress_percent ?? 0"
              :status="row.status === 'failed' ? 'exception' : row.status === 'completed' ? 'success' : undefined"
            />
            <div class="stage-text" v-if="row.stage">{{ row.stage }}</div>
          </template>
        </el-table-column>
        <el-table-column :label="t('dataMyNumbers.uploadTasksColStats')" width="110">
          <template #default="{ row }">
            {{ row.inserted ?? 0 }} / {{ row.updated ?? 0 }}
            <div class="muted" v-if="row.total_unique">共 {{ row.total_unique }} 条去重</div>
          </template>
        </el-table-column>
        <el-table-column :label="t('dataMyNumbers.uploadTasksColTime')" width="160">
          <template #default="{ row }">{{ fmtDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="说明" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.status === 'failed'" class="err-cell">{{ row.error_message }}</span>
            <span v-else-if="row.result_batch_id" class="muted">批次 {{ row.result_batch_id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="88" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'pending'"
              type="danger"
              link
              size="small"
              :loading="abandoningTaskId === row.task_id"
              @click="onAbandonUploadTask(row.task_id)"
            >
              {{ t('dataMyNumbers.uploadTaskAbandon') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="upload-tasks-pager" v-if="uploadTasksTotal > uploadTasksPageSize">
        <el-pagination
          layout="prev, pager, next, total"
          :total="uploadTasksTotal"
          :page-size="uploadTasksPageSize"
          v-model:current-page="uploadTasksPage"
          @current-change="loadUploadTasks"
          small
        />
      </div>
    </el-dialog>

    <el-alert v-if="summaryMismatch" type="warning" :closable="false" show-icon class="summary-mismatch">
      {{ t('dataMyNumbers.summaryMismatchWarn') }}
    </el-alert>

    <!-- 运营商统计与筛选 -->
    <el-alert
      v-if="summaryTruncated"
      type="info"
      :closable="false"
      show-icon
      class="summary-truncate-tip"
      title="为加快加载，当前仅展示最近批次分组卡片；号码总数以上方统计为准。短信发送「私有库」仍会加载全部分组。"
    />
    <div class="carrier-filter-section" v-if="totalCount > 0">
      <div class="filter-label">运营商筛选:</div>
      <div class="carrier-tags">
        <span
          class="carrier-tag"
          :class="{ active: !carrierFilter }"
          @click="carrierFilter = ''"
        >全部</span>
        <span
          v-for="c in availableCarriers"
          :key="c.name"
          class="carrier-tag"
          :class="{ active: carrierFilter === c.name }"
          @click="carrierFilter = c.name"
        >
          {{ c.name }} <span class="carrier-count">{{ formatCount(c.count) }}</span>
        </span>
      </div>
    </div>

    <!-- 卡片列表 -->
    <div v-loading="loading" class="groups-wrap">
      <el-empty v-if="!loading && filteredGroups.length === 0" :description="carrierFilter ? '该运营商下暂无数据' : '暂无私有库数据，请前往商店购买或等待上传任务完成'" />

      <el-row :gutter="16">
        <el-col :xs="24" :sm="12" :lg="8" v-for="(g, idx) in filteredGroups" :key="idx">
          <el-card class="group-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <div class="card-title">
                  <span class="card-name">{{ getGroupName(g) }}</span>
                </div>
                <span class="card-count">{{ (carrierFilter ? (g.carriers?.find(c => c.name === carrierFilter)?.count || 0) : g.count).toLocaleString() }} 条</span>
              </div>
            </template>
            <div class="card-body">
                <div class="card-info">
                  <div class="info-row" v-if="g.library_origin">
                    <span class="info-label">{{ t('dataMyNumbers.libraryOriginLabel') }}</span>
                    <el-tag size="small" :type="libraryOriginTagType(g.library_origin)">
                      {{ libraryOriginText(g.library_origin) }}
                    </el-tag>
                  </div>
                  <div class="usage-stats">
                    <div class="usage-item">
                      <span class="usage-label">未使用</span>
                      <span class="usage-value success">{{ g.unused_count.toLocaleString() }}</span>
                    </div>
                    <div class="usage-item">
                      <span class="usage-label">已使用</span>
                      <span class="usage-value info">{{ g.used_count.toLocaleString() }}</span>
                    </div>
                  </div>
                  <div class="info-row">
                    <span class="info-label">来源</span>
                    <el-tag size="small" type="danger">{{ g.source_label || g.source }}</el-tag>
                  </div>
                  <div class="info-row">
                    <span class="info-label">用途</span>
                    <el-tag size="small" type="warning">{{ g.purpose_label || g.purpose }}</el-tag>
                  </div>
                  <div class="info-row" v-if="g.remarks">
                    <span class="info-label">备注</span>
                    <span class="info-remarks" :title="g.remarks">{{ g.remarks }}</span>
                  </div>
                  <div class="carrier-distribution">
                    <div class="info-label" style="margin-bottom: 4px">运营商分布</div>
                    <div class="carrier-tags-mini">
                      <span 
                        v-for="c in g.carriers" 
                        :key="c.name" 
                        class="sp-carrier-badge"
                        :class="{ active: carrierFilter === c.name || !carrierFilter }"
                      >
                        {{ c.name }}: {{ c.count }}
                      </span>
                    </div>
                  </div>
                  <div class="info-row" v-if="g.last_at">
                    <span class="info-label">最新入库</span>
                    <span class="info-date">{{ fmtDate(g.last_at) }}</span>
                  </div>
                </div>

              <div class="card-actions">
                <el-button type="danger" size="small" plain @click="handleDelete(g)">
                  删除
                </el-button>
                <el-button type="success" size="small" @click="handleSendSms(g)">
                  发送短信
                </el-button>
                <el-dropdown @command="(cmd: string) => handleExport(g, cmd)">
                  <el-button type="primary" size="small">
                    下载数据 <el-icon style="margin-left:4px"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="csv">导出 CSV</el-dropdown-item>
                      <el-dropdown-item command="txt">导出 TXT（纯号码）</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowDown, UploadFilled } from '@element-plus/icons-vue'
import {
  getMyNumbersSummary,
  exportMyNumbers,
  deleteMyNumbers,
  createMyNumbersUploadTask,
  getMyNumbersUploadTask,
  listMyNumbersUploadTasks,
  abandonMyNumbersUploadTask,
  type PrivateLibraryUploadTaskDTO,
} from '@/api/data'
import { getAccountInfo } from '@/api/account'
import { ElMessage, ElMessageBox, genFileId, UploadRawFile, UploadProps } from 'element-plus'
import { findCountryByIso } from '@/constants/countries'

const router = useRouter()
const { t } = useI18n()

interface NumberGroup {
  country_code: string
  source: string
  source_label: string
  purpose: string
  purpose_label: string
  count: number
  used_count: number
  unused_count: number
  carriers: { name: string, count: number }[]
  batch_id: string
  remarks: string
  first_at: string | null
  last_at: string | null
  /** 后端：manual | purchased | mixed */
  library_origin?: string
}

const groups = ref<NumberGroup[]>([])
const carrierFilter = ref('')
const totalCount = ref(0)
const summaryTruncated = ref(false)
const summaryMismatch = ref(false)
const loading = ref(false)
const abandoningTaskId = ref<string | null>(null)

const availableCarriers = computed(() => {
  const map: Record<string, number> = {}
  groups.value.forEach(g => {
    if (g.carriers) {
      g.carriers.forEach(c => {
        const name = c.name || 'Unknown'
        map[name] = (map[name] || 0) + c.count
      })
    }
  })
  return Object.entries(map).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count)
})

const filteredGroups = computed(() => {
  if (!carrierFilter.value) return groups.value
  return groups.value.filter(g => g.carriers.some(c => c.name === carrierFilter.value))
})

function formatCount(count: number): string {
  if (count >= 10000) return (count / 10000).toFixed(1) + 'w'
  if (count >= 1000) return (count / 1000).toFixed(1) + 'k'
  return count.toString()
}

function libraryOriginText(origin: string) {
  if (origin === 'manual') return t('dataMyNumbers.libraryOriginManual')
  if (origin === 'purchased') return t('dataMyNumbers.libraryOriginPurchased')
  if (origin === 'mixed') return t('dataMyNumbers.libraryOriginMixed')
  return origin
}

function libraryOriginTagType(origin: string): 'success' | 'warning' | 'info' {
  if (origin === 'manual') return 'success'
  if (origin === 'purchased') return 'warning'
  return 'info'
}

function getGroupName(group: any) {
  const country = findCountryByIso(group.country_code)
  const countryName = country ? country.name : (group.country_code || '未知')
  const sourceName = group.source_label || group.source || '未知来源'
  const purposeName = group.purpose_label || group.purpose || '未知用途'
  const baseName = `${countryName}-${sourceName}-${purposeName}`
  
  if (group.remarks && group.remarks !== '') {
    return `${baseName} (${group.remarks})`
  }
  if (group.last_at) {
    return `${baseName} [${fmtDate(group.last_at)}]`
  }
  return baseName
}

// 上传控制
const showUpload = ref(false)
const uploading = ref(false)
const uploadRef = ref<any>(null)
const uploadFile = ref<File | null>(null)
const uploadForm = ref({
  country_code: '',
  source: 'Manual Upload',
  purpose: 'Marketing',
  remarks: '',
})
const uploadDetectCarrier = ref(true)
const showUploadTasksDialog = ref(false)
/** 与账户 country_code 一致（大写 ISO），打开上传弹窗时拉取 */
const accountCountryLocked = ref('')
const accountCountryLoading = ref(false)

const uploadTasks = ref<PrivateLibraryUploadTaskDTO[]>([])
const uploadTasksLoading = ref(false)
const uploadTasksPage = ref(1)
const uploadTasksPageSize = ref(10)
const uploadTasksTotal = ref(0)
let uploadPollTimer: ReturnType<typeof setInterval> | null = null

function resetForm() {
  uploadForm.value = {
    country_code: accountCountryLocked.value || '',
    source: 'Manual Upload',
    purpose: 'Marketing',
    remarks: '',
  }
  uploadDetectCarrier.value = true
  uploadFile.value = null
  if (uploadRef.value) {
    uploadRef.value.clearFiles()
  }
}

async function loadAccountCountryForUpload() {
  accountCountryLoading.value = true
  try {
    const info = await getAccountInfo()
    const cc = (info.country_code || '').trim().toUpperCase()
    accountCountryLocked.value = cc
    uploadForm.value.country_code = cc
    if (!cc) {
      ElMessage.warning(t('dataMyNumbers.uploadNoAccountCountry'))
    }
  } catch {
    accountCountryLocked.value = ''
    uploadForm.value.country_code = ''
    ElMessage.error(t('dataMyNumbers.uploadAccountCountryLoadFailed'))
  } finally {
    accountCountryLoading.value = false
  }
}

watch(showUpload, (open) => {
  if (open) void loadAccountCountryForUpload()
})

function handleFileChange(file: any) {
  uploadFile.value = file.raw
}

const handleExceed: UploadProps['onExceed'] = (files) => {
  uploadRef.value?.clearFiles()
  const raw = files[0] as UploadRawFile
  raw.uid = genFileId()
  uploadRef.value?.handleStart(raw)
  uploadFile.value = raw
}

function buildUploadFormData(): FormData {
  const formData = new FormData()
  if (!uploadFile.value) return formData
  formData.append('file', uploadFile.value)
  formData.append('country_code', uploadForm.value.country_code)
  formData.append('source', uploadForm.value.source)
  formData.append('purpose', uploadForm.value.purpose)
  if (uploadForm.value.remarks) {
    formData.append('remarks', uploadForm.value.remarks)
  }
  formData.append('detect_carrier', uploadDetectCarrier.value ? 'true' : 'false')
  return formData
}

function mergeTaskRow(updated: PrivateLibraryUploadTaskDTO) {
  const i = uploadTasks.value.findIndex((x) => x.task_id === updated.task_id)
  if (i >= 0) {
    uploadTasks.value[i] = { ...uploadTasks.value[i], ...updated }
  } else {
    uploadTasks.value = [updated, ...uploadTasks.value]
  }
}

function stopUploadPoll() {
  if (uploadPollTimer) {
    clearInterval(uploadPollTimer)
    uploadPollTimer = null
  }
}

function startUploadTaskPoll(taskId: string) {
  stopUploadPoll()
  const tick = async () => {
    try {
      const res = await getMyNumbersUploadTask(taskId)
      if (!res.success || !res.task) return
      mergeTaskRow(res.task)
      const st = res.task.status
      if (st === 'completed') {
        stopUploadPoll()
        ElMessage.success(t('dataMyNumbers.uploadAsyncDone'))
        loadData()
        loadUploadTasks()
      } else if (st === 'failed') {
        stopUploadPoll()
        ElMessage.error((t('dataMyNumbers.uploadAsyncFailed') + ': ') + (res.task.error_message || ''))
        loadUploadTasks()
      }
    } catch {
      /* 轮询失败时保留定时器，下一拍重试 */
    }
  }
  void tick()
  uploadPollTimer = setInterval(() => void tick(), 2000)
}

async function loadUploadTasks() {
  uploadTasksLoading.value = true
  try {
    const res = await listMyNumbersUploadTasks({
      page: uploadTasksPage.value,
      page_size: uploadTasksPageSize.value,
    })
    if (res.success) {
      uploadTasks.value = res.items || []
      uploadTasksTotal.value = res.total ?? 0
    }
  } catch {
    /* 列表失败静默，避免打断主流程 */
  } finally {
    uploadTasksLoading.value = false
  }
}

function openUploadTasksDialog() {
  uploadTasksPage.value = 1
  showUploadTasksDialog.value = true
}

function onUploadTasksDialogOpened() {
  void loadUploadTasks()
}

function uploadStatusLabel(status: string) {
  if (status === 'pending') return '排队中'
  if (status === 'processing') return '处理中'
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '失败'
  return status
}

function uploadStatusTagType(status: string): 'info' | 'warning' | 'success' | 'danger' {
  if (status === 'pending') return 'info'
  if (status === 'processing') return 'warning'
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  return 'info'
}

function fmtDateTime(d: string | null | undefined): string {
  if (!d) return '-'
  return new Date(d).toLocaleString('zh-CN')
}

async function submitUpload() {
  if (!uploadFile.value) return ElMessage.warning('请选择文件')
  if (!accountCountryLocked.value) {
    return ElMessage.warning(t('dataMyNumbers.uploadNoAccountCountry'))
  }
  uploadForm.value.country_code = accountCountryLocked.value

  uploading.value = true
  const formData = buildUploadFormData()

  try {
    const res = await createMyNumbersUploadTask(formData)
    if (res.task_id) {
      showUpload.value = false
      resetForm()
      uploadTasksPage.value = 1
      showUploadTasksDialog.value = true
      ElMessage.success(t('dataMyNumbers.uploadAsyncStartedWithHint'))
      startUploadTaskPoll(res.task_id)
    } else {
      ElMessage.warning(res.message || '创建任务失败')
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || e.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

function countryName(code: string): string {
  if (!code) return '未知'
  const c = findCountryByIso(code)
  return c ? c.name : code
}

function fmtDate(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('zh-CN')
}

async function loadData() {
  loading.value = true
  summaryMismatch.value = false
  try {
    // max_batches=0：展示全部分组卡片；默认 400 时批次极多时新上传可能不在「最近批次」内
    const res = (await getMyNumbersSummary({ max_batches: 0 })) as {
      success?: boolean
      items?: NumberGroup[]
      total?: number
      meta?: { truncated?: boolean }
    }
    if (res.success) {
      groups.value = res.items || []
      totalCount.value = res.total ?? 0
      summaryTruncated.value = Boolean(res.meta?.truncated)
      const t = totalCount.value
      const n = groups.value.length
      if (t > 0 && n === 0 && !carrierFilter.value) {
        summaryMismatch.value = true
        ElMessage.warning(t('dataMyNumbers.summaryMismatchWarn'))
      }
    } else {
      ElMessage.error('私库汇总加载失败，请稍后重试')
    }
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function onAbandonUploadTask(taskId: string) {
  try {
    await ElMessageBox.confirm(t('dataMyNumbers.uploadTaskAbandonConfirm'), '提示', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  abandoningTaskId.value = taskId
  try {
    const res = await abandonMyNumbersUploadTask(taskId)
    if (res.success !== false) {
      ElMessage.success(res.message || '已放弃')
      await loadUploadTasks()
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || e.message || '操作失败')
  } finally {
    abandoningTaskId.value = null
  }
}

async function handleExport(g: NumberGroup, fmt: string) {
  // 优先从 sessionStorage 获取（模拟登录模式），兜底从 localStorage 获取（正常登录）
  const impersonateApiKey = sessionStorage.getItem('impersonate_api_key')
  const localStorageApiKey = localStorage.getItem('api_key')
  const apiKey = (sessionStorage.getItem('impersonate_mode') === '1') ? impersonateApiKey : localStorageApiKey
  
  if (!apiKey) return ElMessage.error('认证信息缺失，请重新登录')

  // 构建下载 URL，将 api_key 作为参数传递以支持浏览器原生下载进度
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
  const apiPath = '/api/v1/data/my-numbers/export'
  const params = new URLSearchParams({
    fmt,
    country: g.country_code || '',
    source: g.source || '',
    purpose: g.purpose || '',
    batch_id: g.batch_id || '',
    api_key: apiKey
  })
  
  const downloadUrl = `${baseUrl}${apiPath}?${params.toString()}`
  
  // 使用隐藏的 iframe 或 window.open 触发下载，避免 axios 占用过多内存
  window.open(downloadUrl, '_blank')
  ElMessage.success('正在开始下载，请查看浏览器下载管理器')
}

function handleSendSms(g: NumberGroup) {
  router.push({
    path: '/sms/send',
    query: {
      data_country: g.country_code,
      data_source: g.source,
      data_purpose: g.purpose,
      data_batch_id: g.batch_id == null || g.batch_id === undefined ? '' : String(g.batch_id),
      data_count: String(g.count),
    },
  })
}

async function handleDelete(g: NumberGroup) {
  try {
    await ElMessageBox.confirm(
      `确定要删除该组 ${g.count} 条号码吗？此操作不可恢复。`,
      '警告',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    
    loading.value = true
    // 必须显式传齐维度；batch_id 为空串时匹配库内 NULL/空批次（避免 axios 省略参数导致条件错位）
    const res = await deleteMyNumbers({
      country: String(g.country_code ?? ''),
      source: String(g.source ?? ''),
      purpose: String(g.purpose ?? ''),
      batch_id: g.batch_id == null || g.batch_id === undefined ? '' : String(g.batch_id),
    })

    if (res.success) {
      ElMessage.success(res.message || '删除成功')
      loadData()
    } else {
      ElMessage.warning(res.message || '未能删除数据')
    }
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e.message || '删除失败')
    }
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
})

onUnmounted(() => {
  stopUploadPoll()
})
</script>

<style scoped>
.summary-truncate-tip { margin-bottom: 16px; }
.page-container { width: 100%; padding: 0 4px; }
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.upload-tasks-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.upload-tasks-hint {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.page-title { font-size: 20px; font-weight: 600; margin: 0; }

.summary-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  margin-bottom: 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  color: #fff;
}
.summary-info { display: flex; gap: 32px; }
.summary-item { display: flex; flex-direction: column; }
.summary-value { font-size: 28px; font-weight: 700; line-height: 1.2; }
.summary-label { font-size: 13px; opacity: 0.85; margin-top: 2px; }

.usage-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  padding: 10px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}
.usage-item { display: flex; flex-direction: column; flex: 1; }
.usage-label { font-size: 11px; color: var(--el-text-color-secondary); margin-bottom: 2px; }
.usage-value { font-size: 16px; font-weight: 700; }
.usage-value.success { color: var(--el-color-success); }
.usage-value.info { color: var(--el-color-info); }

.carrier-filter-section { margin-bottom: 24px; }
.filter-label { font-size: 13px; font-weight: 500; color: var(--text-secondary); margin-bottom: 10px; }
.carrier-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.carrier-tag { display: inline-flex; align-items: center; padding: 6px 16px; font-size: 13px; border-radius: 20px; border: 1px solid var(--border-default); background: rgba(255, 255, 255, 0.05); color: var(--text-secondary); cursor: pointer; transition: all 0.15s; }
.carrier-tag:hover { border-color: var(--el-color-primary-light-5); color: var(--el-color-primary); }
.carrier-tag.active { border-color: var(--el-color-primary); background: rgba(64, 158, 255, 0.1); color: var(--el-color-primary); font-weight: 600; box-shadow: 0 0 0 1px var(--el-color-primary); }
.carrier-count { font-size: 11px; opacity: 0.6; margin-left: 4px; }

.carrier-tags-mini { display: flex; flex-wrap: wrap; gap: 6px; }
.sp-carrier-badge { display: inline-block; padding: 1px 8px; border-radius: 10px; background: rgba(255, 255, 255, 0.05); color: var(--el-text-color-secondary); font-size: 11px; border: 1px solid var(--border-default); opacity: 0.7; }
.sp-carrier-badge.active { background: rgba(64, 158, 255, 0.15); color: var(--el-color-primary); border-color: rgba(64, 158, 255, 0.2); opacity: 1; font-weight: 600; }

.group-card {
  margin-bottom: 16px;
  border-radius: 12px;
  transition: transform 0.2s;
}
.group-card:hover { transform: translateY(-2px); }

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-title { display: flex; align-items: center; }
.card-name { font-weight: 600; font-size: 15px; }
.card-count {
  font-size: 18px;
  font-weight: 700;
  color: var(--el-color-primary);
}

.card-body { display: flex; flex-direction: column; gap: 14px; }
.card-info { display: flex; flex-direction: column; gap: 8px; }
.info-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.info-label {
  color: var(--el-text-color-secondary);
  min-width: 56px;
  flex-shrink: 0;
}
.info-date { color: var(--el-text-color-secondary); font-size: 12px; }

.card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.info-remarks {
  color: var(--el-text-color-regular);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}
.summary-mismatch {
  margin-bottom: 12px;
}
.groups-wrap {
  min-height: 200px;
}
.err-cell {
  color: var(--el-color-danger);
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.stage-text {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.upload-tasks-pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

/* 上传弹窗：运营商开关标签单行展示，避免长文案折行误读为「说明小字」 */
.pl-upload-dialog .pl-upload-carrier-item :deep(.el-form-item__label) {
  white-space: nowrap;
}
</style>
