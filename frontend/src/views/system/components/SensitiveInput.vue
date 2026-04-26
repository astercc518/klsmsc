<template>
  <div class="sensitive-input">
    <!-- 锁定状态：显示掩码 + 解锁按钮 -->
    <div v-if="locked" class="locked-row">
      <code class="masked">{{ displayMasked }}</code>
      <el-button size="small" type="primary" plain @click="onUnlock">
        <el-icon><Edit /></el-icon> 修改
      </el-button>
      <el-tooltip content="复制当前值（明文）" placement="top">
        <el-button size="small" plain @click="onCopy" :disabled="!modelValue">
          <el-icon><DocumentCopy /></el-icon>
        </el-button>
      </el-tooltip>
      <el-tooltip :content="revealed ? '隐藏明文' : '显示明文'" placement="top">
        <el-button size="small" plain @click="revealed = !revealed">
          <el-icon><View v-if="!revealed" /><Hide v-else /></el-icon>
        </el-button>
      </el-tooltip>
    </div>

    <!-- 编辑状态：明文输入 + 取消按钮 -->
    <div v-else class="editing-row">
      <el-input
        v-model="proxyValue"
        :placeholder="placeholder || '输入新的值'"
        :show-password="!showPlain"
        clearable
        autofocus
      />
      <el-button size="small" plain @click="showPlain = !showPlain">
        <el-icon><View v-if="!showPlain" /><Hide v-else /></el-icon>
      </el-button>
      <el-button size="small" plain @click="onCancelEdit">取消</el-button>
    </div>

    <div v-if="!locked" class="warning-tip">
      <el-icon><Warning /></el-icon>
      <span>保存后将完全替换原值；保存前请确认无误。</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, DocumentCopy, View, Hide, Warning } from '@element-plus/icons-vue'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  /** 是否锁定（外部控制初始状态，默认 true） */
  initialLocked?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'unlock'): void
  (e: 'cancel'): void
}>()

const locked = ref(props.initialLocked !== false)
const revealed = ref(false)
const showPlain = ref(false)

const proxyValue = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v),
})

const displayMasked = computed(() => {
  if (revealed.value) return props.modelValue || '(空)'
  if (!props.modelValue) return '(未设置)'
  if (props.modelValue.length <= 8) return '••••••••'
  return props.modelValue.slice(0, 4) + '••••' + props.modelValue.slice(-4)
})

watch(() => props.initialLocked, v => {
  if (v !== undefined) locked.value = v
})

async function onUnlock() {
  try {
    await ElMessageBox.confirm(
      '该字段为敏感凭证，修改后将立即生效（保存后）。是否继续？',
      '修改敏感字段',
      { type: 'warning', confirmButtonText: '继续修改', cancelButtonText: '取消' }
    )
    locked.value = false
    showPlain.value = false
    emit('unlock')
  } catch { /* 用户取消 */ }
}

function onCancelEdit() {
  locked.value = true
  emit('cancel')
}

async function onCopy() {
  if (!props.modelValue) return
  try {
    await navigator.clipboard.writeText(props.modelValue)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('浏览器不支持复制 API')
  }
}

defineExpose({
  /** 父组件保存成功后调用，重新锁定 */
  lock() { locked.value = true; showPlain.value = false; revealed.value = false },
})
</script>

<style scoped>
.sensitive-input { width: 100%; }
.locked-row, .editing-row { display: flex; align-items: center; gap: 8px; }
.masked {
  flex: 1;
  padding: 6px 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-family: monospace;
  font-size: 13px;
  color: var(--el-text-color-regular);
  border: 1px solid var(--el-border-color-lighter);
  user-select: all;
}
.warning-tip {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-color-warning);
  display: flex;
  align-items: center;
  gap: 4px;
}
.editing-row .el-input { flex: 1; }
</style>
