-- =============================================================================
-- 历史数据补录：短信审核（业务助手）已通过/已拒绝，但 tickets 仍为待处理等状态
-- 适用：MySQL 5.7+（JSON 函数）
-- 执行前请先备份 tickets / sms_content_approvals 表，并在事务中执行。
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1) 预览：将受影响的工单（审核已通过，工单未完结）
-- -----------------------------------------------------------------------------
SELECT
    t.id AS ticket_id,
    t.ticket_no,
    t.title,
    t.status AS ticket_status,
    t.review_status AS ticket_review_status,
    a.id AS approval_id,
    a.approval_no,
    a.status AS approval_status,
    a.reviewed_at,
    a.reviewed_by_name
FROM tickets t
INNER JOIN sms_content_approvals a ON a.account_id = t.account_id
    AND (
        CAST(
            JSON_UNQUOTE(JSON_EXTRACT(t.extra_data, '$.sms_approval_id')) AS UNSIGNED
        ) = a.id
        OR (
            t.title IS NOT NULL
            AND a.approval_no IS NOT NULL
            AND t.title LIKE CONCAT('%', a.approval_no, '%')
        )
    )
WHERE t.ticket_type = 'test'
  AND a.status = 'approved'
  AND t.status IN ('open', 'assigned', 'in_progress', 'pending_user');

-- -----------------------------------------------------------------------------
-- 2) 预览：审核已拒绝，工单仍为待处理等
-- -----------------------------------------------------------------------------
SELECT
    t.id AS ticket_id,
    t.ticket_no,
    t.title,
    t.status AS ticket_status,
    a.approval_no,
    a.status AS approval_status
FROM tickets t
INNER JOIN sms_content_approvals a ON a.account_id = t.account_id
    AND (
        CAST(
            JSON_UNQUOTE(JSON_EXTRACT(t.extra_data, '$.sms_approval_id')) AS UNSIGNED
        ) = a.id
        OR (
            t.title IS NOT NULL
            AND a.approval_no IS NOT NULL
            AND t.title LIKE CONCAT('%', a.approval_no, '%')
        )
    )
WHERE t.ticket_type = 'test'
  AND a.status = 'rejected'
  AND t.status IN ('open', 'assigned', 'in_progress', 'pending_user');

-- =============================================================================
-- 3) 执行补录（请先确认上面 SELECT 结果无误后再执行）
-- =============================================================================

START TRANSACTION;

-- 已通过 → 工单标为已解决
UPDATE tickets t
INNER JOIN sms_content_approvals a ON a.account_id = t.account_id
    AND (
        CAST(
            JSON_UNQUOTE(JSON_EXTRACT(t.extra_data, '$.sms_approval_id')) AS UNSIGNED
        ) = a.id
        OR (
            t.title IS NOT NULL
            AND a.approval_no IS NOT NULL
            AND t.title LIKE CONCAT('%', a.approval_no, '%')
        )
    )
SET
    t.review_status = 'approved',
    t.reviewed_at = COALESCE(t.reviewed_at, a.reviewed_at, NOW()),
    t.review_note = CONCAT(
        '业务助手审核通过（历史补录）',
        IF(a.reviewed_by_name IS NOT NULL AND a.reviewed_by_name != '', CONCAT(' — ', a.reviewed_by_name), '')
    ),
    t.status = 'resolved',
    t.resolved_at = COALESCE(t.resolved_at, a.reviewed_at, NOW()),
    t.resolution = CONCAT(
        '短信内容审核已通过（供应商，历史补录）。审核人: ',
        IFNULL(a.reviewed_by_name, '-')
    )
WHERE t.ticket_type = 'test'
  AND a.status = 'approved'
  AND t.status IN ('open', 'assigned', 'in_progress', 'pending_user');

-- 已拒绝 → 工单标为已关闭
UPDATE tickets t
INNER JOIN sms_content_approvals a ON a.account_id = t.account_id
    AND (
        CAST(
            JSON_UNQUOTE(JSON_EXTRACT(t.extra_data, '$.sms_approval_id')) AS UNSIGNED
        ) = a.id
        OR (
            t.title IS NOT NULL
            AND a.approval_no IS NOT NULL
            AND t.title LIKE CONCAT('%', a.approval_no, '%')
        )
    )
SET
    t.review_status = 'rejected',
    t.reviewed_at = COALESCE(t.reviewed_at, a.reviewed_at, NOW()),
    t.review_note = CONCAT(
        '业务助手审核拒绝（历史补录）',
        IF(a.reviewed_by_name IS NOT NULL AND a.reviewed_by_name != '', CONCAT(' — ', a.reviewed_by_name), '')
    ),
    t.status = 'closed',
    t.closed_at = COALESCE(t.closed_at, a.reviewed_at, NOW())
WHERE t.ticket_type = 'test'
  AND a.status = 'rejected'
  AND t.status IN ('open', 'assigned', 'in_progress', 'pending_user');

-- 确认行数与预期一致后再提交；否则 ROLLBACK;
COMMIT;

-- =============================================================================
-- 单条工单手工补录示例（按工单号，按需改 TK... / SA...）
-- =============================================================================
/*
UPDATE tickets t
INNER JOIN sms_content_approvals a
    ON a.approval_no = 'SA2026032514564824D5'
    AND (
        CAST(JSON_UNQUOTE(JSON_EXTRACT(t.extra_data, '$.sms_approval_id')) AS UNSIGNED) = a.id
        OR t.title LIKE CONCAT('%', a.approval_no, '%')
    )
    AND t.account_id = a.account_id
SET
    t.review_status = 'approved',
    t.reviewed_at = COALESCE(t.reviewed_at, a.reviewed_at, NOW()),
    t.status = 'resolved',
    t.resolved_at = COALESCE(t.resolved_at, a.reviewed_at, NOW()),
    t.resolution = CONCAT('短信内容审核已通过（手工补录）。审核人: ', IFNULL(a.reviewed_by_name, '-'))
WHERE t.ticket_no = 'TK202603251456481a3c'
  AND a.status = 'approved';
*/
