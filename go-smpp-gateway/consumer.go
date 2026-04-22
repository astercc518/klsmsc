package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strconv"
	"sync"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/google/uuid"
)

var (
	rabbitConn *amqp.Connection
	publishCh  *amqp.Channel
	rabbitMu   sync.Mutex
)

// closeRabbitMQLocked 关闭发布通道与连接（须在持有 rabbitMu 时调用）
func closeRabbitMQLocked() {
	if publishCh != nil {
		_ = publishCh.Close()
		publishCh = nil
	}
	if rabbitConn != nil {
		_ = rabbitConn.Close()
		rabbitConn = nil
	}
}

func envInt(key string, def int) int {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil || n < 1 {
		return def
	}
	return n
}

// rabbitAckOp 仅由单 goroutine 对消费 channel 执行 Ack/Nack（channel 非线程安全）
type rabbitAckOp struct {
	d       amqp.Delivery
	ack     bool
	nack    bool
	requeue bool
}

// extractMessageIDs 从 Celery 消息体解析 message_id 列表；若需丢弃毒消息返回 nackPoison=true
func extractMessageIDs(body []byte) (messageIDs []string, nackPoison bool) {
	var raw []interface{}
	if err := json.Unmarshal(body, &raw); err == nil {
		if len(raw) > 0 {
			args, ok := raw[0].([]interface{})
			if ok && len(args) > 0 {
				if firstArgList, ok := args[0].([]interface{}); ok {
					for _, id := range firstArgList {
						if idStr, ok := id.(string); ok {
							messageIDs = append(messageIDs, idStr)
						}
					}
				} else if idStr, ok := args[0].(string); ok {
					messageIDs = append(messageIDs, idStr)
				}
			}
		}
	} else {
		var task CeleryTask
		if err := json.Unmarshal(body, &task); err != nil {
			log.Printf("Failed to unmarshal Celery task: %v | Raw: %s", err, string(body))
			return nil, true
		}
		if len(task.Args) > 0 {
			if firstArgList, ok := task.Args[0].([]interface{}); ok {
				for _, id := range firstArgList {
					if idStr, ok := id.(string); ok {
						messageIDs = append(messageIDs, idStr)
					}
				}
			} else if idStr, ok := task.Args[0].(string); ok {
				messageIDs = append(messageIDs, idStr)
			}
		}
	}
	return messageIDs, false
}

// workerProcessDelivery 执行业务逻辑，不向 Rabbit 直接 Ack（由 ack 专用 goroutine 执行）
func workerProcessDelivery(d amqp.Delivery, ackCh chan<- rabbitAckOp) {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("panic in workerProcessDelivery: %v", r)
			ackCh <- rabbitAckOp{d: d, nack: true, requeue: true}
		}
	}()

	messageIDs, nackPoison := extractMessageIDs(d.Body)
	if nackPoison {
		ackCh <- rabbitAckOp{d: d, nack: true, requeue: false}
		return
	}
	if len(messageIDs) == 0 {
		log.Printf("Could not extract message_id(s) from task: %s", string(d.Body))
		ackCh <- rabbitAckOp{d: d, ack: true}
		return
	}

	if len(messageIDs) == 1 {
		log.Printf("Processing SMS Task: %s", messageIDs[0])
		procErr := processSingleSMS(messageIDs[0])
		if procErr != nil {
			log.Printf("Failed to process message %s: %v", messageIDs[0], procErr)
		}
		// 处理失败时必须 Nack 并 requeue，否则会出现「队列已空但 sms_logs 未更新」的假丢失
		if procErr != nil {
			ackCh <- rabbitAckOp{d: d, nack: true, requeue: true}
			return
		}
		ackCh <- rabbitAckOp{d: d, ack: true}
		return
	}

	// 同一 delivery 内多条：限制并发，避免单包过大时 goroutine 爆炸
	const perDeliveryCap = 16
	sem := make(chan struct{}, perDeliveryCap)
	var wg sync.WaitGroup
	var failMu sync.Mutex
	failedCount := 0
	for _, msgID := range messageIDs {
		wg.Add(1)
		sem <- struct{}{}
		go func(mid string) {
			defer wg.Done()
			defer func() { <-sem }()
			defer func() {
				if r := recover(); r != nil {
					log.Printf("panic processSingleSMS %s: %v", mid, r)
					failMu.Lock()
					failedCount++
					failMu.Unlock()
				}
			}()
			log.Printf("Processing SMS Task: %s", mid)
			if err := processSingleSMS(mid); err != nil {
				log.Printf("Failed to process message %s: %v", mid, err)
				failMu.Lock()
				failedCount++
				failMu.Unlock()
			}
		}(msgID)
	}
	wg.Wait()
	totalN := len(messageIDs)
	// 全部失败：整包 Nack 重入队；部分失败仍 Ack，避免已成功 Submit 的条因整包重投而重复下发
	if failedCount == totalN && totalN > 0 {
		ackCh <- rabbitAckOp{d: d, nack: true, requeue: true}
		return
	}
	if failedCount > 0 {
		log.Printf("WARN: multi-SMS delivery partial failures %d/%d; ack to avoid duplicate Submit", failedCount, totalN)
	}
	ackCh <- rabbitAckOp{d: d, ack: true}
}

