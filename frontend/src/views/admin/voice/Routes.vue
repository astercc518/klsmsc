<template>
  <div class="voice-routes-page">
    <div class="page-header">
      <h2>{{ $t('voice.routesTitle') }}</h2>
      <div class="header-actions">
        <el-input
          v-model="countryFilter"
          :placeholder="$t('voice.countryCode')"
          style="width: 180px"
          clearable
          @keyup.enter="loadRoutes"
        />
        <el-button @click="loadRoutes">{{ $t('smsRecords.query') }}</el-button>
        <el-button @click="checkVosStatus">{{ $t('voice.vosStatusCheck') }}</el-button>
        <el-button type="primary" @click="openCreate">{{ $t('voice.addRoute') }}</el-button>
      </div>
    </div>

    <el-card>
      <el-table :data="routes" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="country_code" :label="$t('voice.countryCode')" width="120" />
        <el-table-column prop="provider_id" :label="$t('voice.providerId')" width="120" />
        <el-table-column prop="priority" :label="$t('voice.priority')" width="120" />
        <el-table-column prop="cost_per_minute" :label="$t('voice.costPerMinute')" width="140" />
        <el-table-column prop="gateway_type" :label="$t('voice.gatewayType')" width="100" />
        <el-table-column prop="vos_gateway_name" :label="$t('voice.vosGatewayName')" min-width="120" show-overflow-tooltip />
        <el-table-column prop="trunk_profile" :label="$t('voice.trunkProfile')" min-width="120" show-overflow-tooltip />
        <el-table-column prop="dial_prefix" :label="$t('voice.dialPrefix')" width="100" />
        <el-table-column prop="created_at" :label="$t('common.createdAt')" width="180">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.action')" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">{{ $t('common.edit') }}</el-button>
            <el-button size="small" type="danger" @click="removeRoute(row)">{{ $t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? $t('voice.editRoute') : $t('voice.addRoute')" width="520px">
      <el-form :model="form" label-width="110px">
        <el-form-item :label="$t('voice.countryCode')" required>
          <el-input v-model="form.country_code" :placeholder="$t('voice.countryCodePlaceholder')" :disabled="isEdit" />
        </el-form-item>
        <el-form-item :label="$t('voice.providerId')">
          <el-input-number v-model="form.provider_id" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="$t('voice.priority')">
          <el-input-number v-model="form.priority" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="$t('voice.costPerMinute')">
          <el-input-number v-model="form.cost_per_minute" :min="0" :step="0.001" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="$t('voice.gatewayType')">
          <el-select v-model="form.gateway_type" style="width: 100%">
            <el-option :label="$t('voice.gatewayTypeGeneric')" value="generic" />
            <el-option :label="$t('voice.gatewayTypeVos')" value="vos" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.gateway_type === 'vos'" :label="$t('voice.vosGatewayName')" required>
          <el-input v-model="form.vos_gateway_name" :placeholder="$t('voice.vosGatewayNameHint')" />
        </el-form-item>
        <el-form-item :label="$t('voice.trunkProfile')">
          <el-input v-model="form.trunk_profile" :placeholder="$t('voice.trunkProfileHint')" />
        </el-form-item>
        <el-form-item :label="$t('voice.dialPrefix')">
          <el-input v-model="form.dial_prefix" />
        </el-form-item>
        <el-form-item :label="$t('voice.routeNotes')">
          <el-input v-model="form.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="saveRoute">{{ $t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getVoiceRoutes,
  createVoiceRoute,
  updateVoiceRoute,
  deleteVoiceRoute,
  getVoiceVosStatus,
} from '@/api/voice-admin'

const { t } = useI18n()

const routes = ref<any[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const saving = ref(false)
const countryFilter = ref('')
const currentId = ref<number | null>(null)

const form = ref({
  country_code: '',
  provider_id: undefined as number | undefined,
  priority: 0,
  cost_per_minute: 0,
  gateway_type: 'generic' as 'generic' | 'vos',
  vos_gateway_name: '' as string | undefined,
  trunk_profile: '' as string | undefined,
  dial_prefix: '' as string | undefined,
  notes: '' as string | undefined
})

const loadRoutes = async () => {
  loading.value = true
  try {
    const res = await getVoiceRoutes({ country_code: countryFilter.value || undefined })
    routes.value = res.items || []
  } catch (error: any) {
    ElMessage.error(t('voice.loadRoutesFailed'))
  } finally {
    loading.value = false
  }
}

const checkVosStatus = async () => {
  try {
    const res = await getVoiceVosStatus()
    const lines = [
      `${t('voice.vosHttpConfigured')}: ${res.vos_http_base_configured ? t('common.yes') : t('common.no')}`,
      `${t('voice.vosHttpUserSet')}: ${res.vos_http_username_set ? t('common.yes') : t('common.no')}`,
    ]
    if (res.reachable != null) {
      lines.push(`${t('voice.vosReachable')}: ${res.reachable ? t('common.yes') : t('common.no')}`)
    }
    lines.push('', res.detail || '')
    await ElMessageBox.alert(lines.join('\n'), t('voice.vosStatusTitle'), {
      confirmButtonText: t('common.confirm'),
    })
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('common.failed'))
  }
}

const openCreate = () => {
  isEdit.value = false
  currentId.value = null
  form.value = {
    country_code: '',
    provider_id: undefined,
    priority: 0,
    cost_per_minute: 0,
    gateway_type: 'generic',
    vos_gateway_name: '',
    trunk_profile: '',
    dial_prefix: '',
    notes: ''
  }
  dialogVisible.value = true
}

const openEdit = (row: any) => {
  isEdit.value = true
  currentId.value = row.id
  form.value = {
    country_code: row.country_code,
    provider_id: row.provider_id || undefined,
    priority: row.priority,
    cost_per_minute: row.cost_per_minute,
    gateway_type: (row.gateway_type === 'vos' ? 'vos' : 'generic') as 'generic' | 'vos',
    vos_gateway_name: row.vos_gateway_name || '',
    trunk_profile: row.trunk_profile || '',
    dial_prefix: row.dial_prefix || '',
    notes: row.notes || ''
  }
  dialogVisible.value = true
}

const saveRoute = async () => {
  if (!form.value.country_code) {
    ElMessage.warning(t('voice.pleaseEnterCountryCode'))
    return
  }
  if (form.value.gateway_type === 'vos' && !form.value.vos_gateway_name?.trim()) {
    ElMessage.warning(t('voice.vosGatewayNameRequired'))
    return
  }
  saving.value = true
  try {
    const payload = {
      ...form.value,
      vos_gateway_name:
        form.value.gateway_type === 'vos' ? form.value.vos_gateway_name?.trim() : null,
    }
    if (isEdit.value && currentId.value) {
      await updateVoiceRoute(currentId.value, payload)
      ElMessage.success(t('voice.updateSuccess'))
    } else {
      await createVoiceRoute(payload)
      ElMessage.success(t('voice.createSuccess'))
    }
    dialogVisible.value = false
    loadRoutes()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.failed'))
  } finally {
    saving.value = false
  }
}

const removeRoute = async (row: any) => {
  try {
    await ElMessageBox.confirm(t('voice.confirmDeleteRoute'), t('dialog.deleteTitle'), { type: 'warning' })
    await deleteVoiceRoute(row.id)
    ElMessage.success(t('voice.deleteSuccess'))
    loadRoutes()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(t('common.failed'))
    }
  }
}

onMounted(() => {
  loadRoutes()
})
</script>

<style scoped>
.voice-routes-page {
  width: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}
</style>
