package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	amqp "github.com/rabbitmq/amqp091-go"
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

// parseSMSLogData 将 JSON map 转为 SMSLogData（Celery JSON 数字常为 float64）
func parseSMSLogData(m map[string]interface{}) (SMSLogData, error) {
	var d SMSLogData
	if v, ok := m["log_id"]; ok {
		switch x := v.(type) {
		case float64:
			d.LogID = int64(x)
		case int64:
			d.LogID = x
		case int:
			d.LogID = int64(x)
		default:
			return d, fmt.Errorf("log_id type %T", v)
		}
	} else {
		return d, fmt.Errorf("missing log_id")
	}
	if v, ok := m["message_id"].(string); ok {
		d.MessageID = v
	} else {
		return d, fmt.Errorf("missing message_id")
	}
	if v, ok := m["phone_number"].(string); ok {
		d.PhoneNumber = v
	}
	if v, ok := m["message"].(string); ok {
		d.Message = v
	}
	if v, ok := m["channel_id"]; ok {
		switch x := v.(type) {
		case float64:
			d.ChannelID = int(x)
		case int:
			d.ChannelID = x
		case int64:
			d.ChannelID = int(x)
		}
	}
	if v, ok := m["batch_status"].(string); ok {
		d.BatchStatus = v
	}
	if v, ok := m["record_status"].(string); ok {
		d.RecordStatus = v
	}
	return d, nil
}

const maxPayloadLogBytes = 4096

// logPayloadParseError 无法解析或拒绝投递时的显式日志，便于与 DB pending 对账
func logPayloadParseError(reason string, body []byte) {
	raw := string(body)
	if len(raw) > maxPayloadLogBytes {
		raw = raw[:maxPayloadLogBytes] + fmt.Sprintf("… (truncated, len=%d)", len(body))
	}
	log.Printf("Payload Parse Error, dropping message: %s | raw=%s", reason, raw)
}

// stripCeleryEnvelope 从 Celery / kombu JSON 消息体取出 send_sms_task 的首个位置参数，
// 或识别无信封的裸 SMSLogData 对象（须同时含 log_id 与 message_id）。
// 第二返回值 true 表示 first 可交给 smsPayloadsFromFirstTaskArg。
func stripCeleryEnvelope(body []byte) (first interface{}, ok bool) {
	trimmed := bytes.TrimSpace(body)
	if len(trimmed) == 0 {
		return nil, false
	}

	// ① Celery JSON / kombu 常见体：[位置参数数组, kwargs 对象, 嵌入元数据]，三段数组（v2 风格）
	if trimmed[0] == '[' {
		var top []interface{}
		if err := json.Unmarshal(trimmed, &top); err != nil {
			return nil, false
		}
		if len(top) == 0 {
			return nil, false
		}
		posArgs, isArr := top[0].([]interface{})
		if !isArr || len(posArgs) == 0 {
			return nil, false
		}
		if posArgs[0] == nil {
			return nil, false
		}
		return posArgs[0], true
	}

	// ② JSON 对象：含 "args" 的 Celery v1 信封，或裸负载
	if trimmed[0] == '{' {
		var m map[string]interface{}
		if err := json.Unmarshal(trimmed, &m); err != nil {
			return nil, false
		}
		if argsVal, has := m["args"]; has {
			argsList, isList := argsVal.([]interface{})
			if isList && len(argsList) > 0 && argsList[0] != nil {
				return argsList[0], true
			}
			return nil, false
		}
		_, hasLog := m["log_id"]
		_, hasMid := m["message_id"]
		if hasLog && hasMid {
			return m, true
		}
		return nil, false
	}

	return nil, false
}

// smsPayloadsFromFirstTaskArg 解析 send_sms_task 的首参：单 dict、dict 数组（批量）、或旧版 message_id 字符串。
// 若非毒消息则 poisonReason 为空；否则为简短原因（由上层统一带 raw 打日志）。
func smsPayloadsFromFirstTaskArg(first interface{}) (payloads []SMSLogData, poisonReason string) {
	switch x := first.(type) {
	case string:
		return nil, fmt.Sprintf("legacy message_id-only payload (len=%d)", len(x))
	case map[string]interface{}:
		d, err := parseSMSLogData(x)
		if err != nil {
			return nil, fmt.Sprintf("invalid SMSLogData map: %v", err)
		}
		return []SMSLogData{d}, ""
	case []interface{}:
		var out []SMSLogData
		for i, el := range x {
			mm, ok := el.(map[string]interface{})
			if !ok {
				return nil, fmt.Sprintf("batch args[%d] is not object (type %T)", i, el)
			}
			d, err := parseSMSLogData(mm)
			if err != nil {
				return nil, fmt.Sprintf("batch args[%d]: %v", i, err)
			}
			out = append(out, d)
		}
		return out, ""
	default:
		return nil, fmt.Sprintf("unsupported first task arg type %T", first)
	}
}

