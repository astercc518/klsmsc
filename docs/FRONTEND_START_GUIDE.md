# 前端服务启动指南

## 问题诊断

当前环境可能缺少Node.js/npm，需要先安装或配置。

## 解决方案

### 方案1: 安装Node.js和npm

```bash
# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# 或使用nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 18
nvm use 18
```

### 方案2: 使用Docker运行前端

如果已有Docker环境，可以创建Dockerfile：

```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

### 方案3: 使用已构建的静态文件

如果已有构建好的前端文件，可以使用nginx等Web服务器：

```nginx
server {
    listen 5173;
    server_name 103.246.244.237;
    
    location / {
        root /var/smsc/frontend/dist;
        try_files $uri $uri/ /index.html;
    }
    
    location /api {
        proxy_pass http://103.246.244.237:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 当前配置状态

✅ 已完成的配置:
- Vite代理配置已更新
- API baseURL配置已更新
- 环境变量文件已创建 (.env.local)

## 验证配置

即使前端服务未运行，配置已经正确：

1. **Vite配置** (`frontend/vite.config.ts`):
   - 代理target: `http://103.246.244.237:8000`
   - 支持环境变量配置

2. **API配置** (`frontend/src/api/index.ts`):
   - 支持直接使用完整URL
   - 如果配置了VITE_API_BASE_URL，直接使用

3. **环境变量** (`frontend/.env.local`):
   ```bash
   VITE_API_BASE_URL=http://103.246.244.237:8000
   VITE_API_TARGET=http://103.246.244.237:8000
   ```

## 启动命令

一旦Node.js安装完成：

```bash
cd /var/smsc/frontend

# 安装依赖（首次）
npm install

# 启动开发服务器
npm run dev

# 或构建生产版本
npm run build
npm run preview
```

## 验证修复

启动后访问：
- http://103.246.244.237:5173/admin/system/config

应该：
- ✅ 页面正常加载
- ✅ 无503错误
- ✅ API请求返回200
- ✅ 系统配置列表正常显示

