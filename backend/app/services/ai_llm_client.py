"""
AI LLM 会话客户端，用于处理语音外呼时的对话逻辑
"""
import httpx
import json
from typing import List, Dict, Any, Optional
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

class AILlmClient:
    def __init__(self):
        # 默认使用 OpenAI 兼容的 API
        self.api_url = getattr(settings, "LLM_API_URL", "https://api.openai.com/v1/chat/completions")
        self.api_key = getattr(settings, "LLM_API_KEY", "")
        self.model = getattr(settings, "LLM_MODEL", "gpt-3.5-turbo")

    async def chat(self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None) -> str:
        if not self.api_key:
            logger.warning("LLM_API_KEY 未配置，返回模拟回答")
            return "您好，我暂时无法连接到智能大脑，请稍后再试。"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": []
        }
        
        if system_prompt:
            payload["messages"].append({"role": "system", "content": system_prompt})
            
        payload["messages"].extend(messages)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.api_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM API 请求失败: {e}")
            return "不好意思，我刚刚走神了，您能重复一遍吗？"

llm_client = AILlmClient()
