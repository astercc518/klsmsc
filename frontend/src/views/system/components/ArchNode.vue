<template>
  <div class="arch-node" :class="nodeClass">
    <div class="node-top">
      <span class="node-icon">{{ cfg.icon }}</span>
      <div class="node-identity">
        <div class="node-name">{{ cfg.name }}</div>
        <div class="node-tech">{{ cfg.tech }}</div>
      </div>
      <el-tag :type="tagType" size="small" effect="light" class="node-badge">{{ stateText }}</el-tag>
    </div>

    <div class="node-desc">{{ cfg.desc }}</div>

    <div class="node-ports" v-if="cfg.ports">
      <span class="port-label">端口</span> {{ cfg.ports }}
    </div>

    <div class="node-metrics" v-if="hasMetrics">
      <div class="nm-row">
        <span class="nm-label">CPU</span>
        <el-progress :percentage="Math.min(container!.cpu_pct!, 100)" :stroke-width="3"
          :show-text="false" :color="cpuColor" class="nm-bar" />
        <span class="nm-num" :class="cpuClass">{{ container!.cpu_pct!.toFixed(1) }}%</span>
      </div>
      <div class="nm-row">
        <span class="nm-label">MEM</span>
        <el-progress :percentage="Math.min(container!.mem_pct ?? 0, 100)" :stroke-width="3"
          :show-text="false" :color="memColor" class="nm-bar" />
        <span class="nm-num" :class="memClass">{{ formatMem(container!.mem_usage_mb) }}</span>
      </div>
    </div>

    <div class="node-status-line" v-else-if="container">
      <span class="status-uptime">{{ container.status }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ContainerInfo } from '@/api/system'

interface ServiceConfig {
  key: string
  name: string
  icon: string
  tech: string
  desc: string
  ports?: string
}

const props = defineProps<{ cfg: ServiceConfig; container?: ContainerInfo }>()

const state = computed(() => props.container?.state ?? 'unknown')

const nodeClass = computed(() => ({
  'node-running': state.value === 'running',
  'node-warn': state.value === 'restarting',
  'node-error': state.value !== 'running' && state.value !== 'restarting' && state.value !== 'unknown',
  'node-unknown': state.value === 'unknown',
}))

const tagType = computed(() => {
  if (state.value === 'running') return 'success'
  if (state.value === 'restarting') return 'warning'
  if (state.value === 'unknown') return 'info'
  return 'danger'
})

const stateText = computed(() => {
  const m: Record<string, string> = {
    running: '运行中', restarting: '重启中',
    paused: '已暂停', exited: '已退出',
    dead: '异常', created: '已创建', unknown: '未知',
  }
  return m[state.value] ?? state.value
})

const hasMetrics = computed(() =>
  props.container && props.container.cpu_pct !== null && props.container.cpu_pct !== undefined
)

const cpuPct = computed(() => props.container?.cpu_pct ?? 0)
const memPct = computed(() => props.container?.mem_pct ?? 0)

const cpuColor = computed(() => {
  if (cpuPct.value < 30) return 'var(--el-color-success)'
  if (cpuPct.value < 70) return 'var(--el-color-warning)'
  return 'var(--el-color-danger)'
})
const memColor = computed(() => {
  if (memPct.value < 60) return 'var(--el-color-success)'
  if (memPct.value < 85) return 'var(--el-color-warning)'
  return 'var(--el-color-danger)'
})
const cpuClass = computed(() => cpuPct.value >= 70 ? 'num-danger' : cpuPct.value >= 30 ? 'num-warn' : '')
const memClass = computed(() => memPct.value >= 85 ? 'num-danger' : memPct.value >= 60 ? 'num-warn' : '')

function formatMem(mb: number | null | undefined) {
  if (mb == null) return '—'
  if (mb >= 1024) return (mb / 1024).toFixed(1) + ' GB'
  return mb.toFixed(0) + ' MB'
}
</script>

<style scoped>
.arch-node {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 180px;
  flex: 1;
  transition: box-shadow 0.15s, border-color 0.15s;
  position: relative;
  overflow: hidden;
}
.arch-node::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--el-color-success);
}
.arch-node:hover { box-shadow: 0 2px 12px rgba(0,0,0,.09); }
.node-warn::before { background: var(--el-color-warning); }
.node-error::before { background: var(--el-color-danger); }
.node-unknown::before { background: var(--el-border-color); }
.node-error { opacity: 0.8; }

.node-top { display: flex; align-items: flex-start; gap: 8px; }
.node-icon { font-size: 22px; line-height: 1; flex-shrink: 0; margin-top: 1px; }
.node-identity { flex: 1; min-width: 0; }
.node-name { font-size: 13px; font-weight: 700; color: var(--el-text-color-primary); font-family: monospace; }
.node-tech { font-size: 11px; color: var(--el-text-color-placeholder); margin-top: 1px; }
.node-badge { flex-shrink: 0; }

.node-desc { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.5; }

.node-ports { font-size: 11px; color: var(--el-text-color-placeholder); }
.port-label { background: var(--el-fill-color); padding: 0 4px; border-radius: 3px; font-size: 10px; margin-right: 2px; }

/* Metrics */
.node-metrics { display: flex; flex-direction: column; gap: 4px; }
.nm-row { display: flex; align-items: center; gap: 5px; }
.nm-label { font-size: 10px; color: var(--el-text-color-placeholder); width: 26px; flex-shrink: 0; text-transform: uppercase; }
.nm-bar { flex: 1; }
.nm-num { font-size: 11px; font-weight: 600; color: var(--el-text-color-primary); width: 44px; text-align: right; }
.nm-num.num-warn { color: var(--el-color-warning); }
.nm-num.num-danger { color: var(--el-color-danger); }

.node-status-line { font-size: 11px; color: var(--el-text-color-placeholder); }
.status-uptime { font-family: monospace; }
</style>
