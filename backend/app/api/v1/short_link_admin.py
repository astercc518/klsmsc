"""
短链相关 API：域名管理（admin）+ 客户域名下拉 + 批次点击统计 + 提取已点击号码

路由分布：
- /api/v1/admin/short-link-domains*  — admin CRUD
- /api/v1/short-link-domains          — 客户/admin 共用，仅返回 active 列表
- /api/v1/sms/batches/{id}/click-stats         — 批次点击概览
- /api/v1/sms/batches/{id}/clicked-phones      — 已点击号码列表（JSON 预览）
- /api/v1/sms/batches/{id}/clicked-phones.csv  — CSV 下载
"""
import csv
import io
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import get_current_admin
from app.core.auth import AuthService
from app.database import get_db
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser
from app.modules.sms.short_link_domain import ShortLinkDomain
from app.utils.logger import get_logger

logger = get_logger(__name__)
from app.modules.sms.short_link_log import ShortLinkLog
from app.modules.sms.sms_log import SMSLog


# =============================================================================
# Pydantic
# =============================================================================

class DomainCreate(BaseModel):
    domain: str = Field(..., max_length=255)
    base_path: str = Field("/s", max_length=64)
    scheme: str = Field("https", max_length=8)
    omit_scheme: bool = False
    remark: Optional[str] = Field(None, max_length=255)
    status: str = Field("active")
    sort_order: int = 0


class DomainUpdate(BaseModel):
    domain: Optional[str] = Field(None, max_length=255)
    base_path: Optional[str] = Field(None, max_length=64)
    scheme: Optional[str] = Field(None, max_length=8)
    omit_scheme: Optional[bool] = None
    remark: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = None
    sort_order: Optional[int] = None


class DomainOut(BaseModel):
    id: int
    domain: str
    base_path: str
    scheme: str
    omit_scheme: bool
    remark: Optional[str]
    status: str
    sort_order: int
    base_url: str

    @classmethod
    def from_orm_obj(cls, d: ShortLinkDomain) -> "DomainOut":
        return cls(
            id=d.id,
            domain=d.domain,
            base_path=d.base_path,
            scheme=d.scheme,
            omit_scheme=bool(d.omit_scheme),
            remark=d.remark,
            status=d.status,
            sort_order=d.sort_order,
            base_url=d.base_url(),
        )


# =============================================================================
# Admin: 域名 CRUD（super_admin 限定）
# =============================================================================

admin_router = APIRouter(prefix="/admin/short-link-domains", tags=["短链域名管理"])


def _require_super_admin(admin: AdminUser):
    if (admin.role or "") not in ("super_admin",):
        raise HTTPException(status_code=403, detail="仅 super_admin 可操作")


