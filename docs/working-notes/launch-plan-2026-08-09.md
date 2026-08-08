# 上线计划：部署形态、Turso 双备份、日志追踪选型（2026-08-09）

> 性质：内部备忘（`docs/working-notes/` 屏蔽出构建）。目标：**尽快跑通上线逻辑**——服务部署到云上可用、数据每日自动抓取、基础功能可用、无生产级严重 bug。本文给出部署形态、数据双备份（Turso）、日志/错误追踪（Sentry）三项选型与任务清单、工时评估。

## 1. 上线目标与现状盘点

### 1.1 目标

- 后端 API + 前端工具站部署到云上，公网可用；
- 每日自动抓取（基金净值 / 市场温度 / 自选行情）不依赖本机；
- 核心功能（记账、探市、温度计、自选）可用；
- 接口日常健壮性：错误可追踪、日志可查、数据有备份。

### 1.2 现状（2026-08-09 实证）

| 项 | 现状 | 缺口 |
|:---|:---|:---|
| 后端 API | `backend/app`（APIFlask + SQLite WAL），本地 :8000 可用 | **无生产 WSGI 服务器配置、无容器化**（现有 `backend/Dockerfile` 是 V1 遗留：`fundmate/`、webpack、supervisord 均已退役，不可用） |
| 前端 | `frontend/`（Vue3 + pure-admin），Vite 构建（base 由 `VITE_PUBLIC_PATH` 控制） | 有可用 `frontend/Dockerfile`（nginx）；部署形态未定 |
| 登录鉴权 | Supabase Auth + 后端 JWT 白名单中间件 | 生产需 Supabase 项目 env 配置 |
| 数据 | 本地 SQLite `invest.db`（权威） | **无异地备份**；每日抓取依赖本机定时任务 |
| 抓取任务 | `pdm run sync --all` / `grab.*` / 温度计 | 无云端定时调度 |
| 日志 | loguru 本地输出 | 无集中日志、无错误追踪 |
| 环境变量 | `backend/.env.example` 仅 CORS/FLASK_DEBUG | 生产 env 清单缺失 |
| 测试 | 573 passed（单进程全量） | — |
| 部署文档 | `docs/ops/deployment.md` 只规划静态三站（Vercel） | **后端 API 部署完全空白** |

## 2. 部署形态建议（待用户拍板）

### 方案 A：单台云主机（推荐，成本最低）

- **形态**：一台 Linux 云服务器（2C4G 起步，如腾讯云轻量 ~60-100 元/年），Docker Compose 或裸进程跑后端；
- **后端**：`waitress`（纯 Python WSGI，个人项目够用）或 `gunicorn` 单 worker + 前贴 nginx 反代；
- **前端**：静态产物（`dist`）由同一台 nginx 托管（`/app` 路径，与部署文档的路径拆分一致）；
- **定时抓取**：宿主 cron（或容器内 supervisord/cron）每日 `pdm run sync --all` + 温度计 job；
- **备份**：每日快照导出本地 DB 文件 + 可选上传对象存储（见 §3）。

### 方案 B：Vercel（静态三站）+ 云主机（仅后端）

- 三站（主站/工具站/文档站）按 `docs/ops/deployment.md` 走 Vercel；
- 后端仍须一台云主机常驻（SQLite 文件需要持久盘，Serverless 不适用）。

### 方案 C：Supabase Edge / 全托管

- 不适合：SQLite 文件 + 长驻抓取任务，Serverless 函数式平台（Vercel/Cloudflare）均不满足；
- **结论：后端必须一台常驻云主机，方案 A 为最优起点。**

### 2.1 后端生产依赖缺口（需补）

- `waitress`（或 gunicorn）——生产 WSGI 服务器（当前依赖里只有 uvicorn，且是 ASGI，与 Flask/APIFlask 不匹配）；
- 新写 V2 `backend/Dockerfile`（替换 V1 遗留文件，仅构建 V2 代码）；
- 生产 env 清单：`DATABASE_URL`、`CORS_ORIGINS`、`FLASK_DEBUG=0`、`SUPABASE_URL`、`SUPABASE_ANON_KEY`、`SUPABASE_JWT_SECRET`（如适用）、`REALTIME_QUOTES_ENABLED`、Sentry DSN（§4）。

## 3. Turso 双备份方案（调研实证，2026-08-09）

