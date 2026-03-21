<template>
  <div class="system-services">
    <div class="services-header">
      <el-button type="primary" @click="loadData" :loading="loading" :icon="Refresh">
        {{ $t('common.refresh') }}
      </el-button>
    </div>
    <el-row :gutter="16" v-loading="loading" class="services-grid">
      <el-col v-for="(svc, key) in services" :key="key" :xs="24" :sm="12" :md="12">
        <el-card shadow="hover" class="service-card" :class="{ 'is-ok': svc.status === 'ok', 'is-error': svc.status !== 'ok' }">
          <div class="service-body">
            <div class="service-icon">
              <el-icon v-if="svc.status === 'ok'" color="var(--el-color-success)" :size="32"><CircleCheck /></el-icon>
              <el-icon v-else color="var(--el-color-danger)" :size="32"><CircleClose /></el-icon>
            </div>
            <div class="service-info">
              <div class="service-name">{{ svc.name }}</div>
              <el-tag :type="svc.status === 'ok' ? 'success' : 'danger'" size="small" class="service-tag">
                {{ svc.status === 'ok' ? $t('system.services.normal') : $t('system.services.abnormal') }}
              </el-tag>
              <div class="service-message">{{ svc.message }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Refresh, CircleCheck, CircleClose } from '@element-plus/icons-vue'
import { getServicesStatus } from '@/api/system'

const loading = ref(false)
const services = ref<Record<string, { name: string; status: string; message: string }>>({})

const loadData = async () => {
  loading.value = true
  try {
    const res = await getServicesStatus()
    services.value = res.services
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.system-services { padding: 0; }
.services-header { margin-bottom: 20px; }
.services-grid { min-height: 120px; }
.services-grid .el-col { margin-bottom: 16px; }
.service-card { margin-bottom: 0; }
.service-card :deep(.el-card__body) { padding: 20px; }
.service-body { display: flex; align-items: flex-start; gap: 16px; }
.service-icon { flex-shrink: 0; }
.service-info { flex: 1; min-width: 0; }
.service-name { font-size: 16px; font-weight: 600; margin-bottom: 8px; color: var(--el-text-color-primary); }
.service-tag { margin-bottom: 8px; }
.service-message { font-size: 13px; color: var(--el-text-color-secondary); line-height: 1.5; }
</style>
