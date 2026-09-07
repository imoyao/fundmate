# 现金等价物分类与收益口径（单一事实文档，2026-09-07 锁定）

> 状态：**终局拍板，可落地**。本文是货币基金 / 逆回购「分类 + 收益口径」的**唯一实时文档**。
> 历史依据：#863（本金口径，已并入 §5 不变量）、#1137（账本绑定，分类正交见 §6）、#1354（大类收敛，当前分支）。
> 取代：`money-fund-caliber-reconcile-replan-2026-09-02.md`（replan 已落地、内容已并入，文件已删除）。

## 1. 核心矛盾与定位

两类用户心理账户相反：
- **理财 / 投资导向**：买货基是为了赚 ~3% 年化，希望看到收益贡献，倾向归「投资」。
- **现金 / 预算导向**：货基是「随时取用的钱」（余额宝），看现金流时要合并计算，倾向归「现金」。

结论：**不在底层做二选一分类**，采用「主分类归现金、子分类透视到投资」的混合模式。

## 2. 设计原则（锁死）

1. 默认归类 = 现金等价物 / 流动资产（流动性好、功能等同现金；会计上货币基金本就是现金等价物）。
2. 提供穿透视图与收益归属：无论归在哪，货基 / 逆回购收益在流水里标记为**投资收益 / 理财收益（INTEREST）**，不标记为普通收入。
3. 不试图用固定标签满足所有人，而是「主视图合并 + 次视图穿透 + 收益独立计算」。

## 3. 终局拍板（7 项）

### 3.1 开关粒度 = Per-asset（持仓级）
- `Position.count_as_investment`（Boolean, nullable）为覆盖项；null = 未覆盖，按规则推导。
- **不做**全局持久「一键纳入」开关（避免全局 vs 单笔优先级爆炸）。视图切换用 ephemeral context（见 §4）。

### 3.2 默认推导规则（未覆盖时）
- 货币基金（无到期日）→ 默认当现金（`count_as_investment = False`）。
- 逆回购 ≤ 1 天（隔夜）→ 默认当现金（明天回来的钱）。
- 逆回购 ≥ 7 天 → 默认算投资（锁住的）。
- 逆回购缺失 `maturity_date` → 默认算投资（保守兜底），但导入 / QuickEntry **强制补录期限**，正常路径不触发。

### 3.3 income_source 计算时派生（不落库）
- `INTEREST`（货币 / 逆回购 / 存款）、`DIVIDEND`（分红）、`CAPITAL_GAIN`（买卖价差）。
- 从 `asset_type + txn_type` 映射，集中一处，测试覆盖。

### 3.4 纳入投资的含义 = 独立桶，绝不混算 XIRR
- 货基 / 逆回购即使被纳入投资，也只参与资产配置饼图与总资产（TNA）聚合；算「股票 / 基金组合年化」时永远隔离在 INTEREST 桶，绝不与股基 CAPITAL_GAIN 混同一 XIRR 分母。

### 3.5 子类枚举 = investment 下新增 cash_management（现金管理类）
- 不复用 `fixed_income`（固收隐含到期还本付息期限匹配，语义不同）。

### 3.6 命名极性 = count_as_investment（True = 纳入投资）
- 摒弃 `is_cash_equivalent`（True 到底当现金还是投资易横跳）。

### 3.7 逆回购时间建模 = maturity_date 真相源
- `effective = override ?? (now < maturity_date ? True : False)`（未到期 → 算投资；已到期 → 自动变现金）。
- `count_as_investment` 仅作覆盖项；读时算，不建定时任务，V2 前不自动拆续作。

## 4. 展示层（小咪方案落地，不推翻数据模型）

- 资产总览提供「现金流视图 / 投资组合视角」切换：
  - **现金流视图**：总资产含货基 + 逆回购，看可用余额 / 规划支出。
  - **投资组合视角**：含现金等价物桶的资产配置饼图，复盘收益与配置比例；用户可勾选是否将现金等价物计入组合分析（即 ephemeral `include_cash_equivalent` 上下文）。
- 现金类卡片可展开明细：银行活期 / 货币基金 / 逆回购 / 合计（预算用户看总额，投资用户看结构）。
- 三大类（**展示分组，非新 DB 类别**）：现金等价物 / 投资资产 / 其他。现金等价物下设「纯现金」「准现金」标签（派生自 `asset_type`）。
- 月度收益报告：准现金收益单列（现金管理产生），不与股基混算综合收益率。
- 智能记账：买货基 → 现金等价物；赎回 → 现金等价物；货基分红 / 利息 → 投资收益。

## 5. 统一函数（唯一真相源）

