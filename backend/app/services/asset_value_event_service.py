# -*- coding: utf-8 -*-
"""单资产值变动事件的**唯一写者**与读路径（D99 / D100）。

设计见 `docs/design/asset-value-history-design.md`。职责边界：

- 写：`record_value_change` 在同一事务内完成「插入 append-only 事件 + 更新
  `assets.amount` 投影缓存」。视图层不碰这两张表的写，避免第二个写者。
- 读：`list_value_events`（时间线）与 `value_asof`（时点值）；家庭级
  `asset_snapshots` 一行不改，也不参与此处计算。

事务边界沿用 `core/database.py` 的 teardown（统一 commit / rollback），
本模块**不 commit**。金额存储恒为整数分，出参统一转元（与 assets API 一致）。
"""

import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.money import Money
from app.domains.assets.models import Asset, AssetValueEvent

# kind 只是展示标签，不是分表依据（设计 §3.1）
KIND_VALUATION = 'valuation'
KIND_REPAYMENT = 'repayment'
KIND_BORROW = 'borrow'
KIND_RECEIVABLE_CHANGE = 'receivable_change'
KIND_CORRECTION = 'correction'
KIND_ADJUSTMENT = 'adjustment'

# 前端只允许显式声明「更正」；其余 kind 一律由大类派生，避免多一套词表维护
ALLOWED_CHANGE_KINDS = frozenset({KIND_CORRECTION})
_VALUE_CATEGORIES = frozenset({'real_estate', 'fixed', 'precious_metal', 'custom'})


def today_in_app_zone() -> date:
    """业务日期默认值用东八区，不用 UTC（前端 `utils/date.ts` 同口径）。"""
    return datetime.now(ZoneInfo('Asia/Shanghai')).date()


def resolve_kind(major_category: str | None, delta: int, change_kind: str | None = None) -> str:
    """按大类派生展示标签；`change_kind='correction'` 优先（设计 §3.4）。"""
    if change_kind:
        if change_kind not in ALLOWED_CHANGE_KINDS:
            raise ValueError(f'change_kind 非法：{change_kind!r}')
        return change_kind
    if major_category in _VALUE_CATEGORIES:
        return KIND_VALUATION
    if major_category == 'liability':
        return KIND_REPAYMENT if delta < 0 else KIND_BORROW
    if major_category == 'receivable':
        return KIND_RECEIVABLE_CHANGE
    return KIND_ADJUSTMENT


def _insert_statement(db):
    """按方言选 Core insert，用数据库原生约束做幂等（不做先 SELECT 再 INSERT）。"""
    bind = db.get_bind()
    dialect = getattr(bind, 'dialect', None)
    insert_fn = pg_insert if getattr(dialect, 'name', 'sqlite') == 'postgresql' else sqlite_insert
    return insert_fn(AssetValueEvent.__table__)


def record_value_change(
    db,
    asset: Asset,
    *,
    delta_cents: int,
    effective_date: date | None = None,
    change_note: str | None = None,
    client_token: str | None = None,
    change_kind: str | None = None,
) -> dict:
    """记录一次值变化：append-only 事件 + `assets.amount` 投影，二者同一事务。

    ## 为什么入参是 delta 而不是「变动后绝对值」

    delta 必须是**独立业务事实**（还款 −3000、重估 +20 万），不能由
    `新值 − 当前值` 反推：当前值已包含后续所有变动，用绝对值补录一条更早
    事件会把后面整条曲线平移（实证：先录 11 月 90 万、再补 10 月 95 万
    ⇒ 10 月变 105 万）。delta 的求和可交换，乱序补录才真的**零重算**：
    `Σdelta` 自动包含它，`value_asof` 的倒推公式天然正确（设计 §4.2 / §5.3）。

    兼容旧客户端：若 PATCH 仍传绝对 `amount`，由视图层换算成
    `after − before` 再调本函数；两条入口都收敛到这里的唯一写者。

    幂等（D71 同源）：`client_token` UNIQUE + `ON CONFLICT DO NOTHING`。
    重放时不更新 `amount`、不追加事件，返回首次写入的结果。这里的 SELECT
    发生在 INSERT **之后**，不是会引入 TOCTOU 的「先查后写」。

    `delta == 0`（只改名 / 只改备注 / 只改子类）⇒ 不写事件，否则时间线会被
    纯改名刷屏且 `Σdelta` 不变却多出无意义行（设计 §5.2）。
    """
    before_cents = int(asset.amount or 0)
    delta_cents = int(delta_cents)
    if delta_cents == 0:
        return {'written': False, 'reason': 'unchanged', 'delta': 0, 'event_id': None}
    after_cents = before_cents + delta_cents
    if after_cents < 0:
        raise ValueError('变动后余额不能为负（assets.amount 恒正口径）')

    token = (client_token or '').strip() or uuid.uuid4().hex
    eff_date = effective_date or today_in_app_zone()
    kind = resolve_kind(asset.major_category, delta_cents, change_kind)
    family_id = asset.family_id or 1
    note = (change_note or '').strip() or None

    payload = {
        'family_id': family_id,
        'asset_id': asset.id,
        'effective_date': eff_date,
        'delta': delta_cents,
        'kind': kind,
        'notes': note,
        'client_token': token,
    }

    # 先 INSERT：若此处先 flush 了 ORM 的 amount 变更，重放分支就会变成
    # 「事件没写、金额却已变」，破坏 amount − Σdelta 不变量。
    stmt = _insert_statement(db).values(**payload).on_conflict_do_nothing(index_elements=['client_token'])
    result = db.execute(stmt)

    if result.rowcount != 1:
        first = db.query(AssetValueEvent).filter_by(client_token=token).one()
        return {
            'written': False,
            'reason': 'replayed',
            'delta': first.delta,
            'event_id': first.id,
            'effective_date': first.effective_date,
        }

    asset.amount = int(after_cents)
    db.flush()
    return {
        'written': True,
        'reason': 'written',
        'delta': delta_cents,
        'event_id': None,
        'effective_date': eff_date,
    }


