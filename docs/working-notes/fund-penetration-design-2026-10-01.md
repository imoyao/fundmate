# 基金持仓穿透服务 设计与实施（2026-10-01，#870 Step 2 / PR B1）

> 前置：Step 1（基准指数日线扩容）已完成，见 `./index-daily-tencent-source-2026-10-01.md`（PR #1825）。
> 本文覆盖 Step 2：把已有的 `fund_industry_allocs` / `fund_holdings` 变成**用户组合的真实行业/个股暴露**。
> 状态：**B1（服务 + API + 测试）已实施**，本文记录最终口径与实施中修正的四处认知。

---

## 一、结论先行

1. **数据底座早已齐备、读侧为零。** `fund_industry_allocs`（830 行 / 101 基金）与 `fund_holdings`（6423 行 / 100 基金）此前只被 `FundPositionSyncJob` **写**，全仓无任何读侧（`services/penetration.py` 不存在）。本卡补的就是这个读侧。
2. **穿透覆盖率实测 46.5%（全组合）/ 77.2%（基金维度），有硬上限。** 剔除本机库里的演示数据后实测：基金占组合 60.2%、直持 35.9%、现金等价 3.9%。直持股票/可转债无「个股→行业」映射、场内 ETF 无底层持仓数据，这两块合计 **49.2%** 的市值天然穿不透。**输出必须显式分「已穿透 / 未穿透」并逐条给 reason**，绝不能假装 100%。
3. **csrc 作 v1 唯一主聚合口径。** 实测「只有 gics 没有 csrc」的基金仅 2 只 / 市值 26 元，csrc 的遗漏可忽略。
4. **gics 不是「平行分类体系」，而是「港股那一块敞口」。** 见 §2.3 陷阱一 —— 这是本轮最重要的认知修正，直接改变了出参设计。
5. 本轮只做**后端服务 + API + 测试**；前端看板拆为 B2。

---

## 二、现状实证

### 2.1 数据底座（生产库 `D:/codes/fundmate/backend/invest.db`，2026-10-01）

| 表 | 行数 | 基金数 | 最新报告期 | scheme / basis 分布 |
|---|---|---|---|---|
| `fund_industry_allocs` | 830 | 101 | 2026Q2 | `csrc` 654 行 / 99 基金；`gics` 176 行 / 44 基金 |
| `fund_holdings` | 6423 | 100 | 2026Q2 | `full` 6419 行 / 100 基金；`top10` 4 行 / 1 基金 |

报告期分布：2026Q2 → 99 只、2026Q1 → 1 只、2025Q4 → 1 只。**各基金报告期不一致**（新建仓基金天然滞后），必须逐基金取自身最新期。

### 2.2 组合形态与实测穿透结果

生产库组合（`ownership_status='active'`，154 条持仓，`valuation_mode` 全为 `nav`）：

| asset_type | 市值占比 |
|---|---|
| fund（含场内 ETF） | 60.2% |
| stock（直持） | 27.6% |
| etf（场内） | 7.7% |
| bond（可转债） | 4.5% |

**服务实跑结果**（`build_penetration`，已剔除演示数据，见 §2.4）：

```
total            584,141.15
  penetrated     271,721.70  (46.5%)      ← 基金维度穿透率 77.2%
  unpenetrated   312,419.45
    基金合计      351,774.60
    直持合计      209,437.63
    现金等价       22,928.92
行业合计 192,333.92 + 未分配 79,387.78 = 271,721.70 ✓
```

行业 TOP：制造业 153,158（26.2%）> 金融业 10,160 > 信息传输/软件 7,707 > 科学研究和技术服务 5,556 > 采矿业 4,771。
个股 TOP：贵州茅台 6,697 > 中际旭创 6,038 > 新易盛 5,861 > 五粮液 5,618 > 泸州老窖 4,399。

未穿透四类（按金额）：

| reason | 条数 | 金额 | 性质 |
|---|---|---|---|
| `industry_map_missing` | 20 | 209,437.63 | 真缺口（直持股票/可转债无行业映射） |
| `etf_holding_missing` | 8 | 77,968.30 | 真缺口（场内 ETF 无底层持仓） |
| `cash_equivalent` | 11 | 22,928.92 | **非缺口**（货基/逆回购，本质无股票敞口） |
| `fund_alloc_missing` | 5 | 2,084.60 | 真缺口（基金无行业配置记录） |

> 场外基金 114 只中 **109 只有行业配置**，缺失仅 5 只 —— 覆盖率远超预期，`fund_alloc_missing` 金额极小。

### 2.3 四个必须钉死的口径陷阱

**陷阱一（最重要）：gics 不是「平行分类体系」，而是「港股那一块敞口」。**

原先的假设是「csrc / gics 是两套平行的分类体系，同一只基金在两套下各有一套完整分布」。实测**证伪**：

