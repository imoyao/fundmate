# AGENTS.md

个人投资记账/家庭资产管理平台「多多贝」（fundmate）。前后端分离：后端 Flask/APIFlask（Python 3.12+），前端 Vue 3 + Vite（pure-admin），另有 VitePress 文档站与静态落地页。仓库文档均为中文，提交信息用中文 + conventional commits。权威规范在 `docs/spec/`（入口 `docs/spec/index.md`；`conventions.md` 为冻结区，变更须先在 `decisions.md` 记决策）。当前开发分支 `main-v2`（`origin/HEAD` 指向 `dev`，其余本地分支为历史遗留）。

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
- **内部备忘命名（强制，2026-08-09 起）**：`working-notes/` 下文件名一律英文 kebab-case + 日期后缀 `{topic}-{YYYY-MM-DD}.md`（如 `deployment-implementation-guide-2026-08-04.md`），**禁止中文文件名/路径**；正文标题用中文，交叉引用用相对链接 `./{english-name}.md`。新增备忘须同步登记进 `docs/working-notes/README.md` 索引表，防止历史中文命名债（`多多贝_*.md`）复发。
- 落地页：`pnpm run build:landing` / `build:about` / `build:story` / `build:pages`。`vercel.json` 构建时执行 `pnpm run build:landing`。
- Markdown lint：`pnpm run docs:lint-md`（CI 用 `npx lint-md docs`，不带 `-f`）。

## 一键启动

Windows：`dev.cmd`（内部走 `scripts/dev.ps1`）；Git Bash / WSL / macOS：`./scripts/dev.sh`（`--install` 重装依赖）。同时拉起后端 :8000 与前端 :8848。

## 本机提交环境（Windows）

- 提交走根 `.pre-commit-config.yaml`（ruff --fix + ruff-format，已 `pre-commit install` 生效）；前端 husky（lint-staged + vue-tsc）因 `ignore-scripts=true` 未安装，故 `vue-tsc` 须手动跑（见前端命令）。
- 若 pre-commit 崩溃报 `ACC_PRODUCT_CONFIG_V3` 超 32767 字符上限：commit 命令前先 `unset ACC_PRODUCT_CONFIG_V3` 再提交，勿用 `env -i`。
- 给用户看的命令行须兼容 Windows cmd（无 `head`/`cat`/`grep`/`sed`）：优先用项目自带脚本（如 `backend/scripts/diag_em.py`）或说明用 PowerShell 执行。
- **中文 commit message 编码（重要）**：提交信息一律走 UTF-8 文件 + `git commit --file`（见上「代码提交工具」），**禁止**在 PowerShell/cmd 内联中文（`Set-Content -Encoding UTF8` 会带 BOM，且 shell 引号易把中文当命令解析）。git 把 message 存为 UTF-8，在 GitHub/IDE 等 UTF-8 环境查看正常；**本机 GBK 终端 `git log`/`git show` 或 read_file 工具显示成「淇�」等乱码，是显示层 GBK 解码假象，不是真乱码**——可用 `git cat-file -p HEAD | python -c "import sys,os;raw=os.sys.stdin.buffer.read();raw.decode('utf-8')"` 严格 UTF-8 解码校验（成功即存储正确）。如遇 message 确为 mojibake，可设 `git config i18n.commitEncoding utf-8` 与 `i18n.logOutputEncoding utf-8`，但本仓库默认值即 UTF-8，正常走 message 文件即无需额外配置。

## 临时文件清理工具（所有 AI / agent 删除临时文件必须走此脚本）

**为什么（WHY）**：曾发现直接用 IDE / 编码助手的「删除文件」工具在部分环境下会被系统拦截或静默失败（报 workspace boundary / 调用异常），导致临时文件越积越多且删除动作不可靠。为绕开该限制并把「删除」这一破坏性操作统一收口，约定：**以后所有临时文件清理一律走 `backend/scripts/cleanup_temp.py`，不再依赖 IDE 删除工具**。它与「禁止武断执行」一节同源——删除必须先列清单给人判断、确认后才执行。

**工具位置与约束**：`backend/scripts/cleanup_temp.py`（自研，无第三方依赖）。
- 默认 **DRY-RUN**：只收集并打印「将要删除的文件」清单，**绝不真正删除**；
- 必须显式传 `--apply` 才真正删除；
- **删除前强制二次核验 git 跟踪状态**：对每个待删文件执行 `git ls-files --error-unmatch`，
  只有「未跟踪（含被 `.gitignore` 忽略）」的文件才会被删；已跟踪（源码 / 配置 / 文档 /
  入库资产）一律标 `[TRACKED-跳过]` 并**绝不删除**。这是防误删的最后一道闸，不可绕过。
