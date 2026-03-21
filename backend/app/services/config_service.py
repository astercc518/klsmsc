"""
系统配置服务 — 带 Redis 读缓存 + 变更审计日志
"""
from typing import Any, Dict, List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.common.system_config import SystemConfig
from app.modules.common.config_audit_log import ConfigAuditLog
from app.services.operation_log import log_operation
from app.utils.cache import get_cache_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)

_CACHE_PREFIX = "syscfg"
_CACHE_TTL = 600  # 10 分钟


class ConfigService:
    """系统配置读写服务（单例风格，通过 db session 传入）"""

    # ==================== 读取 ====================

    @staticmethod
    async def get(key: str, db: AsyncSession, default: Any = None) -> Any:
        """获取单个配置值（优先缓存）"""
        cache = await get_cache_manager()
        cache_key = f"{_CACHE_PREFIX}:{key}"

        cached = await cache.get(cache_key)
        if cached is not None:
            return cached

        result = await db.execute(
            select(SystemConfig).where(SystemConfig.config_key == key)
        )
        cfg = result.scalar_one_or_none()
        if cfg is None:
            return default

        value = _cast_value(cfg.config_value, cfg.config_type)
        await cache.set(cache_key, cfg.config_value, ttl=_CACHE_TTL)
        return value

    @staticmethod
    async def get_many(keys: List[str], db: AsyncSession) -> Dict[str, Any]:
        """批量获取配置值"""
        cache = await get_cache_manager()
        result_map: Dict[str, Any] = {}
        missing_keys: List[str] = []

        for k in keys:
            cached = await cache.get(f"{_CACHE_PREFIX}:{k}")
            if cached is not None:
                result_map[k] = cached
            else:
                missing_keys.append(k)

        if missing_keys:
            res = await db.execute(
                select(SystemConfig).where(SystemConfig.config_key.in_(missing_keys))
            )
            for cfg in res.scalars().all():
                val = _cast_value(cfg.config_value, cfg.config_type)
                result_map[cfg.config_key] = val
                await cache.set(f"{_CACHE_PREFIX}:{cfg.config_key}", cfg.config_value, ttl=_CACHE_TTL)

        return result_map

    @staticmethod
    async def get_by_category(category: str, db: AsyncSession) -> Dict[str, Any]:
        """按分类获取所有配置"""
        res = await db.execute(
            select(SystemConfig).where(SystemConfig.category == category)
        )
        return {
            cfg.config_key: _cast_value(cfg.config_value, cfg.config_type)
            for cfg in res.scalars().all()
        }

    @staticmethod
    async def get_all_grouped(db: AsyncSession) -> Dict[str, list]:
        """获取所有配置并按分类分组（管理后台用）"""
        from app.modules.common.admin_user import AdminUser

        res = await db.execute(
            select(SystemConfig).order_by(SystemConfig.category, SystemConfig.config_key)
        )
        all_cfgs = res.scalars().all()

        admin_ids = {c.updated_by for c in all_cfgs if c.updated_by}
        admin_map: Dict[int, str] = {}
        if admin_ids:
            admin_res = await db.execute(
                select(AdminUser.id, AdminUser.username).where(AdminUser.id.in_(admin_ids))
            )
            admin_map = {row.id: row.username for row in admin_res.all()}

        groups: Dict[str, list] = {}
        for cfg in all_cfgs:
            groups.setdefault(cfg.category or "general", []).append({
                "id": cfg.id,
                "config_key": cfg.config_key,
                "config_value": cfg.config_value,
                "config_type": cfg.config_type,
                "category": cfg.category or "general",
                "description": cfg.description,
                "is_public": cfg.is_public,
                "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
                "updated_by": cfg.updated_by,
                "updated_by_name": admin_map.get(cfg.updated_by, "") if cfg.updated_by else "",
            })
        return groups

    # ==================== 写入 ====================

    @staticmethod
    async def set(key: str, value: str, db: AsyncSession, *,
                  admin_id: Optional[int] = None,
                  admin_name: Optional[str] = None,
                  description: Optional[str] = None) -> bool:
        """设置单个配置值（写入 + 审计 + 失效缓存）"""
        res = await db.execute(
            select(SystemConfig).where(SystemConfig.config_key == key)
        )
        cfg = res.scalar_one_or_none()
        if cfg is None:
            return False

        old_value = cfg.config_value
        if old_value == value:
            return True

        cfg.config_value = value
        if description is not None:
            cfg.description = description
        if admin_id is not None:
            cfg.updated_by = admin_id

        db.add(ConfigAuditLog(
            config_key=key,
            action="update",
            old_value=old_value,
            new_value=value,
            admin_id=admin_id,
            admin_name=admin_name or "",
        ))

        await db.flush()
        await _invalidate_key(key)

        await log_operation(
            db, admin_id=admin_id, admin_name=admin_name,
            module="config", action="update", target_type="config", target_id=key,
            title=f"修改配置 {key}",
            detail={"old_value": _mask(old_value) if _is_sensitive_key(key) else old_value,
                    "new_value": _mask(value) if _is_sensitive_key(key) else value},
        )

        logger.info(f"配置变更: {key} = {_mask(old_value)} -> {_mask(value)} (by admin:{admin_id})")
        return True

    @staticmethod
    async def batch_update(updates: Dict[str, str], db: AsyncSession, *,
                           admin_id: Optional[int] = None,
                           admin_name: Optional[str] = None) -> int:
        """批量更新配置 + 类型校验 + 审计日志"""
        if not updates:
            return 0

        res = await db.execute(
            select(SystemConfig).where(SystemConfig.config_key.in_(updates.keys()))
        )
        configs = {c.config_key: c for c in res.scalars().all()}
        count = 0

        for key, new_val in updates.items():
            cfg = configs.get(key)
            if cfg is None:
                continue
            if cfg.config_value == new_val:
                continue

            _validate_value_strict(new_val, cfg.config_type, key)

            old_val = cfg.config_value
            cfg.config_value = new_val
            if admin_id is not None:
                cfg.updated_by = admin_id

            db.add(ConfigAuditLog(
                config_key=key,
                action="update",
                old_value=old_val,
                new_value=new_val,
                admin_id=admin_id,
                admin_name=admin_name or "",
            ))

            count += 1
            await _invalidate_key(key)
            logger.info(f"配置变更: {key} = {_mask(old_val)} -> {_mask(new_val)} (by admin:{admin_id})")

        if count:
            await db.flush()
            await log_operation(
                db, admin_id=admin_id, admin_name=admin_name,
                module="config", action="update", target_type="config",
                title=f"批量修改 {count} 项配置",
                detail={"keys": list(updates.keys()), "count": count},
            )
        return count

    @staticmethod
    async def create(key: str, value: str, db: AsyncSession, *,
                     config_type: str = "string",
                     category: str = "general",
                     description: Optional[str] = None,
                     is_public: bool = False,
                     admin_id: Optional[int] = None,
                     admin_name: Optional[str] = None) -> SystemConfig:
        """创建配置 + 审计"""
        cfg = SystemConfig(
            config_key=key,
            config_value=value,
            config_type=config_type,
            category=category,
            description=description,
            is_public=is_public,
            updated_by=admin_id,
        )
        db.add(cfg)

        db.add(ConfigAuditLog(
            config_key=key,
            action="create",
            old_value=None,
            new_value=value,
            admin_id=admin_id,
            admin_name=admin_name or "",
        ))

        await db.flush()
        await log_operation(
            db, admin_id=admin_id, admin_name=admin_name,
            module="config", action="create", target_type="config", target_id=key,
            title=f"创建配置 {key}",
        )
        logger.info(f"配置创建: {key} (by admin:{admin_id})")
        return cfg

    @staticmethod
    async def delete(key: str, db: AsyncSession, *,
                     admin_id: Optional[int] = None,
                     admin_name: Optional[str] = None) -> bool:
        """删除配置 + 审计 + 缓存失效"""
        res = await db.execute(
            select(SystemConfig).where(SystemConfig.config_key == key)
        )
        cfg = res.scalar_one_or_none()
        if cfg is None:
            return False

        db.add(ConfigAuditLog(
            config_key=key,
            action="delete",
            old_value=cfg.config_value,
            new_value=None,
            admin_id=admin_id,
            admin_name=admin_name or "",
        ))

        await db.delete(cfg)
        await db.flush()
        await _invalidate_key(key)

        await log_operation(
            db, admin_id=admin_id, admin_name=admin_name,
            module="config", action="delete", target_type="config", target_id=key,
            title=f"删除配置 {key}",
        )
        logger.info(f"配置删除: {key} (by admin:{admin_id})")
        return True

    # ==================== 审计查询 ====================

    @staticmethod
    async def get_audit_logs(db: AsyncSession, *,
                             config_key: Optional[str] = None,
                             limit: int = 50,
                             offset: int = 0) -> Dict[str, Any]:
        """查询变更审计日志"""
        query = select(ConfigAuditLog)
        if config_key:
            query = query.where(ConfigAuditLog.config_key == config_key)
        query = query.order_by(desc(ConfigAuditLog.created_at))

        from sqlalchemy import func as sa_func
        count_q = select(sa_func.count()).select_from(query.subquery())
        total = (await db.execute(count_q)).scalar() or 0

        rows = (await db.execute(query.offset(offset).limit(limit))).scalars().all()
        return {
            "total": total,
            "items": [
                {
                    "id": r.id,
                    "config_key": r.config_key,
                    "action": r.action,
                    "old_value": _mask(r.old_value) if _is_sensitive_key(r.config_key) else r.old_value,
                    "new_value": _mask(r.new_value) if _is_sensitive_key(r.config_key) else r.new_value,
                    "admin_id": r.admin_id,
                    "admin_name": r.admin_name,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        }

    # ==================== 导出 / 导入 ====================

    @staticmethod
    async def export_all(db: AsyncSession) -> List[Dict[str, Any]]:
        """导出所有配置（敏感字段脱敏）"""
        res = await db.execute(
            select(SystemConfig).order_by(SystemConfig.category, SystemConfig.config_key)
        )
        return [
            {
                "config_key": c.config_key,
                "config_value": c.config_value,
                "config_type": c.config_type,
                "category": c.category or "general",
                "description": c.description,
                "is_public": c.is_public,
            }
            for c in res.scalars().all()
        ]

    @staticmethod
    async def import_configs(items: List[Dict[str, Any]], db: AsyncSession, *,
                             admin_id: Optional[int] = None,
                             admin_name: Optional[str] = None,
                             overwrite: bool = False) -> Dict[str, int]:
        """导入配置，返回 created / updated / skipped 计数"""
        created = updated = skipped = 0
        for item in items:
            key = item.get("config_key")
            if not key:
                skipped += 1
                continue

            res = await db.execute(
                select(SystemConfig).where(SystemConfig.config_key == key)
            )
            existing = res.scalar_one_or_none()

            if existing:
                if not overwrite:
                    skipped += 1
                    continue
                old_val = existing.config_value
                new_val = item.get("config_value", "")
                if old_val == new_val:
                    skipped += 1
                    continue
                existing.config_value = new_val
                if item.get("description") is not None:
                    existing.description = item["description"]
                if admin_id:
                    existing.updated_by = admin_id
                db.add(ConfigAuditLog(
                    config_key=key, action="update",
                    old_value=old_val, new_value=new_val,
                    admin_id=admin_id, admin_name=admin_name or "",
                ))
                updated += 1
                await _invalidate_key(key)
            else:
                cfg = SystemConfig(
                    config_key=key,
                    config_value=item.get("config_value", ""),
                    config_type=item.get("config_type", "string"),
                    category=item.get("category", "general"),
                    description=item.get("description"),
                    is_public=item.get("is_public", False),
                    updated_by=admin_id,
                )
                db.add(cfg)
                db.add(ConfigAuditLog(
                    config_key=key, action="create",
                    old_value=None, new_value=item.get("config_value", ""),
                    admin_id=admin_id, admin_name=admin_name or "",
                ))
                created += 1

        await db.flush()
        return {"created": created, "updated": updated, "skipped": skipped}

    # ==================== 缓存管理 ====================

    @staticmethod
    async def invalidate_all():
        """清除所有系统配置缓存"""
        cache = await get_cache_manager()
        await cache.delete_pattern(f"{_CACHE_PREFIX}:*")


# ==================== 内部工具 ====================

async def _invalidate_key(key: str):
    cache = await get_cache_manager()
    await cache.delete(f"{_CACHE_PREFIX}:{key}")


def _cast_value(raw: Optional[str], config_type: str) -> Any:
    """将字符串值转换为对应 Python 类型"""
    if raw is None:
        return None
    if config_type == "number":
        try:
            return int(raw) if "." not in raw else float(raw)
        except (ValueError, TypeError):
            return raw
    if config_type == "boolean":
        return raw.lower() in ("true", "1", "yes")
    if config_type == "json":
        import json
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw
    return raw


def _validate_value_strict(value: str, config_type: str, key: str = ""):
    """批量更新时的类型校验（抛出 ValueError）"""
    if config_type == "number":
        try:
            float(value)
        except ValueError:
            raise ValueError(f"配置 '{key}' 的值 '{value}' 不是有效数字")
    elif config_type == "boolean":
        if value.lower() not in ("true", "false", "1", "0", "yes", "no"):
            raise ValueError(f"配置 '{key}' 的值 '{value}' 不是有效布尔值")
    elif config_type == "json":
        import json
        try:
            json.loads(value)
        except json.JSONDecodeError as e:
            raise ValueError(f"配置 '{key}' 的值不是有效 JSON: {e}")


def _is_sensitive_key(key: str) -> bool:
    return any(w in key for w in ("token", "password", "secret"))


def _mask(value: Optional[str]) -> str:
    """对敏感值脱敏"""
    if not value:
        return "(empty)"
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]
