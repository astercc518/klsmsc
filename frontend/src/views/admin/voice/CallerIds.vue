<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t('voice.callerIdsTitle') }}</h1>
      <p class="page-desc">{{ $t('voice.callerIdsDesc') }}</p>
    </div>
    <div class="table-card">
      <el-button type="primary" @click="openCreate">{{ $t('common.add') }}</el-button>
      <el-table :data="items" v-loading="loading" stripe class="mt-2">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="account_id" :label="$t('voice.accountIdCol')" width="100" />
        <el-table-column prop="number_e164" :label="$t('voice.callerNumber')" />
        <el-table-column prop="trunk_ref" :label="$t('voice.trunkRefCol')" min-width="100" show-overflow-tooltip />
        <el-table-column prop="voice_route_id" :label="$t('voice.voiceRouteBind')" width="110" />
        <el-table-column prop="label" :label="$t('common.remark')" />
        <el-table-column prop="status" :label="$t('common.status')" width="100" />
        <el-table-column :label="$t('common.action')" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">{{ $t('common.edit') }}</el-button>
            <el-button size="small" type="danger" @click="remove(row)">{{ $t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="show" :title="isEdit ? $t('voice.editCallerId') : $t('voice.addCallerId')" width="520px">
      <el-form label-width="130px">
        <el-form-item v-if="!isEdit" :label="$t('voice.accountIdCol')" required>
          <el-input v-model.number="form.account_id" type="number" />
        </el-form-item>
        <el-form-item v-if="!isEdit" :label="$t('voice.callerNumber')" required>
          <el-input v-model="form.number_e164" placeholder="+8613800138000" />
        </el-form-item>
        <el-form-item :label="$t('common.remark')">
          <el-input v-model="form.label" />
        </el-form-item>
        <el-form-item :label="$t('voice.trunkRefCol')">
          <el-input v-model="form.trunk_ref" :placeholder="$t('voice.trunkRefHint')" />
        </el-form-item>
        <el-form-item :label="$t('voice.voiceRouteBind')">
          <el-select
            v-model="form.voice_route_id"
            clearable
            filterable
            :placeholder="$t('voice.voiceRouteBindHint')"
            style="width: 100%"
          >
            <el-option
              v-for="r in routes"
              :key="r.id"
              :label="`${r.country_code} · #${r.id} (${r.cost_per_minute}/min)`"
              :value="r.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="isEdit" :label="$t('common.status')">
          <el-select v-model="form.status" style="width: 100%">
            <el-option :label="$t('voice.callerStatusActive')" value="active" />
            <el-option :label="$t('voice.callerStatusDisabled')" value="disabled" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="show = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="submit">{{ $t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getVoiceCallerIds,
  createVoiceCallerId,
  updateVoiceCallerId,
  deleteVoiceCallerId,
  getVoiceRoutes,
  type VoiceRoute,
} from '@/api/voice-admin'

const { t } = useI18n()

const loading = ref(false)
const saving = ref(false)
const items = ref<any[]>([])
const routes = ref<VoiceRoute[]>([])
const show = ref(false)
const isEdit = ref(false)
const editingId = ref<number | null>(null)

const form = ref({
  account_id: 1,
  number_e164: '',
  label: '',
  trunk_ref: '',
  voice_route_id: undefined as number | undefined,
  status: 'active' as 'active' | 'disabled',
})

async function loadRoutes() {
  try {
    const res: any = await getVoiceRoutes()
    routes.value = res.items || []
  } catch {
    routes.value = []
  }
}

async function load() {
  loading.value = true
  try {
    const res: any = await getVoiceCallerIds()
    items.value = res.items || res.data?.items || []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  isEdit.value = false
  editingId.value = null
  form.value = {
    account_id: 1,
    number_e164: '',
    label: '',
    trunk_ref: '',
    voice_route_id: undefined,
    status: 'active',
  }
  show.value = true
}

function openEdit(row: any) {
  isEdit.value = true
  editingId.value = row.id
  form.value = {
    account_id: row.account_id,
    number_e164: row.number_e164,
    label: row.label || '',
    trunk_ref: row.trunk_ref || '',
    voice_route_id: row.voice_route_id ?? undefined,
    status: (row.status as 'active' | 'disabled') || 'active',
  }
  show.value = true
}

async function submit() {
  saving.value = true
  try {
    if (isEdit.value && editingId.value != null) {
      await updateVoiceCallerId(editingId.value, {
        label: form.value.label || undefined,
        trunk_ref: form.value.trunk_ref || undefined,
        voice_route_id: form.value.voice_route_id ?? null,
        status: form.value.status,
      })
      ElMessage.success(t('voice.updateSuccess'))
    } else {
      if (!form.value.number_e164?.trim()) {
        ElMessage.warning(t('voice.callerNumberRequired'))
        return
      }
      await createVoiceCallerId({
        account_id: form.value.account_id,
        number_e164: form.value.number_e164.trim(),
        label: form.value.label || undefined,
        trunk_ref: form.value.trunk_ref || undefined,
        voice_route_id: form.value.voice_route_id ?? undefined,
      })
      ElMessage.success(t('voice.createSuccess'))
    }
    show.value = false
    load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || t('common.failed'))
  } finally {
    saving.value = false
  }
}

async function remove(row: any) {
  try {
    await ElMessageBox.confirm(t('voice.confirmDeleteCallerId'), t('dialog.deleteTitle'), {
      type: 'warning',
    })
    await deleteVoiceCallerId(row.id)
    ElMessage.success(t('voice.deleteSuccess'))
    load()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.detail || t('common.failed'))
    }
  }
}

onMounted(() => {
  loadRoutes()
  load()
})
</script>
<style scoped>
.mt-2 {
  margin-top: 12px;
}
.page-container {
  width: 100%;
}
.table-card {
  background: var(--bg-card);
  padding: 16px;
  border-radius: 12px;
  border: 1px solid var(--border-default);
}
.page-header {
  margin-bottom: 20px;
}
.page-title {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 8px;
}
.page-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}
</style>
