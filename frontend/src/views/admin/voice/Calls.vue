<template>
  <div class="voice-calls-page">
    <div class="page-header">
      <h2>{{ $t('voice.callRecords') }}</h2>
      <div class="header-actions">
        <el-input v-model="filters.account_id" :placeholder="$t('voice.accountId')" style="width: 120px" />
        <el-select v-model="filters.status" :placeholder="$t('voice.status')" style="width: 140px" clearable>
          <el-option :label="$t('voice.initiated')" value="initiated" />
          <el-option :label="$t('voice.ringing')" value="ringing" />
          <el-option :label="$t('voice.answered')" value="answered" />
          <el-option :label="$t('voice.busy')" value="busy" />
          <el-option :label="$t('voice.failed')" value="failed" />
          <el-option :label="$t('voice.completed')" value="completed" />
        </el-select>
        <el-button @click="loadCalls">{{ $t('smsRecords.query') }}</el-button>
      </div>
    </div>

    <el-card>
      <el-table :data="calls" stripe v-loading="loading">
        <el-table-column prop="call_id" :label="$t('voice.callId')" min-width="160" />
        <el-table-column prop="account_id" :label="$t('voice.accountId')" width="100" />
        <el-table-column prop="caller" :label="$t('voice.caller')" width="140" />
        <el-table-column prop="callee" :label="$t('voice.callee')" width="140" />
        <el-table-column prop="status" :label="$t('voice.status')" width="100" />
        <el-table-column prop="duration" :label="$t('voice.duration')" width="120" />
        <el-table-column prop="cost" :label="$t('voice.cost')" width="100" />
        <el-table-column prop="start_time" :label="$t('voice.startTime')" width="180">
          <template #default="{ row }">
            {{ row.start_time ? new Date(row.start_time).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="end_time" :label="$t('voice.endTime')" width="180">
          <template #default="{ row }">
            {{ row.end_time ? new Date(row.end_time).toLocaleString() : '-' }}
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next, sizes"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="(p:number)=>{ page=p; loadCalls() }"
          @size-change="(s:number)=>{ pageSize=s; page=1; loadCalls() }"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { getVoiceCalls } from '@/api/voice-admin'

const { t } = useI18n()
const calls = ref<any[]>([])
const loading = ref(false)
const total = ref(0)
let page = 1
let pageSize = 20

const filters = reactive({
  account_id: '',
  status: ''
})

const loadCalls = async () => {
  loading.value = true
  try {
    const res = await getVoiceCalls({
      account_id: filters.account_id ? Number(filters.account_id) : undefined,
      status: filters.status || undefined,
      page,
      page_size: pageSize
    })
    calls.value = res.items || []
    total.value = res.total || 0
  } catch (error: any) {
    ElMessage.error(t('voice.loadCallsFailed'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadCalls()
})
</script>

<style scoped>
.voice-calls-page {
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

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
