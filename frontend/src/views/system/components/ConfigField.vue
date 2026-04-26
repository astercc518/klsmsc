<template>
  <div
    class="config-field"
    :class="{ 'is-dirty': dirty, 'is-highlight': highlight }"
    :data-config-key="configKey"
  >
    <!-- 标签 + 提示 + 元信息 -->
    <div class="field-header">
      <div class="field-label">
        <span class="label-text">{{ meta.label }}</span>
        <el-tooltip v-if="meta.hint" :content="meta.hint" placement="top">
          <el-icon class="hint-icon"><QuestionFilled /></el-icon>
        </el-tooltip>
        <el-tag v-if="meta.restartRequired" size="small" type="warning" effect="plain" class="restart-tag">
          需重启
        </el-tag>
        <el-tag v-if="dirty" size="small" type="primary" effect="plain" class="dirty-tag">
          未保存
        </el-tag>
      </div>
      <div class="field-meta">
        <span class="config-key">{{ configKey }}</span>
        <span v-if="updatedByName || updatedAt" class="audit-info">
          · 上次修改：{{ updatedByName || '系统' }}
          <span v-if="updatedAt"> {{ formatTime(updatedAt) }}</span>
        </span>
      </div>
    </div>

    <!-- 控件 -->
    <div class="field-control">
      <!-- boolean -->
      <el-switch
        v-if="meta.uiType === 'boolean'"
        :model-value="modelValue"
        @update:model-value="emit('update:modelValue', $event)"
        active-text="开启"
        inactive-text="关闭"
        inline-prompt
      />

      <!-- number -->
      <el-input-number
        v-else-if="meta.uiType === 'number'"
        :model-value="modelValue"
        @update:model-value="emit('update:modelValue', $event ?? 0)"
        :min="meta.validation?.min"
        :max="meta.validation?.max"
        :step="meta.validation?.step ?? 1"
        :placeholder="meta.placeholder"
        controls-position="right"
        style="width: 240px"
      />

      <!-- enum -->
      <el-select
        v-else-if="meta.uiType === 'enum'"
        :model-value="modelValue"
        @update:model-value="emit('update:modelValue', $event)"
        :placeholder="meta.placeholder || '请选择'"
        style="width: 240px"
      >
        <el-option
          v-for="opt in meta.options"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>

      <!-- text 长文本 -->
      <div v-else-if="meta.uiType === 'text'" class="text-wrapper">
        <el-input
          :model-value="modelValue"
          @update:model-value="emit('update:modelValue', $event)"
          type="textarea"
          :rows="6"
          :maxlength="meta.maxLength"
          :placeholder="meta.placeholder"
          show-word-limit
          resize="vertical"
        />
      </div>

      <!-- sensitive -->
      <SensitiveInput
        v-else-if="meta.uiType === 'sensitive'"
        :model-value="modelValue || ''"
        @update:model-value="emit('update:modelValue', $event)"
        :placeholder="meta.placeholder"
        ref="sensitiveRef"
      />

      <!-- string 默认 -->
      <el-input
        v-else
        :model-value="modelValue"
        @update:model-value="emit('update:modelValue', $event)"
        :placeholder="meta.placeholder"
        clearable
        style="width: 360px"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import SensitiveInput from './SensitiveInput.vue'
import type { ConfigMeta } from '@/config/system_config_meta'

defineProps<{
  configKey: string
  meta: ConfigMeta
  modelValue: any
  dirty?: boolean
  highlight?: boolean
  updatedByName?: string
  updatedAt?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: any): void
}>()

const sensitiveRef = ref<InstanceType<typeof SensitiveInput> | null>(null)

function formatTime(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const mins = Math.floor(diffMs / 60000)
    if (mins < 1) return '刚刚'
    if (mins < 60) return `${mins} 分钟前`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours} 小时前`
    const days = Math.floor(hours / 24)
    if (days < 30) return `${days} 天前`
    return d.toLocaleDateString()
  } catch {
    return iso
  }
}

defineExpose({
  /** 保存后重新锁定敏感字段 */
  lockSensitive() { sensitiveRef.value?.lock() },
})
</script>

<style scoped>
.config-field {
  padding: 16px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
  transition: background 0.3s;
}
.config-field:last-child { border-bottom: none; }
.config-field.is-dirty { background: var(--el-color-primary-light-9); padding-left: 12px; padding-right: 12px; margin-left: -12px; margin-right: -12px; border-radius: 4px; }
.config-field.is-highlight { background: var(--el-color-warning-light-9); animation: pulse 1.5s ease-out 1; }

@keyframes pulse {
  0% { box-shadow: 0 0 0 4px var(--el-color-warning-light-7); }
  100% { box-shadow: 0 0 0 0 transparent; }
}

.field-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 4px;
}
.field-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  font-size: 14px;
  color: var(--el-text-color-primary);
}
.hint-icon {
  color: var(--el-text-color-secondary);
  cursor: help;
  font-size: 14px;
}
.restart-tag, .dirty-tag { margin-left: 4px; }
.field-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.config-key {
  font-family: monospace;
  background: var(--el-fill-color-lighter);
  padding: 1px 6px;
  border-radius: 3px;
}
.audit-info { margin-left: 4px; }
.field-control { padding-left: 0; }
.text-wrapper { width: 100%; max-width: 720px; }
</style>
