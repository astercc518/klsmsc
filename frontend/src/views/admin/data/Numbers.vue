<template>
  <div class="numbers-page">
    <!-- 顶部操作栏 -->
    <el-card shadow="never" class="action-card">
      <el-row align="middle" justify="space-between">
        <el-col :span="12">
          <h3 style="margin:0;font-size:18px">{{ t('dataPool.uploadData') }}</h3>
          <p style="margin:4px 0 0;font-size:13px;color:var(--el-text-color-secondary)">{{ t('dataPool.uploadDataDesc') }}</p>
        </el-col>
        <el-col :span="12" style="text-align:right">
          <el-button type="primary" size="large" @click="showImportDialog" :icon="UploadFilled">
            {{ t('dataPool.uploadDataBtn') }}
          </el-button>
          <el-button type="danger" size="large" plain @click="showDeleteByCountryDialog">
            {{ t('dataPool.deleteCountryData') }}
          </el-button>
          <el-button type="danger" size="large" @click="showClearAllDialog">
            {{ t('dataPool.clearAll') }}
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <el-statistic :title="t('dataPool.totalDataCount')" :value="stats.total" />
        </el-card>
      </el-col>
      <el-col :span="4" v-for="(count, code) in topCountries" :key="code">
        <el-card shadow="never" class="stat-card">
          <el-statistic :title="formatCountry(String(code))" :value="count" />
        </el-card>
      </el-col>
      <el-col :span="4" v-for="(info, src) in stats.by_source" :key="src">
        <el-card shadow="never" class="stat-card">
          <el-statistic :title="info?.label || sourceLabel(String(src))" :value="info?.count || 0" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 导入任务列表 -->
    <el-card shadow="never" class="tasks-card">
      <template #header>
        <el-row align="middle" justify="space-between">
          <span style="font-weight:600;font-size:15px">{{ t('dataPool.importTasks') }}</span>
          <el-button size="small" text @click="loadImportTasks">
            <el-icon><Refresh /></el-icon> {{ t('common.refresh') }}
          </el-button>
        </el-row>
      </template>
      <el-empty v-if="!importTasks.length" :description="t('dataPool.noImportTasks')" />
      <div v-else class="task-list">
        <div v-for="task in importTasks" :key="task.batch_id" class="task-item" :class="'task-' + (task._progress?.status || task.status)">
          <!-- 任务头部 -->
          <div class="task-header">
            <div class="task-file">
              <span class="task-filename">{{ task.file_name }}</span>
              <el-tag v-if="task._progress?.file_size_mb" size="small" type="info" effect="plain" style="margin-left:8px">
                {{ task._progress.file_size_mb }}MB
              </el-tag>
              <span class="task-source">{{ sourceLabel(task.source) }}</span>
            </div>
            <div class="task-status-badge">
              <template v-if="isTaskRunning(task)">
                <el-icon class="is-loading" style="color: var(--el-color-warning)"><Refresh /></el-icon>
                <span class="status-text processing">{{ t('common.processing') }}</span>
              </template>
              <template v-else-if="task.status === 'completed'">
                <span class="status-dot completed"></span>
                <span class="status-text completed">{{ t('common.completed') }}</span>
              </template>
              <template v-else-if="task.status === 'failed'">
                <span class="status-dot failed"></span>
                <span class="status-text failed">{{ t('common.failed') }}</span>
              </template>
              <template v-else>
                <span class="status-dot pending"></span>
                <span class="status-text pending">{{ t('common.waiting') }}</span>
              </template>
            </div>
          </div>

          <!-- 进行中任务：进度详情 -->
          <div v-if="isTaskRunning(task)" class="task-progress-area">
            <div class="progress-bar-row">
              <el-progress
                :percentage="task._progress?.progress_pct || 0"
                :stroke-width="20"
                :text-inside="true"
                :format="(pct: number) => `${pct}%`"
                :color="progressColors"
                striped
                striped-flow
                :duration="8"
              />
            </div>
            <div class="progress-phase">{{ task._progress?.phase || t('dataPool.preparing') }}</div>
            <div class="progress-metrics">
              <div class="metric">
                <span class="metric-value">{{ (task._progress?.total_count || 0).toLocaleString() }}</span>
                <span class="metric-label">{{ t('dataPool.scannedRows') }}</span>
              </div>
              <div class="metric">
                <span class="metric-value highlight-green">{{ (task._progress?.valid_count || 0).toLocaleString() }}</span>
                <span class="metric-label">{{ t('dataPool.written') }}</span>
              </div>
              <div class="metric">
                <span class="metric-value highlight-orange">{{ ((task._progress?.file_dedup_count || 0) + (task._progress?.duplicate_count || 0)).toLocaleString() }}</span>
                <span class="metric-label">{{ t('dataPool.dedupLabel') }}</span>
              </div>
              <div class="metric">
                <span class="metric-value highlight-red">{{ ((task._progress?.invalid_count || 0) + (task._progress?.cleaned_count || 0)).toLocaleString() }}</span>
                <span class="metric-label">{{ t('dataPool.invalidCleaned') }}</span>
              </div>
              <div class="metric">
                <span class="metric-value highlight-blue">{{ (task._progress?.speed || 0).toLocaleString() }}/s</span>
                <span class="metric-label">{{ t('dataPool.processSpeed') }}</span>
              </div>
              <div class="metric">
                <span class="metric-value">{{ formatElapsed(task._progress?.elapsed_seconds) }}</span>
                <span class="metric-label">{{ t('dataPool.elapsed') }}</span>
              </div>
            </div>
          </div>

          <!-- 已完成任务：结果摘要 -->
          <div v-else-if="task.status === 'completed'" class="task-result-row">
            <span class="result-item"><b class="highlight-green">{{ t('dataPool.itemsWritten', { n: (task._progress?.valid_count ?? task.valid_count ?? 0).toLocaleString() }) }}</b></span>
            <span class="result-sep">|</span>
            <span class="result-item">共 {{ (task._progress?.total_count ?? task.total_count ?? 0).toLocaleString() }} 行</span>
            <span class="result-sep">|</span>
            <span class="result-item">去重 {{ ((task._progress?.file_dedup_count ?? task.file_dedup_count ?? 0) + (task._progress?.duplicate_count ?? task.duplicate_count ?? 0)).toLocaleString() }}</span>
            <span class="result-sep">|</span>
            <span class="result-item">无效 {{ ((task._progress?.invalid_count ?? task.invalid_count ?? 0) + (task._progress?.cleaned_count ?? task.cleaned_count ?? 0)).toLocaleString() }}</span>
            <span v-if="task._progress?.elapsed_seconds" class="result-sep">|</span>
            <span v-if="task._progress?.elapsed_seconds" class="result-item">耗时 {{ formatElapsed(task._progress.elapsed_seconds) }}</span>
            <span v-if="task._progress?.speed" class="result-sep">|</span>
            <span v-if="task._progress?.speed" class="result-item">{{ task._progress.speed.toLocaleString() }}/s</span>
          </div>

          <!-- 失败任务 -->
          <div v-else-if="task.status === 'failed'" class="task-result-row task-error">
            {{ task._progress?.phase || task.error_message || t('dataPool.importFailed') }}
          </div>

          <!-- 底部信息 -->
          <div class="task-footer">
            <span class="task-batch-id">{{ task.batch_id }}</span>
            <span class="task-time">{{ formatDate(task.created_at) }}</span>
            <el-button
              v-if="canRetryTask(task)"
              type="primary"
              size="small"
              link
              :loading="retryingBatchId === task.batch_id"
              @click="retryImportTask(task)"
            >
              {{ t('dataPool.retrySubmit') }}
            </el-button>
            <el-button
              v-else-if="canSupplementProduct(task)"
              type="warning"
              size="small"
              link
              :loading="supplementingBatchId === task.batch_id"
              @click="supplementProductTask(task)"
            >
              {{ t('dataPool.supplementProduct') }}
            </el-button>
            <el-button
              type="danger"
              size="small"
              link
              :loading="deletingBatchId === task.batch_id"
              @click="deleteByBatchTask(task)"
            >
              {{ t('dataPool.deleteBatchData') }}
            </el-button>
            <el-button
              type="danger"
              size="small"
              link
              :loading="deletingTaskId === task.batch_id"
              @click="deleteImportTask(task)"
            >
              {{ t('dataPool.deleteTask') }}
            </el-button>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 导入弹窗 -->
    <el-dialog
      v-model="importVisible"
      :title="t('dataPool.importNumbers')"
      width="580px"
      :close-on-click-modal="false"
    >
      <el-form label-position="top">
        <!-- 第一步：选国家 -->
        <el-form-item label="① 选择国家" required>
          <CountrySelect v-model="importCountryCode" placeholder="先选国家，快速筛选模板" />
        </el-form-item>

        <!-- 第二步：选模板（按国家过滤） -->
        <el-form-item label="② 选择定价模板">
          <el-select
            v-model="selectedTemplateId"
            :placeholder="templateListLoading ? t('dataPool.loadingTemplates') : t('dataPool.templatesCount', { n: filteredTemplates.length })"
            filterable
            clearable
            style="width: 100%"
            @change="onTemplateSelect"
          >
            <!-- 已选国家：分组展示 -->
            <template v-if="importCountryCode">
              <el-option-group
                v-if="countryTemplates.length"
                :label="`${formatCountry(importCountryCode)} 专属模板`"
              >
                <el-option
                  v-for="tpl in countryTemplates"
                  :key="tpl.id"
                  :value="tpl.id"
                  :label="tpl.name"
                >
                  <span>{{ tpl.source_label }}-{{ tpl.purpose_label }}-{{ tpl.freshness_label }}</span>
                  <span style="float: right; color: #67C23A; font-size: 12px; margin-left: 12px">
                    ${{ tpl.price_per_number }}
                  </span>
                </el-option>
              </el-option-group>
              <el-option-group
                v-if="wildcardTemplates.length"
                label="通用模板 (全部国家)"
              >
                <el-option
                  v-for="tpl in wildcardTemplates"
                  :key="tpl.id"
                  :value="tpl.id"
                  :label="tpl.name"
                >
                  <span>{{ tpl.source_label }}-{{ tpl.purpose_label }}-{{ tpl.freshness_label }}</span>
                  <span style="float: right; color: #67C23A; font-size: 12px; margin-left: 12px">
                    ${{ tpl.price_per_number }}
                  </span>
                </el-option>
              </el-option-group>
            </template>
            <!-- 未选国家：平铺展示所有模板 -->
            <template v-else>
              <el-option
                v-for="tpl in templateList"
                :key="tpl.id"
                :value="tpl.id"
                :label="tpl.name"
              >
                <span>{{ formatCountry(tpl.country_code) }} | {{ tpl.source_label }}-{{ tpl.purpose_label }}-{{ tpl.freshness_label }}</span>
                <span style="float: right; color: #67C23A; font-size: 12px; margin-left: 12px">
                  ${{ tpl.price_per_number }}
                </span>
              </el-option>
            </template>
            <el-option
              v-if="!filteredTemplates.length && !templateListLoading"
              :value="-1"
              disabled
              label="暂无可用模板，请先到定价模板页面创建"
            />
          </el-select>
          <div v-if="importCountryCode && !filteredTemplates.length && !templateListLoading" style="color:var(--el-color-warning);font-size:12px;margin-top:4px">
            该国家暂无模板，可清空国家查看全部模板，或到定价模板页面创建
          </div>
        </el-form-item>

        <!-- 选中模板的信息卡 -->
        <el-card v-if="selectedTemplate" shadow="never" class="pricing-match-card" style="margin-bottom: 16px">
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="售价">
              <span style="color:#67C23A;font-weight:600">${{ selectedTemplate.price_per_number }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="成本">
              <span style="color:#F56C6C">${{ selectedTemplate.cost_per_number }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="国家">{{ formatCountry(selectedTemplate.country_code) }}</el-descriptions-item>
            <el-descriptions-item label="来源">{{ selectedTemplate.source_label }}</el-descriptions-item>
            <el-descriptions-item label="用途">{{ selectedTemplate.purpose_label }}</el-descriptions-item>
            <el-descriptions-item label="时效">{{ selectedTemplate.freshness_label }}</el-descriptions-item>
          </el-descriptions>
        </el-card>

        <!-- 第三步：上传文件（支持多文件） -->
        <el-form-item :label="'③ ' + t('dataPool.selectFile') + ' (CSV/TXT，支持多文件)'">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="20"
            multiple
            accept=".csv,.txt"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
            :before-upload="beforeImportUpload"
            drag
          >
            <el-icon style="font-size: 40px; color: var(--el-color-primary)"><UploadFilled /></el-icon>
            <div style="margin-top: 8px">拖拽文件到此处，或点击选择文件</div>
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px">
              支持同时选择多个文件
            </div>
          </el-upload>
          <div class="el-upload__tip">支持 CSV/TXT 格式，最大500MB/文件，自动清洗无效数据</div>
          <div v-if="importFiles.length > 1" style="margin-top: 8px; font-size: 13px; color: var(--el-color-primary); font-weight: 500">
            已选择 {{ importFiles.length }} 个文件，将逐个提交导入任务
          </div>
        </el-form-item>

        <el-divider content-position="left">其他参数（选择模板后自动填充）</el-divider>

        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="t('dataPool.source')" required>
              <el-select v-model="importSourceType" :placeholder="t('dataPool.selectSource')" style="width: 100%">
                <el-option v-for="s in SOURCE_OPTIONS" :key="s.value" :value="s.value" :label="s.label" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('dataPool.purpose')" required>
              <el-select v-model="importPurpose" :placeholder="t('dataPool.selectPurpose')" style="width: 100%">
                <el-option v-for="p in PURPOSE_OPTIONS" :key="p.value" :value="p.value" :label="p.label" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item :label="t('dataPool.freshness')">
              <el-select v-model="importFreshness" placeholder="选择时效" style="width: 100%">
                <el-option v-for="f in FRESHNESS_OPTIONS" :key="f.value" :value="f.value" :label="f.label" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="t('dataPool.dataDate')">
              <el-date-picker v-model="importDataDate" type="date" value-format="YYYY-MM-DD" :placeholder="t('dataPool.selectDataDate')" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="t('dataPool.defaultTags')">
              <el-input v-model="importTags" :placeholder="t('dataPool.defaultTagsPlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row v-if="importCountryCode" :gutter="12">
          <el-col :span="24">
            <el-form-item>
              <el-checkbox v-model="importForceCountry">
                强制使用选定国家：所有号码统一标为「{{ formatCountry(importCountryCode) }}」，不再按区号细分（如 +1 下的美国/加拿大/波多黎各）
              </el-checkbox>
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 任务已提交（支持多文件结果） -->
        <el-card v-if="importResults.length" shadow="never" class="import-result-card">
          <div style="text-align:center;padding:12px 0 8px">
            <el-icon style="font-size:36px;color:var(--el-color-success)"><UploadFilled /></el-icon>
            <div style="margin-top:8px;font-size:16px;font-weight:600;color:var(--el-color-success)">
              {{ importResults.length }} 个导入任务已提交
            </div>
          </div>
          <div class="multi-result-list">
            <div v-for="(r, idx) in importResults" :key="idx" class="multi-result-item" :class="{ 'is-error': r.error }">
              <div class="multi-result-file">
                <el-icon v-if="!r.error" color="#67C23A" :size="16"><UploadFilled /></el-icon>
                <el-icon v-else color="#F56C6C" :size="16"><UploadFilled /></el-icon>
                <span class="multi-result-name">{{ r.file_name }}</span>
              </div>
              <div v-if="!r.error" class="multi-result-info">
                <span>批次号：{{ r.batch_id }}</span>
                <span>{{ r.file_size_mb }}MB</span>
              </div>
              <div v-else class="multi-result-error">{{ r.error }}</div>
            </div>
          </div>
          <div style="text-align:center;margin-top:8px;font-size:12px;color:var(--el-text-color-regular)">
            关闭弹窗后可在下方「导入任务」列表中查看实时进度
          </div>
        </el-card>
      </el-form>
      <template #footer>
        <el-button @click="importVisible = false">{{ importResults.length ? '关闭' : t('common.cancel') }}</el-button>
        <el-button v-if="!importResults.length" type="primary" :loading="importing" @click="submitImport">
          {{ importing ? t('dataPool.submitting', { n: importSubmitIdx, total: importFiles.length }) : (importFiles.length > 1 ? t('dataPool.submitBatch', { n: importFiles.length }) : t('dataPool.startImport')) }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 清空全部 -->
    <el-dialog v-model="clearAllVisible" title="清空全部数据" width="460px" :close-on-click-modal="false">
      <el-alert type="error" :closable="false" show-icon style="margin-bottom:16px">
        <template #title>危险操作</template>
        将删除所有导入任务、号码数据、数据商品，且不可恢复。请谨慎操作。
      </el-alert>
      <el-form label-width="100px">
        <el-form-item label="确认输入" required>
          <el-input
            v-model="clearAllConfirmInput"
            placeholder="请输入 RESET_ALL 以确认"
            clearable
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="clearAllVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="danger" :loading="clearingAll" :disabled="clearAllConfirmInput !== 'RESET_ALL'" @click="handleClearAll">
          确认清空全部
        </el-button>
      </template>
    </el-dialog>

    <!-- 删除国家数据 -->
    <el-dialog v-model="deleteByCountryVisible" title="删除国家数据" width="420px">
      <el-form label-width="100px">
        <el-form-item label="选择国家" required>
          <el-select v-model="deleteCountryCode" placeholder="选择要删除的国家" filterable style="width:100%">
            <el-option
              v-for="(count, code) in (stats.by_country || {})"
              :key="code"
              :label="`${formatCountry(code)} (${(count || 0).toLocaleString()} 条)`"
              :value="code"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deleteByCountryVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="danger" :loading="deletingByCountry" @click="handleDeleteByCountry">
          确认删除
        </el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Refresh } from '@element-plus/icons-vue'
import {
  getNumberStats,
  importNumbersRaw,
  getImportBatches,
  getImportProgress,
  retryImport,
  supplementProductForBatch,
  deleteNumbersByCountry,
  deleteNumbersByBatch,
  deleteImportBatch,
  clearAllData,
  getPricingTemplates,
  type PricingTemplate,
} from '@/api/data-admin'
import CountrySelect from '@/components/CountrySelect.vue'
import { findCountryByIso, findCountryByDial } from '@/constants/countries'

const { t } = useI18n()

function formatCountry(code: string): string {
  if (!code) return '-'
  const c = findCountryByIso(code) || findCountryByDial(code)
  return c ? `${c.name} (+${c.dial})` : code
}

const SOURCE_MAP: Record<string, string> = {
  credential: '撞库', penetration: '渗透', social_eng: '社工库',
  telemarketing: '电销', otp: 'OTP',
}
function sourceLabel(val: string): string {
  return SOURCE_MAP[val] || val
}

const SOURCE_OPTIONS = [
  { value: 'credential', label: '撞库' },
  { value: 'penetration', label: '渗透' },
  { value: 'social_eng', label: '社工库' },
  { value: 'telemarketing', label: '电销' },
  { value: 'otp', label: 'OTP' },
]
const PURPOSE_OPTIONS = [
  { value: 'bc', label: 'BC' },
  { value: 'part_time', label: '兼职' },
  { value: 'dating', label: '交友' },
  { value: 'finance', label: '金融' },
  { value: 'stock', label: '股票' },
]
const FRESHNESS_OPTIONS = [
  { value: '3day', label: '3日内' },
  { value: '7day', label: '7日内' },
  { value: '30day', label: '30日内' },
  { value: 'history', label: '历史' },
]

// 基础状态
const loading = ref(false)
const stats = ref<any>({ total: 0, by_country: {}, by_status: {}, by_source: {} })

const topCountries = computed(() => {
  const obj = stats.value.by_country || {}
  return Object.fromEntries(
    Object.entries(obj).sort((a: any, b: any) => b[1] - a[1]).slice(0, 5)
  )
})
const filters = reactive({ country: '', status: '', tag: '', batch_id: '', source: '', purpose: '' })

// 导入弹窗
const importVisible = ref(false)
const importing = ref(false)
const importFiles = ref<File[]>([])
const importTags = ref('')
const importSource = ref('')
const importSourceType = ref('')
const importPurpose = ref('')
const importFreshness = ref('')
const importDataDate = ref('')
const importForceCountry = ref(false)
const importCountryCode = ref('')
const uploadRef = ref()
const importSubmitIdx = ref(0)

// 定价模板选择
const templateList = ref<PricingTemplate[]>([])
const templateListLoading = ref(false)
const selectedTemplateId = ref<number | null>(null)
const selectedTemplate = ref<PricingTemplate | null>(null)
const importResults = ref<any[]>([])

// 导入任务列表
const importTasks = ref<any[]>([])
const retryingBatchId = ref<string | null>(null)
const supplementingBatchId = ref<string | null>(null)
const deletingBatchId = ref<string | null>(null)
const deletingTaskId = ref<string | null>(null)
const clearAllVisible = ref(false)
const clearAllConfirmInput = ref('')
const clearingAll = ref(false)
const deleteByCountryVisible = ref(false)
const deleteCountryCode = ref('')
const deletingByCountry = ref(false)
let _pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  loadStats()
  loadImportTasks()
})

