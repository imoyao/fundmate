# 多多贝

> 个人投资记账与家庭资产管理平台 · 看见你的复利曲线

**多多贝**（代码仓库 `fundmate`）是一个自托管的投资记账与分析平台：把手动归集的基金 / 股票交易记成账本，用确定性代码算出收益、风险与持仓穿透，再把这些能力封装成一组**只读工具**，交给内置 Agent 循环或外部 MCP 客户端调用。

它的核心边界只有一句话：**数值由代码算，模型只负责选工具和组织表达**。任何时候模型都不能自己编一个收益率。

## 它做什么

| 能力 | 说明 |
| --- | --- |
| 记账归集 | 多账户 / 多平台手动流水归集，快照与流水双轨记账，支持 Excel / CSV 导入与去重 |
| 收益计算 | 资金加权 XIRR、成本口径收益、时间加权对照；区分场内场外与不同计费口径 |
| 收益归因 | 组合与基准对比、同类分位、归因拆解，回答「这段时间的钱是哪来的」 |
| 持仓穿透 | 基金 → 持仓标的 → 标的历史估值逐层穿透，按申万一级行业归类看集中度 |
| 市场温度 | 近 1 / 3 / 5 / 10 年 PE 分位打分，乖离率与行业拥挤度辅助判断 |
| 行为画像 | 从流水反推买卖时点与持有期，回答「卖早了少赚多少」这类只能用流水回答的问题 |
| 自选跟踪 | 自选组合当日盈亏、净值变动与到价提醒 |
| AI 记账 | 截图 / 自然语言 → 交易草稿，人工确认后入库，不直接写账 |
| Agent 工具层 | 9 个只读工具（内置循环与 MCP Server 共用一份 schema）；MCP 客户端反向接入 2 家数据服务 |

## 技术架构

```text
┌────────────── 前端（Vue 3 + Vite + Element Plus）──────────────┐
│  记账 · 资产 · 探市 · 自选 · 账本精灵 · 产品 · 登录            │
└──────────────────────────┬────────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────┴────────────────────────────────────┐
│  API 层（APIFlask）：统一错误信封 · 鉴权 · 参数校验 · 分页      │
├───────────────────────────────────────────────────────────────┤
│  领域层（30 个 domain）：positions / performance / insight /   │
│  temperature / strategy / watchlist / entitlements / usage …   │
├───────────────────────────────────────────────────────────────┤
│  服务层：收益引擎 · 数据同步 · 导入清洗 · AI 识别 · 通知       │
├───────────────────────────────────────────────────────────────┤
│  Agent 工具层：9 个只读工具 + MCP Server（stdio 传输）         │
│  MCP 客户端（Streamable HTTP）→ 且慢 / Wind 2 家数据服务       │
├───────────────────────────────────────────────────────────────┤
│  数据层：SQLite（默认）/ PostgreSQL / libSQL，多引擎抽象       │
└───────────────────────────────────────────────────────────────┘
```

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.12+ · Flask 3 + APIFlask · SQLAlchemy 2.x · Pydantic 2 · uvicorn · APScheduler · loguru · PyJWT |
| 前端 | Vue 3.5 · TypeScript · Vite · Element Plus · Pinia · Vue Router · ECharts · pure-admin 组件 |
| 数据 | SQLite（默认，`backend/invest.db`）· PostgreSQL · libSQL，统一走 `core/db_factory` 抽象 |
| 金融数据 | akshare · baostock · xalpha；`pyxirr` 算 XIRR，`scipy` 做分位与统计 |
| 文档解析 | pdfplumber · openpyxl · xlrd（对账单与持仓文件导入） |
| AI | `mcp` 2.0（低层 Server）· 自研 Agent 循环，不依赖编排框架 |
| 工程 | PDM · pytest · Playwright · ruff · pre-commit · markdownlint |
| 部署 | Vercel · Cloudflare Pages（应用站），GitHub Actions 27 条工作流 |

## 值得一说的设计

### 工具层：一份 schema，两个方向

9 个工具（资产总览 / 组合收益 / 持仓盈亏 / 交易行为 / 基准对比 / 收益归因 / 基金净值 / 市场温度 / 自选总览）的元数据只有一份 `TOOLS_METADATA`，内置 Agent 循环与 MCP Server 都从它读取——**改一处，两个出口同时生效**，不存在「网页能问、MCP 不能问」的分叉。