- **精准优先**：AI / agent 应优先用 `--file <路径>` 逐项传入要删的精确文件清单，而不是依赖
  宽模式（如 `*.json` 曾误匹配到 `package.json` / `vercel.json` 等配置，已被二次核验拦截）；
- 默认只在白名单目录清理（仓库根 + `docs/working-notes`），不递归扫源码；可用 `--dir` 扩展（可多次）；
- 默认只匹配明确的临时文件名模式（`.tmp_*` / `_commit_*` / `_commit_msg_*` / `_cleanup_*`），可用 `--pattern` 追加（可多次）。

**操作 SOP（AI / 人通用）**：
1. 先 dry-run 看清单（默认即 dry-run，不传 `--apply` 不删）。清单中每个文件会标注
   `[untracked]`（可删）或 `[TRACKED-跳过]`（已跟踪，不会删）：
   - 推荐（精准）：`cd backend && pdm run python backend/scripts/cleanup_temp.py --file ../x.ps1 --file ../y.txt`
   - 或按模式：`pdm run python backend/scripts/cleanup_temp.py --pattern "_close*"`
2. 把打印出的「将要删除的文件清单」呈现给用户，说明要删哪些、为什么（临时调试 / commit /
   issue 产物，无业务价值），**等用户确认**；若清单里出现 `[TRACKED-跳过]` 项属正常（已自动排除）。
3. 用户确认后才真正删除：`pdm run python backend/scripts/cleanup_temp.py --file ../x.ps1 --apply`
   （或带自定义模式 `--pattern`）。
- 任何不在默认模式里的文件（如 `_decode_tmp.py`、`*.json` dump 等），用 `--file` 精确列出或
  `--pattern` 显式指定，且仍要先 dry-run 给用户看清单；
- **绝不用本脚本删除源码 / 配置 / 文档 / 入库资产**（如 `all_pb.csv`）；若二次核验失误，
  已跟踪文件也会被跳过，双重保险。
- 脚本顶部 docstring 含完整 WHY / HOW / SAFETY 说明，调用前可读。

## 代码提交工具（所有 AI / agent 提交代码建议走此脚本）

**为什么（WHY）**：通过 IDE / 远程通道提交时，`git commit` 常被系统弹「允许 / 拒绝」审批卡点拦截；人不在跟前时审批会超时或漏点，导致提交通过率极低。为把「提交」变成可判断、可无人值守的收口操作，约定：**AI / agent 提交代码优先走 `scripts/commit_changes.py`，与 `cleanup_temp.py` 同构（默认 DRY-RUN 展示、`--apply` 才执行）**。它不取代「AI 自动提交标注」等既有提交规范，只是把「跑什么命令」统一收口。

**工具位置与约束**：`scripts/commit_changes.py`（自研，纯标准库，跨平台，Windows 兼容）。
- 默认 **DRY-RUN**：只打印「本次提交干什么 + 提交哪些文件（含 git 状态 M/A/??）」+ 提交信息全文，**绝不真正提交**；
- 必须显式传 `--apply` 才执行 `git commit`；可选 `--push` 提交后推送；
- **精准优先**：优先用 `--files <路径>` 逐项列出要提交的文件（提交前会校验文件存在），
  不传则回退到「已暂存(staged)」改动；提交信息文件缺失时 dry-run 不报错、仅提示，apply 前必须准备；
- **提交信息走文件**：提交信息写在 UTF-8 文件（默认 `git/.git/COMMIT_MSG`，或 `--message-file`），
  由脚本经 `git commit --file` 传入，**禁止**在命令行内联中文（防 mojibake，与 Issue 创建同规则）；
- **永不 `--no-verify`**：pre-commit 守卫（`forbid_bp_input` / `guard_all_pb` / `guard_mojibake`）始终生效；
- 提交信息全文由调用方准备，须遵守本文件「AI 自动提交标注」与 conventional commits 约定（标注 `[AI 自动提交]` + `AI-Committed-By: <实际提交者>`）。

