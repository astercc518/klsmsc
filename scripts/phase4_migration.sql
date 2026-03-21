-- Phase 4 数据库迁移脚本
-- 创建时间: 2025-12-31
-- 说明: 为Phase 4功能添加必要的数据库字段和表

USE sms_system;

-- ============================================
-- 1. 检查并创建 system_config 表（如果不存在）
-- ============================================
CREATE TABLE IF NOT EXISTS `system_config` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `config_key` VARCHAR(100) NOT NULL COMMENT '配置键',
  `config_value` TEXT COMMENT '配置值',
  `config_type` ENUM('string', 'number', 'boolean', 'json') NOT NULL DEFAULT 'string' COMMENT '值类型',
  `description` TEXT COMMENT '配置说明',
  `is_public` BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否公开（API可读取）',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `updated_by` INT UNSIGNED COMMENT '更新人ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_config_key` (`config_key`),
  KEY `idx_public` (`is_public`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统配置表';

-- ============================================
-- 2. 检查并创建 sms_batches 表（如果不存在）
-- ============================================
CREATE TABLE IF NOT EXISTS `sms_batches` (
  `id` VARCHAR(64) NOT NULL COMMENT '批次ID',
  `account_id` INT UNSIGNED NOT NULL COMMENT '账户ID',
  `file_path` VARCHAR(255) COMMENT '号码文件路径',
  `content` TEXT COMMENT '发送内容',
  `total_count` INT DEFAULT 0 COMMENT '总条数',
  `valid_count` INT DEFAULT 0 COMMENT '有效号码数',
  `total_cost` DECIMAL(12, 4) DEFAULT 0 COMMENT '总费用',
  `status` ENUM('pending_audit', 'approved', 'rejected', 'sending', 'completed', 'failed') DEFAULT 'pending_audit' COMMENT '状态',
  `audit_by` INT UNSIGNED COMMENT '审核人ID',
  `audit_at` TIMESTAMP NULL COMMENT '审核时间',
  `reject_reason` VARCHAR(500) COMMENT '拒绝原因',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_account` (`account_id`),
  KEY `idx_status` (`status`),
  KEY `idx_created` (`created_at`),
  FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='短信群发批次表';

-- ============================================
-- 3. 检查并创建 sms_templates 表（如果不存在）
-- ============================================
CREATE TABLE IF NOT EXISTS `sms_templates` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_id` INT UNSIGNED NOT NULL COMMENT '账户ID',
  `content_hash` VARCHAR(64) NOT NULL COMMENT '内容哈希(SHA256)',
  `content_text` TEXT COMMENT '内容原文',
  `status` ENUM('approved', 'rejected') DEFAULT 'approved' COMMENT '状态',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_account` (`account_id`),
  KEY `idx_hash` (`content_hash`),
  KEY `idx_account_hash` (`account_id`, `content_hash`),
  FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='短信文案模版表(白名单)';

-- ============================================
-- 4. 为 sms_batches 表添加 reject_reason 字段（如果不存在）
-- ============================================
SET @column_exists = (
  SELECT COUNT(*) 
  FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'sms_system' 
    AND TABLE_NAME = 'sms_batches' 
    AND COLUMN_NAME = 'reject_reason'
);

SET @sql = IF(@column_exists = 0,
  'ALTER TABLE `sms_batches` ADD COLUMN `reject_reason` VARCHAR(500) COMMENT ''拒绝原因'' AFTER `audit_at`',
  'SELECT ''Column reject_reason already exists'' AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 5. 为 invitation_codes 表添加 pricing_config 字段（如果不存在）
-- ============================================
SET @column_exists = (
  SELECT COUNT(*) 
  FROM INFORMATION_SCHEMA.COLUMNS 
  WHERE TABLE_SCHEMA = 'sms_system' 
    AND TABLE_NAME = 'invitation_codes' 
    AND COLUMN_NAME = 'pricing_config'
);

SET @sql = IF(@column_exists = 0,
  'ALTER TABLE `invitation_codes` ADD COLUMN `pricing_config` JSON COMMENT ''定价配置'' AFTER `sales_id`',
  'SELECT ''Column pricing_config already exists'' AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 6. 初始化系统配置数据
-- ============================================
INSERT IGNORE INTO `system_config` (`config_key`, `config_value`, `config_type`, `description`, `is_public`) VALUES
('telegram_bot_token', '', 'string', 'Telegram Bot Token', FALSE),
('telegram_bot_username', '', 'string', 'Telegram Bot Username', FALSE),
('default_currency', 'USD', 'string', '默认币种', TRUE),
('default_rate_limit', '1000', 'number', '默认每分钟请求限制', TRUE),
('sms_max_length', '1000', 'number', '短信最大长度', TRUE),
('enable_callback', 'true', 'boolean', '是否启用回调', FALSE),
('callback_retry_times', '3', 'number', '回调重试次数', FALSE),
('low_balance_alert_threshold', '100', 'number', '低余额告警阈值', FALSE);

-- ============================================
-- 7. 创建索引优化查询性能
-- ============================================
-- invitation_codes 表索引
CREATE INDEX IF NOT EXISTS `idx_invites_sales_status` ON `invitation_codes`(`sales_id`, `status`);
CREATE INDEX IF NOT EXISTS `idx_invites_expires` ON `invitation_codes`(`expires_at`);
CREATE INDEX IF NOT EXISTS `idx_invites_created` ON `invitation_codes`(`created_at` DESC);

-- recharge_orders 表索引
CREATE INDEX IF NOT EXISTS `idx_recharge_account_status` ON `recharge_orders`(`account_id`, `status`);
CREATE INDEX IF NOT EXISTS `idx_recharge_created` ON `recharge_orders`(`created_at` DESC);

-- sms_batches 表索引
CREATE INDEX IF NOT EXISTS `idx_batch_account_status` ON `sms_batches`(`account_id`, `status`);
CREATE INDEX IF NOT EXISTS `idx_batch_created` ON `sms_batches`(`created_at` DESC);

-- sms_templates 表索引
CREATE INDEX IF NOT EXISTS `idx_template_account_hash` ON `sms_templates`(`account_id`, `content_hash`);
CREATE INDEX IF NOT EXISTS `idx_template_search` ON `sms_templates`(`content_text`(100));

SELECT 'Phase 4 migration completed successfully!' AS status;
