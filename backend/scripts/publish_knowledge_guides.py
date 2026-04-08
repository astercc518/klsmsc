#!/usr/bin/env python3
"""
将指定 Markdown 指南转为 PDF，并写入业务知识库（knowledge_articles + knowledge_attachments）。

依赖：已安装 markdown、weasyprint；宿主机可执行 docker；容器 smsc-mysql 运行中。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

# 项目根目录（/var/smsc）
REPO_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = REPO_ROOT / "data" / "knowledge"
MD2PDF = REPO_ROOT / "backend" / "scripts" / "md2pdf.py"


def _load_mysql_root_password() -> str:
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MYSQL_ROOT_PASSWORD="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("MYSQL_ROOT_PASSWORD", "rootpass123")


def _docker_mysql(sql: str) -> str:
    pwd = _load_mysql_root_password()
    r = subprocess.run(
        [
            "docker",
            "exec",
            "smsc-mysql",
            "mysql",
            "-uroot",
            f"-p{pwd}",
            "sms_system",
            "-N",
            "-e",
            sql,
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        raise RuntimeError(f"mysql 失败: {r.stderr}")
    return r.stdout.strip()


def _sql_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "''")


def publish_one(
    title: str,
    category: str,
    summary: str,
    content: str,
    md_path: Path,
    pdf_basename: str,
    is_pinned: int,
) -> None:
    """生成 PDF、创建文章与附件"""
    if not md_path.is_file():
        raise FileNotFoundError(md_path)

    tmp_pdf = Path("/tmp") / f"_kb_{uuid.uuid4().hex}.pdf"
    subprocess.run(
        [sys.executable, str(MD2PDF), str(md_path), str(tmp_pdf)],
        check=True,
        cwd=str(REPO_ROOT),
    )

    t = _sql_str(title)
    c = _sql_str(content)
    s = _sql_str(summary)
    cat = _sql_str(category)

    _docker_mysql(
        f"""INSERT INTO knowledge_articles (title, content, category, summary, created_by, status, is_pinned)
        VALUES ('{t}', '{c}', '{cat}', '{s}', 1, 'published', {is_pinned});"""
    )

    # 取刚插入的文章 ID（标题唯一假设：本脚本单次运行各标题不同）
    aid_s = _docker_mysql(
        f"SELECT id FROM knowledge_articles WHERE title = '{t}' ORDER BY id DESC LIMIT 1;"
    )
    article_id = int(aid_s.split()[0])
    safe_name = f"{uuid.uuid4().hex[:8]}_{pdf_basename}"
    sub = KNOWLEDGE_DIR / str(article_id)
    sub.mkdir(parents=True, exist_ok=True)
    dest = sub / safe_name
    shutil.copy2(tmp_pdf, dest)
    tmp_pdf.unlink(missing_ok=True)

    rel = f"{article_id}/{safe_name}"
    sz = dest.stat().st_size
    fn = _sql_str(pdf_basename)

    _docker_mysql(
        f"""INSERT INTO knowledge_attachments (article_id, file_type, file_name, file_path, file_size)
        VALUES ({article_id}, 'doc', '{fn}', '{_sql_str(rel)}', {sz});"""
    )

    print(f"已发布: {title} → 文章 id={article_id}, 附件 {rel}")


def main() -> None:
    guides = [
        {
            "title": "SMS Gateway 客户操作指南",
            "category": "sms",
            "summary": "客户使用 Web 门户的说明：登录、短信发送与记录、账户与 API、余额与工单、数据业务入口及常见问题。",
            "content": "详见附件 PDF。本文档面向已开户客户，配合《SMS Gateway HTTP与SMPP接口文档》进行技术对接。",
            "md": REPO_ROOT / "docs" / "guides" / "客户操作指南.md",
            "pdf": "客户操作指南.pdf",
            "pinned": 1,
        },
        {
            "title": "SMS Gateway 员工操作指南",
            "category": "general",
            "summary": "内部员工使用说明：权限角色、业务数据看板、代客登录协助、业务知识库、工单与客户管理注意事项。",
            "content": "详见附件 PDF。实际菜单以管理员分配的角色为准。",
            "md": REPO_ROOT / "docs" / "guides" / "员工操作指南.md",
            "pdf": "员工操作指南.pdf",
            "pinned": 1,
        },
        {
            "title": "SMS Gateway 管理员系统维护手册",
            "category": "general",
            "summary": "运维与管理员手册：Docker 启停、数据库与迁移、Worker/SMPP、系统配置、监控排错及仓库内参考文档索引。",
            "content": "详见附件 PDF。命令与密码请以实际环境为准。",
            "md": REPO_ROOT / "docs" / "guides" / "管理员系统维护手册.md",
            "pdf": "管理员系统维护手册.pdf",
            "pinned": 1,
        },
    ]

    for g in guides:
        publish_one(
            title=g["title"],
            category=g["category"],
            summary=g["summary"],
            content=g["content"],
            md_path=g["md"],
            pdf_basename=g["pdf"],
            is_pinned=g["pinned"],
        )

    print("全部完成。")


if __name__ == "__main__":
    main()