- 44 只基金有 gics 行，参与基金市值 182,220.93（占基金 42.3%）；
- 但 gics 行业合计只有 **17,314.32，仅占参与市值的 9.5%**（residual 90.5%）。
- 对照同一批基金的 csrc：合计普遍在 85%~95%。

⇒ GICS 在东财数据里只标注基金持仓中的**港股部分**，A 股部分全走证监会门类。**把 gics 当独立口径算「穿透率」，会得出「港股只占 0.5%」这种完全错误的结论。**

**出参应对**：非主口径仍单列，但必须自带 `covered_cny` / `covered_ratio_of_fund` / `industry_total_cny` / `industry_ratio_of_covered` / `note`，把「这不是完整口径」写在数据里而不是只写在注释里。

**陷阱二：csrc / gics 禁止跨体系相加。**

GICS 的「非必需消费品」在证监会门类里被并进「制造业」，跨体系求和会得出「制造业与非必需消费品同级并列」的荒谬结论。聚合必须按 scheme 分区。

**陷阱三：同码多名 —— 但它只可能出现在不同基金之间。**

实测同一 `industry_code` 在不同基金下名称不一致：`45` = 信息技术 / 科技；`25` = 非必需消费品 / 非日常生活消费品；`50` = 通讯 / 电信服务 / 通信服务。聚合键必须是 `industry_code`，名称取先出现者。

**实施中修正的一处认知**：初版测试按「同一基金同报告期两行同 code」构造，被唯一约束拦下 —— 表上唯一键是 `(fund_code, report_period, industry_code)`，**不含 scheme**，同一基金同一期不可能有两行同 code。名称分歧只发生在**跨基金聚合**时。测试已按真实形态重写。

> 遗留观察（不在本 PR 修）：唯一键不含 `scheme` 在语义上不严谨 —— 按「禁止跨体系相加」的原则，唯一键理应含分类体系维度。当前 csrc 是单字母、gics 是两位数字，值域天然不交，故无实际冲突；改约束需重建表（SQLite），成本大于收益，留档待后续。

**陷阱四：ratio 合计不是 100%，且「差额」不是误差。**

实测 99 只 csrc 基金的 ratio 合计分布：

| 区间 | 基金数 |
|---|---|
| 90~100% | 34 |
| 70~90% | 32 |
| 40~70% | 20 |
| <40% | 13 |

低合计的全是**债基 / 指数联接基金**（如易方达岁丰添利债券 0.77%、景顺长城景颐裕利债券C 6.41%、易方达中证红利ETF联接发起式C 0.48%）—— 它们的资产主体是**债券或 ETF 份额，不是股票**，行业配置字段自然很低。

⇒ **禁止归一化到 100%**（会把 86% 仓位的基金拉成满仓，抹掉真实的现金垫差异）。差额单列为 `industry_non_equity_cny`。

> **命名修正**：初版字段名 `industry_residual_cny`（残余）有误导性 —— 会让人以为是「数据缺失」。实际上它是**该基金的债券 / 现金 / 其他资产**，是真实资产构成。已改名 `industry_non_equity_cny` 并在 notes 中写明「不是缺失数据」。
>
> 归因实测：未分配 128,586 元（未剔除演示数据时）中，72% 来自 ratio 合计 <40% 的基金，主体是债基的债券部分。

### 2.4 数据卫生发现：生产库混入演示数据（不在本 PR 处理）

本机库里存在 3 只命名带「示例」的基金，代码 `012345` / `023456` / `034567`（键盘序，明显是演示/种子数据），合计约 **14.2 万元**：

| 代码 | 名称 | 市值 | 问题 |
|---|---|---|---|
| `023456` | 示例现金添利**货币市场基金** | 100,895 | `asset_type='fund'`（非 `money_fund`）、`is_money_fund=0`；**却被穿透出「制造业 10.61%」** |
| `012345` | 示例红利优选混合A | 20,978 | 行业合计 46.4%（伪造） |
| `034567` | 示例行业精选指数C | 19,752 | 无行业数据 |

三只基金在 `funds` 表里**都没有记录**，但 `fund_industry_allocs` 里有行业行，且行业名格式异常 —— 正常数据是 `('45', '信息技术')`，它们是 `('45', '45信息技术')`（名称前缀带 code）。⇒ 这些行是直接插入的演示数据，没走同步流程。

**影响**：`023456` 被当作普通基金穿透，虚增制造业约 10,705 元、虚增「已穿透」约 10 万元。**这不是服务的缺陷**（服务按数据的 `asset_type`/`is_money_fund` 忠实分类，与既有口径一致），是数据卫生问题。

**建议**：单独开卡清洗 —— 演示数据不应留在生产库；同时 `023456` 暴露了 `is_money_fund` 回填（#863）的一处遗漏（名字是货基但标记为 False）。本 PR 不动数据。

