package main

import (
	"fmt"
	"log"
	"os"
	"time"

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
	// 连接池：避免高并发 Submit/DLR 更新时瞬间打满 MySQL
	db.SetMaxOpenConns(150)
	db.SetMaxIdleConns(50)
	db.SetConnMaxLifetime(time.Minute * 5)
	log.Println("Database connection established.")
}

// GetChannelConfigs loads all active SMPP channels
func GetChannelConfigs() ([]ChannelConfig, error) {
	var configs []ChannelConfig
	query := "SELECT id, channel_code, protocol, host, port, username, password, " +
		"smpp_bind_mode, smpp_system_type, smpp_interface_version, " +
		"smpp_dlr_socket_hold_seconds, COALESCE(default_sender_id, '') as default_sender_id, " +
		"max_tps, concurrency, COALESCE(config_json, '') as config_json " +
		"FROM channels WHERE protocol='SMPP' AND status='active' AND is_deleted=0"
	err := db.Select(&configs, query)
	return configs, err
}

// GetSMSLogByMessageID fetches a specific SMS log
func GetSMSLogByMessageID(messageID string) (*SMSLog, error) {
	var log SMSLog
	// Use the latest record if there are duplicates (partitioning might cause this if not careful)
	err := db.Get(&log, `SELECT l.id, l.message_id, l.phone_number, l.message, l.channel_id, l.submit_time, l.status,
		COALESCE(b.status, '') AS batch_status
		FROM sms_logs l
		LEFT JOIN sms_batches b ON b.id = l.batch_id
		WHERE l.message_id = ? ORDER BY l.submit_time DESC LIMIT 1`, messageID)
	return &log, err
}

// UpdateSMSLogResult updates the status and upstream ID after sending
func UpdateSMSLogResult(id int64, messageID string, upstreamID string, status string, errMsg string) error {
	query := "UPDATE sms_logs SET status = ?, upstream_message_id = ?, error_message = ?, sent_time = NOW() WHERE id = ?"
	_, err := db.Exec(query, status, upstreamID, errMsg, id)
	return err
}

// MarkSMSLogQueuedAfterSmppHandoff 已交给 SMPP 会话层（等待 SubmitSMResp），将仍为 pending 的记录标为 queued 并更新 submit_time。
// submit_time 在此处才真正反映消息被提交至 SMPP 网关的时刻，inspector 的孤儿清理窗口以此为基准。
func MarkSMSLogQueuedAfterSmppHandoff(id int64) error {
	_, err := db.Exec("UPDATE sms_logs SET status = 'queued', submit_time = NOW() WHERE id = ? AND status = 'pending'", id)
	return err
}

// MarkSMSLogBatchCancelled 批次已取消时，将未提交上游的待发记录标为失败（与 Python worker 一致）
func MarkSMSLogBatchCancelled(id int64) error {
	_, err := db.Exec(
		"UPDATE sms_logs SET status = 'failed', error_message = '批次已取消' WHERE id = ? AND status IN ('pending', 'queued')",
		id,
	)
	return err
}

// UpdateSMSLogDLR updates the status when a DLR arrives
func UpdateSMSLogDLR(upstreamID string, status string) error {
	query := "UPDATE sms_logs SET status = ?, delivery_time = NOW() WHERE upstream_message_id = ? AND status='sent'"
	_, err := db.Exec(query, status, upstreamID)
	return err
}
