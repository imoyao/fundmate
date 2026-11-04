# 组合 vs 策略：概念边界与「策略级归因」可行性评估（2026-10-29）

> 触发场景：A 账户主仓固收+，但同时配置了成长/价值类基金。组合按账户绑定后，后者被错误归入固收+。
> 性质：**设计评估（未实施）**，本文只做事实核实与路径判断，不含代码改动。
> 关联：D20（`decisions.md:142`）、2026-06-13 原始决策（`decisions.md:98`）、#1095（lot 批次）、
> #2615/#2617（资金流分层与持仓结构）、#2224/#2237（策略引擎）、`data-model.md §5.11`。

---

## 0. 结论速览

1. **组合与策略不重复**，是三个正交维度（目的 / 风格 / 方法），但**只有组合有收益载体**，
   所以任何「想按 X 分类并看年化」的诉求最后都被迫塞进组合——这是"重复感"的来源，不是模型冗余。
2. **用户场景在数据层已具备**（`positions.portfolio_id`，D20 一期），但**被入口守卫挡住**：
   组合视图以 `ledger_ids` 非空为前提（`portfolio_service.py:59`），而一个 `Ledger.portfolio_id` 是单值。
   ⇒ 「A 账户默认组合=固收+」时，新建的「成长组合」绑不了 A 账户，该组合视图直接为空。
   这是**比"收益算不准"更前置**的阻塞点。
3. **策略级 XIRR 的成本被普遍高估**：基金转换落库为 2~3 条带 `link_group_id` 与
   `extra.conversion.role` 的流水（`conversion_service.py:10`），配对键**已经在库里**，
   不需要新建「内部资金流事件表」。缺的是**归因侧消费它**。
4. **账户级 XIRR 并未因转换算偏**：转换两腿均为 L2，账户口径只取 L1（`cashflow_layers.py:51-53`），
   转换天然被排除，方向是正确的。
5. 真正需要改的是三处：**组合视图入口守卫**、**组合 XIRR 的归属口径**、**策略间 L2 配对消费**。

---

## 1. 事实核实（对参考分析的校正）

背景：一轮外部评估（无代码访问权限）给出若干推断，逐条用代码核对如下。

| # | 外部主张 | 代码事实 | 判定 |
|---|---|---|---|
| 1 | 基金转换"可能只改持仓份额、没有任何流水" | `conversion_service.py:10` 明示：一条转换 = 同一 `link_group_id` 下 **2~3 条流水**（OUT sell / IN buy / REFUND）。OUT 腿带 `position_id`、两腿均带 `ledger_id` | ❌ **有流水**，且带显式配对键 |
| 2 | "账户级 XIRR 很可能已经算偏了，转换不进现金流序列" | 转换 OUT=`sell`、IN=`buy`，二者均属 **L2**；账户口径只取 **L1**（`xirr_engine.py` 第 3 步 `if basis=='account': 仅 L1`）。账户总资产未变，现金流序列不应变动 | ✅ **账户 XIRR 正确**，此担忧不成立 |
| 3 | "必须在持仓/策略维度重建一套内部资金流事件表" | `transactions.link_group_id` 已存在（`transactions/models.py:66`），转换双腿同组；`extra.conversion.{group_no,role,status}` 记录角色 | ❌ **无需新表**，属"存量字段未被归因侧消费" |
| 4 | "策略间资金分摊需要先定口径（实际调拨 / 市值加权 / 时间加权）" | 无对应实现；三种口径在语义上确实互斥 | ✅ **成立**，且是必须由产品拍板的规则 |
| 5 | "现金归属会打架：现金不进持仓级组合" | `portfolio_service.py:84-88` 注释明确：账户级资产仍按 `ledger_id` 关联 | ✅ **成立** |
| 6 | "虚拟子账户（virtual ledger）比打 portfolio_id 补丁更干净" | 现模型 = `Portfolio` + `positions.portfolio_id`（可空继承）+ `ledgers.portfolio_id`（默认组合） | ⚠️ **方向相近但成本被高估**：现有模型已具备"账户内再分层"的表达力，缺的是查询路径而非存储层 |

**净结论**：外部评估在**口径设计**上有价值（#4/#5），在**数据现状**上有多处误判（#1/#2/#3），
导致其把成本估到了「先补账再改造」的档位——实际流水是齐的，成本档位应下调一档。

---

## 2. 三个概念的实际职责（代码核实）

