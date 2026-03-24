"""AI 文案生成 API"""
import re
import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from app.config import settings
from app.utils.logger import get_logger
from app.core.auth import get_current_account
from app.modules.common.account import Account

logger = get_logger(__name__)
router = APIRouter()


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
    return {
        "ai_enabled": bool(settings.AI_API_KEY),
        "model": settings.AI_MODEL if settings.AI_API_KEY else None,
    }


@router.post("/generate-sms", response_model=GenerateSmsResponse)
async def generate_sms(req: GenerateSmsRequest, account: Account = Depends(get_current_account)):
    """调用外部 AI API 批量生成短信文案"""
    if not settings.AI_API_KEY:
        raise HTTPException(400, "AI 功能未配置，请在环境变量中设置 AI_API_KEY")

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
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                settings.AI_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.AI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.AI_MODEL,
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

        raw_text = data["choices"][0]["message"]["content"].strip()

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
            cleaned = re.sub(r"\s{2,}", " ", cleaned)
            if cleaned:
                lines.append(cleaned[:req.max_length])

        return GenerateSmsResponse(success=True, messages=lines, source="ai")

    except httpx.HTTPStatusError as e:
        logger.error(f"AI API 返回错误: {e.response.status_code} - {e.response.text}")
        raise HTTPException(502, f"AI 服务返回错误: {e.response.status_code}")
    except Exception as e:
        logger.error(f"AI API 调用失败: {e}")
        raise HTTPException(502, f"AI 服务暂不可用: {str(e)}")