**操作 SOP（AI / 人通用）**：
1. 先 dry-run 看清单（默认即 dry-run）：`python scripts/commit_changes.py --files a.py b.py --message-file .git/COMMIT_MSG`。
2. 把打印出的「标题 + 提交文件清单 + 提交信息」呈现给用户，说明本次提交干了什么、涉及哪些文件，**等用户确认**（或按用户约定「小改动静默提交」规则处理）。
3. 用户确认后执行：`python scripts/commit_changes.py --files a.py b.py --message-file .git/COMMIT_MSG --apply`（如需推送加 `--push`）。
- 脚本顶部 docstring 含完整 WHY / HOW / SAFETY 说明，调用前可读。

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

## 架构与开发原则（所有 AI / agent 决策必须遵守）

核心精神：**追求极简、务实、长期可维护性**。这不是口号，是推翻具体技术选型时的兜底判据。

### 设计哲学
- **不保留向后兼容性**：废弃路径直接移除，不要留 `if legacy` / `deprecated` 分支 / 兼容垫片。旧方案死了就是死了，维护两套只会增加长期负担。
- **选择最简方案，避免过度抽象**：能用一个函数解决的，不抽三层工厂；能用现有依赖的，不复用轮子再造一个。抽象只在「同一逻辑真的出现 2–3 次以上」时才做（参照 #980 结论）。

### 开发流程
- **分层迭代，最小可用版本（MVP）起步**：先让最小闭环跑通，再逐步叠加功能。不为尚未完成的复杂功能牺牲当前产品的可用性与清晰度。
- 需求原子化拆分（见「Issue 原子化约束」）：一个 issue 只解决一类子问题，避免超长 issue 耦合关不掉。共享前置（如 `columnDefs` 数据模型）单独拆 issue 先落地，其余在其上叠加。

### 代码与依赖
- **保持组件模块化**：页面主文件控制行数（目标 ≤ 300 行，编排而非堆逻辑）；常量/枚举/纯函数/ Hook / 无状态组件按职责下沉到 `constants/` `utils/` `composables/` `components/`。
- **优先选用成熟第三方库，不重复造轮子**；**复用已有依赖，不盲目新增**（新增依赖需说明必要性，避免膨胀 `pdm.lock` / `package.json`）。

### 决策视角
- **以长期视角制定架构决策，拒绝临时的权宜之计**：能用一天 hack 解决但埋下技术债的，不取；宁可多花一步做对的事。外部数据源、跨域方案、存储选型等影响面大的决策，先评估长期维护成本再定。

### 与自选股池实时数据相关的约束（重要，避免返工）
- 实时股价 / 场外基金估值当前由前端 `frontend/src/utils/realtimeDataSources.ts` **JSONP 直连**天天基金（`fundgz.1234567.com.cn`）+ 腾讯财经（`qt.gtimg.cn`），封装链为 `realtimeDataSources.ts → valuationEngine.ts → useRealtimeQuotes.ts → 页面`。
- **任何「新增自选字段 / 统一整合外部数据源」的需求，必须先决策数据来源收口方式**：要么维持前端 JSONP（已绕过 CORS，但脆弱、无法服务端缓存/降级/限流），要么收口到**后端代理**（前端只调自家 `/api`，统一解决跨域、稳定性、降级，但需新建后端端点）。方案未定前不要散落地加接口调用。
- 新增行情/估值字段须复用既有 `realtimeDataSources.ts` 封装与 `useRealtimeQuotes` 的轮询/降级机制，禁止在页面里另起一套直连逻辑。
- 注意 #980（上帝页面拆分）进行中：自选 `index.vue` 当前约 2016 行且列仍是硬编码 `<el-table-column>`，`columnDefs` 数据驱动（#995）尚未落地。**新字段/新列需求应建立在 #995 的 `columnDefs` 之上，不要往硬编码模板继续堆列**，否则与拆分方向冲突、后期返工。

## GitHub Issue / Discussion / PR 创建规范（OpenCode 等自动化通道）

- 任何以 `imoyao` 账号通过 `gh` / REST API / 脚本创建 issue、discussion、PR 的自动化通道（含 OpenCode、远程 agent），**必须在 UTF-8 环境下运行**：shell 先 `export LANG=C.UTF-8; export LC_ALL=C.UTF-8`；Python 设 `PYTHONUTF8=1`，禁止用 `latin-1`/`ascii` 编解码中文。
- 中文标题/正文**用文件传**：`gh issue create --title-file <f> --body-file <f>`（文件 UTF-8 无 BOM），避免内联中文变量在非 UTF-8 终端里被吞成 `?`。
- 创建后必须回读校验：`gh issue view <n> --json title` 确认中文无 `?`、无 `Ã`/`Â` 类 mojibake；出现则视为创建失败，立即删掉重建，**严禁保留乱码 issue**。
- 复盘：2026-08-09 的 #859–#862 因创建环境非 UTF-8，中文标题全变 `?`（如 `?????(?? Discussion #152 ????)），已改写成干净中文 issue。完整规则见 `docs/working-notes/opencode-github-issue-utf8-rule-2026-08-09.md`。

