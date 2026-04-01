"""
数据库连接管理
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings
from app.utils.logger import get_logger

_schema_logger = get_logger(__name__)

# 创建异步引擎（仅开发环境开启 SQL echo，避免泄露敏感信息）
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.APP_DEBUG and settings.APP_ENV == "development"),
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=3600
)

# 创建会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# 声明基类
Base = declarative_base()


async def get_db() -> AsyncSession:
    """获取数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def ensure_channel_dlr_preference_columns():
    """
    与 Channel ORM 对齐：补齐 channels 表 DLR 相关列。
    未执行手工迁移时，SELECT Channel 会因 Unknown column 导致整站 500；启动时自动 ALTER。
    仅处理 MySQL / MariaDB。
    """
    url = (settings.DATABASE_URL or "").lower()
    if "mysql" not in url and "mariadb" not in url:
        return
    col_defs = [
        (
            "smpp_dlr_socket_hold_seconds",
            "INT NULL DEFAULT NULL COMMENT 'SMPP发送成功后保持TCP秒数以接收deliver_sm'",
        ),
        (
            "dlr_sent_timeout_hours",
            "INT NULL DEFAULT NULL COMMENT 'sent状态最长等待终态DLR小时数'",
        ),
    ]
    try:
        async with engine.begin() as conn:
            for col_name, col_sql in col_defs:
                r = await conn.execute(
                    text(
                        "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'channels' "
                        "AND COLUMN_NAME = :col"
                    ),
                    {"col": col_name},
                )
                row = r.first()
                if row and (row[0] or 0) > 0:
                    continue
                await conn.execute(
                    text(f"ALTER TABLE channels ADD COLUMN `{col_name}` {col_sql}")
                )
                _schema_logger.info("已自动补齐 channels 列: %s", col_name)
    except Exception as e:
        _schema_logger.warning(
            "自动补齐 channels DLR 列失败（请手动执行 scripts/add_channel_dlr_columns.sql）: %s",
            e,
        )


async def ensure_sales_commission_total_cost_columns():
    """
    与 SalesCommissionSettlement / SalesCommissionDetail ORM 对齐：补齐 total_cost。
    未执行 alembic 时查询会因 Unknown column 导致员工结算接口 500；启动时自动 ALTER。
    仅处理 MySQL / MariaDB。
    """
    url = (settings.DATABASE_URL or "").lower()
    if "mysql" not in url and "mariadb" not in url:
        return
    specs = [
        ("sales_commission_settlements", "名下客户短信成本汇总"),
        ("sales_commission_details", "该客户周期内成本"),
    ]
    try:
        async with engine.begin() as conn:
            for table_name, col_comment in specs:
                t = await conn.execute(
                    text(
                        "SELECT COUNT(*) AS c FROM information_schema.TABLES "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tbl"
                    ),
                    {"tbl": table_name},
                )
                tr = t.first()
                if not tr or (tr[0] or 0) == 0:
                    continue
                r = await conn.execute(
                    text(
                        "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tbl "
                        "AND COLUMN_NAME = 'total_cost'"
                    ),
                    {"tbl": table_name},
                )
                row = r.first()
                if row and (row[0] or 0) > 0:
                    continue
                # 与 alembic 004：Numeric(14,4) NOT NULL DEFAULT 0 一致
                await conn.execute(
                    text(
                        f"ALTER TABLE `{table_name}` ADD COLUMN `total_cost` "
                        f"DECIMAL(14,4) NOT NULL DEFAULT 0 COMMENT '{col_comment}'"
                    )
                )
                _schema_logger.info("已自动补齐 %s.total_cost", table_name)
    except Exception as e:
        _schema_logger.warning(
            "自动补齐 sales_commission total_cost 列失败（请执行 alembic upgrade 或手工 ALTER）: %s",
            e,
        )


