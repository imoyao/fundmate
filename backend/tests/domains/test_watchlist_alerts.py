# -*- coding: utf-8 -*-
"""自选提醒：家庭设置 / 逐标的 CRUD / 扫描投递契约。

分层：
- 触发判据的纯函数回归在 `tests/services/test_watchlist_alert_rules.py`；
- 本文件测编排与接口：多租户隔离、一次性语义、按行情日期去重、按周去重。
"""

from datetime import date, timedelta

import pytest

from app.domains.notification.models import Notification
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.domains.watchlist.models import WatchlistAlert, WatchlistAlertSettings, WatchlistItem
from app.services.alerts import service as svc

BASE = '/api/watchlist'


def _make_item(db, symbol='SH600519', name='贵州茅台', family_id=1, asset_type='stock', venue='EXCHANGE'):
    item = WatchlistItem(symbol=symbol, name=name, family_id=family_id, asset_type=asset_type, venue=venue)
    db.add(item)
    db.commit()  # 请求会话是另一个连接，必须提交才可见
    return item


def _make_prices(db, symbol='SH600519', closes=(('2026-11-06', 1600.0), ('2026-11-07', 1500.0))):
    """造价格历史：closes 按日期升序给 (iso_date, close)。"""
    security = db.query(Security).filter(Security.symbol == symbol).first()
    if security is None:
        security = Security(symbol=symbol, name='测试证券', market='CN_A', type='stock')
        db.add(security)
        db.flush()
    for iso_day, close in closes:
        db.add(
            PriceHistory(
                security_id=security.id,
                symbol=symbol,
                trade_date=date.fromisoformat(iso_day),
                close=close,
            )
        )
    db.commit()


# ── 家庭设置 ──


def test_settings_defaults_are_not_persisted(client, db):
    """没有任何配置行时，GET 返回代码默认值且标 is_customized=False。"""
    resp = client.get(f'{BASE}/alerts/settings/')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    by_type = {item['alert_type']: item for item in data['items']}
    assert by_type['CHANGE_PCT']['is_enabled'] is False
    assert by_type['CHANGE_PCT']['is_customized'] is False
    assert by_type['DRAWDOWN']['window_days'] == 60
    assert db.query(WatchlistAlertSettings).count() == 0


def test_settings_update_roundtrip(client, db):
    """PUT 落库后可读回，且只影响提交的类型。"""
    resp = client.put(
        f'{BASE}/alerts/settings/',
        json={
            'items': [
                {'alert_type': 'CHANGE_PCT', 'is_enabled': True, 'threshold_value': 3.5},
                {'alert_type': 'DRAWDOWN', 'is_enabled': True, 'threshold_value': 12, 'window_days': 120},
            ]
        },
    )
    assert resp.status_code == 200
    by_type = {item['alert_type']: item for item in resp.get_json()['data']['items']}
    assert by_type['CHANGE_PCT']['threshold_value'] == 3.5
    assert by_type['CHANGE_PCT']['is_customized'] is True
    assert by_type['DRAWDOWN']['window_days'] == 120
    assert db.query(WatchlistAlertSettings).count() == 2


@pytest.mark.parametrize(
    'payload',
    [
        {'alert_type': 'CHANGE_PCT', 'is_enabled': True, 'threshold_value': 0.1},  # 低于下界
        {'alert_type': 'CHANGE_PCT', 'is_enabled': True, 'threshold_value': 99},  # 高于上界
        {'alert_type': 'PRICE_UP', 'is_enabled': True, 'threshold_value': 5},  # 到价不设家庭默认
        {'alert_type': 'DRAWDOWN', 'is_enabled': True, 'threshold_value': 10, 'window_days': 2},
    ],
)
def test_settings_rejects_out_of_range(client, payload):
    """越界一律 422 + 统一信封（error_code=1001），不静默回落默认值。"""
    resp = client.put(f'{BASE}/alerts/settings/', json={'items': [payload]})
    assert resp.status_code == 422
    body = resp.get_json()
    assert body['error_code'] == 1001
    assert body['message']


# ── 逐标的规则 + 多租户隔离 ──