| 概念 | 回答的问题 | 归类粒度 | 能否算收益 | 代码状态 |
|---|---|---|---|---|
| **Portfolio 组合** | 这笔钱**为什么**而投（目的） | 持仓（D20）/ 账户（继承） | 组合 XIRR（**但按账户聚合**） | 字段已落地；查询路径半迁移 |
| **StrategyTag 策略标签** | 这个持仓**是什么风格** | 持仓（`position_strategy_tags`） | ❌ 明确"不影响 XIRR 计算"（`strategy/models.py` 模块 docstring） | 已落地，纯标签 |
| **策略引擎** | 这个标的**该怎么操作**（方法） | 标的 `symbol`（含 `TargetAllocation`） | ❌ 只产信号与配比偏离 | P0/P1 已落地，**仅 1 个策略** |

### 2.1 「重复感」的真正来源

用户口中的"策略"（固收+ / 成长 / 价值）实际**跨了两个语义层**：
- 「价值/成长」= **风格**（StrategyTag 的领域）
- 「固收+ / 趋势 / 长期持有」= **方法**（策略引擎的领域）

系统把这两层拆成了两个模块，且**两者都不产出收益**。于是用户找不到"既能分类又能看年化"的落点，
只能往唯一有收益载体的「组合」里塞——从用户视角看就成了"组合和策略重复"。

> 判据：**不是概念重复，是"收益"这一能力只挂在一个维度上。**
> 只要组合仍按账户聚合收益，这个错觉就不会消失。

### 2.2 已实现的策略资产（回答"长期持有/趋势交易有没有"）

| 项 | 状态 | 位置 |
|---|---|---|
| 需求文档（4 策略 + 分期 + 合规口径） | ✅ 完整，v0.3 | `docs/working-notes/investment-strategy-engine-requirements-2026-10-15.md` |
| 框架（契约/注册表/指标/数据适配/诊断） | ✅ 已交付 | `backend/app/services/strategy_engine/` |
| **趋势跟踪**（双均线） | ✅ **唯一已实现策略** | `strategies/trend.py`，`strategies/__init__.py` 注册一次 |
| 长期持有 / 价值投资 / 波段交易 | ❌ **仅存在于需求文档** | 无实现 |
| 前端入口 | ⚠️ 不在「策略」页，在**盘点页**持仓明细下方 | `views/asset/inventory/index.vue:92,105`（`AllocationTargetCard` / `StrategyDiagnosisCard`） |
| 策略标签页 | ✅ 纯标签 CRUD + 分组 | `/asset/strategies`（`router/modules/asset.ts:244`） |

> 用户"前端没看到"的原因：策略诊断卡挂在 `inventory`（盘点）页，而 `/asset/strategies` 只有标签分组。
> 两处都不叫"策略收益"，自然找不到年化。

---

## 3. 用户场景逐步走代码：卡在哪

场景：A 账户持有 5 只固收+、2 只成长基金；期望固收+归「固收+组合」、成长归「成长组合」，且各自有年化。

### 3.1 第一步：建「成长组合」并指派持仓

- 改派入口存在：`positions/views.py:223` → `resolve_portfolio_change`
- 数据层可存：`positions.portfolio_id`（`positions/models.py:57`，nullable，NULL=继承账户默认组合）

**但随即撞墙**：`portfolio_service.py:59`

```python
ledger_ids = [ ... Ledger.portfolio_id == portfolio_id ... ]
if not ledger_ids:
    return []          # ← 组合未绑任何账户 ⇒ 整个组合视图为空
```

而 `Ledger.portfolio_id` 是**单值**（`ledgers/models.py:91`）。A 账户的默认组合只能是固收+，
故「成长组合」绑不到 A 账户 ⇒ `ledger_ids` 为空 ⇒ **成长组合里什么都看不到**，尽管两只成长基金已显式指向它。

> 这是 D20 一期的**未完成点**：字段落地了，但**组合视图的入口仍是"账户集合"**。
> 结论：用户场景**当前不可实现**，且原因不是 lot、不是收益口径，而是这条守卫。

### 3.2 第二步：若强行绑上账户（把成长组合绑到 A）

继承路径会把「未显式指定组合」的持仓一并吸入：

```python
pos_conds = [
    Position.portfolio_id == portfolio_id,                        # 显式
    and_(Position.portfolio_id.is_(None), Position.ledger_id.in_(ledger_ids)),  # 继承
]
```

⇒ 5 只固收+（`portfolio_id IS NULL`）被算进成长组合 ⇒ 两个组合都含全部持仓，**重复计数**。

### 3.3 第三步：算收益——口径完全不认 `portfolio_id`

`calculate_portfolio_xirr_by_id`（`calculators.py:381-450`）：