async def ensure_voice_campaign_ai_prompt_column():
    """
    自动为 voice_outbound_campaigns 补充 ai_prompt 字段
    """
    url = (settings.DATABASE_URL or "").lower()
    if "mysql" not in url and "mariadb" not in url:
        return
    try:
        async with engine.begin() as conn:
            r = await conn.execute(
                text(
                    "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'voice_outbound_campaigns' "
                    "AND COLUMN_NAME = 'ai_prompt'"
                )
            )
            row = r.first()
            if row and (row[0] or 0) == 0:
                await conn.execute(
                    text(
                        "ALTER TABLE `voice_outbound_campaigns` ADD COLUMN `ai_prompt` "
                        "TEXT NULL COMMENT 'AI 外呼营销提示词对话脚本'"
                    )
                )
                _schema_logger.info("已自动补齐 voice_outbound_campaigns.ai_prompt")
                
            # Check and add tts_voice_id
            r2 = await conn.execute(
                text(
                    "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'voice_outbound_campaigns' "
                    "AND COLUMN_NAME = 'tts_voice_id'"
                )
            )
            row2 = r2.first()
            if row2 and (row2[0] or 0) == 0:
                await conn.execute(
                    text(
                        "ALTER TABLE `voice_outbound_campaigns` ADD COLUMN `tts_voice_id` "
                        "VARCHAR(64) NULL COMMENT '大模型TTS发音人音色ID'"
                    )
                )
                _schema_logger.info("已自动补齐 voice_outbound_campaigns.tts_voice_id")
                
            # Check and add interruptible
            r3 = await conn.execute(
                text(
                    "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'voice_outbound_campaigns' "
                    "AND COLUMN_NAME = 'interruptible'"
                )
            )
            row3 = r3.first()
            if row3 and (row3[0] or 0) == 0:
                await conn.execute(
                    text(
                        "ALTER TABLE `voice_outbound_campaigns` ADD COLUMN `interruptible` "
                        "TINYINT(1) DEFAULT 1 COMMENT 'AI交互时是否允许被用户语音打断'"
                    )
                )
                _schema_logger.info("已自动补齐 voice_outbound_campaigns.interruptible")
    except Exception as e:
        _schema_logger.warning(
            "自动补齐 voice_outbound_campaigns AI 相关字段失败: %s", e
        )

async def ensure_voice_call_ai_columns():
    """自动给 historical 的 voice_calls 表增加 AI 分析等冗余字段"""
    try:
        from sqlalchemy import text
        from app.database import engine
        async with engine.begin() as conn:
            r = await conn.execute(
                text(
                    "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'voice_calls' "
                    "AND COLUMN_NAME = 'ai_transcript'"
                )
            )
            row = r.first()
            if row and (row[0] or 0) == 0:
                await conn.execute(
                    text(
                        "ALTER TABLE `voice_calls` "
                        "ADD COLUMN `ai_transcript` LONGTEXT NULL COMMENT 'JSON格式的话术剧本数组留存', "
                        "ADD COLUMN `ai_intent` VARCHAR(32) NULL COMMENT 'AI判定的最高意向或标签', "
                        "ADD COLUMN `ai_summary` TEXT NULL COMMENT '该通外呼的小结提炼'"
                    )
                )
                _schema_logger.info("已自动补齐 voice_calls AI意向字段 (ai_transcript, ai_intent, ai_summary)")
    except Exception as e:
        _schema_logger.warning("自动补齐 voice_calls AI相关字段失败: %s", e)

async def ensure_voice_account_advanced_columns():
    """自动给 voice_accounts 表增加 routing_group 等高级字段"""
    url = (settings.DATABASE_URL or "").lower()
    if "mysql" not in url and "mariadb" not in url:
        return
    try:
        from sqlalchemy import text
        from app.database import engine
        async with engine.begin() as conn:
            r = await conn.execute(
                text(
                    "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'voice_accounts' "
                    "AND COLUMN_NAME = 'routing_group'"
                )
            )
            row = r.first()
            if row and (row[0] or 0) == 0:
                await conn.execute(
                    text(
                        "ALTER TABLE `voice_accounts` "
                        "ADD COLUMN `routing_group` VARCHAR(50) NULL COMMENT 'VOS 路由组名称', "
                        "ADD COLUMN `rate_group` VARCHAR(50) NULL COMMENT 'VOS 费率组名称', "
                        "ADD COLUMN `vos_caller_id` VARCHAR(50) NULL COMMENT 'VOS 固定外显主叫'"
                    )
                )
                _schema_logger.info("已自动补齐 voice_accounts 高级开户字段 (routing_group, rate_group, vos_caller_id)")
    except Exception as e:
        _schema_logger.warning("自动补齐 voice_accounts 高级开户字段失败: %s", e)

