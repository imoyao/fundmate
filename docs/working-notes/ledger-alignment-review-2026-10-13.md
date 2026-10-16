# 账本能力对齐复核（#2018 × 同花顺调研合集精读，2026-10-13）

> 定位：对 issue #2018（2026-10-10 讨论备份）与《同花顺投资账本调研合集》6 份文档的**精读 + 当期代码二次确认**。
> 证据基线：仓库 `main`/`dev` 2026-10-13 快照（`origin/dev` = `4daf620b0`）。
> 产出：① 复核表（承重结论逐条判定）；② 五处需对齐的矛盾；③ 修正后的卡清单；④ 拍板记录（2026-10-13 用户确认）。
> 关系：#2018 是粗糙调研 + 讨论备份；本文是深化层的**仓库内落地版**（深化调研文档原文在仓库外，结论已消化进本文）。

---

## 1. 一句话结论

**调研大方向全部成立，无系统性走偏**。账本主干（成本/流水/分红/估值链路/导入）已完整，多项比同花顺更深（盈亏三段口径、穿透、行为偏差、对账、双口径股息率）。真缺口集中在**分析深度**（基准/归因/TWR）、**账本可信度**（清仓统计/快照体系/状态标注）、**建模完整度**（现金/税费/定投/多市场）。但文档有 **5 处已过期或自相矛盾**，直接照 #2018 开卡会踩坑——本次已全部修正并拍板。

## 2. 承重结论复核表（文档 vs 2026-10-13 代码）

| # | 文档结论 | 判定 | 关键证据 |
|---|---|---|---|
| 1 | `ClearedPosition` 零写入方，清仓即删持仓行 | **成立，且比文档更甚：零写入且零读者** | `backend/app/domains/watchlist/models.py:143`（唯一命中）；frontend 零命中；无端点；`transactions/models.py:39`（清仓删行） |
| 2 | 无 TWR/Dietz | **成立** | 全仓代码零命中（`twr`/`dietz`/`time_weighted`/`时间加权`）；`docs/features/xirr.md:93,99,230` 明确「不做 TWR」；`docs/spec/decisions.md:88` D6 列为 P2 |
| 3 | `asset_snapshot` 不在每日调度（#2018 当缺陷） | **成立但结论反转：是 D21 有意排除** | `daily_scheduler.py:390`；且 `pnl_calendar.py:7-16` / `pnl_snapshot_store.py` 已论证 `asset_snapshots.snapshot_date` 只是标签、收益历史已改走事件驱动新路 |
| 4 | `benchmark` 只存不算 | **成立** | `portfolios/models.py:24` 仅 CRUD（`views.py:35,57,127-128`）；services 层无超额收益计算；`watchlist/models.py:159` `benchmark_return` 同样零赋值 |
| 5 | 现金双标签 + `CASH_SYMBOL` | **成立** | `asset_types.py:42`「现金」/`:57`「流动资金」并存；`constants.py:178`；`:97` `EXCLUDED_ASSET_TYPES` 含 cash |
| 6 | 估值不落库 + `daily_worth` INSERT OR IGNORE | **成立** | `usePositionValuation.ts:15-16`；`fund_nav_job.py:150-160`（`bulk_insert_if_not_exists` + 唯一约束） |
| 7 | performance 目录仅 XIRR | **成立** | 只有 `xirr_engine.py`/`calculators.py`（一粒孤儿 `.pyc` 残留，顺手清） |
| 8 | #1969 市场归一 live bug（deep survey 列 P0） | **⚠️ 已过期：已修复** | 提交 `bc22d1381`（2026-10-09）；`product_identity.py:93-96,191-194` 出口归一 + 读侧别名 |
| 9 | 同花顺导入仅股票交割单 | **成立** | `registry.py:54-63`：ths/ths_stock = `THSStockParser`（股票交割单），无基金/持仓 parser |
| 10 | 无定投计划模型 | **成立** | domains 下「定投」命中全为投顾产品名；`recurring`/`dca` 零命中 |

残余小风险（不单独立卡，随相关改动顺手修）：`position_service.py:1484-1485` market 过滤仍精确匹配（未走别名），当前写入口径统一无错位，存量混存 SH/SZ 时会漏命中。

## 3. 五处必须先对齐的矛盾（不修就开卡会做错）

1. **B 卡方向与 D21 决策冲突**：#2018 B 写「进每日调度」，但那是 D21 有意排除的；`asset_snapshots` 已被降级为「同比底座」，每日资产历史走 `pnl_snapshot_store` 事件驱动新路。B 卡不能按原文实施 → **重写为「快照体系收口：明确 asset_snapshots 定位 + 确认 pnl_snapshot_store 覆盖范围」，先立卡记录问题，后续调研拍板**（拍板 5）。
2. **C 卡（TWR）三处口径打架**：#2018 要做 / `xirr.md` 不做 / D6 排 P2 → **先立卡记录现状，实现时再统一口径**（拍板 6）。
3. **A 卡口径已降级**：「卖完赚了多少永远查不到」是夸大——realized 记在流水可归集。正确形态是 **A'：从流水聚合清仓周期统计**（首买→末卖），不新建写入方。
4. **`ClearedPosition` 表零写入 + 零读者**，踩数据策略硬规则「新表必须有读路径」→ **先立卡记录现状，去留后续讨论**（拍板 7）。
5. **P0 已过期**：deep survey 的「立即做 P0 市场归一」已修复合入，文档可结案。

## 4. 修正后的卡清单（13 张，已按拍板落地为独立 issue + 独立里程碑）

