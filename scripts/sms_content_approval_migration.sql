-- 短信内容审核表迁移
-- 客户通过业务助手发送的短信需转发到供应商群审核，通过后才实际发送

USE sms_system;

CREATE TABLE IF NOT EXISTS `sms_content_approvals` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `approval_no` VARCHAR(50) NOT NULL COMMENT '审核单号',
  `account_id` INT UNSIGNED NOT NULL COMMENT '账户ID',
  `tg_user_id` VARCHAR(50) NOT NULL COMMENT 'Telegram用户ID',
  `phone_number` VARCHAR(50) NOT NULL COMMENT '目标号码',
  `content` TEXT NOT NULL COMMENT '短信内容',
  `status` ENUM('pending', 'approved', 'rejected') NOT NULL DEFAULT 'pending' COMMENT '状态',
  `forwarded_to_group` VARCHAR(50) DEFAULT NULL COMMENT '转发到的TG群组ID',
  `forwarded_message_id` INT DEFAULT NULL COMMENT '转发消息的Message ID',
  `reviewed_at` TIMESTAMP NULL DEFAULT NULL COMMENT '审核时间',
  `reviewed_by_name` VARCHAR(100) DEFAULT NULL COMMENT '审核人名称',
  `review_note` VARCHAR(500) DEFAULT NULL COMMENT '审核备注/拒绝原因',
  `message_id` VARCHAR(100) DEFAULT NULL COMMENT '发送成功后的消息ID',
  `send_error` TEXT DEFAULT NULL COMMENT '发送失败时的错误信息',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_approval_no` (`approval_no`),
  KEY `idx_account_status` (`account_id`, `status`),
  KEY `idx_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='短信内容审核表';

-- 添加配置项：是否启用短信内容审核（默认true）
INSERT IGNORE INTO `system_config` (`config_key`, `config_value`, `config_type`, `category`, `description`)
VALUES ('telegram_enable_sms_content_review', 'true', 'boolean', 'telegram', '业务助手短信发送是否需要供应商群审核');