def test_item_alert_crud(client, db):
    item = _make_item(db)
    resp = client.post(
        f'{BASE}/items/{item.id}/alerts/',
        json={'alert_type': 'PRICE_UP', 'threshold_value': 1800},
    )
    assert resp.status_code == 200
    created = resp.get_json()['data']
    assert created['alert_type'] == 'PRICE_UP'
    assert created['is_active'] is True

    # 再次提交同类型 → 覆盖而不是新增
    again = client.post(
        f'{BASE}/items/{item.id}/alerts/',
        json={'alert_type': 'PRICE_UP', 'threshold_value': 1750},
    )
    assert again.status_code == 200
    assert again.get_json()['data']['id'] == created['id']
    assert db.query(WatchlistAlert).count() == 1

    patched = client.patch(f'{BASE}/alerts/{created["id"]}/', json={'is_active': False})
    assert patched.status_code == 200
    assert patched.get_json()['data']['is_active'] is False

    detail = client.get(f'{BASE}/items/{item.id}/alerts/')
    assert detail.status_code == 200
    body = detail.get_json()['data']
    assert body['item']['symbol'] == 'SH600519'
    assert len(body['rules']) == 1
    assert body['effective']['CHANGE_PCT']['source'] == 'off'

    deleted = client.delete(f'{BASE}/alerts/{created["id"]}/')
    assert deleted.status_code == 200
    assert db.query(WatchlistAlert).count() == 0


def test_cross_family_access_is_404(client, db):
    """他家庭的标的与规则一律 404（不泄漏「存在但不属于你」）。"""
    other = _make_item(db, symbol='SZ000001', name='平安银行', family_id=2)
    other_rule = WatchlistAlert(item_id=other.id, alert_type='PRICE_DOWN', threshold_value=9.0)
    db.add(other_rule)
    db.commit()

    assert client.get(f'{BASE}/items/{other.id}/alerts/').status_code == 404
    assert (
        client.post(
            f'{BASE}/items/{other.id}/alerts/', json={'alert_type': 'PRICE_UP', 'threshold_value': 10}
        ).status_code
        == 404
    )
    assert client.patch(f'{BASE}/alerts/{other_rule.id}/', json={'is_active': False}).status_code == 404
    assert client.delete(f'{BASE}/alerts/{other_rule.id}/').status_code == 404


def test_item_alert_rejects_bad_threshold(client, db):
    item = _make_item(db)
    resp = client.post(f'{BASE}/items/{item.id}/alerts/', json={'alert_type': 'CHANGE_PCT', 'threshold_value': 200})
    assert resp.status_code == 422
    assert resp.get_json()['error_code'] == 1001


# ── 扫描投递 ──


def test_price_alert_fires_once_then_auto_disables(client, db):
    item = _make_item(db)
    db.add(WatchlistAlert(item_id=item.id, alert_type='PRICE_UP', threshold_value=1500.0))
    _make_prices(db, closes=(('2026-11-06', 1600.0), ('2026-11-07', 1520.0)))
    db.flush()

    first = svc.refresh_alerts(db, 1)
    assert first['created'] == 1
    note = db.query(Notification).filter(Notification.family_id == 1).one()
    assert note.category == 'watchlist'
    assert note.level == 'P1'
    assert '到价提醒' in note.title

    rule = db.query(WatchlistAlert).one()
    assert rule.is_active is False
    assert rule.last_triggered_at is not None

    # 已自动停用 → 再扫不产生新消息
    assert svc.refresh_alerts(db, 1)['created'] == 0


def test_pct_alert_dedups_by_quote_date_not_today(client, db):
    """跌幅去重锚点是行情日期：同一份行情跨天不重复提醒。"""
    item = _make_item(db)
    db.add(WatchlistAlert(item_id=item.id, alert_type='CHANGE_PCT', threshold_value=5.0))
    _make_prices(db, closes=(('2026-11-06', 100.0), ('2026-11-07', 94.0)))
    db.flush()

    assert svc.refresh_alerts(db, 1)['created'] == 1
    # 换一个「今天」仍然不该重复
    assert svc.refresh_alerts(db, 1, today=date(2026, 11, 8))['created'] == 0
    assert svc.refresh_alerts(db, 1, today=date(2026, 11, 9))['created'] == 0

    # 新的下跌行情（新日期）→ 新的提醒
    _make_prices(db, closes=(('2026-11-10', 88.0),))
    assert svc.refresh_alerts(db, 1)['created'] == 1


def test_pct_alert_ignores_rise(client, db):
    """只报下跌：涨 8% 不触发「跌幅提醒」。"""
    item = _make_item(db)
    db.add(WatchlistAlert(item_id=item.id, alert_type='CHANGE_PCT', threshold_value=5.0))
    _make_prices(db, closes=(('2026-11-06', 100.0), ('2026-11-07', 108.0)))
    db.flush()
    assert svc.refresh_alerts(db, 1)['created'] == 0


