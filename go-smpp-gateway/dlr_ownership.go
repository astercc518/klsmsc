package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"strings"
	"sync/atomic"
	"time"

	"github.com/redis/go-redis/v9"
)

// DLR 归属过滤：当多套系统共用同一上游 SMPP 账号时，上游会把 DLR 广播给所有当前在线的 bind。
// 没有归属判断的话，外来系统的 DLR 会持续涌入本系统的 sms_dlr 队列与 Worker，永远匹配不到 sms_logs，
// 最终堆积在 Redis 重试缓冲（dlr_pending_retry）耗费资源。
//
// 本模块在 SubmitSMResp 成功时把 (channel_id, upstream_message_id) 写入 Redis；DeliverSM 抵达时
// 只接受存在该索引的 DLR，未命中则直接丢弃（不进 RabbitMQ、不进 Worker、不进重试缓冲）。

const (
	ownershipKeyPrefix = "dlr_owned:" // dlr_owned:{channel_id}:{upstream_id} = "1"
	ownershipTTL       = 7 * 24 * time.Hour
)

var (
	rdb            *redis.Client
	filterEnabled  atomic.Bool // 运行期可以通过环境变量切换
	dropCounter    atomic.Uint64
	acceptCounter  atomic.Uint64
	markRetryQueue chan ownEntry // MarkOwned 失败的异步重试队列
	retryDropped   atomic.Uint64
)

type ownEntry struct {
	channelID  int
	upstreamID string
	attempts   int
}