onUnmounted(() => {
  stopPolling()
})

async function loadStats() {
  try {
    const res = await getNumberStats()
    if (res.success) {
      stats.value = res
    }
  } catch (e) {
    console.error(e)
  }
}

// ====== 导入 ======

async function loadTemplateList() {
  templateListLoading.value = true
  try {
    const res = await getPricingTemplates({ page: 1, page_size: 500, status: 'active' })
    templateList.value = res.items || []
  } catch (e) {
    console.error('加载模板列表失败', e)
    templateList.value = []
  } finally {
    templateListLoading.value = false
  }
}

const countryTemplates = computed(() => {
  if (!importCountryCode.value) return []
  return templateList.value.filter(t => t.country_code === importCountryCode.value)
})

const wildcardTemplates = computed(() => {
  return templateList.value.filter(t => t.country_code === '*')
})

const filteredTemplates = computed(() => {
  if (!importCountryCode.value) return templateList.value
  return [...countryTemplates.value, ...wildcardTemplates.value]
})

watch(importCountryCode, (_new, _old) => {
  if (_old !== undefined && _old !== _new) {
    selectedTemplateId.value = null
    selectedTemplate.value = null
    importSourceType.value = ''
    importPurpose.value = ''
    importFreshness.value = ''
  }
})

function onTemplateSelect(id: number | null) {
  if (!id || id === -1) {
    selectedTemplate.value = null
    selectedTemplateId.value = null
    return
  }
  const tpl = templateList.value.find(t => t.id === id) || null
  selectedTemplate.value = tpl
  if (tpl) {
    importSourceType.value = tpl.source
    importPurpose.value = tpl.purpose
    importFreshness.value = tpl.freshness
    if (tpl.country_code && tpl.country_code !== '*' && !importCountryCode.value) {
      importCountryCode.value = tpl.country_code
    }
  }
}

