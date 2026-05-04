FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir docker

# 复制应用代码
COPY . .

# 创建日志/上传目录
RUN mkdir -p logs /tmp/smsc_imports /tmp/smsc_pl_uploads

# 创建非 root 用户 (uid 1000)，把 /app 与运行时目录交给它
# 容器逃逸/RCE 时降低攻击面：进程不能修改宿主机以 root 拥有的文件
RUN useradd --uid 1000 --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app /tmp/smsc_imports /tmp/smsc_pl_uploads

USER appuser

# 暴露端口
EXPOSE 8000

ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
# 默认命令（可被 docker-compose command 覆盖，参数会传给 entrypoint）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

