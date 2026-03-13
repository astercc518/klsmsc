-- 工单表 created_by_id、closed_by 改为 BIGINT，以支持 Telegram 用户 ID（64位）
USE sms_system;

ALTER TABLE tickets
MODIFY COLUMN created_by_id BIGINT NULL
COMMENT '创建人ID(账户/管理员/Telegram用户ID)';

ALTER TABLE tickets
MODIFY COLUMN closed_by BIGINT NULL
COMMENT '关闭人ID';
