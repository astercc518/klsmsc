# 国际短信系统 - 前端开发计划

## 文档信息
- **文档类型**: Frontend Development Plan
- **项目名称**: International SMS Gateway System - Admin Dashboard
- **技术栈**: Vue 3 + TypeScript + Element Plus + Vite
- **文档版本**: v1.0
- **创建日期**: 2025-12-30

---

## 目录
1. [开发环境搭建](#1-开发环境搭建)
2. [项目结构](#2-项目结构)
3. [开发阶段规划](#3-开发阶段规划)
4. [核心模块开发](#4-核心模块开发)
5. [UI设计规范](#5-ui设计规范)
6. [部署计划](#6-部署计划)

---

## 1. 开发环境搭建

### 1.1 环境要求

```bash
Node.js >= 18.0.0
npm >= 9.0.0
# 或
pnpm >= 8.0.0 (推荐)
```

### 1.2 项目初始化

```bash
# 使用Vite创建Vue 3 + TypeScript项目
npm create vite@latest frontend -- --template vue-ts
cd frontend

# 安装依赖
npm install

# 安装UI组件库
npm install element-plus
npm install @element-plus/icons-vue

# 安装路由
npm install vue-router@4

# 安装状态管理
npm install pinia

# 安装HTTP客户端
npm install axios

# 安装工具库
npm install dayjs
npm install lodash-es
npm install @types/lodash-es -D

# 安装图表库
npm install echarts
npm install vue-echarts

# 安装开发工具
npm install -D eslint prettier
npm install -D @typescript-eslint/parser @typescript-eslint/eslint-plugin
npm install -D eslint-plugin-vue

# 启动开发服务器
npm run dev
```

### 1.3 VS Code扩展推荐

```json
{
  "recommendations": [
    "Vue.volar",
    "Vue.vscode-typescript-vue-plugin",
    "dbaeumer.vscode-eslint",
    "esbenp.prettier-vscode",
    "lokalise.i18n-ally"
  ]
}
```

---

## 2. 项目结构

```
frontend/
├── public/                     # 静态资源
│   ├── favicon.ico
│   └── logo.png
│
├── src/
│   ├── assets/                 # 资源文件
│   │   ├── images/
│   │   ├── icons/
│   │   └── styles/
│   │       ├── variables.scss  # SCSS变量
│   │       ├── mixins.scss     # SCSS混入
│   │       └── global.scss     # 全局样式
│   │
│   ├── api/                    # API接口
│   │   ├── index.ts            # API配置
│   │   ├── sms.ts              # 短信相关API
│   │   ├── account.ts          # 账户相关API
│   │   ├── channel.ts          # 通道相关API
│   │   ├── pricing.ts          # 计费相关API
│   │   ├── senderid.ts         # SID相关API
│   │   ├── report.ts           # 报表相关API
│   │   └── admin.ts            # 管理相关API
│   │
│   ├── components/             # 通用组件
│   │   ├── common/             # 基础组件
│   │   │   ├── AppHeader.vue
│   │   │   ├── AppSidebar.vue
│   │   │   ├── AppFooter.vue
│   │   │   └── Breadcrumb.vue
│   │   ├── charts/             # 图表组件
│   │   │   ├── LineChart.vue
│   │   │   ├── BarChart.vue
│   │   │   └── PieChart.vue
│   │   └── forms/              # 表单组件
│   │       ├── ChannelForm.vue
│   │       ├── PricingForm.vue
│   │       └── SenderIDForm.vue
│   │
│   ├── composables/            # 组合式函数
│   │   ├── useAuth.ts          # 认证相关
│   │   ├── useTable.ts         # 表格相关
│   │   ├── useForm.ts          # 表单相关
│   │   └── useChart.ts         # 图表相关
│   │
│   ├── directives/             # 自定义指令
│   │   ├── permission.ts       # 权限指令
│   │   └── loading.ts          # 加载指令
│   │
│   ├── layouts/                # 布局组件
│   │   ├── DefaultLayout.vue   # 默认布局
│   │   └── BlankLayout.vue     # 空白布局
│   │
│   ├── router/                 # 路由配置
│   │   ├── index.ts            # 路由主文件
│   │   └── routes.ts           # 路由定义
│   │
│   ├── stores/                 # Pinia状态管理
│   │   ├── index.ts            # Store主文件
│   │   ├── user.ts             # 用户状态
│   │   ├── app.ts              # 应用状态
│   │   └── permission.ts       # 权限状态
│   │
│   ├── types/                  # TypeScript类型定义
│   │   ├── api.d.ts            # API类型
│   │   ├── common.d.ts         # 通用类型
│   │   └── modules.d.ts        # 模块类型
│   │
│   ├── utils/                  # 工具函数
│   │   ├── request.ts          # Axios封装
│   │   ├── auth.ts             # 认证工具
│   │   ├── storage.ts          # 存储工具
│   │   ├── validate.ts         # 验证工具
│   │   └── format.ts           # 格式化工具
│   │
│   ├── views/                  # 页面组件
│   │   ├── login/              # 登录页
│   │   │   └── Index.vue
│   │   │
│   │   ├── dashboard/          # 仪表盘
│   │   │   └── Index.vue
│   │   │
│   │   ├── sms/                # 短信管理
│   │   │   ├── Send.vue        # 发送短信
│   │   │   └── Records.vue     # 发送记录
│   │   │
│   │   ├── channels/           # 通道管理
│   │   │   ├── List.vue        # 通道列表
│   │   │   ├── Create.vue      # 创建通道
│   │   │   └── Edit.vue        # 编辑通道
│   │   │
│   │   ├── pricing/            # 计费管理
│   │   │   ├── Rules.vue       # 计费规则
│   │   │   ├── Import.vue      # 批量导入
│   │   │   └── History.vue     # 价格历史
│   │   │
│   │   ├── senderids/          # 发送方ID管理
│   │   │   ├── List.vue        # SID列表
│   │   │   ├── Apply.vue       # 申请SID
│   │   │   └── Review.vue      # 审核SID
│   │   │
│   │   ├── account/            # 账户管理
│   │   │   ├── List.vue        # 账户列表
│   │   │   ├── Detail.vue      # 账户详情
│   │   │   ├── Balance.vue     # 余额管理
│   │   │   └── ApiKeys.vue     # API密钥
│   │   │
│   │   ├── reports/            # 报表统计
│   │   │   ├── Overview.vue    # 总览
│   │   │   ├── SendingReport.vue   # 发送报表
│   │   │   ├── FinanceReport.vue   # 财务报表
│   │   │   └── ChannelReport.vue   # 通道报表
│   │   │
│   │   └── system/             # 系统设置
│   │       ├── Profile.vue     # 个人信息
│   │       ├── Settings.vue    # 系统设置
│   │       └── Logs.vue        # 操作日志
│   │
│   ├── App.vue                 # 根组件
│   ├── main.ts                 # 入口文件
│   └── env.d.ts                # 环境变量类型
│
├── .env.development            # 开发环境变量
├── .env.production             # 生产环境变量
├── .eslintrc.js                # ESLint配置
├── .prettierrc.js              # Prettier配置
├── tsconfig.json               # TypeScript配置
├── vite.config.ts              # Vite配置
├── package.json
└── README.md
```

---

## 3. 开发阶段规划

### 阶段一：基础框架搭建（Week 1-2）

**Week 1: 项目初始化和基础配置**

**任务**:
- [ ] 项目初始化（Vite + Vue 3 + TypeScript）
- [ ] 安装和配置Element Plus
- [ ] 配置路由（Vue Router）
- [ ] 配置状态管理（Pinia）
- [ ] 配置Axios（请求拦截、响应拦截）
- [ ] 配置ESLint和Prettier
- [ ] 创建基础布局组件
- [ ] 配置环境变量

**交付物**:
- 基础项目框架
- 布局组件
- 路由配置
- Axios封装

---

**Week 2: 登录和权限系统**

**任务**:
- [ ] 登录页面UI
- [ ] 登录功能实现
- [ ] Token存储和管理
- [ ] 路由守卫（权限验证）
- [ ] 退出登录
- [ ] 记住密码功能
- [ ] 用户信息状态管理

**交付物**:
- `views/login/Index.vue`
- `stores/user.ts`
- `utils/auth.ts`
- `router/index.ts` (路由守卫)

---

### 阶段二：核心页面开发（Week 3-8）

#### Week 3: 仪表盘页面

**任务**:
- [ ] 仪表盘布局
- [ ] 关键指标卡片
  - [ ] 今日发送量
  - [ ] 成功率
  - [ ] 待发送量
  - [ ] 账户余额
- [ ] 发送量趋势图（ECharts）
- [ ] 国家分布图
- [ ] 通道状态展示
- [ ] 数据刷新（定时/手动）

**交付物**:
- `views/dashboard/Index.vue`
- `components/charts/*.vue`

---

#### Week 4: 短信发送和记录页面

**任务**:
- [ ] 短信发送页面
  - [ ] 手机号输入（支持多个）
  - [ ] 短信内容输入
  - [ ] 发送方ID选择
  - [ ] 通道选择（可选）
  - [ ] 实时费用预估
  - [ ] 发送按钮和结果提示
- [ ] 发送记录页面
  - [ ] 筛选条件（消息ID、手机号、状态、时间范围）
  - [ ] 记录表格（分页）
  - [ ] 详情弹窗
  - [ ] 导出Excel功能

**交付物**:
- `views/sms/Send.vue`
- `views/sms/Records.vue`

---

#### Week 5: 通道管理页面

**任务**:
- [ ] 通道列表页面
  - [ ] 通道表格（名称、类型、状态、TPS、成功率）
  - [ ] 状态指示器（在线/离线/故障）
  - [ ] 操作按钮（编辑、启用/禁用、测试、删除）
- [ ] 创建/编辑通道弹窗
  - [ ] 表单验证
  - [ ] 协议类型选择（SMPP/HTTP/SOAP）
  - [ ] 连接信息配置
  - [ ] 测试连接按钮
- [ ] 通道测试功能
- [ ] 通道详情页面

**交付物**:
- `views/channels/List.vue`
- `components/forms/ChannelForm.vue`

---

#### Week 6: 计费规则管理页面

**任务**:
- [ ] 计费规则列表
  - [ ] 筛选（通道、国家、运营商）
  - [ ] 规则表格
  - [ ] 内联编辑价格
- [ ] 添加/编辑计费规则弹窗
- [ ] 批量导入功能
  - [ ] Excel模板下载
  - [ ] 文件上传
  - [ ] 导入预览
  - [ ] 导入确认
- [ ] 价格历史查询

**交付物**:
- `views/pricing/Rules.vue`
- `views/pricing/Import.vue`
- `views/pricing/History.vue`

---

#### Week 7: 发送方ID管理页面

**任务**:
- [ ] SID列表页面
  - [ ] 筛选（账户、通道、状态）
  - [ ] SID表格
  - [ ] 状态标签（待审、激活、拒绝）
  - [ ] 操作按钮（编辑、启用/禁用、审核）
- [ ] 申请SID弹窗
  - [ ] SID输入（字母/数字）
  - [ ] 通道选择
  - [ ] 国家选择
  - [ ] 申请文档上传
- [ ] 审核SID弹窗
  - [ ] 审核信息展示
  - [ ] 通过/拒绝操作
  - [ ] 拒绝原因输入

**交付物**:
- `views/senderids/List.vue`
- `views/senderids/Apply.vue`
- `views/senderids/Review.vue`

---

#### Week 8: 账户管理页面

**任务**:
- [ ] 账户列表页面
  - [ ] 账户表格
  - [ ] 搜索和筛选
  - [ ] 操作按钮（详情、充值、编辑）
- [ ] 账户详情页面
  - [ ] 基本信息
  - [ ] 余额信息
  - [ ] 消费统计
  - [ ] 发送记录
- [ ] 余额管理
  - [ ] 充值弹窗
  - [ ] 余额变动记录
  - [ ] 低余额告警设置
- [ ] API密钥管理
  - [ ] 密钥列表
  - [ ] 生成新密钥
  - [ ] 撤销密钥

**交付物**:
- `views/account/List.vue`
- `views/account/Detail.vue`
- `views/account/Balance.vue`
- `views/account/ApiKeys.vue`

---

### 阶段三：报表和高级功能（Week 9-11）

#### Week 9: 报表统计页面

**任务**:
- [ ] 总览报表
  - [ ] 时间范围选择器
  - [ ] 关键指标汇总
  - [ ] 趋势对比图表
- [ ] 发送报表
  - [ ] 按日/周/月统计
  - [ ] 成功率分析
  - [ ] 国家分布
- [ ] 财务报表
  - [ ] 消费统计
  - [ ] 充值记录
  - [ ] 费用趋势
- [ ] 通道报表
  - [ ] 通道性能对比
  - [ ] 成功率排名
  - [ ] TPS统计
- [ ] 导出功能（Excel/CSV）

**交付物**:
- `views/reports/Overview.vue`
- `views/reports/SendingReport.vue`
- `views/reports/FinanceReport.vue`
- `views/reports/ChannelReport.vue`

---

#### Week 10: 系统设置和优化

**任务**:
- [ ] 个人信息页面
  - [ ] 信息展示和编辑
  - [ ] 修改密码
  - [ ] 头像上传
- [ ] 系统设置页面
  - [ ] 系统配置项
  - [ ] 参数编辑
- [ ] 操作日志页面
  - [ ] 日志列表
  - [ ] 筛选和搜索
  - [ ] 日志详情
- [ ] 全局加载优化
- [ ] 错误处理优化
- [ ] 响应式布局优化

**交付物**:
- `views/system/Profile.vue`
- `views/system/Settings.vue`
- `views/system/Logs.vue`

---

#### Week 11: 交互优化和细节完善

**任务**:
- [ ] 表单验证优化
- [ ] 提示信息优化
- [ ] 加载状态优化
- [ ] 空数据状态
- [ ] 错误提示优化
- [ ] 快捷键支持
- [ ] 国际化准备（i18n）
- [ ] 暗黑模式支持（可选）

---

### 阶段四：测试和部署（Week 12-13）

#### Week 12: 测试

**任务**:
- [ ] 单元测试（Vitest）
- [ ] 组件测试
- [ ] E2E测试（Cypress）
- [ ] 浏览器兼容性测试
- [ ] 响应式测试（移动端）
- [ ] 性能测试（Lighthouse）
- [ ] Bug修复

---

#### Week 13: 构建和部署

**任务**:
- [ ] 生产构建优化
- [ ] 代码分割优化
- [ ] 静态资源优化
- [ ] CDN配置
- [ ] Nginx配置
- [ ] Docker镜像构建
- [ ] CI/CD配置
- [ ] 部署文档

---

## 4. 核心模块开发

### 4.1 主入口文件

```typescript
// src/main.ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import './assets/styles/global.scss'

const app = createApp(App)

// 注册Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

app.mount('#app')
```

### 4.2 Axios封装

```typescript
// src/utils/request.ts
import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import router from '@/router'

// 创建axios实例
const service: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器
service.interceptors.request.use(
  (config) => {
    const userStore = useUserStore()
    const token = userStore.token

    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }

    return config
  },
  (error) => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
service.interceptors.response.use(
  (response: AxiosResponse) => {
    const { code, data, message } = response.data

    // 根据code判断响应状态
    if (code === 200 || code === 0) {
      return data
    } else {
      ElMessage.error(message || '请求失败')
      return Promise.reject(new Error(message || 'Error'))
    }
  },
  (error) => {
    console.error('Response error:', error)

    if (error.response) {
      const { status, data } = error.response

      switch (status) {
        case 401:
          ElMessage.error('未授权，请重新登录')
          // 清除token并跳转到登录页
          const userStore = useUserStore()
          userStore.logout()
          router.push('/login')
          break
        case 403:
          ElMessage.error('拒绝访问')
          break
        case 404:
          ElMessage.error('请求的资源不存在')
          break
        case 500:
          ElMessage.error('服务器错误')
          break
        default:
          ElMessage.error(data?.message || '请求失败')
      }
    } else if (error.request) {
      ElMessage.error('网络错误，请检查网络连接')
    } else {
      ElMessage.error('请求配置错误')
    }

    return Promise.reject(error)
  }
)

export default service
```

### 4.3 路由配置

```typescript
// src/router/index.ts
import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import BlankLayout from '@/layouts/BlankLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/Index.vue'),
    meta: { layout: BlankLayout, requiresAuth: false },
  },
  {
    path: '/',
    redirect: '/dashboard',
    component: DefaultLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/Index.vue'),
        meta: { title: '仪表盘', icon: 'DataLine' },
      },
      {
        path: 'sms',
        name: 'SMS',
        meta: { title: '短信管理', icon: 'Message' },
        children: [
          {
            path: 'send',
            name: 'SMSSend',
            component: () => import('@/views/sms/Send.vue'),
            meta: { title: '发送短信' },
          },
          {
            path: 'records',
            name: 'SMSRecords',
            component: () => import('@/views/sms/Records.vue'),
            meta: { title: '发送记录' },
          },
        ],
      },
      {
        path: 'channels',
        name: 'Channels',
        component: () => import('@/views/channels/List.vue'),
        meta: { title: '通道管理', icon: 'Connection' },
      },
      {
        path: 'pricing',
        name: 'Pricing',
        component: () => import('@/views/pricing/Rules.vue'),
        meta: { title: '计费管理', icon: 'Money' },
      },
      {
        path: 'senderids',
        name: 'SenderIDs',
        component: () => import('@/views/senderids/List.vue'),
        meta: { title: '发送方ID', icon: 'Postcard' },
      },
      {
        path: 'account',
        name: 'Account',
        component: () => import('@/views/account/List.vue'),
        meta: { title: '账户管理', icon: 'User' },
      },
      {
        path: 'reports',
        name: 'Reports',
        component: () => import('@/views/reports/Overview.vue'),
        meta: { title: '报表统计', icon: 'DataAnalysis' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth !== false)

  if (requiresAuth && !userStore.token) {
    // 需要登录但未登录，跳转到登录页
    next({
      path: '/login',
      query: { redirect: to.fullPath },
    })
  } else if (to.path === '/login' && userStore.token) {
    // 已登录访问登录页，跳转到首页
    next('/dashboard')
  } else {
    next()
  }
})

export default router
```

### 4.4 用户状态管理

```typescript
// src/stores/user.ts
import { defineStore } from 'pinia'
import { login as loginApi, getUserInfo } from '@/api/admin'
import { getToken, setToken, removeToken } from '@/utils/auth'

interface UserState {
  token: string
  userInfo: any
  permissions: string[]
}

export const useUserStore = defineStore('user', {
  state: (): UserState => ({
    token: getToken() || '',
    userInfo: null,
    permissions: [],
  }),

  actions: {
    // 登录
    async login(username: string, password: string) {
      try {
        const res = await loginApi({ username, password })
        this.token = res.token
        setToken(res.token)
        return Promise.resolve()
      } catch (error) {
        return Promise.reject(error)
      }
    },

    // 获取用户信息
    async fetchUserInfo() {
      try {
        const res = await getUserInfo()
        this.userInfo = res.userInfo
        this.permissions = res.permissions
        return Promise.resolve(res)
      } catch (error) {
        return Promise.reject(error)
      }
    },

    // 退出登录
    logout() {
      this.token = ''
      this.userInfo = null
      this.permissions = []
      removeToken()
    },
  },

  getters: {
    isLoggedIn: (state) => !!state.token,
    hasPermission: (state) => (permission: string) => {
      return state.permissions.includes(permission)
    },
  },
})
```

### 4.5 短信发送API

```typescript
// src/api/sms.ts
import request from '@/utils/request'

export interface SendSMSRequest {
  phone_number: string
  message: string
  sender_id?: string
  channel?: string
}

export interface SendSMSResponse {
  message_id: string
  status: string
  pricing: {
    total_cost: number
    currency: string
    message_count: number
  }
}

// 发送短信
export function sendSMS(data: SendSMSRequest) {
  return request<SendSMSResponse>({
    url: '/api/v1/sms/send',
    method: 'post',
    data,
  })
}

// 查询发送记录
export function getSMSRecords(params: any) {
  return request({
    url: '/api/v1/sms/records',
    method: 'get',
    params,
  })
}

// 查询短信状态
export function getSMSStatus(messageId: string) {
  return request({
    url: `/api/v1/sms/status/${messageId}`,
    method: 'get',
  })
}
```

### 4.6 仪表盘页面示例

```vue
<!-- src/views/dashboard/Index.vue -->
<template>
  <div class="dashboard">
    <!-- 关键指标卡片 -->
    <el-row :gutter="20" class="metrics-row">
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card class="metric-card">
          <div class="metric-icon">
            <el-icon :size="40" color="#409EFF"><Message /></el-icon>
          </div>
          <div class="metric-content">
            <div class="metric-value">{{ todayStats.sent }}</div>
            <div class="metric-label">今日发送</div>
            <div class="metric-trend" :class="{ positive: todayStats.sentTrend > 0 }">
              <el-icon><ArrowUp v-if="todayStats.sentTrend > 0" /><ArrowDown v-else /></el-icon>
              {{ Math.abs(todayStats.sentTrend) }}%
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="12" :lg="6">
        <el-card class="metric-card">
          <div class="metric-icon success">
            <el-icon :size="40" color="#67C23A"><Check /></el-icon>
          </div>
          <div class="metric-content">
            <div class="metric-value">{{ todayStats.successRate }}%</div>
            <div class="metric-label">成功率</div>
            <div class="metric-trend positive">
              <el-icon><ArrowUp /></el-icon>
              {{ todayStats.successRateTrend }}%
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="12" :lg="6">
        <el-card class="metric-card">
          <div class="metric-icon warning">
            <el-icon :size="40" color="#E6A23C"><Clock /></el-icon>
          </div>
          <div class="metric-content">
            <div class="metric-value">{{ todayStats.pending }}</div>
            <div class="metric-label">待发送</div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="12" :lg="6">
        <el-card class="metric-card">
          <div class="metric-icon danger">
            <el-icon :size="40" color="#F56C6C"><Wallet /></el-icon>
          </div>
          <div class="metric-content">
            <div class="metric-value">¥{{ todayStats.balance }}</div>
            <div class="metric-label">账户余额</div>
            <el-tag v-if="todayStats.lowBalance" type="danger" size="small">余额不足</el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 趋势图表 -->
    <el-row :gutter="20" class="charts-row">
      <el-col :span="16">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>发送量趋势（近7天）</span>
              <el-button size="small" @click="refreshChart">刷新</el-button>
            </div>
          </template>
          <line-chart :data="chartData" height="300px" />
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card>
          <template #header>国家分布 Top 5</template>
          <div class="country-list">
            <div v-for="(item, index) in countryStats" :key="index" class="country-item">
              <span class="country-flag">{{ item.flag }}</span>
              <span class="country-name">{{ item.name }}</span>
              <el-progress :percentage="item.percentage" :stroke-width="10" />
              <span class="country-count">{{ item.count }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 通道状态 -->
    <el-row>
      <el-col :span="24">
        <el-card>
          <template #header>通道状态</template>
          <el-table :data="channelStats" style="width: 100%">
            <el-table-column prop="name" label="通道名称" />
            <el-table-column label="状态">
              <template #default="{ row }">
                <el-tag :type="row.status === 'online' ? 'success' : 'danger'">
                  {{ row.status === 'online' ? '在线' : '离线' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="tps" label="当前TPS" />
            <el-table-column prop="successRate" label="成功率" />
            <el-table-column prop="avgLatency" label="平均延迟（ms）" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getDashboardStats } from '@/api/report'
import LineChart from '@/components/charts/LineChart.vue'

const todayStats = ref({
  sent: 12543,
  sentTrend: 15.3,
  successRate: 98.5,
  successRateTrend: 2.1,
  pending: 342,
  balance: 8520,
  lowBalance: false,
})

const chartData = ref({
  labels: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
  datasets: [
    {
      label: '发送量',
      data: [8000, 9500, 10200, 12000, 11500, 13000, 12543],
    },
  ],
})

const countryStats = ref([
  { flag: '🇨🇳', name: '中国', count: 5230, percentage: 42 },
  { flag: '🇺🇸', name: '美国', count: 2150, percentage: 17 },
  { flag: '🇮🇳', name: '印度', count: 1890, percentage: 15 },
  { flag: '🇬🇧', name: '英国', count: 980, percentage: 8 },
  { flag: '🇩🇪', name: '德国', count: 750, percentage: 6 },
])

const channelStats = ref([])

const fetchData = async () => {
  // 获取仪表盘数据
  const data = await getDashboardStats()
  // 更新数据...
}

const refreshChart = () => {
  fetchData()
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped lang="scss">
.dashboard {
  padding: 20px;

  .metrics-row {
    margin-bottom: 20px;
  }

  .metric-card {
    display: flex;
    align-items: center;

    .metric-icon {
      margin-right: 20px;
    }

    .metric-content {
      flex: 1;

      .metric-value {
        font-size: 32px;
        font-weight: bold;
        color: #303133;
      }

      .metric-label {
        font-size: 14px;
        color: #909399;
        margin-top: 8px;
      }

      .metric-trend {
        margin-top: 8px;
        font-size: 12px;
        color: #F56C6C;

        &.positive {
          color: #67C23A;
        }
      }
    }
  }

  .charts-row {
    margin-bottom: 20px;
  }

  .country-list {
    .country-item {
      display: flex;
      align-items: center;
      margin-bottom: 15px;

      .country-flag {
        font-size: 24px;
        margin-right: 10px;
      }

      .country-name {
        width: 60px;
      }

      .el-progress {
        flex: 1;
        margin: 0 15px;
      }

      .country-count {
        width: 60px;
        text-align: right;
      }
    }
  }
}
</style>
```

---

## 5. UI设计规范

### 5.1 颜色规范

```scss
// src/assets/styles/variables.scss
$primary-color: #409EFF;
$success-color: #67C23A;
$warning-color: #E6A23C;
$danger-color: #F56C6C;
$info-color: #909399;

$text-primary: #303133;
$text-regular: #606266;
$text-secondary: #909399;
$text-placeholder: #C0C4CC;

$border-base: #DCDFE6;
$border-light: #E4E7ED;
$border-lighter: #EBEEF5;
$border-extra-light: #F2F6FC;

$background-base: #F5F7FA;
```

### 5.2 字体规范

- 标题: PingFang SC, Microsoft YaHei
- 正文: 14px
- 小字: 12px
- 大标题: 20px / 24px

### 5.3 间距规范

- 小间距: 8px
- 中间距: 16px
- 大间距: 24px
- 特大间距: 32px

---

## 6. 部署计划

### 6.1 构建配置

```typescript
// vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    minify: 'terser',
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          'element-plus': ['element-plus'],
          'echarts': ['echarts', 'vue-echarts'],
        },
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

### 6.2 Nginx配置

```nginx
server {
    listen 80;
    server_name sms-admin.example.com;
    
    root /usr/share/nginx/html;
    index index.html;
    
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    location /api {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # Gzip压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
    
    # 缓存静态资源
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### 6.3 Docker构建

```dockerfile
# Dockerfile
FROM node:18-alpine as builder

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

---

## 附录

### A. 常用命令

```bash
# 开发
npm run dev

# 构建
npm run build

# 预览构建结果
npm run preview

# 代码检查
npm run lint

# 代码格式化
npm run format

# 类型检查
npm run type-check
```

### B. 开发规范

1. 组件命名：PascalCase
2. 文件命名：PascalCase（组件）、kebab-case（工具）
3. 变量命名：camelCase
4. 常量命名：UPPER_SNAKE_CASE
5. CSS类名：kebab-case

---

**文档结束**

