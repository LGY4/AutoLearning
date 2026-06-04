# AutoLearning

基于大模型的个性化学习资源生成与多智能体协作学习系统。

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | React + TypeScript + Vite |
| 后端 | Python + FastAPI + SQLAlchemy + Alembic |
| 数据库 | PostgreSQL + Redis + ChromaDB |
| LLM | OpenAI-compatible API（DeepSeek / OpenAI / Ollama / vLLM） |
| 异步 | Celery + Redis |
| 部署 | Docker Compose |

## 项目结构

```
AutoLearning/
├── backend/              # FastAPI 后端
│   ├── app/
│   │   ├── api/          # 路由与依赖注入
│   │   ├── core/         # 配置、枚举、安全
│   │   ├── repositories/ # 数据访问层
│   │   ├── schemas/      # Pydantic 请求/响应模型
│   │   ├── services/     # 业务逻辑（智能体、画像、评分、辅导）
│   │   └── workflows/    # LangGraph 工作流
│   ├── alembic/          # 数据库迁移
│   ├── tests/            # 后端测试
│   └── requirements.txt
├── frontend/             # React 前端
│   └── src/
│       ├── api/          # API 客户端
│       ├── components/   # UI 组件（含 7 个 inline 面板）
│       ├── context/      # 全局状态
│       ├── hooks/        # 自定义 Hooks
│       ├── pages/        # 页面
│       └── types/        # TypeScript 类型
├── infra/                # Docker Compose 配置
├── deploy/               # 部署脚本和配置
├── scripts/              # 运维脚本
├── docs/                 # 项目文档
├── start.sh              # Linux/macOS 一键启动
├── start.ps1             # Windows 一键启动
├── .env.example          # 环境变量模板
└── README.md
```

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/LGY4/AutoLearning.git
cd AutoLearning

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY（DeepSeek/OpenAI 等）

# 3. 启动所有服务
cd infra
docker compose up --build

# 4. 访问
# 前端: http://localhost:5173
# 后端 API: http://localhost:8000/docs
# 健康检查: http://localhost:8000/health
```

### 方式二：一键启动（本地开发）

**Linux / macOS / WSL:**
```bash
chmod +x start.sh
./start.sh
```

**Windows PowerShell:**
```powershell
.\start.ps1
```

脚本会自动：
- 检查并创建 `.env`
- 启动 PostgreSQL + Redis（Docker）
- 创建 Python 虚拟环境并安装依赖
- 运行数据库迁移和种子数据
- 启动后端和前端

### 方式三：手动启动（本地开发）

**后端：**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python -m app.ops.seed_demo_data
uvicorn app.main:app --reload --port 8000
```

**前端：**
```bash
cd frontend
npm install
npm run dev
```

## 云端部署（腾讯云）

### 前置条件

- 腾讯云 CVM 实例（Ubuntu 22.04+, 推荐 4C8G+）
- 安全组开放端口：80, 443, 8000, 5173
- 域名（可选，用于 HTTPS）

### 一键部署

```bash
# SSH 登录服务器
ssh root@your-server-ip

# 下载并运行部署脚本
curl -fsSL https://raw.githubusercontent.com/LGY4/AutoLearning/main/deploy/tencent-cloud.sh | bash

# 或指定域名（自动配置 Nginx + HTTPS）
curl -fsSL https://raw.githubusercontent.com/LGY4/AutoLearning/main/deploy/tencent-cloud.sh | bash -s -- your-domain.com
```

### 手动部署

```bash
# 1. 安装 Docker
curl -fsSL https://get.docker.com | sh

# 2. 克隆项目
git clone https://github.com/LGY4/AutoLearning.git /opt/autolearning
cd /opt/autolearning

# 3. 配置环境变量
cp .env.example .env
nano .env  # 填入 LLM_API_KEY

# 4. 启动（生产模式）
cd infra
docker compose -f docker-compose.yml -f ../deploy/docker-compose.prod.yml up -d --build

# 5. 查看日志
docker compose logs -f
```

### 更新部署

```bash
cd /opt/autolearning
git pull origin main
cd infra
docker compose up -d --build
```

## 核心功能

### 智能对话（14 种意图）

| 意图 | 触发词示例 | 功能 |
|------|-----------|------|
| tutoring | "什么是快速排序" | 辅导问答 + 自适应测验 |
| practice | "帮我出几道题" | 练习刷题 + 即时评分 |
| resource_generation | "生成思维导图" | 生成 8 种类型资源 |
| learning_path | "规划学习路径" | 知识图谱 + 路径规划 |
| assessment | "评估一下我的学习" | 四维度学习评估 |
| dashboard | "看看学习情况" | 学习看板 + 雷达图 |
| learning_map | "展示学习地图" | 知识图谱可视化 |
| analytics | "学习分析" | 趋势图 + 效率指标 |
| video_generation | "生成视频" | 教学视频生成 |
| media_generation | "生成动画" | 动画/图片生成 |
| resource_browse | "浏览资源" | 资源库浏览 |
| course_goal | "设定目标" | 课程目标管理 |
| general_chat | "你好" | 自由对话 |

### 个性化学习闭环

```
登录 → 欢迎面板（今日建议、薄弱点、连续天数）
  → 快捷操作 → 练习/对话/资源生成
    → 学习总结（正确率、等级评价、建议）
      → 画像更新 → 推荐刷新 → 路径解锁
        → 下次登录 → 欢迎面板反映最新状态
```

### 四维度画像模型

每个知识点独立评估 4 个维度：
- **掌握度 (mastery)**: 是否理解概念
- **应用力 (application)**: 是否能实际运用
- **记忆度 (memory)**: 是否能长期记忆
- **理解力 (understanding)**: 是否理解原理

81 种组合（3×3×3×3）映射到不同教学策略。

## 环境变量

参见 `.env.example`，关键配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_BASE` | LLM API 地址 | `https://api.deepseek.com/v1` |
| `LLM_API_KEY` | LLM API 密钥 | 必填 |
| `LLM_MODEL` | 模型名称 | `deepseek-chat` |
| `LLM_TIMEOUT_SECONDS` | LLM 超时时间 | `300` |
| `DATABASE_URL` | PostgreSQL 连接串 | 见 .env.example |
| `REDIS_URL` | Redis 地址 | `redis://localhost:6379/0` |
| `REPOSITORY_BACKEND` | 存储后端 | `postgres` |
| `EMBEDDING_PROVIDER` | Embedding 提供商 | `local` |

## 测试

```bash
# 前端单元测试
cd frontend
npm test

# 后端测试
cd backend
pytest
```

## License

[MIT](LICENSE)
