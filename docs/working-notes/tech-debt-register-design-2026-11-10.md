# 技术债务台账可判定化 — 设计方案（2026-11-10）

> 状态：方案已定，实现同 PR 落地。适用范围：`docs/spec/tech-debt.md`（1281 行）及其状态维护流程。
> 本文件只记方案与依据；**状态的唯一权威是 `docs/spec/tech-debt-register.toml`**。

---

## 1. WHY：为什么先动台账，不动任务

2026-11-10 盘点（`tech-debt.md`，逐条回代码 / issue 实证）发现三类失真：

| 形态 | 实证 | 后果 |
|---|---|---|
| **僵尸条目** | §79/§128 称「无任何代码读取 `nav_per_10k`」，实际 `money_fund_income.py:19` 等 13 个文件已在消费；§80 暗色模式称「前端未接入」，实际 `style/dark.scss` + `useDataThemeChange.ts` 已在；§84 当日盈亏称「前后端均无能力」，实际 `services/today_pnl.py` + 首页 `TodayPnlCard.vue` 已上线 | 🔴「上线前必查」的债挂了 3 个月没人敢关，真正该排的项被埋住 |
| **状态回流缺失** | §121–127 的 5 张 🔴 高红旗 #937/#933/#934/#825 全部 CLOSED（最晚 2026-10-24），§83 跟踪的 #913 早在 08-12 关闭，文档仍写「完全未落地」 | 文档与 issue 各自为真，读者无法判断信哪个 |
| **覆盖缺口** | 11 月架构体检系列（#2803 / #2780 / #2781 / #2874 / #3004 等）在 `tech-debt.md` 里 0 命中 | 新债只进 issue，不进台账；台账越用越旧 |

**根因不是没人勤快，是状态不可判定**：条目的「处理策略」写的是「待排期 / 暂缓 / 需拍板 / 后续优化」——不可执行、无复核日期、无触发条件。issue 关了不会回流，代码写了不会触发更新，于是文档只增不减。头部自称「最后核实 2026-10-11」，git 实际最后提交 `9c6d4f5d97`（11-09），连这个日期自己都失实。

### 1.1 本轮自己踩到的反例（写进方案当反面教材）

首轮盘点用 `Grep ... pull_request_target` 的**出现次数**得出「8 个 workflow 仍用 `pull_request_target`，#2803 未处理」。复核结构化事实后推翻：

- 真实触发器只剩 **2 个**（`dependabot-auto-merge.yml:31`、`dependabot-lockfile-regen.yml:88`），且是 `scripts/guard_workflow_definition_source.py` 里 `_PRT_EXEMPT` 的**显式豁免**（依赖 bot 触发路径不能迁）；
- 其余 6 个文件的命中全是**注释里的说明文字**；
- `python scripts/guard_workflow_definition_source.py` 当前 **exit 0**（「workflow 定义来源正确」）。

即 #2803 的迁移已落地，issue 仍 open 是「等发版同步 main + 关单」，不是「没做」。这正是 #2453 教训（全文 includes / 计数会被自己的注释喂饱）的又一次复现。⇒ **台账判据必须是结构化断言，不能是全文计数或自然语言**。

---

## 2. 设计原则

1. **单一真源**：`tech-debt-register.toml` 是状态的唯一权威；`tech-debt.md` 降级为**历史归档**，只保留「发现过程 / 决策依据 / 实测证据」，不再承载状态。
2. **判据结构化**：每条债必须有 `criterion`（机器可判定的断言），不是「待排期」这类空话。
3. **状态机闭合**：`open / done / blocked / deferred / wontfix` 五态，各有必填附加字段；「已裁决不处理」也是显式状态，不再用「暂缓」糊过去。
4. **新鲜度即闸门**：`verified_at` 超期强制复核（90 天），台账整体 `updated_at` 超期同样判红。
5. **失败态优先**：输入缺失 / 登记表为空 / 解析失败一律退出码 2，不冒充通过。
6. **守卫自身要被验证**：`--self-check` 变异探针 + unittest 回归网，证明「守卫真的会红」。

---

## 3. 字段规范（`tech-debt-register.toml`）

顶层：`schema = 1`、`updated_at`（ISO 日期）、`status_authority`（说明文字）。

