# 国际短信系统 - 开发计划与验收标准

## 文档信息
- **文档版本**: v1.0
- **创建日期**: 2025-12-31
- **项目版本**: v1.5
- **当前进度**: 90%

---

## 📊 项目当前状态评估

### 已完成功能 ✅

#### Phase 1: 核心功能完善 (100%)
- ✅ Redis缓存集成
- ✅ API限流实现
- ✅ 真实SMPP实现
- ✅ Webhook回调实现
- ✅ IP白名单验证
- ✅ 单元测试框架

#### Phase 2: 管理功能开发 (100%)
- ✅ 管理员登录和JWT认证
- ✅ 通道配置管理（CRUD）
- ✅ 费率管理系统（CRUD）
- ✅ 账户管理

#### Phase 3: 报表统计功能 (100%)
- ✅ 发送统计API
- ✅ 成功率分析API
- ✅ 每日统计API
- ✅ 图表展示（ECharts）
- ✅ 数据导出（Excel格式）

#### Phase 4: TG助手管理模块 (部分完成)
- ✅ 后端API框架已搭建 (`bot_admin.py`)
- ✅ 前端页面文件已创建（4个页面）
- ✅ 路由配置已完成
- ⚠️ 需要完善和测试

---

## 🎯 Phase 4 详细开发计划

### 目标
在 Web 管理后台完善"TG 助手管理"板块，实现对邀请码、充值工单、群发审核、文案白名单的可视化管理，形成"TG 获客，Web 管理"的闭环。

### 开发周期
**预计时间**: 1-2周（5-10个工作日）

---

## 📋 任务清单

### 阶段一：后端API完善（2-3天）

#### 1.1 邀请码管理API完善
**文件**: `backend/app/api/v1/bot_admin.py`

**任务**:
- [ ] 修复分页查询总数统计（当前使用 `len(invites)` 不准确）
- [ ] 添加邀请码详情查询接口 `GET /admin/bot/invites/{code}`
- [ ] 添加邀请码使用统计接口 `GET /admin/bot/invites/stats`
- [ ] 完善邀请码过期时间处理
- [ ] 添加邀请码导出功能（可选）

**验收标准**:
- ✅ 分页查询总数准确
- ✅ 支持按状态、销售ID、时间范围筛选
- ✅ 销售角色只能查看自己的邀请码
- ✅ 管理员可以查看所有邀请码

#### 1.2 充值审核API完善
**文件**: `backend/app/api/v1/bot_admin.py`

**任务**:
- [ ] 修复API路径（当前使用 `/audit`，建议保持统一）
- [ ] 添加充值工单详情查询 `GET /admin/bot/recharges/{id}`
- [ ] 完善审核流程（财务审核 → 技术执行）
- [ ] 添加审核历史记录
- [ ] 实现充值成功后通知Telegram用户（TODO项）

**验收标准**:
- ✅ 财务角色可以审核充值工单
- ✅ 审核通过后自动增加账户余额
- ✅ 审核拒绝时记录拒绝原因
- ✅ 充值成功后通过Telegram Bot通知用户

#### 1.3 群发审核API完善
**文件**: `backend/app/api/v1/bot_admin.py`

**任务**:
- [ ] 完善群发批次详情查询
- [ ] 添加审核理由字段
- [ ] 实现审核后自动触发发送流程
- [ ] 添加批量审核功能（可选）

**验收标准**:
- ✅ 可以查看待审核的群发批次列表
- ✅ 审核通过后自动开始发送
- ✅ 审核拒绝时记录拒绝原因
- ✅ 审核操作记录到日志

#### 1.4 白名单管理API完善
**文件**: `backend/app/api/v1/bot_admin.py`

**任务**:
- [ ] 添加白名单创建接口 `POST /admin/bot/templates`
- [ ] 添加白名单编辑接口 `PUT /admin/bot/templates/{id}`
- [ ] 添加白名单搜索功能
- [ ] 添加白名单批量导入功能（可选）

**验收标准**:
- ✅ 可以创建新的文案白名单
- ✅ 可以编辑现有白名单
- ✅ 可以删除白名单
- ✅ 支持按内容搜索

#### 1.5 数据库模型检查
**任务**:
- [ ] 确认所有相关表结构完整
- [ ] 检查外键约束
- [ ] 确认索引优化
- [ ] 添加必要的审计字段

