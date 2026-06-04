#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  AutoLearning — 腾讯云部署脚本                               ║
# ║  前置条件:                                                   ║
# ║  - 腾讯云 CVM (Ubuntu 22.04+, 4C8G+)                       ║
# ║  - 已安装 Docker + Docker Compose                           ║
# ║  - 已开放安全组端口: 80, 443, 8000, 5173                    ║
# ╚══════════════════════════════════════════════════════════════╝
set -euo pipefail

echo "=========================================="
echo "  AutoLearning 腾讯云部署"
echo "=========================================="

# 配置
PROJECT_DIR="/opt/autolearning"
DOMAIN="${1:-localhost}"

# 1. 安装 Docker (如果未安装)
if ! command -v docker &> /dev/null; then
    echo "[1/6] 安装 Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "  ✅ Docker 已安装"
else
    echo "[1/6] Docker 已就绪"
fi

# 2. 安装 Docker Compose (如果未安装)
if ! docker compose version &> /dev/null; then
    echo "[2/6] 安装 Docker Compose..."
    apt-get update -qq
    apt-get install -y -qq docker-compose-plugin
    echo "  ✅ Docker Compose 已安装"
else
    echo "[2/6] Docker Compose 已就绪"
fi

# 3. 克隆项目
echo "[3/6] 克隆项目..."
if [ -d "$PROJECT_DIR" ]; then
    cd "$PROJECT_DIR"
    git pull origin main
else
    git clone https://github.com/LGY4/AutoLearning.git "$PROJECT_DIR"
    cd "$PROJECT_DIR"
fi

# 4. 配置环境变量
echo "[4/6] 配置环境变量..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  ⚠️  请编辑 $PROJECT_DIR/.env 填入 LLM_API_KEY"
    echo "  运行: nano $PROJECT_DIR/.env"
    exit 1
fi

# 5. 启动服务
echo "[5/6] 启动服务..."
cd infra
docker compose up -d --build

# 等待就绪
echo "  等待服务就绪..."
for i in $(seq 1 120); do
    if curl -s http://localhost:8000/health &>/dev/null; then
        echo "  ✅ 后端就绪"
        break
    fi
    sleep 2
done

# 6. 配置 Nginx 反向代理 (可选)
if [ "$DOMAIN" != "localhost" ]; then
    echo "[6/6] 配置 Nginx 反向代理..."
    apt-get install -y -qq nginx certbot python3-certbot-nginx

    cat > /etc/nginx/sites-available/autolearning << EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location /static/ {
        proxy_pass http://127.0.0.1:8000;
    }
}
EOF

    ln -sf /etc/nginx/sites-available/autolearning /etc/nginx/sites-enabled/
    nginx -t && systemctl reload nginx

    # 自动 HTTPS
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@"$DOMAIN" || true
    echo "  ✅ Nginx 配置完成"
else
    echo "[6/6] 跳过 Nginx 配置（未指定域名）"
fi

echo ""
echo "=========================================="
echo "  ✅ 部署完成"
echo "=========================================="
echo "  前端: http://$DOMAIN"
echo "  后端: http://$DOMAIN:8000/docs"
echo "  健康: http://$DOMAIN:8000/health"
echo ""
echo "  查看日志: cd $PROJECT_DIR/infra && docker compose logs -f"
echo "  停止服务: cd $PROJECT_DIR/infra && docker compose down"
echo "  更新代码: cd $PROJECT_DIR && git pull && cd infra && docker compose up -d --build"
echo "=========================================="
