-- 为 balance_logs 添加 refund_recharge 类型（退补充值，不计算业绩、不核算成本）
-- 执行: mysql -u root -p sms_system < scripts/add_refund_recharge.sql

USE sms_system;

-- MySQL 修改 ENUM 需要重新定义整个枚举
ALTER TABLE `balance_logs` 
MODIFY COLUMN `change_type` ENUM('charge', 'refund', 'deposit', 'withdraw', 'adjustment', 'refund_recharge') NOT NULL COMMENT '变动类型';
