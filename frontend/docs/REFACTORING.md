# 前端重构说明

## 已完成的改动

### 1. 路由模块化 (`src/router/`)

路由按业务域拆分为独立模块：

```
router/
├── index.ts          # 主入口，守卫逻辑
├── routes/
│   ├── index.ts      # 路由聚合
│   ├── auth.ts       # 登录、落地页
│   ├── sms.ts        # 短信业务
│   ├── account.ts    # 账户管理
│   ├── data.ts       # 数据业务
│   └── admin.ts      # 管理后台
```

**好处**：新增路由时只需在对应模块添加，便于维护。

### 2. 共享组件 (`src/components/`)

| 组件 | 用途 |
|------|------|
| `StatCard` | 统计卡片（今日发送、成功率等） |
| `PageHeader` | 页面标题 + 描述 + 操作区 |

**使用示例**：

```vue
<script setup>
import { StatCard, PageHeader } from '@/components'
</script>

<template>
  <PageHeader title="发送短信" description="批量发送国际短信" />
  <div class="stats-cards">
    <StatCard value="1,234" label="今日发送" variant="today" />
  </div>
</template>
```

### 3. 类型定义 (`src/types/`)

- `api.ts`：`PaginationParams`、`PaginatedResponse`、`ListQueryParams`
- 可在 API 层和页面中复用

### 4. Composables (`src/composables/`)

- `usePagination`：表格分页逻辑复用

```ts
import { usePagination } from '@/composables/usePagination'

const { page, pageSize, total, paginationParams, setTotal, handlePageChange } = usePagination(20)
```

---

## 后续可优化方向

1. **MainLayout 导航**：将 1400+ 行中的导航配置提取为 `navConfig.ts`，用数据驱动渲染
2. **大页面拆分**：如 `Send.vue`（1500+ 行）可拆为子组件（表单区、预览区、统计区）
3. **API 层**：为各 API 模块补充请求/响应类型
4. **按需注册 Element Plus**：减少首屏体积

---

## 验证

```bash
cd frontend && npm run build
```

构建通过即表示重构未破坏现有功能。
