# AGENTS.md

> 个人投资记账 / 家庭资产管理平台「多多贝」（fundmate）
> 仓库文档均为中文，提交信息用中文 + Conventional Commits。
> 权威规范在 `docs/spec/`（入口 `docs/spec/index.md`），`conventions.md` 为冻结区，变更需先在 `decisions.md` 记录决策。

---

## 目录

- [项目概述](#项目概述)
- [Git 分支规范](#git-分支规范)
- [目录边界](#目录边界)
- [技术栈与开发环境](#技术栈与开发环境)
- [后端开发](#后端开发)
- [前端开发](#前端开发)
- [文档站与落地页](#文档站与落地页)
- [核心约束](#核心约束)
- [数据域架构（双引擎硬规则）](#数据域架构双引擎硬规则)
- [数据策略（按需存、禁止全量堆砌）](#数据策略按需存禁止全量堆砌)
- [Issue 全局治理（里程碑强制）](#issue-全局治理里程碑强制)
- [双库架构 Issue 治理（里程碑 #14）](#双库架构-issue-治理里程碑-14)
- [自动化工具](#自动化工具)
- [协作规范](#协作规范)
- [常用命令速查](#常用命令速查)

---

## 项目概述

- **主分支**：`main`（稳定，受保护，禁止直接 push）
- **集成分支**：`dev`（只接受功能分支的 PR 合并，禁止直接 push）
- **合并门禁（红灯不许合并）**：`ci.yml` 的 `质量门禁汇总`（job id `gate`）是 dev / main 的 **required status check**——任何上游 job（后端 / 前端 / 乱码 / changes）失败，gate 即失败，PR 不可合并。2026-09-11 实开，依据见 `docs/spec/decisions.md` D22。
  - **该门禁的效力随仓库可见性变化**：required check 由 GitHub branch protection 承载，**仅在仓库为 public、或账户为付费计划时生效**。若切回 private 且无付费计划，GitHub 会停用 protection，门禁随之降级为「红灯在 PR 上可见，但不阻止合并」——此时必须人工确认红灯原因再合并，否则升级计划。因此**不要把「有保护」写死为长期前提**。
  - 兜底守卫 `guard-direct-push`：拦截**直接 push `main`**（与仓库可见性无关）；`guard-direct-push` 已对准 `main`（旧版本误指已删除的 `M` 分支，等于空转）。
- **所有进入 `main` 的改动必须通过 PR**（功能分支 → `dev` → `main`）

---

## Git 分支规范

### 长期分支（仅两条）

- `main`：稳定主分支，仅接受 PR 合并。
- `dev`：集成分支，只接受功能分支的 PR 合并，**禁止直接 push**（含小改动）。

### 功能分支

- 新功能 / 较大改动：从 `dev` 切出 `feat/<简短描述>` 或 `fix/<...>`，开发完成后开 PR 合回 `dev`。
- 小改动（错别字、单文件微调、文档更新等）：同样从 `dev` 切分支（`fix/<...>`、`docs/<...>` 前缀），合并后删除分支——`dev` 不接受任何直接 push。
- 功能分支合入目标一律是 `dev`，**禁止**直接对 `main` 开 PR（紧急 hotfix 除外，但目标仍为 `main`）。

### 文档更新

- 随代码改动一起走 PR 合入 `dev`；纯文档改动从 `dev` 切 `docs/<...>` 分支走 PR，不直接提交 `dev`。

### 禁止事项

- 禁止向 `main` 直接 push（CI 会失败）。
- 禁止功能分支互相合并、或从错误 base 开 PR。
- 禁止新建长期分支（如 `staging`/`release` 等）。
- 历史遗留分支（`main-v2`、`M`、各类 `feat/*`/`fix/*`/`refactor/*`/`wip/*`/`backup/*`）已被清理，禁止复活或新建同名分支。

### PR 与 Review

- 功能分支 PR：`base` 填 `dev`。
- 发布 PR（`dev` → `main`）：`base` 填 `main`。
- AI review（免费 GLM 总结 + 智能路由深度）自动在 PR 上评论。

---

## 目录边界

```text
.
├── backend/                # 后端（PDM 管理）
│   ├── app/                # V2 代码（当前主代码）
│   │   ├── main.py         # 工厂函数 create_app()
│   │   ├── core/           # 核心基础设施（DB、money、auth、异常、补丁）
│   │   ├── domains/        # 领域分包（models, schemas, views）
│   │   ├── services/       # 同步、温度计、偏差、导入、绩效
│   │   └── tools/          # CLI 入口（sync_cli, sync_metadata）
│   ├── fundmate/           # V1 代码（已于 2026-08-01 退役，禁止新增引用）
│   ├── tests/              # 测试（pytest，单进程）
│   ├── pyproject.toml      # PDM 配置（项目名历史遗留 `showbuy`）
│   └── invest.db           # 默认本地 SQLite（市场域）
├── frontend/               # Vue3 + TS + Element Plus + pure-admin（pnpm）
│   ├── src/
│   │   ├── api/            # 接口定义（按域）
│   │   ├── views/          # 页面组件（自动路由，需 defineOptions.name 与路由名一致）
│   │   └── ...
│   ├── package.json        # 前端依赖（pnpm 强制）
│   └── pnpm-lock.yaml
├── docs/                   # VitePress 文档站（根目录 package.json 管理）
│   ├── .vitepress/
│   ├── spec/               # 规范（conventions.md 冻结区）
│   └── working-notes/      # 内部备忘（全局屏蔽，文件名须英文 kebab-case + 日期后缀）
├── scripts/                # 根目录脚本（构建落地页、提交工具、守卫等）
├── site/                   # 主站共享资产（style.css, logo.svg 必须入库）
├── landing.template.html   # 落地页模板
├── landing.content.yml     # 落地页内容
├── package.json            # 根目录：仅文档站与落地页依赖
└── vercel.json             # Vercel 构建配置
```

**重要**：
- 根 `package.json` 和 `frontend/package.json` 互不通用，勿混装依赖。
- `backend/pyproject.toml` 项目名 `showbuy` 是历史遗留，勿据此判断包归属。
- V1 代码（`backend/fundmate/`）已被守卫脚本 `scripts/forbid_v1_refs.sh` 拦截，禁止新增引用。

---

## 技术栈与开发环境

| 领域 | 技术 |
|------|------|
| 后端 | Python 3.12+，Flask/APIFlask，PDM，SQLite（开发）/ Turso（生产市场域）/ Supabase（生产用户域） |
| 前端 | Vue 3 + TypeScript + Vite，Element Plus，pure-admin，pnpm |
| 文档站 | VitePress（根目录 pnpm） |
| 落地页 | 已移交主站 duoduobei-web（duoduobei.com），本仓不再构建；应用站部署目标为前端 SPA |
| 测试 | pytest（**必须单进程**，因 xdist 多 worker 导致 OOM） |
| 代码检查 | Ruff（后端，120 行宽，单引号），ESLint + Prettier + Stylelint（前端） |
| 提交钩子 | pre-commit（后端 ruff），husky + commitlint（前端，但因 `ignore-scripts=true` 未实际安装） |

---

## 后端开发

### 架构概览

- **领域分包**：`backend/app/domains/<domain>/{models,schemas,views}.py`，每个域一个 `APIBlueprint`，路由在 `views.py`。
- **模型字段变更**：必须同步更新关联的 Create/Update/Out Schema（`conventions.md` §4.3）。
- **核心模块**：
  - `core/database.py`：SQLite + WAL，多引擎会话管理。
  - `core/money.py`：金额换算唯一入口（`Money` 类）。
  - `core/auth.py`：Supabase JWT 验签 + 白名单鉴权中间件。
  - `core/exceptions.py`：`SBException` + 统一错误信封。
  - `core/requests_patch.py`：东财 TLS 补丁（全局 `impersonate chrome`）。
- **服务层**：
  - `services/sync/`：双适配器（xalpha/akshare）+ 编排器。
  - `services/thermometer/`：温度计（含全 A 中位 PB 历史基线）。
  - `services/bias/`、`importer/`、`performance/`（XIRR）。
  - `services/daily_scheduler.py`：本机常驻每日调度（进程内 APScheduler；自选/持仓净值 + 温度计，#1467）。
- **同步入口**：两套 CLI（`pdm run invoke grab.*` 和 `pdm run sync --job`），共用 `DataSyncOrchestrator`。
  **本机常驻**另有两条路：`.env` 置 `SCHEDULER_ENABLED=1` 随应用启动，或 `pdm run scheduler-daemon`
  独立守护（同机靠单实例锁只跑一份）；详见 `docs/dev/scheduler-tasks.md`。

### 日志（2026-08-09 统一）

- 所有新代码必须使用 `from loguru import logger`，**禁止**新增 `import logging`。
- 唯一例外：`app/__init__.py` 的 `InterceptHandler` 基类需要。
- 第三方库的 stdlib 日志由 `InterceptHandler` + `logging.basicConfig(force=True)` 接入 loguru。
- loguru 0.7.3 维持不变（structlog 学习曲线陡，logbook 已停滞）。

### 测试

- 命令：`pdm run pytest -p no:xdist`（单进程，防 OOM）。
- 夹具：`tests/conftest.py` 提供 `app`/`client`/`db`/`make_position` 等（内存 SQLite）。
- **禁止**直接导入 `SessionLocal`（须用 `conftest` 夹具）。

### 常用后端命令（`cd backend`）

| 目的 | 命令 |
|------|------|
| 安装依赖 | `pdm install`（含 dev 组：`pdm install -G dev`） |
| 运行 API | `pdm run flask --app app.main:app run --debug --host 0.0.0.0 --port 8000` |
| 测试 | `pdm run pytest -p no:xdist`（或 `pdm run invoke test`） |
| 同步任务 | `pdm run invoke grab.temperature` / `grab.all` / `grab.job <name>`<br>或 `pdm run sync --job temperature` |
| 本机每日调度 | `pdm run invoke sched.status`（状态，只读）<br>`pdm run scheduler-daemon`（常驻守护，Ctrl+C 退出） |
| Lint & Format | `pdm run ruff check .` / `pdm run ruff format .` |
| 诊断东财抓取 | `pdm run python scripts/diag_em.py` |

---

## 前端开发

### 架构概览

- **路由**：`src/router/utils.ts` 通过 `import.meta.glob("/src/views/**/*")` 自动生成路由。新建页面须保证 `defineOptions.name` 与路由 name 一致（否则 keep-alive 失效）。
- **接口**：集中在 `src/api/`，按域划分，组件内**禁止**裸 axios。
- **登录**：Supabase Auth（`@supabase/supabase-js`），后端校验 JWT；登录/登出/路由守卫已配置。
- **动态路由**：`src/views/` 下的组件自动成路由，无需手动注册。
- **设计语言**：亮色 `frontend/design.md`，暗色 `design.dark.md`，**禁止硬编码 hex 色值**，必须使用 CSS 变量（`--color-rise`/`--color-fall` 等）。

### 常用前端命令（`cd frontend`）

| 目的 | 命令 |
|------|------|
| 开发 | `pnpm dev`（端口 8848，`/api` 代理到 `http://127.0.0.1:8000`） |
| 类型检查 | `pnpm typecheck`（`tsc --noEmit && vue-tsc --noEmit --skipLibCheck`） |
| Lint | `pnpm lint`（eslint + prettier + stylelint） |
| 构建 | `pnpm build` |
| 提交 | husky + commitlint 强制 conventional commits（type 枚举见 `commitlint.config.js`） |

> ⚠️ **升级/安装依赖后必须重启 dev server**（Issue #972）。
> `pnpm up` / `pnpm install` 只改磁盘上的 `node_modules`，**已在运行的 vite 仍持有旧模块与旧
> 依赖预构建产物**，HMR 会把新旧版本混在一起，症状是「CSS/组件样式莫名错乱」「改了不生效」——
> 极易被误判成业务代码 bug（历史上误判过暗黑模式，见 #976）。
> `dev` 已内置 `frontend/build/dep-drift-guard.ts`：检测到 `pnpm-lock.yaml` / `package.json`
> 变化会自动 `server.restart(true)`；若日志提示不支持自动重启，则 **Ctrl+C 后重新 `pnpm dev`**。
> 需要临时关闭：`DISABLE_DEP_DRIFT_GUARD=1 pnpm dev`。

### 前端约束

- **禁止 `any` / `Record<string, any>`** 作为 API 入参/响应类型。
- 列表增删改成功后**必须主动清空列表缓存**。
- 禁止 Emoji，涨红跌绿必须使用语义变量。

---

## 依赖复用与 Worktree 规范

> 多 worktree 并行开发时，每个 worktree 重复 `pnpm install` / `pdm install` 既耗时又占盘。本节规定复用策略，所有 AI / 开发者开新 worktree 后**必须**按此执行。

### 主仓库只跑 dev server，不在其中切分支（强制，2026-09-11）

- **主仓库 `D:\codes\fundmate` 常驻 `dev`，只用于运行 dev server。一切代码改动都在独立 worktree 里做**
  （`git worktree add ../<repo>-<issue#> -b <type>/<issue#>-<slug> origin/dev`），改完走 PR 合入 `dev`；
  主工作区**始终不切分支、不 stash、不被 pull 覆盖**。CLI 的 cwd 可以是主仓库（读操作、`gh`、`git log`
  之类都无所谓），但只要要**改文件**，就换到 worktree。
- **禁止在主仓库执行会改写工作区的命令**：`git checkout <分支>` / `git switch` / `git stash pop|apply` /
  `git reset --hard` / 有本地改动时的 `git pull` 等。确需切换分支时**先停掉 dev server**。
- **为什么**（#1421 事故复盘，2026-09-11 实测）：主仓库跑着 Vite 时切分支，git 是**逐个文件**改写工作区的——
  它先 unlink 了 `frontend/build/dep-drift-guard.ts`，而仍然 import 它的 `frontend/build/plugins.ts`
  尚未被改写；Vite 监听着「配置依赖」的变化，立刻重载配置 bundle，重新读到的仍是新版 `plugins.ts`，于是报
  `Could not resolve "./dep-drift-guard"` → `server restart failed`。dev server 与磁盘状态随即错位，
  而报错指向一个「明明存在」的文件，极易被误判成代码缺陷。**这是工作流问题，不是代码缺陷。**
- 同理：跑着 dev server 的工作区不要被 `git worktree remove`、外部脚本或编辑器插件批量改写文件。

### 原理（为什么不能"直接复用主仓库依赖"）

- pnpm / PDM 均使用**全局 content-addressable store/cache** 去重：包体只下载一次（pnpm 默认 `%LOCALAPPDATA%\pnpm\store`；PDM 默认 `~/.cache/pdm`）。
- 各 worktree 内的 `node_modules` / `.venv` 不是副本，而是**符号链接 / junction 指回全局 store**，磁盘占用极小（仅链接层，非包本体）。
- **硬约束**：Node 模块解析要求 `node_modules` 必须位于工作树自身目录内（相对 `import`、`.bin`、`pnpm` 虚拟仓库 `.pnpm` 均依赖此位置），故不能把新 worktree 的 `node_modules` 直接指向主仓库，否则 `import` 失败。重复 `install` 的本质是"重建链接结构"，不是"重新下载安装"（数十秒属建链接，非重装）。

### 标准流程（开新 worktree 后）

1. **先比对锁文件一致性**：运行以下命令确认锁文件未变。

   ```powershell
   git diff <base-branch> -- frontend/pnpm-lock.yaml frontend/package.json backend/pyproject.toml
   ```

2. **锁文件一致**（同一条 dev 分支派生，最常见）→ 用目录联结（junction）复用主 worktree 的依赖，零下载、秒级、零额外磁盘：

   ```powershell
   # 前端：删掉新 worktree 自带（或空的）node_modules，挂接主仓库那份
   Remove-Item "D:\codes\<new-worktree>\frontend\node_modules" -Recurse -Force -ErrorAction SilentlyContinue
   cmd /c mklink /J "D:\codes\<new-worktree>\frontend\node_modules" "D:\codes\fundmate\frontend\node_modules"
   ```

   - junction 不需要管理员权限；主 worktree 的 `node_modules` 须保持稳定（不要在其中改动依赖）。
   - **仅前端 `node_modules` 可 junction**：它装的是第三方依赖、不含本仓源码，多 worktree 共享安全。

4. **后端 `.venv` 禁止 junction 复用**（2026-08-30 实测踩坑）：PDM 以 **editable 方式**把 `app` 包装进 venv，
   `.pth` 里写的是**创建该 venv 时的绝对源码路径**。junction 复用主 worktree 的 `.venv` 后，
   在新 worktree 执行 `import app.core.constants` 仍会解析到**主 worktree** 的源码。实测症状：

   - `ImportError: cannot import name 'ValuationMode' from 'app.core.constants'
     (D:\codes\fundmate\backend\app\core\constants.py)` —— 新写的代码明明在，却导入不到；
   - 主 worktree 分支落后于 dev 时，还会连带报 `ModuleNotFoundError: No module named 'app.core.config'`
     一类「文件明明在却找不到」的假象（那些是 dev 上才有的新模块）。

   正确做法：新 worktree 里**独立安装**（走 PDM 全局缓存，是建链接不是重新下载，约 1~2 分钟）：

   ```powershell
   cd <new-worktree>/backend && pdm install -G dev
   pdm run python -c "import app.core.constants as c; print(c.__file__)"   # 必须指向当前 worktree
   ```

   **自检铁律**：装完必须打印 `app` 模块路径确认指向**当前 worktree**，否则测试跑的是别人的代码，
   而失败信息会指向错误的方向。

   **风险提示：pdm 2.26 走 uv 后端时有副作用（2026-09-11 实测）**。`pdm install` 会用临时文件
   `backend/pyproject.toml.<随机后缀>` 重写 `pyproject.toml` 再 rename 覆盖，并额外生成 `uv.lock`。
   两个后果：

   - **不要在 install 执行期间删除或移动那个临时文件**：rename 会因源文件缺失报 `FileNotFoundError`，
     结果是 `pyproject.toml` 直接从工作区**消失**。连带伤害很隐蔽——`ruff` 读不到
     `[tool.ruff.format] quote-style = "single"` 就退回默认双引号，一次 `ruff format` 能把整文件
     单引号改成双引号，diff 从数行膨胀到数百行（先查行尾会白费功夫）。
     丢失后用 `git checkout -- backend/pyproject.toml` 恢复，重跑 format 即收敛。
   - **若该次 install 报错**（如 `pywin32` 拒绝访问），产出的 `.venv` 是**不完整**的（典型症状
     `No module named 'pluggy'`），不要在此基础上跑测试。应急可借主 worktree 的 `.venv`，
     但须把 cwd 设为本 worktree 的 `backend/`，并先打印 `app.__file__` 确认指向正确。

3. **锁文件不一致**（某分支升级了依赖）→ 禁止 junction，走正规安装：

   ```powershell
   cd <new-worktree>/frontend && pnpm install --offline
   cd <new-worktree>/backend && pdm install
   ```

### 风险闸门

- 仅当锁文件逐字节一致才可 junction；一旦某 worktree 的 `package.json` / `pnpm-lock.yaml` / `pyproject.toml` 与主仓库不同，复用旧 `node_modules` 会**版本错配**导致诡异运行时错误。此时必须走第 3 步。
- 同一时刻只在一个 worktree 跑 `pnpm install` / `pdm install`，避免两 worktree 同时改写共享 store 的链接层。

---

## 文档站与落地页

- **文档站**：根目录执行 `pnpm run docs:dev` / `docs:build`。
- **内部备忘**：一律放 `docs/working-notes/`（全局屏蔽），文件名必须英文 kebab-case + 日期后缀，如 `deployment-2026-08-04.md`，正文标题可用中文。新增备忘须同步登记进 `working-notes/README.md` 索引表。
- **落地页**：`pnpm run build:landing` / `build:about` / `build:story` / `build:pages`。`vercel.json` 构建时会执行 `build:landing`。
- **Markdown lint**：`pnpm run docs:lint-md`（CI 用 `npx lint-md docs`，不带 `-f`）。

---

## 核心约束

### API 契约

- 错误统一信封：`{data, message, error_code}`。
- API-First 契约冻结，禁止私改字段、状态码、分页结构。
- 端点一律尾斜杠（**例外**：`/api/temperature/{overview,history,multi}` 无尾斜杠，前端按此调用，勿“修复”）。

### 金额与精度

- 金额：整数分（×100）。
- 份额：最小单位（份×10000）。
- 净值：`DECIMAL(18,6)`。
- 换算必须走 `app/core/money.py` 的 `Money`（`yuan_to_cents`/`shares_to_min_unit`），业务代码禁止直接乘除 float。

### 资产正负

- 用户录入正数，后端按大类自动转换（资产正 / 负债负）。
- 接口统一输出 `signed_amount` 为唯一计算字段，前端禁止二次运算正负。

### 持仓与资产

- 可交易持仓（股票/基金/ETF/可转债）入 `positions` 表。
- 静态资产（现金/房产等）入 `assets` 表。

### 数据分级与登录门禁

- 身份认证与家庭核心账本经 Supabase 云端权威 + 本地 SQLite 缓存（RLS 兜底，须用户授权，可一键关闭）。
- `user_preferences` 等按 `user_id` 私有。
- **探市（`/explore`、`/api/temperature/*`）与 `health` 免登录**，其余功能需登录（后端白名单 + 前端 `requiresAuth` 双轨一致）。
- 抓取合规：仅允许公开市场数据（基金净值 / 市场情绪），**严禁**用户券商持仓的自动登录 / 爬取 / 同步。

### 授权与可见性

- **本仓库当前公开可见（public），但不是开源软件**：自有代码适用根 `LICENSE` = **PolyForm Noncommercial 1.0.0**（SPDX：`PolyForm-Noncommercial-1.0.0`），**禁止任何商业使用**；商业使用须另行取得书面授权。
- **禁止把仓库描述为「开源」**：代码注释、文档、提交信息、PR / issue 描述、包元数据里一律不得出现「开源」「open source」「免费商用」等表述；需要指代时用「公开可见 / source-available（非商业许可）」。
- **不得把 public / private 状态写死为规则前提**：可见状态可随时变更（含切回 private），而**授权不随可见性变化**——公开只代表可见、不构成使用许可，切回私有也不会放宽授权。凡结论依赖于当前可见性的，须写成**带条件的判断**，不得写成永久事实。
- **第三方署名不可删**：`frontend/LICENSE` 是上游模板 [pure-admin](https://github.com/pure-admin) 的 MIT 声明，必须保留；本项目自有代码不因该文件而适用 MIT。
- 对外授权口径以 `README.md`「授权与使用限制」与根 `LICENSE` 为准。

### 注释与文档

- 代码在必要处加注释讲“为什么”。
- 样式/设计类改动必须同步 `frontend/design.md` / `design.dark.md`。
- 注释过期须自主更新，注释用中文。

### 东方财富 WAF 与 akshare

- 已由 `core/requests_patch.py` 全局修复（`impersonate chrome`），**不要**靠加 UA/Referer 头硬修。
- akshare 已设 `request_interval=3`、`use_thread=False`。
- pypinyin 重型依赖（3.2MB 词典）必须保持延迟导入（见 `fund_detail_enrich_job.py`）。
- **并发取数前必须预热 V8（硬约束，事故来源见 `decisions.md` D24）**：akshare 有 **40 个模块**
  用 `py_mini_racer` 解密新浪/巨潮系 JS 数据（`stock_zh_index_daily` / `stock_zh_a_daily` /
  `stock_hk_index_daily_sina` / `index_us_stock_sina` / `fund_etf_hist_sina` /
  `futures_main_sina` / `bond_zh_cov` …），**每次调用都新建一个 `MiniRacer()`**，而 V8 的
  configurable pool **只能初始化一次**——多线程并发首次创建会触发
  `FATAL: Check failed: !IsConfigurablePoolInitialized()`。**那是 C++ abort 而非 Python 异常**，
  `except Exception` 抓不住、`try/finally` 拦不住，**会直接杀掉整个进程**（Web 服务 / 调度器
  守护进程一起没，表现为「服务突然消失」而非「某个资产取数失败」）。
  **已结构性解决**：守卫在 `app/core/v8_guard.py`（`ensure_v8_ready()`，双检锁 + 结果缓存），
  并挂在**全仓唯一收口点** `app/core/akshare_lazy.get_akshare()` 上——**只要走 `get_akshare()`
  就自动免疫，不需要手动预热**。唯一例外：绕过它直接 `import akshare`（当前仅两个 CLI 脚本），
  此类路径若要多线程，必须自行调用 `ensure_v8_ready()` 或改为串行。

### 温度计基线数据

- `backend/app/services/thermometer/data/all_pb.csv`（全 A 中位 PB 历史）**必须入库，禁止删除、禁止 `.gitignore`**。
- pre-commit 守卫 `scripts/guard_all_pb.py` 会在行数骤降（< 1000）时拒绝提交，禁止 `--no-verify` 绕过。

### 提交前检查

- 后端：`pytest` 全量单进程通过。
- 前端：`vue-tsc` 零错误（需手动运行，因 husky 未安装）。

---

## 数据域架构（双引擎硬规则）

**背景**：项目正从单 SQLite 演进为 **Turso（市场域）+ Supabase（用户域）+ Neon（灾备，延后）**。**默认单库**：本地未显式配置独立 user 库时，user 域与 market 域共用同一本地 SQLite（既有数据零迁移）；显式配 `DEV_USER_DATABASE_URL` / `SUPABASE_DATABASE_URL` 才拆双库。权威事实标准见 `docs/dev/db-data-domain.md` §9。

### 语义定义

- **市场域（`market`）**：公开、读多写少、随时间无限膨胀的数据（净值、行情、温度、指数、基金基础资料、基金管理人、系统同步审计）。开发期用本地 `invest.db`，生产用 Turso。
- **用户域（`user`）**：含 `family_id`/`user_id` 的用户私有数据（账户、持仓、交易、组合、自选关系、家庭、用户、销售机构、用户操作审计）。开发期默认与 market 同库（显式设 `DEV_USER_DATABASE_URL` 才独立），生产用 Supabase。

### 强制规则

1. **数据域归属以 `app/core/db_factory.DATA_DOMAIN_REGISTRY` 中央注册表为准**（表名 → `market`/`user`），新增表必须先登记注册表，未登记会被启动校验拦截；模型文件**不声明**域属性（原「模型声明 `__data_domain__` 类属性」条文作废——实现从未采用该机制，2026-08-24 修正，归属清单见 `docs/dev/db-data-domain.md`）。
2. **跨域零外键、零 SQL join**：两域独立引擎，无法 SQL JOIN。关联只存冗余业务键（如 `fund_code`）。
3. **跨域读取只允许“应用层两步法”**：先取键列表，再用 `in_` 批量去另一域取数据。集中到统一 service，禁止各 service 手写 N+1。
4. **归属决策树**：
   - 含 `user_id`/`family_id` → `user` 域；
   - 被 `user` 域表外键引用的小体积名录（如销售机构）→ `user` 域；
   - 被 `market` 域表外键引用（基金管理人）→ `market` 域；
   - 公开、读多写少、无限膨胀 → `market` 域。
5. **`init_db` 按域分别 `create_all`**，启动断言声明域与实际建库一致，不一致直接 fail。
6. **会话入口只有 `market_session()` 和 `user_session()`**，禁止混用。
7. **单库/双库统一可用（默认单库）**：未显式配置独立 user 库（`DEV_USER_DATABASE_URL` / `SUPABASE_DATABASE_URL`）时，user 域与 market 域同库；显式配置才拆，业务代码零改动。
8. **Neon 灾备仅替换连接串**，业务代码不变；但 auth 需单独处理（延后）。

---

## 数据策略（按需存、禁止全量堆砌）

> 权威细则：`docs/spec/data-strategy.md`；决策依据：`docs/spec/decisions.md` D21（2026-09-10）；上位规范：`conventions.md` §16.2。
> 本节是**流程闸门**：新增数据实体不通过准入检查，PR 不得合入。

### 第一原则

**数据策略由产品场景驱动，不由工程完整性驱动。** 记账软件的核心价值是「算得准」（L1 用户数据 + L2 派生计算）；参考展示类（L3，如基金公司 / 经理 / 全称 / 指数估值）与关联关系类（L4，如 ETF↔联接、A/C 份额）数据**按需取 + 缓存 + 可降级 `—`**，缺了不影响产品可用性。**「工程上重要」不等于「产品上重要」。**

> 教训来源：项目早已有 `conventions.md` §16.2「禁止过度工程」，但该节只约束**代码**，从未约束**数据**——「按需开发」被读成「不写多余代码」而非「不存多余数据」，导致本地库 1.22 GB，`funds` 26,938 行中用户实际触达仅 117 只（0.43%）。

### 数据准入四问（强制，写进 PR 描述）

新增 **表 / 列 / job / 抓取目标池** 时，必须逐条回答：

1. **谁在用？**（具体到功能 / 接口 / 界面元素，不接受「以后可能用到」）
2. **什么场景用？**（用户在什么操作路径下看到它）
3. **缺了会怎样？**（降级影响是否可接受——可接受即不必存）
4. **成本多大？**（新增存储量 / 外部请求数 / 限流风险）

**前三问答不出具体答案 → 判定为伪需求，禁止开发。** 回答与结论须留痕在 PR 描述或对应 issue 评论中，不得只在口头讨论。

### 硬约束

1. **新列必须当场指定读者**——API 序列化字段 / 计算输入 / 界面展示三者之一；禁止「先存着，以后可能有用」。新列的预期填充率与写者须在 PR 中说明。
2. **新表必须有读路径**——只写不读的表禁止建立（反面先例：已删除的 `fund_management_companies`）。
3. **抓取目标池必须显式**——只能来自用户触达范围（`positions ∪ watchlist`，经 `orchestrator.resolve_targets()`）或代码内明确配置的核心池常量。**禁止 `targets if targets else 全库` 这类静默退化**（反例 `fund_manager_job.py:37`）；空 targets 的正确语义是「跳过」。
4. **`__full__` 使用有前提**——仅当该 job 单次调用**不产生逐条外部请求**时可用全量；逐只抓取类 job 一律按目标池限量，且须设批量上限与节流。
5. **job 名称 / docstring 必须与行为一致**——禁止「名为全量、实为只增不改」这类契约谎报。
6. **请求路径禁止全表扫描**——接口 / 页面渲染路径中禁止无条件 `db.query(Model).all()`；跨域读走 `services/cross_domain.py` 两步法。
7. **同一实体只能有一张可写表，每个字段只有一个 job 有写权**（沿用既有防漂移原则）。
8. **孤儿表 / 死列不得私自删除**（`conventions.md` §16.3）——发现后登记 `docs/spec/tech-debt.md` 并报用户拍板；库内游离于 `DATA_DOMAIN_REGISTRY` 之外的表须登记或清理，不得长期沉默。
9. **验收口径纪律**——issue 验收标准不得未经第 1~3 问验证就写「全库覆盖率 ≥X%」；参考展示类数据优先采用「用户触达口径」。
10. **新增表仍须先登记 `core/db_factory.DATA_DOMAIN_REGISTRY`**（见「数据域架构」硬规则 §1）——数据策略准入与数据域登记并行，不可互相替代。

---

## Issue 全局治理（里程碑强制）

> 全局硬性规定：**任何 issue（含 AI 自动创建 / ClawBot 生成的元 issue）创建后必须挂里程碑，禁止处于无里程碑（No milestone）状态。**
> 参考 #1287 看板整理教训：2026-09-02 曾出现 31 个开放 issue 完全未挂里程碑、M6 Backlog 被当垃圾桶，经系统整理后已清零；此后以本全局规则 + CI 守卫防止回潮。

### 归属原则

- 主题明确 → 归入对应产品里程碑：`M0 上线`、`M1 付费验证`、`M2 免费核心`、`M3 量化分析`、`M4 护城河生态`、`M5 安全与体验`、`M6 待办积压 Backlog`、`P0 导入统一入口`、`基础数据 Base Data`、`自选增强 Watchlist Enhancement`、`双库架构 / DB Multi-Engine（#14）` 等。
- 确属远期 / 待定 / backlog → 归入 `M6 待办积压 Backlog`，**不得**停留在 No milestone 状态。
- 双库架构 / 数据域 / 数据库相关 issue 的强制归属见下方「双库架构 Issue 治理（里程碑 #14）」（该专项规则是本条全局规则的子集，二者不冲突）。

### CI 守卫（拦住新建漏挂）

- 工作流 `.github/workflows/issue-milestone-guard.yml` 在 issue 被 `opened / edited / reopened` 时检查其 `milestone` 字段：
  - 有里程碑 → 通过；
  - 无里程碑 → 在 issue 下**评论提醒责任人补挂**，并使该 workflow run **失败（红）**作为止损信号（issue 本身无法被 Action 自动关闭/拦截，故以失败 run + 评论提醒）。
- 该守卫只针对 issue（`pull_request` 事件不触发），不影响正常 PR 流程。
- 维护者补挂里程碑（edit 触发 `edited`）后守卫会自动复检通过，自愈。

### 失实信息修正纪律

- 既有 issue 的正文若被发现失实（如快照数字、状态描述与真实不符），**用评论（`gh issue comment`）追加更正，禁止用 `gh issue edit` 覆盖原正文**（遵循 AGENTS.md「追加请续帖」）。误关须 `gh issue reopen` 并留痕。
- 确需修正正文的极特殊场景，先在原 issue 评论说明、再 edit，且保留历史可追溯到评论。

---

## 双库架构 Issue 治理（里程碑 #14）

> 统一管理里程碑：**双库架构 / DB Multi-Engine（#14）**。目的：防止双库/数据域相关工作再度陷入 issue 散落、重复、噪音失控（参考 #1287 看板整理）。所有相关 issue 创建后**必须**归入本里程碑，并在本节登记映射。权威标准仍是 `docs/dev/db-data-domain.md` 与本节「数据域架构（双引擎硬规则）」。

### 本次工作记录（2026-09-02）

- **确认「表→域」归属逻辑已存在**：`backend/app/core/db_factory.py` 的 `DATA_DOMAIN_REGISTRY`（`tables_by_domain` / `validate_domain_labels` 做分组与启动校验），权威文档 `docs/dev/db-data-domain.md`（v1，2026-08-18）。新增表必须先登记注册表，未登记会被启动校验拦截（硬规则 §1）。本次双库路由**复用该注册表**，不另起炉灶。
- **完成 #1085 双库模式就绪**：业务层按表路由——user 域请求落到 user 引擎、market 域落到 app 引擎，调用点零改动。
- **修复并关闭 #1219**：双库模式 `_seed_default_identity` 跨域写入 market 引擎（此前 `tests/core/test_db_data_domain.py` 2 项失败），复跑 `10 passed`。
- **关联图**已发布于 #1085 评论（依赖链：#894/#1028 奠定引擎 → #1085 路由 → #1232 对账框架）。

### Issue ↔ 里程碑 #14 映射

| Issue | 角色 | 状态 |
|-------|------|------|
| #894  | 引擎地基：部署形态、Turso 双备份、日志追踪选型（Q1-RED） | OPEN   |
| #1028 | 独立 dev Supabase 项目 + 前端隔离切换（Q1-RED） | OPEN   |
| #1085 | 双库模式就绪：user 域路由到 user 引擎（hub） | OPEN   |
| #809  | 数据库存储选型调研（早期） | OPEN   |
| #896  | 数据库成本决策（Supabase vs 腾讯云） | OPEN   |
| #979  | Supabase vs Neon 选择建议（灾备延后） | OPEN   |
| #825  | DB 下载导入层（快照导出/导入，full-sync 限范围） | OPEN   |
| #824  | 同步按需回填 + T 日不回填 + sync 入口职责 | OPEN   |
| #1036 | 启动期数据库结构校验守卫（已闭环） | CLOSED |
| #1219 | 双库模式跨域写入 bug（test_db_data_domain，已闭环） | CLOSED |
| #1232 | 统一对账工作台（三域统一，依赖 #1085 路由） | OPEN   |

### 防 issue 失控 / 噪音规则

1. **归入里程碑**：任何双引擎 / 数据域 / 数据库架构类 issue 创建后**必须**指派到里程碑 #14，禁止散落（避免 #1287 式「未挂里程碑清零」重演）。
2. **单 issue 单事项**：遵循「Issue 原子化约束」；双库相关的新表登记、护栏补充、迁移脚本等若属同一主题，尽量在既有 issue / 评论续帖，不为每个小改动另开新卡。
3. **新增表走注册表，不另开 issue**：加表时改 `DATA_DOMAIN_REGISTRY` + `docs/dev/db-data-domain.md` + 启动校验即可；仅在发现注册表/文档漂移（孤儿项、缺登记）时才开 issue，并立即归入 #14。
4. **关联不靠重复卡片**：跨域/引擎讨论集中在 hub issue（#1085 / #894 / #1232）评论区互链，用 `#xxx` 引用，避免复制多张相似卡。
5. **闭环即清理**：完成并验收后及时关闭（遵循「Issue 关闭纪律」），关闭前把遗留项拆新卡并互相关联。
6. **定期巡检**：结合 #1287 的里程碑复核节奏，确认无 issue 长期游离于里程碑之外。

---

## 自动化工具

### 临时文件清理（`backend/scripts/cleanup_temp.py`）

- **WHY**：规避 IDE 删除工具被拦截或静默失败，统一收口删除操作。
- **默认 DRY-RUN**：只列出待删文件，不真正删除。
- **必须显式传 `--apply`** 才执行删除。
- **安全闸门**：每个待删文件经 `git ls-files` 核验，未跟踪（或被 `.gitignore` 忽略）才允许删除，已跟踪文件跳过。
- **用法**：

  ```bash
  cd backend
  pdm run python backend/scripts/cleanup_temp.py --file ../x.ps1 --file ../y.txt  # dry-run
  pdm run python backend/scripts/cleanup_temp.py --file ../x.ps1 --apply          # 真正删除
  ```

- **适用模式**：默认匹配 `.tmp_*`、`_commit_*`、`_commit_msg_*`、`_cleanup_*`，可用 `--pattern` 追加。

### 代码提交工具（`scripts/commit_changes.py`）

- **WHY**：绕过 IDE 提交审批卡点，实现无人值守提交。
- **默认 DRY-RUN**：展示提交文件清单和提交信息全文。
- **必须显式传 `--apply`** 才执行 `git commit`，可选 `--push`。
- **提交信息走文件**：`--message-file` 指定 UTF-8 文件，禁止内联中文。
- **永不 `--no-verify`**：pre-commit 守卫始终生效。
- **用法**：

  ```bash
  python scripts/commit_changes.py --files a.py b.py --message-file .git/COMMIT_MSG  # dry-run
  python scripts/commit_changes.py --files a.py b.py --message-file .git/COMMIT_MSG --apply --push
  ```



---

## 协作规范

### GitHub Issue / Discussion / PR 创建（自动化通道）

- **环境**：必须 UTF-8（`export LANG=C.UTF-8; export LC_ALL=C.UTF-8`；Python 设 `PYTHONUTF8=1`）。
- **中文内容**：issue / discussion 必须用 `--title-file` / `--body-file` 传入 UTF-8 无 BOM 文件，禁止内联中文变量。
- **PR 标题（高频踩坑点）**：`gh pr create` **不支持 `--title-file`**，故严禁 `gh pr create --title "中文…"` 内联传标题——Windows GBK 控制台会把中文按代码页 936 编码，gh 收到 GBK 字节却当 UTF-8 发给 GitHub，标题被永久存成乱码（正文 body 走 `--body-file`/`-F` 不受影响）。正确做法二选一：
  1. **首选 `gh pr create --fill`**：标题与正文直接取自最新提交信息（git 内为干净 UTF-8），完全绕开内联中文；
  2. 确需显式标题时：先 `gh pr create` 建空标题 PR，再用 UTF-8 JSON 文件 `gh api -X PATCH repos/<owner>/<repo>/pulls/<n> --input title.json` 修正（`title.json` 用 `write_to_file` 生成，禁止内联）。
- **守卫盲区**：mojibake 守卫只扫「仓库内文件 + git 提交信息」，PR 标题存在 GitHub、不在仓库内，守卫无法覆盖。因此 PR 标题的干净只能靠创建时走 UTF-8 安全通道，无 CI 兜底。
- **回读校验**：创建后立即 `gh issue view <n> --json title`（或 `gh api .../pulls/<n> --jq .title`）确认中文无乱码；发现乱码用上面 PATCH 方式修正，不要删除重建。

### Issue 原子化约束

- **一个 issue 只承载一件事**，不相关的内容拆分为多个 issue，用引用（`#xxx`）串联。
- **追加请续帖**：在已有 issue 上补充新结论时用评论（comment），禁止用 `gh issue edit` 覆盖原正文。
- **超长即拆分信号**：当 issue 混入第二、第三件事时，新建独立 issue 并引用回原 issue。
- **关闭即终点**：仅当该 issue 对应的事项真正完成才可关闭。

### Issue 关闭纪律（禁止以 PR 状态代替验收）

- **关闭前必须逐条核对验收**：关闭 issue 前，必须逐条核对本 issue 的「要做的事」与「验收标准」，逐项确认已达成，或明确记录未达成项及其归属后方可关闭。**禁止以「PR 已合并 / merged」代替验收**——PR 合并仅代表代码合入，不代表验收标准达成，PR 范围可能小于 issue 范围（#1177 的 PR #1188 只覆盖导入路径，却据此关闭了整张卡）。
- **PR 声明「另立单跟进」必须当场开单**：PR 正文出现「后续处理 / 另立单跟进 / 不在本次范围」等表述时，必须在合并**同时**创建对应 issue 并在原 issue 评论中关联编号；否则原 issue 不得关闭，避免剩余项无 issue 承载（#1177 的 PR 写了「另立单跟进」却未开单）。
- **范围外发现项不得悬空**：实现中发现本 issue 范围外的问题（如其他页面同样存在假数据），要么本卡处理，要么新建 issue 并在本卡评论写明归属；**禁止仅在 PR 正文写「由 #xxx 接管」而不核实 #xxx 是否真覆盖**（#1171 的 PR 声明顶部汇总卡片假数据由 #1014 接管，核实后 #1014 并不覆盖，须补 #1195）。
- **误关须更正留痕**：发现误关立即 `gh issue reopen`，并追加评论说明「误关原因 / 已完成部分 / 未完成部分 / 后续处置」，不得静默重开或抹去痕迹。
- **部分完成时拆卡转移，不要长期挂起**：若 issue **主体已达成**、只剩范围外的遗留项，正确做法是——
  ① 把遗留项**拆成新 issue**；② 在**旧 issue 与新 issue 上互相评论关联**（旧→新「遗留项已转至 #x，本卡关闭」，
  新→旧「遗留自 #y」）；③ **关闭旧 issue**。遗留项有新卡承载即不再悬空，旧卡也不必为了等零碎剩余
  一直 OPEN。判断标准是「**主体验收是否达成**」，而不是「是否还剩一点没做」——
  后者会让几乎所有 issue 永远关不掉，看板随之失去信噪比。
  反例：#1177 导入路径已达成，却因两项遗留（手动记账入口白名单、OP_TYPE_LABEL）整卡重开，
  正确做法应为拆新卡承接遗留、互相关联后关闭 #1177。

### 禁止武断执行

- **删除/移除/覆盖/丢弃**等破坏性操作前必须核实内容价值：
  1. 读内容了吗？
  2. 是否有参考价值 / 是否已被代码实现？
  3. 删了能否恢复？
- 高价值内容（竞品调研、数据源清单、路线图、设计基线、历史笔记）即使 issue/讨论已关闭，也应**打 `归档` 标签 + Status=Done** 保留在看板，而非删除。
- 整理看板 ≠ 清空，双维度分组（活跃/归档）是目标。

### Issue 优先级与 Project 看板

- 内置字段 **`象阵`**（Q1:RED 重要紧急 / Q2:YELLOW 重要不紧急 / Q3:GREEN 紧急不重要 / Q4:GRAY 不重要不紧急）。
- 创建/处理 issue 时务必用 `象阵` 标优先级，**禁止另建 priority 字段**。
- **注意：该字段在 GitHub 上的实际名称是 `象阵`（U+8C61 U+9635），不是 `象限`** —— 2026-09-11 经 GraphQL 实测确认（`fields` 返回 `name: "象阵"`，id 与本文件所载 field id 一致）；此前本文件写作「象限」，会误导按名查字段的操作。
- 看板操作：`gh project item-add 3 --owner imoyao --url <issue-url>`，然后 GraphQL 更新 `singleSelectOptionId`（Q1=`84f4167a` / Q2=`2aead21d` / Q3=`3ea6e338` / Q4=`d3517118`，field id=`PVTSSF_lAHOAV6ff84AAot3zhaGpdo`）。
  - 实测补充（2026-09-11）：`gh project item-add` 在本机 token 下**可能静默不生效**（exit 0 但条目未入板）。可靠做法是直接调 GraphQL `addProjectV2ItemById(input: {projectId, contentId: <issue node_id>})`，再用 `updateProjectV2ItemFieldValue` 设置 `象阵` 与 `Status`。
- **治理纪律**：路线图/未来设想类 issue 打 `归档` 标签并关闭（不删除），引用到索引 #920。

### AI 自动提交标注

所有由 AI 工具（CodeBuddy / OpenCode / 远程 agent 等）主动提交或经用户指示提交的代码改动，必须：

- 在提交信息中追加 footer：
  - `[AI 自动提交]`
  - `AI-Committed-By: <实际提交者>`（如实填写具体工具名，禁止一律写“CodeBuddy AI”）
- 遵守 conventional commits 和所有守卫。

### AI 编码防乱码规则

- 所有含中文的文本文件（`.md`、`.py`、`.vue` 等）必须保存为合法 UTF-8，内容可读中文。
- 写入时确保整个链路 UTF-8 端到端，禁止 GBK/Latin-1 解码后再存为 UTF-8（二次编码导致 mojibake）。
- **提交信息同样受约束**：`pre-commit` 的 `guard-mojibake-commit-msg` 钩子会在 `commit-msg` 阶段拦截乱码提交信息；CI 的 `mojibake_guard` job 作为兜底，扫描 PR 变更文件，防止经 `--no-verify` 或 `gh api` / MCP 直推绕过本地钩子。
- **禁止 `git commit -m "中文..."` 内联写法**（PowerShell 等控制台会把中文按 GBK 传给 git 造成永久乱码历史）。一律用 `git commit -F <utf8文件>` 或 `scripts/commit_changes.py --message-file <...>`。
- 本地 `guard_mojibake.py`（文件）与 `guard-mojibake-commit-msg`（提交信息）会拦截疑似乱码，禁止 `--no-verify` 绕过。

---

## 常用命令速查

| 场景 | 命令 |
|------|------|
| 一键启动（根目录） | `./scripts/dev.sh`（macOS/Linux/WSL）或 `dev.cmd`（Windows） |
| 后端测试 | `cd backend && pdm run pytest -p no:xdist` |
| 后端 Lint | `cd backend && pdm run ruff check .` |
| 后端格式 | `cd backend && pdm run ruff format .` |
| 前端类型检查 | `cd frontend && pnpm typecheck` |
| 前端 Lint | `cd frontend && pnpm lint` |
| 文档站开发 | `pnpm run docs:dev`（根目录） |
| 落地页构建 | 已移交 duoduobei-web，本仓不再构建（见 #918 块3） |
| 临时文件清理（dry-run） | `cd backend && pdm run python backend/scripts/cleanup_temp.py --file <path>` |
| 代码提交（dry-run） | `python scripts/commit_changes.py --files <...> --message-file <...>` |

---

*本文件为所有 AI / 开发者的强制性行为准则，与 `docs/spec/` 下的权威规范共同构成项目治理基础。如有冲突，以 `docs/spec/` 为准，但本文件中的硬约束（如分支、数据域、工具使用）优先级等同。*
