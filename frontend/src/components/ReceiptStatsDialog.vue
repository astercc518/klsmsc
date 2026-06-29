<template>
  <el-dialog
    :model-value="modelValue"
    :title="`回执统计 — 批次 #${batch?.id ?? ''}`"
    :width="width"
    destroy-on-close
    class="receipt-stats-dialog"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div v-if="batch" v-loading="loading" class="receipt-stats">
      <div v-if="batch.batch_name" class="rs-head">{{ batch.batch_name }}</div>

      <!-- 短信内容 -->
      <div v-if="smsContent" class="rs-content">{{ smsContent }}</div>

      <!-- 汇总卡片 -->
      <div class="rs-cards">
        <div class="rs-card rs-card--total">
          <div class="rs-num">{{ fmt(total) }}</div>
          <div class="rs-label">提交总数</div>
        </div>
        <div class="rs-card rs-card--success">
          <div class="rs-num rs-num-success">{{ fmt(delivered) }}</div>
          <div class="rs-label">已送达</div>
          <div class="rs-sub">{{ deliveryRate }}</div>
        </div>
        <div class="rs-card rs-card--warning">
          <div class="rs-num rs-num-warning">{{ fmt(awaiting) }}</div>
          <div class="rs-label">等待回执</div>
        </div>
        <div class="rs-card rs-card--info">
          <div class="rs-num rs-num-info">{{ fmt(processing) }}</div>
          <div class="rs-label">排队处理中</div>
        </div>
        <div class="rs-card rs-card--danger">
          <div class="rs-num rs-num-danger">{{ fmt(failed) }}</div>
          <div class="rs-label">失败</div>
        </div>
      </div>

      <!-- 状态分布（分段条 + 图例，取代旧的明细列表与进度条） -->
      <div v-if="segments.length" class="rs-block">
        <div class="rs-section-title">状态分布</div>
        <div class="rs-dist-bar">
          <div
            v-for="s in segments"
            :key="s.key"
            class="rs-seg"
            :class="`rs-c-${s.cls}`"
            :style="{ width: `${s.pct}%` }"
            :title="`${s.label} ${fmt(s.count)}`"
          ></div>
        </div>
        <div class="rs-legend">
          <span v-for="s in segments" :key="s.key" class="rs-leg">
            <i class="rs-dot" :class="`rs-c-${s.cls}`"></i>{{ s.label }}
            <b>{{ fmt(s.count) }}</b>
          </span>
        </div>
      </div>

      <!-- 失败原因分析 -->
      <div v-if="failureList.length" class="rs-block">
        <div class="rs-section-title">
          失败原因分析<span class="rs-fail-total">共 {{ fmt(failTotal) }} 条</span>
        </div>
        <div class="rs-fail-list">
          <div v-for="(f, i) in failureList" :key="i" class="rs-fail-item">
            <div class="rs-fail-line">
              <span class="rs-fail-reason" :title="f.reason">{{ f.reason }}</span>
              <span class="rs-fail-count">{{ fmt(f.count) }}<em>{{ f.pct }}</em></span>
            </div>
            <div class="rs-fail-bar"><div class="rs-fail-bar-fill" :style="{ width: f.pct }"></div></div>
          </div>
        </div>
      </div>

      <p class="rs-note">「等待回执」已提交上游、终态回执未到；「失败」含发送失败与已过期。</p>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/** 任务/批次行的回执相关字段（客户端 SmsBatch 与管理端 AdminBatchItem 通用子集） */
interface BatchLike {
  id: number
  batch_name?: string | null
  status?: string
  total_count?: number
  success_count?: number
  delivered_count?: number
  failed_count?: number
  processing_count?: number
  /** 客户端批次：首条短信内容样本 */
  message_preview?: string | null
  /** 管理端批次：短信内容 */
  content?: string | null
}

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    batch: BatchLike | null
    /** 后端 sms_logs.status 原始计数分布，用于状态分布条；为空则不展示 */
    statusCounts?: Record<string, number> | null
    /** 失败/过期记录按 error_message 聚合的 Top 原因；为空则不展示失败分析 */
    failureReasons?: { reason: string; count: number }[] | null
    /** 拉取明细时的加载态 */
    loading?: boolean
    width?: string
  }>(),
  { statusCounts: null, failureReasons: null, loading: false, width: '680px' }
)

const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const total = computed(() => Number(props.batch?.total_count) || 0)
const delivered = computed(() => Number(props.batch?.delivered_count) || 0)
const success = computed(() => Number(props.batch?.success_count) || 0)
// 已提交上游、等待终态回执 = 成功(已发出+已送达) - 已送达
const awaiting = computed(() => Math.max(0, success.value - delivered.value))
const processing = computed(() => Number(props.batch?.processing_count) || 0)
const failed = computed(() => Number(props.batch?.failed_count) || 0)

const deliveryRate = computed(() =>
  total.value > 0 ? `送达率 ${((delivered.value / total.value) * 100).toFixed(1)}%` : '送达率 -'
)

// 短信内容：客户端用 message_preview，管理端用 content
const smsContent = computed(() => props.batch?.content || props.batch?.message_preview || '')