@admin_router.get("")
async def list_domains(
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    with_stats: bool = False,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """
    列表查询；with_stats=true 时附带 per-domain 统计：
        link_count   该域名累计生成多少条短链
        total_clicks 该域名累计被点击多少次
        last_used_at 最近一次生成短链的时间
    历史 NULL domain_id 的记录不计入任何域名（属于"未关联"）。
    """
    stmt = select(ShortLinkDomain)
    conds = []
    if keyword:
        kw = f"%{keyword}%"
        conds.append(ShortLinkDomain.domain.like(kw))
    if status:
        conds.append(ShortLinkDomain.status == status)
    if conds:
        stmt = stmt.where(and_(*conds))
    stmt = stmt.order_by(ShortLinkDomain.sort_order.desc(), ShortLinkDomain.id.desc())
    rows = (await db.execute(stmt)).scalars().all()

    stats_map: dict = {}
    if with_stats and rows:
        # 一次性聚合，命中 (domain_id, created_at) 复合索引
        agg = (
            await db.execute(
                select(
                    ShortLinkLog.domain_id,
                    func.count().label("link_count"),
                    func.coalesce(func.sum(ShortLinkLog.click_count), 0).label("total_clicks"),
                    func.max(ShortLinkLog.created_at).label("last_used_at"),
                )
                .where(ShortLinkLog.domain_id.in_([r.id for r in rows]))
                .group_by(ShortLinkLog.domain_id)
            )
        ).all()
        for row in agg:
            stats_map[row.domain_id] = {
                "link_count": int(row.link_count or 0),
                "total_clicks": int(row.total_clicks or 0),
                "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
            }

    out = []
    for r in rows:
        item = DomainOut.from_orm_obj(r).model_dump()
        if with_stats:
            s = stats_map.get(r.id, {"link_count": 0, "total_clicks": 0, "last_used_at": None})
            item.update(s)
        out.append(item)
    return {"success": True, "data": out}


@admin_router.post("")
async def create_domain(
    payload: DomainCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    _require_super_admin(admin)
    domain = (payload.domain or "").strip().lower()
    if not domain or "/" in domain:
        raise HTTPException(status_code=400, detail="域名不合法")

    exists = (
        await db.execute(select(ShortLinkDomain.id).where(ShortLinkDomain.domain == domain))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="域名已存在")

    row = ShortLinkDomain(
        domain=domain,
        # base_path 允许显式空串（即 "无前缀，最省字符"）
        base_path=(payload.base_path if payload.base_path is not None else "/s").strip(),
        scheme=(payload.scheme or "https").strip().lower(),
        omit_scheme=bool(payload.omit_scheme),
        remark=payload.remark,
        status=payload.status if payload.status in ("active", "disabled") else "active",
        sort_order=payload.sort_order or 0,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"success": True, "data": DomainOut.from_orm_obj(row).model_dump()}


@admin_router.put("/{domain_id}")
async def update_domain(
    domain_id: int,
    payload: DomainUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    _require_super_admin(admin)
    row = (
        await db.execute(select(ShortLinkDomain).where(ShortLinkDomain.id == domain_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="域名不存在")

    if payload.domain is not None:
        new_domain = payload.domain.strip().lower()
        if not new_domain or "/" in new_domain:
            raise HTTPException(status_code=400, detail="域名不合法")
        if new_domain != row.domain:
            dup = (
                await db.execute(
                    select(ShortLinkDomain.id).where(ShortLinkDomain.domain == new_domain)
                )
            ).scalar_one_or_none()
            if dup:
                raise HTTPException(status_code=400, detail="域名已存在")
            row.domain = new_domain
    if payload.base_path is not None:
        # 允许显式空串
        row.base_path = payload.base_path.strip()
    if payload.scheme is not None:
        row.scheme = payload.scheme.strip().lower() or "https"
    if payload.omit_scheme is not None:
        row.omit_scheme = bool(payload.omit_scheme)
    if payload.remark is not None:
        row.remark = payload.remark
    if payload.status is not None and payload.status in ("active", "disabled"):
        row.status = payload.status
    if payload.sort_order is not None:
        row.sort_order = int(payload.sort_order)

    await db.commit()
    await db.refresh(row)
    return {"success": True, "data": DomainOut.from_orm_obj(row).model_dump()}


@admin_router.delete("/{domain_id}")
async def delete_domain(
    domain_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    _require_super_admin(admin)
    row = (
        await db.execute(select(ShortLinkDomain).where(ShortLinkDomain.id == domain_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="域名不存在")
    await db.delete(row)
    await db.commit()
    return {"success": True}


# =============================================================================
# 短链 SSL 证书：上传 + 查询当前 + 一键 reload nginx
# =============================================================================

import os
import tempfile
from pathlib import Path
import httpx
from pydantic import BaseModel as _BaseModel

from app.utils.ssl_cert import (
    CertValidationError,
    validate_cert_and_key,
    parse_cert,
    cert_summary,
)

# 容器内挂载点（与 docker-compose.yml 一致）
_CERT_DIR = Path("/etc/nginx/certs")
_CERT_PEM = _CERT_DIR / "short.pem"        # 旧版多 SAN 大证书（兼容路径）
_CERT_KEY = _CERT_DIR / "short.key"
_PER_DOMAIN_CERT_DIR = _CERT_DIR / "domains"             # 一域名一证书的存放目录
_NGINX_SNIPPET_DIR = Path("/etc/nginx/short_link_snippets")
_FRONTEND_CONTAINER = "smsc-frontend"


def _per_domain_pem_path(domain_id: int) -> Path:
    return _PER_DOMAIN_CERT_DIR / f"{int(domain_id)}.pem"


def _per_domain_key_path(domain_id: int) -> Path:
    return _PER_DOMAIN_CERT_DIR / f"{int(domain_id)}.key"


def _per_domain_snippet_path(domain_id: int) -> Path:
    return _NGINX_SNIPPET_DIR / f"{int(domain_id)}.conf"


def _render_nginx_snippet(domain_id: int, domain: str) -> str:
    """
    为每个上传了专属证书的域名生成 nginx server 块片段。
    精确 server_name 优先级高于 catch-all 的 ~.+ 正则，保证流量打到这里。
    """
    return f"""# 自动生成 — 短链域名 {domain} 专属证书 server 块（domain_id={domain_id}）
server {{
    listen 80;
    listen 443 ssl http2;
    server_name {domain} *.{domain};

    ssl_certificate     /etc/nginx/certs/domains/{domain_id}.pem;
    ssl_certificate_key /etc/nginx/certs/domains/{domain_id}.key;

    # CF 真实客户端 IP
    set_real_ip_from 0.0.0.0/0;
    real_ip_header CF-Connecting-IP;

    # 根路径：跳官网，避免短链域名被当主站访问
    location = / {{
        return 302 https://www.kaolach.com/;
    }}

    # 健康检查
    location = /health {{
        access_log off;
        return 200 "ok\\n";
    }}

    # 路径 A（兼容传统）：{domain}/s/{{token}}
    location ^~ /s/ {{
        proxy_pass http://api:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_read_timeout 30s;
        proxy_connect_timeout 10s;
    }}

    # 路径 B（裸 token，省字符）：{domain}/{{token}}
    location ~ "^/([A-Za-z0-9]{{6,8}})$" {{
        rewrite ^/(.+)$ /s/$1 break;
        proxy_pass http://api:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_read_timeout 30s;
        proxy_connect_timeout 10s;
    }}

    # 其他路径返回 404，避免被扫描收录
    location / {{ return 404; }}
}}
"""


class CertUploadPayload(_BaseModel):
    cert_pem: str
    key_pem: str


def _atomic_write(path: Path, content: str, mode: int) -> None:
    """先写入临时文件，rename 替换；避免 nginx 在 reload 瞬间读到半截内容。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".upload_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


async def _reload_nginx() -> Dict:
    """
    通过 docker-socket-proxy 给 frontend 容器发 SIGHUP，nginx 平滑 reload。

    带 3 次重试 + 指数退避，避免连续上传多个证书时 docker-proxy 偶发抖动导致 UI 误报失败。
    nginx 收到 SIGHUP 是幂等的（重复发送只是再触发一次 graceful reload，无副作用）。
    """
    import asyncio as _aio
    proxy_url = os.getenv("DOCKER_PROXY_URL", "http://docker-proxy:2375")
    url = f"{proxy_url}/containers/{_FRONTEND_CONTAINER}/kill?signal=HUP"
    last_err: str = ""
    last_status: int = 0
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url)
            if resp.status_code in (204, 200):
                return {"success": True, "method": "SIGHUP", "attempts": attempt + 1}
            last_status = resp.status_code
            last_err = (resp.text or "")[:300]
        except Exception as e:
            last_err = str(e)
        if attempt < 2:
            await _aio.sleep(0.5 * (attempt + 1))  # 0.5s, 1.0s
    return {
        "success": False,
        "method": "SIGHUP",
        "status_code": last_status,
        "error": last_err,
        "attempts": 3,
    }


@admin_router.get("/cert/info")
async def get_cert_info(admin: AdminUser = Depends(get_current_admin)):
    """
    返回当前 short.pem 信息（SAN、有效期等）；
    若证书文件不存在或解析失败，返回 configured=false 告知前端"未配置"。
    """
    if not _CERT_PEM.exists():
        return {"success": True, "data": {"configured": False, "reason": "证书文件不存在"}}
    try:
        pem_text = _CERT_PEM.read_text(encoding="utf-8")
        cert = parse_cert(pem_text)
        summary = cert_summary(cert)
        return {
            "success": True,
            "data": {
                "configured": True,
                "path": str(_CERT_PEM),
                "key_path": str(_CERT_KEY),
                **summary,
            },
        }
    except Exception as e:
        return {
            "success": True,
            "data": {"configured": False, "reason": f"证书解析失败: {e}"},
        }


@admin_router.post("/cert/upload")
async def upload_cert(
    payload: CertUploadPayload,
    admin: AdminUser = Depends(get_current_admin),
):
    """
    上传 PEM + KEY，原子写入磁盘并通过 docker-proxy SIGHUP 平滑 reload nginx。
    任一校验失败 → 不写文件 / 不 reload。
    """
    _require_super_admin(admin)

    cert_pem = (payload.cert_pem or "").strip()
    key_pem = (payload.key_pem or "").strip()
    if not cert_pem or not key_pem:
        raise HTTPException(status_code=400, detail="证书或私钥为空")
    # 末尾确保有换行（部分 nginx 版本对最后一行无换行的 PEM 容忍度低）
    if not cert_pem.endswith("\n"):
        cert_pem += "\n"
    if not key_pem.endswith("\n"):
        key_pem += "\n"

    try:
        cert, summary = validate_cert_and_key(cert_pem, key_pem)
    except CertValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 写文件（原子）
    try:
        _atomic_write(_CERT_PEM, cert_pem, mode=0o644)
        _atomic_write(_CERT_KEY, key_pem, mode=0o600)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入证书失败: {e}")

    # 异步 reload nginx；reload 失败不抹掉证书（可重试），但要返回给前端
    reload_result = await _reload_nginx()

    return {
        "success": True,
        "data": {
            "cert": summary,
            "reload": reload_result,
        },
    }


@admin_router.post("/cert/reload")
async def manual_reload_nginx(admin: AdminUser = Depends(get_current_admin)):
    """手动触发 nginx reload，用于上传证书后 reload 失败重试。"""
    _require_super_admin(admin)
    return {"success": True, "data": await _reload_nginx()}


# =============================================================================
# 每域名独立证书 (一域名一证书)
# =============================================================================

@admin_router.get("/{domain_id}/cert/info")
async def get_domain_cert_info(
    domain_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """
    返回该域名专属证书的状态。
    若专属证书不存在则 configured=false；前端可显示「未配置 / 上传证书」按钮。
    """
    pem_path = _per_domain_pem_path(domain_id)
    if not pem_path.exists():
        return {"success": True, "data": {"configured": False, "domain_id": domain_id, "reason": "未上传专属证书"}}
    try:
        cert = parse_cert(pem_path.read_text(encoding="utf-8"))
        summary = cert_summary(cert)
        return {
            "success": True,
            "data": {
                "configured": True,
                "domain_id": domain_id,
                "path": str(pem_path),
                **summary,
            },
        }
    except Exception as e:
        return {"success": True, "data": {"configured": False, "domain_id": domain_id, "reason": f"解析失败: {e}"}}


@admin_router.post("/{domain_id}/cert/upload")
async def upload_domain_cert(
    domain_id: int,
    payload: CertUploadPayload,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """
    上传该域名的专属 PEM/KEY，原子写盘 → 生成 nginx snippet → SIGHUP reload。

    校验：
        - PEM/KEY 格式
        - KEY 与 cert 公钥指纹一致
        - 证书未过期
        - 证书 SAN **必须**包含该 domain（否则 TLS 握手对该域名会失败）
    """
    _require_super_admin(admin)

    row = (
        await db.execute(select(ShortLinkDomain).where(ShortLinkDomain.id == domain_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="域名不存在")

    cert_pem = (payload.cert_pem or "").strip()
    key_pem = (payload.key_pem or "").strip()
    if not cert_pem or not key_pem:
        raise HTTPException(status_code=400, detail="证书或私钥为空")
    if not cert_pem.endswith("\n"): cert_pem += "\n"
    if not key_pem.endswith("\n"): key_pem += "\n"

    try:
        cert, summary = validate_cert_and_key(cert_pem, key_pem)
    except CertValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 强校验：SAN 必须包含本域名（裸名或通配）
    sans_lower = [s.lower() for s in summary.get("sans", [])]
    target = row.domain.lower()
    san_match = (
        target in sans_lower
        or f"*.{target}" in sans_lower
        or any(s.startswith("*.") and target.endswith(s[1:]) for s in sans_lower)
    )
    if not san_match:
        raise HTTPException(
            status_code=400,
            detail=f"证书 SAN 不包含 {row.domain}；当前 SAN: {summary.get('sans')}",
        )

    pem_path = _per_domain_pem_path(domain_id)
    key_path = _per_domain_key_path(domain_id)
    snippet_path = _per_domain_snippet_path(domain_id)
    try:
        _atomic_write(pem_path, cert_pem, mode=0o644)
        _atomic_write(key_path, key_pem, mode=0o600)
        _atomic_write(snippet_path, _render_nginx_snippet(domain_id, row.domain), mode=0o644)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入证书或 nginx 片段失败: {e}")

    reload_result = await _reload_nginx()
    return {
        "success": True,
        "data": {
            "domain": row.domain,
            "cert": summary,
            "reload": reload_result,
        },
    }


@admin_router.delete("/{domain_id}/cert")
async def delete_domain_cert(
    domain_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """删除该域名专属证书 + nginx snippet，并 reload。"""
    _require_super_admin(admin)
    pem_path = _per_domain_pem_path(domain_id)
    key_path = _per_domain_key_path(domain_id)
    snippet_path = _per_domain_snippet_path(domain_id)
    removed = []
    for p in (pem_path, key_path, snippet_path):
        try:
            if p.exists():
                p.unlink()
                removed.append(p.name)
        except Exception as e:
            logger.warning(f"删除文件失败 {p}: {e}")
    reload_result = await _reload_nginx() if removed else {"success": True, "method": "noop"}
    return {"success": True, "data": {"removed": removed, "reload": reload_result}}


# =============================================================================
# 短链域名 → 已点击号码导出（按国家筛选）
#
# 与 /sms/batches/{batch_id}/clicked-phones.csv 同款数据源（short_link_logs ⋈ sms_logs），
# 区别在于聚合维度：域名级而非批次级。运营场景：选某个营销短链域名 → 拉某国家点过链
# 的号码做二次触达。
# =============================================================================


@admin_router.get("/{domain_id}/clicked-countries")
async def list_clicked_countries(
    domain_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """该域名下出现过的国家列表（仅含 click_count>=1 的号码所属国家），供下载弹窗下拉。"""
    rows = (
        await db.execute(
            select(SMSLog.country_code, func.count(func.distinct(SMSLog.phone_number)).label("cnt"))
            .select_from(ShortLinkLog)
            .join(SMSLog, SMSLog.id == ShortLinkLog.sms_log_id)
            .where(ShortLinkLog.domain_id == domain_id, ShortLinkLog.click_count >= 1)
            .group_by(SMSLog.country_code)
            .order_by(func.count(func.distinct(SMSLog.phone_number)).desc())
        )
    ).all()
    items = [{"country_code": (cc or "").strip() or "UNKNOWN", "count": int(c or 0)} for cc, c in rows]
    return {"success": True, "items": items}


@admin_router.get("/{domain_id}/clicked-phones")
async def download_domain_clicked_phones(
    domain_id: int,
    fmt: str = Query("txt", regex="^(txt|csv)$"),
    country_code: Optional[str] = Query(None, max_length=10),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """下载该域名下「真实点击过短链」的号码。

    - fmt=txt：一行一个号码，去重 + 剥前导 `+`
    - fmt=csv：phone_number,country_code,click_count,last_click_at,original_url
    - country_code 可选，传则按 sms_logs.country_code 精确匹配（ISO2，大写）
    """
    domain = (await db.execute(
        select(ShortLinkDomain).where(ShortLinkDomain.id == domain_id)
    )).scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=404, detail="domain_not_found")

    cc_norm = (country_code or "").strip().upper() or None

    # 公共 WHERE
    base_where = [ShortLinkLog.domain_id == domain_id, ShortLinkLog.click_count >= 1]
    if cc_norm:
        base_where.append(SMSLog.country_code == cc_norm)

    if fmt == "txt":
        # 仅取去重号码（DISTINCT phone_number），避免一个号码多次点击重复出现
        rows_iter = await db.stream(
            select(SMSLog.phone_number)
            .select_from(ShortLinkLog)
            .join(SMSLog, SMSLog.id == ShortLinkLog.sms_log_id)
            .where(*base_where)
            .distinct()
        )

        async def gen_txt():
            seen = 0
            async for (phone,) in rows_iter:
                p = (phone or "").lstrip("+")
                if not p:
                    continue
                seen += 1
                yield p + "\n"
            if seen == 0:
                yield ""  # 空 body；前端按 blob.size==0 提示无数据

        suffix = cc_norm or "all"
        fname = f"clicked_phones_{domain.domain}_{suffix}_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
        resp_factory = StreamingResponse(
            gen_txt(),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    else:  # csv
        rows_iter = await db.stream(
            select(
                SMSLog.phone_number,
                SMSLog.country_code,
                ShortLinkLog.click_count,
                ShortLinkLog.last_click_at,
                ShortLinkLog.original_url,
            )
            .select_from(ShortLinkLog)
            .join(SMSLog, SMSLog.id == ShortLinkLog.sms_log_id)
            .where(*base_where)
            .order_by(ShortLinkLog.last_click_at.desc())
        )

        async def gen_csv():
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["phone_number", "country_code", "click_count", "last_click_at", "original_url"])
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

            async for r in rows_iter:
                ts = r.last_click_at.isoformat() if r.last_click_at else ""
                w.writerow([r.phone_number, r.country_code or "", int(r.click_count or 0), ts, r.original_url or ""])
                data = buf.getvalue()
                if data:
                    yield data
                    buf.seek(0); buf.truncate(0)

        suffix = cc_norm or "all"
        fname = f"clicked_phones_{domain.domain}_{suffix}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
        resp_factory = StreamingResponse(
            gen_csv(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )

    # 审计日志（fire-and-forget 形式，不阻塞流式响应）
    try:
        from app.services.operation_log import log_operation
        await log_operation(
            db, admin_id=admin.id, admin_name=admin.username,
            module="sms", action="short_link_export_clicked_phones",
            target_type="short_link_domain", target_id=str(domain_id),
            title=f"下载短链域名 {domain.domain} 点击号码（{cc_norm or 'all'}, {fmt}）",
            detail={"domain_id": domain_id, "domain": domain.domain, "country_code": cc_norm, "fmt": fmt},
        )
    except Exception as e:
        logger.warning(f"短链域名点击号码下载审计日志写入失败 domain_id={domain_id}: {e}")

    return resp_factory


# =============================================================================
# 客户/管理员共用：仅返回 active 域名（Send 页下拉）
# =============================================================================

public_router = APIRouter(prefix="/short-link-domains", tags=["短链域名（公开列表）"])


@public_router.get("")
async def list_active_domains(db: AsyncSession = Depends(get_db)):
    """供「短链转换」对话框下拉。无鉴权强制，但会自动通过现有路由保护。"""
    rows = (
        await db.execute(
            select(ShortLinkDomain)
            .where(ShortLinkDomain.status == "active")
            .order_by(ShortLinkDomain.sort_order.desc(), ShortLinkDomain.id.desc())
        )
    ).scalars().all()
    return {"success": True, "data": [DomainOut.from_orm_obj(r).model_dump() for r in rows]}


# =============================================================================
# 批次点击统计 + 提取已点击号码
# =============================================================================

stats_router = APIRouter(prefix="/sms/batches", tags=["短信批次-短链统计"])


@stats_router.get("/{batch_id}/click-stats")
async def batch_click_stats(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
):
    """批次点击概览：总短链数、被点击数、总点击次数。

    公开（无鉴权）— 由前端在租户上下文展示，安全性由路径不可枚举（batch_id 自增但访问需要登录态）保证；
    若需严格租户隔离，可在此处补 Depends 检查（已在 v2 计划中）。
    """
    total_rows, clicked_rows, total_clicks = (
        await db.execute(
            select(
                func.count(ShortLinkLog.id),
                func.sum(func.if_(ShortLinkLog.click_count > 0, 1, 0)),
                func.coalesce(func.sum(ShortLinkLog.click_count), 0),
            )
            .select_from(ShortLinkLog)
            .join(SMSLog, SMSLog.id == ShortLinkLog.sms_log_id)
            .where(SMSLog.batch_id == batch_id)
        )
    ).one()

    return {
        "success": True,
        "data": {
            "batch_id": batch_id,
            "total_links": int(total_rows or 0),
            "clicked_links": int(clicked_rows or 0),
            "total_clicks": int(total_clicks or 0),
        },
    }


@stats_router.get("/{batch_id}/clicked-phones")
async def list_clicked_phones(
    batch_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """JSON 预览：分页返回点击过短链的号码。"""
    base = (
        select(
            SMSLog.phone_number.label("phone_number"),
            ShortLinkLog.click_count.label("click_count"),
            ShortLinkLog.last_click_at.label("last_click_at"),
            ShortLinkLog.original_url.label("original_url"),
            ShortLinkLog.token.label("token"),
        )
        .select_from(ShortLinkLog)
        .join(SMSLog, SMSLog.id == ShortLinkLog.sms_log_id)
        .where(SMSLog.batch_id == batch_id, ShortLinkLog.click_count > 0)
        .order_by(ShortLinkLog.last_click_at.desc())
    )

    total = (
        await db.execute(
            select(func.count())
            .select_from(ShortLinkLog)
            .join(SMSLog, SMSLog.id == ShortLinkLog.sms_log_id)
            .where(SMSLog.batch_id == batch_id, ShortLinkLog.click_count > 0)
        )
    ).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(base.offset(offset).limit(page_size))).all()

    return {
        "success": True,
        "data": {
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "phone_number": r.phone_number,
                    "click_count": int(r.click_count or 0),
                    "last_click_at": r.last_click_at.isoformat() if r.last_click_at else None,
                    "original_url": r.original_url,
                    "token": r.token,
                }
                for r in rows
            ],
        },
    }


@stats_router.get("/{batch_id}/clicked-phones.csv")
async def download_clicked_phones_csv(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
):
    """CSV 下载：流式遍历，避免大批次（百万级）一次性加载到内存。"""
    rows_iter = await db.stream(
        select(
            SMSLog.phone_number,
            ShortLinkLog.click_count,
            ShortLinkLog.last_click_at,
            ShortLinkLog.original_url,
        )
        .select_from(ShortLinkLog)
        .join(SMSLog, SMSLog.id == ShortLinkLog.sms_log_id)
        .where(SMSLog.batch_id == batch_id, ShortLinkLog.click_count > 0)
        .order_by(ShortLinkLog.last_click_at.desc())
    )

    async def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["phone_number", "click_count", "last_click_at", "original_url"])
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)

        async for r in rows_iter:
            ts = r.last_click_at.isoformat() if r.last_click_at else ""
            w.writerow([r.phone_number, int(r.click_count or 0), ts, r.original_url or ""])
            data = buf.getvalue()
            if data:
                yield data
                buf.seek(0); buf.truncate(0)

    fname = f"clicked_phones_batch_{batch_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        gen(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
