"""
SMPP通道适配器 - 支持 transceiver / transmitter / receiver 绑定模式
含 deliver_sm (DLR) 回调处理
"""
import asyncio
import re
import threading
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.channel import Channel
from app.utils.logger import get_logger

logger = get_logger(__name__)

# SMPP DLR 回执格式解析正则
# 标准格式: id:XXX sub:001 dlvrd:001 submit date:YYMMDDHHMM done date:YYMMDDHHMM stat:DELIVRD err:000 text:...
_DLR_PATTERN = re.compile(
    r'id:(?P<id>\S+)\s+sub:\d+\s+dlvrd:\d+\s+'
    r'submit date:(?P<submit>\d+)\s+done date:(?P<done>\d+)\s+'
    r'stat:(?P<stat>\w+)\s+err:(?P<err>\d+)',
    re.IGNORECASE
)
# 备用格式：部分供应商使用简化格式，如 id:3 stat:DELIVRD 或 id:3 ... stat:DELIVRD err:000 或 stat:DELIVRD 000
_DLR_PATTERN_FALLBACK = re.compile(
    r'id:(?P<id>\S+).*?stat:(?P<stat>\w+)(?:\s+(?:err:)?(?P<err>\d+))?',
    re.IGNORECASE | re.DOTALL
)

# 送达成功的 stat 值
_DLR_DELIVERED_STATS = {'DELIVRD', 'ACCEPTD', 'DELIVERABLE'}
# 失败的 stat 值
_DLR_FAILED_STATS = {'UNDELIV', 'REJECTD', 'EXPIRED', 'DELETED', 'UNKNOWN'}

_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="smpp")

# 放宽 smpplib 对 password 字段的长度限制
# SMPP v3.4 规范限 9 字节(含null=8字符)，但很多供应商使用更长密码
try:
    import smpplib.command as _smpp_cmd
    _bt = getattr(_smpp_cmd, "BindTransmitter", None)
    if _bt and hasattr(_bt, "params") and "password" in _bt.params:
        _bt.params["password"].max = 64
    _br = getattr(_smpp_cmd, "BindReceiver", None)
    if _br and hasattr(_br, "params") and "password" in _br.params:
        _br.params["password"].max = 64
    _btc = getattr(_smpp_cmd, "BindTransceiver", None)
    if _btc and hasattr(_btc, "params") and "password" in _btc.params:
        _btc.params["password"].max = 64
except ImportError:
    pass

# SMPP 错误码 3 = Invalid Command ID（服务器不支持该绑定类型）
_ESME_RINVCMDID = 3
# 部分上游在「不支持 transceiver」或「仅允许 TX」时返回 13（Bind Failed），而非标准的 3
_ESME_BIND_FAILED_GENERIC = 13

# ESME 状态码简要说明（SMPP v3.4 常见值；不同供应商文案可能略有差异）
_SMPP_ESME_HINTS_ZH: dict[int, str] = {
    3: "无效命令 ID：对端可能不支持 bind_transceiver，可将通道「SMPP 绑定模式」改为 transmitter（仅发送）后重试",
    4: "已在绑定状态：该账号可能在其他会话已绑定，需断开旧连接或联系上游释放会话",
    13: "绑定被拒绝：常见为账号/密码错误、本机出口 IP 未加入上游白名单、未开通 transceiver、或上游仅允许 TX；若多 Celery worker 并发连接同一账号，也会因「单会话」限制出现本错误（需 Redis 集群锁或 worker-sms --concurrency=1）。请向供应商核对凭证、白名单与 bind 类型",
    14: "无效密码（密码与上游配置不一致）",
    15: "无效 System ID（用户名不存在或未开通）",
}


def _format_smpp_last_error(err_code: Optional[int], exc: Exception) -> str:
    """生成带中文提示的连接错误文案，便于通道检测与发送记录排查"""
    base = f"SMPP错误 (code={err_code}): {str(exc)}"
    if err_code is not None:
        hint = _SMPP_ESME_HINTS_ZH.get(err_code)
        if hint:
            return f"{base} | {hint}"
    return base


