"""
RCS 通道适配器 —— 叮咚 BoltTel RCS OpenAPI

对接文档：BoltTel-RCS-OpenAPI对接指南.md

要点：
  - 鉴权：X-App-Key / X-Timestamp / X-Nonce / X-Signature
    signature = HEX_LOWER(HMAC_SHA256(appSecret, METHOD\\nSIGN_PATH\\nTS\\nNONCE\\nSHA256(body)))
    SIGN_PATH 含 `/api` 不含 `/service`，与实际 URL 路径不同，别写混。
  - 签名的 body 字节必须与实际发出的 HTTP body 完全一致 —— 所以这里先 json.dumps 成
    bytes，再用 content= 发送，绝不能交给 httpx 的 json= 重新序列化。
  - 幂等：clientRef 用我们的 message_id。超时/5xx 重投时带同一个 clientRef，
    上游返回 duplicated=true 且不重复扣费，避免双发。
"""
import hashlib
import hmac
import json
import time
import uuid
from typing import Any, Optional

import httpx

from app.modules.sms.channel import Channel
from app.modules.sms.sms_log import SMSLog
from app.utils.logger import get_logger
from app.utils.rcs_content import rcs_phone_e164, validate_rcs_content

logger = get_logger(__name__)

# 签名用路径前缀：BASE 形如 https://域名/service/api，而签名路径是 /api/openApi/...
_SIGN_PREFIX = "/api"
_PATH_SEND = "/openApi/rcs/send"
_PATH_REPORT = "/openApi/rcs/report"
_PATH_BALANCE = "/openApi/rcs/balance"

# 上游业务错误码 → 对下游安全的中性中文提示。
# 与 http_adapter 同一原则：绝不把上游余额/单价/成本等内部信息透传给客户。
_BIZ_ERROR_MESSAGE = {
    "SENDCODE_MISSING": "RCS 发件人未配置，请联系客服",
    "SENDCODE_INVALID": "RCS 发件人无效或未开通，请联系客服",
    "ISO_MISSING": "目标国家缺失",
    "ROUTE_INVALID": "RCS 线路不可用，请联系客服",
    "ROUTE_UNSUPPORTED": "RCS 线路暂不支持该发件人，请联系客服",
    "REQ_EMPTY": "号码列表为空",
    "REQ_TOO_MANY": "单次提交号码超限",
    "REQ_BAD_MODE": "发送模式与参数不匹配",
    "CONTENT_EMPTY": "短信内容不能为空",
    "CONTENT_TOO_LONG": "RCS 文案超过 160 个字符",
    "CONTENT_EMOJI_FORBIDDEN": "RCS 文案不支持 emoji",
    "PHONE_INVALID": "号码格式不正确",
    "PHONE_ISO_MISMATCH": "号码归属与目标国家不一致",
    "PRICE_MISSING": "该国家/地区暂不支持",
    "BALANCE_INSUFFICIENT": "通道余额不足，请联系客服",
    "SYSTEM_BUSY": "通道繁忙，请稍后重试",
    "INTERNAL_ERROR": "通道内部异常，请稍后重试",
}

# 鉴权类错误码 → 中性提示（这些都是配置问题，重投无用，直接判失败并告警）
_AUTH_ERROR_MESSAGE = {
    "AUTH_MISSING_HEADER": "RCS 通道鉴权异常，请联系客服",
    "AUTH_INVALID_APP_KEY": "RCS 通道鉴权异常，请联系客服",
    "AUTH_DISABLED": "RCS 通道已停用，请联系客服",
    "AUTH_BAD_TIMESTAMP": "RCS 通道鉴权异常，请联系客服",
    "AUTH_TIMESTAMP_EXPIRED": "RCS 通道鉴权异常（服务器时间偏差），请联系客服",
    "AUTH_NONCE_REPLAY": "RCS 通道鉴权异常，请联系客服",
    "AUTH_BAD_SIGNATURE": "RCS 通道鉴权异常，请联系客服",
    "AUTH_IP_FORBIDDEN": "RCS 通道鉴权异常（IP 未加白），请联系客服",
}

