<template>
  <div class="system-services">

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-stats">
        <span class="s-chip"><span class="dot dot-ok" />运行中 <b>{{ runningCount }}</b></span>
        <span class="s-chip" v-if="errorCount > 0"><span class="dot dot-err" />异常 <b class="red">{{ errorCount }}</b></span>
        <span class="s-div" />
        <span class="s-chip">CPU <b>{{ totalCpu }}%</b></span>
        <span class="s-chip">内存 <b>{{ totalMem }}</b></span>
        <span class="s-time" v-if="updatedAt">{{ updatedAt }} 更新</span>
      </div>
      <div class="toolbar-right">
        <el-switch v-model="autoRefresh" active-text="自动刷新 10s" size="small" />
        <el-button :icon="Refresh" size="small" :loading="loading" @click="loadData">刷新</el-button>
      </div>
    </div>

    <!-- 架构图 -->
    <div class="arch-diagram" v-loading="loading">

      <!-- ① 接入层 -->
      <div class="tier" data-tier="access">
        <div class="tier-header">
          <span class="tier-name">① 接入层</span>
          <span class="tier-hint">外部流量与协议入口，用户和客户的唯一交互界面</span>
        </div>
        <div class="tier-nodes">
          <ArchNode v-for="s in ACCESS" :key="s.key" :cfg="s" :container="cm[s.key]" />
        </div>
      </div>

      <div class="connector">
        <div class="conn-line" />
        <div class="conn-labels">
          <span>HTTP REST</span>
          <span>Telegram Bot API</span>
          <span>SMPP 协议 · DLR 回执→RabbitMQ</span>
        </div>
        <div class="conn-arrow">▼</div>
      </div>

      <!-- ② 应用层 -->
      <div class="tier" data-tier="app">
        <div class="tier-header">
          <span class="tier-name">② 应用层</span>
          <span class="tier-hint">核心业务逻辑、鉴权、路由决策、API 响应</span>
        </div>
        <div class="tier-nodes">
          <ArchNode v-for="s in APP" :key="s.key" :cfg="s" :container="cm[s.key]" />
        </div>
      </div>

      <div class="connector">
        <div class="conn-line" />
        <div class="conn-labels">
          <span>写任务到 AMQP 队列</span>
          <span>读写 Redis 缓存</span>
          <span>SQL（经 ProxySQL）</span>
        </div>
        <div class="conn-arrow">▼</div>
      </div>

      <!-- ③ 任务调度层 + ④ 缓存层（并排） -->
      <div class="tier-row">
        <div class="tier flex-3" data-tier="queue">
          <div class="tier-header">
            <span class="tier-name">③ 任务调度层</span>
            <span class="tier-hint">异步任务队列 · 定时调度 · 多 Worker 并发执行</span>
          </div>
          <div class="tier-nodes">
            <ArchNode v-for="s in QUEUE" :key="s.key" :cfg="s" :container="cm[s.key]" />
          </div>
        </div>

        <div class="tier flex-1" data-tier="cache">
          <div class="tier-header">
            <span class="tier-name">④ 缓存层</span>
            <span class="tier-hint">会话 · 限流 · L2 缓存</span>
          </div>
          <div class="tier-nodes">
            <ArchNode v-for="s in CACHE" :key="s.key" :cfg="s" :container="cm[s.key]" />
          </div>
        </div>
      </div>

      <div class="connector">
        <div class="conn-line" />
        <div class="conn-labels">
          <span>TCP 直连 ProxySQL :6033</span>
        </div>
        <div class="conn-arrow">▼</div>
      </div>

      <!-- ⑤ 数据层 -->
      <div class="tier" data-tier="data">
        <div class="tier-header">
          <span class="tier-name">⑤ 数据层</span>
          <span class="tier-hint">持久化存储，ProxySQL 负责连接池复用，避免 MySQL 直连过载</span>
        </div>
        <div class="tier-nodes">
          <ArchNode v-for="s in DATA" :key="s.key" :cfg="s" :container="cm[s.key]" />
        </div>
      </div>

      <!-- ⑥ 监控层 + ⑦ 基础设施（并排） -->
      <div class="tier-row">
        <div class="tier flex-1" data-tier="monitor">
          <div class="tier-header">
            <span class="tier-name">⑥ 监控层</span>
            <span class="tier-hint">指标采集与可视化，排障首选入口</span>
          </div>
          <div class="tier-nodes">
            <ArchNode v-for="s in MONITOR" :key="s.key" :cfg="s" :container="cm[s.key]" />
          </div>
        </div>

        <div class="tier flex-1" data-tier="infra">
          <div class="tier-header">
            <span class="tier-name">⑦ 基础设施</span>
            <span class="tier-hint">平台支撑，通常无需关注</span>
          </div>
          <div class="tier-nodes">
            <ArchNode v-for="s in INFRA" :key="s.key" :cfg="s" :container="cm[s.key]" />
          </div>
        </div>
      </div>

    </div>

    <!-- 依赖连通性 -->
    <div class="health-section">
      <div class="health-title">依赖连通性探测</div>
      <div class="health-cards">
        <div v-for="(svc, key) in services" :key="key"
          class="health-card" :class="svc.status === 'ok' ? 'hc-ok' : 'hc-err'">
          <el-icon :size="20">
            <CircleCheck v-if="svc.status === 'ok'" />
            <CircleClose v-else />
          </el-icon>
          <div>
            <div class="hc-name">{{ svc.name }}</div>
            <div class="hc-msg">{{ svc.message }}</div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { Refresh, CircleCheck, CircleClose } from '@element-plus/icons-vue'
