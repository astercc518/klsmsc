-- 手动执行迁移：添加通道连接状态字段
-- 对应 alembic 版本 002
-- 若已通过 alembic upgrade head 执行，请勿重复运行此脚本
-- 执行前请确认 channels 表存在，且 connection_status 字段尚不存在

ALTER TABLE channels ADD COLUMN connection_status VARCHAR(20) NULL COMMENT '连接状态：online=正常 offline=异常 unknown=未检测';
ALTER TABLE channels ADD COLUMN connection_checked_at TIMESTAMP NULL COMMENT '最后检测时间';
