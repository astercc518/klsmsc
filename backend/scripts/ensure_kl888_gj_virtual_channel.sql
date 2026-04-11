-- 确保 KL_888_GJ 虚拟通道存在，并配置全球（*）路由与单价 0
-- 依赖：channels.protocol 含 VIRTUAL；routing_rules / country_pricing 表存在

SET @code := 'KL_888_GJ';
SET @vconf := '{"delivery_rate_min":80.0,"delivery_rate_max":90.0,"fail_rate_min":5.0,"fail_rate_max":15.0,"dlr_delay_min":3,"dlr_delay_max":30,"fail_codes":["UNDELIV"]}';

INSERT INTO channels (
  channel_code, channel_name, protocol,
  host, port, username, password, api_url, api_key,
  default_sender_id, cost_rate,
  max_tps, concurrency, rate_control_window,
  priority, weight, status, is_deleted,
  virtual_config
)
SELECT
  @code,
  'KL_888 国际虚拟通道',
  'VIRTUAL',
  NULL, NULL, NULL, NULL, NULL, NULL,
  'KL888',
  0.0000,
  100, 1, 1000,
  0, 100, 'active', 0,
  @vconf
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM channels WHERE channel_code = @code AND is_deleted = 0);

UPDATE channels
SET
  channel_name = 'KL_888 国际虚拟通道',
  protocol = 'VIRTUAL',
  virtual_config = @vconf,
  default_sender_id = 'KL888',
  cost_rate = 0.0000,
  status = 'active',
  is_deleted = 0
WHERE channel_code = @code;

SET @cid := (SELECT id FROM channels WHERE channel_code = @code LIMIT 1);

-- 全球路由（* 匹配任意国家，需应用支持通配符路由）
DELETE FROM routing_rules WHERE channel_id = @cid AND country_code = '*';
INSERT INTO routing_rules (channel_id, country_code, priority, is_active)
VALUES (@cid, '*', 0, 1);

-- 全球销售单价 0
DELETE FROM country_pricing WHERE channel_id = @cid AND country_code = '*';
INSERT INTO country_pricing (channel_id, country_code, country_name, price_per_sms, currency)
VALUES (@cid, '*', '全球', 0.0000, 'USD');

SELECT @cid AS channel_id, 'KL_888_GJ configured' AS message;
