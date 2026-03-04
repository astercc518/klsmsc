-- 国际短信系统 - 数据库初始化脚本 (Phase 1 Refactor)
-- 创建时间: 2026-01-04

USE sms_system;

-- 禁用外键约束，方便删除表
SET FOREIGN_KEY_CHECKS = 0;

-- 删除所有旧表（全量重构）
DROP TABLE IF EXISTS `sms_logs`;
DROP TABLE IF EXISTS `sender_ids`; -- 删除SID表
DROP TABLE IF EXISTS `routing_rules`;
DROP TABLE IF EXISTS `country_pricing`;
DROP TABLE IF EXISTS `balance_logs`;
DROP TABLE IF EXISTS `telegram_users`; -- 清理可能的旧TG表
DROP TABLE IF EXISTS `invitation_codes`; -- 清理可能的旧邀请码表
DROP TABLE IF EXISTS `recharge_orders`; -- 清理可能的旧工单表
DROP TABLE IF EXISTS `channels`;
DROP TABLE IF EXISTS `accounts`;
DROP TABLE IF EXISTS `admin_users`;
DROP TABLE IF EXISTS `system_config`;
DROP TABLE IF EXISTS `api_logs`;

-- 1. 管理员表 (admin_users)
CREATE TABLE `admin_users` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `username` VARCHAR(50) NOT NULL COMMENT '用户名',
  `password_hash` VARCHAR(255) NOT NULL COMMENT '密码哈希',
  `real_name` VARCHAR(100) COMMENT '真实姓名',
  `email` VARCHAR(255) COMMENT '邮箱',
  `phone` VARCHAR(20) COMMENT '手机号',
  `role` ENUM('super_admin', 'admin', 'finance', 'sales', 'tech') NOT NULL DEFAULT 'sales' COMMENT '角色',
  `status` ENUM('active', 'inactive', 'locked') NOT NULL DEFAULT 'active' COMMENT '状态',
  `last_login_at` TIMESTAMP NULL COMMENT '最后登录时间',
  `login_failed_count` INT NOT NULL DEFAULT 0 COMMENT '登录失败次数',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='管理员/员工表';

-- 2. 账户表 (accounts) - 增加销售归属
CREATE TABLE `accounts` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '账户ID',
  `account_name` VARCHAR(100) NOT NULL COMMENT '账户名称',
  `email` VARCHAR(255) UNIQUE COMMENT '邮箱(可选,TG用户可能无)',
  `password_hash` VARCHAR(255) COMMENT '密码哈希(可选)',
  `balance` DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT '账户余额',
  `currency` VARCHAR(10) NOT NULL DEFAULT 'USD' COMMENT '币种',
  `sales_id` INT UNSIGNED COMMENT '归属销售ID',
  `status` ENUM('active', 'suspended', 'closed') NOT NULL DEFAULT 'active' COMMENT '账户状态',
  `api_key` VARCHAR(64) UNIQUE COMMENT 'API密钥',
  `api_secret` VARCHAR(128) COMMENT 'API密钥',
  `ip_whitelist` TEXT COMMENT 'IP白名单',
  `rate_limit` INT DEFAULT 1000 COMMENT '每分钟限流',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_deleted` BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (`id`),
  KEY `idx_sales` (`sales_id`),
  FOREIGN KEY (`sales_id`) REFERENCES `admin_users`(`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户账户表';

