<template>
  <div class="approvals-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">短信审核</h1>
        <p class="page-desc">提交需审核的短信，审核通过后点击「立即发送」进行发送。与 Telegram 业务助手同步。</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="showSubmitDialog">
          <el-icon><Plus /></el-icon>
          提交审核
        </el-button>
        <el-button @click="loadList">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 筛选 -->
    <div class="filter-bar">
      <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width: 140px" @change="loadList">
        <el-option label="待审核" value="pending" />
        <el-option label="已通过" value="approved" />
        <el-option label="已拒绝" value="rejected" />
      </el-select>
    </div>

    <!-- 列表 -->
    <div class="table-card">
      <el-table v-loading="loading" :data="list" stripe empty-text="暂无审核记录">
        <el-table-column prop="approval_no" label="审核单号" width="180">
          <template #default="{ row }">
            <span class="mono">{{ row.approval_no }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="phone_number" label="号码" width="140" />
        <el-table-column prop="content" label="内容" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reviewed_at" label="审核时间" width="170">
          <template #default="{ row }">
            {{ row.reviewed_at ? formatTime(row.reviewed_at) : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="提交时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'approved' && !row.message_id"
              type="primary"
              size="small"
              :loading="executingId === row.id"
              @click.stop="handleExecute(row)"
            >
              立即发送
            </el-button>
            <el-button
              v-else-if="row.message_id"
              type="success"
              size="small"
              disabled
            >
              已发送
            </el-button>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadList"
          @current-change="loadList"
        />
      </div>
    </div>

    <!-- 提交审核弹窗 -->
    <el-dialog v-model="submitVisible" title="提交短信审核" width="500px" @close="resetSubmitForm">
      <el-form ref="submitFormRef" :model="submitForm" :rules="submitRules" label-width="80px">
        <el-form-item label="手机号码" prop="phone_number">
          <el-input v-model="submitForm.phone_number" placeholder="+8613800138000" />
        </el-form-item>
        <el-form-item label="短信内容" prop="message">
          <el-input v-model="submitForm.message" type="textarea" :rows="5" placeholder="请输入短信内容" maxlength="1000" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">提交审核</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { getSmsApprovals, submitSmsApproval, executeApprovedSms } from '@/api/sms'

const loading = ref(false)
const list = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filterStatus = ref<string>('')

const submitVisible = ref(false)
const submitting = ref(false)
const submitFormRef = ref<FormInstance>()
const submitForm = ref({ phone_number: '', message: '' })
const submitRules: FormRules = {
  phone_number: [
    { required: true, message: '请输入手机号码', trigger: 'blur' },
    { pattern: /^\+\d{8,20}$/, message: '请使用 E.164 格式，如 +8613800138000', trigger: 'blur' },
  ],
  message: [{ required: true, message: '请输入短信内容', trigger: 'blur' }],
}

const executingId = ref<number | null>(null)

const statusLabel = (s: string) => {
  const m: Record<string, string> = { pending: '待审核', approved: '已通过', rejected: '已拒绝' }
  return m[s] || s
}

const statusType = (s: string) => {
  const m: Record<string, string> = { pending: 'warning', approved: 'success', rejected: 'danger' }
  return m[s] || 'info'
}

const formatTime = (t: string) => {
  if (!t) return '-'
  try {
    const d = new Date(t)
    return d.toLocaleString('zh-CN')
  } catch {
    return t
  }
}

const loadList = async () => {
  loading.value = true
  try {
    const res: any = await getSmsApprovals({
      status: filterStatus.value || undefined,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    list.value = res.items || []
    total.value = res.total || 0
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

const showSubmitDialog = () => {
  submitVisible.value = true
}

const resetSubmitForm = () => {
  submitForm.value = { phone_number: '', message: '' }
  submitFormRef.value?.resetFields()
}

const handleSubmit = async () => {
  if (!submitFormRef.value) return
  await submitFormRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      await submitSmsApproval(submitForm.value)
      ElMessage.success('已提交审核，审核通过后可点击「立即发送」')
      submitVisible.value = false
      resetSubmitForm()
      loadList()
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || e?.message || '提交失败')
    } finally {
      submitting.value = false
    }
  })
}

const handleExecute = async (row: any) => {
  executingId.value = row.id
  try {
    await executeApprovedSms(row.id)
    ElMessage.success('发送成功，可在发送记录中查看')
    loadList()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '发送失败')
  } finally {
    executingId.value = null
  }
}

onMounted(() => {
  loadList()
})
</script>

<style scoped>
.approvals-page {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 8px 0;
}

.page-desc {
  color: var(--el-text-color-secondary);
  font-size: 14px;
  margin: 0;
}

.filter-bar {
  margin-bottom: 16px;
}

.table-card {
  background: var(--el-bg-color);
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.mono {
  font-family: ui-monospace, monospace;
  font-size: 13px;
}
</style>
