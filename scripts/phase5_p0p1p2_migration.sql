-- Phase 5: P0-P2 功能增强数据库迁移脚本
-- 创建时间: 2026-01-26
-- 说明: 短信模板、API密钥管理、批量发送等功能的数据库表

-- ============================================
-- 1. 短信模板表（P0-1）
-- ============================================
CREATE TABLE IF NOT EXISTS `sms_templates` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '模板ID',
  `account_id` INT UNSIGNED NOT NULL COMMENT '账户ID',
  `name` VARCHAR(100) NOT NULL COMMENT '模板名称',
  `category` ENUM('verification', 'notification', 'marketing') NOT NULL COMMENT '模板分类',
  `content` TEXT NOT NULL COMMENT '模板内容',
  `variables` TEXT COMMENT '变量列表（JSON数组）',
  `status` ENUM('pending', 'approved', 'rejected', 'disabled') DEFAULT 'pending' COMMENT '审核状态',
  `reject_reason` VARCHAR(500) COMMENT '拒绝原因',
  `approved_by` INT COMMENT '审核人ID',
  `approved_at` TIMESTAMP NULL COMMENT '审核时间',
  `usage_count` INT DEFAULT 0 COMMENT '使用次数',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '软删除标记',
  PRIMARY KEY (`id`),
  INDEX `idx_account_id` (`account_id`),
  INDEX `idx_status` (`status`),
  FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='短信模板表';

-- ============================================
-- 2. API密钥表（P0-2）
-- ============================================
CREATE TABLE IF NOT EXISTS `api_keys` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '密钥ID',
  `account_id` INT UNSIGNED NOT NULL COMMENT '账户ID',
  `key_name` VARCHAR(100) NOT NULL COMMENT '密钥名称',
  `api_key` VARCHAR(64) NOT NULL UNIQUE COMMENT 'API Key',
  `api_secret` VARCHAR(128) NOT NULL COMMENT 'API Secret（加密存储）',
  `permission` ENUM('read_only', 'read_write', 'full') NOT NULL DEFAULT 'read_write' COMMENT '权限级别',
  `ip_whitelist` JSON COMMENT 'IP白名单（JSON数组）',
  `rate_limit` INT DEFAULT 1000 COMMENT '每分钟请求限制',
  `status` ENUM('active', 'disabled', 'expired') NOT NULL DEFAULT 'active' COMMENT '密钥状态',
  `usage_count` INT DEFAULT 0 COMMENT '使用次数',
  `last_used_at` TIMESTAMP NULL COMMENT '最后使用时间',
  `last_used_ip` VARCHAR(50) COMMENT '最后使用IP',
  `expires_at` TIMESTAMP NULL COMMENT '过期时间',
  `description` TEXT COMMENT '密钥描述',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '软删除标记',
  PRIMARY KEY (`id`),
  INDEX `idx_account_id` (`account_id`),
  INDEX `idx_api_key` (`api_key`),
  INDEX `idx_status` (`status`),
  FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='API密钥表';

-- ============================================
-- 3. 批量发送表（P1-1）
-- ============================================
DROP TABLE IF EXISTS `sms_batches`;
CREATE TABLE `sms_batches` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '批次ID',
  `account_id` INT UNSIGNED NOT NULL COMMENT '账户ID',
  `batch_name` VARCHAR(200) NOT NULL COMMENT '批次名称',
  `template_id` INT COMMENT '使用的模板ID',
  `file_path` VARCHAR(500) COMMENT '上传的CSV文件路径',
  `file_size` INT COMMENT '文件大小（字节）',
  `total_count` INT DEFAULT 0 COMMENT '总条数',
  `success_count` INT DEFAULT 0 COMMENT '成功数',
  `failed_count` INT DEFAULT 0 COMMENT '失败数',
  `processing_count` INT DEFAULT 0 COMMENT '处理中数',
  `status` ENUM('pending', 'processing', 'completed', 'failed', 'cancelled') NOT NULL DEFAULT 'pending' COMMENT '批次状态',
  `error_message` TEXT COMMENT '错误信息',
  `error_details` JSON COMMENT '详细错误列表',
  `sender_id` VARCHAR(20) COMMENT '发送方ID',
  `send_config` JSON COMMENT '发送配置',
  `progress` INT DEFAULT 0 COMMENT '进度百分比 0-100',
  `started_at` TIMESTAMP NULL COMMENT '开始处理时间',
  `completed_at` TIMESTAMP NULL COMMENT '完成时间',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '软删除标记',
  PRIMARY KEY (`id`),
  INDEX `idx_account_id` (`account_id`),
  INDEX `idx_status` (`status`),
  INDEX `idx_created_at` (`created_at`),
  FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='批量发送任务表';

