-- 数据业务模块迁移脚本
-- 执行顺序: 在 init_db.sql 之后运行

-- 1. 号码资源池
CREATE TABLE IF NOT EXISTS data_numbers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL COMMENT '手机号码(E.164格式)',
    country_code VARCHAR(10) NOT NULL COMMENT '国家代码',
    tags JSON COMMENT '标签列表(JSON数组)',
    status ENUM('active','inactive','unknown','blacklisted') DEFAULT 'unknown' COMMENT '号码状态',
    carrier VARCHAR(50) COMMENT '运营商',
    source VARCHAR(100) COMMENT '数据来源',
    batch_id VARCHAR(50) COMMENT '导入批次ID',
    last_used_at DATETIME COMMENT '上次使用时间',
    use_count INT DEFAULT 0 COMMENT '使用次数',
    cooldown_until DATETIME COMMENT '冷却期截止',
    account_id INT UNSIGNED COMMENT '所属账户ID(私库)',
    exclusive_until DATETIME COMMENT '(废弃)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX idx_phone_number (phone_number),
    INDEX idx_country_code (country_code),
    INDEX idx_status (status),
    INDEX idx_account_id (account_id),
    INDEX idx_carrier (carrier),
    INDEX idx_last_used (last_used_at),
    CONSTRAINT fk_data_number_account FOREIGN KEY (account_id) REFERENCES accounts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='号码资源池';

-- 2. 数据商品
CREATE TABLE IF NOT EXISTS data_products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_code VARCHAR(50) NOT NULL UNIQUE COMMENT '商品编码',
    product_name VARCHAR(100) NOT NULL COMMENT '商品名称',
    description TEXT COMMENT '商品描述',
    filter_criteria JSON NOT NULL COMMENT '筛选条件',
    price_per_number VARCHAR(20) DEFAULT '0.001' COMMENT '单价',
    currency VARCHAR(10) DEFAULT 'USD' COMMENT '币种',
    stock_count INT DEFAULT 0 COMMENT '库存',
    min_purchase INT DEFAULT 100 COMMENT '最小购买量',
    max_purchase INT DEFAULT 100000 COMMENT '最大购买量',
    product_type ENUM('data_only','combo','data_and_send') DEFAULT 'data_only' COMMENT '商品类型',
    sms_quota INT COMMENT '组合套餐含短信条数',
    sms_unit_price VARCHAR(20) COMMENT '短信单价',
    bundle_price VARCHAR(20) COMMENT '打包价',
    bundle_discount VARCHAR(10) COMMENT '折扣率(%)',
    status ENUM('active','inactive','sold_out') DEFAULT 'active' COMMENT '状态',
    total_sold INT DEFAULT 0 COMMENT '累计销量',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据商品';

-- 3. 数据订单
CREATE TABLE IF NOT EXISTS data_orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_no VARCHAR(50) NOT NULL UNIQUE COMMENT '订单号',
    account_id INT UNSIGNED NOT NULL COMMENT '账户ID',
    product_id INT COMMENT '商品ID',
    filter_criteria JSON COMMENT '筛选条件',
    quantity INT NOT NULL COMMENT '购买数量',
    unit_price VARCHAR(20) COMMENT '单价',
    total_price VARCHAR(20) COMMENT '总价',
    order_type ENUM('data_only','combo','data_and_send') DEFAULT 'data_only' COMMENT '订单类型',
    status ENUM('pending','processing','completed','cancelled','expired') DEFAULT 'pending' COMMENT '状态',
    sms_batch_id INT COMMENT '关联短信批次ID',
    executed_count INT DEFAULT 0 COMMENT '已执行数量',
    executed_at DATETIME COMMENT '执行时间',
    cancel_reason TEXT COMMENT '取消原因',
    refund_amount VARCHAR(20) COMMENT '退款金额',
    refunded_at DATETIME COMMENT '退款时间',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    expires_at DATETIME COMMENT '过期时间',
    CONSTRAINT fk_data_order_account FOREIGN KEY (account_id) REFERENCES accounts(id),
    CONSTRAINT fk_data_order_product FOREIGN KEY (product_id) REFERENCES data_products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据订单';

