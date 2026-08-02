# -*- coding: utf-8 -*-
"""
temperature service 层补充测试（离线、确定性）：覆盖
  - get_history：单值分支 / 复合分支（composite_temperature）/ days>365 截断
  - get_multi_items：最新日期 / 指定日期 / 空源
  - get_overview：multi 分支（bias / industry_crowding 多维列表聚合）
不依赖真实外部数据源。
"""

from datetime import date, timedelta

from app.domains.temperature.models import (
    MarketComposite,
    MarketMultiItem,
    MarketSingleValue,
)
from app.services.thermometer.service import TemperatureService


def test_get_history_single_value(db):
    base = date.today()
    for i in range(5):
        db.add(
            MarketSingleValue(
                source='eastmoney_volume',
                name='全市场成交额',
                value=1000.0 + i,
                label='温和',
                unit='亿',
                collected_at=base - timedelta(days=i),
            )
        )
    db.commit()

    result = TemperatureService.get_history('eastmoney_volume', days=90)
    assert result['source'] == 'eastmoney_volume'
    assert len(result['dates']) == 5
    assert len(result['values']) == 5
    assert len(result['labels']) == 5
    # 按日期升序返回
    assert result['dates'] == sorted(result['dates'])
    # 最早日期排在首位（i=4 -> base-4）
    assert result['dates'][0] == (base - timedelta(days=4)).strftime('%Y-%m-%d')
    # 数值与日期对应（升序时最早日期对应 value=1004.0）
    assert result['values'][0] == 1004.0


def test_get_history_composite_temperature(db):
    db.add(
        MarketComposite(
            source='composite_temperature',
            collected_at=date.today(),
            data={'value': 55.0, 'level': '适中'},
        )
    )
    db.commit()

    result = TemperatureService.get_history('composite_temperature', days=90)
    assert result['source'] == 'composite_temperature'
    assert result['dates'] == [date.today().strftime('%Y-%m-%d')]
    assert result['values'] == [55.0]
    assert result['levels'] == ['适中']


def test_get_history_days_capped_at_365(db):
    # days>365 时被截断为 365，返回条数不超过 365
    base = date.today()
    for i in range(366):
        db.add(
            MarketSingleValue(
                source='eastmoney_volume',
                name='成交额',
                value=float(i),
                collected_at=base - timedelta(days=i),
            )
        )
    db.commit()

    result = TemperatureService.get_history('eastmoney_volume', days=999)
    assert len(result['dates']) == 365


def test_get_multi_items_latest_when_no_date(db):
    base = date.today()
    # 旧日期一批
    for code in ['A', 'B']:
        db.add(
            MarketMultiItem(
                source='bias',
                item_type='industry',
                item_code=code,
                item_name=code,
                data={'bias': 1.0},
                collected_at=base - timedelta(days=3),
            )
        )
    # 最新日期一批（含一个 stale）
    for code, stale in [('A', False), ('B', True)]:
        db.add(
            MarketMultiItem(
                source='bias',
                item_type='industry',
                item_code=code,
                item_name=code,
                data={'bias': 2.0},
                collected_at=base,
                stale=stale,
            )
        )
    db.commit()

    result = TemperatureService.get_multi_items('bias')
    assert result['source'] == 'bias'
    assert result['date'] == base.strftime('%Y-%m-%d')
    assert len(result['items']) == 2
    # 顶层 stale：任一记录滞后即整体滞后
    assert result['stale'] is True
    assert {it['item_code'] for it in result['items']} == {'A', 'B'}


def test_get_multi_items_by_specific_date(db):
    base = date.today()
    db.add(
        MarketMultiItem(
            source='bias',
            item_type='industry',
            item_code='A',
            item_name='A',
            data={'bias': 1.0},
            collected_at=base - timedelta(days=5),
        )
    )
    db.add(
        MarketMultiItem(
            source='bias',
            item_type='industry',
            item_code='A',
            item_name='A',
            data={'bias': 2.0},
            collected_at=base,
        )
    )
    db.commit()

    result = TemperatureService.get_multi_items('bias', base - timedelta(days=5))
    assert result['date'] == (base - timedelta(days=5)).strftime('%Y-%m-%d')
    assert len(result['items']) == 1
    assert result['items'][0]['data']['bias'] == 1.0
    assert result['stale'] is False


def test_get_multi_items_empty_source(db):
    result = TemperatureService.get_multi_items('sector_flow')
    assert result == {'source': 'sector_flow', 'date': None, 'items': [], 'stale': False}


def test_get_overview_multi_branch(db):
    db.add(
        MarketMultiItem(
            source='bias',
            item_type='industry',
            item_code='801010',
            item_name='农林牧渔',
            data={'bias': 3.5},
            collected_at=date.today(),
        )
    )
    db.add(
        MarketMultiItem(
            source='industry_crowding',
            item_type='industry',
            item_code='801020',
            item_name='采掘',
            data={'crowding': 0.8},
            collected_at=date.today(),
        )
    )
    db.commit()

    data = TemperatureService.get_overview()
    multi = data.get('multi', {})
    assert 'bias' in multi
    assert 'industry_crowding' in multi
    assert any(it['item_code'] == '801010' for it in multi['bias'])
    # 每条记录含标准字段
    for it in multi['bias']:
        assert {'item_type', 'item_code', 'item_name', 'data', 'stale'} <= set(it)
