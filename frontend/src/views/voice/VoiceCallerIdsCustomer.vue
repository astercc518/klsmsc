<template>
  <div class="voice-page">
    <div class="page-header">
      <h1 class="page-title">{{ $t('menu.voiceCallerIdsCustomer') }}</h1>
      <p class="page-desc">{{ $t('voiceCustomer.callerIdsDesc') }}</p>
    </div>

    <el-alert type="info" :closable="false" class="mb-4">{{ $t('voiceCustomer.callerIdsReadonly') }}</el-alert>

    <el-card v-loading="loading">
      <el-table :data="items" stripe>
        <el-table-column prop="number_e164" :label="$t('voice.callerNumber')" />
        <el-table-column prop="label" :label="$t('common.remark')" />
        <el-table-column prop="trunk_ref" :label="$t('voice.trunkRefCol')" show-overflow-tooltip />
        <el-table-column prop="voice_route_id" :label="$t('voice.voiceRouteIdCol')" width="110" />
        <el-table-column prop="status" :label="$t('common.status')" width="100" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { getVoiceCallerIdsCustomer } from '@/api/voice-customer'

const { t } = useI18n()
const loading = ref(false)
const items = ref<any[]>([])

onMounted(async () => {
  loading.value = true
  try {
    const res: any = await getVoiceCallerIdsCustomer()
    items.value = res?.items || []
  } catch {
    ElMessage.error(t('common.failed'))
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.voice-page {
  max-width: 900px;
}
.page-header {
  margin-bottom: 20px;
}
.page-title {
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 8px;
}
.page-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}
.mb-4 {
  margin-bottom: 16px;
}
</style>