async def ensure_voice_okcc_columns():
    """自动给 voice_extensions 和 voice_outbound_campaigns 补充 OKCC 风格字段"""
    url = (settings.DATABASE_URL or "").lower()
    if "mysql" not in url and "mariadb" not in url:
        return
    try:
        from sqlalchemy import text
        from app.database import engine
        async with engine.begin() as conn:
            # 1. voice_extensions 扩展
            result = await conn.execute(
                text(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'voice_extensions'"
                )
            )
            existing_cols = {row[0] for row in result.all()}
            
            if "agent_state" not in existing_cols:
                await conn.execute(text(
                    "ALTER TABLE `voice_extensions` "
                    "ADD COLUMN `agent_state` VARCHAR(20) NOT NULL DEFAULT 'offline' COMMENT '坐席实时状态', "
                    "ADD COLUMN `signed_in_at` DATETIME NULL COMMENT '最近一次签入时间', "
                    "ADD COLUMN `last_state_change` DATETIME NULL COMMENT '上次状态变更时间', "
                    "ADD COLUMN `current_call_id` VARCHAR(128) NULL COMMENT '当前正在处理的 call_id'"
                ))
                _schema_logger.info("已自动补齐 voice_extensions OKCC 坐席状态字段")

            # 2. voice_outbound_campaigns 扩展
            result_c = await conn.execute(
                text(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'voice_outbound_campaigns'"
                )
            )
            existing_cols_c = {row[0] for row in result_c.all()}
            
            if "dial_mode" not in existing_cols_c:
                await conn.execute(text(
                    "ALTER TABLE `voice_outbound_campaigns` "
                    "ADD COLUMN `dial_mode` VARCHAR(16) NOT NULL DEFAULT 'progressive' COMMENT '外呼模式', "
                    "ADD COLUMN `max_retry` INT DEFAULT 3 COMMENT '最大重试次数', "
                    "ADD COLUMN `retry_interval_minutes` INT DEFAULT 30 COMMENT '重试间隔(分钟)'"
                ))
                _schema_logger.info("已自动补齐 voice_outbound_campaigns OKCC 外呼模式字段")

            if "ai_script_template_id" not in existing_cols_c:
                await conn.execute(text(
                    "ALTER TABLE `voice_outbound_campaigns` "
                    "ADD COLUMN `ai_script_template_id` INT NULL COMMENT '关联话术模板'"
                ))
                _schema_logger.info("已自动补齐 voice_outbound_campaigns 话术模板关联字段")

            # 3. ai_script_templates 表创建
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS `ai_script_templates` ("
                "  `id` INT AUTO_INCREMENT PRIMARY KEY,"
                "  `account_id` INT UNSIGNED NULL,"
                "  `name` VARCHAR(128) NOT NULL,"
                "  `category` VARCHAR(64) NULL,"
                "  `prompt_body` TEXT NOT NULL,"
                "  `tts_voice_id` VARCHAR(64) NULL,"
                "  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,"
                "  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 话术模板'"
            ))
                
    except Exception as e:
        _schema_logger.warning("自动补齐 OKCC 业务字段失败: %s", e)


async def ensure_voice_inbound_tables():
    """自动化创建 Phase G 呼入相关表: DID, Queue, IVR"""
    url = (settings.DATABASE_URL or "").lower()
    if "mysql" not in url and "mariadb" not in url:
        return
    try:
        async with engine.begin() as conn:
            # 1. voice_dids
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS `voice_dids` ("
                "  `id` INT AUTO_INCREMENT PRIMARY KEY,"
                "  `voice_account_id` INT NOT NULL,"
                "  `did_number` VARCHAR(50) NOT NULL UNIQUE,"
                "  `provider` VARCHAR(50) NULL,"
                "  `route_type` VARCHAR(20) NOT NULL DEFAULT 'ivr',"
                "  `route_target` VARCHAR(50) NOT NULL,"
                "  `status` VARCHAR(20) DEFAULT 'active',"
                "  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,"
                "  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
                "  INDEX `idx_voice_account_id` (`voice_account_id`)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
            ))
            # 2. voice_ivrs
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS `voice_ivrs` ("
                "  `id` INT AUTO_INCREMENT PRIMARY KEY,"
                "  `voice_account_id` INT NOT NULL,"
                "  `name` VARCHAR(100) NOT NULL,"
                "  `welcome_prompt` TEXT NULL,"
                "  `key_routings` TEXT NULL,"
                "  `timeout_action` VARCHAR(50) NULL,"
                "  `timeout_target` VARCHAR(50) NULL,"
                "  `status` VARCHAR(20) DEFAULT 'active',"
                "  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,"
                "  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
                "  INDEX `idx_voice_account_id` (`voice_account_id`)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
            ))
            # 3. voice_queues
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS `voice_queues` ("
                "  `id` INT AUTO_INCREMENT PRIMARY KEY,"
                "  `voice_account_id` INT NOT NULL,"
                "  `name` VARCHAR(100) NOT NULL,"
                "  `strategy` VARCHAR(20) DEFAULT 'longest_idle',"
                "  `agents` TEXT NULL,"
                "  `moh_prompt` TEXT NULL,"
                "  `max_wait_time` INT DEFAULT 300,"
                "  `status` VARCHAR(20) DEFAULT 'active',"
                "  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,"
                "  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
                "  INDEX `idx_voice_account_id` (`voice_account_id`)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
            ))
            _schema_logger.info("✅ 已自动创建 Phase G 呼入相关表")
    except Exception as e:
        _schema_logger.warning("⚠️ 创建 Phase G 呼入相关表失败: %s", e)


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()

