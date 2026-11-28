# -*- coding: utf-8 -*-
"""账户级收益率（`scope=ledger`）回归（#3287 B0）。

## 修的 bug

`/api/performance/xirr/` 的 `scope` 只认 position / portfolio / symbol，其余一律落到
函数末尾的 `calculate_portfolio_xirr(family_id=...)` —— 也就是**家庭级**。于是：

    GET /api/performance/xirr/?scope=ledger&ledger_id=3

返回 200、`data` 是**全家庭**的年化，而前端已经把标签改成「招商银行」。这比不传参
更坏：不仅静默错口径，还多了一个 `scope=ledger` 让调用方以为筛过了。同一端点的
`method=twr` 早有账户档（`calculate_twr_by_scope` 收 `ledger_id`），只有默认的 xirr
路径是假的——换个 method 行为就变，最难察觉。

## 覆盖

- 账户档只算该账户的流水与市值（不是家庭数）；
- 家庭 ≠ 单账户（防止「改了个寂寞」也能通过）；
- 跨家庭 id ⇒ `ValueError` → 404（`restrict_visible` 对无主行放行，不校验就会返回半截数据）；
- 缺 `ledger_id` ⇒ `XirrScopeParameterError` → 400（不是 500，不是家庭级）；
- 门面两条路径都把 `ledger_id` 透传下去（TWR 曾因门面漏传而同样失效）。
"""

import math
from datetime import date, timedelta

import pytest

from app.domains.ledgers.models import Ledger
from app.services.performance import calculate_return_by_scope
from app.services.performance.calculators import XirrScopeParameterError, calculate_portfolio_xirr
from app.services.performance.xirr_ledger import ledger_scope_xirr

ONE_YEAR_AGO = date.today() - timedelta(days=365)


def _account(db, make_position, make_transaction, *, name, symbol, price):
    """一个账户 + 一条持仓：买入 1000 元，期末市值 = 1000 份 × price。

    用 `asset_type='bond'` 走 `current_price`，不依赖 NAV / 行情表
    （与 `test_portfolio_xirr_units.py` 同一约定）。
    """
    ledger = Ledger(name=name, ledger_type='fund', family_id=1)
    db.add(ledger)
    db.flush()
    pos = make_position(
        symbol=symbol,
        name=f'{name}标的',
        ledger_id=ledger.id,
        asset_type='bond',
        quantity=1000,
        current_price=price,
    )
    make_transaction(
        pos.id,
        ledger.id,
        txn_type='buy',
        asset_type='bond',
        amount=1000,
        confirm_date=ONE_YEAR_AGO,
        account_name=name,
        symbol=symbol,
    )
    return ledger


@pytest.fixture
def two_accounts(db, make_position, make_transaction):
    """A 涨（1200）、B 跌（900）。家庭合计市值 2100，A 档只应有 1200。"""
    a = _account(db, make_position, make_transaction, name='账户A', symbol='AAA', price=1.2)
    b = _account(db, make_position, make_transaction, name='账户B', symbol='BBB', price=0.9)
    db.commit()
    return a, b


class TestService:
    def test_ledger_scope_counts_only_that_account(self, db, two_accounts):
        a, _ = two_accounts
        r = ledger_scope_xirr(db, a.id, family_id=1)
        assert r['current_value'] == 1200.0
        assert r['total_invested'] == 1000.0

    def test_ledger_scope_differs_from_family(self, db, two_accounts):
        """反例网：如果账户档悄悄回了家庭数，这条会红（家庭 2100 ≠ 账户 1200）。"""
        a, _ = two_accounts
        assert ledger_scope_xirr(db, a.id, family_id=1)['current_value'] == 1200.0
        assert calculate_portfolio_xirr(db, family_id=1)['current_value'] == 2100.0

    def test_ledger_scope_rejects_other_family(self, db, two_accounts):
        """跨家庭 id ⇒ ValueError（视图 404）。

        `restrict_visible` 对 `ledger_id IS NULL` 是**放行**的，不校验归属就会返回
        「无主行 + 空集」的半截数据——静默错数，比 404 更难发现。
        """
        a, _ = two_accounts
        with pytest.raises(ValueError, match='账户不存在'):
            ledger_scope_xirr(db, a.id, family_id=999)

    def test_ledger_scope_missing_id_raises_parameter_error(self, db):
        with pytest.raises(XirrScopeParameterError, match='ledger_id'):
            ledger_scope_xirr(db, None, family_id=1)

    def test_ledger_scope_accepts_dietz(self, db, two_accounts):
        """`method` 必须真的透传到底层，不能固定 xirr。"""
        a, _ = two_accounts
        r = ledger_scope_xirr(db, a.id, family_id=1, method='dietz')
        assert r['current_value'] == 1200.0
        # dietz 是区间收益（不年化），与 xirr 是不同字段口径；这里只钉「没抛错、数还对」
        assert not math.isnan(r.get('total_return', 0.0))


class TestFacadePassesLedgerId:
    """门面 `calculate_return_by_scope` 的两条分支都要透传 `ledger_id`。

    这是本次 bug 的另一半：`calculate_twr_by_scope` 早就收了 `ledger_id`，
    但门面没传，于是 `method=twr&scope=ledger` 同样静默回家庭级。
    """

    def test_xirr_branch_passes_ledger_id(self, db, two_accounts):
        a, _ = two_accounts
        r = calculate_return_by_scope(db, method='xirr', scope='ledger', ledger_id=a.id, family_id=1)
        assert r['current_value'] == 1200.0

    def test_twr_branch_passes_ledger_id(self, db, two_accounts, monkeypatch):
        """TWR 依赖日净资产序列，测试库没有 → 允许返回空/零，但**不能**抛「不支持」。"""
        a, _ = two_accounts
        captured = {}

        from app.services.performance import twr as twr_module

        real = twr_module.calculate_twr_by_scope

        def spy(db_, **kwargs):
            captured.update(kwargs)
            return real(db_, **kwargs)

        monkeypatch.setattr('app.services.performance.calculate_twr_by_scope', spy)
        calculate_return_by_scope(db, method='twr', scope='ledger', ledger_id=a.id, family_id=1)
        assert captured.get('ledger_id') == a.id, '门面没把 ledger_id 传给 TWR'


class TestEndpoint:
    """HTTP 编排：状态码不能骗人。"""

    def test_ledger_scope_returns_account_level(self, client, db, two_accounts):
        a, _ = two_accounts
        resp = client.get(f'/api/performance/xirr/?scope=ledger&ledger_id={a.id}')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['current_value'] == 1200.0, '端点回的是家庭口径（2100）'

    def test_ledger_scope_without_id_is_400(self, client):
        resp = client.get('/api/performance/xirr/?scope=ledger')
        assert resp.status_code == 400

    def test_ledger_scope_unknown_id_is_404(self, client):
        resp = client.get('/api/performance/xirr/?scope=ledger&ledger_id=99999')
        assert resp.status_code == 404
