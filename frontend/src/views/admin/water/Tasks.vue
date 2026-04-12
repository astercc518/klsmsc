<template>
  <div class="water-tasks">
    <!-- 概览统计：响应式栅格 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="12" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-value">{{ globalStats.today_clicks }}</div>
          <div class="stat-label">今日点击</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-value">{{ globalStats.today_registers }}</div>
          <div class="stat-label">今日注册</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <div class="stat-card stat-card--ok">
          <div class="stat-value">{{ globalStats.click_success_rate }}%</div>
          <div class="stat-label">点击成功率</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <div class="stat-card stat-card--ok">
          <div class="stat-value">{{ globalStats.register_success_rate }}%</div>
          <div class="stat-label">注册成功率</div>
        </div>
      </el-col>
    </el-row>

    <!-- 工具条：与表格分离，层次更清晰 -->
    <div class="toolbar-card">
      <div class="toolbar-left">
        <el-button type="primary" @click="openDialog()">新增配置</el-button>
      </div>
      <div class="toolbar-right">
        <span class="queue-label" :class="{ 'is-busy': queuePending > 0 }">
          队列待执行：<strong>{{ queuePending }}</strong> 条
          <span v-if="queueConsumers > 0" class="queue-consumers">· {{ queueConsumers }} 个消费者</span>
        </span>
        <el-button size="small" :loading="queueLoading" @click="loadQueueStats">刷新队列</el-button>
        <el-button size="small" type="danger" plain :loading="purging" @click="handlePurgeQueue">清空全队列</el-button>
      </div>
    </div>

    <div class="table-wrap">
      <el-table
        :data="tableData"
        v-loading="loading"
        stripe
        border
        class="water-task-table"
        style="width: 100%"
        :header-cell-style="{ textAlign: 'center' }"
      >
        <el-table-column label="客户与批次" min-width="260" fixed="left">
          <template #default="{ row }">
            <div class="cell-account">
              <div class="cell-acct-row">
                <span class="cell-acct-k">客户账户</span>
                <span class="cell-acct-v" :title="row.account_name">{{ row.account_name }}</span>
                <span class="cell-acct-id muted">#{{ row.account_id }}</span>
              </div>
              <div class="cell-acct-row">
                <span class="cell-acct-k">国家</span>
                <el-tag v-if="row.account_country_code" size="small" type="info" class="country-tag">
                  {{ countryName(row.account_country_code) }}
                </el-tag>
                <span v-else class="cell-acct-v muted">未设置</span>
              </div>
              <div class="cell-acct-row">
                <span class="cell-acct-k">员工</span>
                <span v-if="row.account_staff_name" class="cell-acct-v">{{ row.account_staff_name }}</span>
                <span v-else class="cell-acct-v muted">未分配</span>
              </div>
              <div class="cell-batch-line">
                <template v-if="(row.water_distinct_batches || 0) > 0">
                  已关联 <strong>{{ row.water_distinct_batches }}</strong> 个发送批次
                </template>
                <span v-else class="muted">尚无批次注水记录</span>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="78" align="center" fixed="left">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="点击策略" align="center">
          <el-table-column label="点击率 %" width="102" align="center">
            <template #default="{ row }">
              <span class="mono-range">{{ row.click_rate_min }} ~ {{ row.click_rate_max }}</span>
            </template>
          </el-table-column>
          <el-table-column label="延迟 / 曲线" min-width="168" align="center">
            <template #default="{ row }">
              <div class="cell-delay">
                <div>{{ formatDelay(row.click_delay_min) }} ~ {{ formatDelay(row.click_delay_max) }}</div>
                <el-tag size="small" :type="row.click_delay_curve >= 4 ? 'success' : 'info'">{{ curveLabel(row.click_delay_curve) }}</el-tag>
              </div>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="注册策略" align="center">
          <el-table-column label="开关" width="72" align="center">
            <template #default="{ row }">
              <el-tag :type="row.register_enabled ? 'success' : 'info'" size="small">{{ row.register_enabled ? '开' : '关' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="注册率 %" width="102" align="center">
            <template #default="{ row }">
              <span class="mono-range">{{ row.register_rate_min }} ~ {{ row.register_rate_max }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="代理" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.proxy_name || '—' }}</template>
        </el-table-column>

        <el-table-column label="今日效果" align="center">
          <el-table-column label="点击" width="76" align="center">
            <template #default="{ row }"><span class="stat-num">{{ row.today_clicks }}</span></template>
          </el-table-column>
          <el-table-column label="注册" width="76" align="center">
            <template #default="{ row }"><span class="stat-num">{{ row.today_registers }}</span></template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="操作" width="208" fixed="right" align="center">
          <template #default="{ row }">
            <div class="op-btns">
              <el-button type="primary" size="small" @click="openProgressDrawer(row)">发送进度</el-button>
              <el-button size="small" @click="openDialog(row)">编辑</el-button>
              <el-dropdown trigger="click" @command="(c: string) => onRowCommand(c, row)">
                <el-button size="small">
                  更多
                  <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="toggle">{{ row.enabled ? '停用' : '启用' }}</el-dropdown-item>
                    <el-dropdown-item command="revoke" divided>撤本账户队列</el-dropdown-item>
                    <el-dropdown-item command="delete" class="dropdown-danger">删除配置</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 分页 -->
    <div class="pagination-wrap">
      <el-pagination background layout="total, prev, pager, next" :total="total" :page-size="pageSize" v-model:current-page="currentPage" @current-change="loadData" />
    </div>

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑注水配置' : '新增注水配置'" width="640px" destroy-on-close class="water-task-dialog">
      <el-form :model="form" label-width="110px">
        <el-form-item label="客户账户" required>
          <el-select v-model="form.account_id" placeholder="选择客户账户" filterable style="width: 100%" :disabled="!!editingId">
            <el-option v-for="a in accountList" :key="a.id" :label="a.account_name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用注水">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-divider content-position="left">点击配置</el-divider>
        <el-form-item label="点击率 (%)">
          <div style="display: flex; gap: 10px; align-items: center">
            <el-input-number v-model="form.click_rate_min" :min="0" :max="100" :precision="1" size="small" />
            <span>~</span>
            <el-input-number v-model="form.click_rate_max" :min="0" :max="100" :precision="1" size="small" />
          </div>
        </el-form-item>
        <el-form-item label="延迟范围">
          <div style="display: flex; gap: 10px; align-items: center">
            <el-input-number v-model="form.click_delay_min" :min="10" :step="30" size="small" />
            <span>秒 ~</span>
            <el-input-number v-model="form.click_delay_max" :min="60" :step="1800" size="small" />
            <span>秒</span>
          </div>
          <div class="form-tip">建议范围：最小 30 秒 ~ 最大 4~8 小时（{{ formatDelay(form.click_delay_min) }} ~ {{ formatDelay(form.click_delay_max) }}）</div>
        </el-form-item>
        <el-form-item label="延迟曲线" class="form-item-curve">
          <div class="curve-block">
            <div class="curve-preset-bar">
              <span class="curve-preset-hint muted">快捷预设</span>
              <div class="curve-preset-btns">
                <el-button
                  v-for="p in curvePresets"
                  :key="p.value"
                  size="small"
                  :type="isCurvePresetActive(p.value) ? 'primary' : 'default'"
                  plain
                  @click="form.click_delay_curve = p.value"
                >
                  {{ p.label }}
                </el-button>
              </div>
            </div>
            <div class="curve-slider-row">
              <span class="curve-slider-hint muted">细调 1～10（步进 0.5）</span>
              <el-slider
                v-model="form.click_delay_curve"
                :min="1"
                :max="10"
                :step="0.5"
                :format-tooltip="formatCurveTooltip"
                class="curve-slider"
              />
            </div>
            <div class="curve-current-line">
              <span class="muted">当前</span>
              <el-tag size="small" type="info" effect="plain" class="curve-current-tag">{{ curveLabel(form.click_delay_curve) }}</el-tag>
              <span class="muted">数值</span>
              <strong class="curve-current-num">{{ form.click_delay_curve }}</strong>
            </div>
            <div class="curve-desc-box">
              <template v-if="form.click_delay_curve <= 1.5">均匀分布：点击在延迟范围内均匀分散。</template>
              <template v-else-if="form.click_delay_curve <= 3.0">轻度前倾：约 50% 点击集中在前 1/3 时段。</template>
              <template v-else-if="form.click_delay_curve <= 5.0">自然曲线（推荐）：约 60% 点击集中在前 1/4，模拟真实用户行为。</template>
              <template v-else>极度前倾：约 80% 点击集中在最初时段，适合快速起量。</template>
            </div>
          </div>
        </el-form-item>
        <el-divider content-position="left">注册配置</el-divider>
        <el-form-item label="启用自动注册">
          <el-switch v-model="form.register_enabled" />
        </el-form-item>
        <el-form-item label="注册率 (%)" v-show="form.register_enabled">
          <div style="display: flex; gap: 10px; align-items: center">
            <el-input-number v-model="form.register_rate_min" :min="0" :max="100" :precision="1" size="small" />
            <span>~</span>
            <el-input-number v-model="form.register_rate_max" :min="0" :max="100" :precision="1" size="small" />
          </div>
        </el-form-item>
        <el-divider content-position="left">其他</el-divider>
        <el-form-item label="代理">
          <el-select v-model="form.proxy_id" placeholder="选择代理" clearable style="width: 100%">
            <el-option v-for="p in proxyList" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="UA 类型">
          <el-select v-model="form.user_agent_type" style="width: 100%">
            <el-option label="移动端" value="mobile" />
            <el-option label="桌面端" value="desktop" />
            <el-option label="随机" value="random" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 按发送任务（批次）查看注水进度 -->
    <el-drawer v-model="progressDrawerVisible" :title="progressDrawerTitle" size="92%" destroy-on-close @opened="onProgressDrawerOpened">
      <div v-loading="progressLoading" class="progress-drawer-body">
        <div class="progress-drawer-toolbar">
          <el-button type="primary" size="small" plain :loading="progressLoading" @click="loadBatchProgress">刷新</el-button>
          <span class="toolbar-meta muted">该账户共 <strong class="toolbar-meta-num">{{ progressTotal }}</strong> 个发送批次</span>
        </div>

        <el-collapse v-model="progressLegendActive" class="progress-legend">
          <el-collapse-item title="指标说明（点击展开）" name="legend">
            <ul class="progress-legend-list">
              <li>下列为各「发送批次」在本注水配置下的执行情况；数字来自注水执行记录。</li>
              <li><strong>点击完成度</strong>：（点击成功 + 点击失败）÷ 点击任务总数。</li>
              <li><strong>注册完成度</strong>：（注册成功 + 注册失败）÷ 注册任务总数。</li>
              <li><strong>注水/发送</strong>：已产生的注水点击任务数 ÷ 该批次发送成功数（受点击率随机影响，仅供参考）。</li>
            </ul>
          </el-collapse-item>
        </el-collapse>

        <el-row v-if="progressRows.length" :gutter="12" class="progress-summary-row">
          <el-col :xs="12" :sm="6">
            <div class="progress-summary-card">
              <div class="progress-summary-value">{{ progressPageSummary.batches }}</div>
              <div class="progress-summary-label">本页批次数</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="6">
            <div class="progress-summary-card">
              <div class="progress-summary-value">{{ progressPageSummary.clickTotal }}</div>
              <div class="progress-summary-label">本页点击任务</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="6">
            <div class="progress-summary-card">
              <div class="progress-summary-value">{{ progressPageSummary.clickSuccess }}</div>
              <div class="progress-summary-label">本页点击成功</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="6">
            <div class="progress-summary-card">
              <div class="progress-summary-value">{{ progressPageSummary.regSuccess }} / {{ progressPageSummary.regTotal }}</div>
              <div class="progress-summary-label">本页注册成功 / 任务</div>
            </div>
          </el-col>
        </el-row>

        <el-empty
          v-if="!progressLoading && progressRows.length === 0"
          :description="progressTotal === 0 ? '该客户账户尚无发送批次' : '本页无数据'"
          class="progress-empty"
        />

        <div v-else class="progress-table-wrap">
          <el-table
            :data="progressRows"
            stripe
            border
            size="small"
            class="progress-batch-table"
            style="width: 100%"
            :header-cell-style="{ textAlign: 'center' }"
          >
            <el-table-column label="批次与任务" min-width="216" fixed="left">
              <template #default="{ row }">
                <div class="cell-batch">
                  <div class="cell-batch-head">
                    <span class="cell-batch-id">#{{ row.batch_id }}</span>
                    <el-tag size="small" :type="batchStatusTag(row.batch_status)">{{ batchStatusLabel(row.batch_status) }}</el-tag>
                  </div>
                  <div class="cell-batch-name" :title="row.batch_name">{{ row.batch_name || '—' }}</div>
                  <div class="cell-batch-times muted">
                    <div>创建 {{ formatBatchTime(row.batch_created_at) }}</div>
                    <div v-if="row.batch_completed_at">完成 {{ formatBatchTime(row.batch_completed_at) }}</div>
                  </div>
                </div>
              </template>
            </el-table-column>

            <el-table-column label="发送" align="center" width="96">
              <template #default="{ row }">
                <div class="cell-send">
                  <div>成功 <span class="cell-num">{{ row.send_success ?? 0 }}</span></div>
                  <div class="muted tiny">计划 {{ row.send_total ?? 0 }}</div>
                </div>
              </template>
            </el-table-column>

            <el-table-column label="注水 · 点击" align="center">
              <el-table-column label="任务" width="68" align="center">
                <template #default="{ row }"><span class="cell-num">{{ row.water_click_total ?? 0 }}</span></template>
              </el-table-column>
              <el-table-column label="成功" width="64" align="center">
                <template #default="{ row }"><span class="cell-num ok">{{ row.water_click_success ?? 0 }}</span></template>
              </el-table-column>
              <el-table-column label="失败" width="64" align="center">
                <template #default="{ row }"><span class="cell-num bad">{{ row.water_click_failed ?? 0 }}</span></template>
              </el-table-column>
              <el-table-column label="进行中" width="72" align="center">
                <template #default="{ row }">{{ row.water_click_in_progress ?? 0 }}</template>
              </el-table-column>
              <el-table-column label="完成度" min-width="132" align="center">
                <template #default="{ row }">
                  <template v-if="(row.water_click_total || 0) > 0">
                    <el-progress
                      :percentage="Math.min(100, Number(row.water_click_finished_rate) || 0)"
                      :stroke-width="7"
                      :status="row.water_click_finished_rate >= 100 ? 'success' : undefined"
                    />
                    <div class="muted tiny progress-sub">
                      {{ (row.water_click_success || 0) + (row.water_click_failed || 0) }} / {{ row.water_click_total }} 已终结
                    </div>
                  </template>
                  <span v-else class="muted">—</span>
                </template>
              </el-table-column>
            </el-table-column>

            <el-table-column label="注水 · 注册" align="center">
              <el-table-column label="任务" width="64" align="center">
                <template #default="{ row }"><span class="cell-num">{{ row.water_register_total ?? 0 }}</span></template>
              </el-table-column>
              <el-table-column label="成功" width="64" align="center">
                <template #default="{ row }"><span class="cell-num ok">{{ row.water_register_success ?? 0 }}</span></template>
              </el-table-column>
              <el-table-column label="失败" width="64" align="center">
                <template #default="{ row }"><span class="cell-num bad">{{ row.water_register_failed ?? 0 }}</span></template>
              </el-table-column>
              <el-table-column label="进行中" width="72" align="center">
                <template #default="{ row }">{{ row.water_register_in_progress ?? 0 }}</template>
              </el-table-column>
              <el-table-column label="完成度" min-width="120" align="center">
                <template #default="{ row }">
                  <template v-if="(row.water_register_total || 0) > 0">
                    <el-progress
                      :percentage="registerFinishedPct(row)"
                      :stroke-width="7"
                      :status="registerFinishedPct(row) >= 100 ? 'success' : undefined"
                    />
                    <div class="muted tiny progress-sub">
                      {{ (row.water_register_success || 0) + (row.water_register_failed || 0) }} / {{ row.water_register_total }} 已终结
                    </div>
                  </template>
                  <span v-else class="muted">—</span>
                </template>
              </el-table-column>
            </el-table-column>

            <el-table-column align="center" width="104" fixed="right">
              <template #header>
                <el-tooltip content="注水点击任务数 ÷ 该批次发送成功数（受点击率随机影响，仅供参考）" placement="top">
                  <span>注水/发送</span>
                </el-tooltip>
              </template>
              <template #default="{ row }">
                <span v-if="row.water_vs_send_success_rate != null" class="cell-num cover">{{ row.water_vs_send_success_rate }}%</span>
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="progress-pagination">
          <el-pagination
            background
            layout="total, prev, pager, next"
            :total="progressTotal"
            :page-size="progressPageSize"
            v-model:current-page="progressPage"
            @current-change="loadBatchProgress"
          />
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import {
  getTasks,
  getTaskStats,
  createTask,
  updateTask,
  toggleTask,
  deleteTask,
  getProxies,
  getWaterAccounts,
  getWaterQueueStats,
  purgeWaterQueue,
  getAccountPendingTracked,
  revokeAccountWaterPending,
  getTaskBatchProgress,
} from '@/api/water'

const { tm } = useI18n()
const countriesMap = tm('countries') as Record<string, string>
const countryName = (code: string) => {
  if (!code) return ''
  const upper = String(code).toUpperCase()
  return countriesMap?.[upper] || upper
}

const onRowCommand = (cmd: string, row: any) => {
  if (cmd === 'toggle') handleToggle(row)
  else if (cmd === 'revoke') handleRevokeAccountQueue(row)
  else if (cmd === 'delete') handleDelete(row)
}

/** 与后端 WATER_QUEUE_PURGE_CONFIRM_PHRASE 保持一致 */
const PURGE_QUEUE_PHRASE = '清空注水队列'

const loading = ref(false)
const submitting = ref(false)
const tableData = ref<any[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const accountList = ref<any[]>([])
const proxyList = ref<any[]>([])
const globalStats = ref({ today_clicks: 0, today_registers: 0, click_success_rate: 0, register_success_rate: 0 })
const queuePending = ref(0)
const queueConsumers = ref(0)
const queueLoading = ref(false)
const purging = ref(false)

const progressDrawerVisible = ref(false)
const progressDrawerTitle = ref('')
const progressTaskConfigId = ref<number | null>(null)
const progressLoading = ref(false)
const progressRows = ref<any[]>([])
const progressTotal = ref(0)
const progressPage = ref(1)
const progressPageSize = 20
/** 进度抽屉内「指标说明」折叠，默认收起避免占屏 */
const progressLegendActive = ref<string[]>([])

const progressPageSummary = computed(() => {
  let batches = 0
  let clickTotal = 0
  let clickSuccess = 0
  let regTotal = 0
  let regSuccess = 0
  for (const r of progressRows.value) {
    batches += 1
    clickTotal += r.water_click_total ?? 0
    clickSuccess += r.water_click_success ?? 0
    regTotal += r.water_register_total ?? 0
    regSuccess += r.water_register_success ?? 0
  }
  return { batches, clickTotal, clickSuccess, regTotal, regSuccess }
})

const form = reactive({
  account_id: null as number | null,
  enabled: false,
  click_rate_min: 3.0,
  click_rate_max: 8.0,
  click_delay_min: 60,
  click_delay_max: 14400,
  click_delay_curve: 4.0,
  register_enabled: false,
  register_rate_min: 1.0,
  register_rate_max: 3.0,
  proxy_id: null as number | null,
  user_agent_type: 'mobile',
})

/** 与后端 Beta 曲线语义对应的四个常用锚点（避免滑块刻度文字与拖块重叠） */
const curvePresets = [
  { value: 1, label: '均匀' },
  { value: 4, label: '自然' },
  { value: 7, label: '快速' },
  { value: 10, label: '极速' },
]

const isCurvePresetActive = (v: number) => Math.abs(form.click_delay_curve - v) < 0.01

const formatCurveTooltip = (val: number) => `${curveLabel(val)}（${val}）`

const formatDelay = (seconds: number) => {
  if (!seconds) return '0s'
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return m > 0 ? `${h}小时${m}分` : `${h}小时`
}

/** 与快捷预设 1/4/7/10 及中间细调值对应的展示文案 */
const curveLabel = (curve: number) => {
  if (!curve || curve <= 1.5) return '均匀'
  if (curve <= 3.0) return '轻倾'
  if (curve <= 5.0) return '自然'
  if (curve <= 8.5) return '快速'
  return '极速'
}

const batchStatusLabel = (s: string) => {
  const m: Record<string, string> = {
    pending: '待处理',
    processing: '处理中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return m[s] || s || '-'
}

const batchStatusTag = (s: string) => {
  const m: Record<string, string> = {
    pending: 'info',
    processing: 'warning',
    completed: 'success',
    failed: 'danger',
    cancelled: 'info',
  }
  return (m[s] || 'info') as 'success' | 'warning' | 'info' | 'danger'
}

/** 批次时间展示（接口多为 ISO 字符串） */
const formatBatchTime = (iso: string | null | undefined) => {
  if (!iso) return '—'
  return String(iso).replace('T', ' ').slice(0, 19)
}

/** 注册侧完成百分比（成功+失败）/ 任务总数，与后端点击完成率口径一致 */
const registerFinishedPct = (row: any) => {
  const t = row.water_register_total ?? 0
  if (t <= 0) return 0
  const done = (row.water_register_success ?? 0) + (row.water_register_failed ?? 0)
  return Math.min(100, Math.round((done / t) * 1000) / 10)
}

const openProgressDrawer = (row: any) => {
  progressTaskConfigId.value = row.id
  progressDrawerTitle.value = `发送任务注水进度 — ${row.account_name}（配置#${row.id}）`
  progressPage.value = 1
  progressDrawerVisible.value = true
}

const loadBatchProgress = async () => {
  const tid = progressTaskConfigId.value
  if (!tid) return
  progressLoading.value = true
  try {
    const res: any = await getTaskBatchProgress(tid, {
      page: progressPage.value,
      page_size: progressPageSize,
    })
    progressRows.value = res.items || []
    progressTotal.value = res.total || 0
  } catch (e: any) {
    console.error(e)
    progressRows.value = []
    const msg = e?.response?.data?.detail || e?.message || '加载批次进度失败'
    ElMessage.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  } finally {
    progressLoading.value = false
  }
}

const onProgressDrawerOpened = () => {
  loadBatchProgress()
}

const loadData = async () => {
  loading.value = true
  try {
    const [tasksRes, statsRes]: any[] = await Promise.all([
      getTasks({ page: currentPage.value, page_size: pageSize }),
      getTaskStats(),
    ])
    tableData.value = tasksRes.items || []
    total.value = tasksRes.total || 0
    globalStats.value = statsRes
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const loadOptions = async () => {
  try {
    const [acctRes, pxRes]: any[] = await Promise.all([
      getWaterAccounts(),
      getProxies({ page: 1, page_size: 100 }),
    ])
    accountList.value = acctRes || []
    proxyList.value = pxRes.items || []
  } catch (e) {
    console.error(e)
  }
}

const loadQueueStats = async () => {
  queueLoading.value = true
  try {
    const r: any = await getWaterQueueStats()
    queuePending.value = r.pending_messages ?? 0
    queueConsumers.value = r.consumers ?? 0
  } catch (e) {
    console.error(e)
  } finally {
    queueLoading.value = false
  }
}

const handlePurgeQueue = async () => {
  await loadQueueStats()
  if (queuePending.value <= 0) {
    ElMessage.info('当前队列为空，无需清空')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将丢弃 RabbitMQ 队列「web_automation」中全部 ${queuePending.value} 条尚未被 worker 取走的注水任务，不可恢复。\n` +
        `已在执行中的任务无法取消；注水记录里「处理中」状态不会自动变更。\n\n` +
        `下一步请在弹窗中输入口令：${PURGE_QUEUE_PHRASE}`,
      '危险操作：清空注水队列',
      { type: 'warning', confirmButtonText: '继续', cancelButtonText: '取消' }
    )
    const { value } = await ElMessageBox.prompt(
      `请输入口令（完全一致）：`,
      '确认清空',
      {
        confirmButtonText: '确认清空',
        cancelButtonText: '取消',
        inputPlaceholder: PURGE_QUEUE_PHRASE,
        inputValidator: (v) => {
          if (!v || v.trim() !== PURGE_QUEUE_PHRASE) return '口令不正确'
          return true
        },
      }
    )
    if (value.trim() !== PURGE_QUEUE_PHRASE) return
    purging.value = true
    const res: any = await purgeWaterQueue(PURGE_QUEUE_PHRASE)
    ElMessage.success(res.message || `已丢弃 ${res.purged} 条`)
    await loadQueueStats()
  } catch (e: any) {
    if (e !== 'cancel' && e !== 'close') {
      const msg = e?.response?.data?.detail || e?.message || '操作失败'
      ElMessage.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }
  } finally {
    purging.value = false
  }
}

const openDialog = (row?: any) => {
  if (row) {
    editingId.value = row.id
    Object.assign(form, {
      account_id: row.account_id,
      enabled: row.enabled,
      click_rate_min: row.click_rate_min,
      click_rate_max: row.click_rate_max,
      click_delay_min: row.click_delay_min,
      click_delay_max: row.click_delay_max,
      click_delay_curve: row.click_delay_curve || 4.0,
      register_enabled: row.register_enabled,
      register_rate_min: row.register_rate_min,
      register_rate_max: row.register_rate_max,
      proxy_id: row.proxy_id,
      user_agent_type: row.user_agent_type || 'mobile',
    })
  } else {
    editingId.value = null
    Object.assign(form, {
      account_id: null, enabled: false,
      click_rate_min: 3.0, click_rate_max: 8.0,
      click_delay_min: 60, click_delay_max: 14400, click_delay_curve: 4.0,
      register_enabled: false, register_rate_min: 1.0, register_rate_max: 3.0,
      proxy_id: null, user_agent_type: 'mobile',
    })
  }
  dialogVisible.value = true
}

const handleSubmit = async () => {
  if (!form.account_id) {
    ElMessage.warning('请选择客户账户')
    return
  }
  submitting.value = true
  try {
    if (editingId.value) {
      const { account_id, ...rest } = form
      await updateTask(editingId.value, rest)
      ElMessage.success('更新成功')
    } else {
      await createTask({ ...form })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await loadData()
  } catch (e) {
    console.error(e)
  } finally {
    submitting.value = false
  }
}

const handleToggle = async (row: any) => {
  await toggleTask(row.id)
  ElMessage.success(row.enabled ? '已停用' : '已启用')
  await loadData()
}

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(`确定删除该注水配置？`, '确认')
  await deleteTask(row.id)
  ElMessage.success('删除成功')
  await loadData()
}

const revokeAccountPhrase = (accountId: number) => `确认取消账户${accountId}`

const handleRevokeAccountQueue = async (row: any) => {
  const aid = row.account_id
  const phrase = revokeAccountPhrase(aid)
  let tracked = 0
  try {
    const st: any = await getAccountPendingTracked(aid)
    tracked = st.tracked_pending ?? 0
  } catch (e) {
    console.error(e)
    ElMessage.error('查询该账户排队任务数失败')
    return
  }
  try {
    await ElMessageBox.confirm(
      `仅撤销「客户账户 ${row.account_name}（ID ${aid}）」已记录且尚未开始执行的注水任务，共约 ${tracked} 个。\n` +
        `其他账户的注水排队不受影响。\n\n` +
        `说明：仅统计本功能上线后新派发的任务；历史入队且未追踪的任务请使用工具栏「清空全队列」（会清空全部）。\n\n` +
        `下一步请输入口令：${phrase}`,
      '撤本账户注水队列',
      { type: 'warning', confirmButtonText: '继续', cancelButtonText: '取消' }
    )
    const { value } = await ElMessageBox.prompt('请输入完整口令', '确认撤销', {
      confirmButtonText: '确认撤销',
      cancelButtonText: '取消',
      inputPlaceholder: phrase,
      inputValidator: (v) => {
        if (!v || v.trim() !== phrase) return '口令不正确'
        return true
      },
    })
    if (value.trim() !== phrase) return
    const res: any = await revokeAccountWaterPending(aid, phrase)
    ElMessage.success(res.message || `已撤销 ${res.revoked} 个`)
    await loadQueueStats()
  } catch (e: any) {
    if (e !== 'cancel' && e !== 'close') {
      const msg = e?.response?.data?.detail || e?.message || '操作失败'
      ElMessage.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }
  }
}

onMounted(async () => {
  await Promise.all([loadData(), loadOptions(), loadQueueStats()])
})
</script>

<style scoped>
.water-tasks { padding: 0; }
.stat-row { margin-bottom: 16px; }
.stat-card {
  text-align: center;
  padding: 16px 12px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  height: 100%;
  box-sizing: border-box;
}
.stat-card--ok {
  border-color: var(--el-color-success-light-5);
  background: var(--el-color-success-light-9);
}
.stat-value {
  font-size: 26px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  line-height: 1.2;
}
.stat-card--ok .stat-value { color: var(--el-color-success); }
.stat-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-top: 6px;
}
.toolbar-card {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
}
.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.queue-label {
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.queue-label strong {
  color: var(--el-color-warning);
  font-size: 15px;
}
.queue-label.is-busy strong { color: var(--el-color-danger); }
.queue-consumers { color: var(--el-text-color-secondary); font-size: 12px; }
.table-wrap {
  width: 100%;
  overflow-x: auto;
  border-radius: 8px;
}
.water-task-table {
  min-width: 960px;
}
.cell-account { line-height: 1.5; text-align: left; }
.cell-acct-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 8px;
  margin-bottom: 4px;
  font-size: 13px;
}
.cell-acct-row:last-of-type { margin-bottom: 0; }
.cell-acct-k {
  flex: 0 0 4.5em;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.cell-acct-v {
  flex: 1 1 auto;
  min-width: 0;
  font-weight: 500;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cell-acct-id {
  flex: 0 0 auto;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.country-tag { margin: 0; }
.cell-batch-line {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--el-border-color-lighter);
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.sep { margin: 0 2px; }
.cell-delay { display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 12px; }
.mono-range { font-variant-numeric: tabular-nums; font-size: 12px; }
.stat-num { font-weight: 600; font-variant-numeric: tabular-nums; }
.op-btns {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
:deep(.dropdown-danger) { color: var(--el-color-danger); }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
.form-tip { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; line-height: 1.5; }
/* 注水配置弹窗：延迟曲线（避免刻度文字与拖块重叠） */
.water-task-dialog :deep(.el-dialog__body) {
  padding-top: 8px;
}
.form-item-curve :deep(.el-form-item__content) {
  display: block;
  width: 100%;
}
.curve-block {
  width: 100%;
  box-sizing: border-box;
}
.curve-preset-bar {
  margin-bottom: 14px;
}
.curve-preset-hint {
  display: block;
  font-size: 12px;
  margin-bottom: 8px;
}
.curve-preset-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.curve-slider-row {
  margin-bottom: 10px;
}
.curve-slider-hint {
  display: block;
  font-size: 12px;
  margin-bottom: 10px;
}
.curve-slider {
  width: 100%;
  padding: 6px 10px 4px;
  box-sizing: border-box;
}
.curve-current-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 12px;
}
.curve-current-tag {
  font-weight: 500;
}
.curve-current-num {
  font-variant-numeric: tabular-nums;
  color: var(--el-color-primary);
}
.curve-desc-box {
  font-size: 13px;
  line-height: 1.65;
  color: var(--el-text-color-regular);
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
}
.progress-drawer-body { padding: 0 8px 16px; }
.progress-drawer-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}
.toolbar-meta { font-size: 13px; }
.toolbar-meta-num { color: var(--el-color-primary); font-weight: 600; }
.progress-legend {
  margin-bottom: 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}
.progress-legend-list {
  margin: 0;
  padding-left: 1.25rem;
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.65;
}
.progress-summary-row { margin-bottom: 14px; }
.progress-summary-card {
  text-align: center;
  padding: 10px 8px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  margin-bottom: 8px;
}
.progress-summary-value {
  font-size: 20px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-primary);
  line-height: 1.2;
}
.progress-summary-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.progress-empty { padding: 24px 0; }
.progress-table-wrap {
  width: 100%;
  overflow-x: auto;
  border-radius: 8px;
}
.progress-batch-table { min-width: 920px; }
.cell-batch { line-height: 1.45; text-align: left; }
.cell-batch-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 4px;
}
.cell-batch-id {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-primary);
}
.cell-batch-name {
  font-size: 13px;
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-all;
}
.cell-batch-times { margin-top: 6px; font-size: 12px; line-height: 1.5; }
.cell-send .cell-num { font-weight: 600; font-variant-numeric: tabular-nums; }
.tiny { font-size: 11px; }
.cell-num {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.cell-num.ok { color: var(--el-color-success); }
.cell-num.bad { color: var(--el-color-danger); }
.cell-num.cover { color: var(--el-color-warning); }
.progress-sub { margin-top: 4px; }
.progress-pagination { margin-top: 16px; display: flex; justify-content: flex-end; }
:deep(.progress-batch-table .el-progress__text) { font-size: 11px !important; min-width: 2.2em; }
</style>
