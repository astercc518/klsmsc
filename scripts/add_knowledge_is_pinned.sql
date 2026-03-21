-- 业务知识库：添加置顶字段
-- 执行前请确认 knowledge_articles 表已存在
-- 若列已存在会报错，可忽略

ALTER TABLE knowledge_articles ADD COLUMN is_pinned INT DEFAULT 0 COMMENT '是否置顶：0否 1是';