### 3.1 用户诉求

> 全量历史数据在写入时同步到未来的云数据库（如 Turso 可双备份）。

### 3.2 调研结论（实证）

| 方案 | 能力 | 限制 | 适配度 |
|:---|:---|:---|:---|
| **sqlalchemy-libsql**（官方 SQLAlchemy dialect，0.2.0） | `sqlite+libsql:///embedded.db` + `sync_url`+`auth_token` 即得 **Embedded Replica**：本地读、写转发云端主库并回映 | **仅支持 Linux/macOS（Windows 不支持）**；标注 experimental（非生产级）；用户本机是 Windows | 方向反了：embedded replica 是「云端权威 + 本地缓存」，本项目是「本地权威 + 云端备份」，且本机 Windows 无法直接开发验证 |
| **libsql Python 包**（底层驱动） | `libsql.connect('local.db', sync_url=..., auth_token=...)`，sqlite3 兼容 API，可设 `sync_interval` 定时同步 | Windows 支持存疑（需实测）；仍需换驱动层 | 同 sqlalchemy-libsql |
| **pyturso / turso.sync**（2026 官方新推荐） | **local-first：本地读写 + 显式 `push()`/`pull()` 双向同步**，MVCC 并发写 | 较新，SQLAlchemy 集成成熟度待验证；需评估迁移成本 | **语义最贴合**（本地权威 + 云端副本），但属中期工程 |
| **Turso HTTP API / CLI 旁路同步** | 不换主驱动，写后 hook 或定时把增量同步到 Turso | 需自研同步逻辑（表结构映射、冲突处理） | 工作量可控，风险最低，可先落地 |

### 3.3 推荐路径（分两步，均不阻塞上线）

1. **一期（上线，1-2 天内可交付）**：**旁路快照备份**——扩展现有「DB 快照导入层」设计为双向：
   - 每日定时 `snapshot` 导出本地 DB → 上传 Turso（单文件或分表批量导入）；
   - 依赖 Turso 免费档：100 库 / 5GB / 3GB 月同步 / 1 天 PITR（净值全量 868MB 量级超免费档，但**自选+持仓池**远小于此；市场域大表可后续优化）。
   - 或更轻：每日快照上传对象存储（腾讯云 COS 免费额度），Turso 作长期演进。
2. **二期（中期）**：评估 **pyturso / turso.sync** 换主驱动做真「双备份」（本地权威 + 云端副本，写后自动 push）；前提：Linux 生产机验证通过 + SQLAlchemy 集成实测 + Windows 开发机保留标准 sqlite 驱动（按 env 切换）。
   - **注意**：sqlalchemy-libsql 官方标注 experimental + 仅 Linux/macOS，**不建议直接替换主驱动**（本机 Windows 开发与生产一致性都会被破坏）。

### 3.4 隐私边界（沿用 D3 决策）

- 市场域数据（净值/指数/温度计/自选种子）上云无隐私问题；
- 用户私有账本（positions/transactions）**不进入 Turso**，云端权威仍走 Supabase（RLS 兜底）——Turso 只做市场域快照备份。

## 4. 日志 / 错误追踪选型（Sentry 实证）

### 4.1 结论：**Sentry 免费 Developer 计划（$0）**，不引入自托管

| 项 | 实证 |
|:---|:---|
| 免费档 | **5,000 errors/月、1 用户、30 天留存**，个人项目足够（2026-07 多源实证） |
| 后端集成 | `sentry-sdk[flask]` + **官方 LoguruIntegration**（sentry-sdk ≥ 1.23 内置）：loguru `ERROR` 级自动上报为 event、`INFO` 作 breadcrumb、`enable_logs=True` 收 Sentry Logs——与项目现有 loguru 体系零改造对接 |
| 前端集成 | `@sentry/vue` + Vite sourcemap 上传，捕获前端异常 |
| 隐私 | 私有数据不进 Sentry：`before_send` 过滤（金额/代码/用户标识），沿用「私有数据永不外泄」守则 |
| 替代方案 | 自托管 Sentry（Docker 全家桶，运维重）、GlitchTip（轻量但自托管仍需一台机器）；个人项目免费 SaaS 档最省心 |

### 4.2 集成点（估算工时 0.5-1d）

