# -*- coding: utf-8 -*-
"""fund_utils 货基判定单测：#863 显式 asset_type 优先于兜底解析。

覆盖 AI review 建议的场景：asset_type 为 None / 'money_fund' / 其它显式类型 / 空串。
显式类型分支不触网（不查 market 名录）；仅空白类型走兜底解析（此处 monkeypatch 屏蔽 DB）。
"""

from app.services.fund_utils import is_money_fund_symbol


def test_explicit_money_fund_type_wins(monkeypatch):
    """显式 'money_fund' → True，且不触发兜底解析（避免覆盖显式分类）。"""
    monkeypatch.setattr('app.services.fund_utils.resolve_money_fund_flags', lambda codes: {})
    assert is_money_fund_symbol('000001', 'money_fund') is True


def test_explicit_other_type_returns_false(monkeypatch):
    """显式非货基类型（如 'bond'）→ False，不落入兜底解析误判。"""
    monkeypatch.setattr('app.services.fund_utils.resolve_money_fund_flags', lambda codes: {})
    assert is_money_fund_symbol('000001', 'bond') is False
    assert is_money_fund_symbol('000001', 'stock') is False


def test_blank_asset_type_falls_back_to_resolution(monkeypatch):
    """空串（falsy）→ 走名录/兜底解析。"""
    captured = {}

    def fake_resolve(codes):
        captured['codes'] = codes
        return {codes[0]: True}

    monkeypatch.setattr('app.services.fund_utils.resolve_money_fund_flags', fake_resolve)
    assert is_money_fund_symbol('000001', '') is True
    assert captured['codes'] == ['000001']


def test_none_asset_type_falls_back_to_resolution(monkeypatch):
    """None（缺省）→ 走名录/兜底解析；未命中返回 False。"""
    monkeypatch.setattr(
        'app.services.fund_utils.resolve_money_fund_flags',
        lambda codes: {codes[0]: False},
    )
    assert is_money_fund_symbol('000001') is False
