# -*- coding: utf-8 -*-
"""诊断链路收口测试（#2225 验收第 3/4 条）——零外部请求 + 无建议措辞。

全链路（诊断 + 行为画像）跑一遍，socket 探针全程挂起：
任何 connect / create_connection 尝试即失败，证明「诊断零外部请求」。
"""

import socket
from datetime import date, datetime, timedelta

import pytest

from app.services.strategy_engine.data_provider import DataProvider
from app.services.strategy_engine.diagnosis import behavior_profiles, diagnose_holdings

D0 = date(2025, 1, 1)


@pytest.fixture
def no_network(monkeypatch):
    """全程禁止 socket 连接：#2225 验收「诊断零外部请求（可用测试证明）」。"""

    def _boom(*args, **kwargs):
        raise AssertionError('诊断链路不得发起网络请求')

    monkeypatch.setattr(socket.socket, 'connect', _boom)
    monkeypatch.setattr(socket, 'create_connection', _boom)


def _mk_fund_type(db, name: str) -> int:
    from app.domains.funds.models import FundType

    ft = FundType(name=name)
    db.add(ft)
    db.flush()
    return ft.id


def _mk_fund(db, code: str, type_id: int) -> None:
    from app.domains.funds.models import Fund

    db.add(Fund(fund_code=code, name=f'基金{code}', fund_type_id=type_id))
    db.flush()


def _mk_worth(db, code: str, day: date, nav: float) -> None:
    from app.domains.funds.models import DailyWorth

    db.add(DailyWorth(fund_code=code, date=day, unit_nav=nav))
    db.flush()


def _seed(db, make_position, make_transaction, symbol: str = '000001'):
    """造一个「涨了又卖」的持仓：覆盖诊断 + 行为画像双侧路径。"""
    type_id = _mk_fund_type(db, '股票型')
    _mk_fund(db, symbol, type_id)
    for i in range(260):
        _mk_worth(db, symbol, D0 - timedelta(days=200) + timedelta(days=i), 1.0 + i * (1.59 / 259))
    pos = make_position(
        symbol=symbol,
        name='华夏成长',
        asset_type='fund',
        quantity=1000.0,
        avg_price=1.0,
        account_name='测试账户',
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        symbol=symbol,
        quantity=1000.0,
        price=1.0,
        trade_date=datetime(2025, 1, 1),
        confirm_date=D0,
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='sell',
        symbol=symbol,
        quantity=1000.0,
        price=1.20,
        trade_date=datetime(2025, 1, 21),
        confirm_date=D0 + timedelta(days=20),
    )
    return pos


def test_diagnosis_and_behavior_no_network(app, db, make_position, make_transaction, no_network):
    """全链路零外部请求（#2225 验收第 4 条）。"""
    _seed(db, make_position, make_transaction)
    provider = DataProvider(db)

    holdings = diagnose_holdings(provider, family_id=1)
    assert holdings['holding_count'] >= 1
    assert holdings['items'][0]['data_sufficient'] is True

    profiles = behavior_profiles(provider, family_id=1)
    assert profiles['profiles']
    # 买入侧三指标 + 账户层对照均在（#2225 验收第 2 条：行为画像 + 与买入持有收益差）
    profile = profiles['profiles'][0]
    assert profile['forward_return'] is not None
    assert profiles['summary']['actual_vs_hold'] is not None


def test_diagnosis_output_no_advice_wording(app, db, make_position, make_transaction, no_network):
    """全链路措辞检查（#2225 验收第 3 条）：输出不含「建议买入/卖出」类表述。"""
    _seed(db, make_position, make_transaction)
    provider = DataProvider(db)

    banned = ('建议买入', '建议卖出', '应该买', '应该卖', '可以买入', '可以卖出', '推荐买', '推荐卖')
    texts: list[str] = []

    def _collect(obj):
        if isinstance(obj, str):
            texts.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _collect(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                _collect(v)

    _collect(diagnose_holdings(provider, family_id=1))
    _collect(behavior_profiles(provider, family_id=1))
    assert texts, '应收集到输出文案'
    for text in texts:
        for word in banned:
            assert word not in text, f'输出含建议类措辞: {text!r}'


def test_network_probe_actually_bites(monkeypatch, no_network):
    """探针自检（反向验证）：链路若真发网络请求，探针必须抓住。

    没有这一条，「零外部请求」的证明可能是探针根本没挂对位置的空话。
    """
    import socket as _socket

    from app.services.strategy_engine.data_provider import DataProvider

    def _leaky_nav_series(self, symbol, limit=260):
        conn = _socket.create_connection(('feedback.duoduobei.com', 443), timeout=5)
        conn.close()
        return ()

    monkeypatch.setattr(DataProvider, 'nav_series', _leaky_nav_series)

    from app.services.strategy_engine.diagnosis import diagnose_symbol

    # diagnose_symbol 不查 holdings，直接走 nav_series——泄漏点必经之路
    with pytest.raises(AssertionError, match='网络请求'):
        diagnose_symbol(DataProvider(_socket.socket()), symbol='000001')