### 2.5 一处口径选择：不传净值，与仪表盘对齐

市值统一走 `position_valuation.market_value_cents`，且**不传 `effective_nav_yuan`** —— 与 `summary_service.get_summary_data` 完全一致（都用 `positions.current_price` 快照价）。

理由：① 传净值需调 `NavService`，会引入远程请求副作用（穿透是纯读服务）；② 两条路径口径分叉会让「穿透总额」与「仪表盘总额」对不上，用户立刻会发现。

---

## 三、服务实现

### 3.1 落点

`backend/app/services/penetration.py`（新建，**services 顶层**）。

依据 `architecture.md` §6「跨家族共享件一律放 `services/` 顶层」：本模块不属 sync / bias / thermometer 任何家族，是独立组合分析服务。持仓加载复用 `summary_service._load_user_assets`（同过滤口径：只取 `active`，排除 E 账户影子记录）。

### 3.2 处理流程

```
1. 遍历持仓 → 逐条算市值（cents，唯一口径）
     现金等价物（货基/逆回购） → 未穿透，reason='cash_equivalent'
     fund / etf                → 尝试穿透
     其余（股票/可转债）        → 未穿透，reason='industry_map_missing'
2. 行业层：逐基金取自身最新 report_period 的行业行，过滤 ratio<=0
     市值 × ratio/100 → 按 industry_code 归并
     ratio 合计不足 100% 的差额 → industry_non_equity_cny
3. 其它 scheme 单列（带覆盖度与 note，禁止并入主口径）
4. 个股层：逐基金取自身最新报告期，同期内优先 full；带 holding_basis 打标
5. 分层汇总，三层守恒（已穿透 + 未穿透 == 总市值）
```

### 3.3 出参结构

```jsonc
{
  "as_of": "2026-10-01",
  "scheme": "csrc", "scheme_label": "证监会门类",
  "total_value_cny": 584141.15,
  "coverage": {
    "penetrated_cny": 271721.70,          // 成功穿透的**基金市值**（非行业分摊额）
    "unpenetrated_cny": 312419.45,
    "penetrated_ratio": 0.465,
    "fund_cny": 351774.60, "direct_cny": 209437.63,
    "cash_equivalent_cny": 22928.92, "unpenetrated_fund_cny": 80052.90
  },
  "industries": [
    { "code": "C", "name": "制造业", "value_cny": 153158.25,
      "ratio_of_total": 0.2622, "ratio_of_penetrated": 0.5637, "fund_count": 95 }
  ],
  "industry_non_equity_cny": 79387.78,    // 债券/现金/其他，非缺失
  "other_schemes": {
    "gics": {
      "label": "GICS 板块",
      "covered_cny": 182220.93, "covered_ratio_of_fund": 0.423,
      "industry_total_cny": 17314.32, "industry_ratio_of_covered": 0.095,
      "note": "GICS 板块 仅覆盖基金持仓的一部分（实测 GICS 只标注港股）…",
      "industries": [ /* … */ ]
    }
  },
  "stocks": [ { "code": "600519", "name": "贵州茅台", "value_cny": 6696.76,
                "ratio_of_total": 0.0115, "holder_fund_count": 13 } ],
  "stocks_coverage": {
    "covered_cny": 271721.70,
    "fund_count_by_basis": { "full": 106, "top10": 1 },
    "report_period_by_basis": { "full": "2026Q2", "top10": "2026Q1" }
  },
  "unpenetrated": [ { "symbol": "SZ159857", "name": "光伏ETF", "asset_type": "etf",
                      "value_cny": 13220.0, "ratio_of_total": 0.0226,
                      "reason": "etf_holding_missing",
                      "reason_label": "场内 ETF 无底层持仓数据（真缺口，待采集）" } ],
  "report_periods": { "2026Q1": 1, "2026Q2": 94 },   // 按**基金**去重，不是按持仓条数
  "notes": [ /* 口径提醒，见下 */ ]
}
```

**双 ratio 必须都给**：`ratio_of_total`（主口径，「我的钱有多少在这个行业」，含未穿透作分母）与 `ratio_of_penetrated`（已穿透部分内部的行业结构）。只看前者会把「未穿透 53%」误读为行业分散；只看后者会高估覆盖度。

`report_periods` 与 `notes` 是**口径透明化字段**：前者暴露报告期不一致（96 只 2026Q2 + 1 只 2026Q1），后者把「未分配不是缺失」「gics 不是完整口径」「季报个股只有前十大」写在响应里。

### 3.4 reason 枚举（前端禁止自由字符串）