## Issue 原子化约束（对所有 AI / agent 生效，含 OpenCode、远程 agent）

**核心目标：一个 issue 只承载一件事，相关 issue 用引用串联，避免把不相关的内容耦合进同一个超长 issue，导致后期难以关闭、难以定位。** 这是 2026-08-12 由用户提出、经复盘"issue 越长越耦合、关不掉"的痛点后确立的硬规则。

- **一个 issue 一件事**：创建前先问"这个 issue 想解决/记录的具体是哪一件事？"如果是多件事（如"改 logo + 改品牌名 + 改 jigu 链接"），**拆成多个独立 issue**，不要塞进一个。标题应精确描述该单一事项（例：`docs: jigu header 新增多多贝首页链接` 而非 `jigu 品牌改造一堆事`）。
- **关联靠引用，不靠合并**：若几个 issue 之间有依赖或上下文关系，在正文里用 GitHub 引用语法（`#915`、`#859`）互相 `@`/引用，而不是把内容复制粘贴到一起。读者顺着引用即可拼出全貌，无需读一个巨型 issue。
- **追加请续帖，不要重写**：在已有 issue 上补充新结论/新约束时，**追加评论（comment）**，绝不用 `gh issue edit` 覆盖原正文（原 #915 即因多次追加评论而保留完整演进脉络）。若补充内容属于"另一件事"，另开 issue 并引用原 issue。
- **超长即拆分信号**：当一个 issue 的评论或正文已明显混入第二、第三件不相关的事，应立即新建独立 issue 承接新事项并引用回原 issue，保持原 issue 聚焦于最初那一件事。
- **关闭即终点**：仅当该 issue 对应的那一件事真正完成才可关闭；不要因为"顺手把别的事也做了"就连带关闭关联 issue——各自独立关闭。

## 禁止武断执行（对所有 AI / agent 生效，含 OpenCode、远程 agent）

**核心铁律：不要望文生义、不做判断就直接执行。** 任何涉及「删除 / 移除 / 覆盖 / 丢弃」类破坏性操作（删文件、删 issue、删看板条目、删讨论、撤销改动等），**必须先核实内容价值，再决定处置方式**：

- **删除前必须读内容、做判断**：绝不允许仅凭表面现象（如"issue 已关闭"＝"看板过期"、"草稿"＝"无用"、"旧文档"＝"该删"）就武断删除。已关闭 ≠ 无用，过期 ≠ 无价值。
- **高价值内容一律归档，不删除**：竞品调研、数据源清单、路线图、设计基线、架构讨论、历史笔记等即使 issue/讨论已关闭，也属长期参考资料，应**打 `归档` 标签 + Status=Done 保留在看板**，而非移出或删除。
- **"拉平 / 重构看板 / 整理"≠"清空"**：整理任务的目标是让活跃项与归档项各归其位（双维度分组），不是把"不顺眼的"删掉。判断不清时，宁可保留、标注待确认，也不可擅自删除。
- **破坏性操作三问**：① 这东西的内容我读过了吗？② 它是否还有参考价值 / 是否已被代码实现？③ 删了能否恢复？三个问题有一答不上，就先不动，向用户确认。
- **复盘案例**：2026-08-09 整理 GitHub 看板时，曾因"看板过期"望文生义，误删 5 个高价值已关闭 issue（#237 竞品库、#429 导入导出设计、#588 温度数据源、#661 自选实现、#769 路线图）及 2 个项目草稿，事后已恢复 5 个并打 `归档` 标签。此为反面教材，禁止重犯。

## Issue 优先级与 Project 看板（所有 AI / agent 必须遵守）

**优先级标识已存在，禁止新建字段**：本仓库 GitHub Project「多多贝·投资账本」（编号 3，id `PVT_kwHOAV6ff84AAot3`，owner `imoyao`）已内置 **`象限`** 字段承载紧急程度/优先级，选项为：

