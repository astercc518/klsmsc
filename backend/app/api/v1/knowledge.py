"""
业务知识库 API
- 管理员：上传、编辑、删除
- 员工：查阅、搜索
"""
import os
import uuid
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from typing import Optional, List
from pydantic import BaseModel, Field

from app.database import get_db
from app.api.v1.admin import get_current_admin
from app.modules.common.admin_user import AdminUser
from app.modules.common.knowledge import KnowledgeArticle, KnowledgeAttachment
from app.core.audit_dep import audited

router = APIRouter(prefix="/admin/knowledge", tags=["知识库"])

# 知识库文件存储目录（需在 docker-compose 中挂载可写卷）
KNOWLEDGE_DIR = Path("/app/data/knowledge")
ALLOWED_EXTENSIONS = {
    "doc": [".doc", ".docx", ".pdf", ".txt", ".md"],
    "image": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"],
    "video": [".mp4", ".webm", ".mov", ".avi", ".mkv"],
}


def _ensure_dir():
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)


def _get_file_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    for ft, exts in ALLOWED_EXTENSIONS.items():
        if ext in exts:
            return ft
    return "doc"


# ============ Schemas ============

class KnowledgeCreate(BaseModel):
    title: str = Field(..., max_length=200)
    content: Optional[str] = None
    category: str = Field(default="general", max_length=50)
    summary: Optional[str] = Field(None, max_length=500)


class KnowledgeUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    category: Optional[str] = Field(None, max_length=50)
    summary: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = None
    is_pinned: Optional[bool] = None


# ============ 管理端 API ============

@router.get("")
async def list_knowledge(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    status: Optional[str] = Query(None, description="状态筛选：published/draft，空则仅已发布"),
    sort: Optional[str] = Query("updated_at_desc", description="排序：updated_at_desc/view_count_desc"),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """知识库列表（支持分类筛选、关键词搜索、状态筛选、排序）"""
    # 非管理员仅能看已发布；管理员可筛选 draft/published/all
    can_manage = admin.role in ("super_admin", "admin", "tech")
    if not can_manage:
        query = select(KnowledgeArticle).where(KnowledgeArticle.status == "published")
    elif status == "draft":
        query = select(KnowledgeArticle).where(KnowledgeArticle.status == "draft")
    elif status == "all":
        query = select(KnowledgeArticle)
    else:
        query = select(KnowledgeArticle).where(KnowledgeArticle.status == "published")
    if category:
        query = query.where(KnowledgeArticle.category == category)
    if keyword:
        kw = f"%{keyword}%"
        query = query.where(
            or_(
                KnowledgeArticle.title.like(kw),
                KnowledgeArticle.content.like(kw),
                KnowledgeArticle.summary.like(kw),
            )
        )

    # 排序：置顶优先，再按指定字段
    if sort == "view_count_desc":
        query = query.order_by(KnowledgeArticle.is_pinned.desc(), KnowledgeArticle.view_count.desc(), KnowledgeArticle.updated_at.desc())
    else:
        query = query.order_by(KnowledgeArticle.is_pinned.desc(), KnowledgeArticle.updated_at.desc())

    count_q = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_q)

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(
        query.options(selectinload(KnowledgeArticle.attachments))
    )
    articles = result.scalars().all()

    items = []
    for a in articles:
        att_count = len(a.attachments) if a.attachments else 0
        items.append({
            "id": a.id,
            "title": a.title,
            "summary": a.summary or (a.content[:100] + "..." if a.content and len(a.content) > 100 else a.content),
            "category": a.category,
            "status": a.status,
            "view_count": a.view_count or 0,
            "is_pinned": bool(getattr(a, "is_pinned", 0)),
            "attachment_count": att_count,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        })

    return {"success": True, "total": total, "items": items}


