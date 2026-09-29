# -*- coding: utf-8 -*-
"""探市大类资产观察的快照读写层（#1460 P1）。

职责边界：
- 本模块是 market_asset_daily / market_bond_yield_daily 的**唯一读写口**；
- 写：同步任务 market_asset_daily_job 每日一次；接口在库里缺当日数据时兜底回写；
- 读：/api/market/overview 优先读库（毫秒级），库里不完整才实时取数。

读库组装出的结构与 MarketOverviewService.get_overview() **完全一致**
（含 notes / as_of_note），前端无需区分数据来源；额外带 from_snapshot /
snapshot_date 两个字段，仅用于排障时识别来源。
"""

from datetime import date as date_cls
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import market_session
from app.core.time_utils import now_shanghai
from app.domains.market.models import MarketAssetDaily, MarketBondYieldDaily
from app.services.market_service import (
    ANOMALY_ABS_THRESHOLD,
    ANOMALY_SIGMA_MULTIPLE,
    ANOMALY_SIGMA_WINDOW,
    AS_OF_NOTE,
    ASSET_CONFIG,
    OVERVIEW_NOTES,
    MarketOverviewService,
)


def _to_date(value: Any) -> date_cls:
    """解析源侧日期；解析不出时回退今天（软占位资产没有 trade_date，但仍要占一行）。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_cls):
        return value
    if value:
        try:
            return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    return now_shanghai().date()


def _date_str(d: Optional[date_cls]) -> Optional[str]:
    return d.strftime('%Y-%m-%d') if d else None


def _f(v: Any) -> Optional[float]:
    return float(v) if v is not None else None


# ── 读 ──


def resolve_overview(force: bool) -> Dict[str, Any]:
    """读库优先组装 overview；库里无完整当日数据时实时取数并回写（#1460）。

    编排逻辑集中在 store 层，视图只调本函数（视图层职责边界 #1606）。
    读库 / 回写失败一律静默降级到实时路径：快照是加速手段，不应成为新故障点。
    """
    if not force:
        try:
            with market_session() as db:
                snapshot = load_overview_from_db(db)
            if snapshot:
                return snapshot
        except Exception as e:  # noqa: BLE001 - 快照缺失/异常时降级实时取数，不抛 500
            logger.warning('读大类资产快照失败，降级为实时取数: {}', e)

    # 走到这里说明库里没完整当日快照 → 实时取数（含软占位降级，不整体 500）
    overview = MarketOverviewService.get_overview(force_refresh=force)

    # 兜底回写：本次实时结果存下来，下次请求即可读库（毫秒级命中）。
    try:
        with market_session() as db:
            save_overview_to_db(db, overview)
    except Exception as e:  # noqa: BLE001 - 回写失败不影响本次响应
        logger.warning('大类资产快照回写失败（不影响本次响应）: {}', e)
    return overview


def load_overview_from_db(db: Session) -> Optional[Dict[str, Any]]:
    """读最新交易日快照并组装 overview。

    库里无数据、或覆盖不全（缺任一配置品种）时返回 None —— 调用方据此走实时兜底。
    """
    latest = db.query(func.max(MarketAssetDaily.trade_date)).scalar()
    if latest is None:
        return None

    rows = {r.asset_key: r for r in db.query(MarketAssetDaily).filter(MarketAssetDaily.trade_date == latest).all()}
    if any(a['key'] not in rows for a in ASSET_CONFIG):
        return None

    bond_row = (
        db.query(MarketBondYieldDaily)
        .filter(MarketBondYieldDaily.trade_date <= latest)
        .order_by(MarketBondYieldDaily.trade_date.desc())
        .first()
    )
    bond_yield = None
    if bond_row:
        bond_yield = {
            'cn_10y': _f(bond_row.cn_10y),
            'cn_10y_change_bp': _f(bond_row.cn_10y_change_bp),
            'us_10y': _f(bond_row.us_10y),
            'us_10y_change_bp': _f(bond_row.us_10y_change_bp),
            'trade_date': _date_str(bond_row.trade_date),
        }

    groups_map: Dict[str, List[Dict[str, Any]]] = {c: [] for c in MarketOverviewService.CATEGORY_ORDER}
    unavailable_count = 0
    anomaly_count = 0
    for asset in ASSET_CONFIG:
        item = _asset_item_from_row(asset, rows[asset['key']])
        if not item['available']:
            unavailable_count += 1
        if item['anomaly']:
            anomaly_count += 1
        groups_map.setdefault(asset['category'], []).append(item)

    groups = [
        {'category': c, 'assets': groups_map[c]} for c in MarketOverviewService.CATEGORY_ORDER if groups_map.get(c)
    ]
    return {
        'updated_at': now_shanghai().strftime('%Y-%m-%d %H:%M:%S'),
        'as_of_note': AS_OF_NOTE,
        'groups': groups,
        'unavailable_count': unavailable_count,
        'anomaly_count': anomaly_count,
        'bond_yield': bond_yield,
        'notes': list(OVERVIEW_NOTES),
        'from_snapshot': True,
        'snapshot_date': _date_str(latest),
    }


def _asset_item_from_row(asset: Dict[str, Any], row: MarketAssetDaily) -> Dict[str, Any]:
    """把一行快照还原成前端消费的资产项（结构对齐实时路径）。"""
    position = None
    if row.position_percentile is not None:
        position = {
            'percentile': _f(row.position_percentile),
            'label': row.position_label,
            'basis': row.position_basis,
            'window': row.position_window,
        }
    anomaly = None
    if row.anomaly:
        anomaly = {
            'rule': row.anomaly_rule,
            'sigma': _f(row.anomaly_sigma),
            'sigma_window': ANOMALY_SIGMA_WINDOW,
            'sigma_multiple': ANOMALY_SIGMA_MULTIPLE,
            'abs_threshold': ANOMALY_ABS_THRESHOLD,
            'today_pct': _f(row.change_pct),
            'basis_note': row.anomaly_basis_note,
        }
    return {
        'key': asset['key'],
        'name': asset['name'],
        'category': asset['category'],
        'available': bool(row.available),
        'change_pct': _f(row.change_pct),
        'trade_date': _date_str(row.trade_date),
        'data_asof': row.data_asof,
        'position': position,
        'anomaly': anomaly,
        'caliber': asset.get('caliber'),
        'reason': row.reason,
    }


# ── 写 ──


def save_overview_to_db(db: Session, overview: Dict[str, Any]) -> None:
    """把一次实时取数的结果回写为当日快照（upsert），供后续请求直接读库。"""
    assets: List[Dict[str, Any]] = []
    for group in overview.get('groups') or []:
        assets.extend(group.get('assets') or [])
    if not assets:
        return

    for a in assets:
        _upsert_asset(db, a)
    bond = overview.get('bond_yield')
    if bond:
        _upsert_bond(db, bond)
    # 只 flush、不 commit：请求上下文由 teardown_request_session 统一提交（#1632），
    # job / CLI 这类非请求上下文由调用方自行 commit。
    db.flush()


def _upsert_asset(db: Session, a: Dict[str, Any]) -> None:
    trade_date = _to_date(a.get('trade_date'))
    pos = a.get('position') or {}
    ano = a.get('anomaly') or {}
    values = {
        'close': a.get('close'),
        'change_pct': a.get('change_pct'),
        'position_percentile': pos.get('percentile'),
        'position_label': pos.get('label'),
        'position_basis': pos.get('basis'),
        'position_window': pos.get('window'),
        'anomaly': bool(ano),
        'anomaly_sigma': ano.get('sigma'),
        'anomaly_rule': ano.get('rule'),
        'anomaly_basis_note': ano.get('basis_note'),
        'available': bool(a.get('available', True)),
        'reason': a.get('reason'),
        'caliber': a.get('caliber'),
        'data_asof': a.get('data_asof'),
    }
    row = (
        db.query(MarketAssetDaily)
        .filter(MarketAssetDaily.asset_key == a.get('key'), MarketAssetDaily.trade_date == trade_date)
        .first()
    )
    if row is None:
        db.add(MarketAssetDaily(asset_key=a.get('key'), trade_date=trade_date, **values, source='akshare'))
    else:
        for k, v in values.items():
            setattr(row, k, v)


def _upsert_bond(db: Session, bond: Dict[str, Any]) -> None:
    trade_date = _to_date(bond.get('trade_date'))
    values = {
        'cn_10y': bond.get('cn_10y'),
        'cn_10y_change_bp': bond.get('cn_10y_change_bp'),
        'us_10y': bond.get('us_10y'),
        'us_10y_change_bp': bond.get('us_10y_change_bp'),
    }
    row = db.query(MarketBondYieldDaily).filter(MarketBondYieldDaily.trade_date == trade_date).first()
    if row is None:
        db.add(MarketBondYieldDaily(trade_date=trade_date, **values, source='akshare'))
    else:
        for k, v in values.items():
            setattr(row, k, v)
