# 考拉落地站：构建时从 GitHub 拉取 astercc518/kaolach（Node 快照预览服务）
FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG KAOLACH_REPO=https://github.com/astercc518/kaolach.git
ARG KAOLACH_REF=main

RUN git clone --depth 1 --branch "${KAOLACH_REF}" "${KAOLACH_REPO}" .

# 与 preview-server.mjs 一致：容器内需监听全网卡
ENV PREVIEW_BIND=0.0.0.0
ENV PORT=8787
ENV PREVIEW_BRAND_NAME=kaolach
ENV LIVE_ORIGIN=https://illyvoip.com
ENV PREVIEW_PROXY_MISS=1

EXPOSE 8787

CMD ["node", "preview-server.mjs"]