| reason | 含义 | 是否缺口 |
|---|---|---|
| `cash_equivalent` | 货基/逆回购，本质无股票敞口 | **否** |
| `industry_map_missing` | 直持股票/可转债无「个股→行业」映射 | 是 |
| `etf_holding_missing` | 场内 ETF 无底层持仓数据 | 是 |
| `fund_alloc_missing` | 基金无行业配置记录 | 是 |

每条未穿透都带 `reason_label`（中文），前端不得自己拼文案。

---

## 四、API

`GET /api/summary/penetration/?scheme=csrc&top_n=20`（挂在 `domains/summary/views.py`，与 `sankey` / `distributions` 同级，信封 `{data, message}`）。

- `scheme` 非法 → 400 + `error_code=1001`（不落 500）。
- `top_n` 非整数 → 400 + 明确提示；`<=0` 表示不截断；超出部分合并为 `__other__` 一条，金额不丢。
- 鉴权走既有 `get_family_id()`。

---

## 五、测试

`backend/tests/services/test_penetration.py`，**19 项**，全绿（`pytest -p no:xdist`）。

| # | 用例 | 钉住的口径 |
|---|---|---|
| 1 | `test_schemes_are_not_aggregated_across_systems` | 跨体系隔离 |
| 2 | `test_gics_only_fund_contributes_only_to_other_schemes` | 只有 gics 的基金归未穿透但 gics 侧可见 |
| 3 | `test_same_industry_code_with_multiple_names_is_merged` | 跨基金同码多名归并 |
| 4 | `test_ratio_is_not_normalized_to_hundred` | 不归一化 + 非股票差额单列 |
| 5 | `test_latest_period_is_resolved_per_fund` | 逐基金最新报告期 |
| 6 | `test_layers_conserve_total_value` | 三层守恒 |
| 7 | `test_unpenetrated_reasons_distinguish_gap_from_no_exposure` | 四类 reason 区分 |
| 8 | `test_etf_with_holding_data_is_not_a_gap` | ETF 补数据后自动生效（B3 前置断言） |
| 9 | `test_stock_layer_prefers_full_basis_within_same_period` | 个股同期优先 full |
| 10 | `test_stock_layer_falls_back_to_top10_and_tags_it` | top10 降级打标 |
| 11 | `test_stock_top_n_truncation_keeps_residual_bucket` | 截断不丢金额 |
| 12 | `test_empty_portfolio_degrades_without_error` | 空库降级 |
| 13 | `test_fund_with_zero_total_ratio_is_treated_as_unpenetrated` | ratio≤0 脏数据守卫 |
| 14 | `test_other_scheme_declares_partial_coverage` | 非主口径带覆盖度与 note |
| 15 | `test_report_periods_count_distinct_funds_not_positions` | 报告期按基金去重 |
| 16~19 | API 四例 | 端点注册 / 参数生效 / 非法 scheme / 非法 topN |

> 测试落点是 `tests/services/` 而非 issue 正文建议的 `tests/domains/` —— 服务在 `services/`，测试跟服务走。

---

## 六、缺口与后续

| 缺口 | 金额（实测） | 后续 |
|---|---|---|
| 直持股票/可转债无行业映射 | 209,437.63（35.9%） | 需「个股→行业」映射源；东财源已实证会限流（#1431），申万映射需另找通道 |
| 场内 ETF 无底层持仓 | 77,968.30（13.3%） | 补 ETF 持仓采集；服务已按同一路径处理，补数据后自动生效 |
| 债基的债券部分 | 79,387.78（未分配） | **不是缺口**，是真实资产构成 |
| 货基/逆回购 | 22,928.92 | **不是缺口**，本质无股票敞口 |
| 演示数据污染 | 约 142,000 | 单独开卡清洗（§2.4） |
| 唯一键不含 scheme | — | 留档，无实际冲突，改则需重建表 |

---

## 七、PR 拆分与交付

| PR | 内容 | 状态 |
|---|---|---|
| **B1** | `services/penetration.py` + `GET /api/summary/penetration` + 19 测试 + 决策 D45 | **本轮完成** |
| B2 | 前端穿透看板（`frontend/src/views/asset/`）；须先查 `docs/design/components.md` 复用组件，禁止自写分段控制器（#1717） | 待做 |
| B3 | 覆盖率补强：个股→行业映射源、ETF 持仓采集 | 待做（先决条件：找到不限流的映射源） |

**B1 产物**：新增 3 个文件 + 1 处 import 改动，**零 schema 变更、零数据迁移、零存量数据改动**，回滚 = revert 单个 PR。

**对外契约**：新增 1 个 GET 端点。`docs/spec/pricing-tier.md` 已将「持仓穿透」定为**免费不限次**，本端点无需计费钩子。

**验证**：`scripts/guard_layer_direction.py` R1~R6 全绿（266 文件）；`ruff check` / `ruff format --check` 全绿；相关测试 66 项通过（穿透 19 + summary 47）。
