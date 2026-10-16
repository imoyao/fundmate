# -*- coding: utf-8 -*-
"""同类内分位测试（#167）。

判据只有三条，但每条都能咬人：
1. **分位只在同类内算**——分组键错了，跨类比会静默给出「债基夏普全国第一」；
2. **回撤的方向**（负数值，越大越浅）与波动率（正数值，越小越好）方向**相反**，
   写成同一个方向会让「回撤最小」的基金分位最低；
3. **样本不足不出分位**——2 只基金的「同类第一」是噪音，出它比不出更坏。
"""

from app.services.fund_peer_rank import MIN_PEER_SAMPLE, peer_percentiles, percentile_rank


class TestPercentileRank:
    def test_basic_ecdf(self):
        # 5 个样本里 3 个小于 4.0 ⇒ 60
        assert percentile_rank([1.0, 2.0, 3.0, 4.0, 5.0], 4.0) == 60.0

    def test_uses_strictly_less(self):
        """全样本同值时给 0（保守），不给 100 —— 不宣称「比所有人都好」。"""
        assert percentile_rank([3.0] * 5, 3.0) == 0.0

    def test_none_value_or_insufficient_samples(self):
        assert percentile_rank([1.0, 2.0, 3.0, 4.0, 5.0], None) is None
        assert percentile_rank([1.0, 2.0], 1.5) is None  # 样本 < MIN_PEER_SAMPLE


class TestGrouping:
    def _rows(self, type_id, values_by_code):
        """把 {code: {metric: v}} 摊成 (code, type_id, values)。"""
        return [(code, type_id, vals) for code, vals in values_by_code.items()]

    def test_percentile_is_within_same_type(self):
        """两个类别的同值基金，分位各自在本类内算 —— 跨类比会给出同一个数。"""
        rows = [
            # 甲类：3 只，值 1/2/3（+2 只凑样本门槛）
            ('a1', 1, {'sharpe': 1.0}),
            ('a2', 1, {'sharpe': 2.0}),
            ('a3', 1, {'sharpe': 3.0}),
            ('a4', 1, {'sharpe': 4.0}),
            ('a5', 1, {'sharpe': 5.0}),
            # 乙类：5 只，值全是 100 —— 若跨类比，a3 会掉到很低的分位
            ('b1', 2, {'sharpe': 100.0}),
            ('b2', 2, {'sharpe': 100.0}),
            ('b3', 2, {'sharpe': 100.0}),
            ('b4', 2, {'sharpe': 100.0}),
            ('b5', 2, {'sharpe': 100.0}),
        ]
        out = peer_percentiles(rows, ['sharpe'])
        # a3 在本类 5 只里排第 3（2 只低于它）⇒ 40；若混类则远低于此
        assert out['a3']['sharpe'] == 40.0
        assert out['b1']['sharpe'] == 0.0

    def test_type_none_rows_are_excluded(self):
        rows = [('x', None, {'sharpe': 1.0})] + [(f'y{i}', 1, {'sharpe': float(i)}) for i in range(5)]
        out = peer_percentiles(rows, ['sharpe'])
        assert 'x' not in out


class TestDirection:
    def test_drawdown_negative_sign_means_shallower_is_better(self):
        """回撤是负数：-8 比 -25 好 ⇒ -8 的分位必须**高于** -25。"""
        rows = [
            ('deep', 1, {'max_drawdown': -25.0}),
            ('mid', 1, {'max_drawdown': -15.0}),
            ('shallow', 1, {'max_drawdown': -8.0}),
            ('s4', 1, {'max_drawdown': -30.0}),
            ('s5', 1, {'max_drawdown': -40.0}),
        ]
        out = peer_percentiles(rows, ['max_drawdown'])
        assert out['shallow']['max_drawdown'] > out['deep']['max_drawdown']

    def test_current_drawdown_same_direction_as_max(self):
        rows = [
            ('c', 1, {'current_drawdown': -20.0}),
            ('d', 1, {'current_drawdown': -2.0}),
            ('e', 1, {'current_drawdown': -10.0}),
            ('f', 1, {'current_drawdown': -30.0}),
            ('g', 1, {'current_drawdown': -40.0}),
        ]
        out = peer_percentiles(rows, ['current_drawdown'])
        assert out['d']['current_drawdown'] > out['c']['current_drawdown']

    def test_volatility_positive_sign_means_lower_is_better(self):
        """波动率是正数：越小越好 ⇒ 小波动分位**高于**大波动。

        与回撤方向相反。若两处共用同一个方向常量，本用例或上一个必红。
        """
        rows = [
            ('low', 1, {'annual_volatility': 5.0}),
            ('mid', 1, {'annual_volatility': 15.0}),
            ('high', 1, {'annual_volatility': 30.0}),
            ('s4', 1, {'annual_volatility': 40.0}),
            ('s5', 1, {'annual_volatility': 50.0}),
        ]
        out = peer_percentiles(rows, ['annual_volatility'])
        assert out['low']['annual_volatility'] > out['high']['annual_volatility']

    def test_return_metrics_higher_is_better(self):
        rows = [
            ('a', 1, {'sharpe': 1.0}),
            ('b', 1, {'sharpe': 2.0}),
            ('c', 1, {'sharpe': 3.0}),
            ('d', 1, {'sharpe': 4.0}),
            ('e', 1, {'sharpe': 5.0}),
        ]
        out = peer_percentiles(rows, ['sharpe'])
        assert out['e']['sharpe'] > out['a']['sharpe']


class TestSampleGate:
    def test_below_min_sample_no_percentile_at_all(self):
        """同类只有 2 只时整组都不出分位（不给出「同类第一」这种噪音）。"""
        rows = [('a', 1, {'sharpe': 1.0}), ('b', 1, {'sharpe': 2.0})]
        assert peer_percentiles(rows, ['sharpe']) == {}
        assert MIN_PEER_SAMPLE == 5

    def test_missing_value_excluded_from_denominator(self):
        """值为 None 的成员不进分母，也不出现在结果里。"""
        rows = [
            ('a', 1, {'sharpe': 1.0}),
            ('b', 1, {'sharpe': 2.0}),
            ('c', 1, {'sharpe': 3.0}),
            ('d', 1, {'sharpe': 4.0}),
            ('e', 1, {'sharpe': 5.0}),
            ('f', 1, {'sharpe': None}),
        ]
        out = peer_percentiles(rows, ['sharpe'])
        assert 'f' not in out
        # 分母是 5 而不是 6：4.0 有 3 个小于它 ⇒ 60
        assert out['d']['sharpe'] == 60.0

    def test_unknown_metric_is_skipped_not_crashed(self):
        rows = [(f'a{i}', 1, {'nope': float(i)}) for i in range(6)]
        assert peer_percentiles(rows, ['nope']) == {}
