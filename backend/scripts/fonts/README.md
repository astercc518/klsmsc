# 中文字体目录

生成 `SMS_API_接口文档.pdf` 时，脚本会将 **Noto Sans SC**（简体子集）下载到此目录并缓存，供 WeasyPrint 嵌入 PDF，避免中文显示为方框。

若目录为空，执行：

```bash
python3 backend/scripts/md2pdf.py docs/SMS_API_接口文档.md /path/to/out.pdf
```

也可手动安装系统字体（如 Debian/Ubuntu：`apt install fonts-noto-cjk`），脚本仍会优先使用本目录已缓存的 `.otf` 文件。
