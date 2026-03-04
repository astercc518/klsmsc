-- Phase 3 Migration Script

-- 1. Extend invitation_codes with pricing_config
-- Check if column exists first to avoid error (using a simple add, might fail if exists but ok for dev)
ALTER TABLE invitation_codes ADD COLUMN pricing_config JSON COMMENT '定价配置(JSON)';

-- 2. Create account_pricing table
CREATE TABLE IF NOT EXISTS account_pricing (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    account_id INT UNSIGNED NOT NULL COMMENT '账户ID',
    country_code VARCHAR(10) NOT NULL COMMENT '国家代码',
    business_type VARCHAR(20) NOT NULL DEFAULT 'sms' COMMENT '业务类型: sms/voice',
    price DECIMAL(10, 4) NOT NULL COMMENT '单价',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_account_country (account_id, country_code, business_type),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Create telegram_bindings table
CREATE TABLE IF NOT EXISTS telegram_bindings (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    tg_id BIGINT NOT NULL COMMENT 'Telegram User ID',
    account_id INT UNSIGNED NOT NULL COMMENT '账户ID',
    is_active TINYINT(1) DEFAULT 0 COMMENT '是否当前活跃账户',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tg_account (tg_id, account_id),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Create index for tg_id queries
CREATE INDEX idx_tg_id ON telegram_bindings(tg_id);

-- 4. Create sms_batches table
CREATE TABLE IF NOT EXISTS sms_batches (
    id VARCHAR(64) PRIMARY KEY COMMENT '批次ID',
    account_id INT UNSIGNED NOT NULL,
    file_path VARCHAR(255) COMMENT '号码文件路径',
    content TEXT COMMENT '发送内容',
    total_count INT DEFAULT 0 COMMENT '总条数',
    valid_count INT DEFAULT 0 COMMENT '有效号码数',
    total_cost DECIMAL(12, 4) DEFAULT 0 COMMENT '总费用',
    status ENUM('pending_audit', 'approved', 'rejected', 'sending', 'completed', 'failed') DEFAULT 'pending_audit',
    audit_by INT UNSIGNED COMMENT '审核人ID',
    audit_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. Create sms_templates table (Allowlist)
CREATE TABLE IF NOT EXISTS sms_templates (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    account_id INT UNSIGNED NOT NULL,
    content_hash VARCHAR(64) NOT NULL COMMENT '内容哈希(SHA256)',
    content_text TEXT COMMENT '内容原文',
    status ENUM('approved', 'rejected') DEFAULT 'approved',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_account_hash (account_id, content_hash),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. Clean up telegram_users table if necessary
-- For now, we keep it as a "Profile" table, but we might want to drop the unique constraint on account_id
-- or just ignore account_id in it. 
-- Let's make account_id nullable in telegram_users to allow binding via telegram_bindings primarily.
ALTER TABLE telegram_users MODIFY COLUMN account_id INT UNSIGNED NULL;
-- Drop the unique index on account_id if it exists to allow 1-to-N logic migration
-- (Need to check index name, usually uk_something or index_name)
-- We will handle this logic in code for now: use telegram_bindings for auth lookup.