**相关表**:
- `invitation_codes` - 邀请码表
- `recharge_orders` - 充值工单表
- `sms_batches` - 群发批次表
- `sms_templates` - 文案白名单表

---

### 阶段二：前端页面完善（3-4天）

#### 2.1 邀请码管理页面 (`views/bot/Invites.vue`)
**任务**:
- [ ] 完善列表展示（状态筛选、分页）
- [ ] 完善创建邀请码对话框（表单验证）
- [ ] 添加邀请码详情查看
- [ ] 添加邀请码使用统计展示
- [ ] 添加复制邀请链接功能
- [ ] 添加导出功能（可选）

**验收标准**:
- ✅ 列表展示清晰，支持筛选和分页
- ✅ 创建邀请码表单验证完整
- ✅ 可以查看邀请码使用情况
- ✅ 复制链接功能正常

#### 2.2 充值审核页面 (`views/bot/RechargeAudit.vue`)
**任务**:
- [ ] 完善待审核工单列表
- [ ] 添加工单详情查看（包括支付凭证）
- [ ] 实现审核操作（通过/拒绝）
- [ ] 添加审核历史记录展示
- [ ] 添加批量审核功能（可选）

**验收标准**:
- ✅ 可以查看待审核充值工单列表
- ✅ 可以查看支付凭证图片
- ✅ 审核操作有确认提示
- ✅ 审核后状态及时更新
- ✅ 拒绝时必填拒绝原因

#### 2.3 群发审核页面 (`views/bot/BatchAudit.vue`)
**任务**:
- [ ] 完善待审核批次列表
- [ ] 添加批次详情查看（内容预览、数量、费用）
- [ ] 实现审核操作（通过/拒绝）
- [ ] 添加审核理由输入
- [ ] 添加审核后状态跟踪

**验收标准**:
- ✅ 可以查看待审核群发批次
- ✅ 可以预览短信内容
- ✅ 审核操作有确认提示
- ✅ 审核通过后自动开始发送
- ✅ 审核拒绝时必填拒绝原因

#### 2.4 白名单管理页面 (`views/bot/Templates.vue`)
**任务**:
- [ ] 完善白名单列表展示
- [ ] 添加创建白名单功能
- [ ] 添加编辑白名单功能
- [ ] 添加搜索功能
- [ ] 添加批量删除功能（可选）

**验收标准**:
- ✅ 列表展示清晰
- ✅ 可以创建新白名单
- ✅ 可以编辑现有白名单
- ✅ 可以删除白名单
- ✅ 支持按内容搜索

#### 2.5 路由和菜单检查
**任务**:
- [ ] 确认路由配置正确
- [ ] 确认菜单显示正确
- [ ] 确认权限控制正确（仅管理员可见）

**验收标准**:
- ✅ 路由跳转正常
- ✅ 菜单显示正确
- ✅ 非管理员无法访问

---

### 阶段三：集成测试与优化（2-3天）

#### 3.1 功能测试
**任务**:
- [ ] 邀请码管理端到端测试
- [ ] 充值审核端到端测试
- [ ] 群发审核端到端测试
- [ ] 白名单管理端到端测试
- [ ] 权限控制测试

**测试场景**:
1. 销售创建邀请码 → 用户使用邀请码注册 → 查看使用情况
2. 用户提交充值申请 → 财务审核通过 → 账户余额增加 → Telegram通知
3. 用户提交群发申请 → 管理员审核通过 → 自动开始发送
4. 管理员创建白名单 → 用户使用白名单内容发送 → 自动通过审核

#### 3.2 性能优化
**任务**:
- [ ] 列表查询性能优化（添加索引）
- [ ] 分页查询优化
- [ ] 前端加载优化（懒加载、虚拟滚动）

#### 3.3 用户体验优化
**任务**:
- [ ] 添加加载状态提示
- [ ] 添加错误提示优化
- [ ] 添加操作成功提示
- [ ] 优化表单验证提示

---

## ✅ 验收标准

### 功能验收

#### 1. 邀请码管理
- [ ] ✅ 销售可以创建邀请码
- [ ] ✅ 销售只能查看自己的邀请码
- [ ] ✅ 管理员可以查看所有邀请码
- [ ] ✅ 邀请码状态正确更新（unused → used）
- [ ] ✅ 邀请码过期时间正确
- [ ] ✅ 可以复制邀请链接

