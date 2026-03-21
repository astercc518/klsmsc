-- Phase 5 P2: P2功能数据库迁移脚本
-- 创建时间: 2026-01-26
-- 说明: 定时发送、子账户、套餐、安全中心

-- ============================================
-- 1. 定时发送任务表（P2-1）
-- ============================================
CREATE TABLE IF NOT EXISTS `scheduled_tasks` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '任务ID',
  `account_id` INT UNSIGNED NOT NULL COMMENT '账户ID',
  `task_name` VARCHAR(200) NOT NULL COMMENT '任务名称',
  `template_id` INT COMMENT '模板ID',
  `phone_numbers` JSON NOT NULL COMMENT '手机号列表（JSON）',
  `content` TEXT COMMENT '短信内容（如不使用模板）',
  `sender_id` VARCHAR(20) COMMENT '发送方ID',
  `frequency` ENUM('once', 'daily', 'weekly', 'monthly') NOT NULL DEFAULT 'once' COMMENT '执行频率',
  `scheduled_time` TIMESTAMP NOT NULL COMMENT '计划执行时间',
  `last_run_time` TIMESTAMP NULL COMMENT '上次执行时间',
  `next_run_time` TIMESTAMP NULL COMMENT '下次执行时间',
  `repeat_config` JSON COMMENT '重复配置',
  `status` ENUM('pending', 'running', 'completed', 'failed', 'cancelled') NOT NULL DEFAULT 'pending' COMMENT '任务状态',
  `total_runs` INT DEFAULT 0 COMMENT '总执行次数',
  `success_runs` INT DEFAULT 0 COMMENT '成功次数',
  `failed_runs` INT DEFAULT 0 COMMENT '失败次数',
  `last_error` TEXT COMMENT '最后错误信息',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '软删除标记',
  PRIMARY KEY (`id`),
  INDEX `idx_account_id` (`account_id`),
  INDEX `idx_status` (`status`),
  INDEX `idx_scheduled_time` (`scheduled_time`),
  FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='定时发送任务表';

