<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">我的私有库</h2>
      <div class="header-actions">
        <el-button type="primary" @click="$router.push('/data/store')">前往商店选购</el-button>
      </div>
    </div>

    <!-- 总览统计 -->
    <div class="summary-bar" v-if="totalCount > 0">
      <div class="summary-item">
        <span class="summary-value">{{ totalCount.toLocaleString() }}</span>
        <span class="summary-label">总号码数</span>
      </div>
      <div class="summary-item">
        <span class="summary-value">{{ groups.length }}</span>
        <span class="summary-label">数据分组</span>
      </div>
    </div>

    <!-- 卡片列表 -->
    <div v-loading="loading">
      <el-empty v-if="!loading && groups.length === 0" description="暂无私有库数据，请前往商店购买" />

      <el-row :gutter="16">
        <el-col :xs="24" :sm="12" :lg="8" v-for="(g, idx) in groups" :key="idx">
          <el-card class="group-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <div class="card-title">
                  <el-tag size="small" type="info" style="margin-right:6px">{{ countryName(g.country_code) }}</el-tag>
                  <span class="card-name">{{ g.source_label }} · {{ g.purpose_label }}</span>
                </div>
                <span class="card-count">{{ g.count.toLocaleString() }} 条</span>
              </div>
            </template>

            <div class="card-body">
              <div class="card-info">
                <div class="info-row">
                  <span class="info-label">来源</span>
                  <el-tag size="small" type="danger">{{ g.source_label || g.source }}</el-tag>
                </div>
                <div class="info-row">
                  <span class="info-label">用途</span>
                  <el-tag size="small" type="warning">{{ g.purpose_label || g.purpose }}</el-tag>
                </div>
                <div class="info-row">
                  <span class="info-label">国家</span>
                  <span>{{ countryName(g.country_code) }} ({{ g.country_code }})</span>
                </div>
                <div class="info-row" v-if="g.last_at">
                  <span class="info-label">最新入库</span>
                  <span class="info-date">{{ fmtDate(g.last_at) }}</span>
                </div>
              </div>

              <div class="card-actions">
                <el-button type="success" size="small" @click="handleSendSms(g)">
                  发送短信
                </el-button>
                <el-dropdown @command="(cmd: string) => handleExport(g, cmd)">
                  <el-button type="primary" size="small">
                    下载数据 <el-icon style="margin-left:4px"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="csv">导出 CSV</el-dropdown-item>
                      <el-dropdown-item command="txt">导出 TXT（纯号码）</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowDown } from '@element-plus/icons-vue'
import { getMyNumbersSummary, exportMyNumbers } from '@/api/data'
import { ElMessage } from 'element-plus'
import { findCountryByIso } from '@/constants/countries'

const router = useRouter()

interface NumberGroup {
  country_code: string
  source: string
  source_label: string
  purpose: string
  purpose_label: string
  count: number
  first_at: string | null
  last_at: string | null
}

const groups = ref<NumberGroup[]>([])
const totalCount = ref(0)
const loading = ref(false)

function countryName(code: string): string {
  if (!code) return '未知'
  const c = findCountryByIso(code)
  return c ? c.name : code
}

function fmtDate(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('zh-CN')
}

async function loadData() {
  loading.value = true
  try {
    const res = await getMyNumbersSummary()
    if (res.success) {
      groups.value = res.items || []
      totalCount.value = res.total || 0
    }
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function handleExport(g: NumberGroup, fmt: string) {
  try {
    const res = await exportMyNumbers({
      fmt,
      country: g.country_code || undefined,
      source: g.source || undefined,
      purpose: g.purpose || undefined,
    })
    const ext = fmt === 'txt' ? 'txt' : 'csv'
    const mimeType = fmt === 'txt' ? 'text/plain' : 'text/csv'
    const blob = new Blob([res], { type: mimeType })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${g.country_code}_${g.source}_${g.purpose}_${Date.now()}.${ext}`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e: any) {
    ElMessage.error('导出失败: ' + (e.message || ''))
  }
}

function handleSendSms(g: NumberGroup) {
  router.push({
    path: '/sms/send',
    query: {
      data_country: g.country_code,
      data_source: g.source,
      data_purpose: g.purpose,
      data_count: String(g.count),
    },
  })
}

onMounted(loadData)
</script>

<style scoped>
.page-container { width: 100%; padding: 0 4px; }
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.page-title { font-size: 20px; font-weight: 600; margin: 0; }

.summary-bar {
  display: flex;
  gap: 32px;
  padding: 16px 24px;
  margin-bottom: 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  color: #fff;
}
.summary-item { display: flex; flex-direction: column; }
.summary-value { font-size: 28px; font-weight: 700; line-height: 1.2; }
.summary-label { font-size: 13px; opacity: 0.85; margin-top: 2px; }

.group-card {
  margin-bottom: 16px;
  border-radius: 12px;
  transition: transform 0.2s;
}
.group-card:hover { transform: translateY(-2px); }

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-title { display: flex; align-items: center; }
.card-name { font-weight: 600; font-size: 15px; }
.card-count {
  font-size: 18px;
  font-weight: 700;
  color: var(--el-color-primary);
}

.card-body { display: flex; flex-direction: column; gap: 14px; }
.card-info { display: flex; flex-direction: column; gap: 8px; }
.info-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.info-label {
  color: var(--el-text-color-secondary);
  min-width: 56px;
  flex-shrink: 0;
}
.info-date { color: var(--el-text-color-secondary); font-size: 12px; }

.card-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}
</style>
