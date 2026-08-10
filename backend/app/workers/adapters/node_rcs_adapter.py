"""
RCS 通道适配器 —— 节点(nodesms) 群发 OpenAPI

对接文档：docs/RCS_节点对接指南.md（源文档 img.nodesms.com/doc/group_api.pdf）

与叮咚(BoltTel)的根本差异 —— 决定了它不能复用 send_one 逐条模型：

  叮咚：逐条提交 → 上游返回 messageId → Webhook 逐条推终态回执
  节点：整批提交（号码是一个公网 TXT 文件的 URL）→ 返回任务号 sn
        → 轮询 getTask 拿聚合计数 → 任务完成后下载 getFile 拿逐条结果

所以本适配器只提供「任务级」API 客户端，send_one 明确拒绝（见下）。
把它接进发送链路需要额外的三块能力，尚未实现：
  1. 把批次号码落成一个公网可访问的 TXT（带随机 token、短 TTL、发完即删）
  2. 定时轮询任务状态的 worker
  3. 任务完成后下载结果文件、逐条回写 sms_logs

要点：
  - 鉴权：Header `X-Signature = BASE64(HMAC_SHA256(secret, bodyJson))`（raw binary 再 base64，
    对应文档里的 PHP `base64_encode(hash_hmac('sha256', $dataJson, $secret, true))`）。
    与叮咚同一个坑：签名的字节必须与实际发出的 body 完全一致，故先 dumps 成 bytes 再用
    content= 发送，绝不交给 httpx 的 json= 重新序列化。
  - secret 只参与签名、不进 body：各接口的请求参数表里都只有 account，没有 secret
    （§公共请求参数那张表是笼统写法）。若上游回 710/711 需优先复核这个判断。
  - 幂等：orderId 由我们生成且需全局唯一；重复提交同一 orderId 上游回 709「订单号已存在」，
    但**不返回原 sn** —— 拿不回任务号，只能人工核查，因此 709 绝不能自动重试。
"""
import base64
import hashlib
import hmac
import json
from typing import Any, Optional

import httpx

from app.modules.sms.channel import Channel
from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_BASE_URL = "https://apip.nodesms.com"

# 群发（send）
PATH_SEND_CREATE = "/api/send/createTask"
PATH_SEND_GET = "/api/send/getTask"
PATH_SEND_FILE = "/api/send/getFile"
PATH_SEND_REVOKE = "/api/send/revoke"
PATH_SEND_PAUSE = "/api/send/pause"
PATH_SEND_RECOVER = "/api/send/recover"
PATH_SEND_INTERRUPT = "/api/send/interrupt"
PATH_SEND_UPDATE = "/api/send/updateTask"
PATH_SEND_REMAIN = "/api/send/getValNumByShortCode"
# 筛选（filter）—— 号码筛选/空号检测，属数据业务，非发送
PATH_FILTER_CREATE = "/api/filter/createTask"
PATH_FILTER_GET = "/api/filter/getTask"
PATH_FILTER_CANCEL = "/api/filter/cancelTask"
PATH_FILTER_FILE = "/api/filter/getFile"

# 群发业务/类别字典
BUSINESS_RCS = "RCS"
CATEGORY_TEXT = "RCS_Text"
CATEGORY_IMGTEXT = "RCS_ImgText"

# 群发前是否先筛选：1=直接发送，2=筛选后发送
IS_FILTER_DIRECT = 1
IS_FILTER_SCREEN = 2

# 任务状态（getTask.status）
TASK_STATUS = {
    0: "等待审核",
    1: "待开始",
    2: "筛选中",
    3: "群发中",
    4: "已取消",
    5: "已完成",
    6: "结算中",
    7: "已拒绝",
    8: "失败",
    9: "中断",
    10: "暂停",
    11: "撤单",
}
# 终态：不会再变，可以停止轮询并结算
TASK_STATUS_FINAL = {4, 5, 7, 8, 11}
# 在途：继续轮询
TASK_STATUS_RUNNING = {0, 1, 2, 3, 6, 9, 10}

