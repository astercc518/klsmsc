<template>
  <!-- 桌面端：原样展示筛选栏 -->
  <div v-if="!isMobile" class="filter-card mfd-desktop">
    <slot />
  </div>

  <!-- 移动端：折叠为「筛选」按钮 + 抽屉 -->
  <template v-else>
    <div class="mfd-trigger-bar">
      <button class="mfd-trigger" @click="open = true" type="button">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M2 3H14M4 8H12M6 13H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
        <span>{{ label || '筛选' }}</span>
        <span v-if="activeCount > 0" class="mfd-badge">{{ activeCount }}</span>
      </button>
      <slot name="trigger-extra" />
    </div>

    <el-drawer
      v-model="open"
      :title="label || '筛选条件'"
      direction="rtl"
      :size="drawerSize"
      :append-to-body="true"
      :destroy-on-close="false"
      class="mfd-drawer"
    >
      <div class="mfd-drawer-body">
        <slot />
      </div>
      <template #footer>
        <div class="mfd-drawer-footer">
          <button class="mfd-btn mfd-btn-reset" @click="emit('reset')" type="button">
            {{ resetLabel || '重置' }}
          </button>
          <button class="mfd-btn mfd-btn-apply" @click="handleApply" type="button">
            {{ applyLabel || '应用筛选' }}
          </button>
        </div>
      </template>
    </el-drawer>
  </template>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useBreakpoint } from '@/composables/useBreakpoint'

interface Props {
  /** 当前生效的筛选条件数量，用于触发按钮上显示徽标 */
  activeCount?: number
  /** 触发按钮文字 */
  label?: string
  resetLabel?: string
  applyLabel?: string
}
const props = withDefaults(defineProps<Props>(), { activeCount: 0 })

const emit = defineEmits<{
  (e: 'apply'): void
  (e: 'reset'): void
}>()

const { isMobile } = useBreakpoint()
const open = ref(false)

const drawerSize = computed(() => {
  if (typeof window === 'undefined') return '85%'
  return Math.min(window.innerWidth, 420) + 'px'
})

const handleApply = () => {
  emit('apply')
  open.value = false
}
</script>

<style scoped>
.mfd-desktop { /* 由各页面自身的 .filter-card 样式接管 */ }

.mfd-trigger-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.mfd-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 10px;
  border: 1px solid var(--border-default, rgba(0,0,0,0.1));
  background: var(--bg-secondary, #fff);
  color: var(--text-primary, #0a1425);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  position: relative;
}
.mfd-trigger:active { transform: scale(0.98); }
.mfd-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: #2f6df0;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  margin-left: 2px;
}

.mfd-drawer-body {
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.mfd-drawer-body :deep(.filter-content) {
  display: flex;
  flex-direction: column;
  gap: 14px;
  align-items: stretch;
}
.mfd-drawer-body :deep(.filter-item) {
  min-width: 0;
  width: 100%;
}
.mfd-drawer-body :deep(.filter-item .el-select),
.mfd-drawer-body :deep(.filter-item .el-input),
.mfd-drawer-body :deep(.filter-item .el-input-number),
.mfd-drawer-body :deep(.filter-item .el-date-editor) {
  width: 100% !important;
}
.mfd-drawer-body :deep(.filter-actions) {
  display: none;
}

.mfd-drawer-footer {
  display: flex;
  gap: 10px;
}
.mfd-btn {
  flex: 1;
  padding: 12px 16px;
  border-radius: 10px;
  border: 1px solid var(--border-default, rgba(0,0,0,0.1));
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  min-height: 44px;
}
.mfd-btn-reset {
  background: var(--bg-secondary, #fff);
  color: var(--text-secondary, #5f6c7c);
}
.mfd-btn-apply {
  flex: 2;
  background: var(--el-color-primary, #2f6df0);
  border-color: var(--el-color-primary, #2f6df0);
  color: #fff;
}
</style>
