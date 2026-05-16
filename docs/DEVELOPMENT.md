# 开发说明

## 技术基线

本项目严格遵守 `统一技术基线.docx`：

- API 前缀统一为 `/api/v1/...`
- 主键统一使用 UUID
- 表名采用单数命名：`app_user`、`student_profile`、`learning_resource`、`agent_task`
- 资源类型：`document`、`mindmap`、`quiz`、`reading`、`video`、`animation`、`code_case`
- Agent 名称：`profile_agent`、`path_agent`、`document_agent`、`quiz_agent`、`mindmap_agent`、`video_agent`、`code_agent`、`quality_agent`、`recommendation_agent`、`tutor_agent`
- 任务状态：`pending`、`running`、`success`、`failed`、`retrying`、`cancelled`、`timeout`
- 学生画像覆盖 `basic_info`、`knowledge_profile`、`learning_goal`、`learning_preference`、`learning_behavior`、`cognitive_profile`、`dynamic_update`

## 主运行环境

Docker Compose 是当前推荐主运行环境：

- `postgres`：主业务数据库
- `redis`：Celery broker/result backend
- `backend`：FastAPI API 服务
- `celery-worker`：异步资源生成任务
- `frontend`：React + Vite
- `minio`：对象存储预留

backend 容器启动时会执行：

```text
等待 PostgreSQL/Redis
→ alembic upgrade head
→ 写入初始化用户、画像、课程、知识点、Prompt 模板
→ 导入 Chroma RAG 知识库
→ 启动 FastAPI
```

worker 容器启动时会等待 PostgreSQL/Redis 后启动 Celery worker。

## 当前垂直闭环

```text
GET  /api/v1/auth/me
POST /api/v1/learning/start
GET  /api/v1/learning/tasks/{workflow_id}
GET  /api/v1/learning/stream/tasks/{workflow_id}
GET  /api/v1/profiles/{user_id}
POST /api/v1/learning-paths/generate
POST /api/v1/resources/generate
POST /api/v1/resources/generate-async
GET  /api/v1/resources/tasks/{celery_task_id}
GET  /api/v1/agent-workflows/{workflow_id}
GET  /api/v1/agent-workflows/{workflow_id}/events
GET  /api/v1/recommendations/{user_id}
POST /api/v1/learning-records
POST /api/v1/tutor/chat
GET  /api/v1/knowledge/status
POST /api/v1/knowledge/rebuild
GET  /api/v1/system/runtime
```

## 环境变量

```text
REPOSITORY_BACKEND=auto | postgres | memory
RAG_BACKEND=auto | chroma | memory
MODEL_PROVIDER=mock | spark
EMBEDDING_PROVIDER=deterministic | http
EMBEDDING_API_URL=
EMBEDDING_ALLOW_FALLBACK=true | false
SPARK_APP_ID=
SPARK_API_KEY=
SPARK_API_SECRET=
SPARK_JSON_RETRIES=2
```

真实星火密钥只允许写入本机 `.env`。`.env.example` 必须保持空占位。

## 验收脚本

- `scripts/validate_baseline.py`：检查技术基线文件、接口、枚举、Docker 与运维入口。
- `scripts/verify_runtime.py`：检查运行态 API、RAG、画像、路径、资源、推荐与反馈闭环。
- `scripts/compose_integration.py`：检查 Docker Compose 下 PostgreSQL、Redis、Celery、Chroma、Alembic 和前端代理。
- `scripts/docker_up.cmd` / `scripts/docker_verify.cmd`：Windows 免执行策略的一键 Docker 启动与运行态验证入口。
- `scripts/spark_smoke.cmd`：星火凭证与 WebSocket 联调入口。
- `backend/tests/test_vertical_loop.py`：覆盖内存兜底垂直闭环、RAG、异步任务兜底。
- `frontend/tests/e2e/product.spec.ts`：Playwright 产品主流程与异常展示回归测试。

## 后续优先级

1. 将 Compose 集成测试纳入固定 CI 流程。
2. 接入真实 embedding 服务并关闭生产环境 fallback。
3. 配置真实星火凭证后运行 `scripts\spark_smoke.cmd` 做 live smoke test。
4. 扩展多学生画像、课程知识点和真实学习记录样本。
5. 为 Playwright 截图建立长期稳定基线。