def apply_patch_value_change(db, asset: Asset, update_data: dict) -> tuple[dict, str | None]:
    """消费 PATCH body 中的值变动字段，返回「剩余普通字段 + 可选错误信息」。

    视图层只做 HTTP 编排（`check_view_thickness.py` 的职责边界），所以
    delta/amount 兼容换算与事件字段校验都落在这里。返回副本而非就地改
    `update_data`，避免调用方在 400 分支里看到被悄悄 pop 过的 body。
    """
    remaining = dict(update_data)
    event_fields = {
        key: remaining.pop(key)
        for key in ('effective_date', 'change_note', 'client_token', 'change_kind')
        if key in remaining
    }
    has_delta = 'delta' in remaining
    has_amount = 'amount' in remaining
    if has_delta and has_amount:
        return remaining, 'delta 与 amount 不能同时提交'
    if event_fields and not (has_delta or has_amount):
        return remaining, '变动日期／说明／更正标记须配合 delta 或 amount'

    if has_delta or has_amount:
        if has_delta:
            delta_cents = Money.yuan_to_cents(remaining.pop('delta'))
        else:
            after_cents = Money.yuan_to_cents(remaining.pop('amount'))
            delta_cents = after_cents - int(asset.amount or 0)
        try:
            record_value_change(db, asset, delta_cents=delta_cents, **event_fields)
        except ValueError as exc:
            return remaining, str(exc)
    return remaining, None


def _ordered_events(db, asset: Asset) -> list[AssetValueEvent]:
    """单资产全序列：按 (effective_date, id) 升序，走复合索引，非全表扫描。"""
    return (
        db.query(AssetValueEvent)
        .filter(
            AssetValueEvent.family_id == (asset.family_id or 1),
            AssetValueEvent.asset_id == asset.id,
        )
        .order_by(AssetValueEvent.effective_date.asc(), AssetValueEvent.id.asc())
        .all()
    )


def _event_dict(event: AssetValueEvent, value_after_cents: int) -> dict:
    """出参统一为元；`value_after` 是读时折叠结果，**不落库**（设计 §4.2）。"""
    return {
        'id': event.id,
        'asset_id': event.asset_id,
        'effective_date': event.effective_date.isoformat() if event.effective_date else None,
        'recorded_at': event.recorded_at.isoformat() if event.recorded_at else None,
        'delta': Money.cents_to_yuan(event.delta),
        'value_after': Money.cents_to_yuan(value_after_cents),
        'kind': event.kind,
        'notes': event.notes,
    }


def list_value_events(db, asset: Asset, *, page: int = 1, per_page: int = 20) -> dict:
    """时间线：返回分页事件 + 逐条「变动后值」。

    逐条 `value_after` 需要全序列折叠（`初始余额 = amount − Σdelta` 后逐条累加），
    故一次索引扫描后在内存切片；单资产年均数十行，量级有界，避免 N+1 或窗口函数
    的跨方言差异（设计 §8 / §9.2）。
    """
    page = max(1, int(page))
    per_page = max(1, min(int(per_page), 200))
    rows = _ordered_events(db, asset)

    total_delta = sum(int(r.delta or 0) for r in rows)
    running = int(asset.amount or 0) - total_delta
    value_after: dict[int, int] = {}
    for row in rows:
        running += int(row.delta or 0)
        value_after[row.id] = running

    start = (page - 1) * per_page
    items = [_event_dict(r, value_after[r.id]) for r in rows[start : start + per_page]]
    return {
        'data': items,
        'total': len(rows),
        'page': page,
        'per_page': per_page,
        'message': 'ok',
    }


def value_asof(db, asset: Asset, d: date) -> dict:
    """时点值：`amount − Σ(delta_i | effective_date_i > d)`（设计 §6.2，复用 D98 倒推）。

    D100 可信下界：`start_date` 为空或 `d < start_date` ⇒ `valid=false` / `value=null`。
    不回落 `created_at`、不用最早事件反推、不向前外推成水平线、不插值。

    I2：出现负值说明 delta 写反或漏写，**忠实返回并记错误日志**，不夹紧成 0
    （夹紧会把不变量错误藏起来）；非负性由 A5 判据逐组断言。
    """
    if asset.start_date is None or d < asset.start_date:
        return {'value': None, 'valid': False}

    later = (
        db.query(func.coalesce(func.sum(AssetValueEvent.delta), 0))
        .filter(
            AssetValueEvent.family_id == (asset.family_id or 1),
            AssetValueEvent.asset_id == asset.id,
            AssetValueEvent.effective_date > d,
        )
        .scalar()
        or 0
    )
    cents = int(asset.amount or 0) - int(later)
    if cents < 0:
        logger.error(
            'asset_value_events 不变量 I2 破缺：as-of {} 推得负余额 {} 分（asset_id={}）',
            d,
            cents,
            asset.id,
        )
    return {'value': Money.cents_to_yuan(cents), 'valid': True}


def initial_balance_cents(db, asset: Asset) -> int:
    """派生锚点：`amount − Σ(全部 delta)`；序列为空时就是当前值（设计 §6.2）。"""
    total = (
        db.query(func.coalesce(func.sum(AssetValueEvent.delta), 0))
        .filter(
            AssetValueEvent.family_id == (asset.family_id or 1),
            AssetValueEvent.asset_id == asset.id,
        )
        .scalar()
        or 0
    )
    return int(asset.amount or 0) - int(total)
