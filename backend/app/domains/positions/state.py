# -*- coding: utf-8 -*-
"""持仓状态机与不变量的纯函数层（#2875 切片 B）。

## 为什么单独立一层

持仓的「状态迁移」此前散在 2000+ 行的 ``position_service.py`` 里，只有服务层能调用。
但它们是**业务不变量**，不是某个服务的内务：

- :func:`is_covered_by_anchor` —— 锚点覆盖判定（流水是否已被快照包含，决定要不要驱动份额）；
- :func:`mark_position_cleared` —— 清仓（零份额 + ``cleared_at`` 周期下界 + 保留锚点）；
- :func:`reactivate_cleared_position` —— 清仓后再买入，复用同一行并把锚点重置为新一轮起点；
- :func:`derive_state_from_txns` —— 无锚点时按全量流水派生份额/成本。

导入、重建、数据修复脚本都该走同一套，而不是各自复刻一遍（这正是 #2875 说的
「每条新写路径重写一套状态机」）。抽成**纯函数**（只吃 Position / 流水 / 日期，
不碰 Session）之后，才能被单测直接钉住——在此之前它们只能通过 403 行的
``process_buy_or_deposit`` 间接覆盖。

## 与库级约束的分工

本模块管「怎么写」，``positions`` 上的两条 CHECK（``ck_positions_cleared_zero_qty`` /
``ck_positions_anchor_qty_needs_date``）管「写坏了库会报错」。
后者是**方向式**的：有份额就必须有日期，反向不要求（「有日期、无份额」是
``migrate_positions_snapshot_anchor`` 的正常产物）。
两边是同一组不变量的两处表达：改这里的写入语义时，同步看模型与
``migrations._POSITION_STATE_CHECKS``。
"""

from datetime import date, datetime, timedelta

from app.core.constants import AnchorKind, OwnershipStatus
from app.core.money import Money
from app.domains.positions.models import Position