-- 4. 数据订单-号码关联
CREATE TABLE IF NOT EXISTS data_order_numbers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL COMMENT '订单ID',
    number_id BIGINT NOT NULL COMMENT '号码ID',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_order_number_order (order_id),
    INDEX idx_order_number_number (number_id),
    CONSTRAINT fk_don_order FOREIGN KEY (order_id) REFERENCES data_orders(id),
    CONSTRAINT fk_don_number FOREIGN KEY (number_id) REFERENCES data_numbers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单-号码关联';

-- 5. 数据导入批次
CREATE TABLE IF NOT EXISTS data_import_batches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    batch_id VARCHAR(50) NOT NULL UNIQUE COMMENT '批次ID',
    file_name VARCHAR(255) COMMENT '文件名',
    source VARCHAR(100) COMMENT '来源',
    total_count INT DEFAULT 0,
    valid_count INT DEFAULT 0,
    duplicate_count INT DEFAULT 0,
    invalid_count INT DEFAULT 0,
    status ENUM('pending','processing','completed','failed') DEFAULT 'pending',
    error_message TEXT,
    created_by INT UNSIGNED COMMENT '操作人ID',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    CONSTRAINT fk_dib_admin FOREIGN KEY (created_by) REFERENCES admin_users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据导入批次';

-- 6. 数据账户
CREATE TABLE IF NOT EXISTS data_accounts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_id INT UNSIGNED NOT NULL COMMENT '本地账户ID',
    platform_account VARCHAR(100) COMMENT '平台账号',
    platform_token VARCHAR(255) COMMENT '平台Token',
    external_id VARCHAR(100) UNIQUE COMMENT '平台账户ID',
    country_code VARCHAR(10) NOT NULL COMMENT '国家代码',
    template_id INT COMMENT '开户模板ID',
    balance DECIMAL(10,2) DEFAULT 0 COMMENT '余额',
    total_extracted INT DEFAULT 0 COMMENT '总提取数',
    total_spent DECIMAL(10,2) DEFAULT 0 COMMENT '总花费',
    status ENUM('active','suspended','closed') DEFAULT 'active',
    last_sync_at DATETIME,
    sync_error TEXT,
    extra_data JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_da_account FOREIGN KEY (account_id) REFERENCES accounts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据账户';

-- 7. 数据提取记录
CREATE TABLE IF NOT EXISTS data_extraction_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    data_account_id INT NOT NULL COMMENT '数据账户ID',
    extraction_id VARCHAR(100) COMMENT '平台提取ID',
    count INT NOT NULL COMMENT '提取数量',
    unit_price DECIMAL(10,4) COMMENT '单价',
    total_cost DECIMAL(10,2) COMMENT '总费用',
    filters JSON COMMENT '筛选条件',
    status ENUM('pending','success','failed') DEFAULT 'pending',
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    CONSTRAINT fk_del_account FOREIGN KEY (data_account_id) REFERENCES data_accounts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据提取记录';

-- 8. Package 表新增数据相关字段
ALTER TABLE packages ADD COLUMN IF NOT EXISTS data_quota INT COMMENT '数据条数(号码数量)' AFTER sms_quota;
ALTER TABLE packages ADD COLUMN IF NOT EXISTS data_filter_criteria JSON COMMENT '数据筛选条件' AFTER data_quota;
ALTER TABLE packages ADD COLUMN IF NOT EXISTS bundle_discount DECIMAL(5,2) COMMENT '组合折扣率(%)' AFTER data_filter_criteria;

-- 9. AccountPackage 表新增数据使用字段
ALTER TABLE account_packages ADD COLUMN IF NOT EXISTS data_used INT DEFAULT 0 COMMENT '已使用数据条数' AFTER sms_remaining;
ALTER TABLE account_packages ADD COLUMN IF NOT EXISTS data_remaining INT COMMENT '剩余数据条数' AFTER data_used;
