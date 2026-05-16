import { isRef, watch, type Ref, type WatchSource } from 'vue'

/**
 * 筛选条件 localStorage 持久化
 *
 * 用法：在 setup() 末尾调用一次（在数据 ref 创建之后、首次请求之前），
 * 即可把指定 ref 的值写入 localStorage，并在下次访问时自动恢复。
 *
 * 设计取舍：
 * - 仅持久化「筛选/搜索」字段，不持久化分页（page/pageSize）。分页恢复反而困惑。
 * - 失败时静默：localStorage 被禁用 / 容量满 / JSON 损坏，一律走默认值。
 * - 用整体 JSON 单 key，迁移/清理更简单。
 * - 每个页面通过 `key` 唯一隔离，避免互相污染。
 *
 * @example
 *   const searchForm = ref({ status: '', keyword: '' })
 *   const dateRange = ref<string[] | null>(null)
 *   useFilterPersist('sms-records-filters', { searchForm, dateRange })
 *   await loadRecords() // searchForm/dateRange 已被恢复
 */
type FilterValueMap = Record<string, Ref<unknown> | Record<string, unknown>>

/**
 * 读 / 写一个条目（ref 走 .value；reactive 对象直接读 / 整体合并）
 */
function readEntry(entry: Ref<unknown> | Record<string, unknown>): unknown {
  if (isRef(entry)) return entry.value
  // reactive 对象：返回浅拷贝快照
  return { ...entry }
}
function writeEntry(entry: Ref<unknown> | Record<string, unknown>, val: unknown): void {
  if (isRef(entry)) {
    entry.value = val
    return
  }
  if (val && typeof val === 'object') {
    // 合并到 reactive，保留响应式
    Object.assign(entry, val as Record<string, unknown>)
  }
}

export function useFilterPersist<T extends FilterValueMap>(
  key: string,
  refs: T,
  opts: {
    /** 仅在这些键存在时才尝试恢复（避免 schema 变化后写入老字段）；不传则恢复全部 */
    allowKeys?: (keyof T)[]
    /** 最长保留时长（毫秒），过期则忽略；默认 7 天 */
    ttlMs?: number
  } = {},
): void {
  const storageKey = `filters:${key}`
  const ttlMs = opts.ttlMs ?? 7 * 24 * 60 * 60 * 1000

  // 恢复
  try {
    const raw = localStorage.getItem(storageKey)
    if (raw) {
      const parsed = JSON.parse(raw) as { _ts?: number; data?: Record<string, unknown> }
      const ts = parsed?._ts || 0
      if (Date.now() - ts <= ttlMs && parsed?.data) {
        const allow = opts.allowKeys
        for (const k of Object.keys(refs) as (keyof T)[]) {
          if (allow && !allow.includes(k)) continue
          if (k in parsed.data) {
            try {
              writeEntry(refs[k], parsed.data[k as string])
            } catch { /* 单字段恢复失败：忽略 */ }
          }
        }
      } else {
        localStorage.removeItem(storageKey)
      }
    }
  } catch {
    // localStorage 不可用或 JSON 坏掉：走默认值
  }

  // 持久化：合并所有源进一个 watch，避免开 N 个监听器
  const sources: WatchSource[] = Object.values(refs).map(entry => () => readEntry(entry))
  watch(
    sources,
    () => {
      try {
        const data: Record<string, unknown> = {}
        for (const k of Object.keys(refs) as (keyof T)[]) {
          data[k as string] = readEntry(refs[k])
        }
        localStorage.setItem(storageKey, JSON.stringify({ _ts: Date.now(), data }))
      } catch { /* quota exceeded 等：忽略 */ }
    },
    { deep: true },
  )
}