# 上游 code → 对下游安全的中性提示。与 http/rcs 适配器同一原则：
# 绝不把上游余额/单价/线路等内部信息透传给客户。
_CODE_MESSAGE = {
    400: "通道无权限，请联系客服",
    402: "提交参数有误",
    404: "目标任务不存在或已删除",
    405: "通道繁忙，请稍后重试",
    601: "通道繁忙，请稍后重试",
    701: "通道余额不足，请联系客服",
    702: "该国家/地区暂不支持",
    703: "RCS 线路不可用，请联系客服",
    704: "RCS 线路不可用，请联系客服",
    705: "号码文件异常",
    706: "该国家/地区暂不支持",
    707: "RCS 线路已关闭，请联系客服",
    708: "扣费失败，请联系客服",
    709: "订单号重复提交",
    710: "RCS 通道鉴权异常，请联系客服",
    711: "RCS 通道鉴权异常（验签失败），请联系客服",
    799: "发送失败，请联系客服",
}

# 可安全重投的 code：上游明确是「稍后再试」类。
# 709(订单号已存在) 绝不在此列 —— 它意味着上游已受理过，重试只会继续撞车，
# 而且拿不回原 sn，必须人工核查。
_RETRYABLE_CODES = {405, 601}

CODE_SUCCESS = 200
CODE_ORDER_EXISTS = 709


class NodeRCSConfigError(Exception):
    """节点通道配置缺失/非法（account、secret、productId、base_url）。"""


class NodeRCSResult:
    """节点接口调用结果。retryable=True 表示可安全重投。"""

    __slots__ = ("success", "code", "data", "error", "retryable")

    def __init__(
        self,
        success: bool,
        code: Optional[int] = None,
        data: Any = None,
        error: Optional[str] = None,
        retryable: bool = False,
    ):
        self.success = success
        self.code = code
        self.data = data
        self.error = error
        self.retryable = retryable

    def __repr__(self) -> str:
        return (
            f"<NodeRCSResult success={self.success} code={self.code} "
            f"retryable={self.retryable} err={self.error!r}>"
        )


