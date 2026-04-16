package main

import (
    "encoding/json"
    "fmt"
    "log"

    amqp "github.com/rabbitmq/amqp091-go"
    "github.com/google/uuid"
)

var (
    rabbitConn *amqp.Connection
    publishCh  *amqp.Channel
)

func StartConsumer(url string) error {
    var err error
    rabbitConn, err = amqp.Dial(url)
    if err != nil {
        return err
    }
    // We don't defer close here as we want to keep it global for publishing too
    // But we should handle it in a shutdown hook if needed.

    publishCh, err = rabbitConn.Channel()
    if err != nil {
        return err
    }

    ch, err := rabbitConn.Channel()
    if err != nil {
        return err
    }
    defer ch.Close()

    q, err := ch.QueueDeclare(
        "sms_send_smpp", // name
        true,            // durable
        false,           // delete when unused
        false,           // exclusive
        false,           // no-wait
        nil,             // arguments
    )
    if err != nil {
        return err
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
        return err
    }

    log.Printf("RabbitMQ Consumer started. Waiting for messages...")

    for d := range msgs {
        processTask(d)
    }

    return nil
}

// PublishCeleryTask dispatches a task to the Python worker via RabbitMQ
func PublishCeleryTask(queue string, taskName string, args []interface{}) error {
    if publishCh == nil {
        return fmt.Errorf("RabbitMQ publish channel not initialized")
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
