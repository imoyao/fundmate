# 持仓结构 + 穿透双图（2026-10-25，#2617 一期）

## 一、结论先行

#2617 卡面列了 5 个模块，**只有 2 个能用现有基座 + 现有数据做出来**，本期只交付这 2 个：

| 卡面模块 | 本期 | 依据 |
|---|---|---|
| 持仓结构（资产类别占比 / Top N / 集中度） | ✅ 新端点 `GET /api/summary/position-structure/` | `summary.distributions` 只有家庭级、无作用域、无 Top N/集中度，必须新建 |
| 穿透双图（直接持有 vs 穿透后） | ✅ `penetration` 出参加 `direct_view`，前端行业区加两档切换 | 穿透基座（#870/#1981/#2595）已备，缺的只是「基金整块不拆底层」这一档 |
| 风格分布 | ❌ 硬阻塞 | `fund_style_exposures` **0 行**；`funds.dominant_style` 26975 只**全 NULL**；`manager_style` 明确注释「成长/价值维度不实现」 |
| 组合级资金流动 | ❌ 数据几乎为空 | `transactions` 里 deposit 仅 51 笔 / 2 个账户，做不出时间序列 |
| 超额收益 | ✅ 已完成（#2135 已合入） | 不重复 |

风格分布与组合级资金流动**另开卡**，不塞进本 PR 假装完成。

## 二、真库实证（生产库 `D:/codes/fundmate/backend/invest.db`，2026-10-25）

### 2.1 持仓结构

```
family  total=540814.34  股票 26.40% / 基金 66.65% / 其他 6.95%
        top5_ratio_of_total=23.39   top5_of_stock=69.78   top5_of_fund=30.55
portfolio_id=1  total=400933.08   top5_ratio_of_total=29.77
```

### 2.2 一个必须钉死的发现：`security_industry_maps` **只有申万一级**

```
select scheme, count(*) from security_industry_maps group by scheme
→ [('sw1', 5220)]        # csrc 0 行、gics 0 行
```

直接后果：默认主口径 `csrc` 下**所有直持腿都没有「个股→行业」映射**，`direct_view.industries`
必然为空。这不是计算缺陷，是映射数据源缺口——但如果不显式说出成因，用户只会看到一张空图 + 一笔
「未映射」，然后合理地怀疑功能坏了。

两个口径的实测对照（同一份持仓、同一个作用域）：

| 口径 | mapped_cny | fund_cny | unmapped_cny | cash_equivalent_cny | 合计 |
|---|---|---|---|---|---|
| csrc（默认） | 0.00 (0.00%) | 337523.54 (62.41%) | 180361.88 (33.35%) | 22928.92 (4.24%) | **540814.34** |
| sw1 | 127102.00 (23.50%) | 337523.54 (62.41%) | 53259.88 (9.85%) | 22928.92 (4.24%) | **540814.34** |

两行都严格守恒到分。`sw1` 下能看到 8 个直持行业（房地产 6.54%、农林牧渔 5.52%、交通运输 3.47%…），
`csrc` 下一个都没有。

### 2.3 顺带修掉一处口径混淆：现金等价物不再算进「未映射」

改前 `unmapped_cny` = `direct_legs` 里 `reason is not None` 的全部，**含货基/逆回购**，
于是「未映射」= 真映射缺口 + 现金等价物，缺口被系统性放大（csrc 下 203290.80 / 37.59%）。

改后拆成 `unmapped_cny`（`industry_map_missing`，真缺口）+ `cash_equivalent_cny`（本质无股票敞口），
与 `unpenetrated[].reason` 的既有语义对齐（D45 早已规定这两类不可混为一谈，此处只是出参补齐）。

## 三、实现

### 3.1 持仓结构 `services/position_structure.py`

三条口径：

1. **作用域唯一出口** `services.scope.filter_positions_by_scope`（与归因 / 穿透同一条组合语义）。
2. **股基分列、不合并排名**：股票与基金的份额与价格不可比。`other`（债券/货基/逆回购）只出总额不参与 Top。
3. **按标的合并再排名**：同一 symbol 在多账户持有时先合并市值再排序——否则前 5 大持仓会被账户拆分挤掉，
   集中度被系统性低估；合并后保 `accounts` 计数便于下钻。

市值走唯一口径 `position_valuation.market_value_cents`（外币按 `EXCHANGE_RATES` 折 CNY），与仪表盘 / 穿透 / 归因同源。

### 3.2 穿透双图 `penetration.direct_view`

新增段（不改任何既有字段语义）：

| 字段 | 含义 |
|---|---|
| `industries[]` | 直持腿按行业聚合，**只含直持**，不含基金穿透 |
| `mapped_cny` / `mapped_ratio` | 命中映射的直持金额（= `industries` 各项之和） |
| `fund_cny` / `fund_ratio` | 基金整块，不拆底层 |
| `unmapped_cny` / `unmapped_ratio` | 真映射缺口，**不含现金等价物** |
| `cash_equivalent_cny` / `cash_equivalent_ratio` | 货基/逆回购，单列 |
| `mapping_available` | 当前口径有没有至少一条直持映射；`false` 时直持图必然空 |
| `unmapped_reason` | 缺口成因（`null` 表示无缺口），界面原样展示 |

守恒为硬口径：`Σindustries + fund_cny + unmapped_cny + cash_equivalent_cny == total_cny`，两口径实测均成立。

### 3.3 前端

- 行业分布区加「直接持有 / 穿透后」两档 SegmentedControl，默认**穿透后**（既有行为不变）。
- 直持视图在 `mapping_available === false` 时显示 `unmapped_reason`（后端文案原样透出，前端不改写）。
- `other_schemes` 区块补渲染 `direct_industries`（#1981 早已返回、此前未展示）——主口径无直持映射时，
  这是用户唯一能看到「直持压在哪些行业」的地方。做成标签流而非条形：它是「另一块敞口」，不是可与主口径比较的量级。
- 新面板 `PositionStructurePanel` 插入持仓分析页顶部。

## 四、测试

- `tests/services/test_position_structure.py` **10 项**（含 3 项接口契约：作用域互斥 400、top_n 越界夹取、空库降级）
- `tests/services/test_penetration_industry_map.py` **15 项**（+3：#2617 双图守恒 / 无映射降级给出 `unmapped_reason` / 现金等价物单列）
- 相关回归 `test_penetration.py` + `test_penetration_scope.py` 合计 **64 passed**
- `ruff check` + `ruff format --check` 全绿；`node scripts/check_css_vars.mjs` 无新增幽灵令牌；`pnpm typecheck` 通过

## 五、缺口与后续

1. **`security_industry_maps` 缺 csrc / gics 直持映射**（本卡最大遗留）。补源后 `csrc` 口径的直持图才会自然有内容，
   无需改代码。补源前**不要把 `sw1` 提为主口径**：基金侧 `fund_industry_allocs` 只有 csrc / gics 两套，
   `sw1` 下基金穿透为 0，提为主口径会让「已穿透率」掉到只剩直持，属另一种误导。
2. **风格分布**、**组合级资金流动**：数据未备，另开卡。
3. `position_structure` 的 Top N 目前只到标的层，未下钻到「同一基金经理/同公司」维度——等基金画像卡（#1970）落地后再评估。
