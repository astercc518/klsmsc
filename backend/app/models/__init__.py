"""数据模型"""
# Common Module
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser
from app.modules.common.api_key import ApiKey
from app.modules.common.balance_log import BalanceLog
from app.modules.common.ticket import Ticket, TicketReply, TicketTemplate
from app.modules.common.telegram_binding import TelegramBinding
from app.modules.common.telegram_user import TelegramUser
from app.modules.common.system_config import SystemConfig
from app.modules.common.invitation_code import InvitationCode
from app.modules.common.account_template import AccountTemplate
from app.modules.common.recharge_order import RechargeOrder
from app.modules.common.package import Package, AccountPackage
from app.modules.common.security_log import SecurityLog, LoginAttempt
from app.modules.common.notification import Notification

# SMS Module
from app.modules.sms.channel import Channel
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.country_pricing import CountryPricing
from app.modules.sms.sms_batch import SmsBatch
from app.modules.sms.sms_template import SmsTemplate
from app.modules.sms.channel_relations import ChannelCountry, ChannelCountrySenderId
from app.modules.sms.supplier import Supplier, SupplierChannel, SupplierRate, SellRate, RateDeck, AccountRateDeck

# Data Module
from app.modules.data.models import DataNumber, DataProduct, DataOrder, DataImportBatch, DataOrderNumber, DataPricingTemplate
from app.modules.data.data_account import DataAccount, DataExtractionLog

# Voice Module (New)
from app.modules.voice.models import VoiceRoute, VoiceCall

# Legacy/Unmoved (if any)
from app.modules.common.account_pricing import AccountPricing
from app.models.scheduled_task import ScheduledTask
from app.models.sub_account import SubAccount
from app.models.settlement import Settlement, SettlementDetail, SettlementLog, CustomerBill, CustomerBillDetail, ProfitReport

__all__ = [
    "Account",
    "Channel",
    "SMSLog",
    "CountryPricing",
    "BalanceLog",
    "AdminUser",
    "TelegramUser",
    "InvitationCode",
    "RechargeOrder",
    "AccountPricing",
    "TelegramBinding",
    "SmsBatch",
    "SmsTemplate",
    "ApiKey",
    "ScheduledTask",
    "SubAccount",
    "Package",
    "AccountPackage",
    "SecurityLog",
    "LoginAttempt",
    "Notification",
    # 供应商管理
    "Supplier",
    "SupplierChannel",
    "SupplierRate",
    "SellRate",
    "RateDeck",
    "AccountRateDeck",
    # 工单系统
    "Ticket",
    "TicketReply",
    "TicketTemplate",
    # 结算系统
    "Settlement",
    "SettlementDetail",
    "SettlementLog",
    "CustomerBill",
    "CustomerBillDetail",
    "ProfitReport",
    # 数据业务模块
    "DataNumber",
    "DataProduct",
    "DataOrder",
    "DataOrderNumber",
    "DataImportBatch",
    "DataAccount",
    "DataExtractionLog",
    "DataPricingTemplate",
    # 通道关系模块
    "ChannelCountry",
    "ChannelCountrySenderId",
    # 语音模块
    "VoiceRoute",
    "VoiceCall",
    "VoiceAccount",
    "VoiceRechargeLog",
    # 开户模板
    "AccountTemplate"
]