class SMPPAdapter:
    """SMPP通道适配器"""

    def __init__(self, channel: Channel):
        self.channel = channel
        self.client = None
        self.connected = False
        self._lock = threading.Lock()
        configured = getattr(channel, "smpp_bind_mode", None) or "transceiver"
        self._bind_mode = configured
        # Kaola SMPP (7099) 需 transceiver 才能接收 deliver_sm；若配置为 transmitter 则优先尝试 transceiver
        host = (getattr(channel, "host", "") or "").lower()
        if "kaolasms" in host and configured == "transmitter":
            self._bind_mode = "transceiver"
            logger.info(f"Kaola 通道 {channel.channel_code} 为接收 DLR 尝试 transceiver")
        self._system_type = getattr(channel, "smpp_system_type", None) or ""
        self._interface_version = getattr(channel, "smpp_interface_version", None) or 0x34
        self.last_error = None

    async def connect(self) -> bool:
        """连接SMPP服务器（异步包装）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._connect_sync)

    def _connect_sync(self) -> bool:
        """同步连接SMPP服务器，支持绑定模式自动降级"""
        try:
            import smpplib.client
            import smpplib.consts

            logger.info(
                f"连接SMPP服务器: {self.channel.host}:{self.channel.port} "
                f"bind_mode={self._bind_mode}"
            )

            self.client = smpplib.client.Client(
                self.channel.host,
                self.channel.port,
                allow_unknown_opt_params=True,
                timeout=15,
            )

            self.client.connect()
            logger.debug(f"SMPP TCP连接成功: {self.channel.host}:{self.channel.port}")

            bind_kwargs = dict(
                system_id=self.channel.username,
                password=self.channel.password,
                system_type=self._system_type,
                interface_version=self._interface_version,
            )

            try:
                self._do_bind(self._bind_mode, **bind_kwargs)
            except Exception as first_err:
                err_code = self._extract_smpp_error_code(first_err)
                # transceiver 失败且错误为「不支持该 bind」或部分上游返回的通用 Bind Failed(13)，降级尝试 transmitter
                if (
                    self._bind_mode == "transceiver"
                    and err_code in (_ESME_RINVCMDID, _ESME_BIND_FAILED_GENERIC)
                ):
                    logger.warning(
                        f"bind_transceiver 失败 (err={err_code})，尝试降级为 bind_transmitter："
                        f"{self.channel.channel_code}"
                    )
                    # 需要重新建立TCP连接
                    try:
                        self.client.disconnect()
                    except Exception:
                        pass
                    self.client = smpplib.client.Client(
                        self.channel.host,
                        self.channel.port,
                        allow_unknown_opt_params=True,
                        timeout=15,
                    )
                    self.client.connect()
                    self._bind_mode = "transmitter"
                    self._do_bind("transmitter", **bind_kwargs)
                else:
                    raise

            self.connected = True
            logger.info(
                f"SMPP绑定成功: {self.channel.channel_code} "
                f"(mode={self._bind_mode})"
            )

            # 注册 deliver_sm 回调（接收 DLR 回执）
            if self._bind_mode in ("transceiver", "receiver"):
                self.client.set_message_received_handler(self._on_deliver_sm)
                logger.info(f"已注册 deliver_sm 回调: {self.channel.channel_code}")

            threading.Thread(
                target=self._heartbeat_loop,
                daemon=True,
                name=f"smpp-heartbeat-{self.channel.id}",
            ).start()

            return True

        except ImportError:
            logger.warning("smpplib未安装，使用模拟模式")
            self.connected = True
            return True
        except Exception as e:
            err_code = self._extract_smpp_error_code(e)
            self.last_error = _format_smpp_last_error(err_code, e)
            logger.error(
                f"SMPP连接失败 [{self.channel.channel_code}]: {str(e)} "
                f"(bind_mode={self._bind_mode}, system_type='{self._system_type}', "
                f"interface_version=0x{self._interface_version:02x})",
                exc_info=e,
            )
            self.connected = False
            return False

    # ------------------------------------------------------------------ #
    #  绑定 & 辅助
    # ------------------------------------------------------------------ #

    def _do_bind(self, mode: str, **kwargs):
        """按绑定模式执行 SMPP bind"""
        if mode == "transmitter":
            self.client.bind_transmitter(**kwargs)
        elif mode == "receiver":
            self.client.bind_receiver(**kwargs)
        else:
            self.client.bind_transceiver(**kwargs)

    @staticmethod
    def _extract_smpp_error_code(exc: Exception) -> Optional[int]:
        """从 smpplib 异常中提取 SMPP 状态码"""
        try:
            if hasattr(exc, "args") and exc.args:
                if len(exc.args) >= 2:
                    return int(exc.args[1])
                if exc.args and isinstance(exc.args[0], tuple) and len(exc.args[0]) >= 2:
                    return int(exc.args[0][1])
        except (ValueError, TypeError, IndexError):
            pass
        return None

    # ------------------------------------------------------------------ #
    #  心跳
    # ------------------------------------------------------------------ #

    def _heartbeat_loop(self):
        """心跳保活 + 轮询入站 PDU（deliver_sm 等）"""
        import time

        heartbeat_interval = 30
        poll_interval = 2  # 快速轮询入站 PDU
        elapsed = 0
        can_receive = self._bind_mode in ("transceiver", "receiver")

        while self.connected and self.client:
            try:
                time.sleep(poll_interval)
                elapsed += poll_interval

                # 轮询入站 PDU（处理 deliver_sm 等）
                if can_receive and self.client:
                    try:
                        self.client.read_once(ignore_error_codes=[], auto_send_enquire_link=True)
                    except Exception:
                        pass

                # 心跳（smpplib 2.x 无 enquire_link 方法，需通过 PDU 发送）
                if elapsed >= heartbeat_interval:
                    elapsed = 0
                    if self.client:
                        try:
                            if hasattr(self.client, "enquire_link"):
                                self.client.enquire_link()
                            else:
                                import smpplib.smpp as _smpp
                                pdu = _smpp.make_pdu("enquire_link", client=self.client)
                                self.client.send_pdu(pdu)
                            logger.debug(f"SMPP心跳: {self.channel.channel_code}")
                        except Exception as e:
                            logger.debug(f"SMPP心跳: {e}")

            except Exception as e:
                logger.warning(f"SMPP心跳失败: {str(e)}")
                self.connected = False
                try:
                    time.sleep(5)
                    self._connect_sync()
                except Exception as reconnect_error:
                    logger.error(f"SMPP重连失败: {str(reconnect_error)}")
                    break

    # ------------------------------------------------------------------ #
    #  DLR 回执处理
    # ------------------------------------------------------------------ #

    def _on_deliver_sm(self, pdu):
        """处理收到的 deliver_sm PDU（DLR 回执）"""
        try:
            short_message = ""
            if hasattr(pdu, "short_message") and pdu.short_message:
                raw = pdu.short_message
                short_message = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)

            logger.info(
                f"[{self.channel.channel_code}] 收到 deliver_sm: {short_message[:200]}"
            )

            m = _DLR_PATTERN.search(short_message)
            if not m:
                m = _DLR_PATTERN_FALLBACK.search(short_message)
            if not m:
                logger.debug(
                    f"[{self.channel.channel_code}] deliver_sm 非 DLR 格式，跳过"
                )
                return

            upstream_id = m.group("id")
            stat = m.group("stat").upper()
            err = m.group("err") if m.group("err") else "000"

            if stat in _DLR_DELIVERED_STATS:
                new_status = "delivered"
            elif stat in _DLR_FAILED_STATS:
                new_status = "failed"
            else:
                new_status = "delivered" if err == "000" else "failed"

            logger.info(
                f"[{self.channel.channel_code}] DLR: id={upstream_id} "
                f"stat={stat} err={err} -> {new_status}"
            )

            dest_addr = getattr(pdu, "destination_addr", None) or ""
            source_addr = getattr(pdu, "source_addr", None) or ""
            receipted = getattr(pdu, "receipted_message_id", None) or ""
            if isinstance(dest_addr, bytes):
                dest_addr = dest_addr.decode("utf-8", errors="replace")
            if isinstance(source_addr, bytes):
                source_addr = source_addr.decode("utf-8", errors="replace")
            if isinstance(receipted, bytes):
                receipted = receipted.decode("utf-8", errors="replace")

            # 异步更新数据库
            threading.Thread(
                target=self._update_dlr_status,
                args=(upstream_id, new_status, stat, err, str(dest_addr), str(source_addr), str(receipted)),
                daemon=True,
                name=f"smpp-dlr-{upstream_id}",
            ).start()

        except Exception as e:
            logger.error(
                f"[{self.channel.channel_code}] 处理 deliver_sm 失败: {e}",
                exc_info=e,
            )

    def _update_dlr_status(
        self,
        upstream_id: str,
        new_status: str,
        stat: str,
        err: str,
        dest_addr: str = "",
        source_addr: str = "",
        receipted_message_id: str = "",
    ):
        """在独立线程中同步更新 DLR 状态到数据库"""
        from datetime import datetime
        from sqlalchemy import select as sa_select, and_, or_
        from sqlalchemy.ext.asyncio import (
            AsyncSession as _AS,
            create_async_engine as _cae,
            async_sessionmaker as _asm,
        )
        from app.config import settings

        async def _do():
            eng = _cae(
                settings.DATABASE_URL,
                echo=False,
                pool_size=2,
                max_overflow=2,
                pool_pre_ping=True,
            )
            session = _asm(eng, class_=_AS, expire_on_commit=False)()
            try:
                channel_id = self.channel.id

                def _expand_id_candidates(raw: str) -> List[str]:
                    upstream_id_str = str(raw).strip()
                    if not upstream_id_str:
                        return []
                    cands = [upstream_id_str]
                    if any(x in upstream_id_str.upper() for x in "ABCDEF"):
                        cands.append(upstream_id_str.upper())
                        cands.append(upstream_id_str.lower())
                    try:
                        if upstream_id_str.startswith("0x") or upstream_id_str.startswith("0X"):
                            cands.append(str(int(upstream_id_str, 16)))
                        elif upstream_id_str.isdigit():
                            cands.append(hex(int(upstream_id_str)))
                        elif all(c in "0123456789abcdefABCDEF" for c in upstream_id_str):
                            cands.append(str(int(upstream_id_str, 16)))
                    except (ValueError, TypeError):
                        pass
                    return list(dict.fromkeys(cands))

                candidate_ids: List[str] = []
                for piece in (upstream_id, receipted_message_id):
                    candidate_ids.extend(_expand_id_candidates(piece))
                candidate_ids = list(dict.fromkeys(candidate_ids))

                sms_log = None
                if candidate_ids:
                    stmt = sa_select(SMSLog).where(
                        and_(
                            SMSLog.upstream_message_id.in_(candidate_ids),
                            SMSLog.status.in_(["sent", "pending", "queued"]),
                        )
                    ).order_by(SMSLog.submit_time.desc()).limit(1)
                    # 短重试：应对主事务提交略晚于 deliver_sm 线程读库的残余竞态（每次约 80ms，最多约 400ms）
                    for _attempt in range(5):
                        result = await session.execute(stmt)
                        sms_log = result.scalar_one_or_none()
                        if sms_log:
                            break
                        if _attempt < 4:
                            await asyncio.sleep(0.08)

                # 上游 ID 未入库或与 submit_sm_resp 不一致时（例如误存了 SMPP sequence），用手机号兜底
                if not sms_log:
                    def _digits(s: str) -> str:
                        return "".join(c for c in str(s) if c.isdigit())

                    for addr in (dest_addr, source_addr):
                        d = _digits(addr)
                        if len(d) < 8:
                            continue
                        stmt2 = sa_select(SMSLog).where(
                            and_(
                                SMSLog.channel_id == channel_id,
                                SMSLog.status.in_(["sent", "pending", "queued"]),
                                or_(
                                    SMSLog.phone_number.like(f"%{d}"),
                                    SMSLog.phone_number == f"+{d}",
                                ),
                            )
                        ).order_by(SMSLog.sent_time.desc()).limit(1)
                        res2 = await session.execute(stmt2)
                        sms_log = res2.scalar_one_or_none()
                        if sms_log:
                            logger.info(
                                f"SMPP DLR: 按号码兜底匹配成功 upstream_id={upstream_id} -> "
                                f"log={sms_log.message_id} phone={sms_log.phone_number}"
                            )
                            break

                if not sms_log:
                    logger.warning(
                        f"SMPP DLR: 未找到 upstream_id={upstream_id} (候选 {candidate_ids})，"
                        f"dest={dest_addr!r} src={source_addr!r}"
                    )
                    return

                sms_log.status = new_status
                if new_status == "delivered":
                    sms_log.delivery_time = datetime.now()
                elif new_status == "failed":
                    sms_log.error_message = f"SMPP DLR: stat={stat} err={err}"
                # 纠正错误保存的 sequence 等占位 ID，便于后续对账
                if upstream_id and str(sms_log.upstream_message_id or "") != str(upstream_id).strip():
                    sms_log.upstream_message_id = str(upstream_id).strip()

                await session.commit()
                logger.info(
                    f"SMPP DLR 更新成功: {sms_log.message_id} -> {new_status}"
                )
            except Exception as e:
                logger.error(f"SMPP DLR 更新失败: {e}", exc_info=e)
                await session.rollback()
            finally:
                await session.close()
                await eng.dispose()

        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_do())
            loop.close()
        except Exception as e:
            logger.error(f"SMPP DLR 线程异常: {e}", exc_info=e)

    # ------------------------------------------------------------------ #
    #  发送
    # ------------------------------------------------------------------ #

    async def send(self, sms_log: SMSLog) -> Tuple[bool, Optional[str], Optional[str]]:
        """发送短信（异步包装）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._send_sync, sms_log)

    def _send_sync(self, sms_log: SMSLog) -> Tuple[bool, Optional[str], Optional[str]]:
        """同步发送短信"""
        try:
            if not self.connected or not self.client:
                if not self._connect_sync():
                    # 使用 last_error 便于发送记录中展示具体原因（超时/认证/网络等）
                    return False, None, (self.last_error or "SMPP connection failed")

            try:
                import smpplib.gsm
                import smpplib.consts
            except ImportError:
                message_id = f"smpp_{sms_log.message_id[:16]}"
                logger.info(f"SMPP发送成功（模拟）: {message_id}")
                return True, message_id, None

            parts, encoding_flag, msg_type_flag = smpplib.gsm.make_parts(sms_log.message)

            message_ids = []
            sender_id = self.channel.default_sender_id or ""

            # 注册消息响应处理器以捕获 submit_sm_resp 中的 message_id
            resp_message_ids = []

            def _msg_sent_handler(pdu):
                """捕获 submit_sm_resp 中的 message_id"""
                if hasattr(pdu, "message_id") and pdu.message_id:
                    mid = pdu.message_id
                    if isinstance(mid, bytes):
                        mid = mid.decode("utf-8", errors="replace")
                    resp_message_ids.append(mid)

            self.client.set_message_sent_handler(_msg_sent_handler)

            for i, part in enumerate(parts):
                # 每段提交前清空，避免 smpplib 将多段 submit_sm_resp 记混到同一段
                resp_message_ids.clear()
                try:
                    pdu = self.client.send_message(
                        source_addr_ton=(
                            smpplib.consts.SMPP_TON_ALNUM
                            if sender_id
                            else smpplib.consts.SMPP_TON_INTL
                        ),
                        source_addr_npi=smpplib.consts.SMPP_NPI_UNK,
                        source_addr=sender_id,
                        dest_addr_ton=smpplib.consts.SMPP_TON_INTL,
                        dest_addr_npi=smpplib.consts.SMPP_NPI_ISDN,
                        destination_addr=sms_log.phone_number.lstrip("+"),
                        short_message=part,
                        data_coding=encoding_flag,
                        esm_class=msg_type_flag,
                        registered_delivery=1,
                    )

                    # 同步读取 submit_sm_resp 以获取真实 message_id（否则会误用 sequence 导致 DLR 无法匹配）
                    try:
                        self.client.read_once(ignore_error_codes=[], auto_send_enquire_link=False)
                    except Exception:
                        pass

                    # 优先从 resp handler 获取 message_id
                    if resp_message_ids:
                        mid = resp_message_ids[-1]
                    elif hasattr(pdu, "message_id") and pdu.message_id:
                        mid = pdu.message_id
                        if isinstance(mid, bytes):
                            mid = mid.decode("utf-8", errors="replace")
                    else:
                        mid = None

                    # 禁止将 pdu.sequence 当作上游 message_id：与 deliver_sm 中 id: 完全对不上，会导致 DLR 永久无法匹配
                    if not mid or (isinstance(mid, str) and not mid.strip()):
                        seq = getattr(pdu, "sequence", None)
                        logger.warning(
                            f"SMPP submit_sm 未获得上游 message_id（第 {i + 1}/{len(parts)} 段），"
                            f"sequence={seq}；已放弃写入占位 ID，送达依赖 DLR 手机号兜底或上游修复 resp"
                        )
                        mid = None

                    message_ids.append(mid)
                    logger.info(f"SMPP发送 {i+1}/{len(parts)}: message_id={mid!r}")

                except Exception as e:
                    error_msg = f"发送部分 {i+1} 失败: {str(e)}"
                    logger.error(error_msg, exc_info=e)
                    return False, None, error_msg

            final_message_id = next((m for m in message_ids if m), None)
            logger.info(f"SMPP发送成功: {sms_log.message_id} -> {final_message_id!r}")

            # transceiver/receiver 模式下不在此断开，由 sms_worker 加入延迟断开队列，避免阻塞 Celery 任务
            return True, final_message_id, None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"SMPP发送失败: {error_msg}", exc_info=e)
            self.connected = False
            return False, None, error_msg

    # ------------------------------------------------------------------ #
    #  断开
    # ------------------------------------------------------------------ #

    async def disconnect(self):
        """断开连接"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, self._disconnect_sync)

    def _disconnect_sync(self):
        """同步断开连接"""
        try:
            with self._lock:
                if self.client:
                    try:
                        self.client.unbind()
                        self.client.disconnect()
                    except ImportError:
                        pass
                    except Exception as e:
                        logger.warning(f"关闭SMPP连接时出错: {str(e)}")
                    self.client = None
                    self.connected = False
                    logger.info(f"SMPP连接已关闭: {self.channel.channel_code}")
        except Exception as e:
            logger.error(f"断开SMPP连接失败: {str(e)}")

    def __del__(self):
        if self.client:
            try:
                self._disconnect_sync()
            except Exception:
                pass
