# -*- coding: utf-8 -*-
"""TWR 与 Modified Dietz 测试（#871）。

口径约定（与实现同源，写测试前先对齐）：
- 金额存**分**、价格存 **0.0001 元**、份额存最小单位 **0.0001 份**；
- cashflows 里的金额是**元**（generate_cashflows 已换算）；
- 已知案例全部手算可复现：先算期望值再写断言，不用「跑出来是多少就写多少」。

#871 终态（C 方案）：TWR 统一到 #2133 的日因子引擎（`pnl_calendar` 的
`daily_pnl` 连乘），本文件只测两件事——
1. `calculate_modified_dietz`（#871 新增的区间口径，落在 xirr_engine）；
2. 组合级序列聚合与分派（#871 对日因子引擎的扩展）。
日因子连乘本体由 `tests/services/test_twr.py`（#2133，8 条）守着，不重复。
"""

import datetime as dt
import unittest
from unittest.mock import MagicMock, patch

from app.services.performance import XirrScopeParameterError, calculate_return_by_scope
from app.services.performance.twr import _merge_member_series, calculate_twr_by_scope
from app.services.performance.xirr_engine import calculate_modified_dietz

D0 = dt.date(2025, 1, 1)
D_MID = dt.date(2025, 7, 2)  # D0 + 182 天
D1 = dt.date(2025, 12, 31)  # D0 + 364 天（权重恰好 0.5 / 0，手算友好）


class TestModifiedDietz(unittest.TestCase):
    """Modified Dietz：区间线性近似，不年化（卡面 #796 结论：区间归因辅助）。"""

    def test_single_buy_full_period(self):
        """D0 买 1000 元、年末值 1100 元 ⇒ +10%（与 XIRR 同年化时重合）。"""
        cf = [(D0, -1000.0), (D1, 1100.0)]
        self.assertAlmostEqual(calculate_modified_dietz(cf), 0.10, places=6)

    def test_two_contributions_mid_period(self):
        """D0/D_MID 各买 1000、年末值 2300 ⇒ 权重 0.5 手算 +20.00%。

        分子 = Σa = +300；分母 = Σw·a = 1×(−1000) + 0.5×(−1000) = −1500。
        """
        cf = [(D0, -1000.0), (D_MID, -1000.0), (D1, 2300.0)]
        self.assertAlmostEqual(calculate_modified_dietz(cf), 0.20, places=6)

    def test_loss_case(self):
        cf = [(D0, -1000.0), (D1, 800.0)]
        self.assertAlmostEqual(calculate_modified_dietz(cf), -0.20, places=6)

    def test_with_withdrawal(self):
        """D0 买 1000、D_MID 卖出 600、年末余 550 ⇒ 分子 +150、分母 −700 ⇒ +21.43%。"""
        cf = [(D0, -1000.0), (D_MID, 600.0), (D1, 550.0)]
        self.assertAlmostEqual(calculate_modified_dietz(cf), 150.0 / 700.0, places=6)

    def test_degenerate_same_day(self):
        """所有流同一天（T=0）：权重无定义，退化为简单回报（增益/成本）。"""
        cf = [(D0, -1000.0), (D0, 1100.0)]
        self.assertAlmostEqual(calculate_modified_dietz(cf), 0.10, places=6)

    def test_period_starts_at_first_flow(self):
        """区间起点 = 首笔流（非日历起点）：钱在第 350 天才进仓、第 364 天值 1100 ⇒ 14 天 +10%。"""
        late = D0 + dt.timedelta(days=350)
        cf = [(late, -1000.0), (D1, 1100.0)]
        self.assertAlmostEqual(calculate_modified_dietz(cf), 0.10, places=6)

    def test_small_early_plus_large_late_blows_up(self):
        """Dietz 权重分母被晚期大额稀释 ⇒ 区间收益放大（预期行为，非 bug）。

        「临测前才进大钱」本就显得赚得多；年化口径（XIRR）才把它压回合理
        量级。钉住此特性，防止后人误当异常去「修」。
        """
        late = D0 + dt.timedelta(days=350)
        cf = [(D0, -1.0), (late, -1000.0), (D1, 1101.0)]
        # 分子 = Σa = +100；分母 = Σw·a = 1×(−1) + (14/364)×(−1000)
        expected = 100.0 / (1.0 + 1000.0 * 14 / 364)
        self.assertAlmostEqual(calculate_modified_dietz(cf), expected, places=6)
        self.assertGreater(calculate_modified_dietz(cf), 1.0)

    def test_empty_and_single(self):
        self.assertEqual(calculate_modified_dietz([]), 0.0)
        self.assertEqual(calculate_modified_dietz([(D0, -1000.0)]), 0.0)

    def test_zero_denominator_returns_zero(self):
        """全部资金最后一天才进（虚拟卖出之外无持续在仓资本）⇒ 0.0，不造数字。"""
        cf = [(D1, -1000.0), (D1, 1000.0)]  # 同日已走 simple 分支；
        # 构造「权重分母≈0」：唯一早期流金额为 0（被过滤后只剩末流）
        cf2 = [(D0, -0.0), (D1, 1100.0)]
        self.assertEqual(calculate_modified_dietz(cf2), 0.0)
        self.assertEqual(calculate_modified_dietz(cf), 0.0)