#### 2. 充值审核
- [ ] ✅ 财务可以查看待审核充值工单
- [ ] ✅ 可以查看支付凭证
- [ ] ✅ 审核通过后账户余额正确增加
- [ ] ✅ 审核拒绝时记录拒绝原因
- [ ] ✅ 充值成功后Telegram通知用户
- [ ] ✅ 审核操作记录到日志

#### 3. 群发审核
- [ ] ✅ 管理员可以查看待审核群发批次
- [ ] ✅ 可以预览短信内容
- [ ] ✅ 审核通过后自动开始发送
- [ ] ✅ 审核拒绝时记录拒绝原因
- [ ] ✅ 审核操作记录到日志

#### 4. 白名单管理
- [ ] ✅ 管理员可以创建白名单
- [ ] ✅ 管理员可以编辑白名单
- [ ] ✅ 管理员可以删除白名单
- [ ] ✅ 支持按内容搜索
- [ ] ✅ 白名单内容用于自动审核

### 性能验收

- [ ] ✅ 列表查询响应时间 < 500ms
- [ ] ✅ 分页查询性能良好（1000+条数据）
- [ ] ✅ 前端页面加载时间 < 2秒

### 安全验收

- [ ] ✅ 权限控制正确（角色验证）
- [ ] ✅ API接口有认证保护
- [ ] ✅ 敏感操作有确认提示
- [ ] ✅ SQL注入防护
- [ ] ✅ XSS防护

### 用户体验验收

- [ ] ✅ 界面美观、操作流畅
- [ ] ✅ 错误提示清晰
- [ ] ✅ 操作成功有反馈
- [ ] ✅ 加载状态有提示
- [ ] ✅ 表单验证完整

### 代码质量验收

- [ ] ✅ 代码符合规范（PEP 8 / ESLint）
- [ ] ✅ 有必要的注释
- [ ] ✅ 无明显的bug
- [ ] ✅ 错误处理完善

---

## 📅 开发时间表

| 阶段 | 任务 | 预计时间 | 负责人 | 状态 |
|------|------|----------|--------|------|
| 阶段一 | 后端API完善 | 2-3天 | 后端开发 | ⏳ 待开始 |
| 阶段二 | 前端页面完善 | 3-4天 | 前端开发 | ⏳ 待开始 |
| 阶段三 | 集成测试与优化 | 2-3天 | 测试/开发 | ⏳ 待开始 |
| **总计** | | **7-10天** | | |

---

## 🚀 后续计划（Phase 5-6）

### Phase 5: 测试与优化（2-3周）
- 单元测试覆盖率提升到 > 80%
- 集成测试完善
- 性能测试和优化
- 安全测试
- 压力测试（10,000 TPS）

### Phase 6: 运维功能（2周）
- 系统监控完善
- 日志分析优化
- 备份恢复流程
- 故障处理流程
- 运维文档完善

---

## 📝 注意事项

1. **API路径统一**: 确保所有API路径符合RESTful规范
2. **权限控制**: 严格验证用户角色和权限
3. **错误处理**: 所有API都要有完善的错误处理
4. **日志记录**: 重要操作要记录日志
5. **数据一致性**: 确保数据库操作的事务性
6. **用户体验**: 关注前端交互体验

---

## 📞 联系方式

- **项目经理**: [待填写]
- **技术负责人**: [待填写]
- **产品经理**: [待填写]

---

## 📝 详细实施指南

### API接口详细规范

#### 1. 邀请码管理API

**1.1 获取邀请码列表**
```
GET /admin/bot/invites
Query Parameters:
  - page: int = 1 (页码)
  - limit: int = 20 (每页数量)
  - status: str = None (筛选状态: unused/used/expired)
  - sales_id: int = None (筛选销售ID，仅管理员可用)

Response:
{
  "items": [
    {
      "code": "ABC12345",
      "sales_id": 1,
      "sales_name": "张三",
      "config": {
        "country": "CN",
        "price": 0.05,
        "business_type": "sms"
      },
      "status": "unused",
      "used_by_account_id": null,
      "created_at": "2025-12-31T10:00:00",
      "expires_at": "2026-01-01T10:00:00",
      "used_at": null
    }
  ],
  "total": 100,
  "page": 1,
  "limit": 20
}
```

**1.2 创建邀请码**
```
POST /admin/bot/invites
Request Body:
{
  "country": "CN",
  "price": 0.05,
  "business_type": "sms",
  "valid_hours": 24
}

Response:
{
  "success": true,
  "code": "ABC12345",
  "invite_link": "https://t.me/your_bot?start=ABC12345"
}
```

