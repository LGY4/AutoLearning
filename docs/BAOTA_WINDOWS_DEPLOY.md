# AutoLearning 宝塔 Windows 面板部署

适用场景：Windows Server + 宝塔 Windows 面板 + Nginx。当前服务器 IP 可按 `159.75.71.163` 配置，后端默认只监听本机 `127.0.0.1:8000`，公网只开放站点的 `80/443`。

## 1. 前置条件

- 宝塔安全组/系统防火墙放行 `80`、`443`。
- 宝塔软件商店安装 Nginx。
- 服务器安装 Git、Python 3.10+、Node.js 18+。
- 生产稳定模式需要 PostgreSQL 和 Redis，并在 `backend\.env` 配置 `DATABASE_URL`、`REDIS_URL`。
- 必填模型密钥：`LLM_API_KEY`。不要把密钥提交到 Git，也不要发在聊天记录里。

如果只是先做连通性验证，可用脚本的 `-UseMemoryBackend` 临时跳过 PostgreSQL/Redis；这不是生产稳定方案，重启后业务数据不会持久化。

## 2. 执行部署脚本

在服务器上用管理员 PowerShell 执行：

```powershell
New-Item -ItemType Directory -Path C:\Temp -Force
Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/LGY4/AutoLearning/main/deploy/baota-windows-deploy.ps1 -OutFile C:\Temp\baota-windows-deploy.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Temp\baota-windows-deploy.ps1 -PublicOrigin http://159.75.71.163
```

首次运行时，如果 `backend\.env` 里还没有真实 `LLM_API_KEY`，脚本会停下。编辑：

```text
C:\www\wwwroot\AutoLearning\backend\.env
```

至少确认：

```env
ENVIRONMENT=production
HOST=127.0.0.1
PORT=8000
CORS_ORIGINS=http://159.75.71.163
LLM_API_KEY=你的模型服务密钥
DATABASE_URL=postgresql+psycopg://用户名:密码@127.0.0.1:5432/autolearning
REDIS_URL=redis://127.0.0.1:6379/0
REPOSITORY_BACKEND=postgres
RAG_BACKEND=chroma
```

然后再次运行同一条部署命令。脚本会：

- clone/pull 最新项目代码到 `C:\www\wwwroot\AutoLearning`；
- 创建 `backend\.venv` 并安装依赖；
- 执行数据库迁移、种子数据和治理型知识库导入；
- 执行 `frontend\npm ci` 和 `npm run build`；
- 创建后端启动循环脚本；
- 注册并启动 Windows 计划任务 `AutoLearning-API`。

需要 Celery 异步 Worker 时追加 `-EnableWorker`：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Temp\baota-windows-deploy.ps1 -PublicOrigin http://159.75.71.163 -EnableWorker
```

## 3. 配置宝塔站点

在宝塔面板中新建站点：

- 域名/IP：`159.75.71.163` 或已解析的域名；
- 站点目录：`C:\www\wwwroot\AutoLearning\frontend\dist`；
- Web 服务：Nginx。

进入站点配置文件，参考：

```text
C:\www\wwwroot\AutoLearning\deploy\baota-nginx-autolearning.conf.example
```

关键规则是：

- `/api/` 反向代理到 `http://127.0.0.1:8000`；
- `/static/` 反向代理到 `http://127.0.0.1:8000`；
- 前端路由使用 `try_files $uri $uri/ /index.html`。

改完后重载 Nginx。

## 4. 验证

在服务器 PowerShell 验证后端：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/readyz
```

在本机浏览器验证：

```text
http://159.75.71.163/
```

如果访问失败，优先检查：

- 腾讯云安全组是否放行 `80/443`；
- Windows 防火墙是否放行 Nginx；
- 宝塔站点目录是否指向 `frontend\dist`；
- Nginx 配置是否保留 `/api/` 和 `/static/` 代理；
- 后端日志：`C:\www\wwwroot\AutoLearning\logs\api.log`。

## 5. 更新项目

后续更新代码后，在服务器重新执行部署脚本即可。脚本会 `git pull --ff-only origin main`、重装缺失依赖、重新构建前端，并重启/保活后端计划任务。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Temp\baota-windows-deploy.ps1 -PublicOrigin http://159.75.71.163
```
