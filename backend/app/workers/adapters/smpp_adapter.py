"""
SMPP通道适配器
"""
import asyncio
import threading
from typing import Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.channel import Channel
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 全局线程池（用于运行同步SMPP操作）
_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="smpp")


class SMPPAdapter:
    """SMPP通道适配器"""
    
    def __init__(self, channel: Channel):
        self.channel = channel
        self.client = None
        self.connected = False
        self._lock = threading.Lock()
    
    async def connect(self) -> bool:
        """连接SMPP服务器（异步包装）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._connect_sync)
    
    def _connect_sync(self) -> bool:
        """同步连接SMPP服务器"""
        try:
            import smpplib.client
            import smpplib.consts
            
            logger.info(f"连接SMPP服务器: {self.channel.host}:{self.channel.port}")
            
            # 创建SMPP客户端
            self.client = smpplib.client.Client(
                self.channel.host,
                self.channel.port,
                allow_unknown_opt_params=True
            )
            
            # 连接
            self.client.connect()
            logger.debug(f"SMPP TCP连接成功: {self.channel.host}:{self.channel.port}")
            
            # 绑定（使用Transceiver模式，可以发送和接收）
            self.client.bind_transceiver(
                system_id=self.channel.username,
                password=self.channel.password
            )
            
            self.connected = True
            logger.info(f"SMPP绑定成功: {self.channel.channel_code}")
            
            # 启动心跳任务（在后台线程中）
            threading.Thread(
                target=self._heartbeat_loop,
                daemon=True,
                name=f"smpp-heartbeat-{self.channel.id}"
            ).start()
            
            return True
            
        except ImportError:
            logger.warning("smpplib未安装，使用模拟模式")
            # 模拟模式
            self.connected = True
            logger.info(f"SMPP连接成功（模拟）: {self.channel.channel_code}")
            return True
        except Exception as e:
            logger.error(f"SMPP连接失败: {str(e)}", exc_info=e)
            self.connected = False
            return False
    
    def _heartbeat_loop(self):
        """心跳保活循环（在后台线程中运行）"""
        import time
        import smpplib.client
        
        while self.connected and self.client:
            try:
                time.sleep(30)  # 每30秒发送一次心跳
                if self.client:
                    # 发送enquire_link
                    self.client.enquire_link()
                    logger.debug(f"SMPP心跳发送: {self.channel.channel_code}")
            except Exception as e:
                logger.warning(f"SMPP心跳失败: {str(e)}")
                # 心跳失败，标记为断开
                self.connected = False
                # 尝试重连
                try:
                    time.sleep(5)
                    self._connect_sync()
                except Exception as reconnect_error:
                    logger.error(f"SMPP重连失败: {str(reconnect_error)}")
                    break
    
    async def send(self, sms_log: SMSLog) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        发送短信（异步包装）
        
        Returns:
            (成功标志, 通道消息ID, 错误信息)
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._send_sync, sms_log)
    
    def _send_sync(self, sms_log: SMSLog) -> Tuple[bool, Optional[str], Optional[str]]:
        """同步发送短信"""
        try:
            # 确保已连接
            if not self.connected or not self.client:
                if not self._connect_sync():
                    return False, None, "SMPP connection failed"
            
            # 检查是否安装了smpplib
            try:
                import smpplib.gsm
                import smpplib.consts
            except ImportError:
                # 模拟模式
                message_id = f"smpp_{sms_log.message_id[:16]}"
                logger.info(f"SMPP发送成功（模拟）: {message_id}")
                return True, message_id, None
            
            # 处理长短信拆分
            parts, encoding_flag, msg_type_flag = smpplib.gsm.make_parts(sms_log.message)
            
            message_ids = []
            
            # 获取发送方ID（优先使用通道默认发送方ID）
            sender_id = self.channel.default_sender_id or ""
            
            for i, part in enumerate(parts):
                try:
                    # gsm.make_parts 返回 bytes，不需要再编码
                    # encoding_flag: 0=GSM-7, 8=UCS-2
                    
                    # 发送短信
                    pdu = self.client.send_message(
                        source_addr_ton=smpplib.consts.SMPP_TON_ALNUM if sender_id else smpplib.consts.SMPP_TON_INTL,
                        source_addr_npi=smpplib.consts.SMPP_NPI_UNK,
                        source_addr=sender_id,
                        dest_addr_ton=smpplib.consts.SMPP_TON_INTL,
                        dest_addr_npi=smpplib.consts.SMPP_NPI_ISDN,
                        destination_addr=sms_log.phone_number.lstrip('+'),  # 移除+号
                        short_message=part,  # make_parts 已返回 bytes
                        data_coding=encoding_flag,
                        esm_class=msg_type_flag,
                        registered_delivery=1  # 请求送达回执
                    )
                    
                    # send_message 返回 SubmitSM 对象，使用 sequence 作为消息标识
                    # 实际的 message_id 会在响应中返回，这里先用 sequence
                    message_id = str(pdu.sequence) if hasattr(pdu, 'sequence') else f"smpp_{i}"
                    message_ids.append(message_id)
                    logger.info(f"SMPP发送部分 {i+1}/{len(parts)}: sequence={message_id}")
                    
                except Exception as e:
                    error_msg = f"发送部分 {i+1} 失败: {str(e)}"
                    logger.error(error_msg, exc_info=e)
                    return False, None, error_msg
            
            # 返回第一个消息ID（或合并的消息ID）
            final_message_id = message_ids[0] if message_ids else None
            logger.info(f"SMPP发送成功: {sms_log.message_id} -> {final_message_id}")
            return True, final_message_id, None
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"SMPP发送失败: {error_msg}", exc_info=e)
            self.connected = False
            return False, None, error_msg
    
    async def disconnect(self):
        """断开连接（异步包装）"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, self._disconnect_sync)
    
    def _disconnect_sync(self):
        """同步断开连接"""
        try:
            with self._lock:
                if self.client:
                    try:
                        import smpplib.client
                        self.client.unbind()
                        self.client.disconnect()
                    except ImportError:
                        pass  # 模拟模式
                    except Exception as e:
                        logger.warning(f"关闭SMPP连接时出错: {str(e)}")
                    
                    self.client = None
                    self.connected = False
                    logger.info(f"SMPP连接已关闭: {self.channel.channel_code}")
        except Exception as e:
            logger.error(f"断开SMPP连接失败: {str(e)}")
    
    def __del__(self):
        """析构时断开连接"""
        if self.client:
            try:
                self._disconnect_sync()
            except:
                pass
