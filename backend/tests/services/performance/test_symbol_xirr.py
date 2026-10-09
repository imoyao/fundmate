# -*- coding: utf-8 -*-
"""#1972：`calculate_symbol_xirr` —— 产品级持有年化（跨账户按 symbol 汇总现金流）。

验收三条对应的覆盖：

1. **三种情形**：单账户（`test_single_account...`）、多账户同 symbol（`test_multi_account...`）、
   无成交记录（`test_no_transactions...`，另含「已清仓但有流水」的边界）；
2. **不回归**：`test_symbol_scope_is_isolated_from_other_symbols` 断言 symbol 维度只吃自己的
   现金流、而 `scope=portfolio` 仍吃全部（既有 `test_include_cash_equivalents.py` /
   `test_xirr_engine.py` 继续钉 portfolio / 引擎层）；
3. **不出现 NaN**：空结果为全 0 结构（`xirr == 0.0`、`cashflow_count == 0`），前端据此降级 `—`。

市值口径说明：测试统一用 `asset_type='bond'` —— 该类型走 `current_price` 分支，
不依赖基金净值 / 行情表（fund/stock/etf 需要 NAV 或 PriceHistory 才有市值，
会让用例被无关的数据前置拖累）。
"""

import math
from datetime import date, timedelta

from app.services.performance.calculators import (
    calculate_portfolio_xirr,
    calculate_symbol_xirr,
)

# 「持有一年」的基准日：买入日相对今天倒推 365 天，避免把年份写死
# （写死年份会让「约等于 1 年」的 XIRR 期望随真实日期漂移——本文件初版就踩过：
#  2024-01-01 买入到运行日 2026-10 实为 2.75 年，期望 0.20 却得到 0.068）。
ONE_YEAR_AGO = date.today() - timedelta(days=365)


def _bond_position(make_position, symbol, account_name, quantity, current_price):
    """建一条用 current_price 定值的持仓（避开 NAV / 行情表前置）。"""
    return make_position(
        symbol=symbol,
        name=f'测试标的{symbol}',
        account_name=account_name,
        asset_type='bond',
        quantity=quantity,
        current_price=current_price,
    )


class TestSingleAccount:
    def test_buy_then_hold_is_buy_plus_virtual_sale(self, db, make_position, make_transaction):
        """单账户：买入后仍持有 → 现金流 = 买入（负）+ 虚拟卖出（当前市值，正）。"""
        pos = _bond_position(make_position, '000001', '账户A', quantity=1000, current_price=1.2)
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='buy',
            asset_type='bond',
            amount=1000,
            confirm_date=ONE_YEAR_AGO,
            account_name='账户A',
            symbol='000001',
        )

        r = calculate_symbol_xirr(db, '000001', family_id=1)

        # 1 笔买入 + 1 笔虚拟卖出（今天，市值 1000×1.2=1200）
        assert r['cashflow_count'] == 2
        assert r['total_invested'] == 1000.0
        assert r['current_value'] == 1200.0
        assert r['total_return'] == 200.0
        # 持有一整年 +20%：XIRR 解应为 0.20
        assert abs(r['xirr'] - 0.20) < 0.005
        assert not math.isnan(r['xirr'])


class TestMultiAccount:
    def test_same_symbol_across_accounts_merges_cashflows(self, db, make_position, make_transaction):
        """多账户同 symbol：两条账户的现金流**合并成一条时间线**，市值也合并。

        只统计单账户时 total_invested 会是 1000 —— 这正是本 scope 存在的意义。
        """
        pos_a = _bond_position(make_position, '000001', '账户A', quantity=1000, current_price=1.2)
        pos_b = _bond_position(make_position, '000001', '账户B', quantity=500, current_price=1.2)

        make_transaction(
            pos_a.id,
            pos_a.ledger_id,
            txn_type='buy',
            asset_type='bond',
            amount=1000,
            confirm_date=date(2024, 1, 1),
            account_name='账户A',
            symbol='000001',
        )
        make_transaction(
            pos_b.id,
            pos_b.ledger_id,
            txn_type='buy',
            asset_type='bond',
            amount=500,
            confirm_date=date(2024, 7, 1),
            account_name='账户B',
            symbol='000001',
        )

        r = calculate_symbol_xirr(db, '000001', family_id=1)

        assert r['total_invested'] == 1500.0  # 两个账户都算进来了
        assert r['current_value'] == 1800.0  # 1000×1.2 + 500×1.2
        assert r['cashflow_count'] == 3  # 两笔买入 + 虚拟卖出
        assert r['xirr'] > 0
        assert not math.isnan(r['xirr'])


