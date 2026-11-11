# 配置目标数据治理（五笔钱成员边界 / 现金归活钱 / 来源标记）

> 跟踪 issue：[#3031](https://github.com/imoyao/fundmate/issues/3031)
> 状态：**方案冻结（2026-11-10）**，按 G0→G6 顺序实施；G3 实改前必须先交 dry-run 报告。
> 概念 SSOT 仍是 `docs/features/concepts.md`；本文只定义**数据口径与治理流程**，不改概念定义。

## 一、为什么要做

首页「心理账户」卡片是硬编码 mock（`store/modules/overview.ts` 的 `mockPsychAccount`），排查时顺藤发现更根本的问题：

本机家庭总资产 **¥3,384,804.89** = 房产 2,200,091 + 持仓 669,535.33 + 类现金 465,178.56 + 应收 50,000（负债 1,760,000 单列），而 `/api/summary/distributions/` 的 `allocation_distribution` 只返回 `[{长期增值, 669535.33}]` —— **五笔钱只看得见约 19.8% 的资产，且全挤在一档**。

用户反馈的原话是：「每个账户里面可能有一些类似现金的东西，它应该自动归入活钱里面」「银行里有多少钱，或者有多少现金，我们应该能够修改和配置，这一块目前并没有体现出来，所以导致我们的数据是空态的」。

这句话把两件事串起来了：**不是 UI 缺一个空态，而是数据模型缺一类成员**。

## 二、问题清单（本机实证，见 §五核实记录）

| # | 问题 | 证据 |
|:---|:---|:---|
| P0-1 | 五笔钱分布只遍历 `positions`，资产行整类被排除 | `summary_service.py:834-843` vs `:848-857`；`get_position_groups('allocation')` 同样只遍历 positions（`:998-1001`）；`_asset_group_payload:953-963` 连 `allocation` 字段都不返回。`assets.allocation` 能写（`assets/schemas.py:40,60`）、能展示（`assets/views.py:35`），对五笔钱零影响 |
| P0-2 | 类现金 46.5 万不进五笔钱 | 222 笔孤儿货基/逆回购流水只进 `category_distribution`「流动资金」与总资产（`:862-866`），`/api/summary/cash-like/` 实测 465,178.56 |
| P0-3 | 账户现金余额 0 行、账户页不能改 | `assets` 中 `major_category='cash'` 0 行；`AssetEditDialog.vue` 只能改金额/备注/子类；`LedgerCashLikeCard.vue` 是纯展示卡 |
| P0-4 | 新建现金资产会被标成「长期增值」 | `assetEntryModel.ts:140` 空值不传 allocation → `AssetCreate` 默认 `'longterm'`；无 `cash ⇒ liquid` 规则 |
| P0-5 | 264/264 持仓全 `longterm`（**值本身不错，见 §4.1 反证**；缺的是现金类成员） | 16 个账户 `default_allocation` 除 1 个外全为 longterm；`orchestrator_holdings.py` 多处硬编码 longterm；`orchestrator_parse.py:517` 只给货基流水 `liquid`，而货基不建持仓 |
| P0-6 | 负债行也带 `longterm` | `conventions.md:98` / `decisions.md:147` 冻结「负债不参与五笔钱」；本机 2 条 liability 行均为 longterm。修 P0-1 时若不加守卫，负债会被算进「长期增值」 |
| P0-7 | 分不清「系统默认」与「用户设过」 | 全表无 `allocation_source`、无字段级 updated；只有导入预览内存里有 `allocationEdited`（`previewRow.ts:36`）。批量回填会覆盖用户手工配置 |
| P0-8 | 账外 46.5 万是「待核实」数据 | `LedgerCashLikeCard.vue:81-87` 自述「可能混有跨账本重复导入…请把本区块视为待核实」 |

附带两项：`count_as_investment` 264 条全 NULL（2026-09-07 已终局拍板的「per-asset 算现金还是投资」开关从未被使用）；`conventions.md:94` 的三层优先级链（Ledger → 导入行 → Position）**根本没有 Asset 与类现金流水**。

## 三、冻结口径（2026-11-10 用户确认）

| 决策点 | 结论 |
|:---|:---|
| 分母与成员边界 | **只算可投资资产端**：持仓 + 现金类资产 + 已核实账外类现金。房产 / 应收 / 负债不进，另出「未纳入」提示 |
| 账外孤儿类现金 | **先对账核实再归置**；治理期间「活钱」保持空态提示，不给 100% 假柱子 |
| 存量 3 条非默认 allocation | 标 `user` 保留、不被回填；在新边界下属「未纳入」，**值保留但不参与分布** |
| 账户现金录入 | **一账户一条 cash 资产行**，复用 `assets` 表与 `AssetCreate/Update`，不改 `ledgers` schema；`major_category='cash'` 且 `allocation` 强制 `liquid` 只读 |

### 3.1 分母两阶段（必须在 UI 明示）

| 阶段 | 成员 | 分母 |
|:---|:---|---:|
| G0 后（账外未放行） | 持仓 + 现金类资产 | 669,535.33 |
| 账外核实放行后 | 上述 + 已核实类现金 | 1,134,713.89 |

同一张图上「长期增值」占比会从 100% → 59% 左右。UI 必须**明示当前分母与「未纳入」金额**（房产 220.01 万 / 应收 5 万 / 负债 176 万），否则用户会以为数据算错了。

### 3.2 优先级链补记（`conventions.md:94`）

原三层链（Ledger → 导入行 → Position）保持不变，补两类成员：

- `Asset` 资产行：用户显式设置 > 大类推导规则 > `longterm` 默认；**负债行永不出链**。
- 类现金孤儿流水：不落 `positions`，按「产品大类 → `liquid`」单列入桶，须带「账外」标记与下钻入口。

**回填判据必须同时满足**：`allocation_source='default'` **且**该行在成员集合内。只改两者都满足的行——那 3 条 `user` 值保留但不进分布，就是这个判据的直接后果。

## 四、执行批次

| 批次 | 内容 | 关键判据 |
|:---|:---|:---|
| **G0** | 定口径；`conventions.md` 补两类成员；核实记录归档 | 负债永不进；房产/应收列为「未纳入」；对账结论书面留档 |
| **G1** | `positions` / `assets` 加 `allocation_source`（`default\|import\|user\|governance`）+ 迁移；导入、行内编辑、资产表单三处写入侧补齐 | 存量 3 条标 `user`，264 条 longterm 持仓与其余资产标 `default` |
| **G2** | 归置规则收敛为**一个纯函数 + 单测**：cash / 货基 / 逆回购 / 已核实类现金 → `liquid`；bond / 银行理财 → `stable`；fund / etf / stock → `longterm`；insurance → `security`；`speculative` 不自动判留人工 | 规则表对齐 `core/investment_tiers.py`；**负债零命中**；同一规则不得在两处各写一遍 |
| **G3** | 一次性回填：`--dry-run` 出 CSV（id / 名称 / 旧值 / 新值 / 依据 / 金额），备份两表快照，事务内批量改并标 `governance` | 幂等（重跑零变更）、可按快照回滚、只碰 `default` ∩ 成员集合 |
| **G4** | `get_distributions` 与 `get_position_groups('allocation')` 纳入非负债资产行 + 已核实类现金；`/api/summary/groups/` items 让「活钱」可下钻 | **Σ五笔钱 ≡ 该口径分母** 恒等断言，防与 `category_distribution` 双算（`ledger_service.split_cash_like_allocation:406-433` 有前车之鉴） |
| **G5** | 账户详情「类现金」卡加「录入/修改账户现金」；`AssetEditDialog` 补配置目标（负债行隐藏） | 不改 `ledgers` schema，统计出口天然同源 |
| **G6** | 回归网 + 文档同步 | 负债零命中、恒等断言、来源标记不被批量覆盖、反向探针；`docs/features/concepts.md` 口径补记；新增 `docs/design/*.md` 须登记 `index.md`（集合相等守卫） |

**硬依赖**：G2 的「已核实类现金 → `liquid`」与 G4 的入桶，输入都是 §五的对账核实结论。核实结论未完成前，「活钱」只能是空态提示——不是「不能给 100% 假柱子」，就是同一条纪律。

### 4.1 dry-run 反证：G3 回填是空操作，主线要换

2026-11-10 用 `scripts/backfill_allocation.py` 在本机真库跑 dry-run（`SIMULATED` 模式——
G1 迁移尚未应用到真库，脚本按迁移打标规则在内存里推来源并显式标注）：

| 表 | 总行 | 结果 |
|:---|---:|:---|
| `assets` | 4 | 2 条负债跳过、2 条非成员（房产 / 应收）跳过 → 0 条变更 |
| `positions` | 264 | 全部 `no_change`（旧值 `longterm`，规则表对 fund/stock/etf 也判 `longterm`） |
| **合计** | 268 | **建议变更 0 行** |

这推翻了「264/264 持仓全 `longterm` 是待回填的错误值」这一诊断：**值本身没错**。
五笔钱只有一个桶的真正原因是**成员缺失**——现金类资产行 0 条，账外类现金流水
只落在 `transactions`、既不进 `assets` 也不进 `positions`，所以无论怎么回填都冒不出 `liquid` 桶。

⇒ **批次顺序据此调整**：G3 降级为「守门 + 幂等验证」（当前数据下预期 0 变更，重跑零变更），
**真正让「活钱」有内容的是 G5（录入账户现金资产行）与 G4（统计侧纳入 Asset 与已核实类现金）**。
P0-5 的措辞应改为「持仓侧缺少现金类成员」，而不是「持仓值错」。
G3 实改因此更没有理由现在跑：先让用户把现金录进来，回填才有对象。

## 五、对账核实结论（2026-11-10，只读）

完整记录与复现脚本见 `docs/working-notes/cash-like-orphan-flows-2026-11-10.md`、`scripts/reconcile_orphan_cash_flows.py`。要点：

- 222 笔孤儿类现金流水（`position_id IS NULL AND asset_type IN ('money_fund','reverse_repo')`），按 `orphan_flow_delta`（`summary_service.py:276-307`）复算：本金 **465,096.82** + 收益 **81.74** = **465,178.56 元**，与 `/api/summary/cash-like/` 完全一致。按账本：ledger 12 = 464,705.93 + 81.74，ledger 20 = 390.89。
- **跨账本重复 = 0 组**：`/api/reconciliation/ghost-duplicates/` 实测 `groups=0`；按 `scan_cross_ledger_duplicates` 指纹在这 222 笔内复算亦为 0；`import_hash` 重复仅 1 组 3 行且同账本。222 笔 `status` 全为 `success`、`confirm_date` 全有值，说明**对账中心确实扫到了这些行**，0 组不是漏扫。
  ⇒ `LedgerCashLikeCard.vue` 那句「可能混有跨账本重复导入」是历史保守文案，**在本机数据上不成立**。
- **但发现真问题**：162 行 `trade_date` 为空、158 行 `symbol` 为空、`source` 全 NULL、`entry_status` 158 行 NULL（另 53 `pending_cash` / 11 `orphan`）、7 行 `trade_date` 带时间、7 行 `import_hash` 为空；这批行几乎全在 ledger 12，流水毛毛额合计 135.30 万。
  ⇒ 约束理由从「疑似跨账本重复」改为「**来源不可追溯、无法逐笔下钻对账**」。

**待用户确认**：是否放行这 46.5 万进入 G4 分母，还是先补元数据治理（回填 `trade_date` / `symbol` / `source`）。本轮不擅自把待核实数据洗成确定值。

## 六、纪律与门禁

- 改动只在 worktree 进行，主仓固定 `dev` 只读（跑 dev server）；回填真实数据前必须先交 dry-run 报告并取得确认。
- 改后端 views/services 注意 `check_view_thickness.py` / `guard_service_size.py` 基线「只减不增」，且 `ruff format` 会把深层长中文文案折行顶破 `max_func`（#2977）——长文案抽模块常量。
- 改 `.vue` 前跑 `node scripts/check_vue_size.mjs --baseline`；新增 `docs/design/*.md` 必须同步 `docs/design/index.md`（`check_design_doc_index.py` 集合相等）。
- 归置规则、净额口径必须**单一真相源**：前者收敛成一个纯函数，后者继续复用 `orphan_flow_delta`，禁止在治理脚本里复制 elif 链（#2839 教训）。
- 反向验证：删掉真实规则实现后守卫必须变红（变异先确认「真的应用了」，#2739 教训）。
