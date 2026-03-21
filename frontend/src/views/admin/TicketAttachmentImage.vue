<template>
  <el-image
    v-if="blobUrl"
    :src="blobUrl"
    fit="cover"
    class="attachment-thumb"
    :preview-src-list="[blobUrl]"
  />
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import request from '@/api/index'

const props = defineProps<{
  ticketId: number
  filename: string
}>()

const blobUrl = ref('')

const loadImage = async () => {
  if (!props.ticketId || !props.filename) return
  try {
    const res = await request.get(
      `/admin/tickets/${props.ticketId}/attachments/${props.filename}`,
      { responseType: 'blob' }
    )
    blobUrl.value = URL.createObjectURL(res as Blob)
  } catch (e) {
    console.error('Failed to load attachment:', e)
  }
}

onMounted(loadImage)
onUnmounted(() => {
  if (blobUrl.value) URL.revokeObjectURL(blobUrl.value)
})

watch(() => [props.ticketId, props.filename], () => {
  if (blobUrl.value) URL.revokeObjectURL(blobUrl.value)
  blobUrl.value = ''
  loadImage()
})
</script>

<style scoped>
.attachment-thumb {
  width: 80px;
  height: 80px;
  margin-right: 8px;
  margin-top: 4px;
  border-radius: 4px;
  cursor: pointer;
}
</style>
