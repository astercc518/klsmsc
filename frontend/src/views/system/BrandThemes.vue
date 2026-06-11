<template>
  <div class="brand-themes">
    <div class="bt-toolbar">
      <div class="bt-hint">多品牌皮肤：主色 + Logo + 品牌名 + favicon。同一时间仅一套生效（激活），保存/激活后全站即时套用。</div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增品牌</el-button>
    </div>

    <el-table :data="items" v-loading="loading" size="small" border style="width: 100%">
      <el-table-column label="品牌名称" min-width="180">
        <template #default="{ row }">
          <div class="bt-name">
            <img v-if="row.logo" :src="row.logo" class="bt-logo-thumb" alt="logo" />
            <span>{{ row.name }}</span>
            <el-tag v-if="row.is_active" type="success" size="small" effect="dark">使用中</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="主色" width="140">
        <template #default="{ row }">
          <div class="bt-color">
            <span class="bt-swatch" :style="{ background: row.primary_color }"></span>
            <code>{{ row.primary_color }}</code>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="favicon" width="90" align="center">
        <template #default="{ row }">
          <img v-if="row.favicon" :src="row.favicon" class="bt-favicon" alt="favicon" />
          <span v-else class="bt-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!row.is_active" link type="success" size="small" @click="onActivate(row)">设为使用中</el-button>
          <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button v-if="!row.is_active" link type="danger" size="small" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增/编辑 -->
    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑品牌' : '新增品牌'" width="560px" :close-on-click-modal="false">
      <el-form label-width="92px">
        <el-form-item label="品牌名称">
          <el-input v-model="form.name" maxlength="40" show-word-limit placeholder="如：考拉出海 / SMSCPRO" style="max-width: 360px" />
        </el-form-item>
        <el-form-item label="主色">
          <el-color-picker v-model="form.primary_color" />
          <code class="bt-color-hex">{{ form.primary_color }}</code>
          <span class="bt-muted" style="margin-left: 12px">按钮/链接/高亮等主色,衍生色阶自动生成</span>
        </el-form-item>
        <el-form-item label="Logo">
          <div class="bt-upload">
            <img v-if="form.logo" :src="form.logo" class="bt-logo-preview" alt="logo" />
            <div>
              <el-button size="small" @click="pickFile('logo')">选择图片</el-button>
              <el-button v-if="form.logo" size="small" link type="danger" @click="form.logo = ''">清空</el-button>
              <div class="bt-muted">建议 PNG/SVG,小于 480KB;留空用默认</div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="favicon">
          <div class="bt-upload">
            <img v-if="form.favicon" :src="form.favicon" class="bt-favicon-preview" alt="favicon" />
            <div>
              <el-button size="small" @click="pickFile('favicon')">选择图片</el-button>
              <el-button v-if="form.favicon" size="small" link type="danger" @click="form.favicon = ''">清空</el-button>
              <div class="bt-muted">浏览器标签图标,建议正方形 PNG/ICO,小于 100KB</div>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <input ref="fileInput" type="file" accept="image/*" style="display: none" @change="onFileChange" />
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  listBrands, createBrand, updateBrand, activateBrand, deleteBrand,
  type BrandTheme,
} from '@/api/brand'
import { loadBrand } from '@/composables/useBrand'

const loading = ref(false)
const items = ref<BrandTheme[]>([])
const dialogVisible = ref(false)
const saving = ref(false)
const form = reactive<{ id: number | null; name: string; primary_color: string; logo: string; favicon: string }>({
  id: null, name: '', primary_color: '#2a9d8f', logo: '', favicon: '',
})

const fileInput = ref<HTMLInputElement | null>(null)
const pickTarget = ref<'logo' | 'favicon'>('logo')
// 各自大小上限(原始文件字节)
const LIMITS: Record<'logo' | 'favicon', number> = { logo: 480 * 1024, favicon: 100 * 1024 }

async function load() {
  loading.value = true
  try {
    const r = await listBrands()
    if (r.success) items.value = r.items
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.id = null
  form.name = ''
  form.primary_color = '#2a9d8f'
  form.logo = ''
  form.favicon = ''
  dialogVisible.value = true
}

function openEdit(row: BrandTheme) {
  form.id = row.id
  form.name = row.name
  form.primary_color = row.primary_color || '#2a9d8f'
  form.logo = row.logo || ''
  form.favicon = row.favicon || ''
  dialogVisible.value = true
}

function pickFile(target: 'logo' | 'favicon') {
  pickTarget.value = target
  fileInput.value?.click()
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // 允许重复选同一文件
  if (!file) return
  const target = pickTarget.value
  if (file.size > LIMITS[target]) {
    ElMessage.error(`图片过大,请小于 ${Math.round(LIMITS[target] / 1024)}KB`)
    return
  }
  const reader = new FileReader()
  reader.onload = () => { form[target] = String(reader.result || '') }
  reader.onerror = () => ElMessage.error('读取图片失败')
  reader.readAsDataURL(file)
}

async function onSave() {
  if (!form.name.trim()) { ElMessage.warning('请填写品牌名称'); return }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      primary_color: form.primary_color || '#2a9d8f',
      logo: form.logo,      // 空串=清空,后端按 None 处理
      favicon: form.favicon,
    }
    if (form.id) {
      const r = await updateBrand(form.id, payload)
      if (!r.success) throw new Error()
      ElMessage.success('已保存')
    } else {
      const r = await createBrand(payload)
      if (!r.success) throw new Error()
      ElMessage.success('已新增')
    }
    dialogVisible.value = false
    await load()
    // 若编辑的是当前激活品牌,立即重新套用
    await loadBrand()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onActivate(row: BrandTheme) {
  try {
    await ElMessageBox.confirm(`确认将「${row.name}」设为当前使用中的品牌？全站皮肤将立即切换。`, '切换品牌', { type: 'warning' })
  } catch { return }
  try {
    const r = await activateBrand(row.id)
    if (!r.success) throw new Error()
    ElMessage.success('已切换')
    await load()
    await loadBrand() // 即时套用,无需刷新
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '切换失败')
  }
}

async function onDelete(row: BrandTheme) {
  try {
    await ElMessageBox.confirm(`确认删除品牌「${row.name}」？`, '删除品牌', { type: 'warning', confirmButtonText: '删除' })
  } catch { return }
  try {
    const r = await deleteBrand(row.id)
    if (!r.success) throw new Error()
    ElMessage.success('已删除')
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.brand-themes { width: 100%; }
.bt-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; gap: 16px; }
.bt-hint { color: var(--el-text-color-secondary); font-size: 13px; }
.bt-name { display: flex; align-items: center; gap: 10px; }
.bt-logo-thumb { height: 24px; max-width: 80px; object-fit: contain; border-radius: 4px; }
.bt-color { display: flex; align-items: center; gap: 8px; }
.bt-swatch { width: 18px; height: 18px; border-radius: 4px; border: 1px solid var(--el-border-color); display: inline-block; }
.bt-favicon { height: 20px; width: 20px; object-fit: contain; }
.bt-muted { color: var(--el-text-color-secondary); font-size: 12px; }
.bt-color-hex { margin-left: 12px; }
.bt-upload { display: flex; align-items: center; gap: 14px; }
.bt-logo-preview { height: 40px; max-width: 140px; object-fit: contain; border: 1px solid var(--el-border-color); border-radius: 6px; padding: 4px; background: #fff; }
.bt-favicon-preview { height: 32px; width: 32px; object-fit: contain; border: 1px solid var(--el-border-color); border-radius: 6px; padding: 2px; background: #fff; }
</style>
