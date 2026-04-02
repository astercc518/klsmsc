"""
批量发送 Celery Worker
"""
import os
import csv
import io
import time
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.workers.celery_app import celery_app
from app.config import settings
from app.modules.sms.sms_batch import SmsBatch, BatchStatus
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.sms_template import SmsTemplate
from app.modules.common.account import Account
from app.core.pricing import PricingEngine
from app.core.router import RoutingEngine
from app.utils.queue import QueueManager
from app.utils.validator import Validator
from app.utils.logger import get_logger
from app.utils.errors import InsufficientBalanceError, PricingNotFoundError

logger = get_logger(__name__)

def _get_worker_session():
    """为 worker 创建独立的数据库会话"""
    eng = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URL,
        echo=False,
        pool_size=2,
        max_overflow=3,
        pool_pre_ping=True,
        pool_recycle=600,
    )
    return async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)()

def _run_async(coro):
    """在 Celery 同步 worker 中安全地执行异步协程"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@celery_app.task(name='process_batch', bind=True)
def process_batch(self, batch_id: int):
    """
    异步处理批量发送任务
    """
    logger.info(f"开始处理批量发送任务: batch_id={batch_id}")
    return _run_async(_do_process_batch(batch_id))

async def _do_process_batch(batch_id: int):
    db = _get_worker_session()
    try:
        # 1. 获取批次记录
        result = await db.execute(select(SmsBatch).where(SmsBatch.id == batch_id))
        batch = result.scalar_one_or_none()
        if not batch:
            logger.error(f"批次记录不存在: {batch_id}")
            return
        
        if batch.status != BatchStatus.PENDING:
            logger.warning(f"批次状态不是 PENDING: {batch_id}, status={batch.status}")
            return

        # 2. 更新状态为处理中
        batch.status = BatchStatus.PROCESSING
        batch.started_at = datetime.now()
        await db.commit()

        # 3. 准备工具
        pricing_engine = PricingEngine(db)
        routing_engine = RoutingEngine(db)
        validator = Validator()
        
        # 获取模板（如果使用）
        template = None
        if batch.template_id:
            result = await db.execute(select(SmsTemplate).where(SmsTemplate.id == batch.template_id))
            template = result.scalar_one_or_none()
            if not template:
                logger.error(f"模板不存在: batch_id={batch_id}, template_id={batch.template_id}")
                batch.status = BatchStatus.FAILED
                batch.error_message = f"模板 ID {batch.template_id} 不存在"
                await db.commit()
                return

        # 4. 读取 CSV 文件
        if not batch.file_path or not os.path.exists(batch.file_path):
            logger.error(f"文件不存在: {batch.file_path}")
            batch.status = BatchStatus.FAILED
            batch.error_message = "文件不存在"
            await db.commit()
            return

        # 检测编码
        detected_enc = "utf-8"
        try:
            with open(batch.file_path, 'rb') as f:
                sample = f.read(4096)
                for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
                    try:
                        sample.decode(enc)
                        detected_enc = enc
                        break
                    except UnicodeDecodeError:
                        continue
        except Exception:
            pass

        # 解析文件
        rows = []
        try:
            with open(batch.file_path, 'r', encoding=detected_enc, errors='replace') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except Exception as e:
            logger.error(f"解析 CSV 失败: {e}")
            batch.status = BatchStatus.FAILED
            batch.error_message = f"解析 CSV 失败: {str(e)}"
            await db.commit()
            return

        total_rows = len(rows)
        if total_rows == 0:
            batch.status = BatchStatus.FAILED
            batch.error_message = "CSV 文件为空"
            await db.commit()
            return

        # 5. 逐行处理
        success_count = 0
        failed_count = 0
        
        for i, row in enumerate(rows):
            # 校验进度汇报频率
            if i % 100 == 0:
                batch.progress = int(i * 100 / total_rows)
                await db.commit()

            phone = row.get('phone', '').strip()
            if not phone:
                failed_count += 1
                continue

            # 渲染内容
            content = ""
            if template:
                # 简单变量替换: {name} -> row['name']
                content = template.content
                for key, val in row.items():
                    if key != 'phone':
                        content = content.replace(f"{{{key}}}", str(val))
            else:
                # 如果没有模板，可能 CSV 中有 content 列？
                content = row.get('content', '').strip()
            
            if not content:
                failed_count += 1
                continue

            # 验证并格式化号码
            e164, country_code = validator.validate_phone(phone)
            if not e164:
                failed_count += 1
                continue

            # 选择通道
            try:
                channel = await routing_engine.select_channel(country_code)
                if not channel:
                    failed_count += 1
                    continue
                
                # 计费
                charge_result = await pricing_engine.calculate_and_charge(
                    account_id=batch.account_id,
                    channel_id=channel.id,
                    country_code=country_code,
                    message=content
                )
                
                # 创建短信记录
                message_id = f"MSG_{int(time.time()*1000)}_{i}_{batch.id}"
                sms_log = SMSLog(
                    message_id=message_id,
                    account_id=batch.account_id,
                    batch_id=batch.id,
                    phone_number=e164,
                    country_code=country_code,
                    message=content,
                    message_count=charge_result.get("message_count", 1),
                    channel_id=channel.id,
                    cost_price=charge_result.get("total_base_cost", 0),
                    selling_price=charge_result.get("total_cost", 0),
                    currency=charge_result.get("currency", "USD"),
                    status="queued",
                    submit_time=datetime.now()
                )
                db.add(sms_log)
                await db.flush() # 获取 ID 或确保记录入库

                # 入队
                if QueueManager.queue_sms(message_id):
                    success_count += 1
                else:
                    # 退款
                    await _refund_single(db, batch.account_id, charge_result.get("total_cost", 0), message_id)
                    sms_log.status = "failed"
                    sms_log.error_message = "Queue failed"
                    failed_count += 1
                
            except (InsufficientBalanceError, PricingNotFoundError, Exception) as e:
                logger.warning(f"处理行 {i} 失败: {e}")
                failed_count += 1
                continue

        # 6. 完成处理
        batch.success_count = success_count
        batch.failed_count = failed_count
        batch.status = BatchStatus.COMPLETED
        batch.completed_at = datetime.now()
        batch.progress = 100
        await db.commit()
        
        logger.info(f"批次处理完成: batch_id={batch_id}, total={total_rows}, success={success_count}, failed={failed_count}")

    except Exception as e:
        logger.exception(f"处理批次异常: {e}")
        try:
            batch.status = BatchStatus.FAILED
            batch.error_message = str(e)[:500]
            await db.commit()
        except:
            pass
    finally:
        await db.close()

async def _refund_single(db, account_id: int, amount: float, message_id: str):
    """入队失败退款"""
    if amount <= 0:
        return
    try:
        from app.modules.common.balance_log import BalanceLog
        await db.execute(
            update(Account).where(Account.id == account_id)
            .values(balance=Account.balance + amount)
        )
        bal = await db.execute(select(Account.balance).where(Account.id == account_id))
        db.add(BalanceLog(
            account_id=account_id, change_type='refund', amount=amount,
            balance_after=float(bal.scalar()),
            description=f"Batch queue fail refund: {message_id}"
        ))
    except Exception as e:
        logger.error(f"退款失败: {message_id}, {e}")