-- ============================================
-- 2. 子账户表（P2-2）
-- ============================================
CREATE TABLE IF NOT EXISTS `sub_accounts` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '子账户ID',
  `parent_account_id` INT UNSIGNED NOT NULL COMMENT '父账户ID',
  `username` VARCHAR(100) NOT NULL UNIQUE COMMENT '用户名',
  `email` VARCHAR(255) COMMENT '邮箱',
  `password_hash` VARCHAR(255) NOT NULL COMMENT '密码哈希',
  `role` ENUM('viewer', 'operator', 'manager') NOT NULL DEFAULT 'operator' COMMENT '角色',
  `permissions` JSON COMMENT '详细权限配置',
  `status` ENUM('active', 'suspended', 'disabled') NOT NULL DEFAULT 'active' COMMENT '状态',
  `rate_limit` INT COMMENT '请求频率限制',
  `daily_limit` INT COMMENT '每日发送限制',
  `ip_whitelist` JSON COMMENT 'IP白名单',
  `total_sent` INT DEFAULT 0 COMMENT '总发送数',
  `last_login_at` TIMESTAMP NULL COMMENT '最后登录时间',
  `last_login_ip` VARCHAR(50) COMMENT '最后登录IP',
  `description` VARCHAR(500) COMMENT '备注',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '软删除标记',
  PRIMARY KEY (`id`),
  INDEX `idx_parent_account` (`parent_account_id`),
  INDEX `idx_username` (`username`),
  INDEX `idx_status` (`status`),
  FOREIGN KEY (`parent_account_id`) REFERENCES `accounts`(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='子账户表';

-- ============================================
-- 3. 套餐管理表（P2-3）
-- ============================================
CREATE TABLE IF NOT EXISTS `packages` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '套餐ID',
  `package_name` VARCHAR(200) NOT NULL COMMENT '套餐名称',
  `package_type` ENUM('sms_bundle', 'time_based', 'prepaid', 'postpaid') NOT NULL COMMENT '套餐类型',
  `description` TEXT COMMENT '套餐描述',
  `price` DECIMAL(12,4) NOT NULL COMMENT '价格',
  `currency` VARCHAR(10) DEFAULT 'USD' COMMENT '货币',
  `sms_quota` INT COMMENT '短信条数',
  `validity_days` INT COMMENT '有效期（天）',
  `features` JSON COMMENT '功能列表',
  `rate_limit` INT COMMENT '频率限制',
  `discount_percent` DECIMAL(5,2) COMMENT '折扣百分比',
  `status` ENUM('active', 'inactive', 'archived') NOT NULL DEFAULT 'active' COMMENT '状态',
  `sort_order` INT DEFAULT 0 COMMENT '排序顺序',
  `is_featured` BOOLEAN DEFAULT FALSE COMMENT '是否推荐',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '软删除标记',
  PRIMARY KEY (`id`),
  INDEX `idx_status` (`status`),
  INDEX `idx_type` (`package_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='套餐定义表';

CREATE TABLE IF NOT EXISTS `account_packages` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `account_id` INT UNSIGNED NOT NULL COMMENT '账户ID',
  `package_id` INT NOT NULL COMMENT '套餐ID',
  `sms_used` INT DEFAULT 0 COMMENT '已使用短信数',
  `sms_remaining` INT COMMENT '剩余短信数',
  `start_date` TIMESTAMP NOT NULL COMMENT '开始日期',
  `end_date` TIMESTAMP NOT NULL COMMENT '结束日期',
  `is_active` BOOLEAN DEFAULT TRUE COMMENT '是否激活',
  `purchase_price` DECIMAL(12,4) COMMENT '购买价格',
  `order_id` VARCHAR(100) COMMENT '订单ID',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  INDEX `idx_account_id` (`account_id`),
  INDEX `idx_package_id` (`package_id`),
  INDEX `idx_is_active` (`is_active`),
  FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`),
  FOREIGN KEY (`package_id`) REFERENCES `packages`(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='账户套餐关联表';

-- ============================================
-- 4. 安全日志表（P2-4）
-- ============================================
CREATE TABLE IF NOT EXISTS `security_logs` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '日志ID',
  `account_id` INT UNSIGNED COMMENT '账户ID',
  `event_type` ENUM('login', 'login_failed', 'logout', 'password_change', 'api_key_create', 'api_key_delete', 'permission_change', 'suspicious_activity', 'ip_blocked', 'rate_limit_exceeded') NOT NULL COMMENT '事件类型',
  `level` ENUM('info', 'warning', 'danger', 'critical') NOT NULL DEFAULT 'info' COMMENT '安全级别',
  `title` VARCHAR(200) NOT NULL COMMENT '标题',
  `description` TEXT COMMENT '描述',
  `details` JSON COMMENT '详细数据',
  `ip_address` VARCHAR(50) COMMENT 'IP地址',
  `user_agent` VARCHAR(500) COMMENT 'User Agent',
  `location` VARCHAR(200) COMMENT '地理位置',
  `related_id` INT COMMENT '关联业务ID',
  `related_type` VARCHAR(50) COMMENT '关联业务类型',
  `is_resolved` BOOLEAN DEFAULT FALSE COMMENT '是否已处理',
  `resolved_at` TIMESTAMP NULL COMMENT '处理时间',
  `resolved_by` INT COMMENT '处理人ID',
  `resolution_note` TEXT COMMENT '处理备注',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  INDEX `idx_account_id` (`account_id`),
  INDEX `idx_event_type` (`event_type`),
  INDEX `idx_level` (`level`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='安全日志表';

CREATE TABLE IF NOT EXISTS `login_attempts` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `username` VARCHAR(100) COMMENT '用户名',
  `ip_address` VARCHAR(50) COMMENT 'IP地址',
  `success` BOOLEAN NOT NULL COMMENT '是否成功',
  `failure_reason` VARCHAR(200) COMMENT '失败原因',
  `user_agent` VARCHAR(500) COMMENT 'User Agent',
  `attempted_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '尝试时间',
  PRIMARY KEY (`id`),
  INDEX `idx_username` (`username`),
  INDEX `idx_ip_address` (`ip_address`),
  INDEX `idx_attempted_at` (`attempted_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='登录尝试记录表';

-- ============================================
-- 5. 插入示例套餐数据
-- ============================================
INSERT INTO `packages` (`package_name`, `package_type`, `description`, `price`, `sms_quota`, `validity_days`, `status`, `sort_order`, `is_featured`) VALUES
('基础套餐', 'sms_bundle', '适合个人和小型企业，包含1000条短信', 50.0000, 1000, 30, 'active', 1, FALSE),
('标准套餐', 'sms_bundle', '适合中小企业，包含5000条短信', 200.0000, 5000, 30, 'active', 2, TRUE),
('专业套餐', 'sms_bundle', '适合大型企业，包含20000条短信', 700.0000, 20000, 90, 'active', 3, TRUE),
('企业套餐', 'sms_bundle', '适合超大规模使用，包含100000条短信', 3000.0000, 100000, 180, 'active', 4, FALSE);

-- ============================================
-- 迁移完成
-- ============================================
SELECT 'Phase 5 P2 Migration Completed!' AS Status;