@router.get("/categories")
async def get_categories(
    status: Optional[str] = Query(None, description="状态筛选，与列表一致"),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """获取知识库分类列表"""
    can_manage = admin.role in ("super_admin", "admin", "tech")
    if not can_manage or not status or status == "published":
        stmt = select(KnowledgeArticle.category, func.count(KnowledgeArticle.id)).where(KnowledgeArticle.status == "published").group_by(KnowledgeArticle.category)
    elif status == "draft":
        stmt = select(KnowledgeArticle.category, func.count(KnowledgeArticle.id)).where(KnowledgeArticle.status == "draft").group_by(KnowledgeArticle.category)
    else:
        stmt = select(KnowledgeArticle.category, func.count(KnowledgeArticle.id)).group_by(KnowledgeArticle.category)
    result = await db.execute(stmt)
    rows = result.all()
    cats = [{"value": r[0], "label": {"sms": "短信", "voice": "语音", "data": "数据", "general": "通用"}.get(r[0], r[0]), "count": r[1]} for r in rows]
    return {"success": True, "categories": cats}


@router.get("/{article_id}")
async def get_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """获取知识详情（增加浏览次数）；管理员可查看草稿"""
    can_manage = admin.role in ("super_admin", "admin", "tech")
    query = select(KnowledgeArticle).options(selectinload(KnowledgeArticle.attachments)).where(KnowledgeArticle.id == article_id)
    if not can_manage:
        query = query.where(KnowledgeArticle.status == "published")
    result = await db.execute(query)
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 在 commit 前提取所有需要的数据，避免 commit 后访问 ORM 对象触发 MissingGreenlet
    attachments = []
    for att in (article.attachments or []):
        attachments.append({
            "id": att.id,
            "file_type": att.file_type,
            "file_name": att.file_name,
            "file_size": att.file_size,
            "url": f"/api/v1/admin/knowledge/attachment/{att.id}",
        })

    view_count = article.view_count or 0
    if article.status == "published":
        view_count += 1
        article.view_count = view_count

    article_data = {
        "id": article.id,
        "title": article.title,
        "content": article.content,
        "category": article.category,
        "summary": article.summary,
        "status": article.status,
        "view_count": view_count,
        "is_pinned": bool(getattr(article, "is_pinned", 0)),
        "attachments": attachments,
        "created_at": article.created_at.isoformat() if article.created_at else None,
        "updated_at": article.updated_at.isoformat() if article.updated_at else None,
    }

    await db.commit()

    return {"success": True, "article": article_data}


@router.post("")
async def create_article(
    title: str = Form(...),
    content: Optional[str] = Form(None),
    category: str = Form("general"),
    summary: Optional[str] = Form(None),
    status: str = Form("published"),
    is_pinned: bool = Form(False),
    files: List[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("knowledge", "create")),
):
    """创建知识文章（可上传附件）"""
    admin, audit = auth
    if admin.role not in ("super_admin", "admin", "tech"):
        raise HTTPException(status_code=403, detail="无权限")

    _ensure_dir()
    article = KnowledgeArticle(
        title=title,
        content=content,
        category=category,
        summary=summary,
        created_by=admin.id,
        status=status if status in ("draft", "published") else "published",
        is_pinned=1 if is_pinned else 0,
    )
    db.add(article)
    await db.flush()

    # 保存附件
    for f in files:
        if not f.filename:
            continue
        ftype = _get_file_type(f.filename)
        content_bytes = await f.read()
        if len(content_bytes) > 50 * 1024 * 1024:  # 50MB
            continue
        subdir = KNOWLEDGE_DIR / str(article.id)
        subdir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex[:8]}_{f.filename}"
        file_path = subdir / safe_name
        with open(file_path, "wb") as fp:
            fp.write(content_bytes)
        rel_path = f"{article.id}/{safe_name}"
        att = KnowledgeAttachment(
            article_id=article.id,
            file_type=ftype,
            file_name=f.filename,
            file_path=rel_path,
            file_size=len(content_bytes),
        )
        db.add(att)

    await db.commit()
    await audit(target_id=article.id, target_type="knowledge",
                title=f"创建知识文章: {title[:60]}",
                detail={"category": category, "status": article.status,
                        "attachments": len(files or [])})
    await db.commit()
    return {"success": True, "id": article.id, "message": "创建成功"}


