# -*- coding: utf-8 -*-
"""诊断引擎取数层的单测（#2603）。

规则层在 `test_rules.py`（纯函数喂快照），这里只测**取数与降级**：

1. 风格暴露取数抛异常 → 该维度置空，**其余维度照常取**（一条数据源挂掉不该让整页提示消失）；
2. 取到但没有风格箱数据 → 同样置空，**不拿空数组冒充「风格均衡」**；
3. 快照摘要里的风格覆盖率与实际取数一致（前端空态文案靠它区分两种「没有提示」）。
"""

import pytest

from app.services.insight import engine


def test_风格取数异常时降级为空(monkeypatch, db):
    def _boom(*args, **kwargs):
        raise RuntimeError('上游挂了')

    monkeypatch.setattr(engine, 'portfolio_style_exposure', _boom)
    snapshot = engine.build_snapshot(db, family_id=1)
    assert snapshot['style_exposure'] is None
    # 其余维度不受影响：行业/最近交易日仍取到了值或 None，但键都在
    assert 'top_industry' in snapshot
    assert 'penetration_ratio' in snapshot
    assert 'latest_day' in snapshot


def test_风格数据为空时降级为空(monkeypatch, db):
    monkeypatch.setattr(engine, 'portfolio_style_exposure', lambda *a, **k: {'styles': [], 'coverage_pct': 0})
    snapshot = engine.build_snapshot(db, family_id=1)
    assert snapshot['style_exposure'] is None


def test_风格覆盖率为零时不冒充有风格数据(monkeypatch, db):
    # 有 styles 但覆盖率 0：说明有箱体的持仓市值占比为 0，口径上等于「算不出来」
    monkeypatch.setattr(
        engine,
        'portfolio_style_exposure',
        lambda *a, **k: {'styles': [{'style_name': '大盘成长', 'value': 100.0}], 'coverage_pct': 0},
    )
    snapshot = engine.build_snapshot(db, family_id=1)
    # styles 非空 → 维度保留，但覆盖率如实为 0（规则侧靠覆盖率门槛挡住）
    assert snapshot['style_exposure'] is not None
    assert snapshot['style_exposure']['coverage_pct'] == 0


def test_快照摘要带风格覆盖率(monkeypatch, db):
    monkeypatch.setattr(
        engine,
        'portfolio_style_exposure',
        lambda *a, **k: {
            'styles': [{'style_name': '大盘成长', 'value': 55.0}],
            'coverage_pct': 77.25,
            'fund_count': 3,
        },
    )
    result = engine.build_tips(db, family_id=1)
    assert result['snapshot']['style_coverage_pct'] == pytest.approx(77.25)


def test_风格维度缺失时摘要覆盖率如实为零(monkeypatch, db):
    monkeypatch.setattr(engine, 'portfolio_style_exposure', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('挂了')))
    result = engine.build_tips(db, family_id=1)
    assert result['snapshot']['style_coverage_pct'] == 0
