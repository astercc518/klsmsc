-- 手动绑定 Telegram 用户到账户
-- 用法: 修改下面的变量后执行
-- mysql -u smsuser -p sms_system < scripts/bind_telegram_to_account.sql

USE sms_system;

-- 设置变量（请修改为实际值）
-- tg_id: 用户的 Telegram 用户 ID（可用 @userinfobot 获取）
-- account_id: 要绑定的账户 ID

SET @tg_id = 6650783812;   -- 替换为实际 Telegram 用户 ID
SET @account_id = 17;       -- 替换为实际账户 ID

-- 先将该 tg_id 的其他绑定设为非活跃
UPDATE telegram_bindings SET is_active = 0 WHERE tg_id = @tg_id;

-- 插入或更新绑定（uk_tg_account 唯一键）
INSERT INTO telegram_bindings (tg_id, account_id, is_active)
VALUES (@tg_id, @account_id, 1)
ON DUPLICATE KEY UPDATE is_active = 1;

-- 验证
SELECT tb.id, tb.tg_id, tb.account_id, tb.is_active, a.account_name 
FROM telegram_bindings tb 
JOIN accounts a ON tb.account_id = a.id 
WHERE tb.tg_id = @tg_id;
