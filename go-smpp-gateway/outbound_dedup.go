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

// 出站 submit 幂等：杜绝同一 message_id 被向上游二次提交（双发）。
//
// [事故根因 1638/1639] Python 巡检的 SMPP pending 重派发（batch_inspector 2.5 节）在
// 结果回写队列(sms_result_queue)积压时误判：消息其实已成功 submit 上游、只是 SubmitSMResp 的
// "sent" 回写堵在队列没落库，DB 仍显示 pending → 重派发把同一条又投了一遍 → 上游双发 + 双付成本。
// consumer.go processSingleSMSData 原有的"查 DB 实时 status"幂等被同一个回写滞后击穿
// （DB 还没变 sent，所以放行）。
//
// 本模块提供一个**不依赖 Python 回写、由网关自己掌握**的权威标记：网关在收到 SubmitSMResp
// ESME_ROK（确认已提交上游）那一刻写 Redis `submit_done:{message_id}`，提交前查它即可拦住重复。
//
// 安全性关键（避免误伤合法重发、避免丢消息）：
//   1. 只在 ROK（提交成功）时标记。88 限流重投 / 其它失败都不标记 → 合法重投天然放行，不会被拦丢。
//      这点至关重要：88 重投复用同一 message_id，若被拦就是丢消息。
//   2. Redis 全局存储：一个通道多个 bind（独立 goroutine），原件与重复副本可能落不同 bind/不同
//      消费者进程，只有共享存储能跨进程去重。
//   3. fail-open：Redis 异常一律放行提交，宁可偶发重复也绝不丢消息。
//   4. check 与 mark 之间有极小并发窗口（两副本几乎同时在飞，都没看到标记 → 都提交）。但 redispatch
//      重复副本实测相隔数分钟，标记早已写入，足以拦住；偶发漏拦只是少去重一份，不影响正确性。
//
// TTL 须盖住"原件提交 → 重复副本被消费"的跨度（redispatch 窗口最长约 30min），默认 1h。
// 长 TTL 不会误伤合法重发：标记只代表"已成功提交上游",成功的消息本就不该重发;真正的合法重发
// （88/失败后）不写标记。客户手动重发走新批次新 message_id，亦不受影响。

const (
	outboundDedupKeyPrefix = "submit_done:" // submit_done:{message_id} = "1"
)

var (
	outboundRdb      *redis.Client
	outboundEnabled  atomic.Bool
	outboundTTL      time.Duration
	outboundDedupHit atomic.Uint64 // 命中标记、跳过二次提交的次数（=拦下的双发）
)

// InitOutboundDedup 初始化。默认开启（本系统目标是彻底杜绝双发）；
// 设 OUTBOUND_DEDUP_FILTER=false 可关闭。
func InitOutboundDedup() {
	disabled := strings.EqualFold(strings.TrimSpace(os.Getenv("OUTBOUND_DEDUP_FILTER")), "false")
	if disabled {
		outboundEnabled.Store(false)
		log.Printf("[OUTBOUND-DEDUP] disabled (OUTBOUND_DEDUP_FILTER=false)")
		return
	}
	outboundEnabled.Store(true)

	ttlSec := 3600
	if v := strings.TrimSpace(os.Getenv("OUTBOUND_DEDUP_TTL_SEC")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			ttlSec = n
		}
	}
	outboundTTL = time.Duration(ttlSec) * time.Second

	host := os.Getenv("REDIS_HOST")
	if host == "" {
		host = "redis"
	}
	port := os.Getenv("REDIS_PORT")
	if port == "" {
		port = "6379"
	}
	addr := fmt.Sprintf("%s:%s", host, port)

	outboundRdb = redis.NewClient(&redis.Options{
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
	if err := outboundRdb.Ping(ctx).Err(); err != nil {
		log.Printf("[OUTBOUND-DEDUP] Redis unreachable at %s: %v — fail-open（放行提交）until reconnect", addr, err)
		return
	}
	log.Printf("[OUTBOUND-DEDUP] enabled, Redis=%s, ttl=%v", addr, outboundTTL)
	go outboundDedupStatsLogger()
}

func outboundDedupKey(messageID string) string {
	return outboundDedupKeyPrefix + messageID
}

// IsAlreadySubmitted 在向上游 submit 之前调用。
//
//	true  → 该 message_id 近期已成功提交上游（收到过 ROK），本次是重复（如 redispatch/重启重复消费），
//	        应跳过提交，杜绝双发。
//	false → 未提交过（或 Redis 异常 fail-open），应正常提交。
func IsAlreadySubmitted(messageID string) bool {
	if !outboundEnabled.Load() || outboundRdb == nil || messageID == "" {
		return false
	}
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	n, err := outboundRdb.Exists(ctx, outboundDedupKey(messageID)).Result()
	if err != nil {
		return false // fail-open：宁可重复也不丢
	}
	if n > 0 {
		outboundDedupHit.Add(1)
		return true
	}
	return false
}

// MarkSubmitted 在网关收到 SubmitSMResp ESME_ROK（已成功提交上游）后调用，写入幂等标记。
// 只在 ROK 时调用：88 限流 / 其它失败均不调用，以放行合法重投，绝不拦丢。
func MarkSubmitted(messageID string) {
	if !outboundEnabled.Load() || outboundRdb == nil || messageID == "" {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	// 标记失败不致命：万一下次重复消费,会落到 processSingleSMSData 的 DB 实时 status 兜底闸。
	_ = outboundRdb.Set(ctx, outboundDedupKey(messageID), "1", outboundTTL).Err()
}

func outboundDedupStatsLogger() {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()
	for range ticker.C {
		hits := outboundDedupHit.Swap(0)
		if hits > 0 {
			log.Printf("[OUTBOUND-DEDUP] last 5min: 拦下重复提交(双发) %d 条", hits)
		}
	}
}
