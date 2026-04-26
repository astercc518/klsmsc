/**
 * 系统配置项元数据中心
 *
 * 后端 system_config 表只存原始 (key, value, type, category)，
 * UI 展示所需的中文标签、提示语、控件类型、校验规则、是否需要重启等
 * 全部由本文件定义。
 *
 * 新增配置项：
 *   1. 后端先 INSERT 到 system_config 表
 *   2. 这里加一条 meta 定义
 *   3. 缺失 meta 时 UI 会用兜底渲染（label=key、uiType=string）
 */

export type ConfigUIType = 'boolean' | 'number' | 'string' | 'text' | 'sensitive' | 'enum'
export type ConfigGroup = 'basic' | 'sms' | 'notification' | 'telegram' | 'security'

export interface ConfigOption {
  label: string
  value: string | number
}

export interface ConfigValidation {
  min?: number
  max?: number
  step?: number
  pattern?: RegExp
  required?: boolean
}

export interface ConfigMeta {
  /** 中文标签（UI 展示） */
  label: string
  /** 字段提示（el-tooltip / placeholder 用） */
  hint?: string
  /** 主分类（左侧导航） */
  group: ConfigGroup
  /** 子组 key（同一卡片内） */
  subgroup: string
  /** 控件类型 */
  uiType: ConfigUIType
  /** enum 类型必填的选项 */
  options?: ConfigOption[]
  /** 数值/字符串校验 */
  validation?: ConfigValidation
  /** 改后是否需要重启服务 */
  restartRequired?: boolean
  /** 重启提示（含建议命令） */
  restartHint?: string
  /** 占位符 */
  placeholder?: string
  /** text 类型可选最大字符数（仅展示用） */
  maxLength?: number
}

export interface GroupDescriptor {
  key: ConfigGroup
  label: string
  icon: string
  /** 子组顺序与中文名 */
  subgroups: Array<{ key: string; label: string; description?: string }>
}

/* ================================================================
 * 主分类导航 + 子组顺序
 * ================================================================ */
export const CONFIG_GROUPS: GroupDescriptor[] = [
  {
    key: 'basic',
    label: '基础与限流',
    icon: 'Setting',
    subgroups: [
      { key: 'general', label: '通用设置', description: '币种、API 全局限流' },
    ],
  },
  {
    key: 'sms',
    label: '短信与回调',
    icon: 'Message',
    subgroups: [
      { key: 'content', label: '内容限制' },
      { key: 'callback', label: '回调设置', description: 'DLR 回调相关' },
    ],
  },
  {
    key: 'notification',
    label: '通知告警',
    icon: 'BellFilled',
    subgroups: [
      { key: 'balance', label: '余额监控' },
    ],
  },
  {
    key: 'telegram',
    label: 'Telegram 业务助手',
    icon: 'ChatDotRound',
    subgroups: [
      { key: 'credentials', label: 'Bot 凭证', description: '从 @BotFather 获取的访问凭证' },
      { key: 'features', label: '功能开关' },
      { key: 'limits', label: '阈值与限额' },
      { key: 'templates', label: '消息模板' },
      { key: 'webhook', label: 'Webhook（可选）' },
      { key: 'groups', label: '通知群组' },
    ],
  },
  {
    key: 'security',
    label: '安全策略',
    icon: 'Lock',
    subgroups: [
      { key: 'rate_limit', label: 'API 限流' },
      { key: 'login', label: '登录与密码策略' },
      { key: 'token', label: 'Token 有效期' },
      { key: 'access', label: '访问控制' },
    ],
  },
]

/* ================================================================
 * 33 个配置项的元数据
 * ================================================================ */
