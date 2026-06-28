package main

// 每通道独立队列消费者(per-channel queue consumer)。
//
// 背景：所有通道原本共用单一 sms_send_smpp 队列 + 单消费者 FIFO，一个被上游限流(88)的慢
// 通道占住队头，后面的通道全部饿死(head-of-line blocking)。本文件为【每个 active 通道】
// 起一条独立队列 sms_send_smpp.{channel_id} + 独立 consumer/prefetch/worker 池，使一个慢
// 通道只堆自己的队列、不再拖累其它通道，实现通道间真正并行。
//
// 设计要点：
//   - 独立 AMQP 连接(与 legacy 消费者/发布连接解耦)，自带重连；连接断开后重置并重建全部
//     通道消费者。
//   - 通道集合来自 GetChannelConfigs()(active SMPP 通道)，周期 sync：新增通道起消费者、
//     下线通道停消费者；某通道 consume 异常退出会在下个 sync 周期自动重建。
//   - 业务处理完全复用 workerProcessDelivery / rabbitAckOp，跳过取消批次、限流重投、结果
//     回写逻辑一律不变。
//   - 默认关闭(env SMPP_PER_CHANNEL_QUEUES=1 才启用)。关闭时本文件不起任何 goroutine，
//     行为与改造前完全一致；legacy sms_send_smpp 消费者始终运行，负责存量排空与兜底。
//
// 灰度顺序：先在网关容器设 SMPP_PER_CHANNEL_QUEUES=1(供应消费者就绪)，再在 api/worker
// 容器设同名 env(生产端开始投递每通道队列)。回滚反向操作即可，老队列两端都在消费，零丢消息。

import (
	"context"
	"fmt"
	"log"
	"os"
	"strings"
	"sync"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
)

const perChannelQueuePrefix = "sms_send_smpp."

// perChannelEnabled 网关侧总开关：启用每通道队列消费 + 限流重投按通道回投。
func perChannelEnabled() bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv("SMPP_PER_CHANNEL_QUEUES")))
	return v == "1" || v == "true" || v == "yes" || v == "on"
}

// perChannelQueueName 通道队列名(默认交换机按队列名路由，无需显式 binding)。
func perChannelQueueName(channelID int) string {
	return fmt.Sprintf("%s%d", perChannelQueuePrefix, channelID)
}

// perChannelPrefetch / perChannelWorkers：按通道并发能力定 QoS/worker，慢通道也只占自己的额度。
func perChannelPrefetch(cfg ChannelConfig) int {
	if cfg.Concurrency > 0 {
		return cfg.Concurrency * 2
	}
	return envInt("SMPP_PCQ_PREFETCH", 16)
}

func perChannelWorkers(cfg ChannelConfig) int {
	if cfg.Concurrency > 0 {
		return cfg.Concurrency
	}
	return envInt("SMPP_PCQ_WORKERS", 8)
}

type pcSupervisor struct {
	url     string
	mu      sync.Mutex
	conn    *amqp.Connection
	running map[int]context.CancelFunc // channelID -> 该通道消费者 cancel
}

var perChannel *pcSupervisor

// StartPerChannelSupervisor 启用时启动每通道消费者监管循环；未启用则直接返回。
func StartPerChannelSupervisor(ctx context.Context, url string) {
	if !perChannelEnabled() {
		log.Printf("[PCQ] per-channel queues disabled (SMPP_PER_CHANNEL_QUEUES not set); legacy single queue only")
		return
	}
	perChannel = &pcSupervisor{url: url, running: map[int]context.CancelFunc{}}
	go perChannel.loop(ctx)
	log.Printf("[PCQ] per-channel queue supervisor enabled")
}

func (s *pcSupervisor) loop(ctx context.Context) {
	syncEvery := time.Duration(envInt("SMPP_PCQ_SYNC_SEC", 60)) * time.Second
	for {
		if err := s.ensureConn(); err != nil {
			log.Printf("[PCQ] connect failed: %v; retry in 5s", err)
			select {
			case <-ctx.Done():
				return
			case <-time.After(5 * time.Second):
				continue
			}
		}
		s.syncOnce(ctx)
		select {
		case <-ctx.Done():
			s.stopAll()
			return
		case <-time.After(syncEvery):
		}
	}
}

// ensureConn 保证有可用连接；连接已断则重连并清空 running(旧连接上的消费者已随之退出)。
func (s *pcSupervisor) ensureConn() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.conn != nil && !s.conn.IsClosed() {
		return nil
	}
	conn, err := amqp.Dial(s.url)
	if err != nil {
		return err
	}
	s.conn = conn
	s.running = map[int]context.CancelFunc{} // 旧连接上的 per-channel 消费者已死，重建
	closeCh := make(chan *amqp.Error, 1)
	conn.NotifyClose(closeCh)
	go func() {
		if e := <-closeCh; e != nil {
			log.Printf("[PCQ] connection closed: %v (will reconnect on next sync)", e)
		}
	}()
	log.Printf("[PCQ] AMQP connection established")
	return nil
}

