import random
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.voice.voice_inbound import VoiceQueue
from app.modules.voice.voice_extension import VoiceExtension
from app.utils.logger import get_logger

logger = get_logger(__name__)

async def get_best_agent(db: AsyncSession, queue_id: int) -> Optional[str]:
    """
    ACD 核心算法：为队列分配最佳坐席。
    """
    # 1. 获取队列配置
    res = await db.execute(select(VoiceQueue).where(VoiceQueue.id == queue_id))
    queue = res.scalar_one_or_none()
    if not queue or not queue.agents:
        return None
        
    agent_numbers = [a.strip() for a in queue.agents.split(",") if a.strip()]
    if not agent_numbers:
        return None
        
    # 2. 查询这些坐席的当前状态
    # 必须是 active 且 agent_state 为 'idle'
    stmt = select(VoiceExtension).where(
        VoiceExtension.extension_number.in_(agent_numbers),
        VoiceExtension.status == "active",
        VoiceExtension.agent_state == "idle"
    )
    res_agents = await db.execute(stmt)
    available_agents = res_agents.scalars().all()
    
    if not available_agents:
        return None
        
    # 3. 根据策略选择
    strategy = queue.strategy or "longest_idle"
    
    if strategy == "longest_idle":
        # 最长空闲：按 last_state_change 升序排列（越久以前改变状态的越空闲）
        sorted_agents = sorted(
            available_agents, 
            key=lambda x: x.last_state_change if x.last_state_change else x.created_at
        )
        selected = sorted_agents[0]
        
    elif strategy == "random":
        selected = random.choice(available_agents)
        
    elif strategy == "ring_all":
        # 简单起见，返回第一个。高级实现可能返回所有号码供网关并行拨打。
        selected = available_agents[0]
        
    else:
        selected = available_agents[0]
        
    logger.info(f"ACD: Queue {queue_id} selected Agent {selected.extension_number} using {strategy}")
    return selected.extension_number
