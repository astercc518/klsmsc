<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    title="📥 导入配置 — 变更预览"
    width="780px"
    :close-on-click-modal="false"
  >
    <div v-if="!parsedItems.length" class="upload-area">
      <el-upload
        drag
        :auto-upload="false"
        :on-change="onFileChange"
        :show-file-list="false"
        accept=".json"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">
          拖拽 JSON 文件到此处，或<em>点击选择</em>
        </div>
        <template #tip>
          <div class="upload-tip">
            JSON 格式：<code>{ "configs": [{"config_key":"...", "config_value":"..."}] }</code>
            <br>或直接是 <code>[{"config_key":"...", ...}]</code> 数组
          </div>
        </template>
      </el-upload>
    </div>

    <div v-else>
      <el-alert
        :title="`共 ${parsedItems.length} 项 — ${changedItems.length} 项变更，${unchangedCount} 项无变化`"
        :type="changedItems.length > 0 ? 'warning' : 'success'"
        :closable="false"
        show-icon
      />

      <el-table :data="changedItems" max-height="400" style="margin-top: 12px" stripe>
        <el-table-column label="配置键" prop="config_key" width="240">
          <template #default="{ row }">
            <code class="key-cell">{{ row.config_key }}</code>
          </template>
        </el-table-column>
        <el-table-column label="旧值" width="200">
          <template #default="{ row }">
            <code class="diff-old">{{ truncate(row.old_value) }}</code>
          </template>
        </el-table-column>
        <el-table-column label="新值">
          <template #default="{ row }">
            <code class="diff-new">{{ truncate(row.new_value) }}</code>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_new ? 'success' : 'primary'">
              {{ row.is_new ? '新增' : '更新' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="changedItems.length === 0" description="所有项与当前值相同，无需导入" />
    </div>

    <template #footer>
      <el-button v-if="parsedItems.length > 0" @click="reset">重新选择</el-button>
      <el-button @click="close">取消</el-button>
      <el-button
        type="primary"
        :disabled="changedItems.length === 0"
        :loading="submitting"
        @click="onConfirm"
      >
        确认导入 {{ changedItems.length }} 项
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { importConfigs } from '@/api/system'

const props = defineProps<{
  modelValue: boolean
  /** 当前所有配置（按 key -> value 的字符串映射），用于 diff */
  currentValues: Record<string, string>
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'imported', result: { created: number; updated: number; skipped: number }): void
}>()

const parsedItems = ref<any[]>([])
const submitting = ref(false)

const changedItems = computed(() => {
  return parsedItems.value
    .filter(it => it.config_key)
    .map(it => {
      const old_value = props.currentValues[it.config_key]
      const new_value = String(it.config_value ?? '')
      return {
        config_key: it.config_key,
        old_value: old_value ?? '(不存在)',
        new_value,
        is_new: old_value === undefined,
        changed: old_value !== new_value,
      }
    })
    .filter(it => it.changed)
})

const unchangedCount = computed(() => parsedItems.value.length - changedItems.value.length)

function onFileChange(file: any) {
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const text = e.target?.result as string
      const parsed = JSON.parse(text)
      let items: any[] = []
      if (Array.isArray(parsed)) {
        items = parsed
      } else if (parsed && Array.isArray(parsed.configs)) {
        items = parsed.configs
      } else {
        ElMessage.error('JSON 格式错误：应为数组或 {configs:[...]} 结构')
        return
      }
      parsedItems.value = items
    } catch (err: any) {
      ElMessage.error(`JSON 解析失败：${err.message}`)
    }
  }
  reader.readAsText(file.raw || file)
}

async function onConfirm() {
  if (changedItems.value.length === 0) return
  submitting.value = true
  try {
    const items = changedItems.value.map(it => ({
      config_key: it.config_key,
      config_value: it.new_value,
    }))
    const res = await importConfigs(items, true)
    ElMessage.success(`导入完成：新增 ${res.created} / 更新 ${res.updated} / 跳过 ${res.skipped}`)
    emit('imported', res)
    close()
  } catch (e: any) {
    ElMessage.error(e?.message || '导入失败')
  } finally {
    submitting.value = false
  }
}

function reset() {
  parsedItems.value = []
}

function close() {
  emit('update:modelValue', false)
  reset()
}

function truncate(v: string | null | undefined): string {
  if (v === null || v === undefined) return '(空)'
  const s = String(v)
  return s.length > 80 ? s.slice(0, 80) + '...' : s
}
</script>

<style scoped>
.upload-area { padding: 20px 0; }
.upload-tip {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.upload-tip code {
  background: var(--el-fill-color);
  padding: 2px 4px;
  border-radius: 3px;
}
.key-cell {
  font-family: monospace;
  background: var(--el-fill-color);
  padding: 2px 6px;
  border-radius: 3px;
}
.diff-old, .diff-new {
  font-family: monospace;
  font-size: 12px;
  padding: 2px 4px;
  border-radius: 3px;
  word-break: break-all;
  display: inline-block;
  max-width: 100%;
}
.diff-old { background: var(--el-color-danger-light-9); color: var(--el-color-danger); text-decoration: line-through; }
.diff-new { background: var(--el-color-success-light-9); color: var(--el-color-success); }
</style>