import { getServicesStatus, type ContainerInfo } from '@/api/system'
import ArchNode from './components/ArchNode.vue'

// ─── 服务定义 ───────────────────────────────────────────────────

interface SC { key: string; name: string; icon: string; tech: string; desc: string; ports?: string }

const ACCESS: SC[] = [
  { key: 'frontend',        name: 'Frontend',        icon: '🌐', tech: 'Nginx + Vue 3 SPA',  desc: '管理员与客户的 Web 操作界面，所有页面均从这里访问', ports: '80 / 443' },
  { key: 'bot',             name: 'Telegram Bot',    icon: '🤖', tech: 'Python aiogram',      desc: '业务助手：客户通过 Telegram 查余额、发短信、收状态通知' },
  { key: 'smpp-gateway',    name: 'SMPP Gateway',    icon: '📡', tech: 'Go · SMPP v3.4',      desc: '连接上游运营商 SMPP 协议，下发短信并将 DLR 回执推送到 RabbitMQ' },
  { key: 'landing-preview', name: 'Landing Page',    icon: '🏠', tech: 'Node.js · kaolach',   desc: '对外公开首页（kaolach.com /），展示产品介绍、定价、FAQ，由 Nginx 反代到此服务，与管理后台共用同一个域名', ports: '8787' },
]

const APP: SC[] = [
  { key: 'api', name: 'FastAPI', icon: '⚡', tech: 'Python FastAPI · Uvicorn', desc: '核心业务 API：鉴权、短信路由决策、账户管理、通道调度，所有请求的统一入口', ports: '8000' },
]

