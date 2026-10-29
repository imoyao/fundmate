# 持仓结构视角：由账户类型决定，不由用户切换

> 状态：**已实现**（2026-10-29 owner 裁定后落地）。
> 关联卡：#2739（账户详情页内嵌持仓结构，本口径变更随其落地）；#2617（持仓结构面板原始实现）；#870 / #2595（持仓穿透）。
> 前置事实：`docs/spec/account-detail-depth-analysis.md`（账户详情页补齐两块分析的依据）。

---

## 1. 结论先行

账户是**基金账户还是股票账户**，由 `ledgers.ledger_type` 确定（owner 裁定）。
既然账户类型是确定的，持仓结构里的「股票 / 基金」双视角切换对账户级**没有价值**：

| 作用域 | 视角 | 切换控件 |
|---|---|---|
| 证券账户（`ledger_type=stock`） | 固定**股票** | **不提供** |
| 基金账户（`fund`） | 固定**基金** | **不提供** |
| 银行账户（`bank`） | 固定**基金**（除现金外按基金视角处理） | **不提供** |
| 基金 E 账户（`e_account`） | 固定**基金** | **不提供** |
| 组合级 / 家庭级 | 股 / 基双视角 | **保留** |

组合/家庭级保留切换的理由：一个组合可同时含股票账户与基金账户的持仓
（实测组合「嘲风仰望星空」含 28 只基金持仓），家庭级更是全类型混合，
此时切换才有意义。**把账户级的固定视角套到组合/家庭级会误伤已上线的组合页。**

---

## 2. 用哪个字段（易错点）

账户类型有**两个**字段，职责正交，选错会踩坑：

