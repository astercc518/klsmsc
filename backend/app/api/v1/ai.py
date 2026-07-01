"""AI 文案生成 API"""
import re
import asyncio
import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.utils.logger import get_logger
from app.core.auth import get_current_account
from app.modules.common.account import Account
from app.database import get_db

logger = get_logger(__name__)
router = APIRouter()


def _ai_is_google() -> bool:
    return (settings.AI_PROVIDER or "openai").strip().lower() in ("google", "gemini")


def _ai_key() -> Optional[str]:
    """当前生效的 AI 密钥（Google 优先用 GEMINI_API_KEY，回退 AI_API_KEY）。"""
    if _ai_is_google():
        return settings.GEMINI_API_KEY or settings.AI_API_KEY
    return settings.AI_API_KEY


def _ai_model() -> str:
    if _ai_is_google():
        return settings.GEMINI_MODEL or settings.AI_MODEL
    return settings.AI_MODEL


async def _ai_chat(system_prompt: str, user_prompt: str) -> str:
    """统一 LLM 调用：Google Gemini 原生接口 或 OpenAI 兼容接口（DeepSeek 等），返回模型文本。"""
    key = _ai_key()
    if not key:
        raise HTTPException(400, "AI 功能未配置")
    client_kwargs: dict = {"timeout": 30.0}
    if settings.AI_HTTP_PROXY:
        client_kwargs["proxies"] = settings.AI_HTTP_PROXY
    async with httpx.AsyncClient(**client_kwargs) as client:
        if _ai_is_google():
            model = _ai_model()
            url = f"{settings.GEMINI_API_BASE.rstrip('/')}/models/{model}:generateContent"
            resp = await client.post(
                url,
                params={"key": key},
                headers={"Content-Type": "application/json"},
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                    "generationConfig": {"temperature": 0.9, "maxOutputTokens": 2000},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            cands = data.get("candidates") or []
            if not cands:
                return ""
            parts = (cands[0].get("content") or {}).get("parts") or []
            return "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
        resp = await client.post(
            settings.AI_API_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": _ai_model(),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.9,
                "max_tokens": 2000,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


class GenerateSmsRequest(BaseModel):
    prompt: str = Field(..., description="用户描述，如: 巴西博彩推广短信")
    count: int = Field(default=5, ge=1, le=20, description="生成条数")
    language: str = Field(default="zh", description="目标语言: zh/en/pt/es/vi 等")
    max_length: int = Field(default=300, description="单条最大字符数")


class GenerateSmsResponse(BaseModel):
    success: bool
    messages: List[str] = []
    source: str = ""  # "ai" 或 "template"


@router.get("/config")
async def ai_config(account: Account = Depends(get_current_account)):
    """返回 AI 功能是否可用"""
    key = _ai_key()
    return {
        "ai_enabled": bool(key),
        "model": _ai_model() if key else None,
        "provider": "google" if _ai_is_google() else "openai",
    }


@router.post("/generate-sms", response_model=GenerateSmsResponse)
async def generate_sms(
    req: GenerateSmsRequest,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """调用外部 AI API 批量生成短信文案（支持 Google Gemini / OpenAI 兼容接口）"""
    if not _ai_key():
        raise HTTPException(400, "AI 功能未配置，请配置 GEMINI_API_KEY（Google）或 AI_API_KEY")

    lang_map = {
        "zh": "中文", "en": "English", "bn": "বাংলা (Bengali)",
        "pt": "Português", "es": "Español", "vi": "Tiếng Việt", "th": "ภาษาไทย",
        "id": "Bahasa Indonesia", "ja": "日本語", "ko": "한국어",
    }
    lang_name = lang_map.get(req.language, req.language)

    system_prompt = (
        "你是一位专业的营销短信文案专家。"
        "根据用户描述生成短信文案，要求：\n"
        "1. 内容简洁有吸引力，单条不超过 {max_len} 字符\n"
        "2. 每条文案各不相同，风格多样\n"
        "3. 只输出文案列表，每条一行，行首用数字编号\n"
        "4. 不要输出解释或额外说明\n"
        "5. 使用 {lang} 语言\n"
        "6. 严禁使用任何 emoji 表情符号（如😀🔥💰等），只使用纯文字\n"
        "7. 内容不得包含敏感违规词汇（赌博、色情、毒品、暴力、恐怖等），保持内容合规"
    ).format(max_len=req.max_length, lang=lang_name)

    user_prompt = f"请生成 {req.count} 条短信文案。主题/场景: {req.prompt}"

    try:
        raw_text = (await _ai_chat(system_prompt, user_prompt)).strip()

        # 解析编号列表，每行类似 "1. 文案内容" 或 "1、文案内容"
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF\U00002600-\U000027BF\U0000FE00-\U0000FE0F"
            "\U0001F900-\U0001F9FF\U0000200D\U000020E3\U00002702-\U000027B0"
            "\U000E0020-\U000E007F]+",
            flags=re.UNICODE,
        )
        lines = []
        for line in raw_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            cleaned = re.sub(r"^\d+[.、)\]\s]+", "", line).strip()
            cleaned = emoji_pattern.sub("", cleaned).strip()
            # 注意：不压缩内部连续空格——上游模板审核常按字节精确比对，
            # 「! 」「!  」是两个不同模板；以前 re.sub(r"\s{2,}", " ", ...) 会把
            # 客户特意保留的双空格压成单空格，导致提交 65 字符发送变 64 字符。
            if cleaned:
                lines.append(cleaned[:req.max_length])

        # AI 输出二次过滤：丢弃命中全局违禁词的行（仅全局，AI 阶段无通道/国家）
        from app.utils.banned_words import check_banned_words
        from app.services.operation_log import log_operation
        safe_lines: List[str] = []
        dropped_hits: List[str] = []
        for ln in lines:
            hit = await check_banned_words(db, ln)
            if hit:
                dropped_hits.append(hit)
            else:
                safe_lines.append(ln)
        if dropped_hits:
            await log_operation(
                db, module="security", action="content_blocked",
                title=f"AI 生成内容违禁词过滤：丢 {len(dropped_hits)}/{len(lines)} 条",
                target_type="account", target_id=account.id,
                detail={"account_id": account.id, "stage": "ai_output", "hits": dropped_hits[:10], "kept": len(safe_lines), "dropped": len(dropped_hits)},
                status="failed", error_message="CONTENT_BLOCKED",
            )

        return GenerateSmsResponse(success=True, messages=safe_lines, source="ai")

    except httpx.HTTPStatusError as e:
        logger.error(f"AI API 返回错误: {e.response.status_code} - {e.response.text}")
        raise HTTPException(502, f"AI 服务返回错误: {e.response.status_code}")
    except Exception as e:
        logger.error(f"AI API 调用失败: {e}")
        raise HTTPException(502, f"AI 服务暂不可用: {str(e)}")


async def _google_translate(client: httpx.AsyncClient, text: str, source: str, target: str) -> str:
    """调用 Google gtx 免 key 接口翻译单条文本；失败返回空串。"""
    if not text.strip():
        return ""
    try:
        resp = await client.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text},
        )
        resp.raise_for_status()
        data = resp.json()
        # data[0] 为分句数组，每项 [译文, 原文, ...]；拼接所有译文段
        return "".join(seg[0] for seg in (data[0] or []) if seg and seg[0])
    except Exception as e:
        logger.warning(f"翻译失败（已跳过）: {e}")
        return ""


