<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">{{ $t('menu.businessKnowledge') }}</h1>
        <p class="page-desc">{{ $t('businessKnowledge.desc') }}</p>
      </div>
      <div class="header-right" v-if="canManage">
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          {{ $t('businessKnowledge.addArticle') }}
        </el-button>
      </div>
    </div>

    <!-- 搜索筛选 -->
    <div class="filter-bar">
      <el-input
        v-model="filters.keyword"
        :placeholder="$t('businessKnowledge.searchPlaceholder')"
        clearable
        style="width: 220px"
        @keyup.enter="loadList"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="filters.category" :placeholder="$t('businessKnowledge.category')" clearable style="width: 130px" @change="loadList">
        <el-option label="全部" value="" />
        <el-option v-for="c in categories" :key="c.value" :label="c.label" :value="c.value" />
      </el-select>
      <el-select v-if="canManage" v-model="filters.status" :placeholder="$t('businessKnowledge.status')" clearable style="width: 110px" @change="loadList">
        <el-option :label="$t('businessKnowledge.statusPublished')" value="" />
        <el-option :label="$t('businessKnowledge.statusDraft')" value="draft" />
        <el-option :label="$t('businessKnowledge.statusAll')" value="all" />
      </el-select>
      <el-select v-model="filters.sort" :placeholder="$t('businessKnowledge.sort')" style="width: 130px" @change="loadList">
        <el-option :label="$t('businessKnowledge.sortByUpdate')" value="updated_at_desc" />
        <el-option :label="$t('businessKnowledge.sortByViews')" value="view_count_desc" />
      </el-select>
      <el-button type="primary" @click="loadList">{{ $t('common.search') }}</el-button>
    </div>

    <!-- 知识列表 -->
    <div class="knowledge-list" v-loading="loading">
      <el-empty v-if="!loading && items.length === 0" :description="$t('businessKnowledge.noData')" />
      <div v-else class="article-cards">
        <el-card
          v-for="item in items"
          :key="item.id"
          class="article-card"
          shadow="hover"
          @click="viewArticle(item)"
        >
          <div class="card-body">
            <div class="card-title-row">
              <h3 class="article-title">
                <el-icon v-if="item.is_pinned" class="pin-icon" title="置顶"><Top /></el-icon>
                {{ item.title }}
              </h3>
              <div class="card-tags">
                <el-tag v-if="item.status === 'draft'" size="small" type="warning">{{ $t('businessKnowledge.draft') }}</el-tag>
                <el-tag size="small" type="info">{{ categoryLabel(item.category) }}</el-tag>
              </div>
            </div>
            <p class="article-summary">{{ item.summary || '-' }}</p>
            <div class="card-meta">
              <span><el-icon><View /></el-icon> {{ item.view_count }}</span>
              <span v-if="item.attachment_count"><el-icon><Paperclip /></el-icon> {{ item.attachment_count }}</span>
              <span class="time">{{ formatDate(item.updated_at || item.created_at) }}</span>
            </div>
          </div>
          <div class="card-actions" v-if="canManage" @click.stop>
            <el-tooltip :content="item.is_pinned ? $t('businessKnowledge.unpin') : $t('businessKnowledge.pin')" placement="top">
              <el-button type="primary" link size="small" @click="togglePin(item)">
                <el-icon><Top /></el-icon>
              </el-button>
            </el-tooltip>
            <el-button type="primary" link size="small" @click="openEdit(item)">{{ $t('common.edit') }}</el-button>
            <el-popconfirm :title="$t('businessKnowledge.confirmDelete')" @confirm="handleDelete(item.id)">
              <template #reference>
                <el-button type="danger" link size="small">{{ $t('common.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </div>
        </el-card>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="filters.page"
        v-model:page-size="filters.page_size"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadList"
        @current-change="loadList"
      />
    </div>

    <!-- 文章详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="currentArticle?.title" size="75%" destroy-on-close @closed="revokeInlinePreviewUrl">
      <div v-if="currentArticle" class="article-detail">
        <div class="detail-meta">
          <el-tag size="small">{{ categoryLabel(currentArticle.category) }}</el-tag>
          <span>{{ $t('businessKnowledge.views') }}: {{ currentArticle.view_count }}</span>
          <span>{{ formatDate(currentArticle.updated_at) }}</span>
        </div>
        <div class="detail-content" v-html="contentHtml"></div>
        <div v-if="currentArticle.attachments?.length" class="attachments">
          <h4>{{ $t('businessKnowledge.attachments') }}</h4>
          <div class="attach-list">
            <div v-for="att in currentArticle.attachments" :key="att.id" class="attach-item">
              <el-icon><Document /></el-icon>
              <span class="attach-name attach-clickable" @click="onAttachmentClick(att)">{{ att.file_name }}</span>
              <el-button v-if="canPreview(att)" type="primary" link size="small" @click="previewAttachment(att)">{{ $t('businessKnowledge.preview') }}</el-button>
              <el-button type="primary" link size="small" @click="downloadAttachment(att)">{{ $t('common.download') }}</el-button>
            </div>
          </div>
          <!-- 内联文档预览：打开详情时自动加载第一个可预览附件 -->
          <div v-if="firstPreviewableAtt" class="inline-preview">
            <h4>{{ $t('businessKnowledge.documentPreview') }}: {{ inlinePreviewFileName }}</h4>
            <div v-loading="inlinePreviewLoading" class="inline-preview-body">
              <iframe v-if="inlinePreviewUrl && inlinePreviewType === 'pdf'" :src="inlinePreviewUrl" class="inline-preview-iframe" />
              <el-image v-else-if="inlinePreviewUrl && inlinePreviewType === 'image'" :src="inlinePreviewUrl" fit="contain" class="inline-preview-image" />
              <video v-else-if="inlinePreviewUrl && inlinePreviewType === 'video'" :src="inlinePreviewUrl" controls class="inline-preview-video" />
              <div v-else-if="inlinePreviewTextHtml" class="inline-preview-text" v-html="inlinePreviewTextHtml"></div>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- 新增/编辑对话框 -->
    <el-dialog
      v-model="formVisible"
      :title="editingId ? $t('businessKnowledge.editArticle') : $t('businessKnowledge.addArticle')"
      width="600px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="80px">
        <el-form-item :label="$t('businessKnowledge.title')" prop="title">
          <el-input v-model="form.title" :placeholder="$t('businessKnowledge.titlePlaceholder')" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item :label="$t('businessKnowledge.category')" prop="category">
          <el-select v-model="form.category" style="width: 100%">
            <el-option label="短信" value="sms" />
            <el-option label="语音" value="voice" />
            <el-option label="数据" value="data" />
            <el-option label="通用" value="general" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="canManage" :label="$t('businessKnowledge.status')">
          <el-radio-group v-model="form.status">
            <el-radio value="published">{{ $t('businessKnowledge.statusPublished') }}</el-radio>
            <el-radio value="draft">{{ $t('businessKnowledge.statusDraft') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="canManage">
          <el-checkbox v-model="form.is_pinned">{{ $t('businessKnowledge.pinArticle') }}</el-checkbox>
        </el-form-item>
        <el-form-item :label="$t('businessKnowledge.summary')">
          <el-input v-model="form.summary" type="textarea" :rows="2" :placeholder="$t('businessKnowledge.summaryPlaceholder')" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item :label="$t('businessKnowledge.content')" prop="content">
          <el-input v-model="form.content" type="textarea" :rows="8" :placeholder="$t('businessKnowledge.contentPlaceholder')" />
          <div class="form-tip">{{ $t('businessKnowledge.markdownTip') }}</div>
        </el-form-item>
        <el-form-item :label="$t('businessKnowledge.attachments')" v-if="!editingId">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="5"
            :on-change="onFileChange"
            :file-list="fileList"
          >
            <el-button type="primary" size="small">{{ $t('businessKnowledge.selectFiles') }}</el-button>
            <span class="upload-tip">{{ $t('businessKnowledge.uploadTip') }}</span>
          </el-upload>
        </el-form-item>
        <el-form-item :label="$t('businessKnowledge.attachments')" v-else>
          <el-upload :auto-upload="false" :on-change="onExtraFileChange" :file-list="extraFileList" ref="extraUploadRef">
            <el-button type="primary" size="small">{{ $t('businessKnowledge.addMoreFiles') }}</el-button>
          </el-upload>
          <el-button v-if="extraUploadFiles.length" type="primary" size="small" :loading="uploadingExtra" @click="uploadExtraFiles" style="margin-top:8px">
            {{ $t('businessKnowledge.uploadNow') }}
          </el-button>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">{{ $t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 附件预览对话框 -->
    <el-dialog
      v-model="previewVisible"
      :title="previewAtt?.file_name"
      width="90%"
      top="5vh"
      class="preview-dialog"
      destroy-on-close
      @closed="revokePreviewUrl"
    >
      <div v-loading="previewLoading" class="preview-content">
        <iframe v-if="previewType === 'pdf'" :src="previewUrl" class="preview-iframe" />
        <el-image v-else-if="previewType === 'image'" :src="previewUrl" fit="contain" class="preview-image" />
        <video v-else-if="previewType === 'video'" :src="previewUrl" controls class="preview-video" />
        <div v-else-if="previewType === 'text'" class="preview-text" v-html="previewTextHtml"></div>
        <div v-else-if="previewType === 'unsupported'" class="preview-unsupported">
          {{ $t('businessKnowledge.previewUnsupported') }}
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Search, View, Paperclip, Document, Top } from '@element-plus/icons-vue'
import { marked } from 'marked'
import {
  listKnowledge,
  getKnowledgeArticle,
  getKnowledgeCategories,
  createKnowledgeArticle,
  updateKnowledgeArticle,
  deleteKnowledgeArticle,
  addKnowledgeAttachments,
  getAttachmentDownloadUrl,
  fetchAttachmentBlob,
  type KnowledgeArticle,
} from '@/api/knowledge'

const canManage = computed(() => {
  const role = localStorage.getItem('admin_role')
  return ['super_admin', 'admin', 'tech'].includes(role || '')
})

const loading = ref(false)
const items = ref<KnowledgeArticle[]>([])
const total = ref(0)
const categories = ref<{ value: string; label: string; count: number }[]>([])
const filters = ref({ page: 1, page_size: 20, keyword: '', category: '', status: '', sort: 'updated_at_desc' })

const loadList = async () => {
  loading.value = true
  try {
    const res = await listKnowledge({
      page: filters.value.page,
      page_size: filters.value.page_size,
      keyword: filters.value.keyword || undefined,
      category: filters.value.category || undefined,
      status: filters.value.status || undefined,
      sort: filters.value.sort,
    })
    items.value = res.items
    total.value = res.total
    loadCategories()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

const loadCategories = async () => {
  try {
    const res = await getKnowledgeCategories({ status: filters.value.status || undefined })
    categories.value = res.categories
  } catch {
    categories.value = []
  }
}

const categoryLabel = (cat: string) => {
  const map: Record<string, string> = { sms: '短信', voice: '语音', data: '数据', general: '通用' }
  return map[cat] || cat
}

const formatDate = (d?: string) => {
  if (!d) return '-'
  const dt = new Date(d)
  return dt.toLocaleString('zh-CN')
}

// 详情
const detailVisible = ref(false)
const currentArticle = ref<KnowledgeArticle | null>(null)
const contentHtml = computed(() => {
  const c = currentArticle.value?.content
  if (!c) return ''
  try {
    return marked.parse(c, { gfm: true, breaks: true }) as string
  } catch {
    return c.replace(/\n/g, '<br>')
  }
})

const viewArticle = async (item: KnowledgeArticle) => {
  try {
    const res = await getKnowledgeArticle(item.id)
    currentArticle.value = res.article
    detailVisible.value = true
    // 自动加载第一个可预览附件的内联预览
    loadInlinePreview(res.article.attachments)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
  }
}

// 内联预览（详情抽屉内直接显示）
const inlinePreviewUrl = ref('')
const inlinePreviewTextHtml = ref('')
const inlinePreviewLoading = ref(false)
const inlinePreviewFileName = ref('')
const inlinePreviewType = ref<'pdf' | 'image' | 'video' | 'text' | ''>('')
const inlinePreviewAttId = ref<number | null>(null)

const firstPreviewableAtt = computed(() => {
  const atts = currentArticle.value?.attachments || []
  return atts.find((a: any) => canPreview(a)) || null
})

const revokeInlinePreviewUrl = () => {
  if (inlinePreviewUrl.value) {
    URL.revokeObjectURL(inlinePreviewUrl.value)
    inlinePreviewUrl.value = ''
  }
  inlinePreviewTextHtml.value = ''
  inlinePreviewFileName.value = ''
  inlinePreviewType.value = ''
  inlinePreviewAttId.value = null
}

const loadInlinePreview = async (attachments?: any[]) => {
  revokeInlinePreviewUrl()
  const atts = attachments || currentArticle.value?.attachments || []
  const att = atts.find((a: any) => canPreview(a))
  if (!att) return

  inlinePreviewLoading.value = true
  inlinePreviewFileName.value = att.file_name
  inlinePreviewAttId.value = att.id

  try {
    const blob = await fetchAttachmentBlob(att.id) as Blob
    const ext = getFileExt(att.file_name)

    // 检查是否为错误响应（API 返回 JSON 时 blob 可能是错误信息）
    if (blob.type?.includes('application/json')) {
      const text = await blob.text()
      const err = JSON.parse(text)
      throw new Error(err.detail || '加载失败')
    }

    if (['.txt', '.md'].includes('.' + ext)) {
      inlinePreviewType.value = 'text'
      const text = await blob.text()
      inlinePreviewTextHtml.value = ext === 'md'
        ? marked.parse(text, { gfm: true, breaks: true }) as string
        : text.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>')
    } else if (att.file_type === 'image' || att.file_type === 'video' || ext === 'pdf') {
      inlinePreviewType.value = ext === 'pdf' ? 'pdf' : att.file_type === 'image' ? 'image' : 'video'
      inlinePreviewUrl.value = URL.createObjectURL(blob)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '预览加载失败')
    revokeInlinePreviewUrl()
  } finally {
    inlinePreviewLoading.value = false
  }
}

const onAttachmentClick = (att: any) => {
  if (canPreview(att)) {
    loadInlinePreview([att])
  }
}

const downloadAttachment = async (att: { id: number; file_name: string }) => {
  try {
    const base = import.meta.env.VITE_API_BASE_URL ? `${import.meta.env.VITE_API_BASE_URL}/api/v1` : '/api/v1'
    const url = `${base}${getAttachmentDownloadUrl(att.id)}`
    const token = localStorage.getItem('admin_token')
    const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = att.file_name
    a.click()
    URL.revokeObjectURL(a.href)
  } catch (e) {
    ElMessage.error('下载失败')
  }
}

// 附件预览
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewAtt = ref<{ id: number; file_name: string; file_type: string } | null>(null)
const previewUrl = ref('')
const previewTextHtml = ref('')
const previewType = ref<'pdf' | 'image' | 'video' | 'text' | 'unsupported'>('unsupported')

const getFileExt = (name: string) => (name || '').split('.').pop()?.toLowerCase() || ''

const canPreview = (att: { file_name: string; file_type: string }) => {
  const ext = getFileExt(att.file_name)
  if (att.file_type === 'image') return true
  if (att.file_type === 'video') return true
  if (att.file_type === 'doc' && ['.pdf', '.txt', '.md'].includes('.' + ext)) return true
  return false
}

const revokePreviewUrl = () => {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
}

const previewAttachment = async (att: { id: number; file_name: string; file_type: string }) => {
  const ext = getFileExt(att.file_name)
  revokePreviewUrl()
  previewAtt.value = att
  previewVisible.value = true
  previewLoading.value = true
  previewType.value = 'unsupported'
  previewTextHtml.value = ''

  try {
    const blob = await fetchAttachmentBlob(att.id) as Blob

    // 文本类：TXT、MD 直接显示
    if (['.txt', '.md'].includes('.' + ext)) {
      previewType.value = 'text'
      const text = await blob.text()
      previewTextHtml.value = ext === 'md'
        ? marked.parse(text, { gfm: true, breaks: true }) as string
        : text.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>')
      previewLoading.value = false
      return
    }

    // PDF、图片、视频：使用 Blob URL
    if (att.file_type === 'image' || att.file_type === 'video' || ext === 'pdf') {
      previewType.value = ext === 'pdf' ? 'pdf' : att.file_type === 'image' ? 'image' : 'video'
      previewUrl.value = URL.createObjectURL(blob)
    } else {
      previewType.value = 'unsupported'
    }
  } catch (e) {
    ElMessage.error('预览加载失败')
    previewVisible.value = false
  } finally {
    previewLoading.value = false
  }
}

// 表单
const formVisible = ref(false)
const formRef = ref()
const submitting = ref(false)
const editingId = ref<number | null>(null)
const form = ref({ title: '', content: '', category: 'general', summary: '', status: 'published' as string, is_pinned: false })
const formRules = { title: [{ required: true, message: '请输入标题', trigger: 'blur' }] }
const fileList = ref<any[]>([])
const uploadFiles = ref<File[]>([])
const uploadRef = ref()
const extraFileList = ref<any[]>([])
const extraUploadFiles = ref<File[]>([])
const extraUploadRef = ref()
const uploadingExtra = ref(false)

const onExtraFileChange = (file: any, files: any[]) => {
  extraFileList.value = files
  extraUploadFiles.value = files.map(f => f.raw).filter(Boolean)
}

const uploadExtraFiles = async () => {
  if (!editingId.value || !extraUploadFiles.value.length) return
  uploadingExtra.value = true
  try {
    await addKnowledgeAttachments(editingId.value, extraUploadFiles.value)
    ElMessage.success('上传成功')
    extraFileList.value = []
    extraUploadFiles.value = []
    extraUploadRef.value?.clearFiles()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '上传失败')
  } finally {
    uploadingExtra.value = false
  }
}

const onFileChange = (file: any, files: any[]) => {
  fileList.value = files
  uploadFiles.value = files.map(f => f.raw).filter(Boolean)
}

const openCreate = () => {
  editingId.value = null
  form.value = { title: '', content: '', category: 'general', summary: '', status: 'published', is_pinned: false }
  fileList.value = []
  uploadFiles.value = []
  formVisible.value = true
}

const openEdit = (item: KnowledgeArticle) => {
  editingId.value = item.id
  form.value = {
    title: item.title,
    content: item.content || '',
    category: item.category,
    summary: item.summary || '',
    status: (item as any).status || 'published',
    is_pinned: item.is_pinned || false,
  }
  extraFileList.value = []
  formVisible.value = true
}

const submitForm = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    submitting.value = true
    try {
      if (editingId.value) {
        await updateKnowledgeArticle(editingId.value, {
          title: form.value.title,
          content: form.value.content,
          category: form.value.category,
          summary: form.value.summary,
          status: form.value.status,
          is_pinned: form.value.is_pinned,
        })
        ElMessage.success('更新成功')
      } else {
        const fd = new FormData()
        fd.append('title', form.value.title)
        fd.append('content', form.value.content)
        fd.append('category', form.value.category)
        fd.append('status', form.value.status)
        fd.append('is_pinned', String(form.value.is_pinned))
        if (form.value.summary) fd.append('summary', form.value.summary)
        uploadFiles.value.forEach(f => fd.append('files', f))
        await createKnowledgeArticle(fd)
        ElMessage.success('创建成功')
      }
      formVisible.value = false
      loadList()
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
    } finally {
      submitting.value = false
    }
  })
}

const handleDelete = async (id: number) => {
  try {
    await deleteKnowledgeArticle(id)
    ElMessage.success('删除成功')
    loadList()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

const togglePin = async (item: KnowledgeArticle) => {
  try {
    await updateKnowledgeArticle(item.id, { is_pinned: !item.is_pinned })
    ElMessage.success(item.is_pinned ? '已取消置顶' : '已置顶')
    loadList()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

onMounted(() => {
  loadList()
})
</script>

<style scoped>
.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}
.article-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
.article-card {
  cursor: pointer;
  transition: all 0.2s;
}
.article-card:hover {
  transform: translateY(-2px);
}
.card-body {
  min-height: 100px;
}
.card-title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}
.pin-icon {
  color: var(--el-color-warning);
  margin-right: 4px;
  vertical-align: middle;
}
.card-tags {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.article-title {
  margin: 0 0 8px 0;
  font-size: 16px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.article-summary {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.card-meta .time {
  margin-left: auto;
}
.card-actions {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.pagination-wrap {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
.detail-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.detail-content {
  line-height: 1.8;
}
/* Markdown 内容样式 */
.detail-content :deep(h1) { font-size: 1.5em; margin: 1em 0 0.5em; }
.detail-content :deep(h2) { font-size: 1.25em; margin: 1em 0 0.5em; }
.detail-content :deep(h3) { font-size: 1.1em; margin: 0.8em 0 0.4em; }
.detail-content :deep(ul), .detail-content :deep(ol) { margin: 0.5em 0; padding-left: 1.5em; }
.detail-content :deep(code) { background: var(--el-fill-color-light); padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
.detail-content :deep(pre) { background: var(--el-fill-color-darker); padding: 12px; border-radius: 6px; overflow-x: auto; }
.detail-content :deep(pre code) { background: none; padding: 0; }
.detail-content :deep(a) { color: var(--el-color-primary); }
.detail-content :deep(img) { max-width: 100%; height: auto; border-radius: 4px; }
.attachments {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.attach-list {
  margin-top: 8px;
}
.attach-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
}
.upload-tip {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.form-tip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.attach-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attach-clickable {
  cursor: pointer;
  color: var(--el-color-primary);
}
.attach-clickable:hover {
  text-decoration: underline;
}
.inline-preview {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.inline-preview h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
}
.inline-preview-body {
  min-height: 400px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  overflow: hidden;
}
.inline-preview-iframe {
  width: 100%;
  height: 70vh;
  min-height: 500px;
  border: none;
}
.inline-preview-image {
  width: 100%;
  max-height: 70vh;
  display: block;
}
.inline-preview-video {
  width: 100%;
  max-height: 70vh;
}
.inline-preview-text {
  padding: 16px;
  max-height: 70vh;
  overflow-y: auto;
  line-height: 1.6;
  white-space: pre-wrap;
}
.inline-preview-text :deep(pre) { white-space: pre-wrap; }
.preview-dialog :deep(.el-dialog__body) {
  padding: 0;
  max-height: 80vh;
  overflow: hidden;
}
.preview-content {
  min-height: 400px;
}
.preview-iframe {
  width: 100%;
  height: 80vh;
  min-height: 500px;
  border: none;
}
.preview-image {
  width: 100%;
  max-height: 80vh;
  display: block;
}
.preview-video {
  width: 100%;
  max-height: 80vh;
}
.preview-text {
  padding: 16px;
  max-height: 80vh;
  overflow-y: auto;
  line-height: 1.6;
  white-space: pre-wrap;
}
.preview-text :deep(pre) { white-space: pre-wrap; }
.preview-unsupported {
  padding: 40px;
  text-align: center;
  color: var(--el-text-color-secondary);
}
</style>
