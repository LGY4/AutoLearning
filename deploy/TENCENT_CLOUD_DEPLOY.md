# 腾讯云部署完整指南

## 前置条件

- 腾讯云账号
- 域名（可选，用于 HTTPS）
- DeepSeek API Key（或其他 LLM 服务）

---

## 第一步：购买云服务器

### 推荐配置

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2 核 | 4 核 |
| 内存 | 4 GB | 8 GB |
| 硬盘 | 40 GB SSD | 80 GB SSD |
| 系统 | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| 带宽 | 5 Mbps | 10 Mbps |

### 购买步骤

1. 登录 [腾讯云控制台](https://console.cloud.tencent.com/)
2. 进入 **云服务器 CVM** → **创建实例**
3. 选择 **Ubuntu 22.04 LTS**
4. 选择推荐配置
5. 设置 root 密码或 SSH 密钥
6. 安全组开放端口：**22**（SSH）、**80**（HTTP）、**443**（HTTPS）、**8000**（后端 API）、**5173**（前端）
7. 创建实例，等待启动完成

---

## 第二步：配置安全组

在腾讯云控制台 → **安全组** → 编辑入站规则：

| 协议 | 端口 | 来源 | 说明 |
|------|------|------|------|
| TCP | 22 | 0.0.0.0/0 | SSH 远程连接 |
| TCP | 80 | 0.0.0.0/0 | HTTP 访问 |
| TCP | 443 | 0.0.0.0/0 | HTTPS 访问 |
| TCP | 8000 | 0.0.0.0/0 | 后端 API |
| TCP | 5173 | 0.0.0.0/0 | 前端页面 |

---

## 第三步：连接服务器

```bash
# 使用 SSH 连接（替换为你的服务器 IP）
ssh root@your-server-ip

# 如果使用密钥文件
ssh -i ~/.ssh/your-key.pem root@your-server-ip
```

---

## 第四步：安装 Docker

```bash
# 更新系统
apt update && apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 启动 Docker
systemctl enable docker
systemctl start docker

# 验证安装
docker --version
docker compose version
```

---

## 第五步：部署项目

### 方式一：一键脚本部署（推荐）

```bash
# 下载并执行部署脚本
curl -fsSL https://raw.githubusercontent.com/LGY4/AutoLearning/main/deploy/tencent-cloud.sh -o deploy.sh
chmod +x deploy.sh

# 执行部署（无域名）
./deploy.sh

# 或指定域名（自动配置 Nginx + HTTPS）
./deploy.sh your-domain.com
```

脚本会自动完成：
- 克隆项目到 `/opt/autolearning`
- 检查并配置 `.env`
- 启动所有 Docker 服务
- 配置 Nginx 反向代理（如果有域名）
- 申请 Let's Encrypt HTTPS 证书（如果有域名）

### 方式二：手动部署

```bash
# 1. 克隆项目
git clone https://github.com/LGY4/AutoLearning.git /opt/autolearning
cd /opt/autolearning

# 2. 配置环境变量
cp .env.example .env

# 编辑 .env 文件
nano .env
```

**必须配置的环境变量：**

```bash
# LLM 配置（必填）
LLM_API_KEY=sk-your-deepseek-api-key
LLM_MODEL=deepseek-chat
LLM_TIMEOUT_SECONDS=300

# 安全密钥（生产环境必须修改）
SECRET_KEY=your-random-secret-key-here

# 数据库（Docker 自动创建，无需修改）
DATABASE_URL=postgresql+psycopg://autolearning:autolearning@postgres:5432/autolearning
REDIS_URL=redis://redis:6379/0

# CORS（添加你的域名或 IP）
CORS_ORIGINS=http://your-domain.com,https://your-domain.com
```

```bash
# 3. 启动服务
cd infra
docker compose -f docker-compose.yml -f ../deploy/docker-compose.prod.yml up -d --build

# 4. 查看启动日志
docker compose logs -f

# 5. 验证服务
curl http://localhost:8000/health
# 应返回: {"status":"ok","service":"AutoLearning"}
```

---

## 第六步：配置 Nginx 反向代理（推荐）

### 安装 Nginx

```bash
apt install -y nginx
```

### 配置 Nginx

```bash
nano /etc/nginx/sites-available/autolearning
```

写入以下配置：

```nginx
server {
    listen 80;
    server_name your-domain.com;  # 替换为你的域名

    # 前端
    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 后端 API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # 静态资源
    location /static/ {
        proxy_pass http://127.0.0.1:8000;
    }

    # SSE 流式连接
    location /api/v1/learning/chat-stream {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

### 启用配置

```bash
ln -sf /etc/nginx/sites-available/autolearning /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

---

## 第七步：配置 HTTPS（推荐）

```bash
# 安装 Certbot
apt install -y certbot python3-certbot-nginx

# 申请证书（自动配置 Nginx）
certbot --nginx -d your-domain.com

# 自动续期（Certbot 自动设置定时任务）
certbot renew --dry-run
```

---

## 第八步：配置域名解析

在你的域名注册商（如腾讯云 DNSPod）添加 DNS 记录：

| 类型 | 主机记录 | 记录值 | TTL |
|------|---------|--------|-----|
| A | @ | 你的服务器 IP | 600 |
| A | www | 你的服务器 IP | 600 |

---

## 第九步：验证部署

### 访问测试

```
前端页面: http://your-domain.com 或 https://your-domain.com
后端 API: http://your-domain.com:8000/docs
健康检查: http://your-domain.com:8000/health
```

### 功能测试

1. 打开前端页面，注册新账号
2. 登录后，看到欢迎面板（今日学习建议）
3. 输入"帮我出几道练习题"→ 练习面板出现
4. 输入"生成思维导图"→ 资源生成
5. 输入"看看学习地图"→ 知识图谱展示
6. 切换侧边栏模块 → 对话中发送对应消息

---

## 常用运维命令

```bash
# 查看服务状态
cd /opt/autolearning/infra
docker compose ps

# 查看日志
docker compose logs -f backend
docker compose logs -f frontend

# 重启服务
docker compose restart

# 更新代码
cd /opt/autolearning
git pull origin main
cd infra
docker compose up -d --build

# 停止所有服务
docker compose down

# 备份数据库
docker compose exec postgres pg_dump -U autolearning autolearning > backup_$(date +%Y%m%d).sql

# 恢复数据库
docker compose exec -T postgres psql -U autolearning autolearning < backup.sql
```

---

## 故障排查

### 后端启动失败

```bash
# 查看后端日志
docker compose logs backend | tail -50

# 常见原因：
# 1. LLM_API_KEY 未配置 → 编辑 .env
# 2. PostgreSQL 未就绪 → 等待几秒后重试
# 3. 端口被占用 → 检查 8000 端口
```

### 前端无法访问

```bash
# 检查前端容器
docker compose ps frontend

# 查看 Nginx 日志
tail -50 /var/log/nginx/error.log

# 常见原因：
# 1. Nginx 配置错误 → nginx -t 检查
# 2. 端口未开放 → 检查安全组
```

### AI 响应超时

```bash
# 检查 LLM 配置
grep LLM_API_KEY /opt/autolearning/.env

# 测试 LLM 连通性
curl -s https://api.deepseek.com/v1/models \
  -H "Authorization: Bearer your-api-key"

# 常见原因：
# 1. API Key 无效 → 更换 Key
# 2. 网络不通 → 检查服务器出网
# 3. 超时太短 → 增加 LLM_TIMEOUT_SECONDS
```

---

## 成本估算

| 资源 | 配置 | 月费用（约） |
|------|------|-------------|
| CVM 云服务器 | 4C8G | ¥200-400 |
| 域名 | .com | ¥50-80/年 |
| HTTPS 证书 | Let's Encrypt | 免费 |
| DeepSeek API | 按量计费 | ¥10-50 |
| **合计** | | **¥210-450/月** |

---

## 项目结构

```
/opt/autolearning/
├── backend/              # FastAPI 后端
│   ├── app/              # 业务代码
│   ├── Dockerfile        # 后端 Docker 镜像
│   └── requirements.txt  # Python 依赖
├── frontend/             # React 前端
│   ├── src/              # 源代码
│   ├── Dockerfile        # 前端 Docker 镜像
│   └── nginx.conf        # Nginx 配置
├── infra/                # Docker Compose
│   └── docker-compose.yml
├── deploy/               # 部署配置
│   ├── docker-compose.prod.yml
│   └── tencent-cloud.sh
├── .env                  # 环境变量（不提交到 Git）
├── .env.example          # 环境变量模板
├── start.sh              # 一键启动脚本
└── README.md             # 项目说明
```
