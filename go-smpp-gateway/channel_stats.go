package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"sync"
	"sync/atomic"
	"time"

	"github.com/redis/go-redis/v9"
)

// 出站每通道每日计数器，用于和上游"提交量"对账。
//
// 背景：一条客户消息在 sms_logs 永远只有一行，但向上游可能 submit 多次
// (88 限流重投、长信分段)。按提交计费时 submit 数 > 客户消息数 = 多计的成本。
// 此前网关重启即丢内存计数和 stdout 日志，6/27 那种"上游报数对不上又查不了"就无解。
// 故把计数每 60s flush 到 Redis 按【China 日期】HASH 累加(键 smpp:stats:{cid}:{YYYYMMDD})，
// 跨重启可查、可直接和上游按日对账。
//
// 字段语义：
//   submit      = 实际写到上游的 submit_sm PDU 数(含重投、含长信每段) —— 对账上游"提交量"看这个
//   rok         = SubmitSMResp status=0 接受成功
//   throttle88  = SubmitSMResp status=88(ESME_RTHROTTLED) 次数
//   retry       = 88 触发的重投成功(回投 sms_send_smpp)次数 —— submit 被放大的根源
//   retry_fail  = 88 重投失败/达上限落 failed 次数
//   other_fail  = 其它非零状态(如 TS 的 status=1=模板拒收)落 failed 次数
type channelStats struct {
	submit      atomic.Uint64
	rok         atomic.Uint64
	throttled88 atomic.Uint64
	retry       atomic.Uint64
	retryFail   atomic.Uint64
	otherFail   atomic.Uint64
}

var (
	statsRegMu sync.RWMutex
	statsReg   = make(map[int]*channelStats)
	statsRDB   *redis.Client
	statsTTL   = 14 * 24 * time.Hour
)

// statsFor 取(或惰性建)某通道的计数器。热路径只走 RLock 快路径。
func statsFor(cid int) *channelStats {
	statsRegMu.RLock()
	cs := statsReg[cid]
	statsRegMu.RUnlock()
	if cs != nil {
		return cs
	}
	statsRegMu.Lock()
	defer statsRegMu.Unlock()
	if cs = statsReg[cid]; cs == nil {
		cs = &channelStats{}
		statsReg[cid] = cs
	}
	return cs
}

// 埋点(热路径，无锁原子自增)
func statSubmit(cid int)    { statsFor(cid).submit.Add(1) }
func statROK(cid int)       { statsFor(cid).rok.Add(1) }
func statThrottled(cid int) { statsFor(cid).throttled88.Add(1) }
func statRetry(cid int)     { statsFor(cid).retry.Add(1) }
func statRetryFail(cid int) { statsFor(cid).retryFail.Add(1) }
func statOtherFail(cid int) { statsFor(cid).otherFail.Add(1) }

// InitChannelStats 初始化独立 Redis 客户端并启动 flush goroutine。
// 与 DLR_OWNERSHIP_FILTER 无关——统计始终开启。Redis 不可达则 fail-open(仅打日志)。
func InitChannelStats() {
	host := os.Getenv("REDIS_HOST")
	if host == "" {
		host = "redis"
	}
	port := os.Getenv("REDIS_PORT")
	if port == "" {
		port = "6379"
	}
	addr := fmt.Sprintf("%s:%s", host, port)
	rdb := redis.NewClient(&redis.Options{
		Addr:         addr,
		Password:     os.Getenv("REDIS_PASSWORD"),
		DB:           0,
		DialTimeout:  3 * time.Second,
		ReadTimeout:  1 * time.Second,
		WriteTimeout: 1 * time.Second,
		PoolSize:     10,
	})
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		log.Printf("[SMPP-STATS] Redis unreachable at %s: %v — 计数仅打日志，不落 Redis", addr, err)
		statsRDB = nil
	} else {
		statsRDB = rdb
		log.Printf("[SMPP-STATS] enabled, Redis=%s, ttl=%v", addr, statsTTL)
	}
	go statsFlushLoop()
}

func statsFlushLoop() {
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()
	tick := 0
	for range ticker.C {
		tick++
		flushChannelStats(tick%5 == 0) // 每 5 分钟(第 5 次)打一行汇总日志
	}
}

// flushChannelStats 把各通道增量 Swap 出来累加进 Redis 当日 HASH，并可选打日志。
// Swap 后若 Redis 写失败该增量丢失(best-effort 观测，不影响发送)。
func flushChannelStats(logIt bool) {
	statsRegMu.RLock()
	regCopy := make(map[int]*channelStats, len(statsReg))
	for id, cs := range statsReg {
		regCopy[id] = cs
	}
	statsRegMu.RUnlock()

	date := time.Now().Format("20060102")
	for id, cs := range regCopy {
		submit := cs.submit.Swap(0)
		rok := cs.rok.Swap(0)
		thr := cs.throttled88.Swap(0)
		retry := cs.retry.Swap(0)
		retryFail := cs.retryFail.Swap(0)
		otherFail := cs.otherFail.Swap(0)
		if submit == 0 && rok == 0 && thr == 0 && retry == 0 && retryFail == 0 && otherFail == 0 {
			continue
		}
		if statsRDB != nil {
			persistStat(id, date, submit, rok, thr, retry, retryFail, otherFail)
		}
		if logIt {
			log.Printf("[SMPP-STATS] channel=%d date=%s submit=%d rok=%d throttle88=%d retry=%d retry_fail=%d other_fail=%d",
				id, date, submit, rok, thr, retry, retryFail, otherFail)
		}
	}
}

func persistStat(cid int, date string, submit, rok, thr, retry, retryFail, otherFail uint64) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	key := fmt.Sprintf("smpp:stats:%d:%s", cid, date)
	pipe := statsRDB.Pipeline()
	if submit > 0 {
		pipe.HIncrBy(ctx, key, "submit", int64(submit))
	}
	if rok > 0 {
		pipe.HIncrBy(ctx, key, "rok", int64(rok))
	}
	if thr > 0 {
		pipe.HIncrBy(ctx, key, "throttle88", int64(thr))
	}
	if retry > 0 {
		pipe.HIncrBy(ctx, key, "retry", int64(retry))
	}
	if retryFail > 0 {
		pipe.HIncrBy(ctx, key, "retry_fail", int64(retryFail))
	}
	if otherFail > 0 {
		pipe.HIncrBy(ctx, key, "other_fail", int64(otherFail))
	}
	pipe.Expire(ctx, key, statsTTL) // 滑动续期 14 天
	if _, err := pipe.Exec(ctx); err != nil {
		log.Printf("[SMPP-STATS] persist channel=%d failed: %v", cid, err)
	}
}