// 状态分布：直接由原始 status_counts 渲染分段条，保留逐状态粒度又比明细列表紧凑
const SEG_META: Record<string, { label: string; cls: string }> = {
  delivered: { label: '已送达', cls: 'delivered' },
  sent: { label: '待回执', cls: 'sent' },
  queued: { label: '排队中', cls: 'queued' },
  pending: { label: '待处理', cls: 'pending' },
  expired: { label: '已过期', cls: 'expired' },
  failed: { label: '失败', cls: 'failed' },
}
const SEG_ORDER = ['delivered', 'sent', 'queued', 'pending', 'expired', 'failed']

const segments = computed<{ key: string; label: string; cls: string; count: number; pct: number }[]>(() => {
  const sc = props.statusCounts
  if (!sc) return []
  const sum = Object.values(sc).reduce((a, b) => a + (Number(b) || 0), 0)
  const den = Math.max(total.value, sum) || 1
  const known = SEG_ORDER.filter((k) => (Number(sc[k]) || 0) > 0).map((k) => {
    const c = Number(sc[k]) || 0
    return { key: k, label: SEG_META[k].label, cls: SEG_META[k].cls, count: c, pct: (c / den) * 100 }
  })
  const extra = Object.keys(sc)
    .filter((k) => !SEG_ORDER.includes(k) && k !== '' && (Number(sc[k]) || 0) > 0)
    .map((k) => {
      const c = Number(sc[k]) || 0
      return { key: k, label: k, cls: 'other', count: c, pct: (c / den) * 100 }
    })
  return [...known, ...extra]
})

// 失败原因分析：百分比相对失败总数；后端可能截断 Top12，故求和兜底
const failTotal = computed(() => {
  if (failed.value > 0) return failed.value
  return (props.failureReasons || []).reduce((s, r) => s + (Number(r.count) || 0), 0)
})
const failureList = computed<{ reason: string; count: number; pct: string }[]>(() => {
  const list = props.failureReasons || []
  const den = failTotal.value || 1
  return list.map((r) => {
    const c = Number(r.count) || 0
    return {
      reason: r.reason || '未知原因',
      count: c,
      pct: `${Math.min(100, (c / den) * 100).toFixed(1)}%`,
    }
  })
})

function fmt(n: number): string {
  return n.toLocaleString('en-US')
}
</script>

<style scoped>
.rs-head {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
}
.rs-content {
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 16px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow-y: auto;
}

/* ===== 汇总卡片 ===== */
.rs-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}
@media (max-width: 640px) {
  .rs-cards { grid-template-columns: repeat(3, 1fr); }
}
.rs-card {
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-top: 3px solid var(--el-border-color);
  border-radius: 8px;
  padding: 14px 8px 12px;
  text-align: center;
}
.rs-card--total { border-top-color: var(--el-color-primary); }
.rs-card--success { border-top-color: var(--el-color-success); }
.rs-card--warning { border-top-color: var(--el-color-warning); }
.rs-card--info { border-top-color: var(--el-color-info); }
.rs-card--danger { border-top-color: var(--el-color-danger); }
.rs-num {
  font-size: 23px;
  font-weight: 700;
  line-height: 1.1;
  color: var(--el-text-color-primary);
  font-variant-numeric: tabular-nums;
}
.rs-num-success { color: var(--el-color-success); }
.rs-num-warning { color: var(--el-color-warning); }
.rs-num-info { color: var(--el-color-info); }
.rs-num-danger { color: var(--el-color-danger); }
.rs-label {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.rs-sub {
  margin-top: 2px;
  font-size: 11px;
  color: var(--el-color-success);
}

/* ===== 区块通用 ===== */
.rs-block { margin-top: 20px; }
.rs-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 10px;
}
.rs-fail-total {
  margin-left: 8px;
  font-weight: 400;
  font-size: 12px;
  color: var(--el-color-danger);
}

/* ===== 状态分布条 ===== */
.rs-dist-bar {
  display: flex;
  height: 12px;
  border-radius: 6px;
  overflow: hidden;
  background: var(--el-fill-color);
}
.rs-seg { height: 100%; transition: width 0.3s ease; }
.rs-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.rs-leg { display: inline-flex; align-items: center; }
.rs-leg b {
  margin-left: 6px;
  color: var(--el-text-color-primary);
  font-variant-numeric: tabular-nums;
}
.rs-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  display: inline-block;
}
/* 状态色（分段条与图例点共用） */
.rs-c-delivered { background: var(--el-color-success); }
.rs-c-sent { background: var(--el-color-warning); }
.rs-c-queued { background: var(--el-color-info-light-3); }
.rs-c-pending { background: var(--el-color-info); }
.rs-c-expired { background: var(--el-color-danger-light-3); }
.rs-c-failed { background: var(--el-color-danger); }
.rs-c-other { background: var(--el-color-info-light-5); }

/* ===== 失败原因 ===== */
.rs-fail-list { display: flex; flex-direction: column; gap: 12px; }
.rs-fail-line {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 13px;
  margin-bottom: 5px;
}
.rs-fail-reason {
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 12px;
}
.rs-fail-count {
  flex: none;
  color: var(--el-text-color-primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.rs-fail-count em {
  margin-left: 6px;
  font-style: normal;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}
.rs-fail-bar {
  height: 6px;
  border-radius: 3px;
  background: var(--el-fill-color);
  overflow: hidden;
}
.rs-fail-bar-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--el-color-danger);
  transition: width 0.3s ease;
}

.rs-note {
  margin: 18px 0 0;
  font-size: 11px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}
</style>