const QUEUE: SC[] = [
  { key: 'rabbitmq',      name: 'RabbitMQ',      icon: '📨', tech: 'RabbitMQ 3.x · AMQP',  desc: '消息代理：API 将任务投递到队列，Worker 消费。解耦生产与消费，支持流量削峰', ports: '5672 / 15672' },
  { key: 'beat',          name: 'Celery Beat',   icon: '⏰', tech: 'Celery Beat',            desc: '定时调度器：按计划触发周期任务，如 DLR 超时检查、库存刷新、批次巡检等' },
  { key: 'worker',        name: 'Worker（通用）', icon: '👷', tech: 'Celery Worker',          desc: '通用后台任务：数据导入导出、Webhook 推送、OKCC 同步、私库批量上传' },
  { key: 'worker-sms',    name: 'Worker SMS',    icon: '✉️', tech: 'Celery Worker',          desc: '专用短信发送 Worker：消费 sms_send 队列，调用通道 API/SMPP 实际发送' },
  { key: 'worker-dlr',    name: 'Worker DLR',    icon: '✅', tech: 'Celery Worker',          desc: '专用 DLR 处理 Worker：消费 sms_dlr 队列，更新送达状态，触发 Webhook 回调' },
  { key: 'worker-result', name: 'Worker Result', icon: '💾', tech: 'Celery Worker',          desc: '结果写库 Worker：批量将短信发送结果从内存队列刷入 MySQL，降低写压力' },
  { key: 'worker-web',    name: 'Worker Web',    icon: '🕸️', tech: 'Celery Worker',          desc: '网页自动化 Worker：数据号码采集、网页爬取等耗时任务' },
]

const CACHE: SC[] = [
  { key: 'redis', name: 'Redis', icon: '⚡', tech: 'Redis 7 · 无密码', desc: '高速缓存：Token 验证、API 限流计数器、余额缓存（L2）、跨进程状态共享' },
]

const DATA: SC[] = [
  { key: 'proxysql', name: 'ProxySQL', icon: '🔀', tech: 'ProxySQL 连接池', desc: 'MySQL 连接池代理：API 和 Worker 均连此处（:6033），复用连接、防止 MySQL 直连过载', ports: '6033' },
  { key: 'mysql',    name: 'MySQL',    icon: '🗄️', tech: 'MySQL 8',       desc: '主数据库：存储短信日志、账户、通道、配置、批次等所有持久化业务数据', ports: '3306' },
]

const MONITOR: SC[] = [
  { key: 'prometheus', name: 'Prometheus', icon: '📊', tech: 'Prometheus',   desc: '指标采集：定时抓取 API/Worker 暴露的 metrics 端点，存储时序数据' },
  { key: 'grafana',    name: 'Grafana',    icon: '📈', tech: 'Grafana',      desc: '监控可视化：展示 QPS、延迟、队列深度、错误率等图表，排障首选入口' },
]

const INFRA: SC[] = [
  { key: 'docker-proxy', name: 'Docker Proxy', icon: '🔧', tech: 'tecnativa/docker-socket-proxy', desc: '受限 Docker API 代理：仅开放容器重启权限，供 Bot 和 API 触发特定容器重启，避免暴露完整 Docker socket' },
]

// ─── 数据 & 刷新 ─────────────────────────────────────────────────

const loading = ref(false)
const autoRefresh = ref(false)
const updatedAt = ref('')
const containers = ref<ContainerInfo[]>([])
const services = ref<Record<string, { name: string; status: string; message: string }>>({})

const cm = computed<Record<string, ContainerInfo>>(() => {
  const map: Record<string, ContainerInfo> = {}
  containers.value.forEach(c => { map[c.name.replace(/^smsc-/, '')] = c })
  return map
})

const runningCount = computed(() => containers.value.filter(c => c.state === 'running').length)
const errorCount = computed(() => containers.value.filter(c => c.state !== 'running').length)
const totalCpu = computed(() => {
  const vals = containers.value.filter(c => c.cpu_pct != null).map(c => c.cpu_pct!)
  return vals.length ? vals.reduce((a, b) => a + b, 0).toFixed(1) : '0.0'
})
const totalMem = computed(() => {
  const total = containers.value.filter(c => c.mem_usage_mb != null).reduce((s, c) => s + c.mem_usage_mb!, 0)
  return total >= 1024 ? (total / 1024).toFixed(1) + ' GB' : Math.round(total) + ' MB'
})

let timer: ReturnType<typeof setInterval> | null = null

