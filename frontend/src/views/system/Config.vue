<template>
  <div class="config-layout" v-loading="loading">
    <!-- 顶部 Header -->
    <header class="config-header">
      <div class="header-left">
        <h2 class="page-title">⚙️ 系统配置</h2>
        <el-input
          v-model="searchText"
          placeholder="🔍 搜索配置项（支持中英文）"
          clearable
          class="search-input"
          @input="onSearchChange"
        />
      </div>
      <div class="header-right">
        <el-button :icon="Document" @click="auditDrawerVisible = true">审计日志</el-button>
        <el-button :icon="Download" @click="onExport">导出</el-button>
        <el-button :icon="Upload" @click="importDialogVisible = true">导入</el-button>
        <el-button
          type="primary"
          :icon="Check"
          :disabled="dirtyKeys.size === 0"
          :loading="saving"
          @click="onSaveAll"
        >
          保存改动
          <el-badge v-if="dirtyKeys.size > 0" :value="dirtyKeys.size" class="save-badge" />
        </el-button>
      </div>
    </header>

    <div class="config-body">
      <!-- 左侧分类导航 -->
      <aside class="config-nav">
        <el-menu
          :default-active="currentGroup"
          @select="onGroupSelect"
          class="nav-menu"
        >
          <el-menu-item
            v-for="g in CONFIG_GROUPS"
            :key="g.key"
            :index="g.key"
          >
            <el-icon><component :is="resolveIcon(g.icon)" /></el-icon>
            <span>{{ g.label }}</span>
            <el-badge
              v-if="dirtyByGroup[g.key] > 0"
              :value="dirtyByGroup[g.key]"
              class="nav-badge"
              type="primary"
            />
            <el-badge
              v-else-if="searchHitsByGroup[g.key] > 0"
              :value="searchHitsByGroup[g.key]"
              class="nav-badge"
              type="warning"
            />
          </el-menu-item>
        </el-menu>

        <div v-if="dirtyKeys.size > 0" class="nav-footer">
          <el-alert type="warning" :closable="false">
            <template #title>
              <span>{{ dirtyKeys.size }} 项未保存</span>
            </template>
            <el-button size="small" link @click="onDiscardAll">放弃全部改动</el-button>
          </el-alert>
        </div>
      </aside>

      <!-- 主内容区 -->
      <main class="config-main">
        <template v-for="g in CONFIG_GROUPS" :key="g.key">
          <div v-show="currentGroup === g.key" class="group-section">
            <ConfigGroup
              v-for="sg in g.subgroups"
              :key="sg.key"
              ref="groupRefs"
              :group="g.key"
              :subgroup="sg"
              :values="values"
              :dirty-keys="dirtyKeys"
              :audit-map="auditMap"
              :highlight-key="highlightKey"
              :visible-key-filter="searchActive ? searchHitsSet : undefined"
              @change="onFieldChange"
            />
            <el-empty
              v-if="searchActive && searchHitsByGroup[g.key] === 0"
              description="该分类下无匹配的配置项"
            />
          </div>
        </template>

        <!-- 重启提示 -->
        <el-affix v-if="restartHint" :offset="20" position="bottom">
          <el-alert
            type="warning"
            show-icon
            :closable="true"
            @close="restartHint = ''"
          >
            <template #title>
              <strong>部分改动需重启服务才能生效</strong>
            </template>
            <pre class="restart-cmd">{{ restartHint }}</pre>
          </el-alert>
        </el-affix>
      </main>
    </div>

    <!-- 审计日志 -->
    <AuditLogDrawer v-model="auditDrawerVisible" />

    <!-- 导入预览 -->
    <ImportPreviewDialog
      v-model="importDialogVisible"
      :current-values="rawValuesForExport"
      @imported="onImported"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Setting, Message, BellFilled, ChatDotRound, Lock,
  Document, Download, Upload, Check,
} from '@element-plus/icons-vue'
import {
  getConfigsGrouped, batchUpdateConfigs, exportConfigs,
  type GroupedConfigItem,
} from '@/api/system'
import {
  CONFIG_GROUPS, SYSTEM_CONFIG_META,
  resolveMeta, parseValue, serializeValue,
  type ConfigGroup as ConfigGroupKey,
} from '@/config/system_config_meta'
import ConfigGroup from './components/ConfigGroup.vue'
import AuditLogDrawer from './components/AuditLogDrawer.vue'
import ImportPreviewDialog from './components/ImportPreviewDialog.vue'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)