export const SYSTEM_CONFIG_META: Record<string, ConfigMeta> = {
  // ---- 基础 ----
  default_currency: {
    label: '默认币种',
    hint: '账户和价格的默认显示货币',
    group: 'basic', subgroup: 'general',
    uiType: 'enum',
    options: [
      { label: '美元 USD', value: 'USD' },
      { label: '人民币 CNY', value: 'CNY' },
      { label: '欧元 EUR', value: 'EUR' },
      { label: '印度卢比 INR', value: 'INR' },
    ],
  },
  default_rate_limit: {
    label: '默认请求限制（次/分钟）',
    hint: '账户未单独配置时的默认 API 调用频率',
    group: 'basic', subgroup: 'general',
    uiType: 'number',
    validation: { min: 1, max: 100000, step: 10 },
  },

  // ---- 短信 ----
  sms_max_length: {
    label: '短信最大字符数',
    hint: '超过将被拒绝。GSM-7 一条 160 字符，UCS-2 一条 70 字符',
    group: 'sms', subgroup: 'content',
    uiType: 'number',
    validation: { min: 1, max: 5000, step: 1 },
  },
  enable_callback: {
    label: '启用 DLR 回调',
    hint: '关闭后将不向客户回调送达回执',
    group: 'sms', subgroup: 'callback',
    uiType: 'boolean',
  },
  callback_retry_times: {
    label: '回调重试次数',
    hint: '回调失败后的最大重试次数',
    group: 'sms', subgroup: 'callback',
    uiType: 'number',
    validation: { min: 0, max: 10, step: 1 },
  },

  // ---- 通知告警 ----
  low_balance_alert_threshold: {
    label: '低余额告警阈值',
    hint: '账户余额低于此值（USD）时触发告警',
    group: 'notification', subgroup: 'balance',
    uiType: 'number',
    validation: { min: 0, max: 100000, step: 10 },
  },

  // ---- Telegram 凭证 ----
  telegram_bot_token: {
    label: 'Bot Token',
    hint: '从 @BotFather 获取，泄露后需立即吊销',
    group: 'telegram', subgroup: 'credentials',
    uiType: 'sensitive',
    restartRequired: true,
    restartHint: '修改后需重启 telegram-bot 容器（docker compose restart bot）',
  },
  telegram_bot_username: {
    label: 'Bot 用户名',
    hint: '不带 @ 前缀，例如 kaolachbot',
    group: 'telegram', subgroup: 'credentials',
    uiType: 'string',
    placeholder: 'kaolachbot',
  },
  telegram_bot_status: {
    label: '运行状态',
    hint: 'maintenance 时 Bot 仅回复维护消息',
    group: 'telegram', subgroup: 'credentials',
    uiType: 'enum',
    options: [
      { label: '✅ 运行中 active', value: 'active' },
      { label: '⏸ 维护中 maintenance', value: 'maintenance' },
      { label: '⛔ 已停用 disabled', value: 'disabled' },
    ],
  },
  telegram_admin_group_id: {
    label: '管理员群组 ID',
    hint: '收到管理通知的群组，例如 -100xxxxxxxxxx',
    group: 'telegram', subgroup: 'groups',
    uiType: 'string',
    placeholder: '留空表示不通知',
  },
  telegram_tech_group_id: {
    label: '技术群组 ID',
    hint: '工单/告警转发的群组 ID',
    group: 'telegram', subgroup: 'groups',
    uiType: 'string',
    placeholder: '留空表示不转发',
  },
  telegram_notification_group_id: {
    label: '业务通知群组 ID',
    hint: '充值/重要业务事件通知群组',
    group: 'telegram', subgroup: 'groups',
    uiType: 'string',
    placeholder: '留空表示不通知',
  },

  // ---- Telegram 功能开关 ----
  telegram_enable_register: {
    label: '允许注册',
    hint: '关闭后用户无法通过 Bot 自助开户',
    group: 'telegram', subgroup: 'features',
    uiType: 'boolean',
  },
  telegram_enable_send_sms: {
    label: '允许发送短信',
    group: 'telegram', subgroup: 'features',
    uiType: 'boolean',
  },
  telegram_enable_balance_query: {
    label: '允许查询余额',
    group: 'telegram', subgroup: 'features',
    uiType: 'boolean',
  },
  telegram_enable_recharge: {
    label: '允许申请充值',
    group: 'telegram', subgroup: 'features',
    uiType: 'boolean',
  },
  telegram_enable_ticket: {
    label: '允许提交工单',
    group: 'telegram', subgroup: 'features',
    uiType: 'boolean',
  },
  telegram_enable_batch_review: {
    label: '允许批次复核',
    hint: '管理员审核大批量发送任务',
    group: 'telegram', subgroup: 'features',
    uiType: 'boolean',
  },

  // ---- Telegram 阈值 ----
  telegram_max_recipients: {
    label: '单次最大收件人数',
    hint: '通过 Bot 发送时的接收号码数上限',
    group: 'telegram', subgroup: 'limits',
    uiType: 'number',
    validation: { min: 1, max: 1000000, step: 100 },
  },
  telegram_daily_send_limit: {
    label: '每日发送总量上限',
    group: 'telegram', subgroup: 'limits',
    uiType: 'number',
    validation: { min: 1, max: 10000000, step: 1000 },
  },
  telegram_min_recharge_amount: {
    label: '最低充值金额（USD）',
    group: 'telegram', subgroup: 'limits',
    uiType: 'number',
    validation: { min: 0, max: 10000, step: 1 },
  },
  telegram_send_cooldown_seconds: {
    label: '发送冷却时间（秒）',
    hint: '同一用户两次发送之间的最小间隔',
    group: 'telegram', subgroup: 'limits',
    uiType: 'number',
    validation: { min: 0, max: 3600, step: 5 },
  },

  // ---- Telegram 消息模板 ----
  telegram_welcome_message: {
    label: '欢迎消息',
    hint: '用户首次启动 Bot 时收到的消息',
    group: 'telegram', subgroup: 'templates',
    uiType: 'text',
    maxLength: 4096,
  },
  telegram_help_message: {
    label: '帮助消息',
    hint: '用户发送 /help 时收到的消息',
    group: 'telegram', subgroup: 'templates',
    uiType: 'text',
    maxLength: 4096,
  },
  telegram_maintenance_message: {
    label: '维护消息',
    hint: 'Bot 状态为 maintenance 时统一回复',
    group: 'telegram', subgroup: 'templates',
    uiType: 'text',
    maxLength: 4096,
  },

  // ---- Telegram Webhook ----
  telegram_webhook_url: {
    label: 'Webhook URL',
    hint: '留空则使用 long-polling',
    group: 'telegram', subgroup: 'webhook',
    uiType: 'string',
    placeholder: 'https://example.com/tg-webhook',
    restartRequired: true,
    restartHint: '修改后需重启 bot 容器',
  },
  telegram_webhook_secret: {
    label: 'Webhook Secret',
    hint: 'X-Telegram-Bot-Api-Secret-Token 校验',
    group: 'telegram', subgroup: 'webhook',
    uiType: 'sensitive',
    restartRequired: true,
    restartHint: '修改后需重启 bot 容器',
  },

  // ---- 安全 ----
  api_rate_limit_per_minute: {
    label: 'API 全局限流（次/分钟）',
    hint: '所有 API 请求的总速率上限',
    group: 'security', subgroup: 'rate_limit',
    uiType: 'number',
    validation: { min: 10, max: 1000000, step: 100 },
  },
  max_login_attempts: {
    label: '登录失败锁定阈值',
    hint: '连续失败次数超过将锁定账户',
    group: 'security', subgroup: 'login',
    uiType: 'number',
    validation: { min: 1, max: 100, step: 1 },
  },
  login_lock_minutes: {
    label: '登录锁定时长（分钟）',
    hint: '触发锁定后多少分钟自动解锁',
    group: 'security', subgroup: 'login',
    uiType: 'number',
    validation: { min: 1, max: 10080, step: 5 },
  },
  password_min_length: {
    label: '密码最小长度',
    group: 'security', subgroup: 'login',
    uiType: 'number',
    validation: { min: 6, max: 64, step: 1 },
  },
  jwt_token_expire_hours: {
    label: 'JWT Token 有效期（小时）',
    hint: '管理员登录 Token 过期时间',
    group: 'security', subgroup: 'token',
    uiType: 'number',
    validation: { min: 1, max: 720, step: 1 },
    restartRequired: true,
    restartHint: '修改后需重启 api 容器才能生效（docker compose restart api）',
  },
  ip_whitelist_enabled: {
    label: '启用 IP 白名单',
    hint: '开启后非白名单 IP 将无法访问后台',
    group: 'security', subgroup: 'access',
    uiType: 'boolean',
    restartRequired: true,
    restartHint: '修改后需重启 api 容器',
  },
}

