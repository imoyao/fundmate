# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/14
# File : test_money_fund_income.py
"""货币基金每日收益计算服务与 API 单测。"""

import datetime as dt

import pytest

from app.core.money import Money
from app.domains.funds.models import Fund, MoneyFundDailyWorth
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.money_fund_income import calculate_money_fund_income

# -------------------- 测试辅助 --------------------


def _make_ledger(db, name='测试账户', family_id=1):
    ledger = Ledger(name=name, ledger_type='bank', family_id=family_id)
    db.add(ledger)
    db.flush()
    return ledger


def _make_fund(db, fund_code, name='测试货基'):
    fund = Fund(fund_code=fund_code, name=name)
    db.add(fund)
    db.flush()
    return fund


def _make_worth(db, fund_code, day, nav_per_10k):
    """构造 MoneyFundDailyWorth 行（nav_per_10k 单位：分）。"""
    db.add(MoneyFundDailyWorth(fund_code=fund_code, date=day, nav_per_10k=nav_per_10k))
    db.flush()


def _make_orphan_flow(db, ledger, fund_code, day, txn_type, amount_yuan, family_id=1):
    """构造孤儿流水（position_id IS NULL、asset_type='money_fund'）。"""
    txn = Transaction(
        position_id=None,
        ledger_id=ledger.id,
        txn_type=txn_type,
        symbol=fund_code,
        amount=Money.yuan_to_cents(amount_yuan),
        confirm_date=day,
        trade_date=dt.datetime.combine(day, dt.time(10, 0)),
        asset_type='money_fund',
        family_id=family_id,
        status='success',
    )
    db.add(txn)
    db.flush()
    return txn


def _make_money_fund_position(db, ledger, fund_code, quantity, current_price_yuan, family_id=1):
    """构造 positions 货基持仓（迁移前兼容口径）。"""
    pos = Position(
        ledger_id=ledger.id,
        symbol=fund_code,
        name='测试货基持仓',
        asset_type='money_fund',
        quantity=Money.shares_to_min_unit(quantity),
        current_price=Money.yuan_to_cents(current_price_yuan),
        family_id=family_id,
    )
    db.add(pos)
    db.flush()
    return pos


# -------------------- 服务层：计算式 --------------------


