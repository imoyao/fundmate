# 技术债务 P0 批次第一批：判据纠偏 + PG 侧真库验证（2026-11-10）

> 前置：`#3032`（台账可判定化）已合入 `dev`（`3d7ad48161`）。本文件是实施记录与**口径裁决材料**，
> 状态一律以 `docs/spec/tech-debt-register.toml` 为准；`tech-debt.md` 只是历史归档。

## 1. 先证伪：昨天刚落的登记表，三条 P0 判据有两条是假的

| 条目 | 原判据 | 为什么不可信 |
|---|---|---|
| TD-010 两套市值基准 | `grep ledger_service.py "NavService.get_latest_navs" present=false` | 指向的是 `ledger_service.py:53/70` 的**第三套裸算实现**，不是「品类聚合 vs 总资产」两套基准。把裸算收敛掉就会判「已完成」，但基准分叉仍在 ⇒ 会逼出假 `done`。 |
| TD-011 四列 vs FIFO | `grep frontend/src/api/summary.ts "只声明被消费的字段" present=false` | 这句**只存在于 `summary.ts:198` 的块注释**。删掉一行注释即判「已完成」，与盈亏口径统一毫无关系 ⇒ `#2453`「注释喂饱判据」的翻版。 |
| TD-012 CI 真 PG | `command: guard_migrations_pg_aware.py && grep -n 'postgres' ci.yml` | `grep` 命中注释也算；且 `command` 类型**不自动执行**，靠 90 天新鲜度闸门 ⇒ 既测不了「真 PG 在跑」，连「有没有接」都不判。 |

**结论：先修判据，再修债。** 否则这轮治理会以「删几行注释全绿」收场，比不改更坏。

## 2. 实证复核：三条 P0 的真实状态（file:line）

### TD-010 —— 待 owner 裁决，本轮不改口径

- 品类聚合：`position_aggregation.py:176` 取 `NavService.get_latest_navs(..., allow_remote=False)`（库中最新 `DailyWorth.unit_nav`，`nav_service.py:87-116`）→ `:236` `effective_nav` → `:239` 注入 `position_valuation.market_value_cents`。
- 家庭总资产：`summary_service.py:174` 调用同一函数但**不传** `effective_nav` ⇒ 落到 `position_valuation.py:105` 的 `positions.current_price`（快照价）。
- 差值可复算：`quantity × (nav_T − nav_{T-1})`。`position_price_job.py:95-97,239-248` 每日 22:15 回写 T-1 确认净值，新鲜度闸门 7 天；聚合侧直接读库内最新 T 日净值 ⇒ 同步窗口内必然分叉。
- 货币基金**不因净值日分叉**（`money_fund_daily_worth.nav_per_10k`，净值恒 miss 回退面值），但本金形态不同（持仓 vs 孤儿流水净额），是另一类不等。
- 历史归档 `tech-debt.md:1195` 原文：「**待决策**：两套基准是否统一、以哪一侧为准。判据是「持仓多久同步一次」与「快照历史能否重算」，不靠拍脑袋换基准。」
- **本轮不擅自统一**：切 summary 到净值会让总资产 / 快照 / 环比同比一起跳变，而存量 `asset_snapshots` 按旧基准写下且按 D62/D65 禁止伪造式回填 ⇒ 制造口径不连续；反向把聚合改回 `current_price` 会推翻 `#1133` 修过的「账本页与聚合页市值不一致」，属倒退。

裁决所需三个选项（代价已实测，供 owner 拍板）：

| 选项 | 动作 | 代价 |
|---|---|---|
| A 统一到快照价 | 聚合侧停注 `effective_nav` | 最快；但推翻 #1133，账本页回到「净值更新滞后一天」的旧问题 |
| B 统一到库内最新净值 | summary 全域注入同一 `ValuationContext` | 需一次性批量取净值（禁 N+1）；总资产 / 快照跳变；存量快照口径不连续，须先定 CALIBER 版本与存量处置 |
| C 保留双基准但显式标注 | 品类卡显示「净值日 T」，总资产显示「快照日 T-1」并给出差值 | 零数据风险；但用户仍会看到两个不等的数，只是变成「可解释」 |

### TD-011 —— 同样待裁决

`asset_snapshots` 四列读流水 `transactions.realized_pnl`（存量全 0，与真零不可区分），「已落袋表现」走 FIFO 配对自算（口径 v2）。归档 `:1063` 已给倾向（FIFO 为准、流水列标不可用），但「定唯一口径」属业务裁决，本轮不替 owner 拍板。