**1.3 获取邀请码详情**
```
GET /admin/bot/invites/{code}

Response:
{
  "code": "ABC12345",
  "sales_id": 1,
  "sales_name": "张三",
  "config": {...},
  "status": "used",
  "used_by_account_id": 100,
  "used_by_account_name": "TG_123456",
  "created_at": "...",
  "expires_at": "...",
  "used_at": "..."
}
```

**1.4 邀请码统计**
```
GET /admin/bot/invites/stats
Query Parameters:
  - sales_id: int = None
  - start_date: str = None
  - end_date: str = None

Response:
{
  "total": 100,
  "unused": 30,
  "used": 60,
  "expired": 10,
  "usage_rate": 0.6,
  "recent_usage": [
    {"date": "2025-12-31", "count": 5}
  ]
}
```

#### 2. 充值审核API

**2.1 获取充值工单列表**
```
GET /admin/bot/recharges
Query Parameters:
  - status: str = 'pending' (pending/finance_approved/completed/rejected)
  - page: int = 1
  - limit: int = 20

Response:
[
  {
    "id": 1,
    "order_no": "RCH20251231001",
    "account_id": 100,
    "account_name": "TG_123456",
    "amount": 1000.00,
    "currency": "CNY",
    "payment_proof": "https://...",
    "status": "pending",
    "created_at": "...",
    "finance_audit_by": null,
    "finance_audit_at": null
  }
]
```

**2.2 获取充值工单详情**
```
GET /admin/bot/recharges/{id}

Response:
{
  "id": 1,
  "order_no": "RCH20251231001",
  "account_id": 100,
  "account": {
    "id": 100,
    "name": "TG_123456",
    "balance": 500.00
  },
  "amount": 1000.00,
  "currency": "CNY",
  "payment_proof": "https://...",
  "status": "pending",
  "created_at": "...",
  "finance_audit_by": null,
  "finance_audit_at": null,
  "reject_reason": null
}
```

**2.3 审核充值工单**
```
POST /admin/bot/recharges/{id}/audit
Request Body:
{
  "action": "approve",  // or "reject"
  "reason": "审核通过"  // required if action is "reject"
}

Response:
{
  "success": true,
  "message": "审核成功"
}
```

#### 3. 群发审核API

**3.1 获取群发批次列表**
```
GET /admin/bot/batches
Query Parameters:
  - status: str = 'pending_audit'
  - page: int = 1
  - limit: int = 20

Response:
[
  {
    "id": "BATCH_20251231_001",
    "account_id": 100,
    "account_name": "TG_123456",
    "content": "您的验证码是123456",
    "content_preview": "您的验证码是...",
    "total_count": 1000,
    "valid_count": 950,
    "total_cost": 50.00,
    "status": "pending_audit",
    "created_at": "..."
  }
]
```

**3.2 审核群发批次**
```
POST /admin/bot/batches/{id}/audit
Request Body:
{
  "action": "approve",  // or "reject"
  "reason": "内容合规"  // optional
}

Response:
{
  "success": true,
  "message": "审核成功，已开始发送"
}
```

#### 4. 白名单管理API

**4.1 获取白名单列表**
```
GET /admin/bot/templates
Query Parameters:
  - account_id: int = None
  - search: str = None (搜索内容)
  - page: int = 1
  - limit: int = 50

Response:
[
  {
    "id": 1,
    "account_id": 100,
    "account_name": "TG_123456",
    "content_text": "您的验证码是{code}",
    "content_hash": "abc123...",
    "status": "approved",
    "created_at": "..."
  }
]
```

**4.2 创建白名单**
```
POST /admin/bot/templates
Request Body:
{
  "account_id": 100,
  "content_text": "您的验证码是{code}"
}

Response:
{
  "success": true,
  "id": 1,
  "content_hash": "abc123..."
}
```

**4.3 编辑白名单**
```
PUT /admin/bot/templates/{id}
Request Body:
{
  "status": "approved"  // or "rejected"
}

Response:
{
  "success": true
}
```

---

## 💻 代码实现示例

### 后端：修复分页查询总数统计