function showImportDialog() {
  importFiles.value = []
  importTags.value = ''
  importSource.value = ''
  importSourceType.value = ''
  importPurpose.value = ''
  importFreshness.value = ''
  importDataDate.value = ''
  importCountryCode.value = ''
  selectedTemplateId.value = null
  selectedTemplate.value = null
  importResults.value = []
  importSubmitIdx.value = 0
  importVisible.value = true
  loadTemplateList()
}

function beforeImportUpload(file: File) {
  const maxSize = 500 * 1024 * 1024
  if (file.size > maxSize) {
    ElMessage.warning('文件大小不能超过 500MB')
    return false
  }
  return true
}

function handleFileChange(file: any, fileList: any[]) {
  const maxSize = 500 * 1024 * 1024
  if (file.raw && file.raw.size > maxSize) {
    ElMessage.warning(`文件 ${file.name} 大小超过 500MB，已跳过`)
    fileList.splice(fileList.indexOf(file), 1)
    return
  }
  importFiles.value = fileList.map((f: any) => f.raw).filter(Boolean)
}

function handleFileRemove(_file: any, fileList: any[]) {
  importFiles.value = fileList.map((f: any) => f.raw).filter(Boolean)
}

async function submitImport() {
  if (!importFiles.value.length) {
    ElMessage.warning(t('dataPool.pleaseSelectFile'))
    return
  }
  if (!importSourceType.value) {
    ElMessage.warning(t('dataPool.pleaseSelectSource'))
    return
  }
  if (!importPurpose.value) {
    ElMessage.warning(t('dataPool.pleaseSelectPurpose'))
    return
  }
  importing.value = true
  importResults.value = []
  importSubmitIdx.value = 0

  const params: { source: string; purpose: string; data_date?: string; default_tags?: string; freshness?: string; country_code?: string; pricing_template_id?: number } = {
    source: importSourceType.value,
    purpose: importPurpose.value,
  }
  if (importFreshness.value) params.freshness = importFreshness.value
  if (importCountryCode.value) params.country_code = importCountryCode.value
  if (importForceCountry.value) params.force_country = true
  if (importDataDate.value) params.data_date = importDataDate.value
  if (importTags.value) params.default_tags = importTags.value
  if (selectedTemplateId.value) params.pricing_template_id = selectedTemplateId.value

  // 全部使用 raw 流式上传，规避 multipart 解析导致的 Network Error
  let successCount = 0
  for (let i = 0; i < importFiles.value.length; i++) {
    importSubmitIdx.value = i + 1
    const file = importFiles.value[i]
    try {
      const res = await importNumbersRaw(file, params)
      if (res?.success) {
        importResults.value.push({
          file_name: res.file_name || file.name,
          batch_id: res.batch_id,
          file_size_mb: res.file_size_mb,
        })
        successCount++
      } else {
        importResults.value.push({
          file_name: file.name,
          error: (res as any)?.detail || '提交失败',
        })
      }
    } catch (e: any) {
      let errMsg = e?.response?.data?.detail || e?.message
      if (e?.code === 'ECONNABORTED' || errMsg?.includes?.('timeout') || errMsg?.includes?.('Timeout')) {
        errMsg = '上传超时，大文件请使用稳定网络或分批上传'
      } else if (errMsg === 'Network Error' || !errMsg) {
        errMsg = '网络异常，请检查连接或稍后重试'
      }
      importResults.value.push({
        file_name: file.name,
        error: typeof errMsg === 'string' ? errMsg : (errMsg?.[0]?.msg || '提交失败'),
      })
    }
  }

  if (successCount > 0) {
    ElMessage.success(`${successCount} 个导入任务已提交，后台处理中`)
    // 立即刷新任务列表并轮询，确保新提交的任务显示
    importTasks.value = []
    await loadImportTasks()
    startPolling()
  }
  importing.value = false
}