// syncOnce 对齐「活跃通道集合」与「正在运行的消费者集合」。
func (s *pcSupervisor) syncOnce(ctx context.Context) {
	cfgs, err := GetChannelConfigs()
	if err != nil {
		log.Printf("[PCQ] load channels failed: %v", err)
		return
	}
	want := make(map[int]ChannelConfig, len(cfgs))
	for _, c := range cfgs {
		if c.ID > 0 {
			want[c.ID] = c
		}
	}

	s.mu.Lock()
	conn := s.conn
	if conn == nil || conn.IsClosed() {
		s.mu.Unlock()
		return
	}
	// 新增通道：起消费者
	for id, cfg := range want {
		if _, ok := s.running[id]; !ok {
			cctx, cancel := context.WithCancel(ctx)
			s.running[id] = cancel
			go s.runChannel(cctx, conn, cfg)
		}
	}
	// 下线通道：停消费者
	for id, cancel := range s.running {
		if _, ok := want[id]; !ok {
			cancel()
			delete(s.running, id)
			log.Printf("[PCQ] channel %d removed; consumer cancelled", id)
		}
	}
	s.mu.Unlock()
}

func (s *pcSupervisor) stopAll() {
	s.mu.Lock()
	for id, cancel := range s.running {
		cancel()
		delete(s.running, id)
	}
	s.mu.Unlock()
}

// drop 在某通道消费者退出时从 running 移除，使下个 sync 周期可自动重建。
func (s *pcSupervisor) drop(channelID int) {
	s.mu.Lock()
	delete(s.running, channelID)
	s.mu.Unlock()
}

// runChannel 单个通道队列的消费会话：声明 durable 队列 + 独立 QoS + worker 池，复用
// workerProcessDelivery。会话因 ctx 取消、通道关闭或连接断开而退出，退出后自动 drop。
func (s *pcSupervisor) runChannel(ctx context.Context, conn *amqp.Connection, cfg ChannelConfig) {
	defer s.drop(cfg.ID)

	qname := perChannelQueueName(cfg.ID)
	ch, err := conn.Channel()
	if err != nil {
		log.Printf("[PCQ] %s open channel failed: %v", qname, err)
		return
	}
	defer ch.Close()

	// durable 队列，默认交换机按名路由(生产端用 exchange="" routing_key=qname 投递)。
	if _, err := ch.QueueDeclare(qname, true, false, false, false, nil); err != nil {
		log.Printf("[PCQ] %s declare failed: %v", qname, err)
		return
	}
	prefetch := perChannelPrefetch(cfg)
	if err := ch.Qos(prefetch, 0, false); err != nil {
		log.Printf("[PCQ] %s qos failed: %v", qname, err)
		return
	}
	tag := fmt.Sprintf("pcq-%d", cfg.ID)
	msgs, err := ch.Consume(qname, tag, false, false, false, false, nil)
	if err != nil {
		log.Printf("[PCQ] %s consume failed: %v", qname, err)
		return
	}
	workers := perChannelWorkers(cfg)
	log.Printf("[PCQ] started %s (channel_code=%s prefetch=%d workers=%d)", qname, cfg.ChannelCode, prefetch, workers)

	jobs := make(chan amqp.Delivery, prefetch*2)
	ackCh := make(chan rabbitAckOp, prefetch*4)

	var ackWg sync.WaitGroup
	ackWg.Add(1)
	go func() {
		defer ackWg.Done()
		for op := range ackCh {
			if op.ack {
				if err := op.d.Ack(false); err != nil {
					log.Printf("[PCQ] %s ack failed: %v", qname, err)
				}
			} else if op.nack {
				if err := op.d.Nack(false, op.requeue); err != nil {
					log.Printf("[PCQ] %s nack failed: %v", qname, err)
				}
			}
		}
	}()

	var wg sync.WaitGroup
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for d := range jobs {
				workerProcessDelivery(d, ackCh)
			}
		}()
	}

	// ctx 取消(通道下线/关停)：Cancel 消费者，AMQP 关闭 msgs，下面 range 自然退出。
	go func() {
		<-ctx.Done()
		_ = ch.Cancel(tag, false)
	}()

	for d := range msgs {
		jobs <- d
	}
	close(jobs)
	wg.Wait()
	close(ackCh)
	ackWg.Wait()
	log.Printf("[PCQ] stopped %s", qname)
}
