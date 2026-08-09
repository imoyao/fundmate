# AGENTS.md

个人投资记账/家庭资产管理平台「多倍贝」（fundmate）。前后端分离：后端 Flask/APIFlask（Python 3.12+），前端 Vue 3 + Vite（pure-admin），另有 VitePress 文档站与静态落地页。仓库文档均为中文，提交信息用中文 + conventional commits。权威规范在 `docs/spec/`（入口 `docs/spec/index.md`；`conventions.md` 为冻结区，变更须先在 `decisions.md` 记决策）。当前开发分支 `main-v2`（`origin/HEAD` 指向 `dev`，其余本地分支为历史遗留）。

## 目录边界

- `backend/` — 后端（PDM 管理）。V2 代码在 `backend/app/`；V1（`backend/fundmate/`）已于 2026-08-01 退役，**禁止新增任何 `backend.fundmate` 引用**（守卫脚本 `scripts/forbid_v1_refs.sh`）。入口 `backend/app/main.py`（工厂 `create_app()`，模块底部 `app = create_app()`）。
- `frontend/` — 工具站（Vue3 + TS + Element Plus + pure-admin，pnpm）。包管理器强制 pnpm（`preinstall: only-allow pnpm`）。
- `docs/` — VitePress 文档站；依赖在**仓库根** `package.json`，命令从仓库根运行。根与 `frontend/` 各有独立 `package.json` + `pnpm-lock.yaml`（互不通用），勿在仓库根装前端依赖或反之。
- 根目录 `package.json` — 只管文档站与落地页，**不是**前端应用。
- 落地页：`landing.template.html` + `landing.content.yml` 由 `scripts/build-landing.mjs` 生成 `landing.html`（还有 about/story）。`site/style.css` + `site/logo.svg` 是主站共享资产必须入库，其余 `/site/*` 忽略。
- `backend/pyproject.toml` 项目名是历史遗留 `showbuy`，勿据此判断包归属。

## 后端架构（`backend/app/`）

- 按领域分包：`domains/<domain>/{models,schemas,views}.py`，每域一个 APIBlueprint，路由在 `views.py`。改模型字段必须同步更新关联 Create/Update/Out Schema（conventions §4.3）。
- `core/`：`database.py`（SQLite + WAL）、`money.py`（单位换算唯一入口）、`constants.py`（`CURRENT_USER_ID` 已随 v4.7 多用户化退役，当前用户从 `g.current_user` 取，勿再引用常量）、`auth.py`（Supabase JWT 验签 + 白名单鉴权中间件，见 D2）、`exceptions.py`（`SBException` + 统一错误信封）、`requests_patch.py`（东财 TLS 补丁实现）。
- `services/`：`sync/`（jobs + adapters，xalpha/akshare 双适配器）、`thermometer/`、`bias/`、`importer/`（CSV/PDF 解析）、`performance/`（XIRR）。
- 同步入口两套、同一 `DataSyncOrchestrator`：`pdm run invoke grab.*` 走 `app/tools/sync_cli.py`；`pdm run sync --job <name>` 走 `app/tools/sync_metadata.py`。
- **日志（2026-08-09 统一）**：入口一律 `from loguru import logger`，**禁止新增** `import logging` + `logging.getLogger(__name__)`（唯一例外：`app/__init__.py` 的 `InterceptHandler` 基类需要）。8 处历史原生 logging（`core/requests_patch.py`、`services/bias/*`、`services/thermometer/{fetchers,industry_crowding,jobs}.py`）已于当日迁移完成。第三方库（werkzeug/urllib3/akshare 等）的 stdlib 日志由 `app/__init__.py` 的 `InterceptHandler` + `logging.basicConfig(force=True)` 兜底接入 loguru。loguru 0.7.3 经 2026-08 评估**未过时**：仍是 GitHub 最流行的第三方日志库（21k+ stars）；structlog 结构化/性能更强但学习曲线陡、logbook 已停滞（最后发布 2023-09，不支持 3.13+），本项目维持 loguru 不换。

## 后端命令（`cd backend`）