// ====== 导入任务列表 ======

async function loadImportTasks() {
  try {
    const res = await getImportBatches({ page: 1, page_size: 10 })
    if (res?.success && Array.isArray(res.items)) {
      const items = res.items
      if (!importTasks.value.length) {
        importTasks.value = items
      } else {
        for (const item of items) {
          const existing = importTasks.value.find((t: any) => t.batch_id === item.batch_id)
          if (existing) {
            Object.assign(existing, item)
          } else {
            importTasks.value.unshift(item)
          }
        }
        importTasks.value = importTasks.value.filter((t: any) =>
          items.some((i: any) => i.batch_id === t.batch_id)
        )
      }
      checkPolling()
    }
  } catch (e) {
    console.error('加载导入任务失败', e)
  }
}

async function pollRunningTasks() {
  let anyChanged = false
  for (const task of importTasks.value) {
    if (task.status === 'pending' || task.status === 'processing') {
      try {
        const res = await getImportProgress(task.batch_id)
        if (!res.success) continue
        task._progress = res
        if (res.status === 'completed') {
          task.status = 'completed'
          task.valid_count = res.valid_count
          task.total_count = res.total_count
          task.duplicate_count = res.duplicate_count
          task.invalid_count = res.invalid_count
          anyChanged = true
        } else if (res.status === 'failed') {
          task.status = 'failed'
          anyChanged = true
        }
      } catch { /* ignore */ }
    }
  }
  if (anyChanged) loadStats()
  checkPolling()
}