每条 `[[debt]]`：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✅ | `TD-\d{3}`，全表唯一 |
| `title` | string | ✅ | 一句话，不含状态词 |
| `status` | enum | ✅ | `open` / `done` / `blocked` / `deferred` / `wontfix` |
| `priority` | enum | ✅ | `P0` / `P1` / `P2` / `P3` |
| `doc_ref` | string | ✅ | `tech-debt.md:<行号>` 或 `<文件>:<章节>`；仅作定位提示，**不是判据**（行号会漂） |
| `issue` | int | ✅ | 关联 issue 号，`0` = 无 |
| `verified_at` | ISO date | ✅ | 最后一次**回代码/回 issue 实证**的日期 |
| `criterion` | inline table | ✅ | 见 §4 |
| `evidence` | string | `done` 必填 | 闭环证据（file:line / 命令输出） |
| `blocker` / `next_action` | string | `blocked` 必填 | 卡在哪、下一步做什么 |
| `trigger` | string | `deferred` 必填 | 什么条件下重新激活 |
| `decision` | string | `wontfix` 必填 | 决策编号或文档位置 |

### 3.1 状态语义（消除「暂缓」这个垃圾桶）

| 状态 | 含义 | 判据要求 |
|---|---|---|
| `open` | 未做，判据当前**不满足** | 自动判据未满足；若已满足 ⇒ 红（僵尸 open，要求改 `done`） |
| `done` | 已闭环，判据当前**满足** | 自动判据满足；不满足 ⇒ 红（假闭环） |
| `blocked` | 代码侧已做，被外部条件卡住（如等发版） | 只校验 `blocker` + `next_action`，不做满足性判定 |
| `deferred` | 已裁决暂缓，有明确复活条件 | 只校验 `trigger`，不做满足性判定 |
| `wontfix` | 明确不处理 | 只校验 `decision`，不做满足性判定 |

---

## 4. 判据 DSL（内联表，四类）

| type | 字段 | 语义 | 自动执行 |
|---|---|---|---|
| `grep` | `path`, `text`, `present` | 文件内出现 / 不出现某文本 | ✅ |
| `file` | `path`, `present` | 文件存在 / 不存在 | ✅ |
| `guard` | `script` | 守卫脚本 exit 0 | ✅（限 `scripts/guard_*.py`、`scripts/check_*.py`，timeout 20s） |
| `command` | `run` | 可复现的人工命令（issue 状态、真机 axe、真 PG 等无法静态判定） | ❌ 只登记 + 新鲜度闸门 |

约束：`command.run` 不得命中空话黑名单（「待排期 / 暂缓 / 后续优化 / 需拍板 / 择机」）。路径不得越出仓库。`grep` 判据引用的文件不存在 ⇒ exit 2（读不到文本无法判断，属台账写错）；`file` 类型则相反——「文件存在 / 不存在」本身就是判据，不存在是合法状态，按 `present` 算出满足与否。

**为什么允许 `command` 而不强行全自动化**：真机 axe、CI 真 PG、GitHub issue 状态这类判据依赖环境，硬塞进 CI 会因为「拿不到输入」制造假红（本仓教训：拿不到输入一律按红，故不能让网络成为阻断点）。`command` 靠 `verified_at` 逼人定期复核，是诚实的可判定，不是假装自动。

---

## 5. 守卫：`scripts/guard_tech_debt_register.py`

并入 `ci.yml` 的 `scripts_test`（不新增 job ⇒ 不动 `gate.needs`），阻断。

| # | 判据 | 失败退出码 |
|---|---|---|
| R1 | 结构：必填字段 / 枚举 / `id` 唯一 / ISO 日期 / `doc_ref` 指向的文件存在 | 1 |
| R2 | 判据形态：结构化内联表、`type` 在白名单、`command.run` 不含空话、状态附加字段齐全 | 1 |
| R3 | 新鲜度：`open`/`blocked`/`deferred` 的 `verified_at` 与顶层 `updated_at` 超 90 天 ⇒ 红 | 1 |
| R4 | **自动复核**：`done` 判据必须满足、`open` 判据必须不满足；`command` 类型跳过 | 1 |
| R5 | 双真源：`tech-debt.md` 头部必须有 `STATUS_AUTHORITY: tech-debt-register.toml` 标记；`docs/spec/index.md` 的文件导航表首列必须登记该 toml | 1 |
| R6 | 失败态：登记表缺失 / 为空 / TOML 解析失败 / 路径越界 / `grep` 引用文件不存在 / `guard` 脚本不存在 ⇒ **2**，不得降级成通过 | 2 |