async function loadData() {
  loading.value = true
  try {
    const res = await getServicesStatus()
    containers.value = res.containers
    services.value = res.services
    updatedAt.value = new Date().toLocaleTimeString('zh-CN')
  } finally {
    loading.value = false
  }
}

watch(autoRefresh, val => {
  if (val) { timer = setInterval(loadData, 10000) }
  else { if (timer) { clearInterval(timer); timer = null } }
})

onMounted(loadData)
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.system-services { display: flex; flex-direction: column; gap: 16px; }

/* 工具栏 */
.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 8px;
  padding: 10px 16px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}
.toolbar-stats { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.toolbar-right { display: flex; align-items: center; gap: 10px; }
.s-chip { font-size: 13px; color: var(--el-text-color-secondary); display: flex; align-items: center; gap: 5px; }
.s-chip b { color: var(--el-text-color-primary); }
.s-chip b.red { color: var(--el-color-danger); }
.s-div { width: 1px; height: 16px; background: var(--el-border-color-lighter); }
.s-time { font-size: 12px; color: var(--el-text-color-placeholder); }
.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; }
.dot-ok  { background: var(--el-color-success); }
.dot-err { background: var(--el-color-danger); }

/* 架构图主体 */
.arch-diagram {
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* Tier */
.tier {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  overflow: hidden;
}

.tier-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 16px;
  background: var(--el-fill-color-lighter);
  border-bottom: 1px solid var(--el-border-color-extra-light);
}

[data-tier="access"]  .tier-header { background: #ecf5ff; border-bottom-color: #c6e0f5; }
[data-tier="app"]     .tier-header { background: #f0f9eb; border-bottom-color: #c2e7b0; }
[data-tier="queue"]   .tier-header { background: #fdf6ec; border-bottom-color: #f5dab1; }
[data-tier="cache"]   .tier-header { background: #fef0f0; border-bottom-color: #fbc4c4; }
[data-tier="data"]    .tier-header { background: #f4f4f5; border-bottom-color: #dcdfe6; }
[data-tier="monitor"] .tier-header { background: #f0f7ee; border-bottom-color: #b3d8ad; }
[data-tier="infra"]   .tier-header { background: #fafafa; border-bottom-color: #e4e7ed; }

.tier-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}
.tier-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.3;
}

.tier-nodes {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px;
}

/* 连接器 */
.connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px 0;
  position: relative;
  z-index: 0;
}
.conn-line {
  width: 1px;
  height: 8px;
  background: var(--el-border-color);
}
.conn-labels {
  display: flex;
  gap: 16px;
  padding: 3px 12px;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-extra-light);
  border-radius: 20px;
  margin: 2px 0;
}
.conn-labels span {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
.conn-arrow {
  font-size: 12px;
  color: var(--el-border-color-dark);
  line-height: 1;
  margin-top: 2px;
}

/* 并排行 */
.tier-row {
  display: flex;
  gap: 12px;
  align-items: stretch;
}
.tier-row .tier { flex: 1; }
.flex-1 { flex: 1; }
.flex-2 { flex: 2; }
.flex-3 { flex: 3; }

/* 健康探测 */
.health-section { display: flex; flex-direction: column; gap: 8px; }
.health-title { font-size: 13px; font-weight: 600; color: var(--el-text-color-secondary); padding: 0 2px; }
.health-cards { display: flex; gap: 12px; flex-wrap: wrap; }
.health-card {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  min-width: 160px;
}
.hc-ok  { border-left: 3px solid var(--el-color-success); }
.hc-ok .el-icon  { color: var(--el-color-success); }
.hc-err { border-left: 3px solid var(--el-color-danger); }
.hc-err .el-icon { color: var(--el-color-danger); }
.hc-name { font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); }
.hc-msg  { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 1px; }

@media (max-width: 768px) {
  .tier-row { flex-direction: column; }
}
</style>
