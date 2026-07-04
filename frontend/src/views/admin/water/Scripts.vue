<template>
  <div class="water-scripts">
    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button type="primary" @click="openDialog()">新增脚本</el-button>
    </div>

    <el-alert type="info" :closable="false" show-icon style="margin-top: 10px">
      <template #title>
        <span style="font-size: 13px">
          <b>内置</b>脚本（TK688/SP111/1win/直连API）是为反爬站硬编码的代码 handler，只读、改代码维护；
          <b>可编辑</b>的是你自己配的通用脚本（标准站，无验证码/图形验证码）。两者都可在「注水配置 → 注册脚本」里按账户选用。
        </span>
      </template>
    </el-alert>

    <!-- 表格 -->
    <el-table :data="tableData" v-loading="loading" stripe border style="width: 100%; margin-top: 15px">
      <el-table-column label="脚本名称" width="200">
        <template #default="{ row }">
          <el-tag v-if="row.builtin" type="warning" size="small" effect="dark" style="margin-right: 6px">内置</el-tag>
          {{ row.name }}
        </template>
      </el-table-column>
      <el-table-column prop="domain" label="目标域名" width="220" show-overflow-tooltip />
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
          <el-button size="small" type="warning" :loading="row._testing" @click="handleTest(row)">测试运行</el-button>
          <template v-if="!row.builtin">
            <el-button size="small" @click="openDialog(row)">编辑</el-button>
            <el-button size="small" :type="row.enabled ? 'danger' : 'success'" @click="handleToggle(row)">
              {{ row.enabled ? '停用' : '启用' }}
            </el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
          <span v-else style="color: #909399; font-size: 12px; margin-left: 4px">内置·改代码维护</span>
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

        <!-- 自动生成:只填目标站,系统探测目标站自动产出脚本 -->
        <template v-if="!editingId">
          <el-form-item label="目标站">
            <div style="display: flex; gap: 8px; width: 100%">
              <el-input v-model="genUrl" placeholder="落地URL / 短链 / 域名，如 https://xxx.com 或 shorturl.at/xxx" style="flex: 3" />
              <el-input v-model="genCountry" placeholder="国家如BD(可选)" style="flex: 1" />
              <el-button type="success" :loading="generating" @click="handleGenerate">🪄 自动生成</el-button>
            </div>
          </el-form-item>
          <el-form-item v-if="genStatus" label=" ">
            <span :style="{ color: genOk ? '#67c23a' : '#909399' }">{{ genStatus }}</span>
          </el-form-item>
        </template>

        <el-form-item label="目标域名" required>
          <el-input v-model="form.domain" placeholder="自动生成后回填，也可手填，如: example.com" />
        </el-form-item>
        <el-divider content-position="left">注册步骤配置（自动生成后可检查/微调）</el-divider>
        <el-form-item label="注册入口">
          <el-input v-model="form.steps.entry_selector" placeholder="CSS选择器，如: a:has-text('注册')" />
        </el-form-item>
        <el-form-item label="表单字段">
          <div style="width: 100%">
            <div v-for="(field, idx) in form.steps.fields" :key="idx" style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center">
              <el-input v-model="field.selector" placeholder="CSS选择器" style="flex: 2" size="small" />
              <el-select v-model="field.type" style="width: 110px" size="small">
                <el-option label="账号" value="username" />
                <el-option label="手机号" value="phone" />
                <el-option label="密码" value="password" />
                <el-option label="邮箱" value="email" />
                <el-option label="姓名" value="name" />
                <el-option label="验证码" value="captcha" />
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
        <el-form-item label="验证码类型">
          <el-select v-model="form.steps.captcha_handler" style="width: 220px">
            <el-option label="无" value="none" />
            <el-option label="图形验证码（引擎自动解）" value="image" />
            <el-option label="GeeTest（需专用handler）" value="geetest" />
            <el-option label="reCAPTCHA（需专用handler）" value="recaptcha" />
            <el-option label="滑块（需专用handler）" value="slider" />
          </el-select>
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
import { getScripts, createScript, updateScript, deleteScript, generateScript, getGenerateResult, testRunScript, getTestRunResult } from '@/api/water'

const loading = ref(false)
const submitting = ref(false)
const tableData = ref<any[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)

// 自动生成
const generating = ref(false)
const genUrl = ref('')
const genCountry = ref('')
const genStatus = ref('')
const genOk = ref(false)

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