-- ============================================
-- 4. 通知表（P1-3）
-- ============================================
CREATE TABLE IF NOT EXISTS `notifications` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '通知ID',
  `account_id` INT UNSIGNED NOT NULL COMMENT '账户ID',
  `type` ENUM('system', 'balance', 'send_fail', 'batch_complete', 'security') NOT NULL COMMENT '通知类型',
  `title` VARCHAR(200) NOT NULL COMMENT '通知标题',
  `content` TEXT NOT NULL COMMENT '通知内容',
  `priority` ENUM('low', 'medium', 'high', 'urgent') DEFAULT 'medium' COMMENT '优先级',
  `is_read` BOOLEAN DEFAULT FALSE COMMENT '是否已读',
  `read_at` TIMESTAMP NULL COMMENT '阅读时间',
  `related_id` INT COMMENT '关联业务ID',
  `related_type` VARCHAR(50) COMMENT '关联业务类型',
  `action_url` VARCHAR(500) COMMENT '操作链接',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `expires_at` TIMESTAMP NULL COMMENT '过期时间',
  PRIMARY KEY (`id`),
  INDEX `idx_account_id` (`account_id`),
  INDEX `idx_is_read` (`is_read`),
  INDEX `idx_created_at` (`created_at`),
  FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统通知表';

-- ============================================
-- 5. 账户设置表（P1-2）
-- ============================================
CREATE TABLE IF NOT EXISTS `account_settings` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '设置ID',
  `account_id` INT UNSIGNED NOT NULL UNIQUE COMMENT '账户ID',
  `balance_alert` BOOLEAN DEFAULT TRUE COMMENT '余额提醒',
  `balance_threshold` DECIMAL(12,4) DEFAULT 100.0000 COMMENT '余额阈值',
  `send_fail_alert` BOOLEAN DEFAULT TRUE COMMENT '发送失败提醒',
  `batch_complete_alert` BOOLEAN DEFAULT TRUE COMMENT '批量完成提醒',
  `email_notify` BOOLEAN DEFAULT TRUE COMMENT '邮件通知',
  `telegram_notify` BOOLEAN DEFAULT FALSE COMMENT 'Telegram通知',
  `webhook_url` VARCHAR(500) COMMENT 'Webhook回调地址',
  `webhook_secret` VARCHAR(100) COMMENT 'Webhook密钥',
  `timezone` VARCHAR(50) DEFAULT 'Asia/Shanghai' COMMENT '时区',
  `language` VARCHAR(10) DEFAULT 'zh-CN' COMMENT '语言',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  INDEX `idx_account_id` (`account_id`),
  FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='账户设置表';

-- ============================================
-- 6. 权限与索引优化
-- ============================================

-- 为高频查询添加复合索引（忽略重复错误）
CREATE INDEX `idx_templates_account_status` ON `sms_templates`(`account_id`, `status`);
CREATE INDEX `idx_batches_account_status` ON `sms_batches`(`account_id`, `status`);
CREATE INDEX `idx_apikeys_account_status` ON `api_keys`(`account_id`, `status`);

-- ============================================
-- 迁移完成
-- ============================================
SELECT 'Phase 5 P0-P2 Migration Completed!' AS Status;
