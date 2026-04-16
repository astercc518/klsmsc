from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.utils import logger
from bot.services.api_client import APIClient

api = APIClient()

async def get_user_role(tg_id: int) -> str:
    """获取用户角色"""
    res = await api.get_user_role(tg_id)
    if res.get("success"):
        return res.get("role", "guest")
    return "guest"


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理/help命令 - 根据用户角色显示帮助"""
    user = update.effective_user
    logger.info(f"用户 {user.id} 查看帮助")
    
    role = await get_user_role(user.id)
    
    # 基础帮助
    base_help = """
🤖 *TG业务助手*

欢迎使用TG业务助手！本助手支持短信、语音、数据三大业务的全流程管理。

"""
    
    # 客户帮助
    customer_help = """
👤 *客户功能*

*📱 业务发送*
/send - 交互式发送短信/语音
/quick <号码> <内容> - 快速发送
/history - 查看发送记录
/mass - 群发任务

*💰 账户管理*
/start - 查看账户状态
/balance - 查询余额
/recharge - 申请充值

*📋 工单服务*
/ticket - 创建工单
  ├ 📝 测试申请 - 业务测试请求
  ├ 🔧 技术支持 - 技术问题反馈
  ├ 💳 账务问题 - 充值/扣费问题
  └ 💬 意见反馈 - 其他建议
/tickets - 我的工单列表

"""
    
    # 销售帮助
    sales_help = """
💼 *销售功能*

*🎯 开户邀请*
/invite - 创建开户邀请码
  1. 选择业务类型（短信/语音/数据）
  2. 选择国家/地区
  3. 选择资费模板
  4. 输入单价
  5. 生成邀请链接

*📊 客户管理*
/my\\_customers - 我的客户列表
/customer\\_stats - 客户统计

*💰 佣金查询*
/commission - 查看本月佣金

"""
    
    # 技术/审核帮助
    tech_help = """
🔧 *技术/审核功能*

*📋 审核操作*
/approve <工单号> [备注] - 通过测试申请
/reject <工单号> <原因> - 拒绝测试申请
/pending - 待审核工单列表

*💳 充值确认*
/confirm\\_recharge <工单号> - 确认充值到账
/reject\\_recharge <工单号> <原因> - 拒绝充值

"""
    
    # 财务帮助
    finance_help = """
💳 *财务功能*

*💰 充值审核*
/recharge\\_list - 待审核充值列表
/approve\\_recharge <工单号> - 通过充值申请
/reject\\_recharge <工单号> <原因> - 拒绝充值

*📊 财务报表*
/finance\\_stats - 财务统计

"""
    
    # 通用帮助
    common_help = """
*📌 通用命令*
/start - 开始使用
/help - 查看帮助
/cancel - 取消当前操作

*🔄 业务流程*

1️⃣ *开户流程*
销售发起邀请 → 客户点击链接 → 自动开通账户

2️⃣ *测试流程*
客户/销售提交测试工单 → 转发供应商群 → 技术审批 → 执行测试

3️⃣ *充值流程*
客户/销售发起充值 → 上传凭证 → 财务确认 → 技术同步 → 余额到账

4️⃣ *问题反馈*
客户/销售提交工单 → 技术/供应商处理 → 回复解决

*📞 联系客服*
遇到问题请使用 /ticket 提交工单
"""
    
    # 根据角色组合帮助内容
    help_text = base_help
    
    if role == 'guest':
        help_text += """
⚠️ *您尚未绑定账户*

请通过销售获取邀请链接，或联系客服开通账户。
"""
    elif role == 'customer':
        help_text += customer_help
    elif role == 'sales':
        help_text += sales_help + customer_help
    elif role in ['tech', 'admin', 'super_admin']:
        help_text += tech_help + sales_help + customer_help
    elif role == 'finance':
        help_text += finance_help + customer_help
    
    help_text += common_help
    
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def sales_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """销售专用帮助 /sales_help"""
    help_text = """
💼 *销售操作指南*

*🎯 第一步：绑定销售账号*
```
/bind_sales 用户名 密码
```

*🎯 第二步：创建开户邀请*
```
/invite
```
按提示选择：
1. 业务类型（短信/语音/数据）
2. 国家/地区
3. 资费模板
4. 输入客户单价

*🎯 第三步：发送邀请链接*
系统会生成专属邀请链接，发送给客户点击即可自动开户

*📊 客户统计*
```
/my_customers
```

*💰 佣金查看*
```
/commission
```

*🔔 提示*
- 客户通过您的邀请开户后，自动关联为您的客户
- 客户充值消费产生的佣金自动计入您的账户
- 每月15日结算上月佣金
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def tech_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """技术/审核专用帮助 /tech_help"""
    help_text = """
🔧 *技术审核操作指南*

*📋 测试工单审核*

当客户或销售提交测试工单后，工单会自动转发到对应的供应商群。

*通过测试申请：*
```
/approve TK2024XXXXXX 测试通过，可正常使用
```

*拒绝测试申请：*
```
/reject TK2024XXXXXX 号码格式错误，请修正后重新提交
```

*💳 充值确认*

财务审核通过后，技术需确认同步：
```
/confirm_recharge RCH2024XXXXXX
```

*📊 待处理列表*
```
/pending
```

*🔔 工单处理流程*
1. 收到测试工单通知
2. 联系供应商进行测试
3. 根据结果通过或拒绝
4. 系统自动通知客户
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')
