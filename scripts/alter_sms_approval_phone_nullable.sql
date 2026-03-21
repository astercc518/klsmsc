-- 短信审核表 phone_number 改为可空（只审核文案时无需号码）
USE sms_system;

ALTER TABLE sms_content_approvals
MODIFY COLUMN phone_number VARCHAR(50) NULL
COMMENT '目标号码，只审核文案时为空';
