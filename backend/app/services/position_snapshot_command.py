# -*- coding: utf-8 -*-
"""持仓**快照导入命令**（#2873 第五抽）。

`PositionService.upsert_from_holding` 曾是一个 203 行、圈复杂度 30 的单方法（#2873 第四抽
收尾时它是 `position_service.py` 里最大的函数），把四件事串在一条直线里：

    解析校验 → 锚点 SET/新建 → 落溯源 meta → 挂孤儿 + 锚点派生 + 自选同步

本模块承接整条链路，主模块只留转发薄壳（签名与行为逐字不变，203 行 → 约 20 行）。

## 四段与 `SnapshotIntent`

    resolve_snapshot_intent   校验 + venue 归一 + 同日/金额口径收敛，产出不可变 intent
    upsert_anchor_position    「合并既有 / 新建」+ 锚点时间轴守卫，落 positions 层
    upsert_import_meta        position_import_meta 的 1:1 upsert
    finalize_snapshot         挂回孤儿流水 → 锚点派生 → 净值补抓 → 自选静默入库

段间共享的既有局部变量里，**只有派生值**进 `SnapshotIntent`（份额/价格的「最小单位」形态、
快照日、来源、import_hash）。名称、账户、溯源 meta 等字段刻意仍从原始 `data` 取：
`data` 本身就是这条链路的入参契约，把它们再抄一份进 dataclass 只会制造第二份真相源，
且任何新增字段都要在两处同步——这正是本仓 #2816「状态有值但没人消费」一类静默错的温床。

## 顺序是这条链路的一部分（不是巧合）

下面几处顺序**不能优化**，每一处都有事故史：

1. **venue 归一在查找既有持仓之前**（#1662）：`positions` 的唯一约束是字面量
   `UNIQUE(ledger_id, symbol)`，拦不住 `SZ004369` / `004369` 并存；
2. **`_assert_anchor_accepts` 在任何 SET 之前**：时间不可倒流、同日 manual 优先，
   先写后判会让拒绝路径留下半条脏数据；
3. **`is_money_fund` 在 `db.flush()` 之后**：需要 `position.id` 参与冗余判定落库（#863）；
4. **`_reattach_orphan_flows` 在 `compute_anchored_state` 之前**（#1657）：刚挂回的孤儿
   流水也要参与派生，否则它们要等下一轮重算才计入，中间这段市值偏小；
5. **负份额钳 0 且保留快照成本价**：导入路径不做「删行」（那是卖出路径的职责），
   0 份额时保留 `avg_price` 以免前端显示「成本 0 元」。

## 依赖方向

`position_service` 在模块级导入本模块（转发薄壳）；本模块只在**函数内**延迟导入
主模块的四个辅助（`_assert_anchor_accepts` / `_resolve_money_fund_flag` /
`compute_anchored_state` / `_silent_ensure_watchlist`）。它们同时服务卖出与重算路径，
留主模块才不制造双向依赖——与 `position_buy_command` 同一范式，本仓既有 180+ 处。

## 刻意不做的事

- **不改锚点语义**：`allow_anchor_rewind` 仍只对账工作台 `kind='set'` 开放；
- **不合并 `compute_anchored_state` 的调用点**：卖出/重算/分红也用它，动它超出本抽范围；
- **不动 `ownership_status` 的 shadow 分支**：影子行（非 active）照样不写 positions 锚点，
  只在 meta 层留日期，否则重算会把对账影子链路搅进派生逻辑。
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.constants import AnchorKind, PositionSource
from app.core.money import Money
from app.core.symbol_utils import normalize_by_venue
from app.core.venues import resolve_venue
from app.domains.positions.models import Position, PositionImportMeta
from app.services import async_backfill
from app.services.import_records import compute_position_hash
from app.services.institution_resolver import resolve_sales_institution_id
from app.services.position_orphan_flows import _reattach_orphan_flows
from app.services.position_write_support import _find_existing_position, _resolve_family_id


@dataclass(frozen=True)
class SnapshotIntent:
    """校验并归一后的快照入参（不可变）。

    只装**派生值**：份额/价格已是 `Money` 最小单位、venue 已归一、快照日已确定、
    `import_hash` 已按归一后的 symbol 与日期算出。解析完成后任何一段都不得改写。
    """

    symbol: str
    ledger_id: int
    family_id: int
    venue: Optional[str]
    qty_units: int
    price_units: int
    snapshot_date: date
    anchor_kind: str
    source: str
    import_hash: str
    ownership_status: str
    allow_anchor_rewind: bool


def resolve_snapshot_intent(
    data: dict,
    *,
    ownership_status: str = 'active',
    allow_anchor_rewind: bool = False,
) -> SnapshotIntent:
    """解析 + 校验快照入参，产出不可变 intent。

    校验口径（沿用 #1012 落地时的用户确认，勿单方面放宽）：
    - 必须给 `symbol` 与 `ledger_id`；
    - 份额必须 > 0；
    - 成本均价优先 `avg_price`，缺失降级 `current_price` 近似；两者都缺 ⇒ 拒绝。

    venue 归一顺带把 `data['symbol']` 写回（调用方的字典与后续溯源 meta 都按归一后的
    形态落库）——这是既有行为，不是副作用泄漏。
    """
    symbol = data.get('symbol', '')
    ledger_id = data.get('ledger_id')
    family_id = _resolve_family_id(data)
    if not symbol or not ledger_id:
        raise ValueError('持仓快照导入必须提供 symbol 与 ledger_id')

    # venue（#1662）：显式入参优先，缺失按 asset_type 推断（持仓快照本无场所维度，只能兜底）。
    # 落库前把 symbol 收敛到该场所的唯一形态，避免同一标的并存 `SZ004369` / `004369`
    # 两种写法——positions 的唯一约束是字面量 UNIQUE(ledger_id, symbol)，拦不住。
    venue = resolve_venue(data.get('venue'), data.get('asset_type'))
    if venue:
        symbol, _venue_market, _ = normalize_by_venue(symbol, venue)
        data['symbol'] = symbol

    qty = data.get('quantity', 0) or 0
    if qty <= 0:
        raise ValueError('数量必须大于 0')

    # 成本均价：优先显式 avg_price，缺失降级为当前净值近似（用户已确认）
    price_yuan = data.get('avg_price') or data.get('current_price') or 0
    if price_yuan <= 0:
        raise ValueError('成本均价与当前净值均缺失，无法确定价格')

    # 快照日：优先 snapshot_date，缺失降级为落库当日（规范 §3.3）
    raw_snap = data.get('snapshot_date') or date.today()
    snapshot_date = raw_snap if isinstance(raw_snap, date) else datetime.fromisoformat(str(raw_snap)).date()

    incoming_kind = data.get('anchor_kind') or AnchorKind.EXTERNAL.value
    if isinstance(incoming_kind, AnchorKind):
        incoming_kind = incoming_kind.value

    src = data.get('source', PositionSource.E_ACCOUNT.value)

    return SnapshotIntent(
        symbol=symbol,
        ledger_id=ledger_id,
        family_id=family_id,
        venue=venue,
        qty_units=Money.shares_to_min_unit(qty),
        price_units=Money.yuan_to_price_units(price_yuan),
        snapshot_date=snapshot_date,
        anchor_kind=incoming_kind,
        source=src,
        import_hash=data.get('import_hash') or compute_position_hash(src, ledger_id, symbol, snapshot_date),
        ownership_status=ownership_status,
        allow_anchor_rewind=allow_anchor_rewind,
    )


def _apply_anchor_set(existing: Position, intent: SnapshotIntent, data: dict) -> Position:
    """既有持仓上的锚点 SET（三件套同批写入）。"""
    # 函数内导入：该守卫只服务快照路径，但定义在主模块，模块级导入会成环。
    from app.services.position_service import _assert_anchor_accepts  # noqa: PLC0415

    _assert_anchor_accepts(
        existing,
        intent.snapshot_date,
        intent.anchor_kind,
        allow_rewind=intent.allow_anchor_rewind,
    )
    existing.snapshot_quantity = intent.qty_units
    existing.snapshot_avg_price = intent.price_units
    existing.snapshot_date = intent.snapshot_date
    existing.anchor_kind = intent.anchor_kind
    # quantity 先按快照值占位；下方 reattach 孤儿流水后用锚点重算覆盖。
    existing.quantity = intent.qty_units
    existing.avg_price = intent.price_units
    existing.current_price = intent.price_units
    existing.confirm_date = intent.snapshot_date
    existing.name = data.get('name') or existing.name
    existing.account_name = data.get('account_name') or existing.account_name
    existing.currency = data.get('currency') or existing.currency
    existing.import_hash = intent.import_hash
    existing.source = intent.source
    existing.source_broker = data.get('source_broker')
    # 对账扩展：调用方显式传 shadow 时同步更新（防渠道记录被误标为影子）
    if existing.ownership_status != intent.ownership_status:
        existing.ownership_status = intent.ownership_status
    return existing


def _new_position_from_snapshot(intent: SnapshotIntent, data: dict) -> Position:
    """按快照新建持仓行（影子行不落 positions 层锚点）。"""
    # 影子行（ownership_status != active）不落锚点：它只在 position_import_meta 层
    # 有日期，若写 positions 层锚点，重算会把对账影子链路搅进派生逻辑。
    write_anchor = intent.ownership_status == 'active'
    return Position(
        symbol=intent.symbol,
        name=data.get('name') or intent.symbol,
        market=data.get('market', 'CN_A'),
        asset_type=data.get('asset_type', 'fund'),
        ledger_id=intent.ledger_id,
        account_name=data.get('account_name', ''),
        quantity=intent.qty_units,
        avg_price=intent.price_units,
        current_price=intent.price_units,
        currency=data.get('currency', 'CNY'),
        confirm_date=intent.snapshot_date,
        allocation=data.get('allocation', 'longterm'),
        import_hash=intent.import_hash,
        source=intent.source,
        source_broker=data.get('source_broker'),
        ownership_status=intent.ownership_status,
        family_id=intent.family_id,
        snapshot_quantity=intent.qty_units if write_anchor else None,
        snapshot_avg_price=intent.price_units if write_anchor else None,
        snapshot_date=intent.snapshot_date if write_anchor else None,
        anchor_kind=intent.anchor_kind if write_anchor else None,
    )


def upsert_anchor_position(db: Session, intent: SnapshotIntent, data: dict) -> Position:
    """按 `(ledger_id, symbol, venue)` 定位既有持仓并 SET 锚点，缺失则新建。

    SET 语义：份额 / 成本价 / 快照日三者**必须同批写入**（缺 `snapshot_avg_price` 会让
    重算拿不到快照原价，成本被永久稀释）。`quantity` 先按快照值占位，等
    `finalize_snapshot` 回来用锚点重算覆盖——这是修复「份额被快照与流水重复累加」的关键。
    """
    # 函数内导入：该辅助同时服务卖出/买入路径，留在主模块才不制造双向依赖。
    from app.services.position_service import _resolve_money_fund_flag  # noqa: PLC0415

    existing = _find_existing_position(
        db,
        ledger_id=intent.ledger_id,
        family_id=intent.family_id,
        symbol=intent.symbol,
        venue=intent.venue,
    )

    if existing:
        position = _apply_anchor_set(existing, intent, data)
    else:
        position = _new_position_from_snapshot(intent, data)
        db.add(position)

    db.flush()

    # #863 口径 A：快照持仓也落货基冗余判定（SET 覆盖，聚合分类归「现金」桶）
    position.is_money_fund = _resolve_money_fund_flag(
        intent.symbol,
        position.asset_type,
        data.get('is_money_fund'),
    )
    return position


def upsert_import_meta(db: Session, position: Position, intent: SnapshotIntent, data: dict) -> None:
    """`position_import_meta` 的 1:1 upsert（保留末次快照的溯源信息）。"""
    meta = data.get('meta') or {}
    meta_row = db.query(PositionImportMeta).filter_by(position_id=position.id).first()
    if meta_row is None:
        meta_row = PositionImportMeta(position_id=position.id, family_id=intent.family_id)
        db.add(meta_row)
    meta_row.symbol = intent.symbol
    meta_row.ledger_id = intent.ledger_id
    meta_row.snapshot_date = intent.snapshot_date
    meta_row.source = intent.source
    meta_row.source_import_id = data.get('source_import_id')
    meta_row.source_broker = data.get('source_broker')
    meta_row.fund_manager = meta.get('fund_manager')
    meta_row.share_class = meta.get('share_class')
    meta_row.fund_account = meta.get('fund_account')
    meta_row.trade_account = meta.get('trade_account')
    meta_row.dividend_preference = meta.get('dividend_preference')
    meta_row.market_value = Money.yuan_to_cents(meta['market_value']) if meta.get('market_value') is not None else None
    meta_row.sales_institution_id = resolve_sales_institution_id(db, data.get('source_broker'))
    db.flush()


def finalize_snapshot(db: Session, position: Position, intent: SnapshotIntent) -> Position:
    """挂回孤儿流水 → 锚点派生份额/成本 → 补抓净值 → 自选静默入库。"""
    from app.services.position_service import (  # noqa: PLC0415
        _silent_ensure_watchlist,
        compute_anchored_state,
    )

    # #863 口径 A 写入层互斥 + #1657 修复：无论 is_money_fund 快照判定如何，都尝试挂回
    # 同 (ledger, symbol) 孤儿货基/逆回购流水（幂等；非货基持仓无对应孤儿流水则无操作），
    # 避免快照 is_money_fund 判定不一致时漏挂回导致资金双计。
    _reattach_orphan_flows(db, intent.ledger_id, intent.symbol, position.id, intent.family_id)

    # 锚点派生：quantity 不再等于快照值，而是「快照 + 快照日之后的流水」。
    # 必须在 _reattach_orphan_flows **之后**：刚挂回的孤儿流水也要参与派生，
    # 否则它们在下一轮重算时才会被计入，中间这一段时间市值偏小。
    if position.snapshot_quantity is not None:
        net_qty, derived_avg = compute_anchored_state(db, position)
        if net_qty < 0:
            # 语义矛盾：快照说还有份额，但快照日之后的流水已把它卖成负数。
            # 导入路径不做「删行」这种激进动作（那是卖出路径的职责），钳到 0 并告警，
            # 由对账工作台暴露给用户。
            logger.warning(
                '快照锚点派生出负份额，已钳为 0: position={} symbol={} net={} anchor={} date={}',
                position.id,
                intent.symbol,
                Money.min_unit_to_shares(net_qty),
                Money.min_unit_to_shares(position.snapshot_quantity),
                position.snapshot_date,
            )
            net_qty = 0
        position.quantity = net_qty
        # 成本只在能派生出正份额时采用；0 份额保留快照成本价，避免 avg_price 被清成 0
        # 后前端显示「成本 0 元」。
        if net_qty > 0:
            position.avg_price = derived_avg
        db.flush()

    try:
        async_backfill.trigger_backfill('fund', intent.symbol)
    except Exception:
        pass

    # #1458 后续：持仓快照导入即入自选（静默，失败不影响主链路）
    _silent_ensure_watchlist(db, intent.family_id, intent.symbol)
    return position