**服务端方向**走 stdio 传输，用 `mcp` 2.0 的低层 `Server` + 构造器回调（该版本已移除装饰器与内置 FastMCP），`on_list_tools` / `on_call_tool` 直连适配层，中间不放业务逻辑。启动时主动 `chdir` 锚回 `backend/`——stdio server 由客户端以任意工作目录拉起，不锚回会连到「另一个空库」，表现为数据隐身。

**客户端方向**是反过来的：`backend/app/services/mcp/` 手写了一套 Streamable HTTP 客户端（10 个模块约 1500 行），接入且慢与 Wind 两家数据服务共 9 个工具。不套官方 `mcp` SDK 是形态错配——SDK 2.0 的 `Client` 只有 async，而本仓是全同步批处理（23 个模块用 `requests`，夜跑 111 只组合）；SDK 也替不掉 8 类错误分类、`mcp_call_logs` 审计、`DataScope` 分级 Token 路由这些业务层。迁移触发条件与协议世代判断见 [`docs/dev/mcp-integration.md` §13](docs/dev/mcp-integration.md)。

客户端要处理的坑都不在协议表面：`Mcp-Session-Id` 缓存复用（连续调用只握手一次，会话失效才重握）；SSE 响应不能用 `resp.text` 读——无 charset 会被猜成 ISO-8859-1，`0x85` 续字节被当换行，把 JSON 从汉字中间折断；400 有两种语义，能解析出 JSON-RPC error 就不重握（重握无意义）；每次调用落一行审计，敏感头脱敏。

### 归属字段不进模型参数通道

「查哪个家庭、哪个账户」这类归属信息一旦做成工具参数，模型就有机会填错或被诱导填成别人的。这里的做法是：**归属字段只由服务端上下文决定**——`family_id` 来自本机环境变量，客户端传什么都会被 `apply_server_context` 覆盖。

用户私有数据强制走用户级 Token，缺失即失败，**不回退到系统 Token**。宁可报错，不给出一个「看起来正常」的错误答案。

### 护栏是四层，不是一层

| 层 | 拦什么 | 位置 |
| --- | --- | --- |
| 接口限流 | 每用户每分钟调用次数，防刷接口 | 进模型之前 |
| 连续失败熔断 | 连续失败 N 次后冷却，防「失败返还 → 无限重试 → token 空耗」 | 进模型之前 |
| 全站 token 预算 | 当日累计上限，超限全站熔断 | 进模型之前 |
| 多轮收敛上限 | `turn_count` 落库，重启不丢、多实例一致 | 循环内 |

再叠三道内容安全：输入侧意图分类（越界提问**零模型调用**直接拦）、输出侧逐句扫描、重复步骤检测。**准入拦截放在最便宜的位置，才有意义。**

### 上下文压缩：先有界，再谈质量

多轮对话的压缩策略不是「尽量摘要」，而是分出三个阈值：

- `turn_count > 6` 才允许压缩（早期压缩得不偿失）
- 原文超过 8 条触发一次压缩（摊薄调用成本）
- 压缩失败时降级到原文硬上限 12 条，单侧截断 800 字符

三级是有意为之：**只截断会丢长程诉求**（表现为反复追问同一件事），**只摘要会丢最近细节**。关键信息卡单独序列化，上限同样 800 字符。目标先是有界，其次才是压缩质量。

### 45 条回归评估集

`backend/tests/agent_eval/cases.yaml` 把「问什么 → 期望调哪个工具」固化成 45 条用例：20 条基础意图、2 条跨工具串联、12 条归因 / 基准 / 行为、3 条跨工具混淆、8 条对抗（越狱 / 缺参 / 幻觉诱饵 / 提示注入）。

配套 `scripts/agent_eval.py` 跑批并落 trace：每次工具调用记录入参、出参、耗时、错误码与 token 消耗（敏感参数脱敏），失败链路可以按会话回放到具体一步。

这套东西解决的是一个具体问题：**工具从 6 个扩到 9 个之后，模型开始把「组合总共赚了多少」错选成「资产总览」**。根因不是模型退化，而是老工具描述缺少排他边界句——新工具都写了「何时用 / 何时不用」，老工具没写。**工具变多，放大的正是旧描述的模糊性。**

### 数据源：模拟 TLS 指纹，而不是加请求头

东方财富按 TLS 指纹（JA3）掐掉 Python 裸请求。表现为浏览器能开、Python 第一次请求就持久性 `RemoteDisconnected`，加 UA / Referer 无效——**靠请求头治不了，必须让握手本身看起来像浏览器**。