| 字段 | 含义 | 铁律（`docs/working-notes/ledger-channel-category-redesign-2026-08-28.md` §2.2/§2.3） |
|---|---|---|
| `ledger_type` | 内部**资产类计算口径键**（stock/fund/bank/property/e_account/family） | 「只进计算/费率/**视图分支逻辑**，绝不出现在用户面、绝不当展示标签」 |
| `channel_category` | 用户可见**渠道分组**（bank/securities/fund_platform/insurance/futures/other） | 「分组/标签/排序/筛选只读它，**绝不读 ledger_type 当展示**」 |

**本需求用 `ledger_type`**：它就是「视图分支逻辑」的承载字段，正是本场景的用途。
`channel_category` 是渠道维度、只用于展示分组。

### 2.1 实测数据（本地 `invest.db` 只读探针，2026-10-29）

```
ledger_type 分布：fund 8 / bank 4 / stock 1 / property 1 / e_account 1
channel_category 分布：fund_platform 8 / bank 4 / securities 1 / other 1 / NULL 1
交叉一致性：15 个账户中仅「住房信息记录」不一致（property 账户走 other 渠道→派生 bank）
```

派生关系与 `constants.CHANNEL_CATEGORY_TO_LEDGER_TYPE` 一致，两字段无历史错写残留
（`AssetTypeBadge` 注释提到的「微众银行被导入写成 fund」问题已不复存在）。

---

## 3. 关键事实：账户的持仓不是单一类别

「按账户类型固定视角」若照字面实现，会**藏掉数据**。实测各账户类型的持仓构成：

```
证券账户「同花顺（银河证券）」：stock 11 只 / bond 8 只 / etf 7 只 / fund 2 只
  市值权重：stock 50.4% · etf 21.2% · fund 15.1% · bond 13.3%
基金账户 ×8：全 fund（其中 11 只货基）
银行账户 ×3：全 fund（24 只）
```

若证券账户「只显示股票」，会藏掉 **49.6%** 的持仓。所以口径必须细化到**每类资产怎么归**。

### 3.1 ETF 归权益侧（owner 裁定）

证券账户里的 ETF 归**权益侧，与股票同榜**。

- 理由：ETF 是**场内**交易品种，与股票同为按市价计价，合并排名**不违反**
  「股基不合并排名」那条硬约束（那条约束针对的是场外基金的净值口径）；
- 不这么做会藏掉证券账户 **21.2%** 的市值（实测 7 只行业 ETF：恒生科技 / 创新药 /
  卫星E / 科技HK / 创新药E / 证券ETF / 养殖ETF），对证券账户是重大信息损失。

⚠️ 该改写**只在账户级生效**。组合/家庭级维持原分类（`etf → fund`），避免误伤组合页。

### 3.2 货基走类现金（owner 裁定）

货币基金在基金/银行账户里按**类现金**处理，排除出持仓榜。

- 货本是现金等价物（`services.fund_utils.is_cash_equivalent_position` 是唯一判定入口），
  不是「持仓」；
- 纳入持仓榜会稀释集中度（货基几乎零波动）并让「前 5 大持仓」失真；
- 实测货基仅占家庭总市值 **2.9%**，排除出榜不损失结构信息。

⚠️ 同样**只在账户级生效**：组合/家庭级维持原口径（货基照旧进基金桶、参与 Top）。

### 3.3 排除后必须把「钱去哪了」说清楚

账户级排除货基后，三类占比之和 = **持仓总额**（不含类现金），不等于账户总资产。
面板必须显式说明「另有类现金 ¥X 未计入」，否则用户会以为数据丢了
（前端 `PositionStructurePanel` 的 `hasCashLike` 脚注）。

---

## 4. 实现

### 4.1 后端 `backend/app/services/position_structure.py`

- 新增 `_LEDGER_TYPE_VIEW`：`stock→stock`、`fund/bank/e_account→fund`。
  `property` / `family` 不在表内（不持有可排名的持仓）⇒ 返回 `None`（无固定视角）。
- `_resolve_ledger_view()`：按 `ledger_id` 取该账户的 `ledger_type` → 视角。
- 分类改写（仅账户级）：
  - ETF 在股票视角下归 `stock`；
  - 现金等价物（`is_cash_equivalent_position`）排除出持仓榜，市值计入 `cash_like_cny`。
- 响应新增：`view`（`stock`/`fund`/`null`）、`ledger_type`、`cash_like_cny`。
  `position_count` 改为与 `total_cny` 同口径（不含走类现金的持仓）。
- `notes` 首条按视角插入口径说明（用户据此判断数字含义）。

### 4.2 前端 `frontend/src/components/PositionStructurePanel/index.vue`

- `fixedView = data.view`（**不在前端另算一套**）；
- `showSwitcher = fixedView === null` ⇒ 只有组合/家庭级渲染 `SegmentedControl`；
- 主榜取 `groups[fixedView ?? activeClass]`（账户级下不取用户上次选的那个）；
- 口径说明写明「视角已按账户类型固定」。

### 4.3 顺带修正的口径文案

面板原先把占比分母写死为「占组合」，但它现在也用在**账户页**（#2739 落地后）。
改为随作用域走：`占账户` / `占组合` / `占全家庭`。

---

## 5. 验收与回归网

- **后端**：`backend/tests/services/test_position_structure.py` 新增 9 例
  （视角映射、ETF 归权益、货基走类现金、组合级维持现状、占比守恒、口径说明）；
  既有 11 例全部未改动即通过。
- **前端**：`frontend/src/components/PositionStructurePanel/__tests__/positionStructureViewGuard.spec.ts`
  5 例（切换控件的出现条件、固定视角取自后端、主榜取值、组合级保留切换、口径说明）。
- **反向验证**（各 4 个变异，全部转红后复原全绿）：
  - 后端：ETF 不归权益侧 / 账户级不排除货基 / 视角恒 None / 银行账户不走基金视角；
  - 前端：切换控件恒显示 / `showSwitcher` 恒 false / 主榜取用户上次选的 / 前端自己猜视角。

> ⚠️ 前端守卫首版有一处**假绿**：`showSwitcher` 写成恒 false 时，「组合级保留切换」
> 那条只断言了字面量 `fixedView.value === null` 存在，仍通过。已改为断言该字样
> **出现在 `showSwitcher` 的定义里**，重测确认两条同时转红。

---

## 6. 明确不做

- 不给聚合页加 `?scope=ledger&id=` 深链（#2739 已裁定）。
- 不改组合/家庭级的任何既有分类与口径（避免误伤已上线的组合页与持仓分析页）。
- 不把 `ledger_type` 用作展示标签（铁律：它是内部计算口径键，用户不可见）。