/* ================================================================
 * 工具函数
 * ================================================================ */

/** 取 meta，缺失时返回兜底（uiType=string，label=key） */
export function resolveMeta(key: string): ConfigMeta {
  const m = SYSTEM_CONFIG_META[key]
  if (m) return m
  // eslint-disable-next-line no-console
  console.warn(`[system_config_meta] 缺失 meta 定义: ${key}，使用兜底 string 渲染`)
  return {
    label: key,
    group: 'basic',
    subgroup: 'general',
    uiType: 'string',
  }
}

/** 给定 group key，返回该组下所有配置 key */
export function keysOfGroup(group: ConfigGroup): string[] {
  return Object.entries(SYSTEM_CONFIG_META)
    .filter(([_, m]) => m.group === group)
    .map(([k]) => k)
}

/** 解析后端字符串值到原生类型（用于初始化和提交前的格式化） */
export function parseValue(rawValue: string | null | undefined, uiType: ConfigUIType): any {
  if (rawValue === null || rawValue === undefined) {
    if (uiType === 'boolean') return false
    if (uiType === 'number') return 0
    return ''
  }
  if (uiType === 'boolean') {
    return ['true', '1', 'yes'].includes(String(rawValue).toLowerCase())
  }
  if (uiType === 'number') {
    const n = Number(rawValue)
    return Number.isFinite(n) ? n : 0
  }
  return String(rawValue)
}

/** 把原生值序列化为后端期望的字符串 */
export function serializeValue(value: any, uiType: ConfigUIType): string {
  if (uiType === 'boolean') return value ? 'true' : 'false'
  if (uiType === 'number') return String(value ?? 0)
  return String(value ?? '')
}

/** 是否敏感字段（与后端 _is_sensitive_key 保持一致） */
export function isSensitiveKey(key: string): boolean {
  return ['token', 'password', 'secret'].some(w => key.includes(w))
}