class TestDailyIncome:
    def test_example_50000_x_35(self, db):
        """规格示例：H=50000 分、w=35 分 → 50000×35/1e6=1.75 分 → round 到 2 分。"""
        ledger = _make_ledger(db)
        _make_fund(db, '511880')
        day = dt.date(2026, 8, 1)
        _make_worth(db, '511880', day, 35)
        _make_orphan_flow(db, ledger, '511880', day, 'buy', 500.0)  # 500元 = 50000分

        result = calculate_money_fund_income(db, start_date=day, end_date=day, scope='family', family_id=1)

        # 精确值 1.75 分，round half-up 到分 = 2 分 = 0.02 元
        assert result['daily_series'] == [{'date': '2026-08-01', 'income': 0.02}]
        assert result['today_income'] == 0.02
        assert result['total_income'] == 0.02

    def test_multi_day_cumulative_with_flows(self, db):
        """跨多日累计：D1 买 500 元、D2 追加 300 元，逐日收益随持有金额变化。"""
        ledger = _make_ledger(db)
        _make_fund(db, '511880')
        d1, d2, d3 = dt.date(2026, 8, 1), dt.date(2026, 8, 2), dt.date(2026, 8, 3)
        _make_worth(db, '511880', d1, 35)
        _make_worth(db, '511880', d2, 40)
        _make_worth(db, '511880', d3, 20)
        _make_orphan_flow(db, ledger, '511880', d1, 'buy', 500.0)  # 50000分
        _make_orphan_flow(db, ledger, '511880', d2, 'buy', 300.0)  # 追加 30000分

        result = calculate_money_fund_income(db, start_date=d1, end_date=d3, scope='family', family_id=1)

        # D1: 50000×35/1e6=1.75→2分；D2: 80000×40/1e6=3.2→3分；D3: 80000×20/1e6=1.6→2分
        assert result['daily_series'] == [
            {'date': '2026-08-01', 'income': 0.02},
            {'date': '2026-08-02', 'income': 0.03},
            {'date': '2026-08-03', 'income': 0.02},
        ]
        assert result['today_income'] == 0.02
        assert result['total_income'] == 0.07

    def test_sell_reduces_holding(self, db):
        """卖出减少持有：D1 买 500 元、D2 卖 200 元 → D2 持有 30000 分。"""
        ledger = _make_ledger(db)
        _make_fund(db, '511880')
        d1, d2 = dt.date(2026, 8, 1), dt.date(2026, 8, 2)
        _make_worth(db, '511880', d1, 35)
        _make_worth(db, '511880', d2, 40)
        _make_orphan_flow(db, ledger, '511880', d1, 'buy', 500.0)
        _make_orphan_flow(db, ledger, '511880', d2, 'sell', 200.0)

        result = calculate_money_fund_income(db, start_date=d1, end_date=d2, scope='family', family_id=1)

        # D1: 50000×35/1e6=1.75→2分；D2: 30000×40/1e6=1.2→1分
        assert result['daily_series'] == [
            {'date': '2026-08-01', 'income': 0.02},
            {'date': '2026-08-02', 'income': 0.01},
        ]
        assert result['total_income'] == 0.03

    def test_zero_holding(self, db):
        """零持有：无流水无持仓，序列仍含全部日期，收益全 0。"""
        _make_fund(db, '511880')
        d1, d2, d3 = dt.date(2026, 8, 1), dt.date(2026, 8, 2), dt.date(2026, 8, 3)
        _make_worth(db, '511880', d1, 35)
        _make_worth(db, '511880', d2, 40)
        _make_worth(db, '511880', d3, 20)

        result = calculate_money_fund_income(db, start_date=d1, end_date=d3, scope='family', family_id=1)

        assert len(result['daily_series']) == 3
        assert all(item['income'] == 0.0 for item in result['daily_series'])
        assert result['today_income'] == 0.0
        assert result['total_income'] == 0.0

    def test_missing_nav_day_fallback(self, db):
        """nav_per_10k 缺失日：当日收益记 0，序列仍含该日。"""
        ledger = _make_ledger(db)
        _make_fund(db, '511880')
        d1, d2, d3 = dt.date(2026, 8, 1), dt.date(2026, 8, 2), dt.date(2026, 8, 3)
        _make_worth(db, '511880', d1, 35)  # 仅 D1 有万份收益
        _make_orphan_flow(db, ledger, '511880', d1, 'buy', 500.0)

        result = calculate_money_fund_income(db, start_date=d1, end_date=d3, scope='family', family_id=1)

        assert result['daily_series'] == [
            {'date': '2026-08-01', 'income': 0.02},
            {'date': '2026-08-02', 'income': 0.0},
            {'date': '2026-08-03', 'income': 0.0},
        ]
        assert result['total_income'] == 0.02

    def test_merged_orphan_and_position(self, db):
        """合并口径：孤儿流水（基金A）+ positions 货基（基金B）并存，收益相加。"""
        ledger = _make_ledger(db)
        _make_fund(db, '511880')
        _make_fund(db, '511990')
        day = dt.date(2026, 8, 1)
        _make_worth(db, '511880', day, 35)
        _make_worth(db, '511990', day, 40)
        _make_orphan_flow(db, ledger, '511880', day, 'buy', 500.0)  # 50000分
        _make_money_fund_position(db, ledger, '511990', quantity=1000, current_price_yuan=1.0)  # 100000分

        result = calculate_money_fund_income(db, start_date=day, end_date=day, scope='family', family_id=1)

        # 孤儿: 50000×35/1e6=1.75→2分；持仓: 100000×40/1e6=4分；合计 6 分 = 0.06 元
        assert result['daily_series'] == [{'date': '2026-08-01', 'income': 0.06}]
        assert result['total_income'] == 0.06

    def test_position_baseline_applies_all_days(self, db):
        """迁移前兼容：positions 货基市值作为恒定基线，覆盖整个区间。"""
        ledger = _make_ledger(db)
        _make_fund(db, '511990')
        d1, d2 = dt.date(2026, 8, 1), dt.date(2026, 8, 2)
        _make_worth(db, '511990', d1, 40)
        _make_worth(db, '511990', d2, 40)
        _make_money_fund_position(db, ledger, '511990', quantity=1000, current_price_yuan=1.0)  # 100000分

        result = calculate_money_fund_income(db, start_date=d1, end_date=d2, scope='family', family_id=1)

        # 两天均为 100000×40/1e6=4分
        assert result['daily_series'] == [
            {'date': '2026-08-01', 'income': 0.04},
            {'date': '2026-08-02', 'income': 0.04},
        ]
        assert result['total_income'] == 0.08


# -------------------- 服务层：scope 过滤与参数校验 --------------------


