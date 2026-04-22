package main

import (
    "time"
)

// ChannelConfig represents the SMPP channel configuration from the database
type ChannelConfig struct {
    ID                     int       `db:"id"`
    ChannelCode            string    `db:"channel_code"`
    Protocol               string    `db:"protocol"` // Should be SMPP
    Host                   string    `db:"host"`
    Port                   int       `db:"port"`
    Username               string    `db:"username"`
    Password               string    `db:"password"`
    BindMode               string    `db:"smpp_bind_mode"`
    SystemType             string    `db:"smpp_system_type"`
    InterfaceVersion       int       `db:"smpp_interface_version"`
    DLRHoldSeconds         *int      `db:"smpp_dlr_socket_hold_seconds"`
    DefaultSenderID        string    `db:"default_sender_id"`
    MaxTPS                 int       `db:"max_tps"`
    Concurrency            int       `db:"concurrency"`
    // 与 Python channels.config_json 一致，含 strip_leading_plus 等
    ConfigJSON             string    `db:"config_json"`
}

// SMSLog represents the sms_logs record
type SMSLog struct {
    ID                int64     `db:"id"`
    MessageID         string    `db:"message_id"`
    PhoneNumber       string    `db:"phone_number"`
    Message           string    `db:"message"`
    ChannelID         int       `db:"channel_id"`
    SubmitTime        time.Time `db:"submit_time"`
    Status            string    `db:"status"`       // pending/queued/sent/...
    BatchStatus       string    `db:"batch_status"` // 关联 sms_batches.status；无批次为空串
}

// CeleryTask represents the JSON message received from RabbitMQ (Celery format)
type CeleryTask struct {
    Args []interface{} `json:"args"`
    ID   string        `json:"id"`
    Task string        `json:"task"`
}

// SMSLogData 为 Python 投递至 sms_send_smpp 的单条短信负载；发送路径仅依赖此结构，不查库。
type SMSLogData struct {
    LogID         int64  `json:"log_id"`
    MessageID     string `json:"message_id"`
    PhoneNumber   string `json:"phone_number"`
    Message       string `json:"message"`
    ChannelID     int    `json:"channel_id"`
    BatchStatus   string `json:"batch_status"`
    RecordStatus  string `json:"record_status"`
}