class TranslateRequest(BaseModel):
    texts: List[str] = Field(..., description="待翻译文本列表")
    target: str = Field(default="zh-CN", description="目标语言")
    source: str = Field(default="auto", description="源语言，auto 为自动识别")


class TranslateResponse(BaseModel):
    success: bool
    translations: List[str] = []


@router.post("/translate", response_model=TranslateResponse)
async def translate(
    req: TranslateRequest,
    account: Account = Depends(get_current_account),
):
    """免费 Google 翻译代理：把生成的外语文案翻成中文做对照。无需 AI_API_KEY。

    逐条调用 Google gtx 免 key 接口并发翻译；单条失败回退为空串，不影响其它条目。
    """
    texts = (req.texts or [])[:50]
    if not texts:
        return TranslateResponse(success=True, translations=[])
    try:
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            results = await asyncio.gather(*[_google_translate(client, t, req.source, req.target) for t in texts])
        return TranslateResponse(success=True, translations=list(results))
    except Exception as e:
        logger.error(f"翻译服务调用失败: {e}")
        return TranslateResponse(success=False, translations=["" for _ in texts])


# 往返翻译用的中转语言池（覆盖差异较大的语系，回译后措辞更分散；池越大可去重后留下的不同变体越多）
_PARAPHRASE_PIVOTS = [
    "en", "zh-CN", "ja", "ko", "es", "pt", "vi", "id",
    "fr", "de", "ru", "ar", "hi", "tr", "it", "th",
    "pl", "nl", "uk", "el", "fa", "ms", "ta", "bn",
    "sw", "ro", "cs", "he",
]
# 链接识别（与前端一致），往返翻译前抽走链接，回译后原样拼回，保证链接不被翻译破坏
_URL_RE = re.compile(r"(https?://[^\s]+|(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?)", re.IGNORECASE)