# ──────────────────── 组合级 TWR（#871，#2133 引擎的扩展）────────────────────────────


def _day(date: str, pnl, net_worth):
    return {'date': date, 'daily_pnl': pnl, 'net_worth': net_worth}


def _ledger_payload(days, ledger_id=1):
    return {'scope': 'ledger', 'ledger_id': ledger_id, 'days': days}


class TestMergeMemberSeries(unittest.TestCase):
    """Σ 成员日序列 → 组合日序列（_merge_member_series 纯函数）。"""

    def test_two_members_sum_by_date(self):
        """两成员同日求和：pnl 与 net_worth 分别 Σ（不是先算 TWR 再平均）。"""
        merged = _merge_member_series(
            [
                _ledger_payload([_day('2025-01-01', 0.0, 1000.0), _day('2025-01-02', 10.0, 1010.0)]),
                _ledger_payload([_day('2025-01-01', 0.0, 2000.0), _day('2025-01-02', -20.0, 1980.0)]),
            ]
        )
        self.assertEqual(merged['scope'], 'portfolio')
        self.assertEqual(len(merged['days']), 2)
        self.assertEqual(merged['days'][1]['daily_pnl'], -10.0)  # 10 + (−20)
        self.assertEqual(merged['days'][1]['net_worth'], 2990.0)  # 1010 + 1980

    def test_none_propagates_when_one_member_missing(self):
        """None 传播：任一成员某日缺 ⇒ 组合该日整体置缺（benchmark_excess 同纪律）。

        若误报成「只缺的那个不计、其余照算」，缺数据的一天会被洗成「部分持平」。
        """
        merged = _merge_member_series(
            [
                _ledger_payload([_day('2025-01-01', 0.0, 1000.0), _day('2025-01-02', 10.0, 1010.0)]),
                _ledger_payload([_day('2025-01-01', 0.0, 2000.0), _day('2025-01-02', None, None)]),
            ]
        )
        self.assertIsNone(merged['days'][1]['daily_pnl'])
        self.assertIsNone(merged['days'][1]['net_worth'])

    def test_short_member_series_marks_day_missing(self):
        """成员整天无行（序列更短）⇒ 组合该日同样置缺，不按「有的成员」算。"""
        merged = _merge_member_series(
            [
                _ledger_payload([_day('2025-01-01', 0.0, 1000.0), _day('2025-01-02', 10.0, 1010.0)]),
                _ledger_payload([_day('2025-01-01', 0.0, 2000.0)]),
            ]
        )
        self.assertIsNone(merged['days'][1]['daily_pnl'])

    def test_round_trip_through_chain_twr(self):
        """合并序列可直接喂 chain_twr：两成员各 +10% ⇒ 组合 TWR +10%（市值加权天然正确）。"""
        from app.services.performance.twr import chain_twr

        merged = _merge_member_series(
            [
                _ledger_payload([_day('2025-01-01', 0.0, 1000.0), _day('2025-01-02', 100.0, 1100.0)]),
                _ledger_payload([_day('2025-01-01', 0.0, 2000.0), _day('2025-01-02', 200.0, 2200.0)]),
            ]
        )
        result = chain_twr(merged)
        self.assertAlmostEqual(result['twr'], 0.10, places=6)
        self.assertEqual(result['scope'], 'portfolio')
        self.assertEqual(result['days_used'], 1)

    def test_empty_members_gives_empty_days(self):
        merged = _merge_member_series([])
        self.assertEqual(merged['days'], [])
        merged_one = _merge_member_series([_ledger_payload([])])
        self.assertEqual(merged_one['days'], [])