class TestScopeAndParams:
    def test_scope_ledger_filters_by_ledger(self, db):
        """scope=ledger 只统计指定账户；scope=family 统计家庭全量。"""
        ledger_a = _make_ledger(db, name='账户A')
        ledger_b = _make_ledger(db, name='账户B')
        _make_fund(db, '511880')
        day = dt.date(2026, 8, 1)
        _make_worth(db, '511880', day, 35)
        _make_orphan_flow(db, ledger_a, '511880', day, 'buy', 500.0)
        _make_orphan_flow(db, ledger_b, '511880', day, 'buy', 1000.0)

        ledger_result = calculate_money_fund_income(
            db, start_date=day, end_date=day, scope='ledger', ledger_id=ledger_a.id, family_id=1
        )
        family_result = calculate_money_fund_income(db, start_date=day, end_date=day, scope='family', family_id=1)

        # 账户A: 50000×35/1e6=1.75→2分；家庭: (50000+100000)×35/1e6=5.25→5分
        assert ledger_result['total_income'] == 0.02
        assert family_result['total_income'] == 0.05

    def test_default_window_is_30_days(self, db):
        """不传日期时默认近 30 天（含首尾），序列长度 30。"""
        ledger = _make_ledger(db)
        _make_fund(db, '511880')
        today = dt.date.today()
        _make_worth(db, '511880', today, 35)
        _make_orphan_flow(db, ledger, '511880', today, 'buy', 500.0)

        result = calculate_money_fund_income(db, scope='family', family_id=1)

        assert len(result['daily_series']) == 30
        assert result['daily_series'][-1]['date'] == today.isoformat()
        assert result['today_income'] == 0.02

    def test_invalid_scope_raises(self, db):
        with pytest.raises(ValueError, match='scope'):
            calculate_money_fund_income(db, scope='bad', family_id=1)

    def test_ledger_scope_requires_ledger_id(self, db):
        with pytest.raises(ValueError, match='ledger_id'):
            calculate_money_fund_income(db, scope='ledger', family_id=1)

    def test_inverted_range_returns_empty(self, db):
        """范围倒挂（start > end）返回空序列，不报错。"""
        result = calculate_money_fund_income(
            db,
            start_date=dt.date(2026, 8, 10),
            end_date=dt.date(2026, 8, 1),
            scope='family',
            family_id=1,
        )
        assert result == {'today_income': 0.0, 'total_income': 0.0, 'daily_series': []}


# -------------------- API 端点 --------------------


class TestMoneyFundIncomeEndpoint:
    def test_family_scope_ok(self, client, db):
        ledger = _make_ledger(db)
        _make_fund(db, '511880')
        day = dt.date(2026, 8, 1)
        _make_worth(db, '511880', day, 35)
        _make_orphan_flow(db, ledger, '511880', day, 'buy', 500.0)
        db.commit()

        resp = client.get(f'/api/performance/money-fund-income/?scope=family&start_date={day}&end_date={day}')

        assert resp.status_code == 200
        body = resp.get_json()
        assert body['message'] == 'ok'
        assert body['data']['today_income'] == 0.02
        assert body['data']['total_income'] == 0.02
        assert body['data']['daily_series'] == [{'date': '2026-08-01', 'income': 0.02}]

    def test_ledger_scope_ok(self, client, db):
        ledger = _make_ledger(db)
        _make_fund(db, '511880')
        day = dt.date(2026, 8, 1)
        _make_worth(db, '511880', day, 35)
        _make_orphan_flow(db, ledger, '511880', day, 'buy', 500.0)
        db.commit()

        resp = client.get(
            f'/api/performance/money-fund-income/?scope=ledger&ledger_id={ledger.id}&start_date={day}&end_date={day}'
        )

        assert resp.status_code == 200
        assert resp.get_json()['data']['total_income'] == 0.02

    def test_invalid_scope_400(self, client):
        resp = client.get('/api/performance/money-fund-income/?scope=bad')
        assert resp.status_code == 400
        body = resp.get_json()
        assert body['data'] is None
        assert 'scope' in body['message']
        assert body['error_code']

    def test_missing_scope_400(self, client):
        resp = client.get('/api/performance/money-fund-income/')
        assert resp.status_code == 400
        assert 'scope' in resp.get_json()['message']

    def test_missing_ledger_id_400(self, client):
        resp = client.get('/api/performance/money-fund-income/?scope=ledger')
        assert resp.status_code == 400
        assert 'ledger_id' in resp.get_json()['message']

    def test_ledger_not_found_404(self, client, db):
        resp = client.get('/api/performance/money-fund-income/?scope=ledger&ledger_id=999')
        assert resp.status_code == 404

    def test_no_data_returns_zero_structure(self, client, db):
        """无数据 → 正常返回零值结构（不报错）。"""
        resp = client.get('/api/performance/money-fund-income/?scope=family&start_date=2026-08-01&end_date=2026-08-03')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['data']['today_income'] == 0.0
        assert body['data']['total_income'] == 0.0
        assert len(body['data']['daily_series']) == 3
        assert all(item['income'] == 0.0 for item in body['data']['daily_series'])

    def test_date_range_respected(self, client, db):
        """start_date/end_date 参数生效：只返回区间内日期。"""
        ledger = _make_ledger(db)
        _make_fund(db, '511880')
        d1, d2, d3 = dt.date(2026, 8, 1), dt.date(2026, 8, 2), dt.date(2026, 8, 3)
        _make_worth(db, '511880', d1, 35)
        _make_worth(db, '511880', d2, 40)
        _make_worth(db, '511880', d3, 20)
        _make_orphan_flow(db, ledger, '511880', d1, 'buy', 500.0)
        db.commit()

        resp = client.get(f'/api/performance/money-fund-income/?scope=family&start_date={d1}&end_date={d2}')

        assert resp.status_code == 200
        series = resp.get_json()['data']['daily_series']
        assert [item['date'] for item in series] == ['2026-08-01', '2026-08-02']
        assert resp.get_json()['data']['total_income'] == 0.04  # D1: 2分 + D2: 2分