- 市值：`Position.ledger_id.in_(ledger_ids)` —— **按账户取，不认 portfolio_id**
- 现金流：`generate_portfolio_cashflows` 同样先取 `ledger_ids`，空则 `return []`
- 无账户 ⇒ `_empty_xirr_result()`，全 0（`calculators.py:145-158`）

⇒ 即便 3.1 的守卫修好，**组合 XIRR 仍会把该账户全部持仓算进去**，与组合持仓列表的口径**不一致**。

> **这是当前最实质的缺陷：持仓视图按 `portfolio_id`，收益视图按 `ledger_ids`，两套归属逻辑并存。**

### 3.4 第四步：策略间资金流动（用户的"共用+可转换"）

转换落库形态（`conversion_service.py:355-430`）：

| 腿 | `op_type` | 关键标记 | 新建/复用持仓 |
|---|---|---|---|
| OUT | `sell` | `link_group_id`、`import_hash=…#conv-out`、`extra.conversion.role='out'` | 复用原 `position_id` |
| IN | `buy` | `link_group_id`、`import_hash=…#conv-in`、`extra.conversion.role='in'` | **新建** position（`force_create_position=True`） |
| REFUND | — | `role='refund'` | 可选，仅退款额 >0 |

**两腿分属不同 `position`**，因此只要持仓归属正确，转换在**持仓维度天然就是"固收+流出、成长流入"**。

在策略级 XIRR 里会发生什么（若直接套用现有持仓口径）：

- 固收+：`sell` 被当作 **+回收**（像止盈了）→ 收益率虚高
- 成长：`buy` 被当作 **−新投入**（像外部加钱）→ 本金虚增、收益率被摊薄

⇒ 需要的是**在策略维度把同 `link_group_id` 的 sell/buy 配对识别为"策略间划转"并对冲**，
而不是新建事件表。**配对键已在库中，只差归因侧读取。**

### 3.5 残留问题：现金

`portfolio_service.py:84-88`：账户级资产按 `ledger_id` 归属，**现金不进持仓级组合**。
⇒ 即便持仓归类修好，"A 账户总资产 / 现金"在两个组合间的归属仍无解。
外部评估提出的这一点成立，且必须计入方案成本。

---

## 4. 成本分档（基于代码事实重估）

| 档 | 目标 | 必要改动 | 风险 |
|---|---|---|---|
| **A0 归类可见** | 成长基金显示在成长组合，不混入固收+ | ① `portfolio_service.py:59` 守卫改为「有显式持仓即可见」；② 继承路径增加「显式指派优先」的排他判定；③ 改派入口校验 | 低-中：影响所有组合视图的可见性语义 |
| **A1 归类 + 市值** | A0 + 组合市值/盈亏按 `portfolio_id` 汇总 | ④ `calculators.py` 市值过滤改按组合归属（与 `portfolio_service` 同源，抽公共函数） | 中：必须与持仓列表口径同源，否则出现第三个口径 |
| **B1 策略级收益（不含内部划转）** | 各组合市值变化 + 外部入金归属 | ⑤ 入金指定归属（`deposit` 加 `portfolio_id` 或按默认组合） | 中：历史入金需回填规则 |
| **B2 策略级 XIRR** | B1 + 策略间划转对冲 | ⑥ 归因侧消费 `link_group_id`：同组 sell/buy 判为策略间划转，策略 XIRR 中冲销；⑦ 转换阈值/跨策略判定规则 | 中：配对规则需覆盖「卖A买B」（非同组、非同日）等非转换场景 |
| **B3 资金池计息视角** | 策略间占用计息 | 口径设计 + 长期维护 | 高，**不建议** |

**关键修正**：外部评估把 B2 判为"中大 / 可能翻倍"，前提是"转换无流水需补录"。
事实是流水与配对键齐备，**B2 应降为「中」**——工作量集中在 ⑥ 的配对消费与策略维度容器，
不在数据补录。

**但 A0 是硬前置**：不做 A0，组合容器本身为空，B 档无从谈起。

---

## 5. 与 #1095（lot）的关系：本次不需要

| 场景 | 需要的能力 |
|---|---|
| 固收+基金归固收+、成长基金归成长（**不同持仓行**） | `positions.portfolio_id` 足够 |
| 同一只基金 60% 算固收+、40% 算成长（**同一持仓行内拆**） | 必须 `lots` / `lot_consumptions`（#1095） |

用户场景属前者。**lot 是"同一标的分批分属"的解，不是本次的必需项**；
本轮若引入 lot，属范围外扩张。

---

## 6. 待拍板