-- 3. 通道表 (channels) - 必须包含默认SID
CREATE TABLE `channels` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '通道ID',
  `channel_code` VARCHAR(50) NOT NULL UNIQUE COMMENT '通道编码',
  `channel_name` VARCHAR(100) NOT NULL COMMENT '通道名称',
  `protocol` ENUM('SMPP', 'HTTP') NOT NULL COMMENT '协议类型',
  `host` VARCHAR(255) COMMENT '主机',
  `port` INT COMMENT '端口',
  `username` VARCHAR(100) COMMENT '账号',
  `password` VARCHAR(255) COMMENT '密码',
  `api_url` VARCHAR(500) COMMENT 'API地址',
  `api_key` VARCHAR(255) COMMENT 'API Key',
  `default_sender_id` VARCHAR(20) NOT NULL COMMENT '默认发送方ID(必填)',
  `cost_rate` DECIMAL(10,4) DEFAULT 0.0000 COMMENT '通道基础成本价(参考)',
  `priority` INT NOT NULL DEFAULT 0 COMMENT '优先级',
  `weight` INT NOT NULL DEFAULT 100 COMMENT '权重',
  `status` ENUM('active', 'inactive', 'maintenance') NOT NULL DEFAULT 'active',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_deleted` BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='通道表';

-- 4. 路由规则表 (routing_rules)
CREATE TABLE `routing_rules` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `country_code` VARCHAR(3) NOT NULL COMMENT '国家代码',
  `channel_id` INT UNSIGNED NOT NULL COMMENT '通道ID',
  `priority` INT NOT NULL DEFAULT 0,
  `is_active` BOOLEAN NOT NULL DEFAULT TRUE,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_country_channel` (`country_code`, `channel_id`),
  FOREIGN KEY (`channel_id`) REFERENCES `channels`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='路由规则表';

-- 5. 计费规则表 (country_pricing)
CREATE TABLE `country_pricing` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `channel_id` INT UNSIGNED NOT NULL COMMENT '通道ID',
  `country_code` VARCHAR(3) NOT NULL COMMENT '国家代码',
  `country_name` VARCHAR(100) COMMENT '国家名称',
  `price_per_sms` DECIMAL(10, 4) NOT NULL COMMENT '销售单价',
  `currency` VARCHAR(10) NOT NULL DEFAULT 'USD',
  `effective_date` DATE NOT NULL DEFAULT (CURRENT_DATE),
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_pricing` (`channel_id`, `country_code`),
  FOREIGN KEY (`channel_id`) REFERENCES `channels`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='计费规则表';

-- 6. Telegram 用户表 (telegram_users) [NEW]
CREATE TABLE `telegram_users` (
  `tg_id` BIGINT NOT NULL COMMENT 'Telegram User ID',
  `username` VARCHAR(100) COMMENT 'TG用户名',
  `first_name` VARCHAR(100) COMMENT 'TG昵称',
  `account_id` INT UNSIGNED NOT NULL COMMENT '关联账户ID',
  `lang_code` VARCHAR(10) DEFAULT 'en' COMMENT '语言偏好',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `last_active_at` TIMESTAMP NULL COMMENT '最后活跃时间',
  PRIMARY KEY (`tg_id`),
  UNIQUE KEY `uk_account` (`account_id`),
  FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Telegram用户表';

-- 7. 邀请码表 (invitation_codes) [NEW]
CREATE TABLE `invitation_codes` (
  `code` VARCHAR(32) NOT NULL COMMENT '授权码',
  `sales_id` INT UNSIGNED NOT NULL COMMENT '归属销售ID',
  `status` ENUM('unused', 'used', 'expired') NOT NULL DEFAULT 'unused',
  `used_by_account_id` INT UNSIGNED COMMENT '激活者账户ID',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `expires_at` TIMESTAMP NULL COMMENT '过期时间',
  `used_at` TIMESTAMP NULL COMMENT '使用时间',
  PRIMARY KEY (`code`),
  KEY `idx_sales` (`sales_id`),
  FOREIGN KEY (`sales_id`) REFERENCES `admin_users`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`used_by_account_id`) REFERENCES `accounts`(`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='邀请码表';