@router.put("/{article_id}")
async def update_article(
    article_id: int,
    data: KnowledgeUpdate,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("knowledge", "update")),
):
    """更新知识文章"""
    admin, audit = auth
    if admin.role not in ("super_admin", "admin", "tech"):
        raise HTTPException(status_code=403, detail="无权限")

    result = await db.execute(select(KnowledgeArticle).where(KnowledgeArticle.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    if data.title is not None:
        article.title = data.title
    if data.content is not None:
        article.content = data.content
    if data.category is not None:
        article.category = data.category
    if data.summary is not None:
        article.summary = data.summary
    if data.status is not None:
        article.status = data.status
    if data.is_pinned is not None:
        article.is_pinned = 1 if data.is_pinned else 0

    await db.commit()
    await audit(target_id=article_id, target_type="knowledge",
                title=f"更新知识文章 {article.title[:60]}",
                detail={"changed_fields": [k for k, v in data.dict().items() if v is not None]})
    await db.commit()
    return {"success": True, "message": "更新成功"}


@router.post("/{article_id}/attachments")
async def add_attachments(
    article_id: int,
    files: List[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("knowledge", "add_attachments")),
):
    """为文章追加附件"""
    admin, audit = auth
    if admin.role not in ("super_admin", "admin", "tech"):
        raise HTTPException(status_code=403, detail="无权限")

    result = await db.execute(select(KnowledgeArticle).where(KnowledgeArticle.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    _ensure_dir()
    subdir = KNOWLEDGE_DIR / str(article_id)
    subdir.mkdir(parents=True, exist_ok=True)

    for f in files:
        if not f.filename:
            continue
        ftype = _get_file_type(f.filename)
        content_bytes = await f.read()
        if len(content_bytes) > 50 * 1024 * 1024:
            continue
        safe_name = f"{uuid.uuid4().hex[:8]}_{f.filename}"
        file_path = subdir / safe_name
        with open(file_path, "wb") as fp:
            fp.write(content_bytes)
        att = KnowledgeAttachment(
            article_id=article_id,
            file_type=ftype,
            file_name=f.filename,
            file_path=f"{article_id}/{safe_name}",
            file_size=len(content_bytes),
        )
        db.add(att)

    await db.commit()
    file_count = sum(1 for f in (files or []) if f.filename)
    await audit(target_id=article_id, target_type="knowledge",
                title=f"追加附件 article={article_id}",
                detail={"count": file_count})
    await db.commit()
    return {"success": True, "message": "上传成功"}


@router.delete("/{article_id}")
async def delete_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("knowledge", "delete")),
):
    """删除知识文章"""
    admin, audit = auth
    if admin.role not in ("super_admin", "admin", "tech"):
        raise HTTPException(status_code=403, detail="无权限")

    result = await db.execute(
        select(KnowledgeArticle).options(selectinload(KnowledgeArticle.attachments)).where(KnowledgeArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 删除物理文件
    for att in article.attachments or []:
        fp = KNOWLEDGE_DIR / att.file_path
        if fp.exists():
            try:
                fp.unlink()
            except Exception:
                pass
    subdir = KNOWLEDGE_DIR / str(article_id)
    if subdir.exists():
        try:
            subdir.rmdir()
        except Exception:
            pass

    snap = {"title": article.title, "category": article.category, "status": article.status,
            "attachment_count": len(article.attachments or [])}
    await db.delete(article)
    await db.commit()
    await audit(target_id=article_id, target_type="knowledge",
                title=f"删除知识文章 {snap['title'][:60]}", detail=snap)
    await db.commit()
    return {"success": True, "message": "删除成功"}


@router.get("/attachment/{attachment_id}")
async def download_attachment(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """下载附件"""
    result = await db.execute(
        select(KnowledgeAttachment).where(KnowledgeAttachment.id == attachment_id)
    )
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="附件不存在")

    file_path = (KNOWLEDGE_DIR / att.file_path).resolve()
    if not file_path.is_relative_to(KNOWLEDGE_DIR.resolve()):
        raise HTTPException(status_code=403, detail="非法路径")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    media_type, _ = mimetypes.guess_type(att.file_name)
    return FileResponse(
        path=str(file_path),
        filename=att.file_name,
        media_type=media_type or "application/octet-stream",
    )
