# Phase 4: TG 助手管理模块开发计划

## 1. 目标概述
在 Web 管理后台增加“TG 助手管理”板块，实现对邀请码、充值工单、群发审核、文案白名单的可视化管理，形成“TG 获客，Web 管理”的闭环。

## 2. 后端 API 补全 (Backend API)
需新建 `app/api/v1/bot_admin.py`。

- **开户管理 (Invites)**
    - `GET /admin/bot/invites`: 获取邀请码列表。
    - `POST /admin/bot/invites`: 生成新邀请码。
- **充值审核 (Recharges)**
    - `GET /admin/bot/recharges`: 获取待审核充值工单。
    - `POST /admin/bot/recharges/{id}/approve`: 确认到账。
    - `POST /admin/bot/recharges/{id}/reject`: 驳回。
- **群发审核 (Batches)**
    - `GET /admin/bot/batches`: 获取 `pending_audit` 状态的批次。
    - `POST /admin/bot/batches/{id}/audit`: 通过/驳回。
- **白名单管理 (Templates)**
    - `GET /admin/bot/templates`: 获取文案白名单列表。
    - `DELETE /admin/bot/templates/{id}`: 移除白名单。

## 3. 前端页面开发 (Frontend)

- **API 封装**: `src/api/bot.ts`
- **页面**:
    - `views/bot/Invites.vue` (销售邀约)
    - `views/bot/RechargeAudit.vue` (充值审核)
    - `views/bot/BatchAudit.vue` (群发审核)
    - `views/bot/Templates.vue` (白名单管理)
- **路由**: 更新 `router/index.ts` 和 `MainLayout.vue`。

## 4. 执行顺序
见 Todo List。
