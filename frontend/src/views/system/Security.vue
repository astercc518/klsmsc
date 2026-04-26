<template>
  <div class="system-security" v-loading="loading">

    <!-- 统计卡片 -->
    <div class="stat-cards">
      <div class="stat-card success-card">
        <div class="card-icon"><el-icon :size="28"><CircleCheck /></el-icon></div>
        <div class="card-body">
          <div class="card-value">{{ stats.today_success }}</div>
          <div class="card-label">今日登录成功</div>
        </div>
      </div>
      <div class="stat-card danger-card">
        <div class="card-icon"><el-icon :size="28"><CircleClose /></el-icon></div>
        <div class="card-body">
          <div class="card-value">{{ stats.today_failed }}</div>
          <div class="card-label">今日登录失败</div>
        </div>
      </div>
      <div class="stat-card info-card">
        <div class="card-icon"><el-icon :size="28"><Location /></el-icon></div>
        <div class="card-body">
          <div class="card-value">{{ stats.unique_ips_today }}</div>
          <div class="card-label">今日独立 IP</div>
        </div>
      </div>
      <div class="stat-card" :class="loginSuccessRate >= 95 ? 'success-card' : loginSuccessRate >= 80 ? 'warn-card' : 'danger-card'">
        <div class="card-icon"><el-icon :size="28"><TrendCharts /></el-icon></div>
        <div class="card-body">
          <div class="card-value">{{ loginSuccessRate }}%</div>
          <div class="card-label">今日登录成功率</div>
        </div>
      </div>
    </div>

    <!-- 近 7 日登录趋势 -->
    <el-card shadow="never" class="section-card" v-if="stats.daily_trend.length">
      <template #header><span class="section-title">近 7 日登录趋势</span></template>
      <div class="trend-chart">
        <div
          v-for="day in paddedTrend"
          :key="day.day"
          class="trend-day"
        >
          <div class="trend-bars">
            <el-tooltip :content="`成功 ${day.success}`" placement="top">
              <div
                class="bar success-bar"
                :style="{ height: barHeight(day.success) + 'px' }"
              />
            </el-tooltip>
            <el-tooltip :content="`失败 ${day.failed}`" placement="top">
              <div
                class="bar fail-bar"
                :style="{ height: barHeight(day.failed) + 'px' }"
              />
            </el-tooltip>
          </div>
          <div class="trend-label">{{ formatDay(day.day) }}</div>
        </div>
      </div>
      <div class="trend-legend">
        <span class="legend-dot success-dot" />成功
        <span class="legend-dot fail-dot" style="margin-left:16px" />失败
      </div>
    </el-card>

    <div class="two-col">
      <!-- 高风险 IP -->
      <el-card shadow="never" class="section-card">
        <template #header>
          <span class="section-title">高失败率 IP（近 30 天）</span>
          <el-tag v-if="stats.top_failed_ips.length === 0" type="success" size="small" effect="plain" style="margin-left:8px">暂无</el-tag>
        </template>
        <el-empty v-if="stats.top_failed_ips.length === 0" :image-size="60" description="暂无失败登录记录" />
        <el-table v-else :data="stats.top_failed_ips" stripe size="small">
          <el-table-column label="IP 地址" prop="ip" min-width="130">
            <template #default="{ row }">
              <code class="ip-code">{{ row.ip }}</code>
            </template>
          </el-table-column>
          <el-table-column label="总次数" prop="total" width="72" align="center" />
          <el-table-column label="失败次数" width="80" align="center">
            <template #default="{ row }">
              <el-tag type="danger" size="small" effect="dark">{{ row.failed }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="失败率" width="72" align="center">
            <template #default="{ row }">
              <span :class="row.failed / row.total > 0.5 ? 'text-danger' : 'text-warn'">
                {{ Math.round(row.failed / row.total * 100) }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column label="最后时间" min-width="100">
            <template #default="{ row }">
              <span class="small-time">{{ row.last_time?.slice(0, 16) || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 近期登录事件时间线 -->
      <el-card shadow="never" class="section-card">
        <template #header><span class="section-title">近期登录事件</span></template>
        <el-empty v-if="stats.recent_events.length === 0" :image-size="60" description="暂无登录记录" />
        <div v-else class="event-timeline">
          <div
            v-for="ev in stats.recent_events"
            :key="ev.id"
            class="event-item"
            :class="ev.status === 'failed' ? 'ev-failed' : 'ev-success'"
          >
            <div class="ev-dot" />
            <div class="ev-content">
              <div class="ev-header">
                <span class="ev-admin">{{ ev.admin_name }}</span>
                <el-tag
                  :type="ev.status === 'success' ? 'success' : 'danger'"
                  size="small"
                  effect="plain"
                >{{ ev.status === 'success' ? '成功' : '失败' }}</el-tag>
              </div>
              <div class="ev-meta">
                <code v-if="ev.ip_address" class="ev-ip">{{ ev.ip_address }}</code>
                <span class="ev-time">{{ formatRelative(ev.created_at) }}</span>
              </div>
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 高风险操作记录 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span class="section-title">高风险操作记录（近 30 天）</span>
        <el-tag v-if="stats.recent_risky_ops.length === 0" type="success" size="small" effect="plain" style="margin-left:8px">暂无</el-tag>
      </template>
      <el-empty v-if="stats.recent_risky_ops.length === 0" :image-size="60" description="暂无高风险操作记录" />
      <el-table v-else :data="stats.recent_risky_ops" stripe size="small" style="width:100%">
        <el-table-column label="时间" width="160">
          <template #default="{ row }">
            <el-tooltip :content="row.created_at" placement="top">
              <span class="small-time">{{ formatRelative(row.created_at) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="操作人" width="100">
          <template #default="{ row }">
            <div class="ev-admin">{{ row.admin_name }}</div>
          </template>
        </el-table-column>
        <el-table-column label="模块" width="100">
          <template #default="{ row }">
            <el-tag :type="riskyModuleTagType(row.module)" size="small" effect="light">{{ row.module_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-tag :type="row.action === 'delete' ? 'danger' : 'warning'" size="small" effect="plain">
              {{ ACTION_LABELS[row.action] || row.action }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="72" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status === 'success' ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="描述" min-width="200" show-overflow-tooltip prop="title" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { CircleCheck, CircleClose, Location, TrendCharts } from '@element-plus/icons-vue'
import { getSecurityStats, type SecurityStatsResponse } from '@/api/system'

const ACTION_LABELS: Record<string, string> = {
  create: '新建', update: '修改', delete: '删除', login: '登录',
  export: '导出', import: '导入', query: '查询',
}

const RISKY_MODULE_COLORS: Record<string, string> = {
  security: 'danger', finance: 'success', config: 'warning',
}

function riskyModuleTagType(mod: string) {
  return (RISKY_MODULE_COLORS[mod] || '') as any
}

const loading = ref(false)
const stats = ref<SecurityStatsResponse>({
  today_success: 0,
  today_failed: 0,
  unique_ips_today: 0,
  daily_trend: [],
  top_failed_ips: [],
  recent_events: [],
  recent_risky_ops: [],
})

const loginSuccessRate = computed(() => {
  const total = stats.value.today_success + stats.value.today_failed
  if (total === 0) return 100
  return Math.round(stats.value.today_success / total * 100)
})

const paddedTrend = computed(() => {
  const trend = [...stats.value.daily_trend]
  // pad to 7 days
  while (trend.length < 7) {
    const d = new Date()
    d.setDate(d.getDate() - (7 - trend.length))
    trend.unshift({ day: d.toISOString().slice(0, 10), success: 0, failed: 0 })
  }
  return trend.slice(-7)
})

const trendMax = computed(() => {
  const all = paddedTrend.value.flatMap(d => [d.success, d.failed])
  return Math.max(...all, 1)
})

function barHeight(val: number): number {
  return Math.max(2, Math.round((val / trendMax.value) * 80))
}

function formatDay(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function formatRelative(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const diff = Date.now() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  return d.toLocaleDateString('zh-CN')
}

onMounted(async () => {
  loading.value = true
  try {
    stats.value = await getSecurityStats()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.system-security { display: flex; flex-direction: column; gap: 16px; }

/* 统计卡片行 */
.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
@media (max-width: 900px) { .stat-cards { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .stat-cards { grid-template-columns: 1fr; } }

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}
.success-card { border-left: 4px solid var(--el-color-success); }
.danger-card  { border-left: 4px solid var(--el-color-danger); }
.warn-card    { border-left: 4px solid var(--el-color-warning); }
.info-card    { border-left: 4px solid var(--el-color-info); }
.success-card .card-icon { color: var(--el-color-success); }
.danger-card  .card-icon { color: var(--el-color-danger); }
.warn-card    .card-icon { color: var(--el-color-warning); }
.info-card    .card-icon { color: var(--el-color-info); }
.card-body { display: flex; flex-direction: column; }
.card-value { font-size: 26px; font-weight: 700; line-height: 1; color: var(--el-text-color-primary); }
.card-label { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }

/* 分栏布局 */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 800px) { .two-col { grid-template-columns: 1fr; } }

.section-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: var(--el-fill-color-lighter);
  display: flex;
  align-items: center;
}
.section-card :deep(.el-card__body) { padding: 12px 16px; }
.section-title { font-size: 14px; font-weight: 600; }

/* 趋势图 */
.trend-chart {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  height: 100px;
  padding: 0 4px 4px;
}
.trend-day {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.trend-bars { display: flex; gap: 3px; align-items: flex-end; height: 80px; }
.bar { width: 12px; border-radius: 2px 2px 0 0; transition: height 0.3s; }
.success-bar { background: var(--el-color-success); }
.fail-bar { background: var(--el-color-danger-light-5); }
.trend-label { font-size: 11px; color: var(--el-text-color-secondary); }
.trend-legend { display: flex; align-items: center; gap: 6px; margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.legend-dot { display: inline-block; width: 10px; height: 10px; border-radius: 2px; }
.success-dot { background: var(--el-color-success); }
.fail-dot { background: var(--el-color-danger-light-5); }

/* IP 表格 */
.ip-code { font-family: monospace; font-size: 12px; background: var(--el-fill-color); padding: 1px 4px; border-radius: 3px; }
.small-time { font-size: 12px; color: var(--el-text-color-secondary); }
.text-danger { color: var(--el-color-danger); font-weight: 600; }
.text-warn { color: var(--el-color-warning); font-weight: 600; }

/* 事件时间线 */
.event-timeline {
  max-height: 380px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0;
}
.event-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px dashed var(--el-border-color-extra-light);
  position: relative;
}
.event-item:last-child { border-bottom: none; }
.ev-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  margin-top: 5px;
  flex-shrink: 0;
}
.ev-success .ev-dot { background: var(--el-color-success); }
.ev-failed  .ev-dot { background: var(--el-color-danger); }
.ev-content { flex: 1; min-width: 0; }
.ev-header { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
.ev-admin { font-size: 13px; font-weight: 500; color: var(--el-text-color-primary); }
.ev-meta { display: flex; align-items: center; gap: 10px; }
.ev-ip { font-size: 11px; font-family: monospace; color: var(--el-text-color-secondary); }
.ev-time { font-size: 11px; color: var(--el-text-color-placeholder); }
</style>
