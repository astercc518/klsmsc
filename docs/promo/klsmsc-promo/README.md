# sms1.site 宣传片（HyperFrames）

竖屏 1080×1920 / 45 秒 / 中文 motion-graphics 宣传片。**主题：出售整套国际短信系统**（品牌 sms1.site，受众=想自建/运营出海短信平台的买家，不是终端发短信客户）。用 [HeyGen HyperFrames](https://github.com/heygen-com/hyperframes)（写 HTML/CSS/GSAP → 渲染确定性 MP4，**不需要 GPU**）制作。

> 注意：品牌为 **sms1.site**，全片不出现"考拉出海"。

## 文件
- `index.html` —— 视频源（8 场景：从零搭系统的痛点/sms1.site整套交付/内置全球路由/自带TG开户机器人/管理后台群发回执/系统能力/CTA出售）
- `assets/fonts/KLSans-{Regular,Bold}.woff2` —— Noto Sans CJK SC 子集（全汉字块），渲染器需 @font-face 本地字体
- `renders/klsmsc-promo_*.mp4` —— 已渲染成片
- `hyperframes.json` / `package.json` / `meta.json` / `CLAUDE.md` —— HyperFrames 工程文件

## 在哪渲染
**不要在 KLSMSC 生产机做。** 环境已搭在 **sms1.site（103.246.246.22）**：`/opt/video/klsmsc-promo/`。
改 `index.html` 后：
```bash
cd /opt/video/klsmsc-promo
npm run check     # lint + 校验（淡出到 clip 边界须配 tl.set(opacity:0) 硬清）
npm run render    # 渲染到 renders/，45s 约 80 秒
```

## 从零搭建环境（换新机时）
```bash
# 1. Node 22 + FFmpeg + 无头 Chrome 系统库
curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs ffmpeg
apt-get install -y ca-certificates fonts-liberation libasound2 libatk-bridge2.0-0 \
  libatk1.0-0 libcairo2 libcups2 libdbus-1-3 libexpat1 libfontconfig1 libgbm1 \
  libglib2.0-0 libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 libpangocairo-1.0-0 \
  libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 libxdamage1 libxext6 \
  libxfixes3 libxi6 libxrandr2 libxrender1 libxss1 libxtst6 libxkbcommon0 libdrm2
# 2. 工程
npx hyperframes@latest init klsmsc-promo   # 然后覆盖 index.html / 拷入 assets/fonts
# 3. 中文字体子集（系统装 fonts-noto-cjk + fonttools 后；SC 在 ttc 第 2 号字面）
apt-get install -y fonts-noto-cjk fonttools python3-brotli
UNI="U+0020-007E,U+00A0-00FF,U+2000-206F,U+3000-303F,U+FF00-FFEF,U+4E00-9FFF"
pyftsubset /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc --font-number=2 \
  --unicodes="$UNI" --flavor=woff2 --output-file=assets/fonts/KLSans-Regular.woff2
pyftsubset /usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc --font-number=2 \
  --unicodes="$UNI" --flavor=woff2 --output-file=assets/fonts/KLSans-Bold.woff2
```

## 待替换占位（发布前改 index.html）
- S8：`@你的客服` → 真实 TG 客服号（域名已是 sms1.site）
- S4「200+ 国家」、S6「58,420」→ 换成真实可站得住的数字（**勿吹"99%送达"**）

## 验证（无法直接看视频时）
```bash
ffmpeg -ss <秒> -i renders/xxx.mp4 -frames:v 1 frame.png   # 抽帧检查
```
