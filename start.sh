#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  AutoLearning — 一键启动脚本 (Linux / macOS / WSL)           ║
# ╚══════════════════════════════════════════════════════════════╝
set -euo pipefail

cd "$(dirname "$0")"

echo "=========================================="
echo "  AutoLearning 一键启动"
echo "=========================================="

# 1. 检查 .env
if [ ! -f .env ]; then
    echo "[1/5] 未检测到 .env，从模板创建..."
    cp .env.example .env
    echo "  ⚠️  请编辑 .env 填入 LLM_API_KEY 后重新运行"
    echo "  文件位置: $(pwd)/.env"
    exit 1
fi
echo "[1/5] .env 已就绪"

# 2. 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ 未安装 Docker。请先安装 Docker Desktop: https://docker.com/products/docker-desktop"
    exit 1
fi
echo "[2/5] Docker 已就绪"

# 3. 启动基础设施 (PostgreSQL + Redis)
echo "[3/5] 启动 PostgreSQL + Redis..."
cd infra
docker compose up -d postgres redis
echo "  等待数据库就绪..."
sleep 5

# 等待 PostgreSQL 健康
for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U autolearning &>/dev/null; then
        echo "  ✅ PostgreSQL 就绪"
        break
    fi
    sleep 1
done

# 4. 启动后端
echo "[4/5] 启动后端..."
cd ../backend

# 创建虚拟环境
if [ ! -d .venv ]; then
    python3 -m venv .venv
    echo "  虚拟环境已创建"
fi

source .venv/bin/activate
pip install -q -r requirements.txt

# 运行迁移和种子数据
python -m app.ops.start_api &
BACKEND_PID=$!
echo "  后端 PID: $BACKEND_PID"

# 等待后端就绪
for i in $(seq 1 60); do
    if curl -s http://localhost:8000/health &>/dev/null; then
        echo "  ✅ 后端就绪"
        break
    fi
    sleep 1
done

# 5. 启动前端
echo "[5/5] 启动前端..."
cd ../frontend
if [ ! -d node_modules ]; then
    npm install
    echo "  前端依赖已安装"
fi

npx vite --port 5173 &
FRONTEND_PID=$!
echo "  前端 PID: $FRONTEND_PID"

echo ""
echo "=========================================="
echo "  ✅ AutoLearning 已启动"
echo "=========================================="
echo "  前端: http://localhost:5173"
echo "  后端: http://localhost:8000/docs"
echo "  健康: http://localhost:8000/health"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo "=========================================="

# 等待信号
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; cd infra && docker compose down; exit 0" INT TERM
wait
