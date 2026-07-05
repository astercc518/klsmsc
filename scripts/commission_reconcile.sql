-- 佣金二次加权对账（审计 P0-1 / P0-2）
--
-- 背景：sms_logs.profit 是生成列(selling_price - cost_price)，而 selling/cost 入库时已是
--       "单价 × message_count" 的整条总价，故 profit 已是整条(含分段)总利润。佣金/业绩聚合曾误写
--       SUM(profit * message_count)，对多段短信按段数二次加权。代码已修(internal_bot.py / admin.py /
--       batch_inspector.py 四处)，本脚本重算历史差额供财务核销。
--
-- 用法（务必低峰执行，全表聚合较重）：
--   docker exec smsc-mysql mysql -uroot -p<PW> sms_system < scripts/commission_reconcile.sql
--
-- 首次运行结果（2026-03-01 起，截至 2026-07 初）：全部销售业绩总高估 133.41，佣金多发合计 ≈ 13.34
--   —— 因本节点流量 99.97% 为单段短信(message_count=1，二次加权无影响)，实际多发极小。

SET SESSION time_zone = '+08:00';

-- 按销售汇总的佣金多发（仅 message_count>1 的多段短信有差额；排除虚拟通道 protocol='VIRTUAL'）
SELECT
  a.sales_id,
  au.username                                              AS sales,
  au.role,
  au.commission_rate                                       AS rate_pct,
  SUM(t.cnt)                                               AS multiseg_rows,
  ROUND(SUM(t.overstate), 2)                               AS perf_overstate,
  ROUND(SUM(t.overstate) * au.commission_rate / 100, 2)   AS commission_overpaid
FROM (
  -- 先按 account_id 预聚合(避免 1600w 行直接三表 join)
  SELECT account_id,
         SUM(profit * (message_count - 1)) AS overstate,
         COUNT(*)                          AS cnt
  FROM sms_logs
  WHERE status = 'delivered'
    AND submit_time >= '2026-03-01'         -- 触发分区裁剪；按需调整起始
    AND message_count > 1
    AND channel_id NOT IN (SELECT id FROM channels WHERE protocol = 'VIRTUAL')
  GROUP BY account_id
) t
JOIN accounts a      ON t.account_id = a.id
JOIN admin_users au  ON a.sales_id = au.id
GROUP BY a.sales_id, au.username, au.role, au.commission_rate
HAVING perf_overstate <> 0
ORDER BY commission_overpaid DESC;
