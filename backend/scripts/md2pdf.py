"""
将 Markdown 转为 PDF（嵌入 Noto Sans SC，避免中文乱码）

首次运行若缺少字体，会从官方源自动下载到 backend/scripts/fonts/ 并缓存。

用法：
  python3 md2pdf.py [输入.md] [输出.pdf] [--header 页眉文字]
  未指定 --header 时，取 Markdown 首个一级标题（# xxx）作为页眉。
"""
from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

import markdown
from weasyprint import HTML

SCRIPT_DIR = Path(__file__).resolve().parent
FONT_DIR = SCRIPT_DIR / "fonts"
NOTO_SC_OTF = FONT_DIR / "NotoSansSC-Regular.otf"
# Noto CJK 简体子集（约 8MB），含常用汉字，适合接口文档
NOTO_SC_URL = (
    "https://raw.githubusercontent.com/notofonts/noto-cjk/main/"
    "Sans/SubsetOTF/SC/NotoSansSC-Regular.otf"
)


def _default_header_from_md(md_text: str) -> str:
    for line in md_text.splitlines():
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip()
    return "SMS Gateway 文档"


def _css_escape_content(s: str) -> str:
    """CSS content: "..." 内转义"""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _ensure_cjk_font() -> Path:
    """确保存在可用的简体中文字体文件"""
    if NOTO_SC_OTF.exists() and NOTO_SC_OTF.stat().st_size > 1_000_000:
        return NOTO_SC_OTF
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"正在下载中文字体 Noto Sans SC（约 8MB）到 {NOTO_SC_OTF} ...")
    req = urllib.request.Request(
        NOTO_SC_URL,
        headers={"User-Agent": "smsc-md2pdf/1.0"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    NOTO_SC_OTF.write_bytes(data)
    print("字体下载完成。")
    return NOTO_SC_OTF


def build_pdf(md_path: Path, out_path: Path, header_title: str | None = None) -> None:
    font_path = _ensure_cjk_font()
    # WeasyPrint 需要可访问的绝对路径
    font_url = font_path.as_uri()

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    page_header = header_title or _default_header_from_md(md_text)
    page_header_esc = _css_escape_content(page_header)

    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "codehilite", "toc", "sane_lists"],
        extension_configs={"codehilite": {"css_class": "code"}},
    )

    # 全站使用嵌入字体；代码块同样用该字体以免示例中文乱码
    css = f"""
    @font-face {{
        font-family: "Noto Sans SC";
        font-style: normal;
        font-weight: 400;
        src: url("{font_url}") format("opentype");
    }}

    @page {{
        size: A4;
        margin: 2cm 2.2cm;
        @top-center {{
            content: "{page_header_esc}";
            font-family: "Noto Sans SC", sans-serif;
            font-size: 9px;
            color: #999;
        }}
        @bottom-center {{
            content: "第 " counter(page) " 页";
            font-family: "Noto Sans SC", sans-serif;
            font-size: 9px;
            color: #999;
        }}
    }}
    body {{
        font-family: "Noto Sans SC", sans-serif;
        font-size: 11pt;
        line-height: 1.7;
        color: #333;
    }}
    h1 {{
        color: #1a56db;
        font-size: 22pt;
        border-bottom: 3px solid #1a56db;
        padding-bottom: 8px;
        margin-top: 0;
    }}
    h2 {{
        color: #1e40af;
        font-size: 16pt;
        border-bottom: 1px solid #ddd;
        padding-bottom: 6px;
        margin-top: 28px;
        page-break-after: avoid;
    }}
    h3 {{
        color: #1e3a5f;
        font-size: 13pt;
        margin-top: 22px;
        page-break-after: avoid;
    }}
    h4 {{
        color: #374151;
        font-size: 11.5pt;
        margin-top: 16px;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 12px 0 18px 0;
        font-size: 10pt;
        page-break-inside: avoid;
    }}
    th, td {{
        border: 1px solid #d1d5db;
        padding: 7px 10px;
        text-align: left;
    }}
    th {{
        background-color: #f0f4ff;
        color: #1e40af;
        font-weight: 600;
    }}
    tr:nth-child(even) {{
        background-color: #f9fafb;
    }}
    code {{
        font-family: "Noto Sans SC", "Consolas", monospace;
        background-color: #f3f4f6;
        padding: 1px 5px;
        border-radius: 3px;
        font-size: 9.5pt;
        color: #c7254e;
    }}
    pre {{
        background-color: #1e293b;
        color: #e2e8f0;
        padding: 14px 18px;
        border-radius: 6px;
        overflow-x: auto;
        font-family: "Noto Sans SC", "Consolas", monospace;
        font-size: 9pt;
        line-height: 1.5;
        page-break-inside: avoid;
        margin: 10px 0 16px 0;
    }}
    pre code {{
        background: none;
        color: #e2e8f0;
        padding: 0;
        font-size: 9pt;
    }}
    blockquote {{
        border-left: 4px solid #3b82f6;
        background: #eff6ff;
        margin: 12px 0;
        padding: 10px 16px;
        color: #1e40af;
        font-size: 10.5pt;
    }}
    blockquote p {{
        margin: 4px 0;
    }}
    hr {{
        border: none;
        border-top: 1px solid #e5e7eb;
        margin: 24px 0;
    }}
    a {{
        color: #2563eb;
        text-decoration: none;
    }}
    ul, ol {{
        padding-left: 24px;
    }}
    li {{
        margin-bottom: 4px;
    }}
    strong {{
        color: #111827;
    }}
    img {{
        max-width: 100%;
        height: auto;
        display: block;
        margin: 10px auto 16px auto;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
    }}
    """

    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>{css}</style>
</head>
<body>
{html_body}
</body>
</html>"""

    # Markdown 与图片相对路径（如 images/xxx.png）以 .md 所在目录为基准
    md_base = md_path.resolve().parent
    HTML(string=full_html, base_url=str(md_base)).write_pdf(str(out_path))
    print(f"PDF 已生成: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Markdown 转 PDF（嵌入中文字体）")
    parser.add_argument("md", nargs="?", type=Path, default=Path("/var/smsc/docs/SMS_API_接口文档.md"))
    parser.add_argument("out", nargs="?", type=Path, default=Path("/tmp/SMS_API_接口文档.pdf"))
    parser.add_argument("--header", default=None, help="PDF 页眉标题（默认取首个 # 标题）")
    args = parser.parse_args()
    build_pdf(args.md, args.out, args.header)


if __name__ == "__main__":
    main()
