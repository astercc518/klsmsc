<template>
  <div class="stat-card" :class="[variant]">
    <div class="stat-icon">
      <slot name="icon">
        <component v-if="icon" :is="icon" />
      </slot>
    </div>
    <div class="stat-info">
      <span class="stat-value">{{ value }}</span>
      <span class="stat-label">{{ label }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/** 统计卡片 - 用于 Dashboard、Send 等页面的数据展示 */
defineProps<{
  value: string | number
  label: string
  variant?: 'default' | 'today' | 'success' | 'rate' | 'cost'
  icon?: object
}>()
</script>

<style scoped>
.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.stat-card:hover {
  border-color: var(--el-border-color);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}
.stat-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 12px;
  flex-shrink: 0;
}
.stat-icon :deep(svg) {
  width: 24px;
  height: 24px;
  color: currentColor;
}
.stat-card.today .stat-icon { background: rgba(59, 130, 246, 0.12); color: #3b82f6; }
.stat-card.success .stat-icon { background: rgba(34, 197, 94, 0.12); color: #22c55e; }
.stat-card.rate .stat-icon { background: rgba(168, 85, 247, 0.12); color: #a855f7; }
.stat-card.cost .stat-icon { background: rgba(249, 115, 22, 0.12); color: #f97316; }
.stat-card.default .stat-icon { background: var(--el-fill-color-light); color: var(--el-text-color-regular); }
.stat-info { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.stat-value { font-size: 1.5rem; font-weight: 700; color: var(--el-text-color-primary); line-height: 1.2; }
.stat-label { font-size: 0.85rem; color: var(--el-text-color-secondary); }
</style>