| 卡 | 修正后口径 | 体量 |
|---|---|---|
| A' 清仓周期统计 | 从流水聚合周期（首买→末卖），出胜率/盈亏比/平均持有天数；`ClearedPosition` 表去留一并讨论 | 中 |
| B' 快照体系收口 | 明确 `asset_snapshots` 为同比底座；每日历史走 `pnl_snapshot_store`；不是「进调度」 | 小 |
| J 数据状态标注 | 正式/预估/数据不足三态，各区块口径统一 | 小 |
| K 收盘后估值快照 | 收盘后定格落库（盘中不落库不变）；**独立 `valuation_snapshots` 表**（拍板 3），带预估/确认状态字段，落库范式仿 `pnl_snapshot_store` | 中 |
| L 预估→正式对照 | 官方净值到位后替换 + 记录偏差；改 `daily_worth` 只补不改语义需过数据策略四问 | 中 |
| M 估值状态收口 | 「估/确认」徽标 + 来源 + 时间（与 J 合并推进） | 小 |
| C TWR | 立卡记录三处口径现状，实现时统一（拍板 6） | 中 |
| D 基准超额 | `benchmark_return` 字段在、零计算（真缺口）；先定「同期」口径 | 中 |
| E 收益归因 | 逐品种贡献；**上调**——zcfx 是同花顺真差异化，fundmate 穿透/分布底座已在 | 中 |
| F 现金闭环 | 消除三处表达 + 统一收益分母口径；**单独排期**（拍板 4） | 大 |
| G 佣金/税费分离 | 现只有聚合 fee + `txn_type='tax'` | 小-中 |
| H 定投计划模型 | 现只能记流水；新建计划模型过数据策略四问 | 中 |
| I 多市场日历/时区 | 收窄：契约市场已建模（`markets.py`），缺按市场分日历/时区；**单独排期**（拍板 4） | 大 |

独立挂起项：**同花顺基金/持仓导出 parser**——阻塞在用户提供脱敏样本，不盲写（不入本里程碑，样本到位后另开）。

**推荐顺序**（待用户拍板，记录在汇总卡）：线二（K/L/M，底座已就绪、用户价值最直接）为主线，A'/J 顺带；其余按依赖排。原 #2018 四线分组：线一 = A/B/J（可信度）、线二 = K/L/M（收盘后估值）、线三 = C/D/E（分析深度）、线四 = F/G/H/I（建模完整度）。

## 5. 明确不做清单（同花顺有，我们不要）

- **券商自动同步**：依赖券商授权体系，与「公开数据源 + 导入」路线根本冲突；
- **同花顺数据接口逆向**：薄客户端五层证据已判死，且越合规边界；
- **模拟盘 / 信用卡年费规则 / 负债流水计息 accrual**：延后或 roadmap；
- **Lua 热更引擎 / 国密 SKF·PKI 证书 / 请求签名栈 / 多厂商推送 / 直播·IM·OCR 人脸全家桶 / 高危权限**：全部是「券商交易 App 合规产物」，对 web 个人账本是纯反例；
- **港股/美股独立行情表**：重活，随 I 一起评估。

反向确认：同花顺最重的架构全部服务于交易执行，再次验证 #1969 定位——账本回答「我赚了多少」，深度研究交给专业站。**不要用它的功能清单当标尺**：fundmate 在盈亏三段口径、持仓穿透、行为偏差、对账、双口径股息率、A 股交易规则校验、经理/投顾画像、温度计上已超越它。

## 6. 拍板记录（2026-10-13，用户）

| # | 事项 | 决定 |
|---|---|---|
| 1 | 开卡方式 | 13 张卡各开独立 issue + 1 张汇总卡，统一放入**新独立里程碑** |
| 2 | 线序 | 用户初询「线一/线二」含义（见 §4 说明）；最终顺序记录在汇总卡，推荐线二先行 |
| 3 | K 落库形态 | **独立 `valuation_snapshots` 表**（不并入已被否决的 `asset_snapshots`） |
| 4 | F / I | **单独排期**，不进本期 |
| 5 | B 卡 | 先立卡记录问题，后续调研/深入讨论 |
| 6 | C 卡（TWR） | 先立卡记录现状口径，实现时再统一 |
| 7 | ClearedPosition 去留 | 先立卡记录现状，再去讨论 |

## 7. 顺带文档债（随下次相关 PR 手修，不单独立卡）

- `services/thermometer/README.md` §一仍写「本地脚本 → cache_latest.json → HTML」，实际已迁 Flask + 每日调度 20:00；
- `thermometer/jobs.py` docstring「调度建议 21:30」vs 实际 20:00；
- `pnl_service.py` 注释仍引旧路径 `performance/xirr_engine.py`（现 `services/performance/`）；
- `services/performance/__pycache__/constants.cpython-312.pyc` 孤儿字节码。

## 8. 证据索引

- 复核方式：全仓 grep/read（`ClearedPosition`、`twr|dietz|time_weighted`、`asset_snapshot`、`benchmark`、`CASH_SYMBOL`、`to_contract_market|market_aliases`、`定投|recurring|dca`、registry source 清单、performance 目录清单）。
- #2018 与 6 份调研文档（`tzzb_research_wrapup` / `tzzb_valuation_dividend_deepdive` / `data_acquisition_strategy` / `fundmate_vs_ths_deep_survey` / `tzzb_architecture_review` / `tzzb_highvalue_reference`）已全文精读，结论消化于本文。
- 相关仓库内文档：`docs/working-notes/investment-ledger-gap-analysis-2026-10-10.md`、`ledger-capability-backlog-2026-10-10.md`（A–M 原始卡草案，本文为修正层）。
