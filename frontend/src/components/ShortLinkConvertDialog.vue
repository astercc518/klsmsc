<template>
  <el-dialog
    v-model="visible"
    title="短链转换"
    width="640px"
    destroy-on-close
    append-to-body
    @open="onOpen"
  >
    <el-form label-position="top" @submit.prevent>
      <el-form-item label="短链域名">
        <el-select
          v-model="form.domainId"
          placeholder="请选择域名"
          style="width: 100%"
          :loading="domainLoading"
          filterable
        >
          <el-option
            v-for="d in domains"
            :key="d.id"
            :label="d.base_url"
            :value="d.id"
          >
            <span>{{ d.base_url }}</span>
            <el-tag
              v-if="!d.base_url.startsWith('http')"
              size="small"
              type="success"
              effect="plain"
              style="margin-left: 8px"
            >省字符</el-tag>
            <span v-if="d.remark" style="color: var(--el-text-color-placeholder); margin-left: 8px; font-size: 12px">
              {{ d.remark }}
            </span>
          </el-option>
        </el-select>
        <div class="hint" v-if="!domains.length && !domainLoading">
          暂无可用域名，请联系管理员在「系统管理 → 短链域名」中配置
        </div>
      </el-form-item>

      <el-form-item label="原始链接">
        <el-input
          v-model="form.targetUrl"
          placeholder="https://promo.example.com/landing"
          clearable
        />
        <div class="hint">点击后将 302 重定向到此地址；点击量与时间会异步落库</div>
      </el-form-item>

      <el-form-item label="短信文案">
        <el-input
          v-model="form.message"
          type="textarea"
          :rows="6"
          placeholder="支持把原始链接直接写在文中，转换时自动替换；不写也可以，转换会在末尾追加占位符"
        />
        <div class="hint">
          说明：
          <ul class="hint-list">
            <li>若文案里有完整的 https:// 链接，转换会替换该链接</li>
            <li>若没有，转换会把占位符追加到文末</li>
            <li>每个手机号收到的短链各自唯一，可独立追踪点击</li>
          </ul>
        </div>
      </el-form-item>

      <el-form-item label="预览（占位符内容）" v-if="previewMessage">
        <div class="preview-box">{{ previewMessage }}</div>
        <div v-if="charSavings" class="savings-hint">
          ✨ 该域名为「省字符」模式，每条短信约节省
          <strong>{{ charSavings }}</strong> 字符
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="!canConvert" @click="handleConvert">
        转换并填入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listActiveShortLinkDomains,
  buildTrackUrlPlaceholder,
  type ShortLinkDomain,
} from '../api/short-link'

interface Props {
  modelValue: boolean
  /** 当前文案，会预填到对话框 */
  message?: string
}
const props = withDefaults(defineProps<Props>(), {
  message: '',
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  /** 用户点击「转换并填入」时触发，参数为带占位符的新文案 */
  (e: 'apply', newMessage: string): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const domains = ref<ShortLinkDomain[]>([])
const domainLoading = ref(false)

const form = ref({
  domainId: undefined as number | undefined,
  targetUrl: '',
  message: '',
})

const URL_RE = /https?:\/\/[^\s)\]>]+/i

const canConvert = computed(
  () => Boolean(form.value.domainId) && Boolean((form.value.targetUrl || '').trim()),
)

const previewMessage = computed(() => {
  if (!canConvert.value) return ''
  const dom = domains.value.find((d) => d.id === form.value.domainId)
  if (!dom) return ''
  const placeholder = buildTrackUrlPlaceholder({
    targetUrl: form.value.targetUrl.trim(),
    baseUrl: dom.base_url,
  })
  const msg = form.value.message || ''
  if (URL_RE.test(msg)) {
    return msg.replace(URL_RE, placeholder)
  }
  return msg ? `${msg.replace(/\s+$/, '')} ${placeholder}` : placeholder
})

const charSavings = computed(() => {
  const dom = domains.value.find((d) => d.id === form.value.domainId)
  if (!dom) return 0
  // base_url 越短节省越多；以传统 https://xxx.com/s 为基准（典型 ~25 字符）
  const baseFull = dom.base_url.startsWith('http')
    ? dom.base_url
    : `https://${dom.base_url.replace(/^https?:\/\//, '')}`
  const baseFullWithS = baseFull.includes('/s') ? baseFull : `${baseFull}/s`
  const saving = baseFullWithS.length - dom.base_url.length
  return saving > 0 ? saving : 0
})

async function loadDomains() {
  domainLoading.value = true
  try {
    const resp: any = await listActiveShortLinkDomains()
    domains.value = (resp?.data?.data || resp?.data || []) as ShortLinkDomain[]
    if (!form.value.domainId && domains.value.length) {
      form.value.domainId = domains.value[0].id
    }
  } catch (e) {
    ElMessage.warning('加载短链域名失败，请稍后重试')
  } finally {
    domainLoading.value = false
  }
}

function onOpen() {
  // 预填当前文案；自动从文案中提取首个 URL 作为「原始链接」默认值
  form.value.message = props.message || ''
  if (!form.value.targetUrl) {
    const m = (props.message || '').match(URL_RE)
    if (m) form.value.targetUrl = m[0]
  }
  loadDomains()
}

watch(
  () => props.message,
  (m) => {
    if (visible.value) form.value.message = m || ''
  },
)

function handleConvert() {
  if (!canConvert.value) return
  emit('apply', previewMessage.value)
  visible.value = false
  ElMessage.success('已生成短链占位符并填入文案')
}
</script>

<style scoped>
.hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin-top: 4px;
  line-height: 1.6;
}
.hint-list {
  padding-left: 18px;
  margin: 4px 0 0;
}
.preview-box {
  background: var(--el-fill-color-light);
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  padding: 10px 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--el-text-color-primary);
}
.savings-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-color-success);
}
</style>
