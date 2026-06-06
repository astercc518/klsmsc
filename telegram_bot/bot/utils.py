import sys
import os
from typing import Any, Optional, Tuple, Dict

# 将 backend 目录添加到 path，以便可以直接引用 app 模块
from loguru import logger

# 不需要再添加 backend 到 sys.path，所有交互应通过 APIClient 进行
# logger 使用 loguru 直接初始化

async def log_outgoing_message(user_id: int, content: str, chat_id: Optional[int] = None):
    """记录发出消息异步助手"""
    from bot.services.message_service import MessageService
    await MessageService.log_outgoing(user_id, content, chat_id)

async def send_and_log(context: Any, chat_id: int, text: str, **kwargs):
    """发送并记录消息"""
    message = await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
    # 异步记录，不阻塞发送
    import asyncio
    asyncio.create_task(log_outgoing_message(chat_id, text, chat_id))
    return message

async def edit_and_log(query: Any, text: str, **kwargs):
    """编辑并记录消息"""
    message = await query.edit_message_text(text=text, **kwargs)
    # 异步记录
    import asyncio
    chat_id = query.message.chat_id if query.message else None
    user_id = query.from_user.id
    asyncio.create_task(log_outgoing_message(user_id, text, chat_id))
    return message

def is_internal_staff_from_verify(user_info: Optional[Dict]) -> bool:
    """判断 verify_user / verify_bot_user 返回的是否为员工（非绑定客户的 Telegram）。"""
    return bool(user_info and user_info.get("is_admin"))


# 全局唯一的国家中文名映射（ISO2 大写 → 中文）。
# 历史上 menu.py / account_opening.py / sms_test.py 各自维护了一份且互不同步，
# 导致部分国家（如 ZM 赞比亚、NP 尼泊尔）在某些开户流程里显示成裸代码或缺失。
# 此处为唯一数据源，所有 handler 统一从这里引用。
COUNTRY_NAMES: dict[str, str] = {
    "AF": "阿富汗", "AL": "阿尔巴尼亚", "DZ": "阿尔及利亚", "AO": "安哥拉",
    "AR": "阿根廷", "AU": "澳大利亚", "AT": "奥地利", "AZ": "阿塞拜疆",
    "BH": "巴林", "BD": "孟加拉国", "BY": "白俄罗斯", "BE": "比利时",
    "BJ": "贝宁", "BO": "玻利维亚", "BR": "巴西", "BN": "文莱",
    "BG": "保加利亚", "BF": "布基纳法索", "BI": "布隆迪", "KH": "柬埔寨",
    "CM": "喀麦隆", "CA": "加拿大", "CF": "中非", "CL": "智利",
    "CN": "中国", "CO": "哥伦比亚", "CD": "刚果(金)", "CG": "刚果(布)",
    "CR": "哥斯达黎加", "CI": "科特迪瓦", "HR": "克罗地亚", "CY": "塞浦路斯",
    "CZ": "捷克", "DK": "丹麦", "DJ": "吉布提", "DO": "多米尼加",
    "EC": "厄瓜多尔", "EG": "埃及", "SV": "萨尔瓦多", "ET": "埃塞俄比亚",
    "FI": "芬兰", "FR": "法国", "GA": "加蓬", "GM": "冈比亚",
    "GE": "格鲁吉亚", "DE": "德国", "GH": "加纳", "GR": "希腊",
    "GT": "危地马拉", "GN": "几内亚", "HT": "海地", "HN": "洪都拉斯",
    "HK": "香港", "HU": "匈牙利", "IN": "印度", "ID": "印度尼西亚",
    "IQ": "伊拉克", "IE": "爱尔兰", "IL": "以色列", "IT": "意大利",
    "JM": "牙买加", "JP": "日本", "JO": "约旦", "KZ": "哈萨克斯坦",
    "KE": "肯尼亚", "KW": "科威特", "KG": "吉尔吉斯斯坦", "LA": "老挝",
    "LB": "黎巴嫩", "LS": "莱索托", "LR": "利比里亚", "LY": "利比亚",
    "LT": "立陶宛", "MO": "澳门", "MG": "马达加斯加", "MW": "马拉维",
    "MY": "马来西亚", "MV": "马尔代夫", "ML": "马里", "MT": "马耳他",
    "MR": "毛里塔尼亚", "MX": "墨西哥", "MD": "摩尔多瓦", "MN": "蒙古",
    "MA": "摩洛哥", "MZ": "莫桑比克", "MM": "缅甸", "NA": "纳米比亚",
    "NP": "尼泊尔", "NL": "荷兰", "NZ": "新西兰", "NI": "尼加拉瓜",
    "NE": "尼日尔", "NG": "尼日利亚", "NO": "挪威", "OM": "阿曼",
    "PK": "巴基斯坦", "PA": "巴拿马", "PG": "巴布亚新几内亚", "PY": "巴拉圭",
    "PE": "秘鲁", "PH": "菲律宾", "PL": "波兰", "PT": "葡萄牙",
    "QA": "卡塔尔", "RO": "罗马尼亚", "RU": "俄罗斯", "RW": "卢旺达",
    "SA": "沙特阿拉伯", "SN": "塞内加尔", "RS": "塞尔维亚", "SL": "塞拉利昂",
    "SO": "索马里", "ZA": "南非", "KR": "韩国", "SS": "南苏丹",
    "ES": "西班牙", "LK": "斯里兰卡", "SD": "苏丹", "SE": "瑞典",
    "CH": "瑞士", "SY": "叙利亚", "TW": "台湾", "TZ": "坦桑尼亚",
    "TH": "泰国", "TL": "东帝汶", "TG": "多哥", "TT": "特立尼达",
    "TN": "突尼斯", "TR": "土耳其", "TM": "土库曼斯坦", "UG": "乌干达",
    "UA": "乌克兰", "AE": "阿联酋", "GB": "英国", "US": "美国",
    "UY": "乌拉圭", "UZ": "乌兹别克斯坦", "VE": "委内瑞拉", "VN": "越南",
    "YE": "也门", "ZM": "赞比亚", "ZW": "津巴布韦",
    "SG": "新加坡",
}