```python
def effective_count_as_investment(position, as_of=None) -> bool:
    ov = position.count_as_investment
    if ov is not None:
        return ov
    if position.asset_type == 'money_fund':
        return False                      # 默认现金
    if position.asset_type == 'reverse_repo':
        md = position.maturity_date
        if md is None:
            return True                  # 兜底（正常路径不触发，导入已强制补录）
        return (as_of or now()) < md     # 未到期 → 投资
    return True                          # 其余资产本就是投资

def should_exclude_from_investment(position, as_of=None) -> bool:
    return not effective_count_as_investment(position, as_of)
```

- **两套排除机制正交，切勿混用**（关键，承接 §3.4 决策 #4）：
  - **分类 / 聚合层**（饼图分桶、TNA、类现金统计、portfolio views）：统一改调 `should_exclude_from_investment`（反向视图）／`effective_count_as_investment`，尊重 `count_as_investment` 覆盖项与逆回购到期动态判定。
  - **收益层（XIRR）**：`xirr_engine` / `calculators` **不调用**上述函数，改用 `EXCLUDED_ASSET_TYPES` 按 asset_type **硬隔离**货币基金 / 逆回购 / 现金，不受 `count_as_investment` 影响——货基即使被「纳入投资」也只进饼图与 TNA，永远隔离在 INTEREST 桶，绝不混入 CAPITAL_GAIN 分母。
- `CASH_EQUIVALENT_ASSET_TYPES` **保留**，仅用于现金等价物「识别」（`is_cash_equivalent_position` / `is_cash_equivalent_asset_type`，供分布 / 桑基图归桶），不参与排除决策；`EXCLUDED_ASSET_TYPES` 作为收益层硬隔离集继续使用。
- 所有消费点按上文分层统一，杜绝两层不一致。

## 6. 与账本绑定机制（#1137）正交

- `ledger.linked_cash_ledger_id`（现金账户绑定）、`linked_money_fund_id` + `auto_purchase_money_fund`（类现金绑定 + 自动申购）管「钱流向哪」；`count_as_investment` 管「这笔算现金还是投资」。两者正交。
- 自动申购生成的货基流水本就 `money_fund` 类型 → 默认现金等价，天然一致。

## 7. 场内货基识别缺口（必纳入范围）

- 银河证券等导入的场内货基（华宝添益 511990、银华日利 511880）须确保识别为 `money_fund`（或 `is_money_fund=True`），否则本设计对其无效、仍与股票混算。
- 判定优先级（见 `services/fund_utils.py`）：`asset_type` 显式 > market 域名录货币型 > 代码段兜底（511 等场内货币 ETF 无稳定前缀，**必须依赖名录**，禁止 51 前缀误伤普通 ETF/LOF）。名录缺失须**告警**而非静默归 `fund`。

## 8. 不变量与测试

- **TNA 不变量**：开关切换前后总资产不变，仅改变饼图色块与「投资本金」口径。集成测试断言前后总额一致。
- **默认态回归**：所有覆盖项为空 + 全局默认排除时，计算结果与当前 `EXCLUDED_ASSET_TYPES` 一致（锁定无破坏性）。
- **期限推导**：逆回购缺失期限 → 投资（兜底）；设 `maturity_date` 7 天 → 投资、1 天 → 现金。
- **分账户 / 策略硬排除**：分账户 / 分策略查询下，无论覆盖项如何，货基 / 逆回购不进入年化分子。

## 9. 落地清单（代码改造，下一阶段）

1. `Position` 加 `count_as_investment`（Boolean, nullable）+ `maturity_date`（Date, nullable，仅逆回购）。
2. 写 `effective_count_as_investment` / `should_exclude_from_investment`，**分类 / 聚合层**消费点（饼图分桶、TNA、类现金统计、portfolio views）统一改调；**收益层（XIRR）的 `EXCLUDED_ASSET_TYPES` 硬隔离保留、不替换**（承接 §3.4 决策 #4：货基 / 逆回购无论 `count_as_investment` 如何都隔离在 INTEREST 桶，绝不混入 CAPITAL_GAIN 分母）。`CASH_EQUIVALENT_ASSET_TYPES` **保留**，仅用于现金等价物「识别」（`is_cash_equivalent_position` / `is_cash_equivalent_asset_type`，供分布 / 桑基图归桶），不删除。
3. 重构饼图分桶改调统一函数。
4. XIRR 引擎按 `INTEREST` 标签隔离货基 / 逆回购收益；分账户 / 分策略视角强制排除。
5. 测试：TNA 不变量 + 默认行为 + 期限推导 + 分账户硬排除。
6. **前置核实**：① 逆回购落点（Position vs Asset 表）——决定字段加在哪；② QuickEntry 逆回购期限必填。

## 10. 关联

- issue：#863（本金口径，已并入本文 §5/§8）、#1137（账本绑定 spec，见 `ledger-cash-like-product-binding-2026-08-29.md`）、#1354（大类收敛，当前分支）。
- `docs/spec/decisions.md` 2026-09-07 决策行已登记。