- 安装：`pdm install`（首次或依赖变更；dev 组含 invoke/rich：`pdm install -G dev`）。
- 测试：`pdm run python -m pytest -p no:xdist`（或 `pdm run invoke test`）。**必须单进程**：xdist 多 worker 重复加载 pypinyin 词典 / pandas / akshare / playwright 会 OOM。限定范围：`pdm run invoke test --path tests/services --k test_x`。
- 测试夹具：用 `backend/tests/conftest.py` 的 `app`/`client`/`db`/`make_position`/`make_asset`/`make_transaction`（内存 SQLite）；**禁止直接导入 `SessionLocal`**（conventions §4.2）。
- 启动 API：`pdm run flask --app app.main:app run --debug --host 0.0.0.0 --port 8000`（前端代理指向 :8000）。`pdm run invoke serve` 默认 :5000，前端连不上时注意区分。
- 同步任务：`pdm run invoke grab.temperature` / `grab.all` / `grab.job <name>`（复用 `app/tools/sync_cli.py`，tasks.py 不重复实现业务）；或 `pdm run sync --job temperature`。
- Lint/格式：`pdm run ruff check .` / `pdm run ruff format .`（120 行宽、单引号）。pre-commit 为 ruff --fix + ruff-format。
- 数据：默认本地 SQLite `backend/invest.db`。`migrations/` 不入库，模型结构变更后需重建 DB 文件。

## 前端命令（`cd frontend`）

- 开发：`pnpm dev`（端口 8848，`/api` 代理到 `http://127.0.0.1:8000`）。登录走 Supabase Auth（`@supabase/supabase-js`，登录页/路由守卫/登出），后端校验 JWT 鉴权；动态路由按 pure-admin 惯例由 `src/router/utils.ts` 的 `import.meta.glob("/src/views/**/*")` 自动生成（`src/views/` 下新建组件即自动成路由，须保证组件 `defineOptions.name` 与路由 name 一致）。`frontend/mock/` 为空目录且 vite-plugin-fake-server 仅配置未生效，勿靠它 mock。后端无 login 接口，仅 `/api/auth/logout` 与 `/api/auth/me`。
- 类型检查：`pnpm typecheck`（`tsc --noEmit && vue-tsc --noEmit --skipLibCheck`）。提交前必须手动跑并零错误——husky 钩子因 `frontend/.npmrc` 的 `ignore-scripts=true` 常未安装，勿指望提交时自动拦截。
- Lint：`pnpm lint`（eslint + prettier + stylelint）。构建：`pnpm build`（脚本已含大内存参数）。
- 提交：husky + commitlint 强制 conventional commits，type 枚举见 `frontend/commitlint.config.js`。
- 结构：业务页在 `src/views/{asset,account,temperature}/*`；接口按域集中在 `src/api/*.ts`，公共类型在 `src/api/types.d.ts`；设计语言见 `frontend/design.md`（亮色）与 `design.dark.md`（暗色）。

## 文档站 / 落地页（仓库根）

- `pnpm run docs:dev` / `pnpm run docs:build`。`docs/.vitepress/config.mjs` 的 `srcExclude` 把 working-notes、根级备忘 `.md` 等屏蔽出构建（源码仍保留，勿删）。**新增内部备忘一律放 `working-notes/`（全局屏蔽）；若在 docs 根生成备忘，必须同步登记进 `srcExclude`，否则会公开泄露。** 屏蔽清单与登记规则见 `docs/spec/internal-index.md`。
- **内部备忘命名（强制，2026-08-09 起）**：`working-notes/` 下文件名一律英文 kebab-case + 日期后缀 `{topic}-{YYYY-MM-DD}.md`（如 `deployment-implementation-guide-2026-08-04.md`），**禁止中文文件名/路径**；正文标题用中文，交叉引用用相对链接 `./{english-name}.md`。新增备忘须同步登记进 `docs/working-notes/README.md` 索引表，防止历史中文命名债（`多倍贝_*.md`）复发。
- 落地页：`pnpm run build:landing` / `build:about` / `build:story` / `build:pages`。`vercel.json` 构建时执行 `pnpm run build:landing`。
- Markdown lint：`pnpm run docs:lint-md`（CI 用 `npx lint-md docs`，不带 `-f`）。

## 一键启动

Windows：`dev.cmd`（内部走 `scripts/dev.ps1`）；Git Bash / WSL / macOS：`./scripts/dev.sh`（`--install` 重装依赖）。同时拉起后端 :8000 与前端 :8848。