function checkPolling() {
  const hasRunning = importTasks.value.some(t =>
    t.status === 'pending' || t.status === 'processing'
  )
  if (hasRunning && !_pollTimer) {
    _pollTimer = setInterval(() => pollRunningTasks(), 3000)
  }
  if (!hasRunning && _pollTimer) {
    clearInterval(_pollTimer)
    _pollTimer = null
  }
}

function startPolling() {
  if (!_pollTimer) {
    _pollTimer = setInterval(() => pollRunningTasks(), 3000)
  }
}

function stopPolling() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null }
}

function formatDate(val: string | null) {
  if (!val) return '-'
  return val.replace('T', ' ').slice(0, 19)
}

function isTaskRunning(task: any): boolean {
  // 仅 Worker 已接管并真正处理时显示「处理中」；pending 显示「等待中」
  const s = task._progress?.status || task.status
  return s === 'processing'
}

function canRetryTask(task: any): boolean {
  return task.status === 'pending' || task.status === 'failed'
}

function canSupplementProduct(task: any): boolean {
  if (task.status !== 'completed') return false
  const valid = task._progress?.valid_count ?? task.valid_count ?? 0
  const dup = (task._progress?.duplicate_count ?? task.duplicate_count ?? 0) + (task._progress?.file_dedup_count ?? task.file_dedup_count ?? 0)
  return valid === 0 && dup > 0
}