### TD-012 —— 无需业务裁决，本轮闭环

- `scripts/guard_migrations_pg_aware.py:25-44` 纯 AST 只查「非 SQLite 早退」；`backend/tests/core/migrations_pg_fake.py:85-93` 的假引擎只记 SQL 文本、不连库；`backend/tests/conftest.py:28-31` 在 import 期把 `DEV_DATABASE_URL` 钉成临时 sqlite ⇒ 全仓迁移测试只在 SQLite 上真跑。
- 缺的三件事：PG 是否接受该 DDL、`inspect.get_check_constraints()` 是否真回约束名、违规写入是否被 PG 的 `IntegrityError` 拦下。
- 全仓 workflow 无 `services:` 段，`ci.yml` 零 `postgres` 字样；驱动 `psycopg2-binary` 已在 `backend/pyproject.toml:41`（CI Linux 有效）。

## 3. 本轮落地范围

1. **守卫升级**：`grep` 判据先剥代码注释行再判命中；R2 拒绝「纯中文自然语言」`text`（判据必须指向代码结构，不是注释文案）。带变异探针：把判据文本只写进注释，守卫必须仍判「未满足」。
2. **TD-010 / TD-011** 改 `blocked` + `blocker` / `next_action`，判据换成可复核的人工命令（明确写出「不得仅凭删注释判完成」）；本文件 §2 即裁决材料。
3. **TD-012 落地**：`ci.yml` 的 backend job 加 `services: postgres`，`TEST_POSTGRES_URL` **只挂在串行 step 上**（`pytest -n 0`），跑真 PG 迁移用例；新增 `scripts/guard_pg_migration_ci.py` 结构化钉住接线（含变异探针），TD-012 判据从弱 `command` 换成 `guard`，状态转 `done`。
4. 不新增 CI job ⇒ 不动 `gate.needs`（`#1559/#1560` 两次事故）；真 PG 用例按 `matrix.shard == 'services'` 只跑一次，避开 `-n auto` 8 worker 并发写同一 PG（`_pg_add_check_constraints` 的反射判重非原子，且 #2986 模板并发写坏的教训同源）。**URL 挂 job 级是陷阱**：常规 `pytest -n auto tests --ignore=tests/services` 会收集这份用例、因 URL 存在而不 skip，于是 4 worker 并发撞 `already exists`。守卫把「不得挂 job 级」也钉成判据。

## 4. 边界与风险

- 真 PG 用例读 `TEST_POSTGRES_URL`，**本地无该变量即 skip**；本机无 Docker / psql，故「PG 真的接受约束、真的拒绝违规写入」这一结论**只以 CI 实测为准**，不得拿本地全绿冒充。
- 守卫只钉「接线存在且结构化」，不连 PG；PG 语义由上面的 pytest 用例承担。两者缺一不可：只有守卫会退化成「注释喂饱」，只有用例会退化成「CI 上跑了但没人知道该跑」。
- 剥注释只处理**整行**注释标记（`#`、`//`、`/*`、`*`、`<!--`），不剥 Python docstring（TD-001 的 `nav_per_10k` 在 docstring 里但代码 `:144` 也有 `row.nav_per_10k`，不误伤）；行尾注释与字符串里的 `#` 不处理，属已知边界。
- `.md` / `.toml` / `.yml` 判据仍扫全文——文档本身就是内容，剥注释无意义（TD-004 的 U+FFFD 判据依赖此点）。
- `command` 类判据继续不自动执行：真机 axe、GitHub issue 状态、CI 真 PG 依赖环境，让网络成为阻断条件只会制造假红。

## 5. 验收标准

- 判据：`python scripts/guard_tech_debt_register.py` 全绿；`--self-check` 变异态数 ≥ 9 且全部咬住。
- 判据：`python scripts/guard_pg_migration_ci.py` 全绿；其 `--self-test` 删掉 `services.postgres` / 删掉 step / 把接线只留注释 / 掏空用例 / 把 URL 挂回 job 级，五种变异均红。
- 判据：`python -m unittest scripts.tests.test_guard_tech_debt_register scripts.tests.test_guard_pg_migration_ci` 全绿。
- 判据：`python scripts/guard_rule_registry.py` 登记数递增且预算不超。
- 判据：CI backend job 的 `PG 真库迁移验证` step 真跑（日志里 4 条用例 pass 而非 skip），`gate` 全绿。
- 走查：`tech-debt-register.toml` 里 TD-010/011 为 `blocked` 且带裁决项，TD-012 为 `done` 且带 evidence。