class NodeRCSAdapter:
    """节点(nodesms) RCS 群发适配器。一个实例对应一个通道。"""

    vendor = "node"

    def __init__(self, channel: Channel, timeout: float = 30.0):
        self.channel = channel
        self.timeout = timeout
        cfg = channel.get_rcs_config()
        # 复用通用列回落：api_url→base_url，username→account，password→secret
        self.base_url: str = (cfg.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        self.account: str = cfg.get("app_key") or ""
        self.secret: str = cfg.get("app_secret") or ""
        # 节点特有：产品 ID（决定线路与单价），只能配在 config_json.rcs.product_id
        self.product_id: str = str(cfg.get("product_id") or "").strip()

    # ── 鉴权 ────────────────────────────────────────────────────────────────

    def _require_credentials(self, need_product: bool = False) -> None:
        missing = []
        if not self.base_url:
            missing.append("base_url(api_url)")
        if not self.account:
            missing.append("account(username)")
        if not self.secret:
            missing.append("secret(password)")
        if need_product and not self.product_id:
            missing.append("product_id(config_json.rcs.product_id)")
        if missing:
            raise NodeRCSConfigError(
                f"节点 RCS 通道 {self.channel.channel_code} 配置不完整，缺少: {', '.join(missing)}"
            )

    def sign(self, body: bytes) -> str:
        """X-Signature = BASE64(HMAC_SHA256(secret, body))，对原始发送字节签名。"""
        digest = hmac.new(self.secret.encode("utf-8"), body or b"", hashlib.sha256).digest()
        return base64.b64encode(digest).decode("ascii")

    @staticmethod
    def dumps(payload: dict) -> bytes:
        """序列化为待签名/待发送的同一串字节。"""
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    # ── 低层请求 ─────────────────────────────────────────────────────────────

    async def _request(self, path: str, payload: dict, method: str = "POST") -> NodeRCSResult:
        """发起一次签名请求并按 {code,msg,data} 解析。"""
        body = self.dumps(payload)
        headers = {
            "Content-Type": "application/json;charset=utf-8",
            "X-Signature": self.sign(body),
        }
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 余量查询是 GET，但文档同样给的是 JSON body + 签名，故统一用 content= 带上
                resp = await client.request(method, url, content=body, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            logger.warning(f"节点 RCS 网络异常: {self.channel.channel_code} {path}, {e}")
            return NodeRCSResult(False, error="通道网络异常", retryable=True)
        except Exception as e:
            logger.error(f"节点 RCS 请求异常: {self.channel.channel_code} {path}, {e}", exc_info=e)
            return NodeRCSResult(False, error="发送失败", retryable=True)

        return self._parse(path, resp)

    def _parse(self, path: str, resp: httpx.Response) -> NodeRCSResult:
        text = (resp.text or "")[:500]
        if resp.status_code != 200:
            logger.warning(f"节点 RCS HTTP {resp.status_code}: {path}, {text}")
            return NodeRCSResult(
                False, error="通道暂时不可用，请稍后重试", retryable=resp.status_code >= 500
            )
        try:
            data = resp.json()
        except Exception:
            logger.error(f"节点 RCS 响应非 JSON: {path}, {text}")
            return NodeRCSResult(False, error="通道响应异常", retryable=True)
        if not isinstance(data, dict):
            logger.error(f"节点 RCS 响应结构异常: {path}, {text}")
            return NodeRCSResult(False, error="通道响应异常", retryable=True)

        code = data.get("code")
        try:
            code = int(code)
        except (TypeError, ValueError):
            code = None

        if code == CODE_SUCCESS:
            return NodeRCSResult(True, code=code, data=data.get("data"))

        upstream_msg = str(data.get("msg") or "")[:200]
        if code == CODE_ORDER_EXISTS:
            # 拿不回原 sn，重试也没用：必须人工核查这单到底发没发
            logger.error(
                f"节点 RCS 订单号已存在（上游已受理过、但不返回原 sn，需人工核查）: "
                f"{self.channel.channel_code} {path}, msg={upstream_msg}"
            )
        else:
            logger.error(
                f"节点 RCS 业务错误: {self.channel.channel_code} {path}, "
                f"code={code}, msg={upstream_msg}"
            )
        return NodeRCSResult(
            False,
            code=code,
            error=_CODE_MESSAGE.get(code, f"发送失败（{code if code is not None else 'UNKNOWN'}）"),
            retryable=code in _RETRYABLE_CODES,
        )

    # ── 群发任务 ─────────────────────────────────────────────────────────────

    def build_create_payload(
        self,
        order_id: str,
        country_code: str,
        number_url: str,
        text: str,
        thumbnail: Optional[str] = None,
        variables: Optional[list] = None,
        is_filter: int = IS_FILTER_DIRECT,
    ) -> dict:
        """组装创建群发任务的请求体。

        category 按有无图片自动选：带 thumbnail 即图文(RCS_ImgText)，否则纯文本(RCS_Text)。
        注意 isFilter 在文档的请求示例里嵌在 content 内部（与参数表位置不一致），
        这里按示例放进 content —— 示例是实际报文，优先级高于表格。
        """
        self._require_credentials(need_product=True)
        content: dict = {"text": text or "", "isFilter": int(is_filter)}
        if thumbnail:
            content["thumbnail"] = thumbnail
        payload = {
            "account": self.account,
            "productId": self.product_id,
            "orderId": order_id,
            "business": BUSINESS_RCS,
            "category": CATEGORY_IMGTEXT if thumbnail else CATEGORY_TEXT,
            "countryCode": (country_code or "").strip().upper(),
            "numberUrl": number_url,
            "content": content,
        }
        if variables:
            payload["variable"] = list(variables)
        return payload

    async def create_send_task(self, **kwargs) -> NodeRCSResult:
        """创建群发任务。成功时 data={'sn': '节点订单号'}。"""
        payload = self.build_create_payload(**kwargs)
        result = await self._request(PATH_SEND_CREATE, payload)
        if result.success:
            sn = (result.data or {}).get("sn") if isinstance(result.data, dict) else None
            logger.info(
                f"节点 RCS 任务已创建: {self.channel.channel_code} "
                f"orderId={payload['orderId']} sn={sn}"
            )
        return result

    async def get_send_task(self, sn: str) -> NodeRCSResult:
        """查询群发任务状态。data 含 status/sum/submitNum/totalNum/sendTime/finishTime。"""
        self._require_credentials()
        return await self._request(PATH_SEND_GET, {"account": self.account, "sn": str(sn)})

    async def get_send_file(self, sn: str) -> NodeRCSResult:
        """取任务结果文件（TXT）下载地址。data={'url': ...}。"""
        self._require_credentials()
        return await self._request(PATH_SEND_FILE, {"account": self.account, "sn": str(sn)})

    async def _task_action(self, path: str, sn: str) -> NodeRCSResult:
        self._require_credentials()
        return await self._request(path, {"account": self.account, "sn": str(sn)})

    async def revoke_task(self, sn: str) -> NodeRCSResult:
        """撤销待执行任务。"""
        return await self._task_action(PATH_SEND_REVOKE, sn)

    async def pause_task(self, sn: str) -> NodeRCSResult:
        """暂停群发中的任务。返回成功不代表一定暂停，须以 getTask 为准。"""
        return await self._task_action(PATH_SEND_PAUSE, sn)

    async def recover_task(self, sn: str) -> NodeRCSResult:
        """恢复已暂停的任务。"""
        return await self._task_action(PATH_SEND_RECOVER, sn)

    async def interrupt_task(self, sn: str) -> NodeRCSResult:
        """中断任务。终态是「任务完成」，发送量随中断时机变少。"""
        return await self._task_action(PATH_SEND_INTERRUPT, sn)

    async def update_task(
        self, sn: str, text: str, thumbnail: Optional[str] = None, variables: Optional[list] = None
    ) -> NodeRCSResult:
        """修改群发中任务的文案。无更改的字段也要原样提交。"""
        self._require_credentials()
        content: dict = {"text": text or ""}
        if thumbnail:
            content["thumbnail"] = thumbnail
        payload = {"account": self.account, "sn": str(sn), "content": content}
        if variables:
            payload["variable"] = list(variables)
        return await self._request(PATH_SEND_UPDATE, payload)

    async def get_remaining(self) -> NodeRCSResult:
        """自研 RCS 群发余量查询。data=[{shortCode, count}]。"""
        self._require_credentials()
        return await self._request(
            PATH_SEND_REMAIN, {"account": self.account}, method="GET"
        )

    # ── 与叮咚适配器对齐的接口（供通道检测/管理端复用） ─────────────────────────

    async def get_balance(self) -> dict:
        """通道探测用。节点没有余额接口，用「群发余量」代替：
        一次调用同样能验证 base_url 可达 + account/secret + 签名算法。"""
        result = await self.get_remaining()
        if result.success:
            return {"success": True, "data": result.data}
        return {"success": False, "error_code": str(result.code or ""), "error": result.error}

    async def send_one(self, sms_log) -> Any:
        """节点不支持逐条发送 —— 它只有「号码文件 + 任务」模式。

        故意抛错而不是静默失败：若哪天有人把 vendor=node 的通道挂到逐条发送链路上，
        必须立刻炸出来，而不是把消息悄悄丢掉或误计费。
        """
        raise NodeRCSConfigError(
            f"节点 RCS 通道 {self.channel.channel_code} 不支持逐条发送："
            f"上游只提供「号码文件 URL + 群发任务」模式，需走批量任务链路（尚未接入）"
        )


__all__ = [
    "NodeRCSAdapter",
    "NodeRCSResult",
    "NodeRCSConfigError",
    "TASK_STATUS",
    "TASK_STATUS_FINAL",
    "TASK_STATUS_RUNNING",
    "CATEGORY_TEXT",
    "CATEGORY_IMGTEXT",
    "IS_FILTER_DIRECT",
    "IS_FILTER_SCREEN",
    "DEFAULT_BASE_URL",
]
