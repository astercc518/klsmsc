package main

import (
    "fmt"
    "log"
    "os"

    _ "github.com/go-sql-driver/mysql"
    "github.com/jmoiron/sqlx"
)

var db *sqlx.DB

// InitDB initializes the MySQL connection
func InitDB() {
    dbUser := os.Getenv("DATABASE_USER")
    dbPass := os.Getenv("DATABASE_PASSWORD")
    dbHost := os.Getenv("DATABASE_HOST")
    dbPort := os.Getenv("DATABASE_PORT")
    dbName := os.Getenv("DATABASE_NAME")

    // Default connection string (pointing to ProxySQL)
    dsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?parseTime=true", 
        dbUser, dbPass, dbHost, dbPort, dbName)

    var err error
    db, err = sqlx.Connect("mysql", dsn)
    if err != nil {
        log.Fatalf("Failed to connect to database: %v", err)
    }
    log.Println("Database connection established.")
}

// GetChannelConfigs loads all active SMPP channels
func GetChannelConfigs() ([]ChannelConfig, error) {
    var configs []ChannelConfig
    query := "SELECT id, channel_code, protocol, host, port, username, password, " +
             "smpp_bind_mode, smpp_system_type, smpp_interface_version, " +
             "smpp_dlr_socket_hold_seconds, COALESCE(default_sender_id, '') as default_sender_id, " +
             "max_tps, concurrency " +
             "FROM channels WHERE protocol='SMPP' AND status='active' AND is_deleted=0"
    err := db.Select(&configs, query)
    return configs, err
}

// GetSMSLogByMessageID fetches a specific SMS log
func GetSMSLogByMessageID(messageID string) (*SMSLog, error) {
    var log SMSLog
    // Use the latest record if there are duplicates (partitioning might cause this if not careful)
    err := db.Get(&log, "SELECT id, message_id, phone_number, message, channel_id, submit_time FROM sms_logs WHERE message_id = ? ORDER BY submit_time DESC LIMIT 1", messageID)
    return &log, err
}

// UpdateSMSLogResult updates the status and upstream ID after sending
func UpdateSMSLogResult(id int64, messageID string, upstreamID string, status string, errMsg string) error {
    query := "UPDATE sms_logs SET status = ?, upstream_message_id = ?, error_message = ?, sent_time = NOW() WHERE id = ?"
    _, err := db.Exec(query, status, upstreamID, errMsg, id)
    return err
}

// UpdateSMSLogDLR updates the status when a DLR arrives
func UpdateSMSLogDLR(upstreamID string, status string) error {
    query := "UPDATE sms_logs SET status = ?, delivery_time = NOW() WHERE upstream_message_id = ? AND status='sent'"
    _, err := db.Exec(query, status, upstreamID)
    return err
}
