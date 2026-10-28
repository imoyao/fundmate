# -*- coding: utf-8 -*-
"""持仓可见性口径的统一入口（issue #2343 第一步）。

## 为什么需要单独一个模块

`positions.ownership_status` 有三种取值（见 `app.core.constants.OwnershipStatus`）：

- `active`  —— 真实持有，参与持仓列表 / 总资产 / 收益日历；
- `shadow`  —— E账户导入写下的**对账镜像行**（`ledger_id` 恒为 NULL、`account_name`
  恒为「基金E账户」）。只在对账视图可见，不参与持仓列表 / 总资产 / 交易流水——
  它是「E账户说有这笔、系统还没认领」的待核对项，不是用户开的户，也不是可买卖的账户；
- `cleared` —— **已清仓，行保留**（份额归零，快照锚点与成本基线原样留存）。

在 `cleared` 出现之前，全仓 68 处 `query(Position)` 里只有 6 处显式过滤了
`ownership_status`，持仓列表（`position_service.list_positions`）和账户统计
（`ledger_service` 的 4 处）**都没过滤**——它们默认「表里每一行都是当前持仓」。

这个默认在清仓删行的年代成立。一旦清仓改为「保留行 + 标记 `cleared`」，这些查询
会把已清仓行当成当前持仓，表现为「持仓列表里有、总资产里没有」或「列表里没有、
总市值里还有」的自相矛盾。**必须先铺过滤器、再改删除行为**，否则中间态一定错。

## 迁移顺序（本模块是第一步）

1. 【当前】所有「当前持仓」视图挂上 `exclude_cleared()`。
   此刻库里还没有 `cleared` 行，`ownership_status != 'cleared'` 是**恒等变换**，
   零行为变化——这一点由 `tests/services/test_position_scope.py` 用真实夹具锁住。
2. 【下一步】`process_sell_or_withdraw` 清仓时不再 `db.delete(position)`，
   改为 `quantity = 0` + `ownership_status = 'cleared'`，锚点原样保留。
   过滤器届时自动生效，不需要再动任何查询。

## 反例：这些地方**不要**用它

把 `cleared` 排掉就等于抹掉历史，以下场景必须全量：

| 场景 | 位置 |
|---|---|
| 交易流水查询 | `transactions` 表（已清仓标的的历史交易照常可见） |
| 对账比对 | `reconciliation_service`（要拿全量算差异） |
| 账户迁移 | `ledger_migration_service`（迁走清仓行会丢历史） |
| 孤儿流水回填 | `sync/jobs/orphan_backfill_job`（可能挂到已清仓标的） |
| 产品身份 / 展示名 | `product_identity`（清仓标的仍要能显示名字） |
| XIRR 现金流 | `symbol_scope`（文档已明确：清仓标的的现金流仍参与持有年化） |
| 按主键精确取单行 | `filter_by(id=...)`（调用方已经知道要哪一行） |

份额已归零的 `cleared` 行在 `quantity > 0` 的查询里天然被排除，
但**不要依赖这一点**——依赖它等于把「清仓」和「份额为 0」两个语义绑死，
后续若出现「0 份额但仍持有」（如待确认的赎回）就会出错。
"""

from sqlalchemy.orm import Query

from app.core.constants import OwnershipStatus
from app.domains.positions.models import Position


def exclude_cleared(query: Query) -> Query:
    """给 `query(Position)` 挂上「排除已清仓」条件。

    这是**当前持仓视图**的默认口径。库里还没有 `cleared` 行时它是恒等变换，
    所以可以在改删除行为之前先无风险地铺满全部视图。
    """
    return query.filter(Position.ownership_status != OwnershipStatus.CLEARED.value)


def active_holdings(query: Query) -> Query:
    """只要 `active`：同时排除 `shadow`（对账镜像）与 `cleared`（已清仓）。

    **这是所有「当前持仓」视图的默认口径**，包括持仓列表（`position_service`
    `build_position_list`）、总资产 / 收益计算。

    ## `shadow` 为什么必须一起排掉（2026-10-28 修正）

    `exclude_cleared` 的旧约定是「`shadow` 在持仓列表里要看得见（等用户归属）」，
    那是**归属动作还长在持仓列表里**的年代。归属后来搬进对账工作台
    （`get_reconciliation` 直接查 `ownership_status='shadow'`），列表侧再留着它就只有副作用：

    - `shadow` 行的 `ledger_id` 恒为 NULL、`account_name` 恒为「基金E账户」，
      前端 `groupByLedger` 按 `account_name` 落组，于是**凭空多出一个叫「基金E账户」的渠道**；
    - 本地库实测（2026-10-28）：021180 在产品详情「我的持仓」显示两组
      （基金E账户 3,421.96 份 + 微众银行 3,421.9622 份），市值 9,350.85 + 9,254.70 = 翻倍；
    93 条镜像行全部落在「未归档持仓」分组里，而那 93 条里没有一条是真实的未归档持仓。

    E账户是**对账用的持仓快照来源**，不是用户的交易账户——持仓与交易流水是两个概念，
    镜像行既不该进持仓视图，也不该被当成可记账的账户。
    """
    return query.filter(Position.ownership_status == OwnershipStatus.ACTIVE.value)


def exclude_shadow(query: Query) -> Query:
    """排除 `shadow`（对账镜像行），**保留已清仓**。

    用于「持仓行本身要全、但镜像行不算持仓」的场景——典型是 XIRR 现金流：
    已清仓行的市值是 0，可它名下的买卖 / 分红流水仍要参与年化计算
    （`services/symbol_scope.query_positions_by_symbol` 的既有口径），
    而镜像行既没有自己的流水、也不该贡献市值，留在结果里只会把期末市值算大。

    `active_holdings` 比它更严（连 `cleared` 一起排），两者不可互相替代：
    持仓列表用 `active_holdings`，年度化 / 时间线用 `exclude_shadow`。
    """
    return query.filter(Position.ownership_status != OwnershipStatus.SHADOW.value)


__all__ = ['exclude_cleared', 'active_holdings', 'exclude_shadow']
