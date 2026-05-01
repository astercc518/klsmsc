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

// 发送结果写库已迁至 Python process_sms_result_task（队列 sms_result_queue）；本文件仅保留通道配置加载。

// UpdateChannelConnectionStatus 把 SMPPManager 当前持有的真实 bind 状态回写到 channels 表。
// status 取值与 Python 侧一致：online / offline / unknown。
func UpdateChannelConnectionStatus(channelID int, status string) error {
	_, err := db.Exec(
		"UPDATE channels SET connection_status=?, connection_checked_at=NOW() WHERE id=?",
		status, channelID,
	)
	return err
}