# 可重投的上游业务错误码：上游明确说明「未扣费或已回退」，带同一 clientRef 重试是安全的
_RETRYABLE_BIZ_CODES = {"SYSTEM_BUSY", "INTERNAL_ERROR"}


class RCSSendResult:
    """RCS 发送结果。retryable=True 表示可交给 Celery 重投（同 clientRef 幂等）。"""

    __slots__ = ("success", "upstream_message_id", "batch_id", "error", "retryable", "duplicated")

    def __init__(
        self,
        success: bool,
        upstream_message_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        error: Optional[str] = None,
        retryable: bool = False,
        duplicated: bool = False,
    ):
        self.success = success
        self.upstream_message_id = upstream_message_id
        self.batch_id = batch_id
        self.error = error
        self.retryable = retryable
        self.duplicated = duplicated

    def __repr__(self) -> str:
        return (
            f"<RCSSendResult success={self.success} mid={self.upstream_message_id} "
            f"retryable={self.retryable} err={self.error!r}>"
        )


class RCSConfigError(Exception):
    """通道 RCS 配置缺失/非法（appKey、appSecret、base_url、sendCode）。"""


class BoltTelRCSAdapter:
    """叮咚 BoltTel RCS 适配器。一个实例对应一个通道。"""

    def __init__(self, channel: Channel, timeout: float = 30.0):
        self.channel = channel
        self.timeout = timeout
        cfg = channel.get_rcs_config()
        self.base_url: str = cfg.get("base_url") or ""
        self.app_key: str = cfg.get("app_key") or ""
        self.app_secret: str = cfg.get("app_secret") or ""
        self.default_send_code: str = cfg.get("send_code") or ""
        self.webhook_secret: str = cfg.get("webhook_secret") or ""

    # ── 鉴权 ────────────────────────────────────────────────────────────────

    def _require_credentials(self) -> None:
        missing = [
            name
            for name, val in (
                ("base_url(api_url)", self.base_url),
                ("app_key(username)", self.app_key),
                ("app_secret(password)", self.app_secret),
            )
            if not val
        ]
        if missing:
            raise RCSConfigError(
                f"RCS 通道 {self.channel.channel_code} 配置不完整，缺少: {', '.join(missing)}"
            )

    def _build_headers(self, method: str, url_path: str, body: bytes) -> dict:
        """按对接文档组装签名头。签名用 SIGN_PATH（含 /api），不是实际 URL 路径。"""
        timestamp = str(int(time.time() * 1000))
        nonce = str(uuid.uuid4())
        body_sha = hashlib.sha256(body or b"").hexdigest()
        sign_path = f"{_SIGN_PREFIX}{url_path}"
        string_to_sign = f"{method.upper()}\n{sign_path}\n{timestamp}\n{nonce}\n{body_sha}"
        signature = hmac.new(
            self.app_secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "X-App-Key": self.app_key,
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-Signature": signature,
        }
        if method.upper() == "POST":
            headers["Content-Type"] = "application/json; charset=UTF-8"
        return headers

    # ── 低层请求 ─────────────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        url_path: str,
        body: Optional[bytes] = None,
        params: Optional[dict] = None,
    ) -> tuple[int, Any, str]:
        """
        发起一次签名请求。

        Returns:
            (http_status, 解析后的 JSON 或 None, 原始文本片段)
        """
        self._require_credentials()
        body_bytes = body or b""
        headers = self._build_headers(method, url_path, body_bytes)
        url = f"{self.base_url}{url_path}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if method.upper() == "POST":
                resp = await client.post(url, content=body_bytes, headers=headers, params=params)
            else:
                resp = await client.get(url, headers=headers, params=params)

        text = resp.text or ""
        try:
            data = resp.json()
        except Exception:
            data = None
        return resp.status_code, data, text[:500]

    # ── 发送 ────────────────────────────────────────────────────────────────

    def build_send_body(self, sms_log: SMSLog) -> bytes:
        """组装单条广播请求体。返回 bytes —— 签名与实际发送必须是同一串字节。"""
        send_code = (getattr(sms_log, "sender_id", None) or self.default_send_code or "").strip()
        payload = {
            "sendCode": send_code,
            "isoCode": (sms_log.country_code or "").strip().upper(),
            "sendMode": "broadcast",
            "content": sms_log.message or "",
            "phones": [rcs_phone_e164(sms_log.phone_number)],
            "clientRef": sms_log.message_id,
        }
        # ensure_ascii=False + 无多余空格：内容多为非 ASCII，保持体积最小且字节稳定
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    async def send_one(self, sms_log: SMSLog) -> RCSSendResult:
        """发送单条 RCS。clientRef=message_id 保证重投不双发。"""
        # 本地先卡一遍上游硬限制：批量场景下一条违规文案会导致整批被拒
        ok, err_code, err_msg = validate_rcs_content(sms_log.message)
        if not ok:
            logger.warning(
                f"RCS 文案本地校验不通过: {sms_log.message_id}, {err_code}"
            )
            return RCSSendResult(False, error=err_msg)

        if not (sms_log.country_code or "").strip():
            return RCSSendResult(False, error="目标国家缺失")

        try:
            body = self.build_send_body(sms_log)
        except RCSConfigError as e:
            logger.error(str(e))
            return RCSSendResult(False, error="RCS 通道未配置完整，请联系客服")

        if not json.loads(body.decode("utf-8")).get("sendCode"):
            logger.error(f"RCS 通道 {self.channel.channel_code} 未配置 sendCode(发件人)")
            return RCSSendResult(False, error="RCS 发件人未配置，请联系客服")

        try:
            status, data, raw = await self._request("POST", _PATH_SEND, body=body)
        except RCSConfigError as e:
            logger.error(str(e))
            return RCSSendResult(False, error="RCS 通道未配置完整，请联系客服")
        except (httpx.TimeoutException, httpx.TransportError) as e:
            # 网络层失败：不确定上游是否已受理，交给 Celery 用同一 clientRef 重投（上游幂等）
            logger.warning(f"RCS 发送网络异常，将重投: {sms_log.message_id}, {e}")
            return RCSSendResult(False, error="通道网络异常", retryable=True)
        except Exception as e:
            logger.error(f"RCS 发送异常: {sms_log.message_id}, {e}", exc_info=e)
            return RCSSendResult(False, error="发送失败", retryable=True)

        return self._parse_send_response(sms_log, status, data, raw)

    @staticmethod
    def _pick_message_id(sms_log: SMSLog, msg: dict, batch_id: Optional[str]) -> Optional[str]:
        """从受理响应里取出这条消息的上游 messageId。

        优先级（对接指南 §3）：
          1. messages[{messageId, phone}] —— 文档「推荐使用」的显式映射，顺带能校验号码
          2. messageIds[0] —— 老字段，靠下标对应（我们逐条提交，只有一条）
          3. 按 `msg:{batchId}-{index}` 格式自拼

        第 3 条是为幂等重放准备的：clientRef 命中幂等时上游返回 duplicated=true，
        而 messageIds / messages **可能为 null**。若就此把 upstream_message_id 留空，
        后续回执按 messageId 匹配会全部落空，只能退到「按手机号 + 24h」的模糊兜底，
        同号码多条时会错配到最新那条。我们是逐条提交，index 恒为 0，可以安全拼出来。
        """
        wire_phone = rcs_phone_e164(sms_log.phone_number)

        entries = msg.get("messages")
        if isinstance(entries, list) and entries:
            first = entries[0] if isinstance(entries[0], dict) else {}
            mid = first.get("messageId")
            phone = str(first.get("phone") or "").strip()
            if phone and wire_phone and phone != wire_phone:
                # 串号是最坏情况：回执会把 A 的状态写到 B 头上，宁可不认这个映射
                logger.error(
                    f"RCS 受理响应号码不匹配: {sms_log.message_id} 提交={wire_phone} 返回={phone}，"
                    f"已忽略该 messageId"
                )
            elif mid:
                return str(mid)

        ids = msg.get("messageIds")
        if isinstance(ids, list) and ids and ids[0]:
            return str(ids[0])

        if batch_id:
            synthesized = f"msg:{batch_id}-0"
            logger.warning(
                f"RCS 受理成功但未返回 messageIds/messages（多为 clientRef 幂等重放）: "
                f"{sms_log.message_id}, 按 batchId 拼出 {synthesized} 用于回执匹配"
            )
            return synthesized

        logger.warning(
            f"RCS 受理成功但既无 messageIds 也无 batchId: {sms_log.message_id}，"
            f"回执只能靠 clientRef 兜底匹配"
        )
        return None

    def _parse_send_response(
        self, sms_log: SMSLog, status: int, data: Any, raw: str
    ) -> RCSSendResult:
        """按对接文档 §7.4 的判读顺序解析发送响应。"""
        code = data.get("code") if isinstance(data, dict) else None

        # 1) 鉴权 / 限流（HTTP 401/403/429），errorCode 在响应体顶层
        if status in (401, 403, 429):
            err_code = str((data or {}).get("errorCode") or "") if isinstance(data, dict) else ""
            if status == 429 or err_code == "AUTH_QPS_EXCEEDED":
                logger.warning(
                    f"RCS 上游限流(QPS): {self.channel.channel_code}, 将退避重投 {sms_log.message_id}"
                )
                return RCSSendResult(False, error="发送过于频繁，请稍后重试", retryable=True)
            logger.error(
                f"RCS 鉴权失败: channel={self.channel.channel_code}, http={status}, "
                f"errorCode={err_code}, 请核对 appKey/appSecret/签名路径/IP 白名单"
            )
            return RCSSendResult(
                False, error=_AUTH_ERROR_MESSAGE.get(err_code, "RCS 通道鉴权异常，请联系客服")
            )

        # 2) 5xx / 非 200：可用同一 clientRef 重试
        if status != 200:
            logger.warning(f"RCS 发送 HTTP {status}: {sms_log.message_id}, {raw}")
            return RCSSendResult(False, error="通道暂时不可用，请稍后重试", retryable=True)

        if not isinstance(data, dict):
            logger.error(f"RCS 响应非 JSON: {sms_log.message_id}, {raw}")
            return RCSSendResult(False, error="通道响应异常", retryable=True)

        # 3) 成功
        if code == 0:
            msg = data.get("message")
            if not isinstance(msg, dict):
                logger.error(f"RCS 成功响应缺少 message 体: {sms_log.message_id}, {raw}")
                return RCSSendResult(False, error="通道响应异常", retryable=True)
            batch_id = str(msg.get("batchId")) if msg.get("batchId") is not None else None
            duplicated = bool(msg.get("duplicated"))
            upstream_id = self._pick_message_id(sms_log, msg, batch_id)
            logger.info(
                f"RCS 发送受理: {sms_log.message_id} -> mid={upstream_id} batch={batch_id} "
                f"duplicated={duplicated}"
            )
            return RCSSendResult(
                True,
                upstream_message_id=upstream_id,
                batch_id=batch_id,
                duplicated=duplicated,
            )

        # 4) 业务错误（code=10030，errorCode 在 message 里）
        if code == 10030:
            msg = data.get("message")
            err_code = str((msg or {}).get("errorCode") or "") if isinstance(msg, dict) else ""
            err_detail = str((msg or {}).get("errorMsg") or "") if isinstance(msg, dict) else str(msg)
            retryable = err_code in _RETRYABLE_BIZ_CODES
            logger.error(
                f"RCS 业务拒绝: {sms_log.message_id}, errorCode={err_code}, detail={err_detail[:200]}"
            )
            return RCSSendResult(
                False,
                error=_BIZ_ERROR_MESSAGE.get(err_code, f"发送失败（{err_code or 'RCS_ERROR'}）"),
                retryable=retryable,
            )

        # 5) 鉴权码走 HTTP 200 返回的兜底（部分网关不改状态码）
        if code in (10000, 10140):
            err_code = str(data.get("errorCode") or "")
            if code == 10140 or err_code == "AUTH_QPS_EXCEEDED":
                return RCSSendResult(False, error="发送过于频繁，请稍后重试", retryable=True)
            logger.error(f"RCS 鉴权失败(code={code}): {self.channel.channel_code}, {err_code}")
            return RCSSendResult(
                False, error=_AUTH_ERROR_MESSAGE.get(err_code, "RCS 通道鉴权异常，请联系客服")
            )

        logger.error(f"RCS 未知响应: {sms_log.message_id}, code={code}, {raw}")
        return RCSSendResult(False, error="发送失败")

    # ── 报告 / 余额（对账与后台展示用） ────────────────────────────────────────

    async def get_report(self, batch_id: str, with_messages: bool = False) -> dict:
        """批次报告。query 不参与签名。"""
        status, data, raw = await self._request(
            "GET",
            _PATH_REPORT,
            params={"batchId": str(batch_id), "withMessages": "true" if with_messages else "false"},
        )
        return self._unwrap(status, data, raw)

    async def get_balance(self) -> dict:
        """账户余额（上游侧余额，仅管理员可见，不得透传给客户）。"""
        status, data, raw = await self._request("GET", _PATH_BALANCE)
        return self._unwrap(status, data, raw)

    @staticmethod
    def _unwrap(status: int, data: Any, raw: str) -> dict:
        if status in (401, 403, 429) and isinstance(data, dict):
            return {
                "success": False,
                "error_code": data.get("errorCode") or f"HTTP_{status}",
                "error": _AUTH_ERROR_MESSAGE.get(
                    str(data.get("errorCode") or ""), "RCS 通道鉴权异常"
                ),
            }
        if status != 200 or not isinstance(data, dict):
            return {"success": False, "error_code": f"HTTP_{status}", "error": raw or "通道响应异常"}
        if data.get("code") == 0:
            return {"success": True, "data": data.get("message")}
        msg = data.get("message")
        if isinstance(msg, dict):
            err_code = str(msg.get("errorCode") or "")
            return {
                "success": False,
                "error_code": err_code or str(data.get("code")),
                "error": _BIZ_ERROR_MESSAGE.get(err_code, str(msg.get("errorMsg") or msg)),
            }
        return {"success": False, "error_code": str(data.get("code")), "error": str(msg)}

    # ── 回执验签 ─────────────────────────────────────────────────────────────

    def verify_webhook_signature(self, raw_body: bytes, signature: Optional[str]) -> bool:
        """
        校验 X-Rcs-Signature = HEX_LOWER(HMAC_SHA256(secret, rawBody))。

        必须对「原始 body 字节」验签 —— 先 parse 再 dumps 会改变字节导致永远验不过。
        """
        if not self.webhook_secret:
            return False
        if not signature:
            return False
        expected = hmac.new(
            self.webhook_secret.encode("utf-8"), raw_body or b"", hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, str(signature).strip().lower())


