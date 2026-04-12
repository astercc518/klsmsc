-- 注水子系统建表脚本（MySQL 8.0）
-- 与 app.modules.water.models 保持一致

USE sms_system;

-- 代理池
CREATE TABLE IF NOT EXISTS `water_proxies` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `name` VARCHAR(100) NOT NULL COMMENT '代理名称',
  `proxy_type` ENUM('http', 'https', 'socks5') NOT NULL DEFAULT 'http' COMMENT '代理协议类型',
  `endpoint` VARCHAR(500) NOT NULL COMMENT '代理地址',
  `country_code` VARCHAR(5) NOT NULL DEFAULT '*' COMMENT '目标国家代码',
  `country_auto` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否支持占位符自动替换',
  `max_concurrency` INT NOT NULL DEFAULT 10 COMMENT '最大并发数',
  `status` ENUM('active', 'inactive', 'testing') NOT NULL DEFAULT 'active' COMMENT '状态',
  `last_test_at` TIMESTAMP NULL DEFAULT NULL COMMENT '最近检测时间',
  `last_test_result` VARCHAR(200) NULL DEFAULT NULL COMMENT '最近检测结果摘要',
  `remark` TEXT NULL COMMENT '备注',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='注水-代理池';

-- 注水任务配置（每客户账户一条）
CREATE TABLE IF NOT EXISTS `water_task_configs` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `account_id` INT NOT NULL COMMENT '关联客户账户 ID',
  `enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否启用注水任务',
  `click_rate_min` DECIMAL(5, 2) NOT NULL DEFAULT 3.00 COMMENT '点击率下限(%)',
  `click_rate_max` DECIMAL(5, 2) NOT NULL DEFAULT 8.00 COMMENT '点击率上限(%)',
  `click_delay_min` INT NOT NULL DEFAULT 60 COMMENT '点击延迟下限(秒)',
  `click_delay_max` INT NOT NULL DEFAULT 1800 COMMENT '点击延迟上限(秒)',
  `register_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否启用注册注水',
  `register_rate_min` DECIMAL(5, 2) NOT NULL DEFAULT 1.00 COMMENT '注册率下限(%)',
  `register_rate_max` DECIMAL(5, 2) NOT NULL DEFAULT 3.00 COMMENT '注册率上限(%)',
  `proxy_id` INT NULL DEFAULT NULL COMMENT '关联代理 ID',
  `user_agent_type` ENUM('mobile', 'desktop', 'random') NOT NULL DEFAULT 'mobile' COMMENT 'User-Agent 类型',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_account` (`account_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='注水-任务配置';

-- 按域名的注册脚本
CREATE TABLE IF NOT EXISTS `water_register_scripts` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `name` VARCHAR(100) NOT NULL COMMENT '脚本名称',
  `domain` VARCHAR(255) NOT NULL COMMENT '目标域名（唯一）',
  `steps` TEXT NULL COMMENT '步骤定义（JSON 字符串）',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `success_count` INT NOT NULL DEFAULT 0 COMMENT '成功次数',
  `fail_count` INT NOT NULL DEFAULT 0 COMMENT '失败次数',
  `last_run_at` TIMESTAMP NULL DEFAULT NULL COMMENT '最近执行时间',
  `remark` TEXT NULL COMMENT '备注',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_water_register_scripts_domain` (`domain`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='注水-注册脚本';

-- 注水执行流水
CREATE TABLE IF NOT EXISTS `water_injection_logs` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `sms_log_id` BIGINT NOT NULL COMMENT '关联短信记录 ID',
  `account_id` INT NULL DEFAULT NULL COMMENT '客户账户 ID',
  `batch_id` INT NULL DEFAULT NULL COMMENT '批次 ID',
  `channel_id` INT NOT NULL COMMENT '通道 ID',
  `task_config_id` INT NULL DEFAULT NULL COMMENT '任务配置 ID',
  `url` VARCHAR(1000) NOT NULL COMMENT '目标 URL',
  `action` ENUM('click', 'register') NOT NULL COMMENT '动作类型',
  `status` ENUM('pending', 'processing', 'success', 'failed') NOT NULL DEFAULT 'pending' COMMENT '执行状态',
  `proxy_id` INT NULL DEFAULT NULL COMMENT '使用的代理 ID',
  `proxy_ip` VARCHAR(50) NULL DEFAULT NULL COMMENT '代理出口 IP',
  `proxy_country` VARCHAR(5) NULL DEFAULT NULL COMMENT '代理国家代码',
  `duration_ms` INT NULL DEFAULT NULL COMMENT '耗时(毫秒)',
  `error_message` TEXT NULL COMMENT '错误信息',
  `screenshot_path` VARCHAR(500) NULL DEFAULT NULL COMMENT '截图存储路径',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='注水-执行流水';
