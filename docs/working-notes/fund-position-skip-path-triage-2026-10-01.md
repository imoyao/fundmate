# fund_position 跳过路径三处缺陷 + 生产回填（2026-10-01）

> 触发：#870 合并后做生产库首次回填，**第一次执行就失败且没写进任何数据**。
> 结论：*不是数据源问题，是 CLI 与 job 早退路径的三个独立缺陷*。全部已修，生产回填随后成功。

---

## 1. 现象：`pdm run sync --job fund_position` 报「同步失败」

```
12:50:07 | INFO    | orchestrator:run_job:371 - 开始执行 fund_position (全量=False, 目标数=全部)
12:50:07 | WARNING | fund_position_job:run:88  - 目标池为空或仅含 __full__：... 显式跳过
12:50:07 | ERROR   | __main__:main:185       - 同步失败: unsupported operand type(s) for -: 'datetime.datetime' and 'NoneType'
EXIT=1
```

注意日志顺序：**守卫先正确跳过，然后才崩**。也就是说「数据没写进去」不是 bug，
bug 是「跳过」这件事本身把 CLI 带崩了 —— 而且崩在 `main()` 的通用 except 里，
错误信息完全指不到现场。

---

## 2. 三个独立缺陷

### 缺陷 A（crash）—— 覆写 `run()` 时漏赋 `snapshot_time`

`orchestrator.run_job:378` 用 `now_shanghai() - job.snapshot_time` 算 duration。
`snapshot_time` 由基类 `SyncJob.run()` 开头赋值（`job_base.py:188`），而
`FundPositionSyncJob` **覆写了 `run()`**，空池时直接早退，从不进基类 → 属性停在 `None`
（`job_base.py:73` 初始值）→ `datetime - None` → TypeError。

**这是本仓既有约定**：另外 4 个覆写 `run()` 的 job（`position_price` /
`fund_detail_enrich` / `fund_company_backfill` / `asset_snapshot`）**都在开头显式
`self.snapshot_time = now_shanghai()`**。`#870` 新增的这份覆写漏了这一步。

连带第二个伤口：`_save_sync_log:517` 的 `started_at=job.snapshot_time` 而该列
**NOT NULL** → 即使 duration 那行修好，这里还会抛 IntegrityError，触发
`_save_sync_log_with_fallback` 的「降级重写」，把一条本该是 `success` 的审计行
降级成 error，并在日志里多打一轮 warning 掩盖真相。

> 注：`_save_error_sync_log:538` **早就有** `getattr(job, 'snapshot_time', None) or now`
> 的防御（注释里甚至写明了「未进入 run() 就炸」这种形态）。同一文件里两条审计路径
> 一个防一个不防，说明这不是新问题，是「防御只补在异常路径上」的遗留。

### 缺陷 B（silent no-op）—— CLI 不会解析核心池

`sync_metadata.py` 的 `--job` 分支原先只认 `--targets` / `--target-file`，
不给就 `targets=None`。而 `None` 在 `job_base.SyncJob.run():195` 的语义是
「子类自取全部数据」—— 对 `fund_position` 却是「目标池为空 → 显式跳过」。

`daily_scheduler` 走的是另一条路（`spec.target_kind` + `resolve_targets()`，
`daily_scheduler.py:453`），所以**周任务一直是好的**；只有手工 CLI 踩坑。

即使修好缺陷 A，这个缺陷的表现会从「报错」变成「**静默 success + 0 只**」——
对做手工回填的人更危险（会以为成了）。

### 缺陷 C（静默拿不到目标）—— `--target-file` 的基金分支漏了 `fund_position`

同处还有一份硬编码元组 `('fund_nav', 'fund_detail_enrich', 'fund_manager')`，
`fund_position` 不在其中 → 给了 `--target-file` 也解析不出目标。
这份元组的失效模式**不是报错而是静默**，属于容易被复制粘贴漏掉的地方。

---

## 3. 修复

| 位置 | 改动 |
|---|---|
| `fund_position_job.py` | `run()` 开头补 `self._full_sync_flag` / `self.snapshot_time = now_shanghai()`，并对齐既有约定加注释说明「为什么必须自己打时间戳」 |
| `orchestrator.py` | `run_job` 的 duration 与 `_save_sync_log` 的 `started_at` 均降级为 `job.snapshot_time or now`（与 `_save_error_sync_log` 同口径，双保险） |
| `sync_metadata.py` | 新增 `FUND_TARGET_JOBS`；新增 `DB_POOL_JOBS = {'fund_position': 'fund'}`；把解析逻辑抽成可测的 `resolve_job_targets()` |

`DB_POOL_JOBS` **只放 `fund_position`**：其余逐标的 job 的 `targets=None` 是
「子类自取核心池」的既有语义，赋成显式列表会把执行切到 `_execute_batches`
分批路径，属行为变更，需单独评估（代码内已写明）。

---

## 4. 验证