## 本机提交环境（Windows）

- 提交走根 `.pre-commit-config.yaml`（ruff --fix + ruff-format，已 `pre-commit install` 生效）；前端 husky（lint-staged + vue-tsc）因 `ignore-scripts=true` 未安装，故 `vue-tsc` 须手动跑（见前端命令）。
- 若 pre-commit 崩溃报 `ACC_PRODUCT_CONFIG_V3` 超 32767 字符上限：commit 命令前先 `unset ACC_PRODUCT_CONFIG_V3` 再提交，勿用 `env -i`。
- 给用户看的命令行须兼容 Windows cmd（无 `head`/`cat`/`grep`/`sed`）：优先用项目自带脚本（如 `backend/scripts/diag_em.py`）或说明用 PowerShell 执行。

## 关键约束（权威规范在 `docs/spec/`、`frontend/design.md`）

- 接口错误统一 `{data, message, error_code}` 信封；API-First 契约冻结，字段 / 状态码 / 分页结构禁止私改；端点一律尾斜杠（**例外：`/api/temperature/{overview,history,multi}` 无尾斜杠，前端按此调用，勿"修复"**）。
- 精度：金额一律整数分（×100）、份额最小单位（份×10000）、净值 `DECIMAL(18,6)`，换算必须走 `app/core/money.py` 的 `Money`（`yuan_to_cents`/`shares_to_min_unit`），业务代码禁止直接乘除 float。
- 资产正负：用户录入正数，后端按大类自动转换（资产正/负债负），接口统一输出 `signed_amount` 为唯一计算字段，前端禁止二次运算正负。
- 可交易持仓（股票/基金/ETF/可转债）入 `positions`，静态资产（现金/房产等）入 `assets`。
- 前端：禁止 `any` / `Record<string, any>` 作 API 入参响应类型；组件 `defineOptions.name` 必须与路由 name 一致（否则 keep-alive 失效）；请求统一走 `src/api`，组件内禁止裸 axios；列表增删改成功后须主动清空列表缓存。
- 前端样式：禁止硬编码 hex 色值、禁止 Emoji、涨红跌绿（必须经 `--color-rise`/`--color-fall` 语义变量）。
- 数据分级与登录门禁：身份认证与家庭核心账本经 Supabase **云端权威 + 本地 SQLite 缓存**（RLS 兜底，须用户授权、可一键关闭，D3 修订原"永不上云"条款）；`user_preferences` 等按 `user_id` 私有。**探市（`/explore`、`/api/temperature/*`）与 `health` 免登录**，其余功能需登录（后端白名单 + 前端 `requiresAuth` 双轨一致）。抓取合规边界：仅允许公开市场数据抓取（基金净值 / 市场情绪）；**严禁**用户券商持仓的自动登录 / 爬取 / 同步。
- 注释与文档同步（D5 / conventions §16.5）：代码在必要处加注释讲「为什么」；样式/设计类改动必须同步 `frontend/design.md`/`design.dark.md`；注释过期须自主更新；注释用中文。
- 东方财富 WAF 按 TLS 指纹拦截裸 requests——已由 `backend/app/__init__.py` 的 `install_requests_patch()`（实现在 `core/requests_patch.py`）全局修复（有 curl_cffi 时 impersonate chrome）。**不要**靠加 UA / Referer 头"修"东财抓取，诊断用 `pdm run python scripts/diag_em.py`。akshare 已设 request_interval=3、use_thread=False。
- pypinyin 是重型依赖（3.2MB 词典），必须保持延迟导入（见 `fund_detail_enrich_job.py`）。
- 温度计模块历史基线数据 `backend/app/services/thermometer/data/all_pb.csv`（全A中位PB历史，行业拥挤度分母兜底）**禁止删除、禁止 `.gitignore`、必须入库**：它不是运行时缓存（已从 `cache/` 迁出至 `data/`），而是可被 `scripts/prefetch_all_pb.py` 重建但需稳定可追踪的基线；误删会导致温度计整组标灰。pre-commit 守卫 `scripts/guard_all_pb.py` 会在行数骤降（< 1000）时拒绝提交——不要绕过该守卫（如 `--no-verify`）。
- 提交前：后端 `pytest` 全量单进程通过；前端 `vue-tsc` 零错误。