```python
# backend/app/api/v1/bot_admin.py

@router.get("/invites", response_model=Dict[str, Any])
async def list_invites(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    sales_id: Optional[int] = None,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    # 构建查询
    query = select(InvitationCode)
    count_query = select(func.count(InvitationCode.code))
    
    # 销售只能看自己的
    if admin.role == 'sales':
        query = query.where(InvitationCode.sales_id == admin.id)
        count_query = count_query.where(InvitationCode.sales_id == admin.id)
    elif sales_id and admin.role in ['super_admin', 'admin']:
        query = query.where(InvitationCode.sales_id == sales_id)
        count_query = count_query.where(InvitationCode.sales_id == sales_id)
        
    if status:
        query = query.where(InvitationCode.status == status)
        count_query = count_query.where(InvitationCode.status == status)
        
    # 获取总数
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # 分页查询
    query = query.order_by(desc(InvitationCode.created_at))
    query = query.offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(query)
    invites = result.scalars().all()
    
    # 关联查询销售信息
    from app.models.admin_user import AdminUser
    sales_ids = {i.sales_id for i in invites}
    if sales_ids:
        sales_query = select(AdminUser).where(AdminUser.id.in_(sales_ids))
        sales_result = await db.execute(sales_query)
        sales_map = {s.id: s.real_name or s.username for s in sales_result.scalars().all()}
    else:
        sales_map = {}
    
    return {
        "items": [
            {
                "code": i.code,
                "sales_id": i.sales_id,
                "sales_name": sales_map.get(i.sales_id, "未知"),
                "config": i.pricing_config or {},
                "status": i.status,
                "used_by_account_id": i.used_by_account_id,
                "created_at": i.created_at.isoformat() if i.created_at else None,
                "expires_at": i.expires_at.isoformat() if i.expires_at else None,
                "used_at": i.used_at.isoformat() if i.used_at else None
            }
            for i in invites
        ],
        "total": total,
        "page": page,
        "limit": limit
    }
```

### 后端：实现Telegram通知

```python
# backend/app/api/v1/bot_admin.py

async def notify_telegram_user(account_id: int, message: str):
    """通知Telegram用户"""
    from app.models.telegram_binding import TelegramBinding
    from telegram_bot.bot.services.notification import NotificationService
    
    # 查找账户的Telegram绑定
    query = select(TelegramBinding).where(
        TelegramBinding.account_id == account_id,
        TelegramBinding.is_active == True
    )
    result = await db.execute(query)
    binding = result.scalar_one_or_none()
    
    if binding:
        notification_service = NotificationService()
        await notification_service.send_message(
            telegram_id=binding.tg_id,
            message=message
        )

@router.post("/recharges/{oid}/audit")
async def audit_recharge(
    oid: int,
    request: AuditRequest,
    admin: AdminUser = Depends(AuthService.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    # ... 现有审核逻辑 ...
    
    if request.action == 'approve':
        # ... 余额增加逻辑 ...
        
        # 通知用户
        await notify_telegram_user(
            account_id=order.account_id,
            message=f"✅ 充值成功！\n\n金额: {order.amount} {order.currency}\n当前余额: {account.balance} {account.currency}"
        )
    
    elif request.action == 'reject':
        # ... 拒绝逻辑 ...
        
        # 通知用户
        await notify_telegram_user(
            account_id=order.account_id,
            message=f"❌ 充值申请被拒绝\n\n原因: {request.reason or '未提供原因'}"
        )
```

### 前端：完善邀请码管理页面

