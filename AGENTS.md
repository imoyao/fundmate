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
- [前端交互修复：判据与验证](#前端交互修复判据与验证强制2026-10-06)
- [文档站与落地页](#文档站与落地页)
- [核心约束](#核心约束)
- [数据域架构（双引擎硬规则）](#数据域架构双引擎硬规则)
- [数据策略（按需存、禁止全量堆砌）](#数据策略按需存禁止全量堆砌)
- [双端协作（CNB ↔ GitHub）](#双端协作cnb--github)
  - [规则的生命周期：写进 AGENTS.md 不等于会被执行](#规则的生命周期写进-agentsmd-不等于会被执行2026-10-16)
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

**两种 PR，两种 base，没有第三种**（2026-10-11 明确，源自 CNB #123）：

| PR 类型 | base | 说明 |
|---|---|---|
| 功能 / 文档分支 PR | **`dev`** | 默认情况。从 `dev` 切分支，合回 `dev`。 |
| 发布 PR（`dev` → `main`） | **`main`** | 「发版」这一个动作，不做别的事。 |

- 除此之外**一律 base=`dev`**。看某个 PR 的 base 是不是 `main`，判据只有一个：
  **它是不是「把 `dev` 整体合回 `main`」的发版 PR**（head 就是 `dev` 自己）。
  head 是 `feat/*` / `fix/*` / `docs/*` 等功能分支、base 却填了 `main` ⇒ **错**，即使理由听起来合理。
- **不要因为「这个改动需要尽快生效」就把 base 改成 `main`**。它属于「该发版了」，
  正确做法是单独开一张发布 PR，把要生效的一批改动一起带过去——
  否则 `dev` 会被绕过，`main` 与 `dev` 各自长出对方没有的提交（CNB 侧 #123 实测已发生：
  `main` 独有 9 个提交、`dev` 独有 29 个，两边**互不包含**）。
- **CNB 镜像仓（`duoduobei/fundmate`）没有例外条款**：它同样只有 `dev` / `main` 两条长期分支，
  镜像脚本的改动照走「功能分支 → `dev`」。它曾因「cron 挂在 `main`，所以改动得直接进 `main`」
  连续 5 个 PR 以 `main` 为 base（#114 / #122 / #124 / #126 等），导致上面的分叉。
  **cron 挂在哪个分支，不构成绕过 `dev` 的理由**——正确做法是改变更分支 + 及时发版，
  见下方「CNB 镜像链路的挂钩分支纪律」。
- AI review（免费 GLM 总结 + 智能路由深度）自动在 PR 上评论。

#### CNB 镜像链路的挂钩分支纪律（2026-10-11，#123）

`duoduobei/fundmate` 的镜像作业由 `.cnb.yml` 的 cron 驱动，而 **CNB 的 `crontab` 事件只能挂在具体分支下**
（不能放 `$` 兜底）。这条平台限制带来一个真实约束，但它**不改变 base 的填法**：

- **改动照常提 `dev`**（`docs(bridge):` / `feat(bridge):` 等），不因为「要跑 cron」而改 base；
- **要生效就得发版**：cron 读的是 `main` 上的那版脚本，所以功能分支合入 `dev` 后，
  需要另开一张 `dev` → `main` 的**发布 PR**，让镜像改动真正落地；
- **发版前镜像作业跑的是旧脚本**，这是需接受的窗口，**不是**「所以我要直连 `main`」的许可证。
  改 base 只会把「旧脚本还跑着」变成「新旧代码在两处、且互不包含」——更难收拾；
- **判据（2026-10-14 二次修正，源 CNB #179）**：**发版滞后本身不是故障**。

  | 形态 | 判定 |
  |---|---|
  | `main` 独有提交是**发版 merge**（第二父是 `dev` 的祖先） | ✅ 正常（`main` 停在上一发版点） |
  | `main` 独有提交是**普通提交**，或 merge 的第二父不是 `dev` 的祖先 | ⚠️ **纪律违规**：有人绕过 `dev` |
  | `git cherry origin/dev origin/main` 有 `+` 行 | ⚠️ `main` 上有 `dev` 拿不到的改动 |

  ⚠️ **不要**把「`main` 独有提交数 > 0」当分叉判据：本仓发版后 `main` 必然多一个
  merge commit，且 `dev` 继续前进 ⇒ `main` 既不领先也不是 `dev` 的祖先。拿它报红
  就是**每次都喊狼来了**，红灯随之失去可信度。判据要二分，不要数数。

- **判据机器化**：已固化进 `scripts/bridge/check_branch_divergence.py`
  （只读本地 git、不联网），并挂进 `.cnb.yml` 的收尾阶段（**断链即建卡**，stage 不拦构建）：

  ```bash
  python scripts/bridge/check_branch_divergence.py --report   # 退出码 1 = 有新形态
  ```

  ⚠️ 内容级判据用 **`git cherry`（补丁等价）**，**不是** `git diff`：
  交叉合并（`main` 合过 `dev`、`dev` 又前进）下 `diff` 非空但 `main` 零独有内容，
  用 `diff` + 祖先关系会**假红**（2026-10-14 实测 7 个文件全是假阳性）。
  「拿不到输入」（`git cherry` / `git log` 失败）一律按红，**不得**降级成正常。

  ⚠️ **两个旧口径都产生过假红**，别再走回去：

  | 旧口径 | 为什么会误报 |
  |---|---|
  | ①「`main` 独有提交数 > 0 ⇒ 分叉」 | 发版 PR 必然给 `main` 留一个 merge commit 而**不引入内容** ⇒ 每次正常发版都红一次 |
  | ②「`git diff main dev` 非空 ⇒ 分叉」 | `diff` 是**双向**的，「`dev` 领先、`main` 停在旧版」也非空 ⇒ **假红** |

  ⚠️ 也**不要**改用「逐文件查 blob 历史」（`git log --find-object`）来绕开 ②：
  它只看得见「`main` 侧**存在**的路径」，`main` 上**纯删除**的改动会被跳过 ⇒ **假绿**
  （`main` 合过 `dev` 后又删了一个 `dev` 里还在的文件、`dev` 再前进 ⇒ 逐文件法报
  「两侧内容一致」，而 `git cherry` 报 `+`，是真违规）。判据只用
  **`git cherry <dev> <main>`（补丁等价）**，详细推导见 `docs/dev/github-cnb-mirror.md` §11。

  **退出码不吞**：分叉时 `.cnb.yml` 用非零退出码触发 `notify_mirror_divergence.py`
  建一张断链提醒卡（幂等，标题即幂等键）——crontab 的红灯没人盯，
  只进日志等于静默停摆。stage 整体仍不拦构建（建卡才是主任务）。
  成因侧另有 `pull_request` 反向守卫挂在 `main:` / `dev:` 之下（CNB 侧只读，直接 `exit 1`）。
  自检报红时，第一怀疑对象是「有 PR 用错了 base」——CNB #123 实测：base 用错
  ⇒ 两侧互不包含、且每层判据都可能报红，先查 base 能省掉一整轮排查。

#### git-sync **两个方向**都必须显式指定 `branch`，且不含 `main`（2026-10-13 ~ 10-14，#167 / #172）

**口径（用户 2026-10-14 在 CNB #167 明确）**：

> **CNB 的 `main` 与 GitHub 的 `main` 没有任何关系。** CNB `main` 只由 CNB 自己的发版 PR
> （`dev` → `main`）推进——**既不外推给 GitHub，也不被 GitHub 覆盖**。
> CNB 的 `dev` 推给 GitHub `dev` 可以；CNB 从 GitHub 拉代码也可以。
> 一句话判据：**CNB `main` 不得有 `dev` 没有的代码**（发版 merge commit 除外）。

两个方向各有一个「不写 `branch` 就会碰 `main`」的陷阱：

| 方向 | 不写 `branch` 时插件干什么 | 后果 |
|---|---|---|
| **push** | `git push <target> --all` | 把 CNB 的 `main` 一并推给 GitHub ⇒ 两侧 `main` 分叉（2026-10-13 实测 CNB 31 / GitHub 27，交集 0） |
| **pull** | 取 target **全部**分支，逐个 `pull --rebase` 后 **`git push origin <b> --force`** | **GitHub 的 `main` force 覆盖 CNB 的 `main`**（不看是否 fast-forward） |

- ⚠️ **「pull 只拉不推、不会分叉」是直觉错误**（2026-10-14 读插件 `entrypoint.sh` 实测）：
  pull **总会** `git push origin --force` 写回本地 origin；不写 `branch` 时遍历 target 全分支。
  **故 pull 也必须写 `branch: dev`**（此前 #172 那句「拉取方向不写 branch 是对的」已作废）。
- **四处都要写**：`push:`（推 dev）/ `crontab: 30`（兜底推 dev）/ `"**/!(main|dev)"`
  （`branch: ${CNB_BRANCH}`，推当前功能分支）/ `crontab: 0` 的 **pull（拉 dev）**。
- **判据机器化**：`python scripts/guard_git_sync_push_scope.py`（并入 `ci.yml` 的
  `layout_guard` job，阻断），覆盖两个方向的四条判据；回归网
  `scripts/tests/git_sync_push_scope.test.js`（含 **5 个**变异探针：push 三种 + pull 两种）。

#### `crontab` / `push` 下必须写成「job 列表 + 命名 stage」（2026-10-13，#167）

把 `stages:` **直接**挂在 `"crontab: ..."` 下（没有 `- name:` 包一层 job 对象）时，
stage 在 `get-build-stage` 里**查不到** ⇒ 作业内部推没推成功看不出来。
`crontab: 30` 因此长期「挂旧 sha、实际没推上去、却报绿」——**假绿比红灯更危险**。
两条 cron 与 `push:` 一律写成 `- name: <job 名> / stages: [ - name: <stage 名> ]`，
job 名与 stage 名都要写（后者是查询锚点）。

#### `.cnb.yml` 的事件写在分支下，不写顶层（2026-10-11，#152）

同一条平台限制的另一面，且**更容易踩**：`.cnb.yml` 的**顶层只认分支名**（与 `$`）。
事件（`push:` / `"crontab: ..."` / `web_trigger:`）必须写在**分支之下**。

写成顶层不会报「位置错」，而是被读成**一个名字叫 `push` 的分支**——随后报错形态全错位：

- `GetFileContent: not found` = **事件无定义**，不是「文件不存在」（平台拿默认分支的定义兜底）；
- 同一次事故里 `parse yaml failed` 又是另一件事（定义后来长出来、才轮到读文件内容）。

两者看着像「同一件事的两个阶段」，实际是两个独立原因——2026-10-11 连续 7 条流水线全红
就是被这两句话各带偏一次，注意力全在 `fundmate-secret`（Secret 仓库，API 一律 403），
而真正要改的是 `.cnb.yml` 的缩进。

- **判据机器化**：`python scripts/check_cnb_events.py`（并入 `ci.yml` 的 `scripts_test` job，
  阻断），回归网 `scripts/tests/branch_structure.test.js`；完整推导见
  `docs/dev/github-cnb-mirror.md` §12。
- **守卫白名单只能是单值键**：把 `main` / `dev` 写进「允许的顶层键」会让任何分支名都合法、
  判据当场失效。守卫自带自检探针（用真实存在的 `sync/mirror:` 反证）。

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
│   │   ├── views/          # 页面组件（路由须在 router/modules 手工注册，name 与路由名一致）
│   │   └── ...
│   ├── package.json        # 前端依赖（pnpm 强制）
│   └── pnpm-lock.yaml
├── docs/                   # VitePress 文档站（根目录 package.json 管理）
│   ├── .vitepress/
│   ├── spec/               # 规范（conventions.md 冻结区）
│   └── working-notes/      # 内部备忘（全局屏蔽，文件名须英文 kebab-case + 日期后缀）
├── scripts/                # 根目录脚本（提交工具、守卫、文档/前端审计等）
├── site/                   # 主站共享资产（style.css, logo.svg 必须入库）
├── package.json            # 根目录：仅文档站依赖（落地页脚本已随移交移除）
├── wrangler.toml           # Cloudflare Pages 配置（应用站备线，输出 frontend/dist）
└── vercel.json             # Vercel 配置（应用站兜底：frontend/ 构建 + SPA 回退）
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
| 测试 | 后端 pytest（**必须单进程**，因 xdist 多 worker 导致 OOM）；前端 Playwright E2E（`pnpm test:e2e`，**不进 per-PR 门禁**，见 `docs/dev/frontend-e2e.md`） |
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
  - `core/v8_guard.py`：`py_mini_racer` 并发构造守卫（进程级锁 + 启动预热），防止 akshare
    并发取数触发 V8 Fast Fail 硬杀后端（#1566；不要绕过它去「修」各调用点）。
  - `core/instance_guard.py`：**同一 DB 的 web 单实例守门**（`data/app_instance.lock`，排在
    `init_db()`/迁移之前）。SQLite 只允许一个写者，多实例共享同一库会让写请求等满
    `busy_timeout` 后报 `database is locked`；Windows 的 `SO_REUSEADDR` 还会让第二个
    `flask run` **不报端口占用**、静默多起一个实例（#1809）。冲突实例以**退出码 4** 退出，
    持有者 PID 记在 `data/app_instance.owner`；`APP_INSTANCE_GUARD=0` 可显式关闭。
    **退出码不能用 3**：3 是 werkzeug 重载器「请重载」的哨兵，冲突退 3 会让父进程无限
    拉子进程刷屏（#1810 初版即踩中，#1816 修正）。配套两道防线：重载父进程**只探查不持锁**，
    锁被占即在 `init_db()` 之前退出；`main.py` 导入期置
    `BaseWSGIServer.allow_reuse_address = False`，让第二个实例直接死在绑端口
    （打印 `Port <n> is in use by another program.`），同样见 #1816。
- **服务层**：
  - `services/sync/`：同步编排器 + 各 `SyncJob` 实现（编排/注册类）。
  - `services/adapters/`：第三方数据适配层（xalpha / akshare / 东财直连 / 韭圈儿 / 各投顾平台）；
    与 job 家族无关，跨家族共享（#1607 批次 3 从 `sync/adapters/` 上提）。
  - `services/job_base.py`：任务基类 `SyncJob`（sync / thermometer / bias 共用，**不属任何家族**）。
  - `services/import_records.py`：导入标准化记录（解析器 / `position_service` / OCR 共用）。
  - `services/thermometer/`：温度计（含全 A 中位 PB 历史基线）。
  - `services/bias/`、`importer/`、`performance/`（XIRR）。
  - `services/daily_scheduler.py`：本机常驻每日调度（进程内 APScheduler；自选/持仓净值 + 温度计，#1467）。
- **同步入口**：两套 CLI（`pdm run invoke grab.*` 和 `pdm run sync --job`），共用 `DataSyncOrchestrator`。
  **本机常驻**另有两条路：`.env` 置 `SCHEDULER_ENABLED=1` 随应用启动，或 `pdm run scheduler-daemon`
  独立守护（同机靠单实例锁只跑一份）；详见 `docs/dev/scheduler-tasks.md`。
  - **`--full-sync` 必须带范围（#824 / #1776 ④）**：逐标的回填型 job（`fund_nav` / `price_history` /
    `fund_detail_enrich` / `fund_manager` / `fund_type` / `fund_company_backfill` / `fund_position` /
    `position_price` / `dividend_split`）裸 `--full-sync` 由 CLI 直接拒绝（`sync/orchestrator.py` 的
    `SYMBOL_BACKFILL_JOBS` + `require_full_sync_scope`，接入 `sync_metadata.py` / `sync_cli.py`），
    必须配 `--targets <code>[,<code>...]` 或 `--target-file <csv>`（全市场逐标的全量回填会触发数据源封禁
    且耗时以小时计）；`--all --full-sync` 同样必须带 `--target-file`。列表型（`fund_list` / `stock_list`）/
    指数型（`index_*`）/ 温度计型 job 单次调用换全市场，裸 `--full-sync` 为其正常模式，不受限。
  - **基金净值止于 T-1（#824）**：`fund_nav_job._validate_data` 丢弃 `date >= today` 的记录——净值发布有
    滞后，T 日 / 未来净值尚未成立，不得入库。
  - **初始化/重建走 DB 快照，不走全市场拉取（#1776 ⑤）**：`pdm run sync --snapshot <path>` 导出市场域
    只读快照（31 张市场域表 + `snapshot_meta`，**不含用户私有数据**、排除 `sync_logs`），文件分发给用户后
    `pdm run sync --import-snapshot <file>` 本地导入（校验 magic / meta / 表白名单，按本地唯一约束
    `INSERT OR IGNORE` 幂等去重，不覆盖本地记录）。实现见 `services/sync/snapshot.py`，设计见
    `docs/working-notes/db-download-import-2026-08-09.md`。

### 日志（2026-08-09 统一）

- 所有新代码必须使用 `from loguru import logger`，**禁止**新增 `import logging`。
- 唯一例外：`app/__init__.py` 的 `InterceptHandler` 基类需要。
- 第三方库的 stdlib 日志由 `InterceptHandler` + `logging.basicConfig(force=True)` 接入 loguru。
- loguru 0.7.3 维持不变（structlog 学习曲线陡，logbook 已停滞）。

### 测试

- 命令：`pdm run pytest -p no:xdist`（单进程，防 OOM）。
- 夹具：`tests/conftest.py` 提供 `app`/`client`/`db`/`make_position` 等。
- **测试库既不是内存库、也不是复用的持久化库**：是**每用例一个临时文件**
  （`tmp_path/_fixture_app.db` + `_fixture_market.db`，用完即删），另有一个按源码指纹
  缓存的「完成态模板库」供 `shutil.copyfile` 秒级落地（#1722）。
  - 2026-09-27 起从 StaticPool 内存库切到文件库（#1721）：单连接下 B 会话 `close()`
    的 rollback 会连带回滚 A 的**未提交**写，生产不可能出现，却稳定制造
    `StaleDataError` 假阳性。shared-cache 内存 URI 也试过，表级锁导致
    `database table is locked`。完整三轮踩坑见 `conftest.py` 的 `_make_file_engine` docstring。
  - 想「改回内存库」前先读那段 docstring，别重复已否决的方案。
- **禁止**直接导入 `SessionLocal`（须用 `conftest` 夹具）。

- **本 worktree 的 `backend/.venv` 是空壳**（`pdm run` 会新建一个无依赖的 venv，
  `import sqlalchemy` 直接失败）。跑后端测试/ruff 用**主仓解释器**，不要用 `pdm run`：
  `D:/codes/fundmate/backend/.venv/Scripts/python.exe -m pytest <paths> -p no:xdist -q`
  （主仓路径以 `git rev-parse --git-common-dir` 上溯为准，此 worktree 实测为
  `D:/codes/fundmate`；换 worktree 前先重新确认，别照抄路径）。
- **默认不在本地跑全量测试，交给 CI**（`gh pr checks <pr>`）。实测同一份代码本地全量
  约 **2h40m**、CI 约 **8min**（原因未查清，勿编）。本地只跑**与改动直接相关**的测试
  文件（分钟级）；跑不完就推 CI，**不要**为凑「本地全绿」挂几小时的任务。

### 常用后端命令（`cd backend`）

| 目的 | 命令 |
|------|------|
| 安装依赖 | `pdm install`（含 dev 组：`pdm install -G dev`） |
| 运行 API | `pdm run flask --app app.main:app run --debug --host 0.0.0.0 --port 8000` |
| 测试 | `pdm run pytest -p no:xdist`（或 `pdm run invoke test`） |
| 同步任务 | `pdm run invoke grab.temperature` / `grab.all` / `grab.job <name>`<br>或 `pdm run sync --job temperature` |
| 全量回填 | `pdm run sync --job <name> --full-sync --targets <code>[,<code>...]`（或 `--target-file <csv>`）——逐标的回填型 job（`fund_nav` / `price_history` 等）**禁止裸 `--full-sync`** |
| 本机每日调度 | `pdm run invoke sched.status`（状态，只读）<br>`pdm run scheduler-daemon`（常驻守护，Ctrl+C 退出） |
| Lint & Format | `pdm run ruff check .` / `pdm run ruff format .` |
| 诊断东财抓取 | `pdm run python scripts/diag_em.py` |

---

## 前端开发

### 架构概览

- **路由**：由 `src/router/modules/*.ts` **手工注册**（每页一个模块文件）；`src/router/utils.ts` 的 `import.meta.glob("/src/views/**/*")` 仅用于按路径反查组件，**不自动生成路由**（`handleAsyncRoutes([])`，glob 结果未注入，#1703 实证）。新建页面须保证 `defineOptions.name` 与路由 name 一致（否则 keep-alive 失效）。
- **接口**：集中在 `src/api/`，按域划分，组件内**禁止**裸 axios。
- **登录**：Supabase Auth（`@supabase/supabase-js`），后端校验 JWT；登录/登出/路由守卫已配置。
- **新增页面路由**：`src/views/` 下的组件**不会**自动成路由，须在 `src/router/modules/` 新建模块文件注册（参考 `modules/agent.ts`，含 `meta.requiresAuth` 等）。
- **设计语言**：亮色 `frontend/design.md`，暗色 `design.dark.md`，**禁止硬编码 hex 色值**，必须使用 CSS 变量（`--color-rise`/`--color-fall` 等）。
- **强制复用组件**：清单在 `docs/design/components.md`（`SectionHeader` / `CardBlock` / `MetricCard` / `SegmentedControl` / `PageHeaderBar` 等），**禁止各页面重写同类结构**。其中**分段控制器只有 `SegmentedControl` 一个实现**：禁止页面再用 `el-segmented`（其选中滑块是 JS 绝对定位的独立子元素，几何与轨道各算各的，且带 `transition: all .3s`，每次点击都滑动/缩放一次——#1717 的根因），也禁止页面自写 `.xxx-segmented` 样式块。静态守卫 `scripts/guard_segmented.py`（并入 `layout_guard` job）拦截这两类回潮；其边界是**只拦 `-segmented` 命名**，`role="tablist"` 但另起名字的手写按钮组不在其内。

### 常用前端命令（`cd frontend`）

| 目的 | 命令 |
|------|------|
| 开发 | `pnpm dev`（端口 8848，`/api` 代理到 `http://127.0.0.1:8000`） |
| 类型检查 | `pnpm typecheck`（`tsc --noEmit && vue-tsc --noEmit --skipLibCheck`） |
| Lint | `pnpm lint`（eslint + prettier + stylelint） |
| 构建 | `pnpm build` |
| E2E（前端） | `pnpm test:e2e`（Playwright；自带 dev server 端口 **8849**，不依赖后端与真实 Supabase，见 `docs/dev/frontend-e2e.md`） |
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

## 前端交互修复：判据与验证（强制，2026-10-06）

> 本节来自 #1830–#1842 排查、#1845 / #1883 / #1890 / #1891 / #1892 / #1896 六轮修复的复盘。
> 那一批问题里，**同一类形态反复出现三次**（`initialSnapshot = ref("")` 拿空串当基线、
> 成功路径不复位、宿主没接线），每一次的发现方式都相同：**先扫全仓，再逐处核实**。

### 一、加「未保存离开保护」前先答三问

扫描出「有录入 UI 但无守卫」的组件后，**不要直接加守卫**。按顺序核实这三问，任一命中就**不要加**：

| 问法 | 命中则 | 为什么 |
|---|---|---|
| **1 数据归谁管？** | 数据在别的 composable / context 里 → 不加 | 数据不在自己手里，守卫拦不住也不该拦。`CreateLedgerDialog`（#1897）字段全来自 `useImportWizardContext()`，纯展示组件 |
| **2 有草稿 / 自动保存吗？** | 有 `persist` / localStorage / draft → 不加 | 丢了能恢复，守卫是多余的打断。`EaccountManualPanel` 的 `useEaccountImport` 有 `draft` ×21 / `persist` ×5 |
| **3 关闭路径是显式的吗？** | 只有显式「取消 / 保存」→ 不加 | 静默丢失才需要拦。`RoadCardEditor` 无「点外部收起」，用户点的是有字的按钮，天然知道会丢 |

**反过来，三问都不命中就必须加**——`EditAccountDialog`（#1896）就是这样：数据自己管、
无草稿、13 个字段且弹窗可点遮罩关闭。更糟的是它**自己写了一份 `editFormSnapshot` 比较却只用来
禁用保存按钮**，没有任何人读它，于是「改了费率配置点关闭」全程静默丢弃。

> **判据是「数据归谁管」，不是「有没有守卫」。** 同一份 `AccountFormFields` 的三个宿主，
> 两个需要守卫、一个不需要——差别在数据归属，不在代码长相。

### 二、守门要分两层，组件层抓不到「宿主没接线」

`#1891` 那一页整块漏了守卫，但三个表单组件**本身都没问题**——问题是**没人读它们的 `isDirty`**。
组件层守门（断言 `isFormDirtyJson` 语义、断言组件用了共享 helper）**对此完全无能为力**，
因为出问题的不是组件，是宿主有没有把 `isDirty` 接进守卫。

所以新增「未保存」类守门时，**必须同时覆盖两层**：

- **组件层**：脏基线语义（`baseline === null` 视为不脏）、用共享 helper 不手写快照比较；
- **接线层**：宿主必须调 `useUnsavedChangesGuard`，且脏状态要真的读到了子组件的 `isDirty`
  （只断言 `isDirty` 存在不够——它可能像 `EditAccountDialog` 那样只被用来禁用按钮）。

接线层的断言要按**复用关系**枚举，而不是按文件：`AccountFormFields` 的三个宿主、
快速录入的三个表单，都要在名单里；名单扩到新成员时守门要一起扩。

### 二之二、弹窗类：只调 composable 不够，四路要各自接上（2026-10-06 踩过）

`useUnsavedChangesGuard` 内部的 `onBeforeRouteLeave` **只覆盖「路由离开」**那一路。
弹窗还有两路，必须调用方自己接：

| 路 | 谁接 | 不接的后果 |
|---|---|---|
| 路由离开 | composable 内部自动 | — |
| **关闭按钮 / ESC / 点遮罩** | 调用方挂 `:before-close="onBeforeClose"` | **点 × 直接关掉，数据静默丢失** |
| **底部「取消」等程序化 close** | 调用方包 `requestClose(close)` | 同上（程序化 close 走不到 `before-close`） |

#### 最容易犯的错：把「关闭时复位基线」当成拦截

`#1898` 就是这么错的，原话写在 PR 里：

> 「底部「取消」是程序化 `emit('update:visible', false)`，走不到 `before-close`，
> 但 `fillOnOpen(false)` 已在关闭时复位，两条路都覆盖到。」

**`fillOnOpen(false)` 跑在 `watch(props.visible)` 里——弹窗已经关了之后才复位基线。**
它的作用是「让**之后**的离开不再弹确认」，**阻止不了这次关闭**。把它当拦截手段，
结果就是：用户改了字段点 ×，弹窗直接关、数据没了，而 composable 内部那条路根本没被触发。

修法（`#1901` 补的）：`:before-close="onBeforeClose"` + 底部按钮
`@click="requestClose(() => emit('update:visible', false))"`。

#### 判别口诀

**「这个操作会让弹窗关掉吗？」** —— 会，就必须在**关闭之前**问。
在关闭之后执行的任何复位、清理、重置，都不是拦截。

### 三、守门通过 ≠ 守门有效：必须用探针自检

新写/改判据后，**跑一次绿不算数**。要临时注入一次回退，确认守门真的会红：

```powershell
# 临时把修复删掉 → 确认该条用例 not ok → 还原 → 确认恢复全绿
python - <<'PY'
import pathlib, subprocess
F = "frontend/src/views/asset/ledgers/components/EditAccountDialog.vue"
orig = pathlib.Path(F).read_text(encoding="utf-8")
pathlib.Path(F).write_text(orig.replace("markSaved();", "", 1), encoding="utf-8", newline="")
r = subprocess.run(["node", "--test", "scripts/tests/unsaved_guard_baseline.test.js"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print("CAUGHT" if any(l.startswith("not ok") for l in r.stdout.splitlines()) else "MISSED（守门失效）")
pathlib.Path(F).write_text(orig, encoding="utf-8", newline="")
PY
```

今天的两次真实拦截：#1891 那一版判据按**缩进**截取函数体，被 `CreateAccountDialog.handleCreate`
里第 98 行闭的是 `if (!name.trim())` 假失败；另一版用 `/set\s*\(/` 匹配不到对象方法的
`set: (v) => {}`（`set` 与 `(` 之间有冒号）。**判据自己先崩了两次**——所以判据写好后
必须在**真实代码**上跑，且要有一次回退验证。

### 三之二、判据必须有「失败态」：拿不到输入 ≠ 输入为空（2026-10-13，源 CNB #171）

上一节治的是「判据**写错方向**」（探针一插就发现它没红）。这一节治的是**更隐蔽的一类**：
判据方向没错、探针也拦得住，但它**没有失败态**——输入拿不到时，退化成一个看起来正常的结论。

真实事故：CNB 侧的「镜像卡状态回流」脚本用 `state=all` 拉 GitHub issue 来判断
「GitHub 已关、CNB 还开着」。匿名限额 60 次/时/IP 被同流水线的建卡 job 先耗尽 ⇒ 403 ⇒
函数 `break` 返回**空映射** ⇒ 调用方 `if not todo: print('✅ 无状态漂移，两侧已对齐')`。

**一张 issue 都没拉到，输出「已对齐」。** 它带 `|| true` 收尾，连红灯都没有——
于是这张网**从上线起一直绿、一直没干活**，所有人都以为它在织。

- **判据的失败语义必须显式**：拿不全 ⇒ 说「拿不全」，并**以非 0 退出**，
  **不得**退化成一个看起来正常的结论。修复后拿不全时打印
  「数据不完整，本次结论不可信」并返回 1——**这才是正确的红**。
- **「不会误标」不等于「结论可信」**：原代码注释写「少拉只是少标记、不会误标」——
  对**误标**是对的（逐张跳过而非猜），但它没意识到另一面：**少拉到 0 时结论完全反了**。
  写「降级是安全的」之前，先问一句「降到 0 会怎样」。
- **别用 `|| true` 吞掉判据的失败态**：收尾阶段不拦构建是对的（建卡才是主任务），
  但要把退出码**回显**出来（`rc=$?; [ $rc -ne 0 ] && echo '⚠️ …'`），否则失败态就地消失。
- 同类气味：`except: return []` / `if not data: continue` / `if not rows: print('无异常')`。
  **看到「空 ⇒ 正常」的等价，先问它区分不区分「空」和「没拿到」。**

### 三之三、探针咬不住的分支，往往在做假装的工作（2026-10-13，源 CNB #171）

**写完探针别只看「CAUGHT 数够不够」，还要看「有没有哪条 MISSED」。** MISSED 通常不是
探针写歪了，而是**被测代码里有一段死代码**——它看起来在兜底，其实条件恒真/恒假。

实测（口径改为「自动关」那一轮）：`run()` 里写着

```python
need_close = auto_close and card['cnb_state'] != 'closed'
```

看起来是「不重复关已关闭的卡」的兜底。但 `plan()` 只交出漂移卡，而
`state_drift()` 的定义已经排除「两侧都关」⇒ **该条件恒真**。改掉它，一个测试都不会红
（S5 探针 MISSED 就是这么发现的）。

- **处置是删掉它，不是给它补测试**：补一条「恒真条件的测试」等于把假的工作固化下来。
  真正承担幂等职责的是 `plan()`，就把契约**钉在 `plan()`**（`test_plan_永不交出已关闭的卡`）。
- **自查**：某条探针 MISSED 时，先问「改这段到底改没改变行为」——没改变 ⇒ 它是死代码。

### 三之四、切口径时，先问「存量数据按新口径该怎么办」（2026-10-13，源 CNB #171）

口径变更**只改代码是一半的活**。旧口径已经产出过的事实，必须被新口径**收编**——
否则系统会分裂成「新数据按新规矩、老数据按老规矩」两套真相，而这通常正是这次变更
要消灭的形态。

实测：镜像卡状态回流从「标记不关」改为「自动关」时，旧口径已产出 **13 张**
「评论已发过、卡还开着」的存量卡。若只改代码，它们会**永远漂着**——口径改了、
不一致还在，只是换了个说法。故 `run()` 里把两条判据**分开**：

| 动作 | 判据 |
|---|---|
| 发评论 | 幂等键（同一事实只发一次） |
| **关闭卡片** | **与评论无关**——漂移卡就该关（含存量卡） |

推而广之：改判据/改状态机/改命名规范时，都要单独答一句
**「按旧规则已经产生的数据，会被新规则重新处理一遍吗？」**

### 三之五、引用报错时看时态：**「那一刻找不到」≠「现在还没有」**（2026-10-14，源 CNB #269）

三之二是「**空 ≠ 没拿到**」（假绿）。这一条是它的镜像，同样常见、同样贵：
**拿一条历史构建的报错，断言此刻的事实**（假红）。

真实事故：`认领同步` 合并后的 `push` 构建（`10:10:37`）报 `GetFileContent: not found`，
我引用它写下「那个密钥文件**还没建**」。而用户 **4 分钟后**（`10:14`）就建好了——
截图里文件赫然在目。**报错没骗人**（它描述的是 `10:10` 那一刻），骗人的是**时态**：
把一个**时间点的事实**当成了**持续状态**。

- **引用构建/日志报错必须带构建号与时刻**，并自问：
  **「这条报错的观测时间，和我下结论的时间，差了多少？期间有没有人改过被引用的东西？」**
- **读不到的东西，不得断言其内容**（在 / 不在 / 是什么）。密钥仓库对本仓 API / token
  **一律 403 / Repository Not Found**（三种口径实测），所以「它在不在」是**用户那边的事实** ——
  正确的话是「我读不到，待你确认」，而不是「它不存在」。
- **链式推断要停在第一跳**：「读不到」的成因可能是「不在 / 名字不对 / 权限不对 / 分支不对」，
  把它**收敛成「不在」是猜**。
- **别拿跑错的构建当证据**：`cnb build get-build-logs` 的 `event` 字段分清作业类型 ——
  `issue.comment@npc`（NPC 回复触发的镜像作业）**不跑** `$` 段的 push 作业，
  拿它说「某推送作业还没绿」是张冠李戴。

推导与实测命令见 `docs/dev/github-cnb-mirror.md` §16.10。

### 三之六、**同一事实问两次，然后取第二次**：静默翻转结论的那一类（2026-10-18，源 CNB #573）

`machine_branch.py` 的演练路径这么写：

```python
code, _, _ = _git(['merge-tree', '--write-tree', base, merge])      # ① 取退出码
if code == 1:
    _, out, _ = _git(['merge-tree', '--write-tree', base, merge])   # ② 再跑一遍取输出
```

读起来毫无问题——「先看有没有冲突，有的话把冲突文件列出来」。**但它问了两次。**
只要 ② 的输出（或它对返回值的解包）与 ① 对不上，冲突清单就**恒为空**，
于是「有冲突」与「无冲突」打印的是同一句 **「✅ 无冲突，两侧内容可合。」**

- **失败形态是静默且更响亮的**：判据错的时候，报告给出的结论不但不消失，反而更像结论。
  这次是「每小时红一次、每次都说两边无冲突」，而根因（推不上去）被另一行日志盖住。
- **判据**：`python scripts/guard_ask_git_once.py`（并入 `ci.yml` 的 `scripts_test`，阻断）。
  同一函数内同一个 `_git` **参数形状**出现两次、且第二遍丢掉退出码 ⇒ 红。
  回归网 `scripts/tests/test_ask_git_once_guard.py` 里最重的一条拿 `origin/dev` 上
  **修复前的真实代码**喂守卫，确认它真会红（守卫绿 ≠ 守卫有效）。
- **写「自己回退验证」时也要小心同款**：为了确认守门咬得住，我用脚本把 bug 重新注入再跑测试；
  **第一次我把守卫里那句 `if not conflicts:` 本身删掉了**，于是「读不懂就报不可信」的保护一起没了，
  用例红在一个我没预期的地方。**探针是在改生产代码，不是在改测试数据**——改完要看它红
  *在哪一条*、*因为什么*，而不是只看「红了」。

> 推而广之：**任何「先探测、再执行、再读第二次结果」的结构都要问一句「两次之间变了会怎样」。**
> 能一次调用同时拿码与输出，就别分两次问。

### 四、正则/字符串类判据的两个常见错

- **按缩进截取函数体会截错**：`async function f() { if (x) { … } … }` 里第一个 `\n  }` 闭的是
  `if` 不是函数。要**数花括号配对**（`extractAsyncFunctionBody` 那段）。
- **先 `stripComments` 再匹配**：文档里写「旧写法是 `ref("")`」会被当成代码，仓库里
  `unsaved_guard_baseline.test.js` 的注释已经明说「今天已被咬第三次」。

### 五、扫描优先于抽查

一轮扫 18 个候选，最后只有 1 个是真问题（#1896）。**抽查会漏掉同型漏点**——
#1845 / #1883 / #1884 三轮都在修组件内部语义，而 #1891 那一页始终漏着，因为三轮都没扫过宿主。
机械化扫一遍的成本是几分钟，漏一个的代价是一整轮返工。

判定「不需要修」时，**把三问的答案写进卡或守门注释**，否则下一个人看到「没守卫」就会去补。
`#1897` 就是反面教材：建卡时只看到「在向导内、没守卫」，没查数据归属，卡建错了又关掉。

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
  **同样禁止**（2026-10-05 补充，见下节）：`git add` / `git commit` / `git checkout -- <file>` /
  `git restore` / `git rebase` / `git reset --soft` / `Remove-Item` / `rm`。
  判据不是命令名，而是**是否改写主仓库工作区或 `.git` 状态**——`git add` 只是写 index，
  但它让主仓库进入「有本地改动」状态，从此 `git checkout dev` 开始报
  "local changes would be overwritten"，把主仓库锁死。
- **为什么**（#1421 事故复盘，2026-09-11 实测）：主仓库跑着 Vite 时切分支，git 是**逐个文件**改写工作区的——
  它先 unlink 了 `frontend/build/dep-drift-guard.ts`，而仍然 import 它的 `frontend/build/plugins.ts`
  尚未被改写；Vite 监听着「配置依赖」的变化，立刻重载配置 bundle，重新读到的仍是新版 `plugins.ts`，于是报
  `Could not resolve "./dep-drift-guard"` → `server restart failed`。dev server 与磁盘状态随即错位，
  而报错指向一个「明明存在」的文件，极易被误判成代码缺陷。**这是工作流问题，不是代码缺陷。**
- 同理：跑着 dev server 的工作区不要被 `git worktree remove`、外部脚本或编辑器插件批量改写文件。

### 抢救主仓库里的未提交改动（强制，2026-10-05）

> 上一节的条文假设主仓库工作区是**干净**的。现实是主仓库里常会躺着别的人 / 前序会话的
> 未提交工作——可能是 detached HEAD 上做了一半的活，也可能是「dev 分支切不过去」的原因。
> **这类场景最容易让人在主仓库里「顺手救一下」，那正是上一条禁止的事。**

- **正确姿势（三步，主仓库零改动）**：

  ```powershell
  # ① 只读导出，把「未提交改动」变成一个文件
  git diff > D:\codes\_bk\work.patch

  # ② git worktree add 是**唯一**允许在主仓库执行的命令（纯元数据，不碰工作区）
  git worktree add D:\codes\fm-<issue#> -b <type>/<issue#>-<slug> origin/dev

  # ③ 在新 worktree 里重放并验证
  cd D:\codes\fm-<issue#>
  git apply D:\codes\_bk\work.patch
  ```

- **禁止在主仓库「救」**：不建分支、不 `add`、不 `commit`、不 `checkout --`、不 `rebase`。
  哪怕「只是导出一下」「只是建个分支」也不行——主仓库一旦进入有本地改动的状态，
  就同时挡住了别人和后续的 `checkout dev`。
- **为什么要开新 worktree 而不是原地救**（2026-10-05 实测复盘）：
  - 原地救会**改写主仓库 HEAD**（detached → 自分支），并发会话一旦同时操作同一个 `.git`，
    双方互相覆盖，`.git/refs/remotes/` 被清空、reflog 归零这类元数据损坏随之而来；
  - 原地救**必然 rebase**，而 rebase 撞上 dev 已前进的同名改动就会冲突，
    逼你逐处重新核对——本该 10 分钟的抢救拖成两轮返工，还差点把工作判成冗余而丢弃；
  - 抢救时最危险的判断是「这份改动 dev 上已经有了，丢掉吧」。
    在 worktree 里对着最新 `origin/dev` 核对，判错的后果只是**不提交**；
    在主仓库原地判错，删掉就**不可逆**。
- **抢救前先备份**：动任何文件之前，把 `git diff` 与工作区里那些**未跟踪**文件
  （`git status --porcelain` 里的 `??`）一并复制到仓库外。
  未跟踪文件在 diff 里不存在，而它们往往是这次工作的**主体**。

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

### 本机依赖源配置（#2031，2026-10-11）

- **仓库不再声明依赖源**：`backend/pyproject.toml` 不含 `[[tool.pdm.source]]`（#1628 时代写死阿里云的做法已废除）——CI 不声明源即天然走官方 PyPI（海外 runner 快），`ci.yml` 里的「改写工作区文件切源」步骤已删除。
- **本机（国内）声明机器级源**，只配一次、与仓库文件解耦：

  ```powershell
  pdm config pypi.url https://mirrors.aliyun.com/pypi/simple/   # 本机默认（快）
  pdm config pypi.url https://pypi.org/simple/                  # 一键切官方（镜像滞后时用）
  ```

- **镜像滞后时**（索引列出版本、对应文件 URL 却 404，如 2026-10-10 的 `python-dotenv 1.2.3` / `mcp 2.0.0`）：先 `pdm config pypi.url https://pypi.org/simple/` 再装，装完**无需还原任何仓库文件**（机器级配置不进 `git status`）；想切回阿里云再跑一次第一条命令即可。
- 实测记录（PDM 2.26.8，空项目坏地址探针，2026-10-11）：无项目源时 **user 级 `pypi.url` 生效**、**`PDM_PYPI_URL` 环境变量同样生效**（指向 `127.0.0.1:9` 均 ConnectError）；`pdm.lock` 只记文件名+哈希、**不记录 index URL**，删源声明无需重锁。
- **临时改共享配置的纪律不变**：为让本地跑通而对**共享 / 版本化配置**（`pyproject.toml`、`pnpm-lock.yaml`、`uv.lock`、`tsconfig.json` …）的任何临时改写，**必须放进 `try/finally`、装完立刻还原**，并紧接着用 `git status --porcelain` 自证只剩预期改动：

  ```powershell
  try { <临时改配置> ; pdm sync -G dev }
  finally { git -C <worktree> checkout -- backend/pyproject.toml
            git -C <worktree> status --porcelain -- backend/pyproject.toml }
  ```

- **禁止**：把临时改动留在工作区「等会儿再还原」。#2029 修复过程中曾临时改源且顺序反了，让用户在 `git status` 里看见源被换掉、一度误判为「仓库配置回归」——配置类改动只要出现在 `git status` 里，就会消耗掉别人对仓库的信任。**装依赖卡住想换源时，正确的做法是 `pdm config`（机器级），不是改 pyproject.toml。**

---

## 文档站与落地页

- **文档站**：根目录执行 `pnpm run docs:dev` / `docs:build`。
- **内部备忘**：一律放 `docs/working-notes/`（全局屏蔽），文件名必须英文 kebab-case + 日期后缀，如 `deployment-2026-08-04.md`，正文标题可用中文。新增备忘须同步登记进 `working-notes/README.md` 索引表。
- **落地页**：已移交主站仓库 `duoduobei-web`（`duoduobei.com`），本仓**不再构建落地页**——四条 `build:landing/about/story/pages` 脚本与 `scripts/build-landing.mjs` 均已移除。根 `vercel.json` 现指向**应用站**（`frontend/` 构建 → `frontend/dist` + SPA 回退），Cloudflare Pages 侧见根 `wrangler.toml`，详见 `docs/ops/deployment.md` §3。
- **Markdown lint**：`pnpm run docs:lint-md`（**只读报告**，不改文件）。确实需要自动修复时显式跑 `pnpm run docs:lint-md:fix`（带 `-f`），但必须先看 `git diff` 再提交——`lint-md@0.2.0` 的 fixer 对**缩进代码块**有非幂等 bug：它把缩进代码块首行当成围栏行，每跑一轮就往行尾追加一个 `plain`，与内容无关（`npm install foo` 这类普通行同样中招），永不收敛。另注：CI workflows 目前**未接入** markdown lint，仅本地执行（此前文档里「CI 用 npx lint-md docs」的说法已不准确）。

---

## 核心约束

### API 契约

- 错误统一信封：`{data, message, error_code}`（**三字段**，`error_code` 取 `ErrorCode` 的 int，见 `conventions.md` §2.4；守卫 `scripts/guard_error_envelope.py`）。
- API-First 契约冻结，禁止私改字段、状态码、分页结构。
- 端点一律尾斜杠（**例外**：`/api/health` 与 `/api/temperature/{overview,history,multi,crowding-history}` 无尾斜杠，前端按此调用，勿“修复”；例外清单以 `scripts/check_api_conventions.py` 的 `NO_TRAILING_SLASH_ALLOWLIST` 为准）。
- 全量端点清单见 `docs/spec/api.md` 的自动段（`scripts/check_api_conventions.py --write` 生成，改路由后须重跑）。

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

### 温度计基线数据

- `backend/app/services/thermometer/data/all_pb.csv`（全 A 中位 PB 历史）**必须入库，禁止删除、禁止 `.gitignore`**。
- pre-commit 守卫 `scripts/guard_all_pb.py` 会在行数骤降（< 1000）时拒绝提交，禁止 `--no-verify` 绕过。

### 提交前检查

- 后端：`pytest` 全量单进程通过。
- 前端：`vue-tsc` 零错误（需手动运行，因 husky 未安装）。
- 前端 E2E：**不是每次提交都要跑**，但改动**路由守卫 / 布局 / permission store / 侧边栏**时
  必须跑 `pnpm test:e2e`（`ci.yml` 只做静态检查；E2E 由 `e2e.yml` 每夜或手动触发）。

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

## 双端协作（CNB ↔ GitHub）

> **CNB 侧只读**：`cnb.cool/duoduobei/fundmate` 是 `imoyao/fundmate` 的镜像仓，不做 PR 流程。
> 讨论与状态变更都回 GitHub；CNB 的 issue/评论由流水线单向镜像过来（只增不覆盖、不同步关闭态）。
> 本节是 CNB 侧踩过的坑，**每条都是实测撞出来的**，不是风格建议。

### 引用编号必须挂源：GitHub 的 issue / PR 一律写完整链接

**CNB 的正文与评论里，裸 `#123` 一律被解析成本仓库（CNB）的编号并渲染成链接。** 于是：

- 写「见 GitHub 的 #2050」→ 点进去落到 `cnb.cool/.../-/issues/2050`，**本站根本没这张卡**（用户 2026-10-11 实测撞到）；<!-- cross-repo-ref-allow -->
- 更隐蔽的是**同号撞车**：CNB 侧确实存在同号卡时链接能打开、但打开的是**另一张卡**。
  双端编号是**两个独立空间**，「点得开却是错的」比 404 更难发现。

**规则**：提到 GitHub 的 issue / PR，编号必须挂源，三选一。

| 写法 | 例 | 说明 |
|---|---|---|
| **完整链接（首选）** | `https://github.com/imoyao/fundmate/issues/2050` | 跨仓一律用这个 |
| 限定形态 | `GitHub #2050` / `GH #2050` / `imoyao/fundmate#2050` | 短，但读者已知在说哪一侧 |
| 行内代码 | `` `#2050` `` | 仅限「上下文已明确指 GitHub」的正文 |

**反例**：`见 GitHub 的 #2050` / `另见 #1996` / `PR #1757 已合并`（在讲 GitHub 侧 PR 时）。
后者在 CNB 上点开是 CNB 的 #1757，**换一侧看编号，完全不相干**。

- **裸 `#N` 只留给本仓（CNB）自己**的编号，例如「里程碑 #14」这类 CNB 概念。
- 机器兜底：`scripts/guard_cross_repo_refs.mjs`（并入 CI 的 `scripts_test` job，即 `gate` 的 needs）。
  逐行扫，命中「行里在说 GitHub、行里还有没挂源的裸 `#N`」即报红；行尾加 `cross-repo-ref-allow` 可豁免
  （仅限讲机制本身、代码里的正则、反例清单三类）。回归网与 **6 个证伪探针**见
  `scripts/tests/guard_cross_repo_refs.test.js`。
- **存量取「行级冻结基线 + 只管新增」**（`scripts/guard_cross_repo_refs.baseline.mjs`）：
  上线时全仓 89 处命中（历史文档、上游项目名 `pytest #3221`、`Project #3` 等，多为误报形态），
  一次改完会把修复摊成 90 处无关 diff。基线键是 **`文件|行指纹` 而非文件名**——按文件名冻会
  让「已脏文件里新增的裸引用」跟着蒙混过关。改到某行时顺手挂源，行文本一变指纹即失效、该行转红；
  守卫会列出已失效条目催删档，避免基线长成「永远豁免」的垃圾桶。重新生成：`--freeze`。
- **边界**：判据是**行级**的（同一文件里 CNB 编号与 GitHub 编号混排时，只会有问题的那些行红），
  因此「一句不带任何 GitHub 词的『另见 #999』」是它的**已知假阴性**<!-- cross-repo-ref-allow -->——脚本尾部会打印
  「裸露高发文件」提示人工复核，那部分是**报告不是判据**。

### 分支 Hygiene 与自动合入机制（2026-10-15，#450）

> 背景：#450 系列 4 个 PR 并行造轮子、基于陈旧 dev 开出，合并时冲突爆炸且过不了质量门禁。
> 以下约定+自动化用于**从机制上消灭「分支又旧又冲突又过不了门禁」这个反复现象**，而非逐个 PR 救火。

**分支纪律（所有 AI / agent / CNB 分支必须遵守）**：

1. **必须基于最新 `dev` 开出**：开分支前先 `git fetch origin dev` 并 `git rebase origin/dev`，禁止基于数周前的旧 base。这正是「落后 51 提交」巨无霸分支的根因。
2. **单目标**：一个分支只做一件事，禁止把无关的前端路由 / 后端视图 / 文档改动打包进来。
3. **不重复治理脚本**：`scripts/bridge/`、`scripts/check_*.py`、`.cnb.yml`、`AGENTS.md` 是全局共享文件，多分支同时改会互相污染基线。**确需改这些文件时，先查是否已有 open PR 在改（见下方重叠守卫），优先接力而非另开一份**。

**三层自动机制（已在 `.github/workflows/` 落地）**：

| 层 | 工作流 | 作用 |
|---|---|---|
| ① 自动变基（保新） | `pr-auto-rebase.yml` | PR 有新推送 / 每日定时时，把分支 rebase 到最新 `dev` 并 `--force-with-lease` 推送。冲突即 abort 并留言，绝不半成品强推。 |
| ② 绿灯自动合并 | `pr-auto-merge.yml` | PR 挂 `automerge` 标签且 base=`dev` 时，门禁「质量门禁汇总」转绿即自动合入。**保护一直开着（质量不丢），合是自动的**，不再需人工点合或临时放松保护。 |
| ③ 重叠守卫 | `pr-overlap-guard.yml` | PR 打开/同步时，若与其他 open PR 触碰同一批治理文件，提前评论预警，让人先协调。 |

**控制标签**：

- `automerge`：贴到 base=`dev` 的 PR 上即启用 ② 自动合并（opt-in，防误合）。
- `no-bot-rebase`：贴到 PR 上即禁用 ① 自动变基（人工接管时用）。

> 唯一无法由系统代劳的，仍是「写出能过 CI 的代码」。三层机制把「救火旧分支」的人工动作降到只剩这一件。

### 「永久记忆」存在哪、什么时候读

NPC 没有跨会话记忆，**每一次开工都是新进程**。所谓「记住」= 写进**版本控制的仓库文本**，
靠「开工必读」而不是靠记忆生效：

| 载体 | 读者 | 何时读 |
|---|---|---|
| 根 `AGENTS.md`（本节所在） | 所有人 / AI | **每次任务开始** |
| `docs/spec/decisions.md` | 需要决策依据时 | 动规范 / 架构前 |
| `docs/spec/conventions.md` | 冻结区，不可擅改 | 改契约 / 数据模型前 |
| `docs/dev/*.md` | 专项作业 | 做对应作业时 |
| `scripts/guard_*.py\|mjs` | CI | 每次 PR |

所以**想让 AI 长期遵守某条规则，唯一有效的做法就是把它写进 `AGENTS.md`**
（或对应 spec），并尽量配一条机器守卫——只写在评论里的话，下一个会话就没了。

### 规则的生命周期：**写进 AGENTS.md 不等于会被执行**（2026-10-16）

> 用户的质疑值得记下来：「我们写进 AGENTS.md 里面的文档，我感觉好像其他的 Agent 有时候
> 并不遵守，导致我们发生了这种规则的漂移。」这句话是对的，而且**有数**。

#### 现状（实测普查，2026-10-16）

`AGENTS.md` 里 91 条硬约束条目（列表项 / 表格行 / 引用行 + 「强制 / 必须 / 禁止 /
不得 / 一律 / 只能 / 严禁」），其中**只有 3 条挂了机器判据**，其余 88 条只靠「读到的人
愿意遵守」。所以「AI 不遵守」**不是偶发**，而是当前设计的**必然结果**：没有判据的规则，
只能靠当事人当场的自觉。

同一轮普查里更贵的一类：**写了守卫，却没接进会拦住合并的地方**——它比「没有守卫」
更像已治理，因为所有人（包括 AI）都以为有人在拦。

#### 判据机械化：`scripts/guard_rule_registry.py`

把「这条规矩归谁管」变成一张可校验的登记表（`RULE_REGISTRY`），逐条写清四件事：

| 字段 | 含义 |
|---|---|
| `rule` | 它对应哪条规矩 |
| `runner` | 靠谁跑：`ci`（可拦合并）/ `both`（本地钩子 + CI 兜底，最常见）/ `pre-commit`（只本地）/ `cnb` / `ci_only`（两者都是**观测，不拦人**） |
| `tests` | 回归网在哪（守卫要自带一条具备红灯语义的用例） |
| `covered` | **已知不覆盖**什么（写「无」也算一次思考） |

四条硬判据（任一不满足即红，并入 `ci.yml` 的 `scripts_test`，阻断合并）：

1. `AGENTS.md` 里用反引号挂的脚本必须都登记（且文件存在）；
2. 登记的 `runner` 必须与**实际执行点**一致——`ci.yml` 里找不到就红；登记成
   `pre-commit` 而 `ci.yml` 里也有一份同样红（归属没人说得清，等于没人管）；
3. 挂在 `commit-msg` / `pre-push` 这类**`git commit` 时不跑**的钩子上，必须另有一处
   CI 兜底（`guard-mojibake-commit-msg` 的兜底就是 `mojibake_guard` job）；
4. 本文件里没有判据的硬约束条目数不得超过 `PURE_RULE_BUDGET`（现值 88）。

它的计数口径与边界（**只减不增**、以及为什么不追求「把 91 条都挂上判据」）
写在 `scripts/guard_rule_registry.py` 的 `PURE_RULE_BUDGET` 注释与下方「明确不做的事」里。

#### 明确不做的事（别把预算读成 KPI）

- **不追求「把 91 条都挂上判据」**：像「删除前先读内容」「不要武断执行」这类规矩，
  本质上只能由人判断。硬凑判据只会造出一堆假绿。
- **不把预算当成 KPI 往下压**：预算的唯一作用是「不许悄悄变多」。
  哪天某条规矩真的被机器化了，顺手调低它即可；为降数字而写的守卫一定是假绿。
- **不做中文语义分类**：首版按「行内有情态词」筛出 168 条，其中三成是叙述规则本身的
  句子（如本节的「唯一有效的做法就是写进本文件」）。判据宁可窄，**数错等于钉错**。
- **登记表不替代 review**：它只保证「这条规矩有一个真的在跑的判据」，判据够不够严，
  仍要人看。

#### 给「别的 Agent」的可执行口径

你要新增 / 修改一条规矩时，按这个顺序：

1. 能用脚本判吗？能 ⇒ 写 `scripts/guard_*.py`，登记进 `RULE_REGISTRY`，接进 `ci.yml`
   （并入已有 job，**不新增 job**，避免动 `gate.needs`）；
2. 不能 ⇒ 写进 `AGENTS.md` 的硬约束，并**同步调低/说明**为什么它只能靠自觉；
3. 两边都不做、只想「提醒一下」⇒ 那它不是规则，是建议。别写成「必须」。

判据边界（`guard_rule_registry.py` 只判「登记 / 归属 / 生命周期 / 预算」四件事，
不判规则内容对不对）与回归网见 `scripts/tests/test_rule_registry_guard.py`（含 4 个
变异探针，其中 2 个是 MISSED 后改写出来的——见文件内注释）。

### 什么能到 GitHub、什么不能（一张表说清，2026-10-14 / 源 CNB #172）  <!-- cross-repo-ref-allow -->

用户 2026-10-14 问「只对 CNB 生效的改动会不会永远留在 CNB」。**按类型分，答案不同**：

| 类型 | 能到 GitHub | 走哪条路 |
|---|---|---|
| 代码改动（含 CNB 侧改的脚本、`.cnb.yml`） | **能** | `dev` 分支的 `push:` 段；功能分支走 `"**/!(main|dev)"` 段 |
| issue / 评论（镜**像**卡上的） | **能** | `cnb-github-backfill.yml` 每日拉取 |
| **CNB 本地卡上的讨论** | **按需能** | 需人工触发 `local_card_promote.py` 推广（见上） |
| `main` 分支 | **只出不进** | 只由 GitHub 的发版 PR（`dev → main`）推进；CNB 不推 `main` |

一句话：**代码双向流动、issue 单向可回流（有边界）、本地卡的结论需要人工开闸**。
把「有出口」读成「会自己同步」是最容易犯的误读。

**功能分支上的新卡当天可见**（D56）：`.cnb.yml` 的 `$` 段挂了一段 `push:`，
任何分支的 push 都跑一轮**幂等**建卡 + 状态回流——补的是「有人在 `feat/*` 上开卡、
却永远扫不到」这个缺口（原作业只挂 `main` 的 cron）。两个作业都幂等，故重复跑无副作用。

### Issue 分诊与派活：判据机械化，合入永远是人（D58，源 CNB #564）  <!-- cross-repo-ref-allow -->

> 📍 用户 2026-10-18 拍板四件事（先回流已关的 → 分诊/打标签/写评论 → 派活每轮 3 张、
> 每天两轮 → 合入不打 automerge，人工验证后合并）。本节把这四条写成可执行判据。

**为什么先做回流而不是先派活**：实测 2026-10-18，CNB 侧 open 卡 **198 张**，其中
约 **197 张**的 GitHub 原卡早已关闭——看板脏的时候，任何「扫全部 open 卡」的作业读到的
都是假库存。**脏看板上做出的判断不值钱**，所以顺序不能反。

#### 一、回流（`scripts/bridge/mirror_state_sync.py`）

- 判据是**单向**的：GitHub 已关 + CNB 还开 ⇒ 回流并关闭（B 口径，CNB `#171` 拍板）；
- **镜像卡不能只靠状态文件识别**：状态文件是缓存，只在建卡成功的路径写入。实测
  **48 张** `GitHub 同步` 卡不在里面，它们永远进不了 `plan()`——一条永远不执行的代码
  被读成「已经对齐」（与 CNB `#450` 的 224 张重复卡同因）。现改为**缓存优先、卡面正文兜底**；
- 认不出 GitHub 编号的卡**不静默跳过**：open 的逐张列出来，已关的只计数。

#### 二、分诊（`scripts/triage/issue_triage.py`）

一卡一次，产出**固定枚举**，只贴标签 + 写一条评论，**绝不改代码**：

| 字段 | 取值 | 判据（全机械，不调 LLM） |
|---|---|---|
| `kind` | `stale` | 归档标签 / 正文写着「不再做 / 已被替代」 |
| | `tracker` | 引用了 **≥2 张其他卡** / 标题含「系列」/ 卡面整段加粗（议题式写法） |
| | `decision` | 卡面**明写**「需拍板 / 待决策」 |
| | `task` | 有可逐条对照的验收标准（checkbox / 「验收」小标题） |
| | `discuss` | 以上都不是 —— **先讨论清楚范围，别动手** |
| `size` | `S`/`M`/`L` | S = 卡面自述「单点 / 一处 / typo」；L = 引用多卡或正文超 4000 字 |
| `risk` | `low`/`medium`/`high` | high = 卡面出现钱 / 契约 / 数据域 / 守卫文件名 |
| `next` | `close`/`archive`/`product_gate`/`dispatch_npc`/`human_review` | 见下 |

- **判据顺序有意义**：过时 > 系列卡 > 需决策 > 可执行/讨论。顺序变了结论就变。
- **镜像溯源块不参与判据**（`strip_mirror_header`）：它是建卡脚本写的模板，内含
  `AGENTS.md` / `scripts/bridge/…`，不切掉会让 10+ 张无关的卡一起判成 high（实测踩过）。
- 结论变了（指纹变）或标签被摘掉才重新写；同结论不刷屏。

#### 三、派活闸门（`dispatch_rejects`，不掺感觉）

四问**全过**才允许交给 NPC 自动推进：`kind=task` + `size` ∈ **准入档** + `risk=low` + 卡面不出现
`money.py` / `db_factory.py` / `conventions.md` / `AGENTS.md` / `.cnb.yml` / `scripts/guard_*` /
`migrations/`。**改文案 / 改视觉另有一条**：要同步 `design.md`，属于产品口径 ⇒ 一律转人工。

**规模档是参数，不是判据里的字面量**（2026-10-18 用户拍板放开，判据见 `test_issue_triage.py`）：

| 档 | 含义 | 谁决定 |
|---|---|---|
| 默认 `('S',)` | 只有「卡面自述改一处」的卡可派 | 代码默认值；改宽它等于偷偷放宽判据，`test_default_stays_strict` 会红 |
| `.cnb.yml` 传 `--sizes S/M` | `M` 也进候场 | **用户 2026-10-18 明确放开**（见下） |
| `L` | 永不随仓放开 | 几乎只意味着「正文超长 = 一件事写不清」，派 AI 去做等于替人补写范围；要派得由人在卡面写清验收标准 |

**为什么放开 M**：实测 198 张卡可派 **0** 张，而「低风险 + 有验收」的 17 张**全部卡在 M**——
按原标准，派活吞吐恒为 0，而「每轮 3 张」的额度从未被用上过。用户的原话是
「放开这个限制」——**放开的是准入资格，不是同时能跑的量**：额度仍 3 张/轮，
风险面 / 护栏文件 / 产品口径三条**一条没松**，PR 仍要人 review。

⚠️ 两条踩过的坑，都由回归网钉住：

- **准入档名要取 `size_of()` 真会返回的值**（`S`/`M`/`L`）。首版写成 `('S','SM')`，
  而判据比较的是 `'M'` ⇒ **一张都没多派**，看板上却表现为「已放开、可派仍是 0」。
  这是「放宽 ≠ 生效」型的假信号，与 #171 同族。
- **被闸门挡掉 ≠ 被额度挡掉**，分开报（`🚧 另有 N 张被派活闸门挡下（非额度）`）。
  混在一起时，「可派 0」读起来像「没有活」，而这 17 张正是被同一个条件挡着的活。

#### 四、额度与合入（用户拍板，别再问第二遍）

- **分诊写入**与**派活件数**是**两条上限**，不许合并：分诊只贴标签写评论、无副作用
  （默认每轮 50 张）；派活要开分支写码、每张 PR 都要人 review（**每轮 ≤3 张、每天 ≤2 轮**）。
  合并成一个数的话，130+ 张待分诊的卡要跑三周，期间看板一直是脏的。
- 被额度挡掉的卡要**报出来**（`⏸️ 另有 N 张因额度未处理`），不许冒充「已分诊完」
  ——这条由 `test_issue_triage.py` 的额度用例钉住（见下方护栏）。
- **不贴 `automerge`**。绿灯 ≠ 审查通过：`.ai-review-deep.yaml` 在 `upstream_unavailable`
  时把判定 job 判成 skipped（不是 pass），门禁分不清「通过」与「没跑」。**合入永远是人**。

#### 五、护栏

- **挂上 cron**（2026-10-18）：此前 `issue_triage.py` 只在本地手工跑过，于是「可派 0」
  只出现在一次性终端输出里。现挂在 `main` 的 `crontab: 0 18 * * *` 里、
  **排在「状态回流」之后**（先关掉 GitHub 已关的卡，再对剩下的贴结论，
  否则会去给一张马上要关的卡写标签），`--apply --sizes S/M --batch 3`，退出码回声不吞（#171）。
- 回归网 `scripts/tests/test_issue_triage.py`（46 条，含 **4 个变异探针**：模板当判据 /
  规模检查被删 / 准入档被硬写 / 两条额度混一），并入 `ci.yml` 的 `scripts_test` job，
  **不新增 job**（不新增就不必动 `gate.needs`）；
- 守卫登记在 `guard_rule_registry.py` 的 `RULE_REGISTRY`；
- 写 GitHub（标签 / 评论）仍只走 `claim_detect.py` / `mirror_correction.py`，**本脚本不写 GitHub**
  ——双端写入的闸门不重开第二份。

### 认领同步：两边不要同时改同一张卡（D57，源 CNB #179）  <!-- cross-repo-ref-allow -->

> 📍 这一节回答的是：「我们在 CNB 上修某张卡，GitHub 那边怎么知道？应该有一套约束。」

**先把问题说准**：这不是「同步」（同一事实的两份副本对齐），是**「一件工作被两边同时领走」**。
实测已发生一次，就在这张卡自己身上——CNB 的 PR #180 与 PR #181 是同一张卡（CNB #179）的
**两套并行解法**，base 都是 `dev`、改同一批文件，冲突要人工逐处消解（`724e5add`）。

#### 「实时」的诚实口径

用户要的是「**实时感知，不能靠每小时拉或推**」。这个诉求被**事件拓扑**挡住，
不是「还没做」而是**结构上做不到**：

| 方向 | 通不通 | 结论 |
|---|---|---|
| GitHub 事件 → **叫醒** CNB 流水线 | ❌ 没装 GitHub App、无 webhook 中继 | CNB **收不到**「GitHub 有人动了那张卡」 |
| GitHub Actions → 读 CNB | ✅ `GITHUB_TOKEN` 注入；CNB 公开仓匿名也可读 | **这条通** |
| CNB 构建 → 写 GitHub | ✅ 走插件任务 + Secret `imports` | **有能力**（见上方纠错） |

**故把方向掰过来：自己那一侧的事件由自己订阅。** 没有任何一方在轮询对方：

| 方向 | 谁驱动 | 延迟 |
|---|---|---|
| GitHub 有人动手 → CNB 镜像卡评论区 | `.github/workflows/claim-sync.yml`（订 `issues` / `pull_request` 事件） | **秒级** |
| CNB 有人动手 → GitHub 原卡挂 `CNB 处理中` | `.cnb.yml` 的 `$` 段 `push`（`claim_detect.py`） | 分钟级（跟着 push 走） |

#### 认领判据：只看事实，不看声明

- CNB 侧有 **open PR** 且其引用这张卡（**只信标题里的编号**，见下）+ CNB 镜像卡 **open**
  + 它是**镜像卡而非本地卡**（本地卡不进 GitHub，D52）；
- **刻意不看** assignee（意图不是事实）与「评论里有人说在改」（那句话下次就不算数了）。

#### ⚠️ 从 PR 里认卡号：**只信标题**（实测推翻的初版）

初版收正文裸 `#N`，在 5 个真实 PR 上逐行核对后，**抽出的 7 个裸号里 4 个是别的东西**：
``PR #210``（**PR** 编号）、``#1403`` / ``#2034``（**GitHub** 侧卡号）。  <!-- cross-repo-ref-allow -->
而 CNB 编号连续、镜像卡从 #5 起 ⇒ **这些号在 CNB 侧确实存在同号卡** ⇒ 标签挂到不相干的卡上。

**试过四条行级启发式（行内 `PR #N` / GitHub 字样 / 行内代码 / 加粗）全部不够**
——真实行文里加粗没闭合、纯散文提一句都躲得过去，继续加就是在拟合样本。
**改用结构性判据：标题 = 这件事是什么，正文 = 怎么做的。**

| 形态 | 收不收 |
|---|---|
| 完整 URL / `CNB #N`（限定写法） | ✅ 标题与正文都收（人主动挂的源） |
| **标题**里的裸 `#N` | ✅（标题里的编号必然是本次在做的卡） |
| **正文**里的裸 `#N` | ❌（多数是在引用别的东西） |

已知假阴性：正文写裸号、标题没写卡的 PR 会被漏 ⇒ **少挂一个标签**，可接受。**宁可漏，不可错。**

#### 标签会自己消失

| 形态 | 动作 |
|---|---|
| CNB 侧有 open PR 引用 | 挂 `CNB 处理中` + 写认领评论（只发一次） |
| 认领的 PR **集合变了** | 补一条说明评论（标签说不出「哪些 PR 在动」） |
| CNB 侧**没有** open PR 引用了 | **摘掉标签**（评论不删） |
| 数据不完整 | **什么都不做**，且不得宣称「已对齐」 |

后两行**刻意相反**：**摘多了比留多了贵**（误摘一张其实有人动的卡，下一个人就会去动它）。

#### 边界（不要读成「两边再也不会撞了」）

- **只识别「CNB 有人在动」**：GitHub 侧两人同时动手由 GitHub 自己管；
- **标签是信号不是锁**：不阻止任何人，只让人看得见。要「锁」得靠 assignment + 分支保护
  （本仓不做——会拖慢单人开发）；
- **CNB 侧延迟 = 距离上一次 push**；**摘标签**依赖 GitHub 事件或 2 小时兜底 cron；
- 细节与实测推导见 `docs/dev/github-cnb-mirror.md` §15；决策见 D57。

### ⚠️ 「配置对了」≠「同步成功了」：跨仓 `dev` 分叉会静默锁死（2026-10-14，源 CNB #269）  <!-- cross-repo-ref-allow -->

**这是最容易白干两天的一类**：把 `.cnb.yml` 的形状一路修对（凭据挂载层级、命名 stage 防假绿、
事件挂分支下、`main` 收窄……见下几节），**每一处都真修对了，但两侧 `dev` 依然推不动**——
因为**形状对了，分叉这个事实还在**。判据修的是「水管长什么样」，没人去清「管里堵的那个东西」。

**判据一句话：`dev` 必须两侧一致；`main` 允许不一致**（§13.5 口径）。实测
（2026-10-14，`git ls-remote` + `fetch` 两侧真实 ref）：

```
CNB dev = af8750e0   GitHub dev = eb9c9bba   最后成功同步 = 2026-10-11 13:34
git cherry 双向        → CNB 独有 30 笔 / GitHub 独有 89 笔
```

**根因不是配置错**：push 任务 `branch: dev` 且**刻意不开 `force`**（反向上是护栏），
→ GitHub `dev` 有 CNB 没有的提交 → 非快进 → **永远被拒，只会一直红**；
pull 又只拉 `dev`，**哪边都拉不动对方** ⇒ **死锁，两边都不动，且零信号**。

- **保护 `dev` 的正确形态是「合并」，不是「隔绝」**：用户「怕 pull force 冲掉 CNB dev」
  的担心是对的（§13.3 实测 pull 会 `git push origin <b> --force`），但拒绝同步只让差异滚大。
- **缺口在判据的作用域**：`check_branch_divergence.py`（§11）只比**仓内** `main ← dev`，
  **问不出**跨仓分叉——因为另一半在另一个仓库。三天零信号正是这个原因。
- **判据机器化**：`python scripts/bridge/check_cross_repo_dev_divergence.py --report`
  （只用 `git cherry` 补丁等价、双向各一次；**两侧都有 `+`** ⇒ 退 1；单向领先 ⇒ 退 0；
  拿不到输入 ⇒ 退 2 且声明结论不可信）。挂在 `.cnb.yml` 收尾自检（只报告、退出码回显）；
  **不挂 `ci.yml`**——它是联网判据，PR 门禁不该依赖外网与 GitHub 凭据。
  回归网 `backend/tests/test_cross_repo_dev_divergence.py`（含 2 个变异探针）。
- **`main` 保持现状不是 bug**：实测 CNB `main` 只领先 `dev` 3 个发版 merge、
  GitHub `main` 只领先 GitHub `dev` 1 个合并——**都合规，不要去「同步 main」**。
- **收敛必须先定方向再合**（以哪一侧为基线），且要一次人工合并解冲突；
  **继续放着不动不是中立选项**，每天多欠一笔。细节与推导见 `docs/dev/github-cnb-mirror.md` §17。
- **「CNB 能不能自动向 GitHub 提 PR」= 能，但本仓不需要，判据如下**（2026-10-14，源 `CNB #269`）：<!-- cross-repo-ref-allow -->
  - **能做**：CNB 构建里走「插件/脚本任务 + Secret `imports` 取 `GITHUB_PAT`」通道，
    `POST /repos/{repo}/pulls` 与挂标签/发评论同一条路（`claim_detect.py --apply` 已在生产跑）。
    「CNB 提不了 PR」是**过时判断**，不要沿用。
  - **不做**，两个理由：① 本仓跨仓那一步是「**搬运**」不是「**变更**」——内容是同一批
    已 review 过的提交，再开一层 PR 只会多出无人 review 的噪声（见 §18.4 对照表）；
    ② 造 `CNBDEV` 之类的中转分支**不解决分叉**（§18.2）——只是把同一场冲突换个分支名再演一次，
    且违反「禁止新建长期分支」。
  - **口径**：跨仓 = `dev → dev` 整条线；仓内 = 功能分支 → `dev` 走 PR。**两者不要混用机制。**
  - 收敛工具：`python scripts/bridge/dev_converge.py --apply`（建 rescue 分支 + 合 + 列冲突；
    **不**动 `dev`、**不**自动解冲突、**不** push）。回归网
    `backend/tests/test_dev_converge.py`（含 1 个变异探针）。详见 §18。
- ⚠️ **`bridge/github-dev` 只能有一个写者：GitHub reconcile 写，CNB 只读探针**（2026-10-19，源 CNB #574；守卫 `scripts/guard_bridge_machine_branch_single_writer.py`）。<!-- cross-repo-ref-allow -->
  这张卡来自一张构建日志：两条 pipeline 同一天都红在 `! [rejected] … (fetch first)`，
  而它们撞的是**同一条分支被两个写者各写一份**：

  | 写者 | 触发 | 写法 | 开 PR 吗 |
  |---|---|---|---|
  | GitHub `.github/workflows/dev-reconcile.yml` | 每日 cron | `push --force-with-lease` + `merge -X ours` | **开**（挂 automerge） |
  | CNB `.cnb.yml`「跨仓同步」stage | 每次推 `dev` | 每轮换 base 重合、普通 push | 不开 |

  CNB 这侧每轮都必然徒劳：归一化 base 变了 ⇒ 非快进被拒；侥幸快进也会**改写** reconcile
  刚铺好的合并结果，而**它开的那张 PR 还开着** ⇒ 内容与分支不符（外观正常，比红灯危险）。
  ⇒ 写权归 GitHub reconcile（唯一写者），CNB 降级为**只读探针**：
  合并照跑、结论照报（「两侧能不能无冲突合并」每轮都算得出来），但**一次 push 都不发**。
  要接管时设 `MACHINE_BRANCH_WRITER=cnb`，并**同时停掉** reconcile 的推送步骤 ——
  两个写者不能并存，且写者身份必须是**配置**不是**时序**（`--force-with-lease` 是原子检验，
  「先比 SHA 再推」永远是竞态）。
  判据：`scripts/guard_bridge_machine_branch_single_writer.py`（并入 `ci.yml` 的 `layout_guard`，
  回归网 `scripts/tests/test_bridge_single_writer.py`，3 个变异探针均实测转红）。
  推导见 `docs/dev/github-cnb-mirror.md` §23。
- ⚠️ **「收敛」是动作不是状态：合完不等于成功，且会反复岔开**（2026-10-14 实测，源 CNB #269）。<!-- cross-repo-ref-allow -->
  跨仓分叉**不是一次性故障**。只要「GitHub 侧会推进 `dev`」+「CNB push 刻意不开 `force`」
  两条同时成立，分叉就会复发；#425 收敛完成、#448 再合一次，**30 分钟内又岔开一笔**
  （GitHub `d1b5780b` / CNB `866e2043`，差的是 GitHub #2140 数据新鲜度那一笔）。
  - **验收标准是「push 构建 success **且** GitHub 侧 `ls-remote` ref 对上 SHA」**，
    **不是**「merge 进去了」。只要 push 还没成功，包含关系就是敞的 ——
    GitHub 再动一次 `dev` 即作废。
  - ⇒ **别把「#425 已收敛」当成稳态叙述**；正确说法是「截至那次合并，CNB `dev` 包含
    GitHub `dev`，直到 push 成功一次为止」。
  - **判据不会漏**：`check_cross_repo_dev_divergence.py` 已实测咬住复发（`EXIT=1`，真分叉
    非假阳性）。但它是**构建收尾**触发 ⇒ 信号延迟 = 「距离下一次 push」，**是小时级，
    不得叙述成实时**。
  - **冲突成本主要在第一次**：#425 解了 25 个文件；这次复发只有 1 笔纯新增，**零冲突**。
    这正是「当天看见就便宜、拖三天就贵」的量化版本。
  - 推导与实测命令见 `docs/dev/github-cnb-mirror.md` §19。

### ⚠️ 镜像建卡重复了 224 张：「缓存」被当成「判据」，三天零信号（2026-10-14，源 CNB #450）  <!-- cross-repo-ref-allow -->

用户报的是「issues 重复同步，把 github 上面的又同步了一遍」；实测比这严重得多：

| 指标 | 实测 |
|---|---|
| 受影响 GitHub 卡 | **140 张** |
| 多出来的重复卡 | **224 张**（单卡最多 **11 张**） |

重复卡每约一小时多一张（跟建卡作业同频），已连续三天。根因只有一行：

```python
known = {int(k) for k in mirrored if str(k).isdigit()}
if known:            # ← 缓存非空就直接 return，CNB 侧一个字都不查
    return known
```

**这条读起来像完全合理的缓存优化，所以它在 review 里毫不起眼 —— 它就是漏过去的那一版。**
但状态文件**是不全的缓存**：只在建卡成功的路径写入，中断 / 手建 / 抛错都不补记。
实测它冻结在 107 条（CNB #5~#112），而 CNB 侧已有 365 张镜像卡 ⇒ #112 之后的每张
在判定时都「不存在」⇒ **每轮重建**。判重是幂等的，判重依据却停在不自更新的缓存上。

**三条纪律（本节是全局的，不只对镜像建卡）：**

1. **缓存只能做索引，不能做边界。** `if <有缓存>: return` 是把加速器当成了真相来源。
   写这类判重时先问：**「缓存不全时会怎样？」** —— 它的失败形态是**静默**的
   （判重失效 → 重复建 → 每轮成功 → 全绿）。同族气味：`if not data: return []`（#171）。
2. **「作业成功」证明不了「作业做对了」。** 判据错的时候，日志只会更响亮地复述错结论
   （每轮都打印「✅ CNB #N ← GitHub #M」）。必须**另有一条作业问「结果对不对」**，
   不能只问「跑没跑成」。
3. **修根因只解决未来，存量要单独发现。** 改完代码，那 224 张**还在那儿**。

**机械化（三道）**：

- **阻断**：`python scripts/bridge/harvest_scan_guard.py`（并入 `ci.yml` 的 `scripts_test` job）
  —— `harvest_existing()` 必须在函数体里真的调用 `list_cnb_issues()`，且**扫描前不得有 `return`**；
  判据是「**有没有短路**」，不拟合写法（`if known:` / `if len(known) > 10:` 一视同仁）。
- **观测**：`python scripts/bridge/check_duplicate_mirrors.py --report`（挂 `.cnb.yml` 收尾，只报告）
  —— 同一幂等键 >1 张卡 ⇒ 退 1；**有卡读不到 ⇒ 退 2 且声明「结论不可信」**（不得退化成「无重复」）。
  清理是**人的决定**，脚本只读、不猜留哪张。
- **并集口径**：修好后取 `缓存 ∪ CNB 实况`，不取 CNB 实况单值 ——
  **宁可漏建，不可重复建**（漏建下轮补得上，重复建**不可逆**）。

回归网 `scripts/tests/test_dup_mirror_guard.py`（16 条，含 **3 个变异探针**，
其中一个是拿 `git show origin/dev:` 上**修复前的真实代码**喂给守卫，确认它真的转红）。
推导与实测命令见 `docs/dev/github-cnb-mirror.md` §20。

### 在 CNB 侧的其它已知边界（实测）

- ⚠️ **「CNB 构建环境没有 GitHub 凭据」是错话，2026-10-14 已纠正**（源 CNB #179）。  <!-- cross-repo-ref-allow -->
  准确的说法分两条路：
  - **手工 `git push https://github.com/...`** 确实不通（`env` 里只有 `CNB_*`，
    报 `could not read Username`；`api.github.com` 匿名 POST 返 **401**）；
  - **走插件任务 + Secret 仓库的 `imports`** 是**通的**——凭据来自 `fundmate-secret`
    的 `GITHUB_PAT`，三个 git-sync 方向全在跑、`claim_detect.py --apply` 也走这条路。

  所以 CNB 侧**不是**「只能只读」。要不要在 CNB 存 GitHub PAT，是**取舍**不是**限制**：
  现在只有 `GITHUB_PAT` 一个（与 git-sync 共用），**不要再存第二份**。
- **别在 `dev` / `main` 上直接 push**：CNB 的代码镜像（`sync/mirror` 分支的定时任务）是
  **fast-forward only**——CNB 侧一有独有提交，下一轮就「无法快进」判否、**整条镜像链停摆**
  （2026-10-11 实测停摆，救援分支 `rescue/2-cnb-commits`）。
- **`git push --dry-run` 对 cnb.cool 是假信号**：它不真正建 ref，也不代表正式 push 会成功。
- **CNB API 不在 `cnb.cool`** 而在 `https://api.cnb.cool`，路径是 `/-/` 风格，
  鉴权 `Authorization: Bearer`，且 `Accept` 必须是 `application/vnd.cnb.api+json`
  （否则拿到 HTML）；分页参数是**下划线** `page_size`，写成 `page-size` 会被静默忽略。
- **CNB `create-issue --labels` 会被静默忽略**（HTTP 201 但标签为空）：必须**先建卡、再单独挂标签**。
  标签名只允许中英文 / 数字 / `._:-/\` 与内部空格，长度 ≤50，`&`、`（）`、`#` 一律 400 拒收。
- ⚠️ **脚本任务的镜像里到底有什么，要逐条问，问到脚本真正用过的东西为止**
  （源 CNB #517，2026-10-16）。#461 给「跨仓同步（机器分支）」补了  <!-- cross-repo-ref-allow -->
  `docker.image: python:3.12-slim`，回答了「有没有 python」；但**官方 slim 镜像一律不带 git**，
  而该 job 跑的 `machine_branch.py` 是 `subprocess.run(['git', …])` 驱动的 ⇒ 报
  `FileNotFoundError: … 'git'`，**报错指向脚本内部某行、不指向容器**。同一个 job、
  同一类「执行环境缺失」，两次都以为修完了。
  - **处置**：凡在 `python:3.12-slim` 上跑 `scripts/**/*.py` 的 stage，脚本开头先自证：
    `command -v git >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq --no-install-recommends git; }`
    再 `git --version >/dev/null`（**装失败不吞**）。**不要**改换镜像——会把「python 在哪」
    这个刚解决的不确定项重新打开。
  - ⚠️ **同一根因的另一面是「假绿」**：镜像 job 的「分支分叉自检」跑
    `check_branch_divergence.py`，同样缺 git、**每一轮都崩**，却因 `|| true` + 末尾 `exit 0`
    而**报绿**——自检**从未真正跑过**（实测 stage 只花 0.4s 即 success）。
    一处红、一处绿，根因同一个；**只修红的那个，绿的会永远绿着不干活**。
  - **判据机器化**：`scripts/guard_cnb_script_task_git.py`（并入 `ci.yml` 的 `scripts_test`，阻断）
    先**从源码推导**「哪些 `scripts/**/*.py` 真调 git」，再要求调用它们的 stage 在同一段
    script 里供给 git（不手写名单——手写的会随新脚本失效）。回归网
    `scripts/tests/test_cnb_script_task_git.py`（8 例，含推导假设钉桩 + 重复键遮蔽探针 +
    真实故障前文件 `7b833c4c` 回退探针）。详见 `docs/dev/github-cnb-mirror.md` §21。

---

## Issue 全局治理（里程碑强制）

> 全局硬性规定：**任何 issue（含 AI 自动创建 / ClawBot 生成的元 issue）创建后必须挂里程碑，禁止处于无里程碑（No milestone）状态。**
> 参考 #1287 看板整理教训：2026-09-02 曾出现 31 个开放 issue 完全未挂里程碑、M6 Backlog 被当垃圾桶，经系统整理后已清零；此后以本全局规则 + CI 守卫防止回潮。

### 归属原则

- 主题明确 → 归入对应产品里程碑：`M0 上线`、`M1 付费验证`、`M2 免费核心`、`M3 量化分析`、`M4 护城河生态`、`M5 安全与体验`、`M6 待办积压 Backlog`、`P0 导入统一入口`、`基础数据 Base Data`、`自选增强 Watchlist Enhancement`、`双库架构 / DB Multi-Engine（#14）` 等。
- 确属远期 / 待定 / backlog → 归入 `M6 待办积压 Backlog`，**不得**停留在 No milestone 状态。
- 双库架构 / 数据域 / 数据库相关 issue 的强制归属见下方「双库架构 Issue 治理（里程碑 #14）」（该专项规则是本条全局规则的子集，二者不冲突）。

### CI 守卫（拦住新建漏挂）

- 工作流 `.github/workflows/issue-milestone-guard.yml` 在 issue 被 `opened / edited / reopened / milestoned / demilestoned` 时检查其 `milestone` 字段（后两个为 GitHub #1515 补充：**补挂里程碑时 GitHub 发出的事件是 `milestoned` 而非 `edited`**，旧版只订阅前三个会「补挂后不自愈」——整改完成了 run 仍是红的，红灯可信度随之崩塌；`demilestoned` 用于反向校验「已挂又被摘掉」）：
  - 有里程碑 → 通过；
  - 无里程碑 → 在 issue 下**评论提醒责任人补挂**，并使该 workflow run **失败（红）**作为止损信号（issue 本身无法被 Action 自动关闭/拦截，故以失败 run + 评论提醒）。
- 该守卫只针对 issue（`pull_request` 事件不触发），不影响正常 PR 流程。
- 维护者补挂里程碑后守卫会自动复检通过、自愈：**补挂**发的是 `milestoned`（不是 `edited`，见上），**摘掉**发的是 `demilestoned`。

### 自动关闭关联 issue（dev 合入即关）

- 工作流 `.github/workflows/close-linked-issues.yml` 在 **PR 合入 `dev`** 时解析 PR 正文里的 closing keyword（`Closes` / `Fixes` / `Resolves #N`），关闭对应 issue。
- **为什么需要它**：GitHub **只在 PR 目标为仓库默认分支时**解释 closing keyword；本仓默认分支是 `main`，而功能 PR 一律 base=`dev` ⇒ 关键字**被完全忽略（连 link 都不建）**。实测（2026-09-24）最近 100 个已关闭 PR 里 **15 个**正文写了 `Closes #NNNN`，**全部无效**，issue 每次靠人肉关。
- **发版 PR（`dev → main`）不需要它**：那个方向的目标就是默认分支，GitHub 原生就会关；本 workflow 显式只处理 `base.ref == 'dev'`。
- 解析器**单一来源** `scripts/close_linked_issues.js`（不内联进 YAML），纯函数部分由 `scripts/tests/close_linked_issues.test.js` 钉住，随「守卫:脚本单测 (scripts)」job 跑。
- **边界**：围栏代码块 / 行内代码内的关键字**不匹配**（正文里讲解该机制时不误伤）；跨仓 `owner/repo#N` **不操作**；引用 PR 自身编号不关；已关闭的跳过（幂等）；引用的是 PR 而非 issue 时跳过。
- **红绿语义**：单个目标失败只告警；**全部**目标失败才红 —— 避免「本该关却没关」以绿灯静默溜过。
- 手动复检：`workflow_dispatch` 传 `pr_number`；`dry_run=true` 只报告不实际关闭。
- ⚠️ **判断卡是否「被自动关」看 actor，别再看时间差**：issue 时间线里 `closed` 的 `actor` 是 **`github-actions[bot]`** ⇒ 本 workflow 关的；是**人** ⇒ 人肉关。
  （旧的「`closed` 距 merge ≈ 1 秒 = 自动关」判据**只适用于 GitHub 原生路径**，即 base=`main` 的合并；base=`dev` 现在走本 workflow，多了 job 排队与执行时间，几秒到几十秒都正常。）
  推论不变：**不要依赖 PR 正文的 `Closes #` 判断卡是否已关**，去 issue 时间线看。
- ✅ **已端到端验证**（2026-09-24，PR #1684）：自动路径 run `36013544058` 在合并后 **3 秒**起跑、job 未被跳过；
  手动路径 run `36013935960`（`workflow_dispatch` + `pr_number=1684`）成功关闭 #1683 —— 日志为
  `已关闭 #1683「…」—— 由 #1684 合入 dev 触发。`，issue 时间线里 `closed` 的 actor 即 `github-actions[bot]`。
- ⚠️ **两种「静默空跑」形态**（run 变绿但什么都没关，**只有看日志里的 `##[notice]` 才发现**）：
  ① 正文**只在行内代码 / 代码块里**提到关键字（讲解本机制时举 `` `Closes #123` `` 为例）—— `stripCode` 会剔除，这是**有意**的；
  ② 正文**只是用文字描述**「本 PR 带关键字」而**没有真的写下那一行** —— 实测踩过（#1684 的第一次自动运行正是此因）。
  ⇒ 作者自查：`grep -nE '\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\b *:? *#[0-9]+'` 有命中、且**不在代码里**，才算真写了。

### 失实信息修正纪律

- 既有 issue 的正文若被发现失实（如快照数字、状态描述与真实不符），**用评论（`gh issue comment`）追加更正，禁止用 `gh issue edit` 覆盖原正文**（遵循 AGENTS.md「追加请续帖」）。误关须 `gh issue reopen` 并留痕。
- 确需修正正文的极特殊场景，先在原 issue 评论说明、再 edit，且保留历史可追溯到评论。
- **CNB 镜像卡同样适用本条**（#120）：镜像卡的问题不是「正文被改乱」，而是**永远停在建卡快照**——GitHub 侧后来的更正传不过来，而镜像卡是只读的、下一个人不知道要去 GitHub 看。故：
  - 镜像卡正文顶部（`build_body` 生成的溯源块）已写明「**建卡时快照**（截至建卡日期）、正文行号可能与当前代码不一致、**以 GitHub 为准**」，并提供更正路径；
  - 更正**写在镜像卡的评论区**（正文仍只增不覆盖），格式固定：

    ```text
    ## 更正（YYYY-MM-DD）
    - ❌ 正文「…」→ ✅ 实际「…」（依据：PR #xxx / commit 短号）
    ```

  - 用 `python scripts/bridge/mirror_correction.py add --cnb <编号> --date <日期> --correction '<一条更正>'` 生成（默认 dry-run，加 `--apply` 真正发布；幂等，重复执行只发一次，返工用 `--force`）；`list --cnb <编号>` 看某张卡已记的更正。
  - 边界：**只往 CNB 写，绝不回写 GitHub**；不动镜像卡正文、标签与状态；脚本会拒绝往非镜像卡（人工卡）写更正。
- **CNB 本地卡**（只对 CNB 有效、**不进 GitHub** 的卡，D49 / CNB #117）：  <!-- cross-repo-ref-allow -->
  - 判据是「这张卡的存在意义是否依赖 CNB 这个环境」——`CNB_TOKEN` 构建内注入、`cnb` CLI、
    `.cnb.yml` cron 语义、CNB 自身镜像链路取舍等，镜像到 GitHub 读起来会莫名其妙；
  - **开卡时就声明**，两种任选（都认）：正文顶部写 `> 📍 **CNB 本地卡**`，或挂 `CNB 本地` 标签；
  - **忘了声明也不会丢**：`python scripts/bridge/github_cnb_issues.py --report-local` 会把
    「无 `GitHub 同步` 标签 + 无幂等键」的卡兜底认成本地卡并报出来——但兜底是**猜**
    （报告里记为 `fallback`），所以**声明仍是正道**；
  - 若某张卡正文引用了 GitHub 侧卡，**写完整 URL** `https://github.com/imoyao/fundmate/issues/N`：
    回写作业（`cnb_github_backfill.py`）只认完整 URL，裸引用 `imoyao/fundmate#N` 会被
    **静默跳过**（该取舍是对的——写路径认错会把评论贴到别人卡上；`--report-local` 会把
    这类卡单独标出来供人判断）。
  - **结论需要 GitHub 侧看见时，用推广通道**（D56，源 CNB #172）：  <!-- cross-repo-ref-allow -->
    `python scripts/bridge/local_card_promote.py --list` 列候选，
    `--cnb <编号> --title '<标题>' --body-file <utf8正文> --apply` 执行。它做三步且顺序固定
    （GitHub 建卡 → **CNB 原卡评论区留一条完整 URL 的链** → 刷新镜像），缺一条就等于没推成。
    **这是人工决定的动作，不是自动镜像**——推广后原卡与 GitHub 新卡是两张卡，靠那条链接互相指认。

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
| #1435 | 线上 SaaS 数据分层与多库选型：热 / 温 / 冷（决策卡，不排期实现） | OPEN   |
| #1513 | 技术债：`app/core/database.py` 导入期即建双域 engine（缺一个驱动就让整个后端不可导入） | OPEN   |

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
- **中文内容**：正文一律用 `--body-file` / `-F` 传入 UTF-8 无 BOM 文件，禁止内联中文变量。**`gh issue create` 没有 `--title-file`**（gh 2.97.0 实测 `unknown flag`，2026-10-12；此前本行记载有误）：issue 标题与 PR 标题同理禁止内联中文，正确做法是先用 ASCII 占位标题建卡，再用 UTF-8 JSON 文件 `gh api -X PATCH repos/<owner/repo>/issues/<n> --input title.json` 修正（`title.json` 形如 `{"title": "中文标题"}`，由写文件工具生成，禁止内联中文），随后按下方「回读校验」确认。
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

#### 「同主题」还是「跨主题」——可操作判据（2026-10-11 补，源 CNB #118）

上面那条「跨主题必须拆卡」缺一个判断标准，于是**每张卡都能被解释成「同主题」**。逐条问这四句，
**任一命中即跨主题，必须拆卡**：

1. **验收标准是同一套吗？** 拆开后能否各自独立通过 / 独立失败？能 → 跨主题。
   反例（CNB #106 / GitHub #2034 原文）：  <!-- cross-repo-ref-allow -->UI 措辞、产品布局、跨卡耦合（#2033）、未定产品决策
   四件事装一张卡，验收标准、决策人、动手时机**各不相同**。
2. **动手时机相同吗？** 一件「现在就改 1 行」、另一件「等产品拍板」→ 跨主题。
   同主题的典型长相：**同一处代码、同一次改动、同一个验收口**。
3. **决策人 / 前置依赖相同吗？** 一件等 A 拍板、另一件等 B 拍板 → 跨主题。
4. **「部分完成」时你关得掉这张卡吗？** 关不掉（因为剩下那半是另一件事）→ 跨主题。
   这条最实用：**一张卡「部分完成」就关不掉，本身就是拆卡信号**。

反过来，**同主题必须续帖**的情形：同一处代码的后续发现、同一问题的补充证据、
同一结论的修正。判据是「**删掉先发那条，后发还看得懂吗**」——看不懂就是新主题。

> 症状诊断（源 #118 的实测）：为一张卡做 **4 轮代码核对、改 2 次结论**，
> 说明卡面承载的信息量已超过「一件事」的量级。核对成本高不是罪，**结论反复变化**才是。

#### 卡面引用具体行号时：必须带 `@ref`，核对前先 `git show`（2026-10-11 补，源 CNB #118）

- **写卡时**：引用 `path/to/File.vue:119-130` 一律写成 `path/to/File.vue@origin/dev:119-130`。
  不写 `@ref`，核对者不知道拿哪个版本比——**卡面描述的可能是两个版本之前的代码**。
- **动手前**：先 `git show <ref>:<file>` 确认该行仍在，再改代码。
- **机械化核对**（不要再靠肉眼）：

  ```bash
  # 单张卡面 / 本地文件
  python scripts/bridge/check_issue_refs.py --issue 2034 --ref origin/dev
  python scripts/bridge/check_issue_refs.py --file card.md --strict-ref
  # 全部 CNB 镜像卡（只报告，不改卡）
  python scripts/bridge/check_mirror_refs.py --report
  ```

  首轮实测（2026-10-11，110 张镜像卡）报出 **3 张卡 / 4 条失效引用**，逐条核实为真——
  例如 CNB #56（GitHub imoyao/fundmate#1095）引用  <!-- cross-repo-ref-allow --> `portfolios/views.py:214-215`，该文件**只有 166 行**。

#### 核对结论写在哪（2026-10-11 补，源 CNB #118）

**写在被核对的那张卡上**，不要只写在工具注释 / 分支 / 新开的卡里——
下一轮核对的人**仍然要重做一遍**，因为结论不在他读的地方。

优先级：① 被核对卡片的**新增评论**（禁止改原正文，遵循「失实信息修正纪律」）→
② 若结论改变了原卡范围，同时在被引用卡上链回。**镜像卡同理**：卡面失实就在镜像卡评论区
追加更正（CNB #120），不要另开一张卡与原文并存且互不指向。

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
