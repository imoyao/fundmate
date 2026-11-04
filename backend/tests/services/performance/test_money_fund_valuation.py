# -*- coding: utf-8 -*-
"""#2848：货基市值必须按面值 1.0 计价，不能走 nav 查询。

货基的 `asset_type` 也是 `'fund'`，但每份净值恒为 1.0000 元、收益以「万份收益」
落在 `money_fund_daily_worth`，**从不进 nav 表**。历史实现落到 fund 分支去 nav 取价，
拿到 0.0 → 整块市值凭空消失（真实库 20 行货基 23,249.40 元只算出 33.68 元）。

这组用例的判据是「市值非 0」，不是「有没有抛异常」——原实现不报错、只是静默返回 0，
所以只断言「能跑通」等于没测。
"""

import pytest

from app.domains.positions.models import Position
from app.services.performance.calculators import (
    MONEY_FUND_FACE_VALUE,
    _batch_get_position_values,
    _exclude_cash_equivalent_positions,
    _get_position_current_value,
)


def _patch_nav(monkeypatch, nav_map):
    """把批量 nav 查询打桩成固定结果（避免用例依赖库里的净值表）。"""
    monkeypatch.setattr(
        'app.services.performance.calculators.NavService.get_latest_navs',
        staticmethod(lambda *args, **kwargs: dict(nav_map)),
    )


def test_money_fund_valued_at_face_value_when_nav_missing(db, make_position, monkeypatch):
    """nav 表无该代码（货基的真实情况）：市值 = 份额 × 1.0，不是 0。"""
    _patch_nav(monkeypatch, {})
    pos = make_position(
        symbol='026029',
        name='银河水星现金添利货币市场基金',
        account_name='货基账户',
        asset_type='fund',
        is_money_fund=True,
        quantity=22757.85,
        current_price=1.0,
    )

    values = _batch_get_position_values(db, [pos])

    assert values[pos.id] == pytest.approx(22757.85, abs=0.01)


def test_money_fund_ignores_stale_nav_record(db, make_position, monkeypatch):
    """nav 表若碰巧有该货基的残留记录（错表残留，见 #1554），仍以面值为准。"""
    _patch_nav(monkeypatch, {'026029': 1.2345})
    pos = make_position(
        symbol='026029',
        name='银河水星现金添利货币市场基金',
        account_name='货基账户',
        asset_type='fund',
        is_money_fund=True,
        quantity=100,
        current_price=1.0,
    )

    values = _batch_get_position_values(db, [pos])

    assert values[pos.id] == pytest.approx(100.0, abs=0.01)


def test_money_fund_asset_type_without_flag_still_face_value(db, make_position, monkeypatch):
    """`asset_type='money_fund'` 但 `is_money_fund` 为 False（历史漏回填）也按面值。

    判定刻意取「asset_type 或 flag 任一成立」，与 position_price_job 的价格回写同口径；
    若这里退回 nav，会出现「价格按面值写对了、估值又读丢了」的错位。
    """
    _patch_nav(monkeypatch, {})
    pos = make_position(
        symbol='000620',
        name='易方达现金增利货币',
        account_name='货基账户',
        asset_type='money_fund',
        is_money_fund=False,
        quantity=500,
        current_price=1.0,
    )

    values = _batch_get_position_values(db, [pos])

    assert values[pos.id] == pytest.approx(500.0, abs=0.01)


def test_ordinary_fund_still_uses_nav(db, make_position, monkeypatch):
    """非货基普通基金不受影响：仍按 nav 计价（面值兜底不能外溢）。"""
    _patch_nav(monkeypatch, {'110022': 2.5})
    pos = make_position(
        symbol='110022',
        name='易方达消费行业',
        account_name='普通基金账户',
        asset_type='fund',
        is_money_fund=False,
        quantity=1000,
        current_price=1.0,
    )

    values = _batch_get_position_values(db, [pos])

    assert values[pos.id] == pytest.approx(2500.0, abs=0.01)


def test_single_position_path_also_face_value(db, make_position, monkeypatch):
    """单持仓路径（组合页卡片）与批量路径同口径，否则同一只货基两页两个数。"""
    pos = make_position(
        symbol='026029',
        name='银河水星现金添利货币市场基金',
        account_name='货基账户',
        asset_type='fund',
        is_money_fund=True,
        quantity=236.14,
        current_price=1.0,
    )

    value = _get_position_current_value(db, pos)

    assert value == pytest.approx(236.14, abs=0.01)


def test_face_value_constant_is_one_yuan():
    """面值常量是估值唯一依据，改动它等于全站货基市值平移，须有显式理由。"""
    assert MONEY_FUND_FACE_VALUE == 1.0


def test_exclude_filter_keeps_null_flag_positions(db, make_position):
    """「剔除现金」的 WHERE 条件不能误伤 `is_money_fund` 为 NULL 的普通持仓。

    这是 SQL 三值逻辑的经典坑：若写成 `is_money_fund != True`，NULL 行比较结果是
    NULL、被当成 false 过滤掉，真实库里 102 行未判定标记的普通持仓会集体消失。
    必须走 `IS NOT 1`（`.isnot()`）。用例同时钉住「货基被剔除」这个正向。
    """
    ordinary = make_position(
        symbol='110022',
        name='易方达消费行业',
        account_name='普通基金账户',
        asset_type='fund',
        is_money_fund=None,
        quantity=1000,
        current_price=2.0,
    )
    money_fund = make_position(
        symbol='026029',
        name='银河水星现金添利货币市场基金',
        account_name='货基账户',
        asset_type='fund',
        is_money_fund=True,
        quantity=500,
        current_price=1.0,
    )

    kept = {p.id for p in db.query(Position).filter(Position.quantity > 0, *_exclude_cash_equivalent_positions()).all()}

    assert ordinary.id in kept, '未判定标记（NULL）的普通持仓被误排除'
    assert money_fund.id not in kept, '货基本应被剔除口径排除'
