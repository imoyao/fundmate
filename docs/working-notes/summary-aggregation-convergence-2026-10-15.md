# 总资产聚合收敛（D59 收尾，2026-10-15）

> 源：CNB #478 / GitHub #2154（D59）。本条记录的是 D59 合并时**自己记下、当时划出范围**的那一处。

## 1. 缺口是什么

D59 把「总资产」收敛到 `family_totals` 一个出口，验收三项达成。但那一轮的正文里留了一句边界：

> `get_ledger_distributions`（账户级快照）与 `LedgerService.get_overview_stats` 是**账户级**聚合，
> 各有独立契约与调用方，本次**不动**。

划出范围本身是对的（账户级、归哨兵键 0、有独立契约），**但它就是 D59 要杀的那个形态本身**：

```python
# get_ledger_distributions（#1181）—— 与 family_totals 逐字重写了一遍
for p in positions:
    _bucket(p.ledger_id)['total_assets'] += Money.cents_to_yuan(market_value_cents(p, rate=rate))
for a in assets:
    amount = Money.cents_to_yuan(a.amount)
    if amount <= 0: continue
    if a.major_category == _LIABILITY_KEY: bucket['total_liabilities'] += amount
    else: bucket['total_assets'] += amount
for _lid in set(orphan_map) | set(income_map):
    _bucket(_lid or 0)['total_assets'] += ...
```

一模一样：持仓走唯一市值口径、排除非正数资产、负债单独归桶、孤儿流水并入。
**口径一旦再变，这里就是「下次漏改的那一处」**——正是 `#1174` 收口时
`get_account_groups` / `get_sankey_data` 漏掉的同一个模式。

更值得记的是**它的保护网在哪**：不在 D59 新织的那张契约网里，
只靠 `test_account_snapshots.py:186` 一条既有的「账户级合计 == 家庭级」断言兜着——
**埋在别的文件、靠人找**。人找得到的前提是人知道要找。

## 2. 修法：把「同一份逻辑」变成「同一个函数」

新增 `_per_ledger_buckets(db, family_id, positions=None, assets=None, orphan=None)` 作为**唯一累加实现**：

| 出口 | 关系 |
|---|---|
| `_per_ledger_buckets` | 唯一累加（按 `ledger_id` 归桶，无归属归哨兵键 0） |
| `get_ledger_distributions` | 直接返回它的桶 |
| `family_totals` | **把各账户桶按位相加** |

关键在最后一行：**「Σ账户桶 ≡ 家庭桶」从「两边各自算对」变成了构造出来的恒等式**。
这不是风格问题，是失效模式的差别——各自算对时，口径变了要记得改两处；
相加时，只有一处可改。

对外行为零变化，既有用例（106 条）全绿。

## 3. 契约测试补进同一张网

`test_summary_total_assets_contract.py` 新增 `TestLedgerLevelSharesTheSameAggregation` 5 条（11 → 16），
判据刻意选**逐桶按位相加必须等于家庭桶**，而不是「总数相等」：

> 总数相等可以靠碰巧抵消（一处多算、另一处少算）；按位相等要求两个方向的错同向。

覆盖：balance 持仓归对账户 / 孤儿流水落哨兵键 0 / 混合场景（含负债——负债若在一侧算进
`total_assets`，按位比较立刻暴露）/ shadow 不造出假账户桶 / 空家庭返回空字典。

## 4. 机械化：`guard_summary_aggregation.py`

在 `summary_service.py` 里出现 `total_assets` / `total_liabilities` / `net_worth` 的
`+=`（或 `x = x + y`）即报红；白名单只有唯一实现与 `family_totals` 本身。
并入 `ci.yml` 的 backend job（不新增 job 就不必改 `gate.needs`）。

### 4.1 首版判据的失败：4 处全是误报

初版还写了第二判据「加载了 `_load_user_assets` 却不委托唯一实现」。上线即报 4 处：

```
get_account_groups()   按账户名分组
get_position_groups()  出 items 明细
family_pnl_cents()     算盈亏
get_ledger_pnl()       算账户盈亏
```

**四处全是正常函数**——它们与唯一实现碰的是同一批数据，但累加的不是同一个桶。

⇒ 判据「函数碰了什么数据」拦不住分叉：**碰同一批数据是常态，累加同一个桶才是信号**。已删除该判据。
代价是形态怪异的写法（用 `sum(...)` 或局部变量绕开）会漏判——但那种写法一眼看得出来，
且它绕开的是**守卫**不是**契约网**（数值仍被 `TestTotalAssetsSingleExit` 咬住）。
**宁可漏判，不可把正常函数全判红**：恒红的检查等于没有检查。

## 5. 探针自检

`scripts/tests/guard_summary_aggregation.test.js` 15 条（4 命中 / 7 放行 / 2 失败态 / 2 真实文件正反）。

两个真探针（不是合成样例）：

1. 拿**真实 `summary_service.py`**，把账户级的委托替换回手写累加 → 守卫转红
   （`summary_service.py:591 函数 get_ledger_distributions() 自己累加 total_assets += ...`）；
2. 还原 → 复绿。

失败态按 `#171` 纪律（拿不到输入 ≠ 没有违规）：文件不存在、语法错误一律**退 2 且不得打印 `OK`**。

> 踩坑记录：第一次探针跑完 `ERROR` 之后 `cp` 还原，再跑**仍是 ERROR**。
> 原因是 `cp` 与守卫检查在同一条 `bash -c` 里、还原那步的输出被 `tail` 截掉了——
> 看上去像「守卫恒红」，实际是文件没还原回去。**探针脚本的清理步骤必须自己确认一次**
> （`grep` 一下锚点还在不在），否则会把「没还原」读成「判据失效」。

## 6. 口径变更对存量数据的处置（AGENTS.md 三之四）

本次**不改口径、只改实现**，故存量数据无需收编：`get_ledger_distributions` 此前算出的
账户级快照与家庭级数值**本就一致**（`test_account_snapshots.py` 一直在断言这一点），
换实现后同值。这正是「只改实现」与「改口径」的分别——后者必须单独答「按旧规则已产生的数据怎么办」。

## 7. 边界

- `LedgerService.get_overview_stats`（账户资金全景）**仍然不动**：它算的是账户的资金构成
  （现金 / 持仓 / 负债），不是「总资产」口径，本守卫的射程也不含它。
- 守卫只扫 `summary_service.py` 一个文件——「总资产口径」的归属文件。别处的桶各有独立契约。
