# 上线修改记录

## 2026-03 短信业务功能更新

### 新增功能

#### 1. 充值记录查询
- **路径**：`/sms/recharge-records`
- **菜单**：短信业务 → 充值记录
- **功能**：按客户账户、员工、变动类型、时间范围查询充值/扣减/退补充值记录

#### 2. 发送统计查询
- **路径**：`/sms/send-stats`
- **菜单**：短信业务 → 发送统计
- **功能**：按员工、通道、客户账户筛选，支持日报/周报/月报/季报/年报

#### 3. 退补充值
- **说明**：充值功能支持「退补充值」类型，不计算业绩、不核算成本
- **入口**：客户管理 → 余额调账 → 类型选择「退补充值」

### 数据库迁移

**必须执行**（上线前）：

```bash
# 方式1：直接执行
mysql -u smsuser -p sms_system < scripts/add_refund_recharge.sql

# 方式2：Docker 环境
docker compose exec mysql mysql -u root -p sms_system -e "ALTER TABLE balance_logs MODIFY COLUMN change_type ENUM('charge', 'refund', 'deposit', 'withdraw', 'adjustment', 'refund_recharge') NOT NULL COMMENT '变动类型';"
```

### 上线检查清单

- [ ] 执行 `scripts/add_refund_recharge.sql` 迁移
- [ ] 验证 `balance_logs.change_type` 包含 `refund_recharge`
- [ ] 重新构建前端：`docker compose build frontend`
- [ ] 重启后端服务
- [ ] 验证充值记录、发送统计入口可访问
- [ ] 验证余额调账可选择「退补充值」