- 后端：`pyproject.toml` 加 `sentry-sdk[flask]`；`app/main.py` 的 `create_app()` 内按 env `SENTRY_DSN` 条件初始化 + `LoguruIntegration` + `before_send` 脱敏；
- 前端：`pnpm add @sentry/vue`，`main.ts` 条件初始化（env `VITE_SENTRY_DSN`）+ sourcemap 上传配置。

## 5. 任务清单与工时评估

### M0 上线阻塞（目标：1-2 周内公网可用）

| # | 任务 | 工时 | 依赖 |
|:---|:---|:---|:---|
| 1 | 后端生产依赖与启动：加 `waitress`；`pdm run serve --prod` 入口（127.0.0.1:8000 + gunicorn/waitress） | 0.5d | — |
| 2 | 重写 V2 `backend/Dockerfile`（仅 V2 代码，删除 V1 遗留 build 段） | 0.5d | 1 |
| 3 | 生产 env 清单落档（`.env.production.example`）+ Supabase 生产项目配置核对 | 0.5d | — |
| 4 | 前端构建部署：`VITE_PUBLIC_PATH=/app` 生产构建 + nginx 静态托管（同机或 Vercel） | 0.5d | — |
| 5 | 云主机初始化（安全组/域名/DNS/HTTPS 证书，nginx 反代 /api → :8000） | 1d | 1-4 |
| 6 | 每日定时抓取：宿主 cron 每日 `sync --all` + 温度计 + 净值增量（首日全量） | 0.5d | 1 |
| 7 | **上线冒烟验证**：登录/记账/探市/温度计/自选五条主链路 + `health` + 错误信封 | 0.5d | 5-6 |
| 8 | **M0 验收**：连续 2-3 天定时抓取稳定、无生产级严重 bug | 观察期 | 6-7 |

**M0 小计：约 4.5d + 观察期**

### M1 健壮性（上线后立即跟进）

| # | 任务 | 工时 | 依赖 |
|:---|:---|:---|:---|
| 9 | Sentry 接入（后端 loguru + 前端 vue + 脱敏） | 1d | 3 |
| 10 | DB 快照每日导出 + 上传对象存储 / Turso（一期备份） | 1d | 6 |
| 11 | `--full-sync` 范围强制校验落地（#825 清单项 2） | 0.5d | — |
| 12 | 生产告警：Sentry 事件阈值 + cron 抓取失败通知（邮件/Webhook） | 0.5d | 9 |
| 13 | 接口耗时慢查询排查（如净值大表分页、温度计聚合） | 1d | — |

**M1 小计：约 4d**

### M2 中期（可选演进，与上线解耦）

| # | 任务 | 工时 | 依赖 |
|:---|:---|:---|:---|
| 14 | pyturso/turso.sync 真双备份 POC（Linux 验证 + SQLAlchemy 集成实测 + 数据迁移） | 2-3d | 10 |
| 15 | 按需回填 + T 日净值 + sync 职责梳理（#824） | 2d | — |
| 16 | OCR + 通用用量表（#823） | 2-3d | — |
| 17 | DB 下载导入层完整落地（#825 清单其余项） | 1.5d | 10 |
| 18 | 探市登录态感知（#822） | 1d | — |

**M2 小计：约 9-11d（按用户优先级分批）**

### 风险与回滚

- 换 Turso 主驱动（二期）：高风险，**必须** Linux 实测 + 全量测试通过后灰度；回滚 = env 切回 `sqlite:///`（`DATABASE_URL` 已支持）；
- 云主机到期/故障：本地 `invest.db` 仍为权威，快照可恢复；DB 文件即回滚资产；
- 抓取接口变动（如东财又废接口）：已有 requests_patch + 适配器隔离层，改适配器即可，不影响 API 契约。

## 6. 待用户拍板事项

1. **云主机选型**：方案 A（单机 nginx+后端+前端，推荐）还是方案 B（Vercel 三站 + 云主机后端）？
2. **备份一期**：每日快照上传对象存储（轻）还是直接进 Turso（演进铺垫）？
3. **Sentry**：确认使用 Sentry SaaS 免费档（需要用户注册获取 DSN）？
4. **M2 优先级**：真双备份 POC（#14）还是按需回填（#15）优先？

## 变更记录

- 2026-08-09：初版（含 Turso/Sentry 调研实证、部署形态三案对比、M0-M2 任务与工时）。