- **Q1:RED** — 重要且紧急
- **Q2:YELLOW** — 重要不紧急
- **Q3:GREEN** — 紧急不重要
- **Q4:GRAY** — 不重要不紧急

另有 `Status`（Todo / In Progress / Done / Pending）、`Milestone`、`Labels` 等标准字段。**创建/处理 issue 时务必用 `象限` 字段标优先级，不要另建 priority / 紧急程度 类字段**（避免字段膨胀、与现看板脱节）。给 issue 打象限：先 `gh project item-add 3 --owner imoyao --url <issue-url>` 加入看板，再用 `gh api graphql` 的 `updateProjectV2ItemFieldValue`（变量类型用 `ID!`）写 `singleSelectOptionId`（Q1=`84f4167a` / Q2=`2aead21d` / Q3=`3ea6e338` / Q4=`d3517118`，field id=`PVTSSF_lAHOAV6ff84AAot3zhaGpdo`）。

**issue 治理纪律（2026-08-12 确立，已落地）**：
- 产品路线图 / 未来设想 / 历史参考类 issue **不要以 OPEN 占用注意力**：打 `归档` 标签并关闭（**不删除**，内容保留可查），并引用路线图索引 **#920**（索引型 issue，只列清单与引用，不承载实现）。
- 高价值 active 类（已落地备忘 / 强相关待办）保留 OPEN，不收纳。
- 治理结果：OPEN 由 70 收敛至 44；FeedLog Roadmap 看板须待反馈站部署（#919）后打通（见 #919 阻塞项说明）。
- 以上与「Issue 原子化约束」「禁止武断执行」两节同源，互为补充。

## AI 自动提交标注

- 所有由 AI 助手（CodeBuddy / OpenCode / 远程 agent 等）**主动提交**，或**经用户指示由 AI 提交**的代码改动，必须在提交信息中明确标注其为 AI 自动提交，便于后续追溯哪些提交由 AI 完成、区分人工提交。
- 标注方式：在 conventional commit 标题与正文之后，追加 footer：
  - 标记行：`[AI 自动提交]`
  - trailer 行：`AI-Committed-By: <实际提交者>`
- **trailer 必须如实填写本次提交的实际 AI 工具身份，禁止一律写成 `CodeBuddy AI`**：由 CodeBuddy 提交的填 `CodeBuddy AI`；由 OpenCode 提交的填 `OpenCode`；由其它远程 agent / 通道提交的，填该 agent 的真实标识（如 `Remote Agent`、`ClawBot` 等）。谁提交就署谁的名，不要把别的工具的提交也记到 CodeBuddy 账上。
- 示例（CodeBuddy 提交）：

  ```text
  docs: 新增经16Traders授权转载博客（4篇结构重组版）

  经 16Traders 书面授权转载，正文高保真+结构重组，对比数据用 Markdown 表格呈现。

  [AI 自动提交]
  AI-Committed-By: CodeBuddy AI
  ```

- 示例（OpenCode 提交）：

  ```text
  fix: 修复温度计基线守卫误判

  [AI 自动提交]
  AI-Committed-By: OpenCode
  ```

- 适用范围：所有分支；**人工提交的改动无需标注**。AI 提交仍须遵守本文件其他约束（conventional commits、pre-commit、勿绕过守卫等）。

## AI 编码防乱码规则

- **所有包含中文的文本文件（`.md`、`.py`、`.vue` 等）必须保存为合法 UTF-8，且内容确实为可读中文（不能是"GBK 被误当成 Latin-1 解码后再存为 UTF-8"的二次编码乱码，即 mojibake）。**
- AI 在生成/写入含中文的源文件时，必须确保：
  - 写入编码为 UTF-8（with or without BOM 均可，但内容须可读）。
  - 写完后不要再用非 UTF-8 编码（如 GBK/Latin-1）重新解码一次。
  - 如果用脚本或管道拼接生成文件内容，确保整个链路是 UTF-8 端到端的。
- **提交前 pre-commit 守卫 `guard_mojibake.py` 会拦截疑似乱码文件**：检测策略为"含大量 CJK 字符但完全不含高频常用汉字则拒绝提交"。禁止 `--no-verify` 绕过此守卫。
- **复盘**：2026-08-09 一批 26 个 `legacy/` 前端重构笔记（`.md`）由远程 agent「Claw」写入时编码错误，全部变为不可读乱码（`文档导航` → `鏂囨。瀵艰埅`），无干净副本可还原。此为反面教材，所有 AI 工具必须遵守本规则，防止重犯。