def is_covered_by_anchor(position: Position, effective_date) -> bool:
    """这笔流水是否已包含在持仓快照锚点里（包含则**不得**再驱动 quantity）。

    判定：`归属日 <= 快照日` → 已包含。按 confirm_date 而非 trade_date：
    基金份额在确认日（T+1）才真实变动，快照反映份额登记状态。

    边界：日期无法解析 → 视为「未包含」（保持旧行为，宁可多算也不静默丢流水），
    由对账工作台暴露差异。这与 `compute_anchored_state` 的「排除 + 告警」不同：
    那里是派生（必须唯一），这里是写入（不能吞掉用户刚录的交易）。
    """
    if position is None or position.snapshot_quantity is None or position.snapshot_date is None:
        return False
    if position.ownership_status != 'active':
        return False
    if effective_date is None:
        return False
    if isinstance(effective_date, str):
        # 卖出/导入路径可能直接透传 ISO 字符串（未经 _resolve_confirm_date 归一）
        try:
            day = datetime.strptime(effective_date[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return False
    elif hasattr(effective_date, 'date'):
        day = effective_date.date()
    else:
        day = effective_date
    return day <= position.snapshot_date


def mark_position_cleared(position: Position, when=None) -> None:
    """把持仓标记为**已清仓**（行保留，issue #2343 第二步）。

    取代过去的 `db.delete(position)`。行保留后三样东西不会随清仓消失：
    - 快照锚点四列（`snapshot_quantity / snapshot_avg_price / snapshot_date / anchor_kind`）
      ——删除卖出流水触发重建时仍走锚点口径，不会退回「全量流水」二次累加；
    - `avg_price`（上一轮的成本基线，「历史曾持有」可追溯）；
    - 名下流水（本来就不级联，但持仓行在，`position_id` 归属不断链）。

    `cleared_at` 记录**何时**清仓，取**清仓流水的确认日**（业务事实，可测试、可回放），
    不是墙钟时间——「系统何时处理的」没有业务意义，且会让「清仓日 < 再买入日」的
    常规时间线在补录场景下倒挂。`when` 接受 str/date/datetime，解析失败退墙钟。

    重新激活时**保留不清**本列——它是「清仓后再买入」新一轮周期的下界，
    「当前是否已清仓」一律看 `ownership_status`。
    """
    position.quantity = 0
    position.ownership_status = OwnershipStatus.CLEARED.value
    if when is None:
        position.cleared_at = datetime.now()
    elif isinstance(when, datetime):
        position.cleared_at = when
    elif isinstance(when, date):
        position.cleared_at = datetime(when.year, when.month, when.day)
    else:
        try:
            position.cleared_at = datetime.strptime(str(when)[:10], '%Y-%m-%d')
        except ValueError:
            position.cleared_at = datetime.now()


def reactivate_cleared_position(position: Position, first_flow_date) -> None:
    """把已清仓持仓重新激活为**新一轮周期**（#2343）。

    同账户同标的受 `uq_positions_ledger_symbol(_norm)` 双唯一约束，清仓行保留后
    再次买入**必然**复用同一行——「新建一行」在数据库层面不可行（2026-10-18 实测
    INSERT 直接撞约束）。

    复用的关键动作是**重置锚点**，而不是只把状态改回 active：

        锚点 = (0 份, 0 成本额, 清仓日, manual)

    不重置的后果（同日实测）：旧锚点的成本额按卖出比例核销后仍有残留，新一轮
    3000 份 @1.60 会被派生成 **1.4375**（虚低 10.2% ⇒ 浮盈虚高）——上一轮的利润
    悄悄漏进这一轮的成本里。重置后 quantity = 0 + Σ(归属日 > 清仓日)，只认本轮流水。

    锚点日直接取**清仓日**（`cleared_at.date()`）：
    - 常规（买入在清仓之后）：清仓卖出 `== 锚点日` 被 `> anchor` 规则排除，本笔买入计入 ✓；
    - `cleared_at` 为 NULL（历史清仓行无清仓时间）：退「本笔归属日前一天」，
      保证本笔自身不被锚点吞掉；
    - **清仓当天又买入**（confirm_date == 清仓日）：买入同样被 `>` 排除 → 0 份。
      已知边界，日粒度数据无法区分同日先卖后买；刻意**不**退到前一日——那会把
      清仓卖出也计入，净额变负（比 0 份更糟）。0 份由对账工作台暴露，宁可不算不算错。

    `cleared_at` 保留不清空（周期下界），`confirm_date` 同样不动——持有天数
    口径是「首次建仓确认日」（#862 历史口径），改口径需要产品决策，本次不做。
    """
    if position.cleared_at is not None:
        anchor_date = position.cleared_at.date() if isinstance(position.cleared_at, datetime) else position.cleared_at
    elif first_flow_date is None:
        anchor_date = date.today()
    else:
        if isinstance(first_flow_date, datetime):
            day = first_flow_date.date()
        elif isinstance(first_flow_date, date):
            day = first_flow_date
        else:
            day = datetime.strptime(str(first_flow_date)[:10], '%Y-%m-%d').date()
        anchor_date = day - timedelta(days=1)

    position.ownership_status = OwnershipStatus.ACTIVE.value
    position.snapshot_quantity = 0
    position.snapshot_avg_price = 0
    position.snapshot_date = anchor_date
    position.anchor_kind = AnchorKind.MANUAL.value


def derive_state_from_txns(txns, base_qty: int, base_cost_cents: int) -> tuple[int, int]:
    """纯函数：给定基线份额/成本额，叠加流水推导 (净份额, 成本均价)。

    抽成纯函数是为了让「持仓行已被删除、需要从流水重建」的分支复用同一套加减口径，
    避免重算引擎出现第二份实现（两份实现必然分叉，正是本 bug 的成因之一）。
    """
    buy_qty = 0
    buy_cost = 0
    sell_qty = 0
    for t in txns:
        if t.txn_type in ('buy', 'deposit'):
            buy_qty += t.quantity
            buy_cost += Money.multiply_price_quantity(t.price, t.quantity)
        elif t.txn_type == 'split':
            # 送股/拆分：份额增加、成本不变（仅稀释均价）
            buy_qty += t.quantity
        elif t.txn_type in ('sell', 'withdraw'):
            sell_qty += t.quantity

    net_qty = base_qty + buy_qty - sell_qty
    base_and_buy_qty = base_qty + buy_qty
    avg_price = 0
    if base_and_buy_qty > 0:
        avg_price = Money.yuan_to_price_units(
            round(Money.cents_to_yuan(base_cost_cents + buy_cost) / Money.min_unit_to_shares(base_and_buy_qty), 4)
        )
    return net_qty, avg_price
