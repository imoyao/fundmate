# -*- coding: utf-8 -*-
"""#994 Phase 2：``build_symbol_pro_insight`` —— Pro 模块一账户级指标聚合。

覆盖四条验收线：

1. **无账户数据不是错误**：``has_account_data=False`` + XIRR 全 0 结构 + behavior
   空形态（指标 None）——前端据此渲染引导文案，不编数字；
2. **有数据聚合**：买入持有场景下 XIRR 与行为画像同源自洽（bond 定价规避行情前置，
   与 test_symbol_xirr 同一手法；持有一年 +20% 的 XIRR 期望用相对日期防漂移）；
3. **symbol 隔离**：别的标的流水不串味（两服务同一 symbol_scope 收敛）；
4. **状态位翻转**：``build_pro_status`` 的 performance / risk 模块 available=True
   （Phase 2 两模块钉子），其余两模块保持占位（Phase 3/4 落地节奏的钉子）。

单位约定（与 conftest 一致）：``make_transaction``/``make_position`` 收**元**、
库存**分**；behavior 出参一律元。behavior 断言按「分」推期望再除 100。
"""

import math
from datetime import date, timedelta

from app.services.pro_insight import build_symbol_pro_insight
from app.services.product_pro_status import build_pro_status

# 「持有一年」基准日：相对今天倒推，避免年份写死导致 XIRR 期望随运行日漂移
# （test_symbol_xirr 初版踩过的坑，见其文件头注释）。
ONE_YEAR_AGO = date.today() - timedelta(days=365)


def _bond_position(make_position, symbol, quantity, current_price):
    """bond 类型走 current_price 定值分支，不依赖净值/行情表。"""
    return make_position(
        symbol=symbol,
        name=f'测试标的{symbol}',
        account_name='账户A',
        asset_type='bond',
        quantity=quantity,
        current_price=current_price,
    )


class TestNoAccountData:
    def test_empty_shape_is_not_an_error(self, db):
        """无成交无持仓：has_account_data=False，两子结构均为各自空形态。"""
        r = build_symbol_pro_insight(db, '999999')

        assert r['symbol'] == '999999'
        assert r['has_account_data'] is False
        # XIRR 空结构（#1972 契约）：全 0，前端降级「—」不出 NaN
        assert r['xirr'] == {
            'xirr': 0.0,
            'total_invested': 0.0,
            'current_value': 0.0,
            'total_withdrawn': 0.0,
            'total_return': 0.0,
            'cashflow_count': 0,
        }
        # behavior 空形态：样本类指标 None、笔数 0
        assert r['behavior']['closed_count'] == 0
        assert r['behavior']['win_rate'] is None
        assert r['behavior']['realized_pnl_total'] is None
        assert r['behavior']['avg_holding_days'] is None

    def test_asset_type_echoed(self, db):
        """asset_type 仅回显（与 pro-status 同约定）。"""
        r = build_symbol_pro_insight(db, '999999', asset_type='fund')
        assert r['asset_type'] == 'fund'


class TestWithAccountData:
    def test_buy_hold_aggregates_both_services(self, db, make_position, make_transaction):
        """买入持有一年 +20%：XIRR 与 behavior 从同一批流水各自算对。"""
        pos = _bond_position(make_position, '000001', quantity=1000, current_price=1.2)
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='buy',
            asset_type='bond',
            quantity=1000,
            amount=1000,  # 元（fixture 内部转分）；1000 份 × 1.0 元/份
            confirm_date=ONE_YEAR_AGO,
            symbol='000001',
        )

        r = build_symbol_pro_insight(db, '000001')

        assert r['has_account_data'] is True
        # XIRR：1 笔买入（-1000 元）+ 虚拟卖出（+1200 元），持有一年 +20%
        assert r['xirr']['cashflow_count'] == 2
        assert r['xirr']['total_invested'] == 1000.0
        assert r['xirr']['current_value'] == 1200.0
        assert abs(r['xirr']['xirr'] - 0.20) < 0.005
        assert not math.isnan(r['xirr']['xirr'])
        # behavior：买入 1 笔；无卖出 → 无平仓样本（诚实 None），不编数
        assert r['behavior']['buy_count'] == 1
        assert r['behavior']['closed_count'] == 0
        assert r['behavior']['win_rate'] is None

    def test_closed_trade_yields_behavior_stats(self, db, make_position, make_transaction):
        """一买一卖平仓：胜率/已实现盈亏与 FIFO 配对口径一致（不读 realized_pnl）。"""
        pos = _bond_position(make_position, '000002', quantity=1000, current_price=1.0)
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='buy',
            asset_type='bond',
            quantity=1000,
            amount=1000,  # 1000 元 → 100000 分
            confirm_date=ONE_YEAR_AGO,
            symbol='000002',
        )
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='sell',
            asset_type='bond',
            quantity=1000,
            amount=1050,  # 回款 1050 元 → 105000 分 → 配对盈 +5000 分 = +50 元
            confirm_date=date.today(),
            symbol='000002',
        )

        r = build_symbol_pro_insight(db, '000002')

        assert r['has_account_data'] is True
        assert r['behavior']['closed_count'] == 1
        assert r['behavior']['win_rate'] == 100.0
        assert r['behavior']['realized_pnl_total'] == 50.0

    def test_symbol_isolation(self, db, make_position, make_transaction):
        """A 标的的流水不进 B 标的的聚合（两服务同一 symbol_scope 收敛）。"""
        pos_a = _bond_position(make_position, '000003', quantity=1000, current_price=1.0)
        make_transaction(
            pos_a.id,
            pos_a.ledger_id,
            txn_type='buy',
            asset_type='bond',
            quantity=1000,
            amount=1000,
            confirm_date=ONE_YEAR_AGO,
            symbol='000003',
        )

        r_b = build_symbol_pro_insight(db, '000004')
        assert r_b['has_account_data'] is False
        assert r_b['xirr']['cashflow_count'] == 0
        assert r_b['behavior']['buy_count'] == 0


class TestProStatusFlip:
    def test_performance_module_flipped_available(self):
        """Phase 2 钉子：performance / risk 可用位翻真，其余两模块保持占位。"""
        modules = build_pro_status('000001')['modules']

        assert modules['performance'] == {'available': True, 'phase': 2}
        assert modules['risk'] == {'available': True, 'phase': 2}
        assert modules['allocation'] == {'available': False, 'phase': 3}
        assert modules['report'] == {'available': False, 'phase': 4}