// InitDLROwnership 初始化 Redis 客户端与运行期开关。Redis 不可用时返回 nil（fail-open）。
func InitDLROwnership() {
	enabled := strings.EqualFold(strings.TrimSpace(os.Getenv("DLR_OWNERSHIP_FILTER")), "true")
	filterEnabled.Store(enabled)
	if !enabled {
		log.Printf("[DLR-OWNERSHIP] disabled (set DLR_OWNERSHIP_FILTER=true to enable)")
		return
	}

	host := os.Getenv("REDIS_HOST")
	if host == "" {
		host = "redis"
	}
	port := os.Getenv("REDIS_PORT")
	if port == "" {
		port = "6379"
	}
	addr := fmt.Sprintf("%s:%s", host, port)

	rdb = redis.NewClient(&redis.Options{
		Addr:         addr,
		Password:     os.Getenv("REDIS_PASSWORD"), // 此部署无密码；保留以便兼容
		DB:           0,
		DialTimeout:  3 * time.Second,
		ReadTimeout:  500 * time.Millisecond,
		WriteTimeout: 500 * time.Millisecond,
		PoolSize:     20,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		log.Printf("[DLR-OWNERSHIP] Redis unreachable at %s: %v — filter will fail-open until reconnect", addr, err)
		// 仍保留 client，后续操作会按超时 fail-open
		return
	}
	log.Printf("[DLR-OWNERSHIP] enabled, Redis=%s, ttl=%v", addr, ownershipTTL)

	// 启动时回填最近 7 天的 sms_logs，避免部署后历史在途消息的 DLR 被误丢
	go backfillOwnership()

	// 每 5 分钟打印一次过滤统计
	go statsLogger()

	// 异步重试 worker：处理 MarkOwned 在 Redis 抖动时的失败
	// 容量 10k 足以兜住短时抖动；满了就丢最老的（淘汰策略避免无限堆积）
	markRetryQueue = make(chan ownEntry, 10000)
	go markRetryWorker()
}

func ownershipKey(channelID int, upstreamID string) string {
	return fmt.Sprintf("%s%d:%s", ownershipKeyPrefix, channelID, upstreamID)
}

// MarkOwned 在 SubmitSMResp 成功时调用，把 upstream_id 标记为本系统所有。
// 首次写入失败时入异步重试队列，避免阻塞 SMPP 读包线程；重试在后台 goroutine 进行。
func MarkOwned(channelID int, upstreamID string) {
	if !filterEnabled.Load() || rdb == nil || upstreamID == "" {
		return
	}
	if err := setOwnershipKey(channelID, upstreamID, 300*time.Millisecond); err != nil {
		// 入队异步重试；满了就丢最老的避免阻塞 SMPP 线程
		entry := ownEntry{channelID: channelID, upstreamID: upstreamID, attempts: 1}
		select {
		case markRetryQueue <- entry:
		default:
			// 队列满：先丢一个最老的，再尝试入队
			select {
			case <-markRetryQueue:
				retryDropped.Add(1)
			default:
			}
			select {
			case markRetryQueue <- entry:
			default:
				retryDropped.Add(1)
			}
		}
	}
}

// setOwnershipKey 单次 SET，带超时。caller 决定是否重试。
func setOwnershipKey(channelID int, upstreamID string, timeout time.Duration) error {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	return rdb.Set(ctx, ownershipKey(channelID, upstreamID), "1", ownershipTTL).Err()
}

// markRetryWorker 串行重试 MarkOwned 失败的条目，指数退避，最多 5 次。
// 单 goroutine 足够：MarkOwned 通常 sub-ms 完成，仅在 Redis 异常期间才会有积压；
// 此时所有重试都会失败，串行/并行没差别，串行更省连接。
func markRetryWorker() {
	for entry := range markRetryQueue {
		// 退避：1s, 2s, 4s, 8s, 16s（cumulative 31s 大概率覆盖短时抖动）
		backoff := time.Duration(1<<(entry.attempts-1)) * time.Second
		if backoff > 16*time.Second {
			backoff = 16 * time.Second
		}
		time.Sleep(backoff)

		if err := setOwnershipKey(entry.channelID, entry.upstreamID, 1*time.Second); err == nil {
			log.Printf("[DLR-OWNERSHIP] MarkOwned recovered after %d attempts: channel=%d upstream=%s",
				entry.attempts, entry.channelID, entry.upstreamID)
			continue
		}

		entry.attempts++
		if entry.attempts > 5 {
			// 放弃：DLR 回来时如果在 5 次重试窗口（约 31 秒）之后，会被当作外来 DLR 丢弃
			retryDropped.Add(1)
			log.Printf("[DLR-OWNERSHIP] MarkOwned giving up after 5 attempts: channel=%d upstream=%s",
				entry.channelID, entry.upstreamID)
			continue
		}
		// 重新入队
		select {
		case markRetryQueue <- entry:
		default:
			retryDropped.Add(1)
		}
	}
}

// IsOwned 在 DeliverSM 抵达时调用。返回：
//   ownsIt = true  → 本系统所有，正常发布到 RabbitMQ
//   ownsIt = false → 索引未命中（外来或索引未及时写入），按 fallback 决定
// fallback：当 Redis 出错时返回 true（fail-open，避免 Redis 抖动丢失自家 DLR）。
func IsOwned(channelID int, upstreamID string) (ownsIt bool, hardMiss bool) {
	if !filterEnabled.Load() {
		return true, false
	}
	if rdb == nil || upstreamID == "" {
		return true, false
	}
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	n, err := rdb.Exists(ctx, ownershipKey(channelID, upstreamID)).Result()
	if err != nil {
		// fail-open：Redis 异常时不丢
		log.Printf("[DLR-OWNERSHIP] IsOwned redis err channel=%d upstream=%s: %v (fail-open)", channelID, upstreamID, err)
		return true, false
	}
	if n > 0 {
		acceptCounter.Add(1)
		return true, false
	}
	dropCounter.Add(1)
	return false, true
}

// backfillOwnership 启动时把最近 7 天 sms_logs 的 (channel_id, upstream_message_id) 写入 Redis，
// 防止刚部署时历史在途消息的 DLR 被误丢。
func backfillOwnership() {
	if db == nil {
		log.Printf("[DLR-OWNERSHIP] backfill skipped: DB not initialized")
		return
	}
	start := time.Now()
	rows, err := db.Query(
		"SELECT channel_id, upstream_message_id FROM sms_logs " +
			"WHERE upstream_message_id IS NOT NULL AND upstream_message_id<>'' " +
			"AND submit_time >= NOW() - INTERVAL 7 DAY",
	)
	if err != nil {
		log.Printf("[DLR-OWNERSHIP] backfill query err: %v", err)
		return
	}
	defer rows.Close()

	count := 0
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	pipe := rdb.Pipeline()
	for rows.Next() {
		var channelID int
		var upstreamID string
		if err := rows.Scan(&channelID, &upstreamID); err != nil {
			continue
		}
		pipe.Set(ctx, ownershipKey(channelID, upstreamID), "1", ownershipTTL)
		count++
		if count%2000 == 0 {
			if _, err := pipe.Exec(ctx); err != nil {
				log.Printf("[DLR-OWNERSHIP] backfill exec err at %d: %v", count, err)
			}
			pipe = rdb.Pipeline()
		}
	}
	if _, err := pipe.Exec(ctx); err != nil {
		log.Printf("[DLR-OWNERSHIP] backfill final exec err: %v", err)
	}
	log.Printf("[DLR-OWNERSHIP] backfill done: %d entries in %v", count, time.Since(start))
}

func statsLogger() {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()
	for range ticker.C {
		drops := dropCounter.Swap(0)
		accepts := acceptCounter.Swap(0)
		retryQ := 0
		if markRetryQueue != nil {
			retryQ = len(markRetryQueue)
		}
		retryGiveUp := retryDropped.Swap(0)
		if drops > 0 || accepts > 0 || retryQ > 0 || retryGiveUp > 0 {
			log.Printf("[DLR-OWNERSHIP] last 5min: accepted=%d, dropped=%d (foreign DLRs), mark_retry_queue=%d, mark_retry_giveup=%d",
				accepts, drops, retryQ, retryGiveUp)
		}
	}
}