`--online`（可选，不接 CI）：用 `gh issue view <n> --json state` 校验 `status=open` 条目的 issue 仍 open，并比对 `gh issue list --label tech-debt --state open` 与登记表 issue 集合，报告「未登记的新债」。网络失败 ⇒ 退出码 2（诚实报错，不静默跳过）。

`--self-check`：临时目录造 7 种变异（缺字段 / 空话判据 / 过期 / open 已满足 / done 未满足 / 删权威标记 / 空登记表），断言各自转红或 exit 2。

退出码：`0` 通过 / `1` 命中栅栏 / `2` 输入不可信。

---

## 6. 迁移范围与边界

**收录**（本次约 26 条）：

- 僵尸条目 6 条 → `done` + `evidence`（§79/§80/§84/§121–127/§81/§985 相关）
- 实证未处理的高价值项 → `open` + 自动/命令判据
- #2803 → `blocked`（迁移已落地 + 守卫绿，blocker = 等发版同步 main 后关单）
- 已裁决项（D81 无 Alembic、审计器不进 CI、Element Plus 按需引入、桑基图底层限制）→ `wontfix` / `deferred` + 决策或触发条件

**不收录**：`tech-debt.md` 里已标 ✅ 的历史条目（约 60+ 条，逐条迁移收益低且易抄错）；§15 用户手册 / 落地页视觉抛光等「低·不紧急」项（本来就不进治理批次）。登记表头部显式写明「未收录条目按历史归档处理，新增债一律先登记」。

**不改动**：`tech-debt.md` 正文逐字保留（符合文件头「请勿删除历史条目」），只在头部加权威声明 + 一段 2026-11-10 批量复核更正表。

---

## 7. CI 接线与回归网

- `ci.yml` `scripts_test`：新增一步 `python scripts/guard_tech_debt_register.py`（阻断），放在设计文档索引守卫附近。
- `scripts/tests/test_guard_tech_debt_register.py`：unittest，随 `python -m unittest discover -s scripts/tests -p "test_*.py"` 自动收；含真实仓库绿 + 6 种变异转红 + 失败态 exit 2 + `--self-check` 自检通过。
- 回归网本身按仓库惯例「反向验证」：删掉登记表里任意一条的 `criterion`，守卫与 `test_real_repo_passes` 必须同时转红。

---

## 8. 回滚

纯增量、无数据变更：

1. `git revert <commit>` 即回到旧流程（登记表 / 守卫 / CI step / 头部声明一并撤销）；
2. 若只想临时停用判定、保留台账：`ci.yml` 里把该 step 注释掉即可，登记表仍是唯一真源；
3. 无 DB 迁移、无前端构建产物、无对外 API 变更。

---

## 9. 验收判据（可复算）

```bash
python scripts/guard_tech_debt_register.py            # exit 0
python scripts/guard_tech_debt_register.py --self-check  # exit 0（7 态变异全被咬住）
python -m unittest scripts.tests.test_guard_tech_debt_register -v
python scripts/guard_rule_registry.py                # 不受影响（AGENTS.md 未改）
python scripts/check_design_doc_index.py             # 不受影响
```

反向验证：把 `tech-debt-register.toml` 里任一 `status = "done"` 改成 `open`，守卫必须转红（「僵尸 open」判据 R4）；删掉 `tech-debt.md` 头部的 `STATUS_AUTHORITY` 行，守卫必须转红（R5）。

---

## 10. 已知不覆盖边界（如实登记）

- `command` 类判据不自动执行，靠 90 天新鲜度闸门；`--online` 的 issue 覆盖度不接 CI（避免网络抖动制造假红），由治理动作手动跑。
- `doc_ref` 行号会随文档编辑漂移，守卫只校验文件存在、不校验行号内容。
- 守卫不判断「这条债是否值得做」，只判断「状态是否与可复核的事实一致」；价值排序仍由人拍板。
- 登记表只收本次盘点覆盖的条目；历史 ✅ 条目未逐条迁移，故「登记表条目数」不能当作全仓技术债总数。
