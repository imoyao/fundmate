# -*- coding: utf-8 -*-
"""个股估值分位服务层（#2944）：用户触达口径、代码归一、上限与显式降级。

外部取数一律 monkeypatch，不打真实 HTTP。
"""

import pytest

from app.domains.watchlist.models import WatchlistItem
from app.services import stock_valuation_service as svc
from app.services.adapters import wind_stock_valuation as wsv

# ── 代码归一 ────────────────────────────────────────────────────────────


def test_explicit_codes_normalize_and_dedup():
    """仓内 SH600519 与万得 600519.SH 是同一只；投顾组合码不许撞进股票代码空间。"""
    codes, truncated = svc.resolve_codes(None, 1, 'SH600519,600519.SH,000858.SZ,ZH012926,MGR_123')
    assert codes == ['600519.SH', '000858.SZ']
    assert truncated is False


def test_explicit_codes_reject_all_invalid():
    with pytest.raises(ValueError, match='没有可识别'):
        svc.resolve_codes(None, 1, 'ZH012926,NOT_A_CODE')


def test_explicit_codes_reject_over_limit():
    codes = ','.join(f'600{i:03d}' for i in range(svc.MAX_CODES + 1))
    with pytest.raises(ValueError, match='最多'):
        svc.resolve_codes(None, 1, codes)


# ── 用户触达口径 ────────────────────────────────────────────────────────


def test_default_scope_is_positions_union_watchlist_stocks_only(db, make_position):
    """只取 active 持仓 ∪ 自选里的 stock；ETF / 影子行 / 别家一概不进目标池。"""
    make_position(symbol='SH600519', name='贵州茅台', asset_type='stock', account_name='估值测试账户')
    make_position(symbol='SZ159915', name='创业板ETF', asset_type='etf', account_name='估值测试账户')
    make_position(
        symbol='SH601318', name='影子行', asset_type='stock', ownership_status='shadow', account_name='估值测试账户'
    )
    make_position(symbol='SH600000', name='别家的', asset_type='stock', family_id=2, account_name='估值测试账户2')
    db.add(
        WatchlistItem(symbol='SZ000858', name='五粮液', asset_type='stock', family_id=1, market='SZ', venue='EXCHANGE')
    )
    db.add(
        WatchlistItem(symbol='SZ159915', name='创业板ETF', asset_type='etf', family_id=1, market='SZ', venue='EXCHANGE')
    )
    db.commit()

    codes, truncated = svc.resolve_codes(db, 1)
    assert codes == ['000858.SZ', '600519.SH']
    assert truncated is False


def test_default_scope_empty_for_family_without_stocks(db):
    codes, truncated = svc.resolve_codes(db, 1)
    assert codes == []
    assert truncated is False


# ── 降级与出口 ──────────────────────────────────────────────────────────


def test_empty_scope_never_calls_upstream(db, monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError('没有目标代码时不应打外部')

    monkeypatch.setattr(wsv, 'fetch_stock_valuations', _boom)
    monkeypatch.setattr(wsv, 'is_available', lambda: True)
    result = svc.get_stock_valuations(db, 1)
    assert result['items'] == []
    assert result['degraded'] is False
    assert result['count'] == 0


def test_unconfigured_source_degrades_explicitly(db, monkeypatch):
    monkeypatch.setattr(wsv, 'is_available', lambda: False)
    monkeypatch.setattr(wsv, 'fetch_stock_valuations', lambda *a, **k: [])
    result = svc.get_stock_valuations(db, 1, '600519.SH')
    assert result['degraded'] is True
    assert result['warning'] == '个股估值数据源未配置'
    assert result['items'] == []


def test_upstream_failure_degrades_explicitly(db, monkeypatch):
    monkeypatch.setattr(wsv, 'is_available', lambda: True)

    def _boom(*args, **kwargs):
        raise RuntimeError('上游不可用')

    monkeypatch.setattr(wsv, 'fetch_stock_valuations', _boom)
    result = svc.get_stock_valuations(db, 1, '600519.SH')
    assert result['degraded'] is True
    assert result['warning'] == '个股估值数据源暂时不可用'
    assert result['items'] == []


def test_normal_result_carries_window_and_source(db, monkeypatch):
    row = {
        'wind_code': '600519.SH',
        'name': '贵州茅台',
        'date': '2026-11-06',
        'pe': 22.1075,
        'pb': 6.6974,
        'pe_percentile': 32.7828,
        'pb_percentile': 8.3402,
        'window': '5y',
        'source': wsv.SOURCE,
    }
    monkeypatch.setattr(wsv, 'is_available', lambda: True)
    monkeypatch.setattr(wsv, 'fetch_stock_valuations', lambda codes: [row])
    result = svc.get_stock_valuations(db, 1, '600519.SH')
    assert result['degraded'] is False
    assert result['count'] == 1
    assert result['requested'] == 1
    assert result['window'] == '5y'
    assert result['source'] == wsv.SOURCE
    assert result['items'][0]['pe_percentile'] == pytest.approx(32.7828)
