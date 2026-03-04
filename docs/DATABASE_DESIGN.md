# 国际短信系统 - 数据库设计文档

## 文档信息
- **文档类型**: Database Design Document
- **系统名称**: International SMS Gateway System
- **数据库版本**: MySQL 8.0
- **文档版本**: v1.0
- **创建日期**: 2025-12-30

---

## 目录
1. [数据库概述](#1-数据库概述)
2. [数据库设计原则](#2-数据库设计原则)
3. [表结构设计](#3-表结构设计)
4. [索引设计](#4-索引设计)
5. [分区策略](#5-分区策略)
6. [初始化数据](#6-初始化数据)

---

## 1. 数据库概述

### 1.1 数据库列表
```
sms_system          # 主数据库
├── 核心业务表
│   ├── accounts            # 账户表
│   ├── channels            # 通道表
│   ├── routing_rules       # 路由规则表
│   ├── country_pricing     # 计费规则表
│   └── sender_ids          # 发送方ID表
├── 业务日志表
│   ├── sms_logs            # 短信记录表
│   ├── balance_logs        # 余额变动表
│   └── api_logs            # API调用日志表
└── 系统配置表
    ├── system_config       # 系统配置表
    └── admin_users         # 管理员用户表
```

### 1.2 数据量估算
| 表名 | 日增量 | 年增量 | 数据保留 | 预估总量 |
|------|--------|--------|---------|---------|
| sms_logs | 100万 | 3.65亿 | 1年 | 3.65亿 |
| balance_logs | 10万 | 3650万 | 永久 | 7300万+ |
| api_logs | 200万 | 7.3亿 | 90天 | 1.8亿 |

---

## 2. 数据库设计原则

1. **第三范式**: 减少数据冗余
2. **合理反范式**: 性能优化（如冗余国家名称）
3. **垂直分表**: 大字段独立存储
4. **水平分表**: 按时间分区
5. **软删除**: 重要数据不物理删除
6. **审计字段**: 创建时间、更新时间、创建人、更新人

---

## 3. 表结构设计

### 3.1 账户表 (accounts)

**用途**: 存储客户账户信息

```sql
CREATE TABLE `accounts` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '账户ID',
  `account_name` VARCHAR(100) NOT NULL COMMENT '账户名称',
  `email` VARCHAR(255) NOT NULL COMMENT '邮箱',
  `password_hash` VARCHAR(255) NOT NULL COMMENT '密码哈希',
  `balance` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT '账户余额',
  `currency` VARCHAR(10) NOT NULL DEFAULT 'USD' COMMENT '币种',
  `low_balance_threshold` DECIMAL(10, 4) DEFAULT 100.0000 COMMENT '低余额阈值',
  `status` ENUM('active', 'suspended', 'closed') NOT NULL DEFAULT 'active' COMMENT '账户状态',
  `api_key` VARCHAR(64) UNIQUE COMMENT 'API密钥',
  `api_secret` VARCHAR(128) COMMENT 'API密钥（加密存储）',
  `ip_whitelist` TEXT COMMENT 'IP白名单（JSON数组）',
  `rate_limit` INT DEFAULT 1000 COMMENT '每分钟请求限制',
  `company_name` VARCHAR(200) COMMENT '公司名称',
  `contact_person` VARCHAR(100) COMMENT '联系人',
  `contact_phone` VARCHAR(20) COMMENT '联系电话',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_by` INT COMMENT '创建人ID',
  `is_deleted` BOOLEAN NOT NULL DEFAULT FALSE COMMENT '软删除标记',
  
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_email` (`email`),
  UNIQUE KEY `uk_api_key` (`api_key`),
  KEY `idx_status` (`status`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='账户表';
```

**示例数据**:
```sql
INSERT INTO accounts (account_name, email, password_hash, balance, currency, api_key, api_secret)
VALUES 
('测试账户', 'test@example.com', '$2b$12$...', 10000.00, 'CNY', 'ak_test123...', 'encrypted_secret');
```

---

### 3.2 通道表 (channels)

**用途**: 存储短信通道配置信息

```sql
CREATE TABLE `channels` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '通道ID',
  `channel_code` VARCHAR(50) NOT NULL COMMENT '通道编码（唯一标识）',
  `channel_name` VARCHAR(100) NOT NULL COMMENT '通道名称',
  `protocol` ENUM('SMPP', 'HTTP', 'SOAP') NOT NULL COMMENT '协议类型',
  `host` VARCHAR(255) COMMENT '主机地址',
  `port` INT COMMENT '端口号',
  `username` VARCHAR(100) COMMENT '用户名',
  `password` VARCHAR(255) COMMENT '密码（加密存储）',
  `api_url` VARCHAR(500) COMMENT 'HTTP API地址',
  `api_key` VARCHAR(255) COMMENT 'HTTP API密钥',
  `priority` INT NOT NULL DEFAULT 0 COMMENT '优先级（数值越大越优先）',
  `weight` INT NOT NULL DEFAULT 100 COMMENT '权重（用于负载均衡）',
  `max_tps` INT NOT NULL DEFAULT 100 COMMENT '最大TPS限制',
  `status` ENUM('active', 'inactive', 'maintenance', 'fault') NOT NULL DEFAULT 'active' COMMENT '通道状态',
  `success_rate` DECIMAL(5, 2) DEFAULT 0.00 COMMENT '成功率（百分比）',
  `avg_latency_ms` INT DEFAULT 0 COMMENT '平均延迟（毫秒）',
  `current_tps` INT DEFAULT 0 COMMENT '当前TPS',
  `default_sender_id` VARCHAR(20) COMMENT '默认发送方ID',
  `supported_countries` TEXT COMMENT '支持的国家列表（JSON数组）',
  `config_json` TEXT COMMENT '额外配置（JSON格式）',
  `description` TEXT COMMENT '通道描述',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_by` INT COMMENT '创建人ID',
  `is_deleted` BOOLEAN NOT NULL DEFAULT FALSE,
  
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_channel_code` (`channel_code`),
  KEY `idx_status` (`status`),
  KEY `idx_priority` (`priority` DESC),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='通道表';
```

**示例数据**:
```sql
INSERT INTO channels (channel_code, channel_name, protocol, host, port, username, password, priority, weight, max_tps)
VALUES 
('channel_cn_01', 'China Mobile Gateway', 'SMPP', '192.168.1.100', 2775, 'smpp_user', 'encrypted_pass', 100, 150, 1000),
('channel_us_twilio', 'Twilio US Gateway', 'HTTP', NULL, NULL, NULL, NULL, 90, 120, 500);
```

---

### 3.3 路由规则表 (routing_rules)

**用途**: 配置国家与通道的路由关系

```sql
CREATE TABLE `routing_rules` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '规则ID',
  `country_code` VARCHAR(10) NOT NULL COMMENT '国家代码（ISO 3166-1）',
  `channel_id` INT UNSIGNED NOT NULL COMMENT '通道ID',
  `priority` INT NOT NULL DEFAULT 0 COMMENT '优先级',
  `weight` INT NOT NULL DEFAULT 100 COMMENT '权重',
  `is_active` BOOLEAN NOT NULL DEFAULT TRUE COMMENT '是否启用',
  `effective_date` DATE COMMENT '生效日期',
  `expiry_date` DATE COMMENT '失效日期',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_by` INT,
  
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_country_channel` (`country_code`, `channel_id`),
  KEY `idx_country` (`country_code`),
  KEY `idx_channel` (`channel_id`),
  KEY `idx_priority` (`priority` DESC),
  KEY `idx_is_active` (`is_active`),
  FOREIGN KEY (`channel_id`) REFERENCES `channels`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='路由规则表';
```

**示例数据**:
```sql
INSERT INTO routing_rules (country_code, channel_id, priority, weight, is_active)
VALUES 
('CN', 1, 100, 150, TRUE),
('US', 2, 90, 120, TRUE),
('IN', 1, 80, 100, TRUE);
```

---

### 3.4 计费规则表 (country_pricing)

**用途**: 存储不同国家/运营商的短信价格

```sql
CREATE TABLE `country_pricing` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '价格ID',
  `channel_id` INT UNSIGNED NOT NULL COMMENT '通道ID',
  `country_code` VARCHAR(10) NOT NULL COMMENT '国家代码',
  `country_name` VARCHAR(100) COMMENT '国家名称',
  `mcc` VARCHAR(10) COMMENT '移动国家代码',
  `mnc` VARCHAR(10) COMMENT '移动网络代码',
  `operator_name` VARCHAR(100) COMMENT '运营商名称',
  `price_per_sms` DECIMAL(10, 4) NOT NULL COMMENT '单条价格',
  `currency` VARCHAR(10) NOT NULL DEFAULT 'USD' COMMENT '币种',
  `effective_date` DATE NOT NULL COMMENT '生效日期',
  `expiry_date` DATE COMMENT '失效日期',
  `description` TEXT COMMENT '备注',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_by` INT,
  
  PRIMARY KEY (`id`),
  KEY `idx_channel_country` (`channel_id`, `country_code`),
  KEY `idx_channel_country_mnc` (`channel_id`, `country_code`, `mnc`),
  KEY `idx_effective_date` (`effective_date` DESC),
  FOREIGN KEY (`channel_id`) REFERENCES `channels`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='计费规则表';
```

**示例数据**:
```sql
INSERT INTO country_pricing (channel_id, country_code, country_name, operator_name, price_per_sms, currency, effective_date)
VALUES 
(1, 'CN', '中国', '中国移动', 0.0500, 'CNY', '2025-01-01'),
(1, 'CN', '中国', '中国联通', 0.0480, 'CNY', '2025-01-01'),
(1, 'CN', '中国', '中国电信', 0.0490, 'CNY', '2025-01-01'),
(2, 'US', '美国', 'ALL', 0.0080, 'USD', '2025-01-01'),
(1, 'IN', '印度', 'ALL', 0.0050, 'USD', '2025-01-01');
```

---

### 3.5 发送方ID表 (sender_ids)

**用途**: 管理自定义发送方ID

```sql
CREATE TABLE `sender_ids` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `sid` VARCHAR(20) NOT NULL COMMENT '发送方ID',
  `account_id` INT UNSIGNED COMMENT '账户ID（NULL表示通用）',
  `channel_id` INT UNSIGNED NOT NULL COMMENT '通道ID',
  `country_code` VARCHAR(10) COMMENT '国家代码（NULL表示全球）',
  `sid_type` ENUM('numeric', 'alpha', 'shortcode') NOT NULL COMMENT 'SID类型',
  `status` ENUM('pending', 'active', 'inactive', 'rejected') NOT NULL DEFAULT 'pending' COMMENT '状态',
  `is_default` BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否默认',
  `approved_at` TIMESTAMP NULL COMMENT '审核通过时间',
  `approved_by` INT COMMENT '审核人ID',
  `reject_reason` TEXT COMMENT '拒绝原因',
  `application_documents` TEXT COMMENT '申请文档（JSON格式）',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_by` INT,
  
  PRIMARY KEY (`id`),
  KEY `idx_sid_channel` (`sid`, `channel_id`),
  KEY `idx_account_country_channel` (`account_id`, `country_code`, `channel_id`),
  KEY `idx_status` (`status`),
  FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`channel_id`) REFERENCES `channels`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='发送方ID表';
```

**示例数据**:
```sql
INSERT INTO sender_ids (sid, account_id, channel_id, country_code, sid_type, status, is_default)
VALUES 
('Alibaba', 1, 2, 'US', 'alpha', 'active', TRUE),
('Taobao', 1, 2, 'US', 'alpha', 'active', FALSE),
('106901234567', 1, 1, 'CN', 'numeric', 'active', TRUE);
```

---

### 3.6 短信记录表 (sms_logs)

**用途**: 存储所有短信发送记录

```sql
CREATE TABLE `sms_logs` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '记录ID',
  `message_id` VARCHAR(100) NOT NULL COMMENT '消息ID（唯一）',
  `account_id` INT UNSIGNED NOT NULL COMMENT '账户ID',
  `phone_number` VARCHAR(20) NOT NULL COMMENT '手机号码',
  `country_code` VARCHAR(10) COMMENT '国家代码',
  `operator_name` VARCHAR(100) COMMENT '运营商名称',
  `sender_id` VARCHAR(20) COMMENT '发送方ID',
  `channel_id` INT UNSIGNED COMMENT '通道ID',
  `channel_name` VARCHAR(100) COMMENT '通道名称（冗余）',
  `message_content` TEXT COMMENT '短信内容',
  `message_length` INT COMMENT '消息长度',
  `message_parts` INT NOT NULL DEFAULT 1 COMMENT '短信条数',
  `status` ENUM('pending', 'queued', 'sent', 'delivered', 'failed', 'expired', 'rejected') NOT NULL DEFAULT 'pending' COMMENT '状态',
  `price_per_sms` DECIMAL(10, 4) COMMENT '单条价格',
  `total_price` DECIMAL(10, 4) COMMENT '总价格',
  `currency` VARCHAR(10) COMMENT '币种',
  `error_code` VARCHAR(50) COMMENT '错误代码',
  `error_message` TEXT COMMENT '错误信息',
  `external_message_id` VARCHAR(100) COMMENT '第三方消息ID',
  `submit_time` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '提交时间',
  `queue_time` TIMESTAMP NULL COMMENT '入队时间',
  `sent_time` TIMESTAMP NULL COMMENT '发送时间',
  `delivery_time` TIMESTAMP NULL COMMENT '送达时间',
  `callback_url` VARCHAR(500) COMMENT '回调URL',
  `callback_status` ENUM('pending', 'success', 'failed') COMMENT '回调状态',
  `callback_time` TIMESTAMP NULL COMMENT '回调时间',
  `retry_count` INT NOT NULL DEFAULT 0 COMMENT '重试次数',
  `routing_strategy` VARCHAR(50) COMMENT '路由策略',
  `ip_address` VARCHAR(45) COMMENT '请求IP',
  `user_agent` VARCHAR(255) COMMENT 'User Agent',
  
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_message_id` (`message_id`),
  KEY `idx_account` (`account_id`),
  KEY `idx_phone` (`phone_number`),
  KEY `idx_status` (`status`),
  KEY `idx_submit_time` (`submit_time` DESC),
  KEY `idx_account_submit_time` (`account_id`, `submit_time` DESC),
  KEY `idx_status_submit_time` (`status`, `submit_time` DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='短信记录表'
PARTITION BY RANGE (UNIX_TIMESTAMP(submit_time)) (
    PARTITION p202512 VALUES LESS THAN (UNIX_TIMESTAMP('2026-01-01')),
    PARTITION p202601 VALUES LESS THAN (UNIX_TIMESTAMP('2026-02-01')),
    PARTITION p202602 VALUES LESS THAN (UNIX_TIMESTAMP('2026-03-01')),
    PARTITION p202603 VALUES LESS THAN (UNIX_TIMESTAMP('2026-04-01')),
    PARTITION p202604 VALUES LESS THAN (UNIX_TIMESTAMP('2026-05-01')),
    PARTITION p202605 VALUES LESS THAN (UNIX_TIMESTAMP('2026-06-01')),
    PARTITION p202606 VALUES LESS THAN (UNIX_TIMESTAMP('2026-07-01')),
    PARTITION p202607 VALUES LESS THAN (UNIX_TIMESTAMP('2026-08-01')),
    PARTITION p202608 VALUES LESS THAN (UNIX_TIMESTAMP('2026-09-01')),
    PARTITION p202609 VALUES LESS THAN (UNIX_TIMESTAMP('2026-10-01')),
    PARTITION p202610 VALUES LESS THAN (UNIX_TIMESTAMP('2026-11-01')),
    PARTITION p202611 VALUES LESS THAN (UNIX_TIMESTAMP('2026-12-01')),
    PARTITION p202612 VALUES LESS THAN (UNIX_TIMESTAMP('2027-01-01')),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

**说明**:
- 按月分区，提高查询性能
- 冗余通道名称，避免关联查询
- 包含完整的状态流转时间戳
- 支持回调状态追踪

---

### 3.7 余额变动表 (balance_logs)

**用途**: 记录所有余额变动历史

```sql
CREATE TABLE `balance_logs` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '记录ID',
  `account_id` INT UNSIGNED NOT NULL COMMENT '账户ID',
  `change_type` ENUM('charge', 'refund', 'recharge', 'adjustment') NOT NULL COMMENT '变动类型',
  `amount` DECIMAL(12, 4) NOT NULL COMMENT '变动金额（正数为增加，负数为扣减）',
  `balance_before` DECIMAL(12, 4) NOT NULL COMMENT '变动前余额',
  `balance_after` DECIMAL(12, 4) NOT NULL COMMENT '变动后余额',
  `currency` VARCHAR(10) NOT NULL COMMENT '币种',
  `related_message_id` VARCHAR(100) COMMENT '关联消息ID（如果是短信扣费）',
  `related_order_id` VARCHAR(100) COMMENT '关联订单ID（如果是充值）',
  `description` TEXT COMMENT '变动说明',
  `operator_id` INT COMMENT '操作人ID',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  
  PRIMARY KEY (`id`),
  KEY `idx_account` (`account_id`),
  KEY `idx_created_at` (`created_at` DESC),
  KEY `idx_account_created` (`account_id`, `created_at` DESC),
  KEY `idx_message_id` (`related_message_id`),
  FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='余额变动表';
```

---

### 3.8 API调用日志表 (api_logs)

**用途**: 记录所有API调用

```sql
CREATE TABLE `api_logs` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `request_id` VARCHAR(100) NOT NULL COMMENT '请求ID',
  `account_id` INT UNSIGNED COMMENT '账户ID',
  `api_key` VARCHAR(64) COMMENT 'API密钥',
  `endpoint` VARCHAR(255) NOT NULL COMMENT '接口路径',
  `method` VARCHAR(10) NOT NULL COMMENT 'HTTP方法',
  `request_body` TEXT COMMENT '请求体（可能很大）',
  `response_body` TEXT COMMENT '响应体',
  `status_code` INT COMMENT 'HTTP状态码',
  `response_time_ms` INT COMMENT '响应时间（毫秒）',
  `ip_address` VARCHAR(45) COMMENT '客户端IP',
  `user_agent` VARCHAR(255) COMMENT 'User Agent',
  `error_message` TEXT COMMENT '错误信息',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  
  PRIMARY KEY (`id`),
  KEY `idx_request_id` (`request_id`),
  KEY `idx_account` (`account_id`),
  KEY `idx_created_at` (`created_at` DESC),
  KEY `idx_endpoint` (`endpoint`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='API调用日志表'
PARTITION BY RANGE (UNIX_TIMESTAMP(created_at)) (
    PARTITION p202512 VALUES LESS THAN (UNIX_TIMESTAMP('2026-01-01')),
    PARTITION p202601 VALUES LESS THAN (UNIX_TIMESTAMP('2026-02-01')),
    PARTITION p202602 VALUES LESS THAN (UNIX_TIMESTAMP('2026-03-01')),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

---

### 3.9 管理员用户表 (admin_users)

**用途**: 管理后台用户

```sql
CREATE TABLE `admin_users` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `username` VARCHAR(50) NOT NULL COMMENT '用户名',
  `password_hash` VARCHAR(255) NOT NULL COMMENT '密码哈希',
  `real_name` VARCHAR(100) COMMENT '真实姓名',
  `email` VARCHAR(255) COMMENT '邮箱',
  `phone` VARCHAR(20) COMMENT '手机号',
  `role` ENUM('super_admin', 'admin', 'operator', 'viewer') NOT NULL DEFAULT 'viewer' COMMENT '角色',
  `status` ENUM('active', 'inactive', 'locked') NOT NULL DEFAULT 'active' COMMENT '状态',
  `last_login_at` TIMESTAMP NULL COMMENT '最后登录时间',
  `last_login_ip` VARCHAR(45) COMMENT '最后登录IP',
  `login_failed_count` INT NOT NULL DEFAULT 0 COMMENT '登录失败次数',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_by` INT,
  
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username` (`username`),
  KEY `idx_email` (`email`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='管理员用户表';
```

---

### 3.10 系统配置表 (system_config)

**用途**: 存储系统级配置

```sql
CREATE TABLE `system_config` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `config_key` VARCHAR(100) NOT NULL COMMENT '配置键',
  `config_value` TEXT COMMENT '配置值',
  `config_type` ENUM('string', 'number', 'boolean', 'json') NOT NULL DEFAULT 'string' COMMENT '值类型',
  `description` TEXT COMMENT '配置说明',
  `is_public` BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否公开（API可读取）',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `updated_by` INT,
  
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_config_key` (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统配置表';
```

---

## 4. 索引设计

### 4.1 索引策略

**原则**:
1. 为WHERE、ORDER BY、GROUP BY字段建立索引
2. 高频查询使用复合索引（遵循最左前缀原则）
3. 避免过多索引（影响写入性能）
4. 使用覆盖索引优化查询

### 4.2 重要索引

**sms_logs表**:
```sql
-- 1. 消息ID唯一索引（查询单条记录）
CREATE UNIQUE INDEX uk_message_id ON sms_logs(message_id);

-- 2. 账户+时间复合索引（用户查询自己的记录）
CREATE INDEX idx_account_submit_time ON sms_logs(account_id, submit_time DESC);

-- 3. 状态+时间复合索引（管理后台查询）
CREATE INDEX idx_status_submit_time ON sms_logs(status, submit_time DESC);

-- 4. 手机号索引（查询特定号码的记录）
CREATE INDEX idx_phone ON sms_logs(phone_number);

-- 5. 覆盖索引（常用字段查询）
CREATE INDEX idx_account_status_time 
ON sms_logs(account_id, status, submit_time DESC)
INCLUDE (message_id, phone_number, total_price);
```

**country_pricing表**:
```sql
-- 复合索引（路由查询价格）
CREATE INDEX idx_channel_country_mnc 
ON country_pricing(channel_id, country_code, mnc, effective_date DESC);
```

---

## 5. 分区策略

### 5.1 分区表设计

**sms_logs按月分区**:
```sql
-- 每月自动创建新分区（需要定时任务）
DELIMITER $$
CREATE PROCEDURE create_monthly_partition()
BEGIN
  DECLARE next_month_start DATE;
  DECLARE partition_name VARCHAR(20);
  
  SET next_month_start = DATE_ADD(DATE_FORMAT(NOW(), '%Y-%m-01'), INTERVAL 2 MONTH);
  SET partition_name = CONCAT('p', DATE_FORMAT(next_month_start, '%Y%m'));
  
  SET @sql = CONCAT('ALTER TABLE sms_logs ADD PARTITION (PARTITION ', partition_name, 
                    ' VALUES LESS THAN (UNIX_TIMESTAMP(''', next_month_start, ''')))');
  PREPARE stmt FROM @sql;
  EXECUTE stmt;
  DEALLOCATE PREPARE stmt;
END$$
DELIMITER ;

-- 创建定时任务（每月1号执行）
CREATE EVENT create_partition_monthly
ON SCHEDULE EVERY 1 MONTH STARTS '2026-01-01 00:00:00'
DO CALL create_monthly_partition();
```

### 5.2 分区维护

**删除旧分区**:
```sql
-- 删除1年前的数据分区
ALTER TABLE sms_logs DROP PARTITION p202412;
```

---

## 6. 初始化数据

### 6.1 系统配置初始化

```sql
INSERT INTO system_config (config_key, config_value, config_type, description, is_public) VALUES
('default_currency', 'USD', 'string', '默认币种', TRUE),
('default_rate_limit', '1000', 'number', '默认每分钟请求限制', TRUE),
('sms_max_length', '1000', 'number', '短信最大长度', TRUE),
('enable_callback', 'true', 'boolean', '是否启用回调', FALSE),
('callback_retry_times', '3', 'number', '回调重试次数', FALSE),
('low_balance_alert_threshold', '100', 'number', '低余额告警阈值', FALSE);
```

### 6.2 初始管理员

```sql
-- 密码: admin123 (实际应该用bcrypt加密)
INSERT INTO admin_users (username, password_hash, real_name, email, role, status)
VALUES ('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYzpLKKe7Uu', '系统管理员', 'admin@example.com', 'super_admin', 'active');
```

### 6.3 示例通道数据

```sql
-- 中国移动通道
INSERT INTO channels (channel_code, channel_name, protocol, host, port, username, password, priority, weight, max_tps, status)
VALUES ('channel_cn_mobile', '中国移动网关', 'SMPP', '192.168.1.100', 2775, 'cmcc_user', 'encrypted_pass', 100, 150, 1000, 'active');

-- 添加路由规则
INSERT INTO routing_rules (country_code, channel_id, priority, weight, is_active)
VALUES ('CN', 1, 100, 150, TRUE);

-- 添加计费规则
INSERT INTO country_pricing (channel_id, country_code, country_name, operator_name, price_per_sms, currency, effective_date)
VALUES (1, 'CN', '中国', '中国移动', 0.0500, 'CNY', '2025-01-01');
```

---

## 7. 数据库维护

### 7.1 定期维护任务

```sql
-- 1. 优化表（每周执行）
OPTIMIZE TABLE sms_logs;
OPTIMIZE TABLE balance_logs;
OPTIMIZE TABLE api_logs;

-- 2. 分析表（每天执行）
ANALYZE TABLE sms_logs;
ANALYZE TABLE accounts;
ANALYZE TABLE channels;

-- 3. 检查表
CHECK TABLE sms_logs;

-- 4. 修复表（如果有损坏）
REPAIR TABLE sms_logs;
```

### 7.2 慢查询监控

```sql
-- 开启慢查询日志
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 1; -- 超过1秒的查询记录

-- 查看慢查询
SELECT * FROM mysql.slow_log ORDER BY start_time DESC LIMIT 10;
```

---

## 8. 数据备份策略

### 8.1 备份脚本

```bash
#!/bin/bash
# backup.sh - MySQL全量备份脚本

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/mysql"
DB_NAME="sms_system"
DB_USER="backup_user"
DB_PASS="backup_pass"

# 全量备份
mysqldump -u${DB_USER} -p${DB_PASS} \
  --single-transaction \
  --master-data=2 \
  --flush-logs \
  --databases ${DB_NAME} \
  | gzip > ${BACKUP_DIR}/full_${DATE}.sql.gz

# 删除30天前的备份
find ${BACKUP_DIR} -name "full_*.sql.gz" -mtime +30 -delete

# 上传到OSS（可选）
# ossutil cp ${BACKUP_DIR}/full_${DATE}.sql.gz oss://backup-bucket/mysql/
```

### 8.2 恢复测试

```bash
# 解压备份文件
gunzip full_20251230_020000.sql.gz

# 恢复数据
mysql -u root -p sms_system < full_20251230_020000.sql

# 验证数据
mysql -u root -p -e "SELECT COUNT(*) FROM sms_system.sms_logs;"
```

---

## 附录

### A. ER图

```
[accounts] 1--∞ [sms_logs]
[accounts] 1--∞ [balance_logs]
[accounts] 1--∞ [sender_ids]

[channels] 1--∞ [sms_logs]
[channels] 1--∞ [routing_rules]
[channels] 1--∞ [country_pricing]
[channels] 1--∞ [sender_ids]

[routing_rules] ∞--1 [channels]
[country_pricing] ∞--1 [channels]
[sender_ids] ∞--1 [accounts]
[sender_ids] ∞--1 [channels]
```

### B. 数据字典

见各表结构的COMMENT字段

### C. 变更历史

| 版本 | 日期 | 修改人 | 变更内容 |
|------|------|--------|---------|
| v1.0 | 2025-12-30 | System | 初始版本，完整数据库设计 |

---

**文档结束**