class TestTwrScopeDispatch(unittest.TestCase):
    """calculate_twr_by_scope 的 scope 支持域（#871 与 #2133 的立场一致）。"""

    def test_symbol_scope_rejected_with_400_class(self):
        """产品级没有每日净资产序列 ⇒ XirrScopeParameterError（视图映射 400）。

        悄悄拿家庭净资产当分母会给出一个「看起来对」的错数，比 400 危险得多。
        """
        with self.assertRaises(XirrScopeParameterError):
            calculate_twr_by_scope(db=MagicMock(), scope='symbol', symbol='SH600000')

    def test_position_scope_rejected_with_400_class(self):
        with self.assertRaises(XirrScopeParameterError):
            calculate_twr_by_scope(db=MagicMock(), scope='position', position_id=1)

    def test_family_scope_delegates_to_engine(self):
        """家庭级走 calculate_twr（与 /twr/ 端点同一条路径，不另起实现）。"""
        with patch('app.services.performance.twr.calculate_twr') as m:
            m.return_value = {'twr': 0.1}
            result = calculate_twr_by_scope(db=MagicMock(), scope='portfolio', portfolio_id=None)
        self.assertEqual(result, {'twr': 0.1})
        self.assertTrue(m.called)

    def test_portfolio_scope_builds_member_series(self):
        """组合级：成员解析 → 逐成员取序列 → 合并连乘（db 编排层）。"""
        db = MagicMock()
        # 组合存在性 + 成员账本查询链
        db.query.return_value.filter.return_value.first.return_value = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [(1,), (2,)]
        member_series = [
            _ledger_payload([_day('2025-01-01', 0.0, 1000.0), _day('2025-01-02', 100.0, 1100.0)], ledger_id=1),
            _ledger_payload([_day('2025-01-01', 0.0, 2000.0), _day('2025-01-02', 200.0, 2200.0)], ledger_id=2),
        ]
        with patch('app.services.performance.twr.build_daily_pnl_series', side_effect=member_series):
            result = calculate_twr_by_scope(db=db, scope='portfolio', portfolio_id=7)
        self.assertAlmostEqual(result['twr'], 0.10, places=6)
        self.assertEqual(result['scope'], 'portfolio')
        self.assertEqual(result['days_used'], 1)

    def test_portfolio_not_found_raises_value_error(self):
        """组合不存在 / 非本家庭 ⇒ ValueError（视图转 400/404，不造空数）。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with self.assertRaises(ValueError):
            calculate_twr_by_scope(db=db, scope='portfolio', portfolio_id=999)

    def test_empty_portfolio_returns_none_twr(self):
        """空组合（无成员账本）⇒ twr=None，而不是 0（「没数据」≠「持平」）。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        result = calculate_twr_by_scope(db=db, scope='portfolio', portfolio_id=7)
        self.assertIsNone(result['twr'])


class TestReturnDispatch(unittest.TestCase):
    """包门面 calculate_return_by_scope 的 method 校验（#871）。"""

    def test_invalid_method_raises_400_class(self):
        """非法 method 抛 XirrScopeParameterError（视图映射 400，而非 500/404）。"""
        with self.assertRaises(XirrScopeParameterError):
            calculate_return_by_scope(db=None, method='sharpe', scope='portfolio')

    def test_method_whitelist(self):
        from app.services.performance import _METHODS

        self.assertEqual(set(_METHODS), {'xirr', 'twr', 'dietz'})


if __name__ == '__main__':
    unittest.main()