/** 当前编辑的运行时值（按 key 存原生类型） */
const values = reactive<Record<string, any>>({})
/** 后端返回的原始字符串值（用于 dirty 判断与 diff） */
const originalValues = reactive<Record<string, string>>({})
/** 修改人 / 时间映射 */
const auditMap = reactive<Record<string, { name: string; time: string }>>({})

/** dirty 集合（key） */
const dirtyKeys = ref<Set<string>>(new Set())

const currentGroup = ref<ConfigGroupKey>('basic')
const searchText = ref('')
const searchActive = computed(() => searchText.value.trim().length > 0)
const highlightKey = ref<string>('')

const auditDrawerVisible = ref(false)
const importDialogVisible = ref(false)
const restartHint = ref('')

const groupRefs = ref<InstanceType<typeof ConfigGroup>[]>([])

// ---- 计算 ----

const dirtyByGroup = computed<Record<string, number>>(() => {
  const result: Record<string, number> = {}
  CONFIG_GROUPS.forEach(g => result[g.key] = 0)
  dirtyKeys.value.forEach(k => {
    const g = resolveMeta(k).group
    result[g] = (result[g] || 0) + 1
  })
  return result
})

/** 搜索命中的 key 集合 */
const searchHitsSet = computed<Set<string>>(() => {
  const q = searchText.value.trim().toLowerCase()
  if (!q) return new Set()
  const hits = new Set<string>()
  Object.entries(SYSTEM_CONFIG_META).forEach(([k, m]) => {
    if (
      k.toLowerCase().includes(q)
      || m.label.toLowerCase().includes(q)
      || (m.hint || '').toLowerCase().includes(q)
    ) {
      hits.add(k)
    }
  })
  return hits
})

const searchHitsByGroup = computed<Record<string, number>>(() => {
  const result: Record<string, number> = {}
  CONFIG_GROUPS.forEach(g => result[g.key] = 0)
  searchHitsSet.value.forEach(k => {
    const g = resolveMeta(k).group
    result[g] = (result[g] || 0) + 1
  })
  return result
})

/** 用于导出对比的「key -> 字符串值」映射（取后端原始值） */
const rawValuesForExport = computed<Record<string, string>>(() => ({ ...originalValues }))

// ---- 加载 ----

async function loadAll() {
  loading.value = true
  try {
    const res = await getConfigsGrouped()
    Object.keys(values).forEach(k => delete values[k])
    Object.keys(originalValues).forEach(k => delete originalValues[k])
    Object.keys(auditMap).forEach(k => delete auditMap[k])

    Object.values(res.groups).flat().forEach((c: GroupedConfigItem) => {
      const meta = resolveMeta(c.config_key)
      values[c.config_key] = parseValue(c.config_value, meta.uiType)
      originalValues[c.config_key] = c.config_value ?? ''
      if (c.updated_by_name || c.updated_at) {
        auditMap[c.config_key] = {
          name: c.updated_by_name || '',
          time: c.updated_at || '',
        }
      }
    })
    dirtyKeys.value = new Set()
  } catch (e: any) {
    ElMessage.error(e?.message || '加载配置失败')
  } finally {
    loading.value = false
  }
}

// ---- 事件处理 ----

function onFieldChange(key: string, value: any) {
  values[key] = value
  const meta = resolveMeta(key)
  const newSerialized = serializeValue(value, meta.uiType)
  const original = originalValues[key] ?? ''
  if (newSerialized === original) {
    dirtyKeys.value.delete(key)
  } else {
    dirtyKeys.value.add(key)
  }
  // 触发响应式更新
  dirtyKeys.value = new Set(dirtyKeys.value)
}

function onGroupSelect(key: string) {
  currentGroup.value = key as ConfigGroupKey
  highlightKey.value = ''
}