function showDeleteByCountryDialog() {
  deleteCountryCode.value = ''
  deleteByCountryVisible.value = true
}

function showClearAllDialog() {
  clearAllConfirmInput.value = ''
  clearAllVisible.value = true
}

async function handleClearAll() {
  if (clearAllConfirmInput.value !== 'RESET_ALL') return
  clearingAll.value = true
  try {
    const res: any = await clearAllData()
    if (res?.success) {
      ElMessage.success(res.message || '已清空全部')
      clearAllVisible.value = false
      loadStats()
      loadImportTasks()
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '清空失败')
  } finally {
    clearingAll.value = false
  }
}

async function handleDeleteByCountry() {
  if (!deleteCountryCode.value) {
    ElMessage.warning('请选择国家')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除「${formatCountry(deleteCountryCode.value)}」的全部号码数据？此操作不可恢复。`,
      '确认删除',
      { type: 'warning' }
    )
  } catch {
    return
  }
  deletingByCountry.value = true
  try {
    const res = await deleteNumbersByCountry(deleteCountryCode.value)
    if (res?.success) {
      ElMessage.success(res.message || `已删除 ${res.deleted ?? 0} 条`)
      deleteByCountryVisible.value = false
      loadStats()
      loadImportTasks()
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  } finally {
    deletingByCountry.value = false
  }
}

async function supplementProductTask(task: any) {
  if (!task.batch_id) return
  supplementingBatchId.value = task.batch_id
  try {
    const res = await supplementProductForBatch(task.batch_id)
    if (res?.success) {
      ElMessage.success(res.message || '商品已补充')
      loadImportTasks()
      loadStats()
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '补充失败')
  } finally {
    supplementingBatchId.value = null
  }
}

async function retryImportTask(task: any) {
  if (!task.batch_id) return
  retryingBatchId.value = task.batch_id
  try {
    const res = await retryImport(task.batch_id)
    if (res?.success) {
      ElMessage.success(res.message || '已重新提交')
      task.status = 'pending'
      delete task._progress
      loadImportTasks()
      startPolling()
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '重新提交失败')
  } finally {
    retryingBatchId.value = null
  }
}

async function deleteByBatchTask(task: any) {
  if (!task.batch_id) return
  try {
    await ElMessageBox.confirm(`确定删除批次 ${task.batch_id} 下的所有号码数据？此操作不可恢复。`, '确认删除', { type: 'warning' })
    deletingBatchId.value = task.batch_id
    const res = await deleteNumbersByBatch(task.batch_id)
    if (res?.success) {
      ElMessage.success(res.message || `已删除 ${res.deleted ?? 0} 条号码`)
      loadImportTasks()
      loadStats()
    }
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  } finally {
    deletingBatchId.value = null
  }
}

async function deleteImportTask(task: any) {
  if (!task.batch_id) return
  try {
    await ElMessageBox.confirm(
      `确定删除导入任务「${task.file_name || task.batch_id}」？将同时删除该批次的号码数据，此操作不可恢复。`,
      '确认删除任务',
      { type: 'warning' }
    )
    deletingTaskId.value = task.batch_id
    const res = await deleteImportBatch(task.batch_id)
    if (res?.success) {
      ElMessage.success(res.message || '任务已删除')
      // 直接移除本地任务并刷新，确保等待中/处理中任务也能立即消失
      importTasks.value = importTasks.value.filter((t: any) => t.batch_id !== task.batch_id)
      loadImportTasks()
      loadStats()
    }
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  } finally {
    deletingTaskId.value = null
  }
}

function formatElapsed(sec?: number): string {
  if (!sec && sec !== 0) return '-'
  if (sec < 60) return `${Math.round(sec)}秒`
  if (sec < 3600) return `${Math.floor(sec / 60)}分${Math.round(sec % 60)}秒`
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  return `${h}时${m}分`
}

const progressColors = [
  { color: '#909399', percentage: 10 },
  { color: '#E6A23C', percentage: 40 },
  { color: '#409EFF', percentage: 70 },
  { color: '#67C23A', percentage: 100 },
]

</script>

<style scoped>
.numbers-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.action-card :deep(.el-card__body) {
  padding: 20px 24px;
}

.stats-row {
  margin-bottom: 0;
}

.stat-card {
  text-align: center;
}

.tasks-card {
  margin-top: 0;
}

/* ====== 任务列表卡片式设计 ====== */


.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 16px;
  transition: box-shadow 0.2s;
  background: var(--el-bg-color);
}
.task-item:hover {
  box-shadow: 0 2px 12px rgba(0,0,0,0.06);
}
.task-item.task-processing,
.task-item.task-pending {
  border-left: 3px solid var(--el-color-warning);
  background: var(--el-fill-color-light);
}
.task-item.task-completed {
  border-left: 3px solid var(--el-color-success);
}
.task-item.task-failed {
  border-left: 3px solid var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.task-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.task-file {
  display: flex;
  align-items: center;
  gap: 4px;
}
.task-filename {
  font-weight: 600;
  font-size: 14px;
  color: var(--el-text-color-primary);
}
.task-source {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: 8px;
  background: var(--el-fill-color);
  padding: 1px 8px;
  border-radius: 10px;
}

.task-status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.status-dot.completed { background: var(--el-color-success); }
.status-dot.failed { background: var(--el-color-danger); }
.status-dot.pending { background: var(--el-text-color-placeholder); }
.status-text.processing { color: var(--el-color-warning); }
.status-text.completed { color: var(--el-color-success); }
.status-text.failed { color: var(--el-color-danger); }
.status-text.pending { color: var(--el-text-color-placeholder); }

/* 进度区域 */
.task-progress-area {
  margin-top: 12px;
}
.progress-bar-row {
  margin-bottom: 8px;
}
.progress-bar-row :deep(.el-progress-bar__inner) {
  transition: width 1s ease;
}
.progress-phase {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 10px;
}
.progress-metrics {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.metric {
  flex: 1;
  min-width: 90px;
  text-align: center;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  padding: 8px 4px;
}
.metric-value {
  display: block;
  font-size: 16px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  font-variant-numeric: tabular-nums;
}
.metric-label {
  display: block;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}
.highlight-green { color: var(--el-color-success) !important; }
.highlight-orange { color: var(--el-color-warning) !important; }
.highlight-red { color: var(--el-color-danger) !important; }
.highlight-blue { color: var(--el-color-primary) !important; }

/* 完成结果行 */
.task-result-row {
  margin-top: 8px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.result-item b {
  font-weight: 700;
}
.result-sep {
  color: var(--el-border-color);
  margin: 0 2px;
}
.task-error {
  color: var(--el-color-danger);
  font-size: 12px;
}

/* 底部信息 */
.task-footer {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
.task-batch-id {
  font-family: 'Courier New', Courier, monospace;
}

/* ====== 以下保留原有样式 ====== */

/* 定价信息卡：使用主题变量确保夜间模式适配 */
.pricing-match-card {
  margin-bottom: 8px;
  background: var(--bg-input) !important;
  border: 1px solid var(--border-default);
}

.pricing-match-card :deep(.el-card__header),
.pricing-match-card :deep(.el-card__body) {
  padding: 8px 12px;
  background: var(--bg-input) !important;
}

.pricing-match-card :deep(.el-descriptions__label),
.pricing-match-card :deep(.el-descriptions__content) {
  background: var(--bg-input) !important;
  color: var(--text-primary) !important;
  border-color: var(--border-subtle) !important;
}

.import-result-card {
  margin-top: 8px;
  border-color: var(--el-color-success-light-5);
  background: var(--el-color-success-light-9);
}

.import-result-card :deep(.el-card__header) {
  padding: 8px 12px;
  background: var(--el-color-success-light-7);
}

.import-result-card :deep(.el-card__body) {
  padding: 8px 12px;
}

/* 多文件结果列表 */
.multi-result-list {
  max-height: 240px;
  overflow-y: auto;
  margin: 8px 0;
}

.multi-result-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--el-color-success-light-9);
  margin-bottom: 6px;
  font-size: 13px;
  gap: 12px;
}

.multi-result-item.is-error {
  background: var(--el-color-danger-light-9);
}

.multi-result-file {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.multi-result-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.multi-result-info {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.multi-result-error {
  font-size: 12px;
  color: var(--el-color-danger);
  flex-shrink: 0;
}
</style>
