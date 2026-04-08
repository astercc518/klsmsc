# 操作指南（Markdown 源稿）

本目录为 **客户 / 员工 / 管理员** 三类操作说明的 Markdown 源文件，可用于版本维护与再次生成 PDF。

**客户指南配图**：截图脚本会将 PNG 保存到 `images/`，Markdown 中以 `images/xxx.png` 引用；`md2pdf.py` 会以 `.md` 所在目录为 `base_url` 嵌入 PDF。

## 截取客户门户界面（Playwright）

需本机可访问前端（默认 `http://127.0.0.1`，与 `capture_screenshots.py` 中 `BASE` 一致）：

```bash
cd /var/smsc
python3 backend/scripts/capture_screenshots.py
```

## 生成 PDF

```bash
cd /var/smsc
python3 backend/scripts/md2pdf.py docs/guides/客户操作指南.md /tmp/客户操作指南.pdf
```

## 批量发布到业务知识库

在宿主机已安装 `markdown`、`weasyprint`，且 Docker 中 `smsc-mysql` 可用时：

```bash
python3 backend/scripts/publish_knowledge_guides.py
```

> 重复执行会**再次插入**文章记录；若仅需更新内容，请在管理后台删除旧文后重跑，或改脚本为「按标题更新」逻辑。