`core/requests_patch.py` 在应用启动时把全进程的 `requests` / `akshare` 调用路由到「浏览器头 + 连接复用」会话，装有 `curl_cffi` 时进一步 `impersonate='chrome'`。一处安装，所有数据源调用点自动受益，不再逐处打补丁。

### 运行期守卫：把「偶发」变成「可解释」

几个不显眼、但决定系统会不会「半夜自己坏」的守卫：

| 模块 | 拦的是什么 |
| --- | --- |
| `v8_guard` | `py_mini_racer` 内嵌 V8 的 isolate 并发构造竞态——上游锁只覆盖 DLL 初始化、未覆盖 isolate 创建，两个线程同时穿过 check-then-act 会让第二个直接崩进程 |
| `instance_guard` | 同一 SQLite 库的单实例闸门。Windows 的 `SO_REUSEADDR` 语义让第二个实例照样绑定成功，「重启后端」会静默变成「又多起一个」，最终表现为一堆 `database is locked` |
| `schema_drift` | 只读探查表结构漂到哪、属于哪类修复（可 `ALTER` 补列，还是必须重建表），自身不执行任何 DDL |
| `cold_set_guard` | 冷集行数膨胀监测——防「反复小批量灌」把已清理的历史数据一点点灌回来；这类问题不报错、不失败、也没人投诉 |
| `venues` | 场内 / 场外编码规则单一真相源：场内 `{MARKET}{CODE6}`、场外裸码，禁止各模块自行拼前缀或猜交易所 |

## 演进路线

| 阶段 | 时间 | 做了什么 |
| --- | --- | --- |
| 记账内核 | 2026-05 | 流水 + 快照双轨记账，先把「账对不对」跑通 |
| 分析能力 | 2026-07 | 探市页面、市场温度计、乖离率，从「记下来」到「看得懂」 |
| V2 分层重构 | 2026-08-01 | V1 退役，代码收进 `backend/app/`；领域 / 服务 / 核心三层分离，错误信封契约统一 |
| 数据同步加固 | 2026-08 | TLS 指纹补丁、多源适配、失败重试与降级，让外部数据源从「偶发失败」变「可预期」 |
| AI 识别域 | 2026-08-13 | 截图 / 文本 → 交易草稿，自选与持仓双场景共用一套反查与消歧 |
| Agent 循环 | 2026-08-18 | 账本精灵对话：模型选工具、代码算数值，护栏与上下文压缩同步落地 |
| 评估体系 | 2026-09 → 10 | 30 条评估集 + trace 回放；10 月扩到 45 条并修掉跑批的重试与清理缺陷 |

这条线的走向很明确：**从「一个记账工具」长成「一套可被调用的投资分析能力」**。前三个阶段解决数据准确，第四、五个阶段解决「谁能用」，最后两个阶段解决「怎么证明它没变差」。

## 工程质量

| 指标 | 现状 |
| --- | --- |
| 提交 | 3606 次（2026-05-07 起） |
| 后端模块 | 407 个 Python 文件，30 个业务域 |
| 测试 | 367 个测试文件（pytest），另有 Playwright e2e |
| CI | 27 条 GitHub Actions 工作流（含守卫类：PR 四问、路径重叠、依赖锁同步等） |
| 静态检查 | ruff（lint + format）、pre-commit、markdownlint |
| 文档 | `docs/spec/` 29 篇规格与决策记录，`docs/ops/` 部署与运维手册 |

## 目录结构

仅列关键目录，完整结构以文件系统为准。

```text
fundmate/
├─ backend/
│  ├─ app/
│  │  ├─ core/        # 配置、数据库、鉴权、守卫、异常、时间与交易日历
│  │  ├─ domains/     # 30 个业务域：资产、组合、交易、收益、洞察、市场…
│  │  ├─ services/    # 收益引擎、数据同步、导入、AI 识别（含 Agent 与 MCP）
│  │  ├─ models/      # SQLAlchemy 模型
│  │  └─ main.py      # 应用入口
│  ├─ tests/          # pytest；agent_eval/ 为 Agent 回归评估集
│  └─ scripts/        # 跑批、诊断、数据修复脚本
├─ frontend/          # Vue 3 + Vite（记账、资产、探市、自选、账本精灵）
├─ docs/
│  ├─ spec/           # 需求规格与开发规范（入口 docs/spec/index.md）
│  ├─ ops/            # 部署与运维
│  └─ design/         # 交互与视觉规范
├─ scripts/           # 工程脚本（V1 引用守卫、本地启动）
└─ README.md
```

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