// extractSmsPayloads 从 RabbitMQ body 解析 SMSLogData 列表：兼容 kombu 三段数组、Celery 对象信封、裸 JSON 负载。
func extractSmsPayloads(body []byte) (payloads []SMSLogData, nackPoison bool) {
	root, stripped := stripCeleryEnvelope(body)
	if !stripped {
		logPayloadParseError("无法识别 Celery 信封或裸 SMS JSON（需 [args,…] 或 {\"args\":…} 或 {\"log_id\",\"message_id\"}）", body)
		return nil, true
	}
	payloads, reason := smsPayloadsFromFirstTaskArg(root)
	if reason != "" {
		logPayloadParseError(reason, body)
		return nil, true
	}
	return payloads, false
}

// workerProcessDelivery 执行业务逻辑，不向 Rabbit 直接 Ack（由 ack 专用 goroutine 执行）
func workerProcessDelivery(d amqp.Delivery, ackCh chan<- rabbitAckOp) {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("panic in workerProcessDelivery: %v", r)
			ackCh <- rabbitAckOp{d: d, nack: true, requeue: true}
		}
	}()

	payloads, nackPoison := extractSmsPayloads(d.Body)
	if nackPoison {
		ackCh <- rabbitAckOp{d: d, nack: true, requeue: false}
		return
	}
	if len(payloads) == 0 {
		log.Printf("Could not extract smpp payload(s) from task: %s", string(d.Body))
		ackCh <- rabbitAckOp{d: d, ack: true}
		return
	}

	if len(payloads) == 1 {
		log.Printf("Processing SMS Task: %s log_id=%d", payloads[0].MessageID, payloads[0].LogID)
		procErr := processSingleSMSData(payloads[0])
		if procErr != nil {
			log.Printf("Failed to process message %s: %v", payloads[0].MessageID, procErr)
		}
		if procErr != nil {
			ackCh <- rabbitAckOp{d: d, nack: true, requeue: true}
			return
		}
		ackCh <- rabbitAckOp{d: d, ack: true}
		return
	}

	const perDeliveryCap = 4
	sem := make(chan struct{}, perDeliveryCap)
	var wg sync.WaitGroup
	var failMu sync.Mutex
	failedCount := 0
	for _, pl := range payloads {
		wg.Add(1)
		sem <- struct{}{}
		go func(data SMSLogData) {
			defer wg.Done()
			defer func() { <-sem }()
			defer func() {
				if r := recover(); r != nil {
					log.Printf("panic processSingleSMSData %s: %v", data.MessageID, r)
					failMu.Lock()
					failedCount++
					failMu.Unlock()
				}
			}()
			log.Printf("Processing SMS Task: %s", data.MessageID)
			if err := processSingleSMSData(data); err != nil {
				log.Printf("Failed to process message %s: %v", data.MessageID, err)
				failMu.Lock()
				failedCount++
				failMu.Unlock()
			}
		}(pl)
	}
	wg.Wait()
	totalN := len(payloads)
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

	// 结果回写队列：与 Python Celery task_queues 中 sms_result_queue 对齐
	if _, err = pubCh.QueueDeclare("sms_result_queue", true, false, false, false, nil); err != nil {
		_ = pubCh.Close()
		_ = conn.Close()
		rabbitMu.Lock()
		closeRabbitMQLocked()
		rabbitMu.Unlock()
		return fmt.Errorf("declare sms_result_queue: %w", err)
	}

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

func processSingleSMSData(data SMSLogData) error {
	bs := strings.ToLower(strings.TrimSpace(data.BatchStatus))
	rs := strings.TrimSpace(data.RecordStatus)
	if bs == "cancelled" && (rs == "pending" || rs == "queued") {
		log.Printf("跳过 SMPP 提交: 批次已取消 message_id=%s", data.MessageID)
		if err := publishSmsSubmitResult(data.LogID, data.MessageID, "", "failed", "批次已取消"); err != nil {
			log.Printf("WARN: publish cancel result id=%d: %v", data.LogID, err)
		}
		return nil
	}
	if rs == "failed" || rs == "expired" || rs == "delivered" || rs == "sent" {
		log.Printf("跳过 SMPP 提交: 已是终态 message_id=%s status=%s", data.MessageID, rs)
		return nil
	}

	err := manager.SendSMS(data.LogID, data.MessageID, data.PhoneNumber, data.Message, data.ChannelID)
	if err != nil {
		errStr := err.Error()
		if len(errStr) >= 13 && errStr[:13] == "_window_full:" {
			log.Printf("[SMPP-WARN] window full nack+requeue: message_id=%s", data.MessageID)
			return fmt.Errorf("window full, requeue: %s", data.MessageID)
		}
		if len(errStr) >= 12 && errStr[:12] == "_temp_error:" {
			log.Printf("[SMPP-WARN] temp error nack+requeue: message_id=%s err=%s", data.MessageID, errStr)
			return fmt.Errorf("temp error, requeue: %s", data.MessageID)
		}
		if pubErr := publishSmsSubmitResult(data.LogID, data.MessageID, "", "failed", errStr); pubErr != nil {
			log.Printf("WARN: publish failed result id=%d: %v", data.LogID, pubErr)
		}
		return fmt.Errorf("failed to send: %v", err)
	}
	return nil
}
