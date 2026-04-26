<template>
  <el-drawer
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    title="📋 配置变更审计日志"
    direction="rtl"
    size="640px"
    :destroy-on-close="false"
  >
    <div class="audit-toolbar">
      <el-input
        v-model="filterKey"
        placeholder="按 config_key 过滤（精确匹配）"
        clearable
        style="width: 280px"
        @keyup.enter="loadLogs(1)"
        @clear="loadLogs(1)"
      />
      <el-button type="primary" @click="loadLogs(1)" :loading="loading">查询</el-button>
      <el-button @click="loadLogs(page)" :icon="Refresh">刷新</el-button>
    </div>

    <el-empty v-if="!loading && logs.length === 0" description="暂无变更记录" />

    <el-timeline v-else class="audit-timeline">
      <el-timeline-item
        v-for="log in logs"
        :key="log.id"
        :timestamp="formatTime(log.created_at)"
        :type="actionType(log.action)"
        :hollow="log.action !== 'delete'"
      >
        <div class="audit-card">
          <div class="audit-card-header">
            <code class="key-tag">{{ log.config_key }}</code>
            <el-tag size="small" :type="actionType(log.action)" effect="dark">{{ actionLabel(log.action) }}</el-tag>
            <span class="admin">by {{ log.admin_name || '系统' }}</span>
          </div>
          <div class="audit-diff">
            <div class="diff-row">
              <span class="diff-label">旧值</span>
              <code class="diff-old">{{ truncate(log.old_value) }}</code>
            </div>
            <div class="diff-row">
              <span class="diff-label">新值</span>
              <code class="diff-new">{{ truncate(log.new_value) }}</code>
            </div>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>

    <div v-if="total > pageSize" class="pagination">
      <el-pagination
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next, total"
        small
        @current-change="loadLogs"
      />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { getConfigAuditLogs, type AuditLogItem } from '@/api/system'

const props = defineProps<{
  modelValue: boolean
  /** 打开时若指定，自动按此 key 过滤 */
  defaultKey?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
}>()

const filterKey = ref('')
const logs = ref<AuditLogItem[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = 20

watch(() => props.modelValue, async (open) => {
  if (open) {
    filterKey.value = props.defaultKey || ''
    await loadLogs(1)
  }
})

async function loadLogs(p = 1) {
  page.value = p
  loading.value = true
  try {
    const res = await getConfigAuditLogs({
      config_key: filterKey.value || undefined,
      page: p,
      limit: pageSize,
    })
    logs.value = res.items
    total.value = res.total
  } catch (e: any) {
    ElMessage.error(e?.message || '加载审计日志失败')
  } finally {
    loading.value = false
  }
}

function actionType(action: string): 'success' | 'primary' | 'danger' | 'info' {
  if (action === 'create') return 'success'
  if (action === 'update') return 'primary'
  if (action === 'delete') return 'danger'
  return 'info'
}

function actionLabel(action: string): string {
  return ({ create: '新建', update: '修改', delete: '删除' } as any)[action] || action
}

function truncate(v: string | null): string {
  if (v === null || v === undefined) return '(空)'
  const s = String(v)
  return s.length > 200 ? s.slice(0, 200) + '...' : s
}

function formatTime(iso: string): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN')
}
</script>

<style scoped>
.audit-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.audit-timeline { padding: 0 4px; }
.audit-card {
  border-radius: 6px;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
}
.audit-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.key-tag {
  font-family: monospace;
  background: var(--el-fill-color);
  padding: 2px 6px;
  border-radius: 3px;
  color: var(--el-text-color-primary);
}
.admin {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: auto;
}
.audit-diff {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-family: monospace;
  font-size: 12px;
}
.diff-row { display: flex; gap: 8px; align-items: flex-start; }
.diff-label {
  font-weight: 600;
  flex-shrink: 0;
  width: 36px;
  color: var(--el-text-color-secondary);
}
.diff-old {
  flex: 1;
  background: var(--el-color-danger-light-9);
  padding: 4px 6px;
  border-radius: 3px;
  word-break: break-all;
  text-decoration: line-through;
  color: var(--el-color-danger);
}
.diff-new {
  flex: 1;
  background: var(--el-color-success-light-9);
  padding: 4px 6px;
  border-radius: 3px;
  word-break: break-all;
  color: var(--el-color-success);
}
.pagination {
  margin-top: 16px;
  text-align: center;
}
</style>