### 开发任务集合（invoke + rich，推荐）

日常开发指令（抓取 / 测试 / 启动 / 文档）已统一封装到 `backend/tasks.py`，用 [invoke](https://www.pyinvoke.org/) + [rich](https://github.com/Textualize/rich) 提供美化输出与单一入口，避免指令散落在命令行记忆里。依赖 `invoke`、`rich` 已加入 dev 依赖组（`pdm install -G dev`）。

```bash
cd backend
pdm run invoke --list              # 列出全部任务
pdm run invoke grab.temperature    # 市场温度同步（乖离率跳过）
pdm run invoke grab.all            # 全部同步任务
pdm run invoke grab.job fund_nav   # 透传跑单个 Job
pdm run invoke grab.verify-jisilu  # 只读诊断：jisilu_indicator 是否含 level
pdm run invoke test                # 跑全部后端测试
pdm run invoke test --path tests/services   # 限定目录
pdm run invoke test --path tests/services/foo.py --k test_x  # 限定用例（-k）
pdm run invoke serve               # 启动 API（flask dev server，默认 :8000，热重载）
pdm run invoke docs.dev            # 本地文档预览（需 frontend 依赖已装）
pdm run invoke help                # 打印任务速查表
```

> 抓取 / 验证类任务直接复用 `app/tools/sync_cli.py`，保证单一事实来源；`tasks.py` 不重复实现业务逻辑。Windows 终端为 GBK 编码时 rich 输出偶发乱码但不影响命令执行（符号已规避非 ASCII）。

前端：

```bash
cd frontend
pnpm install                     # 首次或依赖变更时
pnpm dev
```

### 运行 Agent 工具层

内置 Agent 循环随 Web 服务提供；需要把工具暴露给外部 MCP 客户端（Cursor / Claude Desktop 等）时，单独起 stdio server：

```bash
cd backend
pdm run agent-mcp                # = python -m app.services.ai_recognizer.mcp_server
```

归属家庭由环境变量 `FUNDMATE_MCP_FAMILY_ID` 决定（缺省 `1`），客户端无法覆盖。

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

- 规格与开发规范：`docs/spec/index.md`（原根目录 `SPEC.md` 已拆分为多文件体系）
- 部署与运维：`docs/ops/deployment.md`
- 交互与视觉：`docs/design/`
- 变更记录：`docs/changelog/`
- 在线文档站：本地 `pdm run invoke docs.dev` 预览

## 授权与使用限制（License）

**本仓库公开可见，但不是开源软件（source-available, noncommercial）。公开可读 ≠ 授权使用。**

本项目自有代码适用根目录 [`LICENSE`](./LICENSE)：**PolyForm Noncommercial License 1.0.0**
（SPDX 标识：`PolyForm-Noncommercial-1.0.0`）。

- **允许**：个人学习、研究、实验、业余项目等**非商业**用途；慈善机构、教育机构、公共研究机构、公共安全/卫生机构、环保机构、政府机构的非商业使用。
- **禁止**：任何**商业用途**——包括但不限于以本项目或其衍生品对外提供付费服务、销售、企业内部经营性使用。
- **商业授权须另行取得书面许可**（联系仓库 owner）。
- 变更与再分发须随附本许可全文或链接、以及 `Required Notice` 声明；**不得再授权（sublicense）**。

边界说明：

- `frontend/LICENSE` 是上游前端模板 [pure-admin](https://github.com/pure-admin) 的 MIT 声明，属**第三方署名**，仅覆盖其原始代码——本项目自有前端代码不因该文件而适用 MIT。
- 第三方依赖（akshare、Element Plus、VitePress 等）各自适用其自身许可，不受本文件影响，也不因本文件而改变。
- **时间效力**：2026-09-11 之前发布的版本曾适用 BSD-2-Clause；已按 BSD-2 取得的授权**对当时版本继续有效**，不可追溯撤回（新版本适用上面的非商业许可）。
- 仓库的 public / private 状态与授权无关：**公开只代表可见，不构成任何使用许可**；反之切回私有也不会放宽授权。

> 本段为仓库约定说明，不构成法律意见；商业合作请先取得书面授权。
