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

# 创建日志目录（开发环境 bind mount 会覆盖 /app，入口用 sh 执行以免丢失可执行位）
RUN mkdir -p logs

# 暴露端口
EXPOSE 8000

ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
# 默认命令（可被 docker-compose command 覆盖，参数会传给 entrypoint）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

