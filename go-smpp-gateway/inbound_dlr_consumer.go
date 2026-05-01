package main

import (
	"fmt"
	"log"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
)

const inboundDLRQueue = "sms_inbound_dlr"

// RunInboundDLRConsumerForever 消费 sms_inbound_dlr 队列，自动重连
func RunInboundDLRConsumerForever(url string) {
	if url == "" {
		log.Println("[INBOUND-DLR] RABBITMQ_URL 未设置，DLR 消费者未启动")
		return
	}
	const reconnectDelay = 5 * time.Second
	for {
		err := runInboundDLRSession(url)
		log.Printf("[INBOUND-DLR] 会话结束: %v；%v 后重连", err, reconnectDelay)
		time.Sleep(reconnectDelay)
	}
}

func runInboundDLRSession(url string) error {
	conn, err := amqp.Dial(url)
	if err != nil {
		return fmt.Errorf("dial: %w", err)
	}
	defer conn.Close()

	ch, err := conn.Channel()
	if err != nil {
		return fmt.Errorf("channel: %w", err)
	}
	defer ch.Close()

	// 声明队列（与 Python celery_app.py 中声明保持一致：durable、24h TTL）
	_, err = ch.QueueDeclare(
		inboundDLRQueue,
		true,  // durable
		false, // auto-delete
		false, // exclusive
		false, // no-wait
		amqp.Table{"x-message-ttl": int32(86_400_000)},
	)
	if err != nil {
		return fmt.Errorf("queue declare: %w", err)
	}

	if err := ch.Qos(32, 0, false); err != nil {
		return fmt.Errorf("qos: %w", err)
	}

	msgs, err := ch.Consume(inboundDLRQueue, "", false, false, false, false, nil)
	if err != nil {
		return fmt.Errorf("consume: %w", err)
	}
	log.Printf("[INBOUND-DLR] 开始消费 %s", inboundDLRQueue)

	for d := range msgs {
		handleInboundDLRDelivery(d)
	}
	return fmt.Errorf("deliveries closed")
}

func handleInboundDLRDelivery(d amqp.Delivery) {
	first, ok := stripCeleryEnvelope(d.Body)
	if !ok {
		log.Printf("[INBOUND-DLR] 无法解析 Celery envelope，丢弃 (body=%s)", string(d.Body[:min(len(d.Body), 200)]))
		_ = d.Ack(false)
		return
	}
	payload, ok := first.(map[string]interface{})
	if !ok {
		log.Printf("[INBOUND-DLR] 消息体不是 JSON 对象，丢弃")
		_ = d.Ack(false)
		return
	}
	dispatchDLRPayload(payload)
	_ = d.Ack(false)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