-- 8. 充值工单表 (recharge_orders) [NEW]
CREATE TABLE `recharge_orders` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `order_no` VARCHAR(64) NOT NULL UNIQUE COMMENT '工单号',
  `account_id` INT UNSIGNED NOT NULL COMMENT '申请账户',
  `amount` DECIMAL(12, 4) NOT NULL COMMENT '申请金额',
  `currency` VARCHAR(10) NOT NULL DEFAULT 'USD',
  `payment_proof` VARCHAR(500) COMMENT '支付凭证图片URL/FileID',
  `status` ENUM('pending', 'finance_approved', 'completed', 'rejected') NOT NULL DEFAULT 'pending',
  `finance_audit_by` INT UNSIGNED COMMENT '财务审核人',
  `finance_audit_at` TIMESTAMP NULL,
  `tech_audit_by` INT UNSIGNED COMMENT '技术执行人',
  `tech_audit_at` TIMESTAMP NULL,
  `reject_reason` VARCHAR(255) COMMENT '驳回原因',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_account` (`account_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='充值工单表';

-- 9. 短信记录表 (sms_logs) - 增加结算字段
CREATE TABLE `sms_logs` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `message_id` VARCHAR(64) NOT NULL,
  `account_id` INT UNSIGNED NOT NULL,
  `channel_id` INT UNSIGNED,
  `phone_number` VARCHAR(20) NOT NULL,
  `country_code` VARCHAR(3),
  `message` TEXT,
  `message_count` INT DEFAULT 1,
  `status` ENUM('pending', 'queued', 'sent', 'delivered', 'failed') NOT NULL DEFAULT 'pending',
  -- 结算核心字段
  `cost_price` DECIMAL(10, 4) DEFAULT 0.0000 COMMENT '通道成本',
  `selling_price` DECIMAL(10, 4) DEFAULT 0.0000 COMMENT '销售价格',
  `profit` DECIMAL(10, 4) GENERATED ALWAYS AS (selling_price - cost_price) STORED COMMENT '毛利',
  `currency` VARCHAR(10) DEFAULT 'USD',
  `submit_time` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `sent_time` TIMESTAMP NULL,
  `delivery_time` TIMESTAMP NULL,
  `error_message` TEXT,
  PRIMARY KEY (`id`, `submit_time`),
  UNIQUE KEY `uk_message_id_time` (`message_id`, `submit_time`),
  KEY `idx_account_time` (`account_id`, `submit_time` DESC),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='短信记录表'
PARTITION BY RANGE (UNIX_TIMESTAMP(submit_time)) (
    PARTITION p202601 VALUES LESS THAN (UNIX_TIMESTAMP('2026-02-01')),
    PARTITION p202602 VALUES LESS THAN (UNIX_TIMESTAMP('2026-03-01')),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);


-- 10. 余额变动表 (balance_logs)
CREATE TABLE `balance_logs` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_id` INT UNSIGNED NOT NULL,
  `change_type` ENUM('charge', 'refund', 'deposit', 'withdraw', 'adjustment') NOT NULL,
  `amount` DECIMAL(12, 4) NOT NULL,
  `balance_after` DECIMAL(12, 4) NOT NULL,
  `description` TEXT,
  `related_order_id` BIGINT UNSIGNED COMMENT '关联充值工单ID',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_account` (`account_id`),
  FOREIGN KEY (`related_order_id`) REFERENCES `recharge_orders`(`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='余额变动表';

-- 开启外键约束
SET FOREIGN_KEY_CHECKS = 1;

-- 初始数据
-- 1. 超级管理员
INSERT INTO admin_users (username, password_hash, role, real_name) VALUES 
('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYzS8tU8u0W', 'super_admin', 'System Admin'), -- admin123
('sales01', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYzS8tU8u0W', 'sales', 'Alice Sales'),
('finance01', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYzS8tU8u0W', 'finance', 'Bob Finance'),
('tech01', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYzS8tU8u0W', 'tech', 'Charlie Tech');

-- 2. 默认通道
INSERT INTO channels (channel_code, channel_name, protocol, default_sender_id, status) VALUES 
('CH-Direct-01', 'Global Direct Route', 'HTTP', 'SMS-INFO', 'active');

-- 3. 邀请码 (供测试)
INSERT INTO invitation_codes (code, sales_id, status) VALUES 
('INV-TEST-8888', 2, 'unused');

SELECT 'Database refactor completed!' AS status;