def country_label(code: str) -> str:
    """ISO2 代码 → 中文名；无映射时回退原代码。'*' 表示全球。"""
    if not code:
        return code
    if code == "*":
        return "全球（所有国家）"
    return COUNTRY_NAMES.get(str(code).upper(), code)


def dedupe_country_codes_from_templates(raw_codes: list) -> list[str]:
    """
    开户模板国家列表去重：同一国家码只保留一条（避免 distinct(country_code, country_name) 产生重复按钮），
    并合并大小写差异（如 id / ID），统一使用大写 ISO 码。
    返回顺序按中文名排序（'*' 全球置顶），比按 ISO 代码排序更直观，避免如「赞比亚」被甩到列表最末难以查找。
    """
    by_upper: dict[str, str] = {}
    for c in raw_codes:
        if c is None:
            continue
        s = str(c).strip()
        if not s:
            continue
        u = s.upper()
        by_upper.setdefault(u, u)
    # '*'（全球）排最前；其余按中文名排序，未知名回退用代码本身参与排序
    return sorted(by_upper.keys(), key=lambda c: (c != "*", country_label(c)))


async def get_group_ids() -> dict:
    """
    从后端 API 读取各 TG 群组 ID（回退环境变量）
    返回 {'tech_group_id': '...', 'billing_group_id': '...', 'admin_group_id': '...'}
    """
    from bot.services.api_client import APIClient
    
    # 基础环境变量回退
    ids = {
        'admin_group_id': os.getenv('TELEGRAM_ADMIN_GROUP_ID', ''),
        'tech_group_id': os.getenv('STAFF_GROUP_ID', ''),
        'billing_group_id': '',
    }
    
    try:
        api = APIClient()
        settings = await api.get_internal_settings()
        if settings:
            if settings.get('admin_group_id'):
                ids['admin_group_id'] = settings['admin_group_id']
            if settings.get('tech_group_id'):
                ids['tech_group_id'] = settings['tech_group_id']
            if settings.get('billing_group_id'):
                ids['billing_group_id'] = settings['billing_group_id']
    except Exception as e:
        logger.warning(f"从 API 读取群组 ID 配置失败，使用环境变量: {e}")
        
    return ids

async def get_user_binding_internal(tg_id: int) -> Optional[Dict]:
    """通过 API 获取用户绑定信息"""
    from bot.services.api_client import APIClient
    api = APIClient()
    user_info = await api.verify_user(tg_id)
    if user_info and user_info.get("role") == "customer":
        return user_info
    return None
