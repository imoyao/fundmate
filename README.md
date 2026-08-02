# 多倍贝

> 个人投资记账与家庭资产管理平台 · 代码仓库：`fundmate`

基于 **Flask（APIFlask）** 与 **Vue 3（pure-admin）** 的前后端分离 Web 应用，用于记录基金 / 股票等投资交易、追踪资产与收益，并内置「市场温度计」等分析工具。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.12+ · Flask + APIFlask · SQLAlchemy 2.x · PDM 管理依赖 |
| 前端 | Vue 3 · TypeScript · Vite · pure-admin |
| 数据 | 本地 SQLite（默认 `backend/invest.db`） |

## 目录结构（仅列关键目录）

```
fundmate/
├─ backend/      # 后端服务；V2 代码在 backend/app/（V1 已退役，备份于 .backup-v1-2026-08-01/）
├─ frontend/     # 前端应用（Vue 3 + Vite）
├─ docs/
│  └─ spec/      # 需求规格与开发规范（多文件体系，入口 docs/spec/index.md）
├─ scripts/      # 工程脚本（含 V1 引用守卫、本地启动脚本）
└─ README.md
```

> 完整目录以实际文件系统为准，无需在此穷举。

## 本地开发

### 一键启动（推荐）

项目提供跨平台启动脚本，按你的环境选一个即可——都会同时拉起后端（`:8000`）与前端（`:8848`），按 `Ctrl + C` 一并退出。

**Windows（原生，推荐）**

在文件管理器双击 `dev.cmd`，或在 CMD / PowerShell 中运行：

```cmd
dev.cmd
dev.cmd -Install      # 首次或依赖变更时重装依赖
```

> 若 PowerShell 报「禁止运行脚本」，直接用 `dev.cmd` 即可（它已用 `-ExecutionPolicy Bypass` 绕过执行策略）；或先执行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`。

**Git Bash / WSL / Linux / macOS**

```bash
./scripts/dev.sh
./scripts/dev.sh --install
```

启动后访问：

- 前端页面：<http://localhost:8848>
- 后端 API 文档（Swagger UI）：<http://localhost:8000/docs>

### 手动启动

后端：

```bash
cd backend
pdm install                      # 首次或依赖变更时
pdm run flask --app app.main:app run --debug --host 0.0.0.0 --port 8000
```

数据同步：
```bash
pdm run python app/tools/sync_metadata.py --job temperature
# 或者
pdm run sync --all / pdm run sync --job temperature
```

前端：

```bash
cd frontend
pnpm install                     # 首次或依赖变更时
pnpm dev
```


### 环境变量

- 后端读取 `backend/.env`（参考 `backend/.env.example`）。
- 前端开发配置见 `frontend/.env.development`：默认前端端口 `:8848`，并将 `/api` 代理到后端 `:8000`。

## 排错（Troubleshooting）

### 乖离度同步报 `RemoteDisconnected` / 本地连接失败

**根因**：东方财富 WAF 按 TLS 指纹（JA3）掐掉 Python 裸请求。典型表现：浏览器能开东方财富，但 Python 第一次请求就持久性 `RemoteDisconnected`，加 UA/Referer 也无效——靠单纯加请求头治不了，必须模拟浏览器 TLS 握手。

**已根治（全局生效，零配置零维护）**：`app/__init__.py` 启动时调用 `app/core/requests_patch.py` 的 `install_requests_patch()`，将全进程的 `requests`/`akshare` 调用路由到「浏览器头 + 连接复用」会话；若环境装有 `curl_cffi`（已随依赖安装）则进一步 `impersonate='chrome'` 模拟 Chrome TLS 指纹，根治 JA3 拦截，否则自动降级为 `requests + urllib3` 重试。一处安装，所有 akshare 调用点（bias / thermometer / akshare_adapter 等）自动受益，不再需要逐处打补丁。

**本机验证根治效果**（看裸请求 vs 全局补丁后哪种传输层能连通东财）：

```bash
cd backend
pdm run python scripts/diag_em.py
```

**日常跑乖离度**（含于 temperature 任务）：`pdm run sync --job temperature`

## 文档

完整需求与开发规范见 `docs/spec/index.md`（原根目录 `SPEC.md` 已拆分为多文件体系）。


## License

MIT
