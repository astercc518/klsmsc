package main

import (
	"encoding/json"
	"fmt"

	"github.com/google/uuid"
	amqp "github.com/rabbitmq/amqp091-go"
)

// publishSmsSubmitResult 将 SubmitSM 结果投递到 Python Celery 队列，由 process_sms_result_task 批量写库。
// 发送路径禁止直连 MySQL。
func publishSmsSubmitResult(logID int64, messageID, upstreamMessageID, status, errMsg string) error {
	item := map[string]interface{}{
		"log_id":                logID,
		"message_id":            messageID,
		"upstream_message_id": upstreamMessageID,
		"status":                status,
		"error":                 errMsg,
	}
	return publishCeleryTaskToQueue("sms_result_queue", "sms_result_queue", "process_sms_result_task", []interface{}{item})
}

// publishCeleryTaskToQueue 向指定 exchange/routing_key 发布 Celery JSON 任务体。
func publishCeleryTaskToQueue(exchange, routingKey, taskName string, args []interface{}) error {
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
	return publishCh.Publish(
		exchange,
		routingKey,
		false,
		false,
		amqp.Publishing{
			ContentType:  "application/json",
			Body:         body,
			DeliveryMode: amqp.Persistent,
		},
	)
}
