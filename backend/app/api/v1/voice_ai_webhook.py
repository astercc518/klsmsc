"""
AI 交互回调网关，供底层 FreeSWITCH/VOS 触发 HTTP Webhook 以获取 TTS 或者流式语音
"""
import json
from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
import traceback

from app.utils.logger import get_logger
from app.services.ai_llm_client import llm_client
from app.config import settings
import redis.asyncio as redis

logger = get_logger(__name__)

router = APIRouter(prefix="/voice_ai", tags=["Voice AI Gateway"])

# 使用全局 Redis 客户端 (通常从依赖中获取，但为了简单直接配置)
redis_client = redis.from_url(
    f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{getattr(settings, 'REDIS_DB', 0)}",
    encoding="utf8", decode_responses=True
)

class CallStartRequest(BaseModel):
    call_id: str
    callee: str
    campaign_id: Optional[int] = None
    ai_prompt: Optional[str] = None  # 营销任务配置的总体提示词

class AsrCallbackRequest(BaseModel):
    call_id: str
    asr_text: str  # 用户说的话

class HangupRequest(BaseModel):
    call_id: str

def get_session_key(call_id: str) -> str:
    return f"voice_ai_session:{call_id}"

@router.post("/call_start")
async def call_start(req: CallStartRequest):
    """
    呼叫接通时的初始化
    返回第一个播放指令（如开场白）
    """
    # 存入初始状态
    key = get_session_key(req.call_id)
    system_prompt = req.ai_prompt or "你是一个智能语音营销客服，请用简短、口语化、热情的语气进行交流。"
    
    session_data = {
        "campaign_id": req.campaign_id,
        "system_prompt": system_prompt,
        "history": []
    }
    await redis_client.setex(key, 3600, json.dumps(session_data))
    
    # 获取第一句问候语 (这里也可以直接在 Campaign 里固定配好，或者让大模型基于系统 prompt 直接说第一句话)
    # 为提高接通响应速度，通常建议用一条固定的 TTS 作为第一句，然后再交给 LLM
    initial_prompt = "喂，您好！打扰您了，很高兴为您服务。"
    
    return {
        "action": "play_and_detect",
        "tts_text": initial_prompt,
    }

@router.post("/asr_callback")
async def asr_callback(req: AsrCallbackRequest):
    """
    接收 ASR 识别结果，调用大模型返回下一句回应
    """
    key = get_session_key(req.call_id)
    data_str = await redis_client.get(key)
    
    if not data_str:
        logger.warning(f"由于会话已过期或未初始化，跳过 ASR: {req.call_id}")
        return {"action": "hangup"}
        
    session_data = json.loads(data_str)
    system_prompt = session_data.get("system_prompt", "")
    history = session_data.get("history", [])
    
    # 增加用户的输入
    history.append({"role": "user", "content": req.asr_text})
    
    # 请求大模型
    try:
        reply_text = await llm_client.chat(messages=history, system_prompt=system_prompt)
    except Exception as e:
        logger.error(f"处理 LLM 异常: {traceback.format_exc()}")
        reply_text = "不好意思，我这边信号不太好，您能再说一遍吗？"
        
    # 保存 LLM 返回
    history.append({"role": "assistant", "content": reply_text})
    session_data["history"] = history
    
    # 更新 Redis
    await redis_client.setex(key, 3600, json.dumps(session_data))
    
    # 控制 FreeSWITCH 播放该音频，并重新进入 ASR 侦测状态
    return {
        "action": "play_and_detect",
        "tts_text": reply_text
    }

@router.post("/hangup")
async def hangup(req: HangupRequest):
    """
    通话挂断，清理缓存
    """
    key = get_session_key(req.call_id)
    await redis_client.delete(key)
    return {"success": True}
