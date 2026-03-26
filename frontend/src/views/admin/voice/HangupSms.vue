<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t('voice.hangupSmsTitle') }}</h1>
      <p class="page-desc">{{ $t('voice.hangupSmsDesc') }}</p>
    </div>
    <div class="table-card">
      <el-button type="primary" @click="show = true">{{ $t('common.add') }}</el-button>
      <el-table :data="items" v-loading="loading" stripe class="mt-2">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" :label="$t('common.name')" />
        <el-table-column prop="enabled" :label="$t('common.enabled')" width="90" />
        <el-table-column prop="template_body" :label="$t('voice.template')" show-overflow-tooltip />
      </el-table>
    </div>
    <el-dialog v-model="show" :title="$t('voice.addHangupRule')" width="560px">
      <el-form label-width="140px">
        <el-form-item :label="$t('voice.accountIdColOptional')">
          <el-input v-model.number="form.account_id" type="number" clearable />
        </el-form-item>
        <el-form-item :label="$t('common.name')">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item :label="$t('voice.template')">
          <el-input v-model="form.template_body" type="textarea" :rows="4" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="show = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submit">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getVoiceHangupSmsRules, createVoiceHangupSmsRule } from '@/api/voice-admin'

const loading = ref(false)
const items = ref<any[]>([])
const show = ref(false)
const form = ref<{ account_id?: number; name: string; template_body: string }>({
  name: '',
  template_body: '感谢您的接听，{callee} 通话时长 {duration} 秒。',
})

async function load() {
  loading.value = true
  try {
    const res: any = await getVoiceHangupSmsRules()
    items.value = res.items || []
  } finally {
    loading.value = false
  }
}

async function submit() {
  await createVoiceHangupSmsRule({
    account_id: form.value.account_id || undefined,
    name: form.value.name,
    template_body: form.value.template_body,
    match_answered_only: true,
    enabled: true,
    priority: 0,
  })
  ElMessage.success('ok')
  show.value = false
  load()
}

onMounted(load)
</script>
<style scoped>
.mt-2 { margin-top: 12px; }
</style>