# RCS 上游厂商 → 适配器实现。RCS 不占 protocol 枚举（它就是 HTTP），
# 每接一家新供应商只在这里加一行，不动 DB 枚举也不动发送链路。
_RCS_ADAPTERS = {
    "bolttel": BoltTelRCSAdapter,   # 叮咚：逐条提交 + Webhook 回执
    # "node": NodeRCSAdapter,       # 节点(apip.nodesms.com)：任务制，创建任务→轮询结果，待接
}

DEFAULT_RCS_VENDOR = "bolttel"


def get_rcs_adapter(channel: Channel):
    """按通道 config_json.rcs.vendor 选择适配器实现。

    未知 vendor 直接报错而不是回落到叮咚 —— 静默回落会用错误的签名算法把号码发给
    另一家上游，必然全批失败且极难定位。
    """
    vendor = (channel.rcs_vendor() or DEFAULT_RCS_VENDOR).lower()
    impl = _RCS_ADAPTERS.get(vendor)
    if impl is None:
        raise RCSConfigError(
            f"通道 {channel.channel_code} 的 RCS 上游 vendor={vendor!r} 尚未实现，"
            f"当前支持: {', '.join(sorted(_RCS_ADAPTERS))}"
        )
    return impl(channel)


__all__ = [
    "BoltTelRCSAdapter",
    "RCSSendResult",
    "RCSConfigError",
    "get_rcs_adapter",
]
