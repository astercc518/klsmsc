"""
软件授权(License)管理路由。

- GET  /admin/license/status       后台:当前授权状态(admin)
- GET  /admin/license/fingerprint  后台:本机指纹(admin,申请/续期用)
- POST /admin/license/upload       上传 .lic(super_admin),验签通过才落库,即时生效
- GET  /license/brand              公开:有效 OEM 品牌(logo/名称),供前端白标
- PUT  /admin/license/brand        OEM 白标:后台改 logo/名称(super_admin,仅 edition=oem)
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth import get_current_admin
from app.modules.common.admin_user import AdminUser
from app.modules.common.system_config import SystemConfig
from app.core import license as lic
from app.services.operation_log import log_operation

router = APIRouter()

BRAND_NAME_KEY = "brand.name"
BRAND_LOGO_KEY = "brand.logo"
_MAX_LOGO_LEN = 512 * 1024  # data URL 上限 ~512KB


async def _upsert_config(db: AsyncSession, key: str, value: str, *, category: str,
                         admin_id: int = None, description: str = "") -> None:
    """system_config 直接 upsert(ConfigService.set 仅能更新已存在键)。"""
    res = await db.execute(select(SystemConfig).where(SystemConfig.config_key == key))
    cfg = res.scalar_one_or_none()
    if cfg is None:
        db.add(SystemConfig(
            config_key=key, config_value=value, config_type='string',
            category=category, description=description, is_public=False,
            updated_by=admin_id,
        ))
    else:
        cfg.config_value = value
        cfg.updated_by = admin_id
    await db.flush()


@router.get("/admin/license/status")
async def license_status(admin: AdminUser = Depends(get_current_admin),
                         db: AsyncSession = Depends(get_db)):
    """当前授权状态(任意管理员可看,用于横幅与管理页)。"""
    st = await lic.get_license_status(db, use_cache=False)
    return {"success": True, "license": st}


@router.get("/admin/license/fingerprint")
async def license_fingerprint(admin: AdminUser = Depends(get_current_admin)):
    """本机指纹 + 来源(申请/续期授权时提供给厂商)。"""
    return {
        "success": True,
        "fingerprint": lic.compute_fingerprint(),
        "machine_id_file": lic._machine_id_path(),
    }


@router.post("/admin/license/upload")
async def license_upload(blob: str = Body(..., embed=True),
                         admin: AdminUser = Depends(get_current_admin),
                         db: AsyncSession = Depends(get_db)):
    """上传 .lic(仅 super_admin)。验签 + 指纹校验通过才落库;损坏/换机/过期一律拒绝保存。"""
    if admin.role != 'super_admin':
        raise HTTPException(status_code=403, detail="仅超级管理员可上传授权")

    blob = (blob or "").strip()
    # 先验证再保存——避免存入一张本机用不了的证
    st = lic.verify_blob(blob)
    if st["state"] in (lic.STATE_INVALID, lic.STATE_MISSING):
        raise HTTPException(status_code=400, detail=f"授权无效:{st['message']}")
    if st["state"] == lic.STATE_WRONG_MACHINE:
        raise HTTPException(status_code=400,
                            detail=f"{st['message']};本机指纹 {lic.compute_fingerprint()}")
    # expired/grace/valid 允许保存(过期证也存,以便前端显示过期态;但不可发送)

    await _upsert_config(db, lic.CONFIG_KEY_LICENSE, blob, category="security",
                         admin_id=admin.id, description="软件授权 .lic")
    await log_operation(db, admin_id=admin.id, admin_name=admin.username,
                        module="security", action="update", target_type="license",
                        target_id=st.get("edition") or "license",
                        title=f"上传软件授权 edition={st.get('edition')} customer={st.get('customer')}")
    await db.commit()
    lic.invalidate_cache()

    st2 = await lic.get_license_status(db, use_cache=False)
    return {"success": True, "message": "授权已安装", "license": st2}


@router.get("/license/brand")
async def public_brand(db: AsyncSession = Depends(get_db)):
    """
    公开:返回有效 OEM 品牌(供登录页/客户端白标)。
    仅当 edition=oem 且授权可用时生效;否则返回 null(前端用默认考拉品牌)。
    """
    st = await lic.get_license_status(db)
    if st.get("edition") != "oem" or not st.get("valid_for_send"):
        return {"success": True, "brand": None}

    res = await db.execute(select(SystemConfig).where(
        SystemConfig.config_key.in_([BRAND_NAME_KEY, BRAND_LOGO_KEY])
    ))
    kv = {c.config_key: c.config_value for c in res.scalars().all()}
    name = kv.get(BRAND_NAME_KEY)
    logo = kv.get(BRAND_LOGO_KEY)
    # 后台未设则回退 license 内嵌的 brand
    payload_brand = st.get("brand") or {}
    name = name or payload_brand.get("name")
    logo = logo or payload_brand.get("logo")
    if not name and not logo:
        return {"success": True, "brand": None}
    return {"success": True, "brand": {"name": name, "logo": logo}}


@router.put("/admin/license/brand")
async def set_brand(name: str = Body(None, embed=True),
                    logo: str = Body(None, embed=True),
                    admin: AdminUser = Depends(get_current_admin),
                    db: AsyncSession = Depends(get_db)):
    """OEM 白标:改 logo/名称(仅 super_admin,且授权 edition=oem)。"""
    if admin.role != 'super_admin':
        raise HTTPException(status_code=403, detail="仅超级管理员可修改品牌")
    st = await lic.get_license_status(db, use_cache=False)
    if st.get("edition") != "oem":
        raise HTTPException(status_code=403, detail="当前授权非 OEM 白标版,不支持自定义品牌")
    if logo and len(logo) > _MAX_LOGO_LEN:
        raise HTTPException(status_code=400, detail="logo 过大(上限约 512KB),请压缩或用 URL")

    if name is not None:
        await _upsert_config(db, BRAND_NAME_KEY, name, category="general", admin_id=admin.id,
                             description="OEM 品牌名称")
    if logo is not None:
        await _upsert_config(db, BRAND_LOGO_KEY, logo, category="general", admin_id=admin.id,
                             description="OEM 品牌 logo")
    await log_operation(db, admin_id=admin.id, admin_name=admin.username,
                        module="config", action="update", target_type="brand",
                        target_id="brand", title="修改 OEM 品牌")
    await db.commit()
    return {"success": True, "message": "品牌已更新"}
