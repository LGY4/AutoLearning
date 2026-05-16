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
├── backend/          # FastAPI 后端
│   ├── app/
│   │   ├── api/      # 路由与依赖注入
│   │   ├── core/     # 配置、枚举、安全
│   │   ├── models/   # SQLAlchemy ORM 模型
│   │   ├── repositories/  # 数据访问层
│   │   ├── schemas/  # Pydantic 请求/响应模型
│   │   ├── services/ # 业务逻辑（智能体、画像、评分、辅导）
│   │   └── workflows/ # LangGraph 工作流
│   ├── alembic/      # 数据库迁移
│   ├── tests/        # 后端测试
│   └── requirements.txt
├── frontend/         # React 前端
│   └── src/
│       ├── api/      # API 客户端
│       ├── components/ # UI 组件
│       ├── context/  # 全局状态
│       ├── hooks/    # 自定义 Hooks
│       ├── pages/    # 页面
│       └── types/    # TypeScript 类型
├── infra/            # Docker Compose 配置
├── scripts/          # 运维脚本
└── docs/             # 项目文档
```

## 快速开始

### Docker Compose（推荐）

```bash
# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY 等

# 启动
cd infra
docker compose up --build
```

启动后访问：

- 前端：http://localhost:5173
- 后端 API：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 本地开发

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

## 核心功能

- **智能对话**：两阶段意图识别（关键词 + LLM），自动路由到辅导、出题、评估、学习路径等模块
- **学习流程**：LangGraph 多智能体协作流水线（画像构建 → 路径规划 → 资源生成 → 推荐）
- **个性化画像**：四维度评估（掌握度、应用力、记忆度、理解力），每对话独立画像快照
- **智能辅导**：先测后答（quiz-before-answer），根据答题表现动态调整讲解深度
- **多类型资源**：文档、代码案例、思维导图、流程图、视频脚本、测验题目
- **RAG 知识库**：ChromaDB 向量检索，支持知识库导入与重建
- **自适应推荐**：基于画像薄弱点和学习记录的资源推荐策略

## 环境变量

参见 `.env.example`，关键配置：

| 变量 | 说明 |
|------|------|
| `LLM_API_BASE` | LLM API 地址 |
| `LLM_API_KEY` | LLM API 密钥 |
| `LLM_MODEL` | 模型名称 |
| `DATABASE_URL` | PostgreSQL 连接串 |
| `REDIS_URL` | Redis 地址 |
| `EMBEDDING_API_URL` | Embedding 服务地址 |
| `REPOSITORY_BACKEND` | `postgres` 或 `memory` |
| `RAG_BACKEND` | `chroma` 或 `memory` |

## License

[MIT](LICENSE)