// startSingleConsumerSession 建立连接、注册 sms_send_smpp 消费者并阻塞直到连接/通道结束
func startSingleConsumerSession(url string) error {
	conn, err := amqp.Dial(url)
	if err != nil {
		return fmt.Errorf("dial: %w", err)
	}
	pubCh, err := conn.Channel()
	if err != nil {
		_ = conn.Close()
		return fmt.Errorf("publish channel: %w", err)
	}

	rabbitMu.Lock()
	closeRabbitMQLocked()
	rabbitConn = conn
	publishCh = pubCh
	rabbitMu.Unlock()

	ch, err := conn.Channel()
	if err != nil {
		rabbitMu.Lock()
		closeRabbitMQLocked()
		rabbitMu.Unlock()
		return fmt.Errorf("consume channel: %w", err)
	}

	q, err := ch.QueueDeclare(
		"sms_send_smpp", // name
		true,            // durable
		false,           // delete when unused
		false,           // exclusive
		false,           // no-wait
		nil,             // arguments
	)
	if err != nil {
		_ = ch.Close()
		rabbitMu.Lock()
		closeRabbitMQLocked()
		rabbitMu.Unlock()
		return fmt.Errorf("queue declare: %w", err)
	}

	prefetch := envInt("SMPP_GATEWAY_PREFETCH", 32)
	if err := ch.Qos(prefetch, 0, false); err != nil {
		_ = ch.Close()
		rabbitMu.Lock()
		closeRabbitMQLocked()
		rabbitMu.Unlock()
		return fmt.Errorf("qos: %w", err)
	}

	msgs, err := ch.Consume(
		q.Name, // queue
		"",     // consumer
		false,  // auto-ack (set to false for manual ack)
		false,  // exclusive
		false,  // no-local
		false,  // no-wait
		nil,    // args
	)
	if err != nil {
		_ = ch.Close()
		rabbitMu.Lock()
		closeRabbitMQLocked()
		rabbitMu.Unlock()
		return fmt.Errorf("consume: %w", err)
	}

	workers := envInt("SMPP_GATEWAY_WORKERS", 32)
	log.Printf("RabbitMQ Consumer started (workers=%d prefetch=%d). Waiting for messages...", workers, prefetch)

	jobs := make(chan amqp.Delivery, prefetch*2)
	ackCh := make(chan rabbitAckOp, prefetch*4)

	var ackWg sync.WaitGroup
	ackWg.Add(1)
	go func() {
		defer ackWg.Done()
		for op := range ackCh {
			if op.ack {
				if err := op.d.Ack(false); err != nil {
					log.Printf("RabbitMQ Ack failed: %v", err)
				}
			} else if op.nack {
				if err := op.d.Nack(false, op.requeue); err != nil {
					log.Printf("RabbitMQ Nack failed: %v", err)
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

	for d := range msgs {
		jobs <- d
	}
	close(jobs)
	wg.Wait()
	close(ackCh)
	ackWg.Wait()

	_ = ch.Close()
	rabbitMu.Lock()
	closeRabbitMQLocked()
	rabbitMu.Unlock()
	return fmt.Errorf("deliveries channel closed")
}

// RunConsumerForever Broker 重启或网络闪断后自动重连，避免 sms_send_smpp 长期无消费者
func RunConsumerForever(url string) {
	const reconnectDelay = 5 * time.Second
	for {
		err := startSingleConsumerSession(url)
		log.Printf("RabbitMQ consumer session ended: %v; reconnecting in %v", err, reconnectDelay)
		time.Sleep(reconnectDelay)
	}
}

// PublishCeleryTask dispatches a task to the Python worker via RabbitMQ
func PublishCeleryTask(queue string, taskName string, args []interface{}) error {
	rabbitMu.Lock()
	defer rabbitMu.Unlock()
	if publishCh == nil {
		return fmt.Errorf("RabbitMQ publish channel not ready (broker reconnecting)")
	}

	taskID := uuid.New().String()
	payload := map[string]interface{}{
		"args":   args,
		"kwargs": map[string]interface{}{},
		"task":   taskName,
		"id":     taskID,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	err = publishCh.Publish(
		"sms_dlr", // exchange
		"sms_dlr", // routing key
		false,     // mandatory
		false,     // immediate
		amqp.Publishing{
			ContentType:  "application/json",
			Body:         body,
			DeliveryMode: amqp.Persistent,
		},
	)
	return err
}

func processSingleSMS(messageID string) error {
	logData, err := GetSMSLogByMessageID(messageID)
	if err != nil {
		return fmt.Errorf("failed to get log: %v", err)
	}

	// 批次已取消且仍为待发：不再提交到 SMPP（与 Python worker 侧逻辑一致）
	if logData.BatchStatus == "cancelled" && (logData.Status == "pending" || logData.Status == "queued") {
		log.Printf("跳过 SMPP 提交: 批次已取消 message_id=%s status=%s", messageID, logData.Status)
		if err := MarkSMSLogBatchCancelled(logData.ID); err != nil {
			log.Printf("WARN: 批次取消落库失败 id=%d: %v", logData.ID, err)
		}
		return nil
	}
	// 终态或已提交上游：避免重复 Submit
	if logData.Status == "failed" || logData.Status == "expired" || logData.Status == "delivered" ||
		logData.Status == "sent" {
		log.Printf("跳过 SMPP 提交: 已是终态或已发送 message_id=%s status=%s", messageID, logData.Status)
		return nil
	}

	// 必须在 SendSMS 之前将 pending 标为 queued：若先 Send 且 SubmitSMResp 极快把状态写成 sent，
	// 再执行 MarkQueued 会把终态覆盖回 queued，造成卡死。
	if logData.Status == "pending" {
		if err := MarkSMSLogQueuedAfterSmppHandoff(logData.ID); err != nil {
			log.Printf("WARN: MarkSMSLogQueuedAfterSmppHandoff id=%d: %v", logData.ID, err)
		}
	}

	// manager.SendSMS 在收到 SubmitSMResp 时异步更新库（如 sent）；此处仅处理 socket 首包失败等同步错误。
	err = manager.SendSMS(logData.ID, logData.MessageID, logData.PhoneNumber, logData.Message, logData.ChannelID)
	if err != nil {
		errStr := err.Error()
		if len(errStr) >= 13 && errStr[:13] == "_window_full:" {
			// in-flight 窗口满导致超时：消息保持当前 DB 状态，nack+requeue 等待 session 重建后重试
			log.Printf("[SMPP-WARN] window full nack+requeue: message_id=%s", logData.MessageID)
			return fmt.Errorf("window full, requeue: %s", logData.MessageID)
		}
		if len(errStr) >= 12 && errStr[:12] == "_temp_error:" {
			// 临时错误（session 正在关闭/重建）：不写 DB failed，nack+requeue 等待 session 恢复
			log.Printf("[SMPP-WARN] temp error nack+requeue: message_id=%s err=%s", logData.MessageID, errStr)
			return fmt.Errorf("temp error, requeue: %s", logData.MessageID)
		}
		// 其它永久性发送错误：写 failed
		_ = UpdateSMSLogResult(logData.ID, logData.MessageID, "", "failed", errStr)
		return fmt.Errorf("failed to send: %v", err)
	}

	// SubmitSMResp 回调再将状态更新为 sent 并写入上游 message_id。
	return nil
}
