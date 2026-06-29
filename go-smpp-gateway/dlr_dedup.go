package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/redis/go-redis/v9"
)

// DLR 源头去重：上游（尤其 TS_066_zhilian）按设计对每条回执重发约 4 次，跨度实测可达 2~5 分钟。
// 不去重的话 4 份全发进 sms_dlr，导致 RabbitMQ 队列爆炸 + Python Worker 4 倍 DB 负载（每条都查库）。
//
// 安全性关键：自动回 deliver_sm_resp 发生在 gosmpp 读循环（receivable.go），早于 OnPDU→handleDeliverSM。
// 因此本模块的去重发生在「已经 ACK 之后」，物理上不可能引发上游更多重传——这不是没回 ACK 导致的重传，
// 实测 2 万行网关日志 0 条 "auto-response send FAILED"，且上游在被 ACK 后仍隔数分钟补发，证明是上游天性多发。
//
// 三个设计约束（缺一即隐性出错）：
//   1. key = (channel_id, upstream_id, stat)：DELIVRD→UNDELIV 是不同 stat，必须都放行
//      （Python 终态保护依赖看到 UNDELIV 才能拦住迟到 DELIVRD 翻转）。要折叠的只是「同 id 同 stat」的纯重复。
//   2. Redis 全局存储：一个通道有多个 SMPP bind（独立 goroutine），4 份副本可能落在不同 bind，
//      只有共享存储才能跨 bind 去重；进程内 per-session map 会漏。
//   3. 发布成功后才标记（MarkDLRPublished 在 PublishCeleryTask 成功之后调用）：
//      发布失败时键不写入，上游下次重传会再次放行 → 天然重试，绝不丢回执。
//
// check-then-mark 之间有极小并发窗口（两份同时通过 Exists 都发布），只会造成偶发「少去重一份」，
// 由 Python 侧 dlr_seen 短路兜底，绝不会丢回执。宁可偶发重复，不可漏。
//
// fail-open：Redis 异常时一律放行发布，宁可重复也不漏自家回执。

const (
	dedupKeyPrefix = "dlr_dedup:" // dlr_dedup:{channel_id}:{upstream_id}:{stat} = "1"
)

var (
	dedupRdb     *redis.Client
	dedupEnabled atomic.Bool
	dedupTTL     time.Duration
	dedupHit     atomic.Uint64 // 识别为重复、跳过发布的次数
	dedupPass    atomic.Uint64 // 放行并成功发布的次数
)

// InitDLRDedup 初始化 Redis 客户端与开关。默认关闭，需 DLR_DEDUP_FILTER=true 开启。
// 独立于 DLR-OWNERSHIP 的 rdb（后者仅在 ownership 开启时初始化），两者可单独启用。
func InitDLRDedup() {
	enabled := strings.EqualFold(strings.TrimSpace(os.Getenv("DLR_DEDUP_FILTER")), "true")
	dedupEnabled.Store(enabled)
	if !enabled {
		log.Printf("[DLR-DEDUP] disabled (set DLR_DEDUP_FILTER=true to enable)")
		return
	}

	// TTL 必须盖住上游重传跨度（实测 ~5min），默认 15min，可经 DLR_DEDUP_TTL_SEC 调整。
	ttlSec := 900
	if v := strings.TrimSpace(os.Getenv("DLR_DEDUP_TTL_SEC")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			ttlSec = n
		}
	}
	dedupTTL = time.Duration(ttlSec) * time.Second

	host := os.Getenv("REDIS_HOST")
	if host == "" {
		host = "redis"
	}
	port := os.Getenv("REDIS_PORT")
	if port == "" {
		port = "6379"
	}
	addr := fmt.Sprintf("%s:%s", host, port)

	dedupRdb = redis.NewClient(&redis.Options{
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
	if err := dedupRdb.Ping(ctx).Err(); err != nil {
		log.Printf("[DLR-DEDUP] Redis unreachable at %s: %v — dedup fail-open until reconnect", addr, err)
		return
	}
	log.Printf("[DLR-DEDUP] enabled, Redis=%s, ttl=%v", addr, dedupTTL)
	go dedupStatsLogger()
}

func dedupKey(channelID int, upstreamID, stat string) string {
	return fmt.Sprintf("%s%d:%s:%s", dedupKeyPrefix, channelID, upstreamID, stat)
}

// IsDuplicateDLR 在发布到 RabbitMQ 之前调用。
//
//	true  → 该 (channel,upstream_id,stat) 近期已成功发布过，本次是上游重传，应跳过发布。
//	false → 首次出现（或 Redis 异常 fail-open），应发布；发布成功后须调用 MarkDLRPublished。
func IsDuplicateDLR(channelID int, upstreamID, stat string) bool {
	if !dedupEnabled.Load() || dedupRdb == nil || upstreamID == "" {
		return false
	}
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	n, err := dedupRdb.Exists(ctx, dedupKey(channelID, upstreamID, stat)).Result()
	if err != nil {
		// fail-open：Redis 异常时不去重，宁可重复也不漏
		return false
	}
	if n > 0 {
		dedupHit.Add(1)
		return true
	}
	return false
}

// MarkDLRPublished 在成功发布到 RabbitMQ 之后调用，写入去重标记。
// 必须「发布成功后」才标记：发布失败则键不存在，上游下次重传会再次放行（天然重试），绝不丢回执。
func MarkDLRPublished(channelID int, upstreamID, stat string) {
	if !dedupEnabled.Load() || dedupRdb == nil || upstreamID == "" {
		return
	}
	dedupPass.Add(1)
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	// 标记失败不致命：下次重传会重复发布一条，由 Python dlr_seen 层兜底，不影响正确性
	_ = dedupRdb.Set(ctx, dedupKey(channelID, upstreamID, stat), "1", dedupTTL).Err()
}

func dedupStatsLogger() {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()
	for range ticker.C {
		hits := dedupHit.Swap(0)
		passes := dedupPass.Swap(0)
		if hits > 0 || passes > 0 {
			total := hits + passes
			var pct float64
			if total > 0 {
				pct = float64(hits) * 100 / float64(total)
			}
			log.Printf("[DLR-DEDUP] last 5min: published=%d, deduped=%d (%.0f%% upstream retransmits filtered)",
				passes, hits, pct)
		}
	}
}
