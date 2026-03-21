<template>
  <div class="system-index">
    <div class="page-header">
      <h2 class="page-title">{{ $t('system.title') }}</h2>
    </div>
    <el-tabs v-model="activeTab" class="system-tabs">
      <el-tab-pane :label="$t('system.tabs.config')" name="config">
        <SystemConfig />
      </el-tab-pane>
      <el-tab-pane :label="$t('system.tabs.logs')" name="logs">
        <SystemLogs />
      </el-tab-pane>
      <el-tab-pane :label="$t('system.tabs.services')" name="services">
        <SystemServices />
      </el-tab-pane>
      <el-tab-pane :label="$t('system.tabs.security')" name="security">
        <SystemSecurity />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import SystemConfig from './Config.vue'
import SystemLogs from './Logs.vue'
import SystemServices from './Services.vue'
import SystemSecurity from './Security.vue'

const activeTab = ref('config')
</script>

<style scoped>
.system-index {
  width: 100%;
  padding: 0 4px;
}
.page-header {
  margin-bottom: 20px;
}
.page-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin: 0;
}
.system-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}
.system-tabs :deep(.el-tabs__content) {
  padding: 24px 0 0;
}
.system-tabs :deep(.el-tabs__item) {
  font-size: 14px;
}
.system-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}
</style>
