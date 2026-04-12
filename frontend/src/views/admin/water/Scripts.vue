<template>
  <div class="water-scripts">
    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button type="primary" @click="openDialog()">新增脚本</el-button>
    </div>

    <!-- 表格 -->
    <el-table :data="tableData" v-loading="loading" stripe border style="width: 100%; margin-top: 15px">
      <el-table-column prop="name" label="脚本名称" width="180" />
      <el-table-column prop="domain" label="目标域名" width="220" />
      <el-table-column prop="enabled" label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="成功/失败" width="120" align="center">
        <template #default="{ row }">
          <span style="color: #67c23a">{{ row.success_count }}</span> /
          <span style="color: #f56c6c">{{ row.fail_count }}</span>
        </template>
      </el-table-column>
      <el-table-column label="最近运行" width="160">
        <template #default="{ row }">{{ row.last_run_at?.replace('T', ' ') || '-' }}</template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="150" show-overflow-tooltip />
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openDialog(row)">编辑</el-button>
          <el-button size="small" type="warning" :loading="row._testing" @click="handleTest(row)">测试运行</el-button>
          <el-button size="small" :type="row.enabled ? 'danger' : 'success'" @click="handleToggle(row)">
            {{ row.enabled ? '停用' : '启用' }}
          </el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-wrap">
      <el-pagination background layout="total, prev, pager, next" :total="total" :page-size="pageSize" v-model:current-page="currentPage" @current-change="loadData" />
    </div>

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑注册脚本' : '新增注册脚本'" width="650px" destroy-on-close>
      <el-form :model="form" label-width="110px">
        <el-form-item label="脚本名称" required>
          <el-input v-model="form.name" placeholder="如: XX博彩注册" />
        </el-form-item>
        <el-form-item label="目标域名" required>
          <el-input v-model="form.domain" placeholder="如: example.com" />
        </el-form-item>
        <el-divider content-position="left">注册步骤配置</el-divider>
        <el-form-item label="注册入口">
          <el-input v-model="form.steps.entry_selector" placeholder="CSS选择器，如: a:has-text('注册')" />
        </el-form-item>
        <el-form-item label="表单字段">
          <div style="width: 100%">
            <div v-for="(field, idx) in form.steps.fields" :key="idx" style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center">
              <el-input v-model="field.selector" placeholder="CSS选择器" style="flex: 2" size="small" />
              <el-select v-model="field.type" style="width: 100px" size="small">
                <el-option label="手机号" value="phone" />
                <el-option label="密码" value="password" />
                <el-option label="邮箱" value="email" />
                <el-option label="文本" value="text" />
              </el-select>
              <el-input v-model="field.faker_method" placeholder="Faker方法(可选)" style="flex: 1" size="small" />
              <el-button size="small" type="danger" circle @click="removeField(idx)">
                <template #icon><span>✕</span></template>
              </el-button>
            </div>
            <el-button size="small" @click="addField">+ 添加字段</el-button>
          </div>
        </el-form-item>
        <el-form-item label="提交按钮">
          <el-input v-model="form.steps.submit_selector" placeholder="CSS选择器，如: button[type=submit]" />
        </el-form-item>
        <el-form-item label="成功判断">
          <el-input v-model="form.steps.success_indicator" placeholder="URL包含或元素选择器，逗号分隔" />
        </el-form-item>
        <el-divider />
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getScripts, createScript, updateScript, deleteScript, testScript } from '@/api/water'

const loading = ref(false)
const submitting = ref(false)
const tableData = ref<any[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)

interface FieldDef {
  selector: string
  type: string
  faker_method: string
}

const makeEmptyForm = () => ({
  name: '',
  domain: '',
  steps: {
    entry_selector: '',
    fields: [] as FieldDef[],
    submit_selector: '',
    success_indicator: '',
    captcha_handler: 'none',
  },
  remark: '',
})

const form = reactive(makeEmptyForm())

const addField = () => {
  form.steps.fields.push({ selector: '', type: 'text', faker_method: '' })
}

const removeField = (idx: number) => {
  form.steps.fields.splice(idx, 1)
}

const loadData = async () => {
  loading.value = true
  try {
    const res: any = await getScripts({ page: currentPage.value, page_size: pageSize })
    tableData.value = (res.items || []).map((s: any) => ({ ...s, _testing: false }))
    total.value = res.total || 0
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const openDialog = (row?: any) => {
  if (row) {
    editingId.value = row.id
    const steps = row.steps || {}
    Object.assign(form, {
      name: row.name,
      domain: row.domain,
      steps: {
        entry_selector: steps.entry_selector || '',
        fields: (steps.fields || []).map((f: any) => ({ ...f })),
        submit_selector: steps.submit_selector || '',
        success_indicator: steps.success_indicator || '',
        captcha_handler: steps.captcha_handler || 'none',
      },
      remark: row.remark || '',
    })
  } else {
    editingId.value = null
    Object.assign(form, makeEmptyForm())
  }
  dialogVisible.value = true
}

const handleSubmit = async () => {
  if (!form.name || !form.domain) {
    ElMessage.warning('请填写必填项')
    return
  }
  submitting.value = true
  try {
    const payload = { name: form.name, domain: form.domain, steps: { ...form.steps }, remark: form.remark }
    if (editingId.value) {
      await updateScript(editingId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await createScript(payload)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await loadData()
  } catch (e) {
    console.error(e)
  } finally {
    submitting.value = false
  }
}

const handleTest = async (row: any) => {
  row._testing = true
  try {
    const res: any = await testScript(row.id)
    ElMessage.success(res.message || '测试任务已提交')
  } catch (e) {
    console.error(e)
  } finally {
    row._testing = false
  }
}

const handleToggle = async (row: any) => {
  await updateScript(row.id, { enabled: !row.enabled })
  ElMessage.success(row.enabled ? '已停用' : '已启用')
  await loadData()
}

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(`确定删除脚本「${row.name}」？`, '确认')
  await deleteScript(row.id)
  ElMessage.success('删除成功')
  await loadData()
}

onMounted(() => loadData())
</script>

<style scoped>
.water-scripts { padding: 0; }
.toolbar { display: flex; align-items: center; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