```vue
<!-- frontend/src/views/bot/Invites.vue -->

<template>
  <div class="invites-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>开户邀约管理</span>
          <el-button type="primary" @click="showCreateDialog">生成邀请码</el-button>
        </div>
      </template>

      <!-- 筛选器 -->
      <el-form :inline="true" class="filter-form">
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部">
            <el-option label="未使用" value="unused" />
            <el-option label="已使用" value="used" />
            <el-option label="已过期" value="expired" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>

      <!-- 列表 -->
      <el-table :data="invites" v-loading="loading" style="width: 100%">
        <el-table-column prop="code" label="邀请码" width="150">
          <template #default="scope">
            <el-tag size="large" @click="copyCode(scope.row.code)" style="cursor: pointer">
              {{ scope.row.code }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="sales_name" label="销售" width="120" />
        <el-table-column label="配置详情">
          <template #default="scope">
            <div v-if="scope.row.config">
              <el-tag type="info" size="small">{{ scope.row.config.country }}</el-tag>
              <span class="price-tag">${{ scope.row.config.price }}</span>
              <el-tag type="warning" size="small">{{ scope.row.config.business_type }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">
              {{ getStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="生成时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="scope">
            <el-button link type="primary" @click="viewDetail(scope.row.code)">详情</el-button>
            <el-button link type="primary" @click="copyLink(scope.row.code)">复制链接</el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          :page-size="limit"
          :total="total"
          @current-change="loadData"
          layout="total, prev, pager, next"
        />
      </div>
    </el-card>

    <!-- 创建对话框 -->
    <el-dialog v-model="createDialogVisible" title="生成邀请码" width="500px">
      <el-form :model="createForm" :rules="createRules" ref="createFormRef" label-width="100px">
        <el-form-item label="国家" prop="country">
          <el-select v-model="createForm.country">
            <el-option label="中国" value="CN" />
            <el-option label="美国" value="US" />
            <el-option label="全球" value="global" />
          </el-select>
        </el-form-item>
        <el-form-item label="单价" prop="price">
          <el-input-number v-model="createForm.price" :precision="4" :min="0" />
        </el-form-item>
        <el-form-item label="业务类型" prop="business_type">
          <el-select v-model="createForm.business_type">
            <el-option label="短信" value="sms" />
            <el-option label="语音" value="voice" />
          </el-select>
        </el-form-item>
        <el-form-item label="有效期" prop="valid_hours">
          <el-input-number v-model="createForm.valid_hours" :min="1" :max="720" />
          <span style="margin-left: 10px">小时</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreate" :loading="creating">生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getInvites, createInvite } from '@/api/bot'
import type { InviteCode } from '@/api/bot'

const loading = ref(false)
const invites = ref<InviteCode[]>([])
const page = ref(1)
const limit = ref(20)
const total = ref(0)

const filters = ref({
  status: ''
})

const createDialogVisible = ref(false)
const creating = ref(false)
const createForm = ref({
  country: 'CN',
  price: 0.05,
  business_type: 'sms',
  valid_hours: 24
})

const createRules = {
  country: [{ required: true, message: '请选择国家', trigger: 'change' }],
  price: [{ required: true, message: '请输入单价', trigger: 'blur' }],
  business_type: [{ required: true, message: '请选择业务类型', trigger: 'change' }],
  valid_hours: [{ required: true, message: '请输入有效期', trigger: 'blur' }]
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await getInvites({
      page: page.value,
      limit: limit.value,
      status: filters.value.status || undefined
    })
    invites.value = res.items
    total.value = res.total
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const handleCreate = async () => {
  creating.value = true
  try {
    const res = await createInvite(createForm.value)
    ElMessage.success(`邀请码生成成功: ${res.code}`)
    createDialogVisible.value = false
    loadData()
  } catch (error) {
    ElMessage.error('生成失败')
  } finally {
    creating.value = false
  }
}

const copyLink = (code: string) => {
  const link = `https://t.me/your_bot?start=${code}`
  navigator.clipboard.writeText(link)
  ElMessage.success('链接已复制')
}

const formatDate = (date: string) => {
  return new Date(date).toLocaleString('zh-CN')
}

const getStatusType = (status: string) => {
  const map: Record<string, string> = {
    unused: 'success',
    used: 'info',
    expired: 'danger'
  }
  return map[status] || ''
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    unused: '未使用',
    used: '已使用',
    expired: '已过期'
  }
  return map[status] || status
}

