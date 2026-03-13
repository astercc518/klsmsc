-- 供应商表增加 Telegram 群组 ID 字段
-- 用于短信审核转发到对应供应商群，可替代全局 TELEGRAM_ADMIN_GROUP_ID

USE sms_system;

-- 若列已存在可忽略错误
ALTER TABLE suppliers
ADD COLUMN telegram_group_id VARCHAR(50) NULL
COMMENT 'Telegram群组ID，用于短信审核转发，如 -1001234567890'
AFTER supplier_group;
