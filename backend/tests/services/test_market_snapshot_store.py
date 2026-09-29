# -*- coding: utf-8 -*-
"""探市大类资产日频快照读写层单测（#1460 P1）。

不依赖网络：直接构造 overview 结构落库再读回，验证：
1. 两张新表注册在 market 域（写读同一库的前提）；
2. save → load 往返结构与实时路径一致（含分位 / 债券轨 / 软占位）；
3. 库里缺任一品种 → load 返回 None（交给实时兜底，绝不返回半份数据）；
4. 同日重复写入幂等（upsert，不产生重复行）。
"""

from datetime import date

from app.core.db_factory import DATA_DOMAIN_REGISTRY, DOMAIN_MARKET
from app.domains.market.models import MarketAssetDaily
from app.services.market_service import ASSET_CONFIG
from app.services.market_snapshot_store import load_overview_from_db, save_overview_to_db

TRADE_DATE = '2026-09-23'


def test_market_snapshot_tables_registered_as_market():
    """新表必须归 market 域：否则路由会把它们写进应用库，读侧（market_session）读不到。"""
    assert DATA_DOMAIN_REGISTRY.get('market_asset_daily') == DOMAIN_MARKET
    assert DATA_DOMAIN_REGISTRY.get('market_bond_yield_daily') == DOMAIN_MARKET


def _fake_overview(skip_key: str = None) -> dict:
    """按 ASSET_CONFIG 构造一份全量 overview（可跳过某个 key 以模拟不完整）。"""
    groups: dict = {}
    for a in ASSET_CONFIG:
        if skip_key and a['key'] == skip_key:
            continue
        groups.setdefault(a['category'], []).append(
            {
                'key': a['key'],
                'name': a['name'],
                'category': a['category'],
                'available': True,
                'change_pct': 0.85,
                'trade_date': TRADE_DATE,
                'data_asof': f'{TRADE_DATE} 15:00:00',
                'position': {'percentile': 41.2, 'label': '适中', 'basis': '价格分位', 'window': 500},
                'anomaly': None,
                'caliber': a.get('caliber'),
                'reason': None,
            }
        )
    return {
        'groups': [{'category': c, 'assets': assets} for c, assets in groups.items()],
        'bond_yield': {
            'cn_10y': 1.85,
            'cn_10y_change_bp': -2.3,
            'us_10y': 4.12,
            'us_10y_change_bp': 1.1,
            'trade_date': TRADE_DATE,
        },
    }


def test_save_then_load_roundtrip(db):
    save_overview_to_db(db, _fake_overview())
    db.commit()

    loaded = load_overview_from_db(db)
    assert loaded is not None
    assert loaded['from_snapshot'] is True
    assert loaded['snapshot_date'] == TRADE_DATE

    total = sum(len(g['assets']) for g in loaded['groups'])
    assert total == len(ASSET_CONFIG)

    first = loaded['groups'][0]['assets'][0]
    assert first['change_pct'] == 0.85
    assert first['position']['percentile'] == 41.2
    assert first['trade_date'] == TRADE_DATE
    assert loaded['bond_yield']['cn_10y'] == 1.85
    assert loaded['unavailable_count'] == 0


def test_load_returns_none_when_incomplete(db):
    """缺任一品种 → 返回 None，让视图走实时兜底，而不是给用户半份数据。"""
    save_overview_to_db(db, _fake_overview(skip_key=ASSET_CONFIG[0]['key']))
    db.commit()
    assert load_overview_from_db(db) is None


def test_load_returns_none_when_empty(db):
    assert load_overview_from_db(db) is None


def test_soft_placeholder_persisted(db):
    """软占位（available=false + reason）要原样落库并读回，不能伪装成真实值。"""
    overview = _fake_overview()
    target = overview['groups'][0]['assets'][0]
    target.update({'available': False, 'reason': '取数超时（>20s），已降级', 'change_pct': None})
    save_overview_to_db(db, overview)
    db.commit()

    loaded = load_overview_from_db(db)
    assert loaded is not None  # 软占位也是「完整的一天」，不应触发兜底
    item = next(a for g in loaded['groups'] for a in g['assets'] if a['key'] == target['key'])
    assert item['available'] is False
    assert item['reason'] == '取数超时（>20s），已降级'
    assert item['change_pct'] is None
    assert loaded['unavailable_count'] == 1


def test_upsert_same_day_is_idempotent(db):
    save_overview_to_db(db, _fake_overview())
    db.commit()

    again = _fake_overview()
    again['groups'][0]['assets'][0]['change_pct'] = 1.23
    save_overview_to_db(db, again)
    db.commit()

    rows = db.query(MarketAssetDaily).filter(MarketAssetDaily.trade_date == date(2026, 9, 23)).all()
    assert len(rows) == len(ASSET_CONFIG)  # 重复写入只覆盖，不增行

    loaded = load_overview_from_db(db)
    assert loaded['groups'][0]['assets'][0]['change_pct'] == 1.23
