package main

import (
    "encoding/json"
    "fmt"
    "log"
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

    log.Printf("RabbitMQ Consumer started. Waiting for messages...")

    for d := range msgs {
        processTask(d)
    }

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

func processTask(d amqp.Delivery) {
    var messageIDs []string
    var raw []interface{}

    if err := json.Unmarshal(d.Body, &raw); err == nil {
        // Array format: [args, kwargs, options]
        if len(raw) > 0 {
            args, ok := raw[0].([]interface{})
            if ok && len(args) > 0 {
                // Check if first arg is a slice (batch) or string (single)
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
        // Object format: {"args": [...], "task": "..."}
        var task CeleryTask
        if err := json.Unmarshal(d.Body, &task); err != nil {
            log.Printf("Failed to unmarshal Celery task: %v | Raw: %s", err, string(d.Body))
            d.Nack(false, false)
            return
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

    if len(messageIDs) == 0 {
        log.Printf("Could not extract message_id(s) from task: %s", string(d.Body))
        d.Ack(false)
        return
    }

    for _, msgID := range messageIDs {
        log.Printf("Processing SMS Task: %s", msgID)
        err := processSingleSMS(msgID)
        if err != nil {
            log.Printf("Failed to process message %s: %v", msgID, err)
        }
    }
    d.Ack(false)
}

func processSingleSMS(messageID string) error {
    logData, err := GetSMSLogByMessageID(messageID)
    if err != nil {
        return fmt.Errorf("failed to get log: %v", err)
    }

    // manager.SendSMS now updates the database asynchronously when SubmitSMResp is received.
    // However, if the initial socket write fails, it returns an error here.
    err = manager.SendSMS(logData.ID, logData.MessageID, logData.PhoneNumber, logData.Message, logData.ChannelID)
    if err != nil {
        // Update DB with failure since it failed to even queue to the socket
        _ = UpdateSMSLogResult(logData.ID, logData.MessageID, "", "failed", err.Error())
        return fmt.Errorf("failed to send: %v", err)
    }

    // We no longer update the status to "sent" here. 
    // The status stays "pending/queued" until the SubmitSMResp callback updates it to "sent" with the real upstream ID.
    return nil
}