function onSearchChange() {
  highlightKey.value = ''
  // 自动跳到第一个有命中的分类
  const q = searchText.value.trim()
  if (!q) return
  const hits = searchHitsByGroup.value
  const firstHitGroup = CONFIG_GROUPS.find(g => hits[g.key] > 0)
  if (firstHitGroup) {
    currentGroup.value = firstHitGroup.key
    // 滚动到第一个命中
    const firstKey = [...searchHitsSet.value][0]
    if (firstKey) {
      highlightKey.value = firstKey
      setTimeout(() => {
        const el = document.querySelector(`[data-config-key="${firstKey}"]`)
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 100)
    }
  }
}

async function onSaveAll() {
  if (dirtyKeys.value.size === 0) return
  const items: Record<string, string> = {}
  const restartItems: string[] = []

  dirtyKeys.value.forEach(k => {
    const meta = resolveMeta(k)
    items[k] = serializeValue(values[k], meta.uiType)
    if (meta.restartRequired) restartItems.push(k)
  })

  saving.value = true
  try {
    const res = await batchUpdateConfigs(items)
    ElMessage.success(`已保存 ${res.updated} 项配置`)

    // 同步原始值
    Object.entries(items).forEach(([k, v]) => {
      originalValues[k] = v
      auditMap[k] = { name: '我', time: new Date().toISOString() }
    })

    // 重新锁定敏感字段
    const sensitiveKeys = [...dirtyKeys.value].filter(k => resolveMeta(k).uiType === 'sensitive')
    if (sensitiveKeys.length > 0) {
      groupRefs.value.forEach(g => g?.lockSensitiveFields?.(sensitiveKeys))
    }

    dirtyKeys.value = new Set()

    // 重启提示
    if (restartItems.length > 0) {
      const lines = restartItems.map(k => {
        const m = resolveMeta(k)
        return `• ${m.label}（${k}）：${m.restartHint || '需重启相关服务'}`
      })
      restartHint.value = lines.join('\n')
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onDiscardAll() {
  try {
    await ElMessageBox.confirm(
      `确定放弃 ${dirtyKeys.value.size} 项未保存的改动？`,
      '放弃改动',
      { type: 'warning', confirmButtonText: '放弃', cancelButtonText: '继续编辑' }
    )
    // 恢复原始值
    dirtyKeys.value.forEach(k => {
      const meta = resolveMeta(k)
      values[k] = parseValue(originalValues[k], meta.uiType)
    })
    dirtyKeys.value = new Set()
    ElMessage.success('已放弃改动')
  } catch { /* 取消 */ }
}

async function onExport() {
  try {
    const res = await exportConfigs()
    const blob = new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `system_configs_${new Date().toISOString().slice(0,10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success(`已导出 ${res.total} 项配置`)
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  }
}

function onImported() {
  loadAll()
}

function resolveIcon(name: string) {
  return ({ Setting, Message, BellFilled, ChatDotRound, Lock } as any)[name] || Setting
}

// ---- 离开拦截 ----

function beforeUnloadHandler(e: BeforeUnloadEvent) {
  if (dirtyKeys.value.size > 0) {
    e.preventDefault()
    e.returnValue = ''
  }
}

onBeforeRouteLeave(async (_to, _from, next) => {
  if (dirtyKeys.value.size === 0) return next()
  try {
    await ElMessageBox.confirm(
      `还有 ${dirtyKeys.value.size} 项未保存的改动，确定离开？`,
      '未保存提示',
      { type: 'warning', confirmButtonText: '离开', cancelButtonText: '留下' }
    )
    next()
  } catch {
    next(false)
  }
})

onMounted(() => {
  window.addEventListener('beforeunload', beforeUnloadHandler)
  loadAll()
})
onUnmounted(() => {
  window.removeEventListener('beforeunload', beforeUnloadHandler)
})
</script>

<style scoped>
.config-layout {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 220px);
  min-height: 500px;
}

.config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
  border-radius: 6px 6px 0 0;
  gap: 16px;
  flex-wrap: wrap;
}
.header-left { display: flex; align-items: center; gap: 16px; flex: 1; min-width: 0; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; color: var(--el-text-color-primary); }
.search-input { max-width: 400px; }
.header-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.save-badge { margin-left: 6px; }

.config-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  background: var(--el-bg-color);
  border-radius: 0 0 6px 6px;
}

.config-nav {
  width: 240px;
  flex-shrink: 0;
  border-right: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  background: var(--el-fill-color-lighter);
}
.nav-menu { border-right: none; flex: 1; }
.nav-menu :deep(.el-menu-item) {
  position: relative;
  height: 48px;
  line-height: 48px;
}
.nav-badge {
  position: absolute;
  right: 16px;
  top: 50%;
  transform: translateY(-50%);
}
.nav-footer { padding: 12px; }

.config-main {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: var(--el-bg-color-page);
}
.group-section { display: flex; flex-direction: column; gap: 12px; }

.restart-cmd {
  margin: 8px 0 0;
  padding: 8px;
  background: var(--el-fill-color-darker);
  color: var(--el-text-color-primary);
  border-radius: 4px;
  font-family: monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}

/* 响应式：移动端折叠侧栏 */
@media (max-width: 768px) {
  .config-body { flex-direction: column; }
  .config-nav { width: 100%; border-right: none; border-bottom: 1px solid var(--el-border-color-lighter); }
  .nav-menu :deep(.el-menu) { display: flex; overflow-x: auto; }
  .nav-menu :deep(.el-menu-item) { white-space: nowrap; }
  .header-left { flex-direction: column; align-items: stretch; }
  .search-input { max-width: 100%; }
}
</style>
