import { ref, computed } from 'vue'
import type { PaginationParams } from '@/types'

/**
 * 表格分页逻辑复用
 */
export function usePagination(initialPageSize = 20) {
  const page = ref(1)
  const pageSize = ref(initialPageSize)
  const total = ref(0)

  const paginationParams = computed<PaginationParams>(() => ({
    page: page.value,
    page_size: pageSize.value,
  }))

  function setTotal(val: number) {
    total.value = val
  }

  function reset() {
    page.value = 1
    total.value = 0
  }

  function handlePageChange(p: number) {
    page.value = p
  }

  function handleSizeChange(size: number) {
    pageSize.value = size
    page.value = 1
  }

  return {
    page,
    pageSize,
    total,
    paginationParams,
    setTotal,
    reset,
    handlePageChange,
    handleSizeChange,
  }
}