class TestNoTransactions:
    def test_no_data_returns_zero_structure_not_nan(self, db):
        """无成交记录、无持仓：全 0 结构，绝不返回 NaN（前端据此降级 `—`）。"""
        r = calculate_symbol_xirr(db, '999999', family_id=1)

        assert r['cashflow_count'] == 0
        assert r['xirr'] == 0.0
        assert r['total_invested'] == 0.0
        assert r['current_value'] == 0.0
        assert r['total_return'] == 0.0
        assert not math.isnan(r['xirr'])

    def test_empty_symbol_is_rejected(self, db):
        """空 symbol 直接报错，不静默退化成「全家桶」XIRR。"""
        import pytest

        with pytest.raises(ValueError):
            calculate_symbol_xirr(db, '', family_id=1)

    def test_fully_sold_position_still_has_cashflows(self, db, make_position, make_transaction):
        """已清仓（quantity=0）但有流水：市值为 0，现金流仍在，XIRR 仍可算。

        回归点：`query_positions_by_symbol` **不过滤数量** —— 若哪天改成 quantity>0，
        清仓产品的持有年化会凭空变 0。
        """
        pos = _bond_position(make_position, '000001', '账户A', quantity=0, current_price=1.2)
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='buy',
            asset_type='bond',
            amount=1000,
            confirm_date=date(2024, 1, 1),
            account_name='账户A',
            symbol='000001',
        )
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='sell',
            asset_type='bond',
            amount=1200,
            confirm_date=date(2025, 1, 1),
            account_name='账户A',
            symbol='000001',
        )

        r = calculate_symbol_xirr(db, '000001', family_id=1)

        assert r['current_value'] == 0.0  # 清仓行不贡献市值
        assert r['cashflow_count'] == 2  # 但流水一并不少
        assert r['xirr'] > 0


class TestScopeIsolation:
    def test_symbol_scope_is_isolated_from_other_symbols(self, db, make_position, make_transaction):
        """symbol 维度只吃自己的现金流；portfolio 维度仍吃全部（不回归既有口径）。"""
        pos_1 = _bond_position(make_position, '000001', '账户A', quantity=0, current_price=1.2)
        pos_2 = _bond_position(make_position, '000002', '账户A', quantity=0, current_price=1.2)
        for pos, amount in ((pos_1, 1000), (pos_2, 2000)):
            make_transaction(
                pos.id,
                pos.ledger_id,
                txn_type='buy',
                asset_type='bond',
                amount=amount,
                confirm_date=date(2024, 1, 1),
                account_name='账户A',
                symbol=pos.symbol,
            )
            make_transaction(
                pos.id,
                pos.ledger_id,
                txn_type='sell',
                asset_type='bond',
                amount=amount * 2,
                confirm_date=date(2025, 1, 1),
                account_name='账户A',
                symbol=pos.symbol,
            )

        r_symbol = calculate_symbol_xirr(db, '000001', family_id=1)
        r_portfolio = calculate_portfolio_xirr(db, family_id=1)

        assert r_symbol['cashflow_count'] == 2  # 只有 000001 的买 + 卖
        assert r_symbol['total_invested'] == 1000.0
        assert r_portfolio['cashflow_count'] == 4  # portfolio 口径不受影响
        assert r_portfolio['total_invested'] == 3000.0


class TestWrittenVariants:
    def test_position_written_with_other_form_is_matched(self, db, make_position, make_transaction):
        """写法变体：库里落 `SZ000001`、详情页传 `000001.SZ`，仍算同一个标的。

        归一身份键（#1662）在 EXCHANGE 下两者同键（实测 `EXCHANGE:SZ000001`）。
        流水字面量跟持仓写法一致（写入侧按 `Transaction.symbol == position.symbol` 对齐），
        故交易靠 `collect_transaction_symbol_variants` 的两步法一并命中。
        """
        pos = _bond_position(make_position, 'SZ000001', '账户A', quantity=1000, current_price=1.2)
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='buy',
            asset_type='bond',
            amount=1000,
            confirm_date=date(2024, 1, 1),
            account_name='账户A',
            symbol='SZ000001',
        )

        r = calculate_symbol_xirr(db, '000001.SZ', family_id=1)

        assert r['cashflow_count'] == 2
        assert r['total_invested'] == 1000.0
        assert r['current_value'] == 1200.0


class TestEndpoint:
    """端点级：HTTP 编排（参数校验 / 信封）不出错。"""

    def test_scope_symbol_without_symbol_is_400(self, client):
        resp = client.get('/api/performance/xirr/?scope=symbol')
        assert resp.status_code == 400

    def test_scope_position_without_id_is_400_not_500(self, client):
        """参数缺失应为 400。

        存量 bug 的回归钉子：`abort(400)` 抛的 `BadRequest` 落进视图兜底的
        `except Exception` 会被转成 500；#1972 把分派下沉 services 后，
        「参数缺失」由 `XirrScopeParameterError` 显式映射 400。
        """
        resp = client.get('/api/performance/xirr/?scope=position')
        assert resp.status_code == 400

    def test_scope_symbol_returns_data_envelope(self, client, db, make_position, make_transaction):
        pos = _bond_position(make_position, '000001', '账户A', quantity=1000, current_price=1.2)
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='buy',
            asset_type='bond',
            amount=1000,
            confirm_date=date(2024, 1, 1),
            account_name='账户A',
            symbol='000001',
        )
        # make_transaction 只 flush；HTTP 请求走另一个 session，不 commit 看不见这笔流水
        db.commit()

        resp = client.get('/api/performance/xirr/?scope=symbol&symbol=000001')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['cashflow_count'] == 2
        assert data['current_value'] == 1200.0
        assert not math.isnan(data['xirr'])
