"""GeeTest v4 验证码求解 (CapSolver)。

注水注册:部分博彩商户(如 8kbdtf4/rztk6mpvx)注册开启 GeeTest v4,纯接口提交会被
`geetest_captcha_err #1066` 拒。本模块调 CapSolver 的 GeeTestTaskProxyLess 解出
v4 通过凭证,供 jl_api_register 塞进注册体的 `geetestValidateV4` 字段。

返回的 dict 字段(captcha_id/lot_number/pass_token/gen_time/captcha_output)就是站点
前端 SDK getValidate() 的结果结构,直接作为 geetestValidateV4 的值即可。

无 CAPSOLVER_API_KEY 时返回 None,调用方据此跳过/降级。
"""
from __future__ import annotations
import re
import time
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# CapSolver v4 solution 里需要透传给站点的字段
_V4_FIELDS = ("captcha_id", "lot_number", "pass_token", "gen_time", "captcha_output", "risk_type")


def solve_geetest_v4(captcha_id: str, website_url: str,
                     timeout: int = 120, poll_interval: float = 3.0) -> Optional[dict]:
    """解 GeeTest v4。成功返回 {captcha_id, lot_number, pass_token, gen_time, captcha_output[, risk_type]}。
    失败/无 key 返回 None。"""
    key = settings.CAPSOLVER_API_KEY
    if not key:
        logger.warning("geetest_solver: 未配置 CAPSOLVER_API_KEY,跳过求解")
        return None
    base = (settings.CAPSOLVER_API_URL or "https://api.capsolver.com").rstrip("/")

    try:
        with httpx.Client(timeout=30.0) as cli:
            r = cli.post(f"{base}/createTask", json={
                "clientKey": key,
                "task": {
                    "type": "GeeTestTaskProxyLess",
                    "websiteURL": website_url,
                    "captchaId": captcha_id,
                    "version": 4,
                },
            })
            j = r.json()
            if j.get("errorId"):
                logger.error("geetest_solver: createTask 失败 %s/%s", j.get("errorCode"), j.get("errorDescription"))
                return None
            task_id = j.get("taskId")
            if not task_id:
                logger.error("geetest_solver: createTask 无 taskId: %s", str(j)[:200])
                return None

            deadline = time.time() + timeout
            while time.time() < deadline:
                time.sleep(poll_interval)
                rr = cli.post(f"{base}/getTaskResult", json={"clientKey": key, "taskId": task_id})
                jr = rr.json()
                if jr.get("errorId"):
                    logger.error("geetest_solver: getTaskResult 失败 %s/%s",
                                 jr.get("errorCode"), jr.get("errorDescription"))
                    return None
                status = jr.get("status")
                if status == "ready":
                    sol = jr.get("solution") or {}
                    out = {k: sol[k] for k in _V4_FIELDS if k in sol}
                    out.setdefault("captcha_id", captcha_id)
                    logger.info("geetest_solver: 解出 v4 凭证 lot=%s", str(out.get("lot_number"))[:16])
                    return out
                # status == "processing" → 继续轮询
            logger.error("geetest_solver: 求解超时 (%ss)", timeout)
            return None
    except Exception as e:
        logger.error("geetest_solver: 异常 %r", e)
        return None


def eval_captcha_answer(text: Optional[str]) -> Optional[str]:
    """把图形验证码 OCR 文本转成应填答案。

    两型:纯数字(如 45861 → 45861)或算术式(如 9-5=? → 4)。命中运算符则求值,否则取其中数字。
    供 TK688 等 handler 与配置脚本引擎共用。无法解析返回 None。
    """
    if not text:
        return None
    t = (text.strip().replace("=", "").replace("?", "").replace(" ", "")
         .replace("×", "*").replace("x", "*").replace("X", "*").replace("÷", "/"))
    m = re.match(r'^(\d+)\s*([+\-*/])\s*(\d+)$', t)
    if m:
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        try:
            if op == "+":
                return str(a + b)
            if op == "-":
                return str(a - b)
            if op == "*":
                return str(a * b)
            if op == "/":
                return str(a // b) if b else None
        except Exception:
            return None
    digits = re.sub(r"\D", "", t)
    return digits or None


def solve_image_captcha(image_base64: str, module: str = "common",
                        timeout: int = 45) -> Optional[str]:
    """解普通图形验证码(base64 图 → 文本)。用于 TK688 等站的数字/字母验证码。

    image_base64 传纯 base64(不含 `data:image/png;base64,` 前缀)。CapSolver
    ImageToTextTask 多数同步在 createTask 直接返回 solution.text;个别情况回落轮询。
    失败/无 key 返回 None。
    """
    key = settings.CAPSOLVER_API_KEY
    if not key:
        logger.warning("image_captcha: 未配置 CAPSOLVER_API_KEY,跳过求解")
        return None
    base = (settings.CAPSOLVER_API_URL or "https://api.capsolver.com").rstrip("/")
    try:
        with httpx.Client(timeout=float(timeout)) as cli:
            j = cli.post(f"{base}/createTask", json={
                "clientKey": key,
                "task": {"type": "ImageToTextTask", "body": image_base64, "module": module},
            }).json()
            if j.get("errorId"):
                logger.error("image_captcha: createTask 失败 %s/%s",
                             j.get("errorCode"), j.get("errorDescription"))
                return None
            sol = j.get("solution") or {}
            if sol.get("text") is not None:
                return (sol.get("text") or "").strip() or None
            # 极少数走异步:轮询取结果
            task_id = j.get("taskId")
            if task_id:
                deadline = time.time() + timeout
                while time.time() < deadline:
                    time.sleep(2)
                    jr = cli.post(f"{base}/getTaskResult",
                                  json={"clientKey": key, "taskId": task_id}).json()
                    if jr.get("status") == "ready":
                        return ((jr.get("solution") or {}).get("text") or "").strip() or None
            return None
    except Exception as e:
        logger.error("image_captcha: 异常 %r", e)
        return None