onMounted(() => {
  loadData()
})
</script>
```

---

## 🧪 测试用例

### 1. 邀请码管理测试

**测试用例 TC-001: 创建邀请码**
```
前置条件: 已登录销售或管理员账号
测试步骤:
1. 访问邀请码管理页面
2. 点击"生成邀请码"按钮
3. 填写表单（国家、单价、业务类型、有效期）
4. 点击"生成"按钮
预期结果:
- 邀请码生成成功
- 显示成功提示
- 列表中显示新生成的邀请码
- 邀请码状态为"未使用"
```

**测试用例 TC-002: 分页查询**
```
前置条件: 数据库中有100+条邀请码记录
测试步骤:
1. 访问邀请码管理页面
2. 查看第一页数据
3. 点击"下一页"
4. 修改每页数量为50
预期结果:
- 第一页显示20条数据（默认）
- 总数显示正确
- 翻页正常
- 修改每页数量后重新加载
```

**测试用例 TC-003: 权限控制**
```
前置条件: 
- 销售账号A已登录
- 销售账号B已登录
- 管理员账号已登录
测试步骤:
1. 销售A创建邀请码
2. 销售B登录，查看邀请码列表
3. 管理员登录，查看邀请码列表
预期结果:
- 销售A只能看到自己创建的邀请码
- 销售B看不到销售A的邀请码
- 管理员可以看到所有邀请码
```

### 2. 充值审核测试

**测试用例 TC-004: 审核通过充值**
```
前置条件:
- 用户已提交充值申请
- 财务账号已登录
测试步骤:
1. 访问充值审核页面
2. 查看待审核工单列表
3. 点击"查看详情"
4. 查看支付凭证
5. 点击"审核通过"
6. 确认操作
预期结果:
- 工单状态变为"已完成"
- 用户账户余额增加
- Telegram用户收到通知
- 余额变动记录正确
```

### 3. 群发审核测试

**测试用例 TC-005: 审核通过群发**
```
前置条件:
- 用户已提交群发申请
- 管理员账号已登录
测试步骤:
1. 访问群发审核页面
2. 查看待审核批次列表
3. 点击"查看详情"，预览内容
4. 点击"审核通过"
5. 确认操作
预期结果:
- 批次状态变为"sending"
- 自动开始发送流程
- 内容添加到白名单
- Telegram用户收到通知
```

---

## 🔍 数据库优化建议

### 索引优化

```sql
-- 邀请码表索引
CREATE INDEX idx_invites_sales_status ON invitation_codes(sales_id, status);
CREATE INDEX idx_invites_expires ON invitation_codes(expires_at);
CREATE INDEX idx_invites_created ON invitation_codes(created_at DESC);

-- 充值工单表索引
CREATE INDEX idx_recharge_account_status ON recharge_orders(account_id, status);
CREATE INDEX idx_recharge_created ON recharge_orders(created_at DESC);

-- 群发批次表索引
CREATE INDEX idx_batch_account_status ON sms_batches(account_id, status);
CREATE INDEX idx_batch_created ON sms_batches(created_at DESC);

-- 白名单表索引
CREATE INDEX idx_template_account_hash ON sms_templates(account_id, content_hash);
CREATE INDEX idx_template_search ON sms_templates(content_text(100));
```

### 查询优化

```python
# 使用select_related减少查询次数
from sqlalchemy.orm import selectinload

query = select(InvitationCode).options(
    selectinload(InvitationCode.sales)  # 预加载销售信息
)
```

---

## ⚠️ 风险评估与应对

### 风险1: 分页查询性能问题
**风险描述**: 当数据量很大时，分页查询可能变慢
**应对措施**:
- 添加合适的索引
- 使用游标分页（可选）
- 限制最大查询数量
- 添加缓存（Redis）

### 风险2: 并发审核冲突
**风险描述**: 多个管理员同时审核同一工单可能导致数据不一致
**应对措施**:
- 使用数据库事务
- 添加乐观锁（版本号）
- 审核前检查状态

### 风险3: Telegram通知失败
**风险描述**: Telegram Bot服务不可用时，用户无法收到通知
**应对措施**:
- 添加重试机制
- 记录通知日志
- 提供手动通知功能
- 使用消息队列异步处理

### 风险4: 白名单内容冲突
**风险描述**: 不同账户可能有相同内容，需要区分
**应对措施**:
- 白名单按账户隔离（已实现）
- 支持全局白名单（可选）
- 内容哈希唯一性检查

---

## 📋 部署检查清单

### 代码检查
- [ ] 所有API接口已实现
- [ ] 前端页面功能完整
- [ ] 错误处理完善
- [ ] 日志记录完整
- [ ] 代码符合规范

### 数据库检查
- [ ] 表结构完整
- [ ] 索引已创建
- [ ] 外键约束正确
- [ ] 数据迁移脚本准备

### 测试检查
- [ ] 单元测试通过
- [ ] 集成测试通过
- [ ] 功能测试通过
- [ ] 性能测试通过

### 部署检查
- [ ] 环境变量配置
- [ ] API路由注册
- [ ] 前端路由配置
- [ ] 权限配置正确
- [ ] 监控告警配置

---

## 📚 参考文档

- [后端开发计划](./BACKEND_PLAN.md)
- [前端开发计划](./FRONTEND_PLAN.md)
- [数据库设计](./DATABASE_DESIGN.md)
- [Telegram集成方案](./TELEGRAM_INTEGRATION.md)
- [API接口文档](./API_SPECIFICATION.md)

---

**文档结束**
