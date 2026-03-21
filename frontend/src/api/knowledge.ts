/**
 * 知识库 API
 */
import { request } from './index'

export interface KnowledgeArticle {
  id: number
  title: string
  summary?: string
  content?: string
  category: string
  status?: string
  view_count: number
  is_pinned?: boolean
  attachment_count: number
  attachments?: { id: number; file_type: string; file_name: string; file_size: number; url: string }[]
  created_at?: string
  updated_at?: string
}

export function listKnowledge(params: {
  page?: number
  page_size?: number
  category?: string
  keyword?: string
  status?: string
  sort?: string
}) {
  return request.get('/admin/knowledge', { params }) as Promise<{ success: boolean; total: number; items: KnowledgeArticle[] }>
}

export function getKnowledgeCategories(params?: { status?: string }) {
  return request.get('/admin/knowledge/categories', { params }) as Promise<{ success: boolean; categories: { value: string; label: string; count: number }[] }>
}

export function getKnowledgeArticle(id: number) {
  return request.get(`/admin/knowledge/${id}`) as Promise<{ success: boolean; article: KnowledgeArticle }>
}

export function createKnowledgeArticle(formData: FormData) {
  return request.post('/admin/knowledge', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function updateKnowledgeArticle(id: number, data: {
  title?: string
  content?: string
  category?: string
  summary?: string
  status?: string
  is_pinned?: boolean
}) {
  return request.put(`/admin/knowledge/${id}`, data)
}

export function deleteKnowledgeArticle(id: number) {
  return request.delete(`/admin/knowledge/${id}`)
}

export function addKnowledgeAttachments(articleId: number, files: File[]) {
  const formData = new FormData()
  files.forEach(f => formData.append('files', f))
  return request.post(`/admin/knowledge/${articleId}/attachments`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 附件下载地址（需携带 token，通过 request 发起） */
export function getAttachmentDownloadUrl(attachmentId: number): string {
  return `/admin/knowledge/attachment/${attachmentId}`
}

/** 获取附件 Blob（用于预览） */
export function fetchAttachmentBlob(attachmentId: number) {
  return request.get(getAttachmentDownloadUrl(attachmentId), { responseType: 'blob' }) as Promise<Blob>
}