// 自动生成:提交目标站 → 轮询后台探针 → 回填表单供检查保存
const applyGenerated = (result: any) => {
  if (result?.kind === 'config_script' && result.script) {
    const s = result.script
    const fields = (s.steps?.fields || [])
    const landing = result?.profile?.landing_url || ''
    // 空字段=没探到表单(多为:目标站地域封锁没填国家 / 需先过弹窗 / 反爬SPA)
    if (fields.length === 0) {
      genOk.value = false
      const geoHint = /\/405|restrict/i.test(landing) ? '疑似地域封锁——请在「目标站」右侧填对应【国家】(如BR/BD)后重试；' : ''
      genStatus.value = `⚠️ 未探到注册表单。${geoHint}若为TK688/SP111等反爬站，请直接用「注水配置→注册脚本」选专用handler，无需在此配脚本。`
      ElMessage.warning('未识别到注册表单，见提示')
      return
    }
    form.domain = s.domain || form.domain
    if (!form.name) form.name = s.name || ''
    form.steps.entry_selector = s.steps?.entry_selector || ''
    form.steps.fields = fields.map((f: any) => ({ selector: f.selector, type: f.type, faker_method: '' }))
    form.steps.submit_selector = s.steps?.submit_selector || ''
    form.steps.success_indicator = s.steps?.success_indicator || ''
    form.steps.captcha_handler = s.steps?.captcha_handler || 'none'
    genOk.value = true
    genStatus.value = '✅ 已自动生成，请检查字段/提交/成功判断后点“确定”保存'
    ElMessage.success('脚本已自动生成，请检查后保存')
    if (result.note) ElMessage.info(result.note)
  } else if (result?.kind === 'handler_scaffold') {
    genOk.value = false
    genStatus.value = `⚠️ 该站含 ${result?.profile?.captcha?.type || '强反爬'} 验证码，配置脚本搞不定，已生成代码脚手架：${result.scaffold_path || '(见worker /tmp)'}，需开发接入`
    ElMessage.warning('该站需专用代码handler，已生成脚手架文件')
  } else if (result?.kind === 'cannot_automate') {
    genOk.value = false
    genStatus.value = `❌ ${result?.note || '短信OTP，无法自动化'}`
  } else {
    genOk.value = false
    genStatus.value = `❌ ${result?.note || '未识别到注册表单，请看截图或手工配置'}`
  }
}

const handleGenerate = async () => {
  if (!genUrl.value) {
    ElMessage.warning('请填写目标站 URL / 域名')
    return
  }
  generating.value = true
  genOk.value = false
  genStatus.value = '正在探测目标站…（约30-90秒，勿关闭）'
  try {
    const { task_id }: any = await generateScript({ url: genUrl.value, country: genCountry.value })
    for (let i = 0; i < 50; i++) {
      await new Promise((r) => setTimeout(r, 3000))
      const res: any = await getGenerateResult(task_id)
      if (res.state === 'SUCCESS') { applyGenerated(res.result); return }
      if (res.state === 'FAILURE') { genStatus.value = '❌ 生成失败：' + (res.error || ''); return }
      genStatus.value = `正在探测目标站…（${(i + 1) * 3}秒）`
    }
    genStatus.value = '❌ 探测超时，请重试或手工配置'
  } catch (e) {
    console.error(e)
    genStatus.value = '❌ 生成请求失败'
  } finally {
    generating.value = false
  }
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
    genUrl.value = ''
    genCountry.value = ''
    genStatus.value = ''
    genOk.value = false
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

const HANDLER_TEST_COUNTRY: Record<string, string> = { sp111: 'BR', tk688: 'BD', onewin: '', api: '' }

const handleTest = async (row: any) => {
  const firstDomain = (row.domain || '').split(',')[0].trim()
  // 第1步:测试落地URL(反爬/轮换/geo站的品牌域名往往不能直接测,需粘真实campaign落地/短链)
  let url = ''
  try {
    const r1: any = await ElMessageBox.prompt(
      `测试「${row.name}」：填一个真实可达的注册落地URL。反爬/地域限制站（如SP111）的品牌域名不能直接测，请粘贴当前campaign的落地URL或短链。`,
      '测试运行 (1/2)',
      { confirmButtonText: '下一步', cancelButtonText: '取消', inputValue: firstDomain, inputPlaceholder: '落地URL或域名' }
    )
    url = (r1.value || '').trim()
  } catch {
    return
  }
  if (!url) return
  // 第2步:国家(geo站代理出口;内置带默认)
  let country = row.builtin ? (HANDLER_TEST_COUNTRY[row.handler_key] || '') : ''
  try {
    const r2: any = await ElMessageBox.prompt(
      '目标站有地域封锁时填国家（代理出口，如 BR / BD）；普通站留空。',
      '测试运行 (2/2)',
      { confirmButtonText: '开始测试', cancelButtonText: '取消', inputValue: country, inputPlaceholder: '国家ISO2，可留空' }
    )
    country = (r2.value || '').trim()
  } catch {
    return
  }
  row._testing = true
  try {
    const { task_id }: any = await testRunScript({
      handler_key: row.builtin ? row.handler_key : '',
      script_id: row.builtin ? null : row.id,
      domain: url,
      country,
    })
    let done = false
    for (let i = 0; i < 40; i++) {
      await new Promise((r) => setTimeout(r, 3000))
      const res: any = await getTestRunResult(task_id)
      if (res.state === 'SUCCESS') {
        const rr = res.result || {}
        if (rr.success === true) {
          ElMessageBox.alert(`✅ 测试成功建号：${rr.reason || ''}`, '测试运行', { type: 'success' })
        } else if (rr.success === null) {
          ElMessageBox.alert(`ℹ️ ${rr.reason || '该类型无法离线测试'}`, '测试运行', { type: 'info' })
        } else {
          ElMessageBox.alert(`❌ 测试失败：${rr.reason || ''}\n落地：${rr.landing || '-'}`, '测试运行', { type: 'warning' })
        }
        done = true
        break
      }
      if (res.state === 'FAILURE') {
        ElMessage.error('测试失败：' + (res.error || ''))
        done = true
        break
      }
    }
    if (!done) ElMessage.warning('测试超时，请重试（站点慢/反爬）')
  } catch (e) {
    console.error(e)
    ElMessage.error('测试请求失败')
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
