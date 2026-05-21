package main

// 批次取消运行期标记：Python `cancel_batch` 调用时往 Redis 写
// `batch:cancelled:{batch_id}=1`（7 天 TTL）。Go 网关在消费 sms_send_smpp
// 单条短信前查询该 key；命中即跳过 submit，避免取消的批次继续打到上游。
//
// 与 DLR 归属过滤独立、独占 Redis 客户端，无需启用 DLR_OWNERSHIP_FILTER 也生效。

import (
	"context"
	"fmt"
	"log"
	"os"
	"sync/atomic"
	"time"

	"github.com/redis/go-redis/v9"
)

const batchCancelKeyPrefix = "batch:cancelled:"

var (
	cancelRdb       *redis.Client
	cancelHits      atomic.Uint64
	cancelLookups   atomic.Uint64
	cancelRedisErrs atomic.Uint64
)

// InitBatchCancel 初始化用于批次取消查询的 Redis 客户端。Redis 不可用时 fail-open。
func InitBatchCancel() {
	host := os.Getenv("REDIS_HOST")
	if host == "" {
		host = "redis"
	}
	port := os.Getenv("REDIS_PORT")
	if port == "" {
		port = "6379"
	}
	addr := fmt.Sprintf("%s:%s", host, port)

	cancelRdb = redis.NewClient(&redis.Options{
		Addr:         addr,
		Password:     os.Getenv("REDIS_PASSWORD"),
		DB:           0,
		DialTimeout:  3 * time.Second,
		ReadTimeout:  300 * time.Millisecond,
		WriteTimeout: 300 * time.Millisecond,
		PoolSize:     20,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if err := cancelRdb.Ping(ctx).Err(); err != nil {
		log.Printf("[BATCH-CANCEL] Redis unreachable at %s: %v — checks will fail-open", addr, err)
		return
	}
	log.Printf("[BATCH-CANCEL] enabled, Redis=%s", addr)

	go cancelStatsLogger()
}

// IsBatchCancelled 查询 Redis 判断该批次是否已取消。fail-open：Redis 异常返回 false。
func IsBatchCancelled(batchID int64) bool {
	if cancelRdb == nil || batchID <= 0 {
		return false
	}
	cancelLookups.Add(1)
	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
	defer cancel()
	key := fmt.Sprintf("%s%d", batchCancelKeyPrefix, batchID)
	n, err := cancelRdb.Exists(ctx, key).Result()
	if err != nil {
		cancelRedisErrs.Add(1)
		return false
	}
	if n > 0 {
		cancelHits.Add(1)
		return true
	}
	return false
}

// LookupBatchIDByLogID 兼容旧 payload（无 batch_id 字段）：按 log_id 反查 sms_logs.batch_id。
// 仅在 data.BatchID==0 时触发；DB 异常或未关联批次时返回 0（fail-open，按非批次处理）。
func LookupBatchIDByLogID(logID int64) int64 {
	if db == nil || logID <= 0 {
		return 0
	}
	var batchID int64
	row := db.QueryRow("SELECT COALESCE(batch_id, 0) FROM sms_logs WHERE id=? LIMIT 1", logID)
	if err := row.Scan(&batchID); err != nil {
		return 0
	}
	return batchID
}

// LookupCurrentStatus 实时查 sms_logs.status，用于 SMPP 提交前的幂等兜底：
// 若网关因重启等原因重新消费到已处理过的 delivery，DB status 已不是 pending/queued，
// 即跳过此次重复 submit，避免在上游重复计费。
func LookupCurrentStatus(logID int64) string {
	if db == nil || logID <= 0 {
		return ""
	}
	var status string
	row := db.QueryRow("SELECT status FROM sms_logs WHERE id=? LIMIT 1", logID)
	if err := row.Scan(&status); err != nil {
		return ""
	}
	return status
}

func cancelStatsLogger() {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()
	var lastLookups, lastHits, lastErrs uint64
	for range ticker.C {
		ll := cancelLookups.Load()
		lh := cancelHits.Load()
		le := cancelRedisErrs.Load()
		log.Printf("[BATCH-CANCEL] last 5min: lookups=%d, cancel_hits=%d, redis_errs=%d",
			ll-lastLookups, lh-lastHits, le-lastErrs)
		lastLookups, lastHits, lastErrs = ll, lh, le
	}
}