1. **口径**：策略间资金按「实际调拨记账」还是「市值加权分摊」？
   前者依赖配对识别（`link_group_id` 可覆盖转换，卖A买B需启发式），后者简单但策略评价会失真。
2. **容器**：策略级收益挂在 **Portfolio** 上，还是新建独立「策略账本」层？
   倾向 Portfolio——复用现有 XIRR 引擎与目标配比（`TargetAllocation`），避免第四套概念。
3. **现金**：账户现金按「默认组合归属」还是「市值占比分摊」？前者简单、后者更接近真实。
4. **范围**：先做 A0（可见性修复，低风险、能立刻消除"归类错误"的痛感），
   还是 A0+A1 一起（含市值口径统一）？
5. **历史数据**：既有转换的 IN 腿持仓当前继承的是账户默认组合（固收+），
   需要一次性改派脚本，还是由用户在 UI 逐步改？

---

## 7. 一句话总结

> 用户的痛感来自「归类错」，不是「批次拆不开」；实现归类不需要 lot，但**需要先拆掉
> `portfolio_service.py:59` 这道"组合必须绑账户"的守卫**。
> 而策略级年化的成本，因 `link_group_id` 已在库中，**比外部评估的判断低一档**——
> 不是"先补账再改造"，而是"补口径 + 消费存量配对键"。

---

## 8. 实施记录（A0 + A1，2026-10-29 已落地）

### 8.1 对外部评估的最终校正：`link_group_id` 与本场景无关

外部评估把「策略间资金调拨」当作 B2 的核心难点，前提是「一笔转换要拆成两个策略的内部划转」。
该前提在**持仓口径**下不成立：

- 用户在微众银行「卖固收+、买成长」是**两笔独立交易**，不是基金转换功能，没有 `link_group_id`；
- 即便走基金转换功能（同一 `link_group_id` 两腿），按持仓归因时 OUT 腿属固收+持仓、IN 腿属成长持仓，
  `sell` 天然是「回收」、`buy` 天然是「投入」，**两个组合各算各的，不需要配对**；
- 需要「配对」的是**账户口径**（判断 deposit/withdraw 是否为内部划转），而组合已不再是账户口径。

⇒ 「策略间划转对冲」是凭空需求，已从方案中删除。B2 实际只需改口径，不需要新事件表。

### 8.2 改动清单

| 文件 | 改动 |
|---|---|
| `services/portfolio_service.py` | 新增 `portfolio_ledger_ids` / `portfolio_position_conditions`（**归属唯一出口**）；`build_portfolio_holdings` 移除 `if not ledger_ids: return []`，无账户时跳过资产查询 |
| `services/performance/cashflow_layers.py` | `collect_flows` 增加 keyword-only `position_ids`，与 `ledger_ids` 二选一（持仓优先） |
| `services/performance/xirr_engine.py` | `generate_portfolio_cashflows` 改按持仓集合取流水；口径恒为持仓口径；删除逐账户 `basis_by_ledger` 分支与内部划转配对（组合已不消费 L1） |
| `services/performance/calculators.py` | `calculate_portfolio_xirr_by_id` 市值过滤改按组合持仓归属 |
| `tests/domains/test_d20_portfolio_phase2.py` | 新增 6 个用例（见 8.3） |
| `tests/services/performance/test_cashflow_layers.py` | 2 个旧账户口径用例改写为持仓口径（差异见各自 docstring） |
| `tests/services/performance/test_money_fund_income.py` | 同名账户防串味用例补持仓（原裸流水在新口径下不属于任何组合） |

### 8.3 验收

新增用例覆盖五个易回退点：

1. 无账户组合靠显式持仓可见（A0 核心）；
2. 同一账户两只持仓分属两个组合 → 各自现金流不串味（A1 核心）；
3. 无账户组合能算出年化（历史实现返回全 0）；
4. 账户入金不进组合现金流（D67 口径作废的直接体现）；
5. 已清仓持仓（`quantity == 0`）的历史流水仍计入（防"清仓即丢收益"）。

### 8.4 尚未解决

- **现金归属**：账户级资产仍按 `ledger_id` 进组合详情，组合 XIRR 却不含现金 ⇒ 总资产与收益率口径不一致。
  这是 §3.5 的残留，未在本轮处理。
- **前端改派入口**：持仓列表页无「所属组合」选择器，改派只能走 `PATCH /api/positions/{id}/`。
  A0/A1 只开后端能力；UI 入口按项目前端重构纪律需先出线框确认。
- **历史数据**：既有持仓的 `portfolio_id` 多为 NULL（继承账户默认组合），用户场景下需要一次改派。