class ParaphraseRequest(BaseModel):
    text: str = Field(..., description="原始文案")
    lang: str = Field(default="auto", description="文案语言（也是生成变体的语言）")
    count: int = Field(default=5, ge=1, le=20, description="生成条数")


class ParaphraseResponse(BaseModel):
    success: bool
    variants: List[str] = []
    source: str = "translate"


@router.post("/paraphrase", response_model=ParaphraseResponse)
async def paraphrase(
    req: ParaphraseRequest,
    account: Account = Depends(get_current_account),
):
    """用 Google 翻译做「往返翻译改写」：原文 → 不同中转语言 → 译回原语言，得到多条措辞不同的同义文案。
    无需 AI_API_KEY，适合本地模板引擎改不动的语言（如泰语）。链接抽走保护、回译后拼回。
    """
    text = (req.text or "").strip()
    if not text:
        return ParaphraseResponse(success=True, variants=[])

    lang = req.lang if req.lang and req.lang != "auto" else "auto"
    # 抽走链接，仅对正文做往返翻译，回译后把链接拼回末尾
    urls = _URL_RE.findall(text)
    body = _URL_RE.sub("", text).strip()
    body = re.sub(r"\s{2,}", " ", body)
    tail = ("" if not urls else " " + " ".join(urls))

    if not body:
        return ParaphraseResponse(success=True, variants=[text])

    # 中转语言数取条数 3 倍留足去重余量（回译常出现重复）；去掉与目标语言相同的中转语
    base_lang = (lang.split("-")[0] if lang != "auto" else "")
    pivots = [p for p in _PARAPHRASE_PIVOTS if p.split("-")[0] != base_lang]
    pivots = pivots[: min(len(pivots), max(req.count * 3, req.count + 4))]

    async def round_trip(client: httpx.AsyncClient, pivot: str) -> str:
        src = lang  # auto 时让 Google 自动识别第一跳
        mid = await _google_translate(client, body, src, pivot)
        if not mid:
            return ""
        # 第二跳从中转语译回目标语言；auto 时退回中转语的反向（仍用 auto 识别）
        back_target = base_lang or "auto"
        back = await _google_translate(client, mid, pivot, back_target if back_target != "auto" else "auto")
        return back.strip()

    try:
        async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            results = await asyncio.gather(*[round_trip(client, p) for p in pivots])
    except Exception as e:
        logger.error(f"往返翻译改写失败: {e}")
        return ParaphraseResponse(success=False, variants=[])

    seen = set()
    variants: List[str] = []
    # 原文本身也算一条候选（放最前），其余去重
    for cand in [body] + results:
        c = (cand or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        variants.append((c + tail).strip())
        if len(variants) >= req.count:
            break

    return ParaphraseResponse(success=True, variants=variants)