**单测**（`35 passed`）：
- `test_skip_path_always_sets_snapshot_time`（参数化 empty / none / `__full__`）
- `TestRunJobToleratesMissingSnapshotTime`：含「子类完全不赋 snapshot_time」的兜底用例，
  以及真实 `FundPositionSyncJob` + 空池走 `run_job` 的端到端复现
- `tests/tools/test_sync_metadata_targets.py`（7 例）：含「其余 job 仍保持 None 语义」的反向保护

**端到端**（隔离库，不碰生产）：
- 空库 + 裸调用 `--job fund_position` → 解析 0 只 → 跳过 → `status=success, duration=0.0` → **exit=0**
  （修复前：TypeError + exit=1）
- 空库 + `--target-file`（1 只 `000001`）→ 2 次外部请求（`jjcc` 51KB / `HYPZ` 4KB，均 200）
  → 落 77 条持仓（2026Q2/full）+ 5 条行业（csrc）→ **exit=0**

---

## 5. 生产回填结果（`D:/codes/fundmate/backend/invest.db`）

回填前**先做了完整备份**：`H:/fundmate-backups/invest-prod-before-870-20261001.db`
（1,224,622,080 字节，`pragma integrity_check` = ok，与生产行数一致）。
备份前该库 `fund_holdings` / `fund_industry_allocs` 两表为空，`funds.equity_position`
**全库 26,938 行均为 NULL** —— 即本次是纯新增填充，没有既有值需要保护。

回填走的是与调度器等价的路径（`resolve_targets()` + `run_job`），
**不用** CLI（当时 CLI 正好是坏的）：

```
status=success  total=117  success=101  failed=0  duration=363s（6.1 分钟）
```

| 表 | 行数 | 说明 |
|---|---|---|
| `fund_holdings` | 6,423 | 101 只基金；`2026Q2` 6,389 / `2025Q4` 30 / `2026Q1` 4 |
| `fund_industry_allocs` | 830 | `csrc` 654 / `gics` 176 |
| `funds.equity_position` | 101 行被填充 | 报告期 `2026Q2` 99 / `2025Q4` 1 / `2026Q1` 1 |

`holding_basis`：`full` 6,419 / `top10` 4（季报只披露前十大者）。

**一致性核验**（只读复算）：
- `equity_position` 与该基金同报告期行业配置合计 **101/101 精确一致**（零偏差）
- 100 只可交叉验证的基金：行业合计 vs 持仓全量合计，**中位偏差 0.020pp**
- `ratio > 100` 行数 = 0，最大 `ratio` 17.28%，数值列无空值

### 偏差 Top5 恰好全部是「100 条持仓」—— 反向证明口径选择正确

| 基金 | equity_position（行业合计） | 持仓全量求和 | 偏差 |
|---|---|---|---|
| 019983 | 92.25 | 29.66 | 62.59pp |
| 001414 | 93.23 | 41.46 | 51.77pp |
| 018963 | 93.97 | 44.77 | 49.20pp |
| 008318 | 89.75 | 55.78 | 33.97pp |
| 022165 | 90.75 | 83.54 | 7.21pp |

这几只的持仓行数**恰好都是 100** —— 即东财接口的 100 条硬截断（明细链路的已知上限）。
全库共 **19 只**撞到 100 条。也就是说：若沿用「前十大/持仓求和」口径，
**约 19% 的目标池基金会被系统性低估**（最高 62.6pp），而行业配置合计不受该上限影响。
这是「`equity_position` 取行业合计」这一设计选择的直接实证。

---

## 6. 顺带更正：一个被误判的环境结论

`#870` 提交过程中观察到「git 元数据不可信」（`git commit` 成功但分支 ref 消失、
`refs/heads/feat/` 目录整目录消失、`update-ref` 返回 0 但不落盘），当时判断为仓库
后端异常。**该判断证据不足，应予更正。**

2026-10-01 重测：

- `git update-ref refs/heads/fix/zzz-probe` **正常落盘**，`refs/heads/` 下 13 个真实分支
  （`feat/*`、`fix/*`）齐备 —— 嵌套 ref 完全可用；
- 当时唯一稳定的复现条件：**D: 盘处于 444MB / 100% 的有害满盘状态**；
- 另外确认一个纯属自己挖的坑：先前的探针 `refs/heads/zzz-probe`（**作为文件**）残留，
  导致后续 `refs/heads/zzz-probe/nested` 报 `Not a directory` —— 那是 git 正常行为，
  不是损坏（该残留已清理）。

结论：**把「git 元数据损坏」改判为「满盘导致的写入失败 + 我自己的探针残留」**。
不排除并发会话（同机 8 个 worktree）也有影响，但无证据，不再往那个方向下结论。

> D: 盘的容量问题本身仍未解决（`/d/codes` 下十余个 fundmate* 目录各自带
> `.venv` / `node_modules`）。这是独立事项，需单独处理。
