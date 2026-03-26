<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t('voice.dncTitle') }}</h1>
      <p class="page-desc">{{ $t('voice.dncDesc') }}</p>
    </div>
    <div class="table-card">
      <el-button type="primary" @click="show = true">{{ $t('common.add') }}</el-button>
      <el-table :data="items" v-loading="loading" stripe class="mt-2">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="account_id" :label="$t('voice.accountIdCol')" width="100" />
        <el-table-column prop="phone_e164" :label="$t('voice.phone')" />
        <el-table-column :label="$t('common.action')" width="120">
          <template #default="{ row }">
            <el-button type="danger" size="small" @click="remove(row)">{{ $t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <el-dialog v-model="show" :title="$t('voice.addDnc')" width="440px">
      <el-form label-width="120px">
        <el-form-item :label="$t('voice.accountIdCol')">
          <el-input v-model.number="form.account_id" type="number" />
        </el-form-item>
        <el-form-item :label="$t('voice.phone')">
          <el-input v-model="form.phone_e164" placeholder="+8613800138000" />
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { getVoiceDnc, createVoiceDnc, deleteVoiceDnc } from '@/api/voice-admin'

const loading = ref(false)
const items = ref<any[]>([])
const show = ref(false)
const form = ref({ account_id: 1, phone_e164: '' })

async function load() {
  loading.value = true
  try {
    const res: any = await getVoiceDnc()
    items.value = res.items || []
  } finally {
    loading.value = false
  }
}

async function submit() {
  await createVoiceDnc({
    account_id: form.value.account_id,
    phone_e164: form.value.phone_e164,
  })
  ElMessage.success('ok')
  show.value = false
  load()
}

async function remove(row: any) {
  await ElMessageBox.confirm('?', { title: 'Confirm' })
  await deleteVoiceDnc(row.id)
  ElMessage.success('ok')
  load()
}

onMounted(load)
</script>
<style scoped>
.mt-2 { margin-top: 12px; }
</style>
