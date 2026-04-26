<template>
  <el-card v-if="visibleKeys.length > 0" shadow="never" class="config-group" :id="`group-${subgroup.key}`">
    <template #header>
      <div class="group-header">
        <span class="group-title">{{ subgroup.label }}</span>
        <span v-if="subgroup.description" class="group-description">{{ subgroup.description }}</span>
        <el-tag v-if="dirtyCount > 0" size="small" type="primary" effect="dark">
          {{ dirtyCount }} 项未保存
        </el-tag>
      </div>
    </template>
    <ConfigField
      v-for="key in visibleKeys"
      :key="key"
      :config-key="key"
      :meta="resolveMeta(key)"
      :model-value="values[key]"
      :dirty="dirtyKeys.has(key)"
      :highlight="highlightKey === key"
      :updated-by-name="auditMap[key]?.name"
      :updated-at="auditMap[key]?.time"
      @update:model-value="onChange(key, $event)"
      :ref="(el: any) => { if (el) fieldRefs[key] = el }"
    />
  </el-card>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import ConfigField from './ConfigField.vue'
import { resolveMeta, keysOfGroup, type ConfigGroup } from '@/config/system_config_meta'

const props = defineProps<{
  group: ConfigGroup
  subgroup: { key: string; label: string; description?: string }
  values: Record<string, any>
  dirtyKeys: Set<string>
  /** key -> { name, time } */
  auditMap: Record<string, { name: string; time: string }>
  /** 搜索高亮 */
  highlightKey?: string
  /** 搜索过滤后该组内可见的 key 集合（undefined 表示全部可见） */
  visibleKeyFilter?: Set<string>
}>()

const emit = defineEmits<{
  (e: 'change', key: string, value: any): void
}>()

const fieldRefs = ref<Record<string, InstanceType<typeof ConfigField>>>({})

const visibleKeys = computed(() => {
  const groupKeys = keysOfGroup(props.group).filter(k => resolveMeta(k).subgroup === props.subgroup.key)
  if (!props.visibleKeyFilter) return groupKeys
  return groupKeys.filter(k => props.visibleKeyFilter!.has(k))
})

const dirtyCount = computed(() => visibleKeys.value.filter(k => props.dirtyKeys.has(k)).length)

function onChange(key: string, value: any) {
  emit('change', key, value)
}

defineExpose({
  /** 给定 key 列表，重新锁定对应的敏感字段（保存成功后调用） */
  lockSensitiveFields(keys: string[]) {
    keys.forEach(k => fieldRefs.value[k]?.lockSensitive?.())
  },
})
</script>

<style scoped>
.config-group { margin-bottom: 16px; border-radius: 8px; }
.config-group :deep(.el-card__header) { padding: 14px 20px; background: var(--el-fill-color-lighter); }
.config-group :deep(.el-card__body) { padding: 4px 20px; }
.group-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.group-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.group-description {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