def test_family_default_applies_to_all_items_and_item_rule_overrides(client, db):
    """家庭默认对全部自选生效；单标的规则覆盖阈值。"""
    item_a = _make_item(db, symbol='SH600519', name='茅台')
    item_b = _make_item(db, symbol='SZ000001', name='平安')
    db.add(WatchlistAlert(item_id=item_b.id, alert_type='CHANGE_PCT', threshold_value=9.0))
    db.add(WatchlistAlertSettings(family_id=1, alert_type='CHANGE_PCT', is_enabled=True, threshold_value=5.0))
    _make_prices(db, symbol='SH600519', closes=(('2026-11-06', 100.0), ('2026-11-07', 94.0)))
    _make_prices(db, symbol='SZ000001', closes=(('2026-11-06', 10.0), ('2026-11-07', 9.4)))
    db.flush()

    stats = svc.refresh_alerts(db, 1)
    # 茅台走家庭默认 5% → 触发；平安有自己的 9% 线 → 不触发
    assert stats['created'] == 1
    note = db.query(Notification).one()
    assert 'SH600519' in note.source_key


def test_drawdown_alert_weekly_dedup(client, db):
    """回撤按「周」去重：同一周内只提醒一次，跨周新行情再提醒。"""
    item = _make_item(db)
    db.add(WatchlistAlert(item_id=item.id, alert_type='DRAWDOWN', threshold_value=10.0))
    db.add(
        WatchlistAlertSettings(
            family_id=1, alert_type='DRAWDOWN', is_enabled=False, threshold_value=10.0, window_days=60
        )
    )
    _make_prices(db, closes=(('2026-11-02', 100.0), ('2026-11-03', 85.0)))
    db.flush()

    assert svc.refresh_alerts(db, 1)['created'] == 1
    assert svc.refresh_alerts(db, 1)['created'] == 0

    # 下一周的行情（仍是破线状态）→ 新的一周，允许再提醒一次
    _make_prices(db, closes=(('2026-11-10', 84.0),))
    assert svc.refresh_alerts(db, 1)['created'] == 1


def test_no_rules_no_scan(client, db):
    """没有任何提醒配置时扫描直接短路，不查行情、不写通知。"""
    _make_item(db)
    _make_prices(db, closes=(('2026-11-06', 100.0), ('2026-11-07', 90.0)))
    db.flush()
    stats = svc.refresh_alerts(db, 1)
    assert stats == {'evaluated': 0, 'created': 0, 'triggered': []}
    assert db.query(Notification).count() == 0


def test_scan_only_touches_own_family(client, db):
    """扫描只对本家庭生效：他家庭的规则不会被触发、不会写他家庭的通知。"""
    mine = _make_item(db, symbol='SH600519', family_id=1)
    other = _make_item(db, symbol='SZ000001', name='平安', family_id=2)
    db.add(WatchlistAlert(item_id=other.id, alert_type='PRICE_UP', threshold_value=9.0))
    _make_prices(db, symbol='SH600519', closes=(('2026-11-06', 1600.0), ('2026-11-07', 1500.0)))
    _make_prices(db, symbol='SZ000001', closes=(('2026-11-06', 10.0), ('2026-11-07', 9.5)))
    db.flush()

    assert svc.refresh_alerts(db, 1)['created'] == 0
    assert db.query(Notification).count() == 0
    assert db.query(WatchlistAlert).filter(WatchlistAlert.item_id == other.id).one().is_active is True
    assert db.query(WatchlistAlert).filter(WatchlistAlert.item_id == mine.id).count() == 0


def test_quote_window_high_limits_false_positive(client, db):
    """窗口高点之外的旧高点不参与回撤：窗口 5 日时，半年前的高点不算。"""
    item = _make_item(db)
    db.add(WatchlistAlert(item_id=item.id, alert_type='DRAWDOWN', threshold_value=10.0))
    db.add(
        WatchlistAlertSettings(
            family_id=1, alert_type='DRAWDOWN', is_enabled=False, threshold_value=10.0, window_days=5
        )
    )
    old_day = (date.today() - timedelta(days=200)).isoformat()
    recent = (date.today() - timedelta(days=2)).isoformat()
    _make_prices(db, closes=((old_day, 100.0), (recent, 95.0)))
    db.flush()

    assert svc.refresh_alerts(db, 1)['created'] == 0
