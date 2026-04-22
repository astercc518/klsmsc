-- sms_logs：加速 DLR 按 upstream_message_id 更新（与 Alembic z9y8x7w6v5u4 等价）
-- message_id 在业务库上通常为 UNIQUE，已自带 B-Tree，无需重复建索引。
-- 建议在低峰执行；大表可用 ALGORITHM=INPLACE, LOCK=NONE（视 MySQL 版本与表引擎而定）。

CREATE INDEX idx_sms_logs_upstream_message_id ON sms_logs (upstream_message_id);
