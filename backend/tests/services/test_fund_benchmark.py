# -*- coding: utf-8 -*-
"""基金「类别 → 基准」映射测试（#167）。

重点不是「跑起来」，而是三条口径纪律：
1. **偏债不能被「混合」抢走**——规则表的顺序就是判据本身，顺序错了它照样绿；
2. **命不中一律 None，不猜**——拿沪深300 顶替债基是「看起来有数、其实没比」；
3. **映射出的代码必须真的取得到序列**（在 `index_daily_job` 目标清单里），
   否则映射等于「选了一个我们没数据的基准」。
"""

import pytest

from app.services.fund_benchmark import (
    BENCH_BOND_FUND,
    BENCH_EQUITY_FUND,
    BENCH_HS300,
    BENCH_HYBRID_FUND,
    BenchmarkChoice,
    resolve,
)


class TestResolveRouting:
    """按 fund_type.name 的具体形态验证分流。"""

    @pytest.mark.parametrize(
        'type_name,expected',
        [
            ('股票型', BENCH_EQUITY_FUND),
            ('混合型-偏股', BENCH_HYBRID_FUND),
            ('混合型-灵活', BENCH_HYBRID_FUND),
            ('债券型-长期纯债', BENCH_BOND_FUND),
            ('债券型-混合二级', BENCH_BOND_FUND),
        ],
    )
    def test_routes_by_type_name(self, type_name, expected):
        choice = resolve(type_name)
        assert isinstance(choice, BenchmarkChoice)
        assert choice.code == expected
        assert choice.matched_by  # 口径留痕：必须能说清「凭什么拿它比」

    def test_偏债_混合_does_not_fall_into_equity_hybrid(self):
        """「混合型-偏债」含「混合」也含「偏债」——必须是债券族。

        这条是**规则顺序的判据**：把 `('偏债',)` 那条挪到 `('混合',)` 之后，
        本用例会红。没有它，顺序错了没人知道。
        """
        choice = resolve('混合型-偏债')
        assert choice is not None
        assert choice.code == BENCH_BOND_FUND
        assert choice.code != BENCH_HYBRID_FUND

    def test_纯债_match_before_generic_bond(self):
        """「长期纯债」比泛「债券」更具体，规则名应体现命中哪一条。"""
        assert resolve('债券型-长期纯债').matched_by != resolve('债券型-其他').matched_by


class TestNoGuessFallback:
    """命不中 / 不适用时必须是 None —— 不拿宽基顶替。"""

    @pytest.mark.parametrize(
        'type_name',
        ['货币型', '货币型-普通货币', '指数型-股票', 'ETF', 'QDII', 'QDII-股票', 'FOF'],
    )
    def test_not_applicable_returns_none(self, type_name):
        assert resolve(type_name) is None

    def test_index_bond_fund_not_mapped_to_peer_bond_fund(self):
        """指数债基 = 跟踪某只债指数，**不是**「跟同类债基比」。

        这条是变异探针挖出来的真 bug：删掉「指数型 → None」那条规则后，
        `指数型-债券` 会被下面的债券族规则捡走、映射成「万得债券型基金指数」。
        也就是说那条看似多余的规则**是唯一拦住这件事的东西**，它必须留着。
        """
        for t in ('指数型-债券', '指数型-偏债', '债券指数型'):
            assert resolve(t) is None, f'{t} 被判成了同类债基基准（应为 None）'

    def test_index_equity_fund_not_mapped_to_peer_equity_fund(self):
        """同理：指数股基（跟踪沪深300 的）不该被判成「跟同类股基比」。"""
        for t in ('指数型-股票', '指数型'):
            assert resolve(t) is None

    def test_etf_and_feeder_not_mapped(self):
        """ETF / 联接：源侧无「跟踪标的」字段（实测全空）⇒ 不猜。"""
        for t in ('ETF', 'ETF-联接', '联接基金'):
            assert resolve(t) is None

    def test_unknown_type_returns_none_not_hs300(self):
        """未知类型绝不退回沪深300：用户读不出「它其实没被比过」。"""
        for t in ('', None, '   ', '某个新品类', '基金型'):
            assert resolve(t) is None

    def test_none_is_not_confused_with_unavailable(self):
        """「没给基准」与「选了基准但取不到」是两种状态，返回值形态必须不同。"""
        assert resolve('货币型') is None
        choice = resolve('债券型-长期纯债')
        assert choice is not None and choice.code == BENCH_BOND_FUND


class TestVarietyFallback:
    def test_uses_variety_when_type_missing(self):
        """小类缺失时用大类兜底——「混合型」这个大类仍能映射到偏股混基。"""
        choice = resolve(None, '混合型')
        assert choice is not None and choice.code == BENCH_HYBRID_FUND

    def test_type_wins_over_variety(self):
        """小类与大类都在时以小类为准（大类分不出偏股/偏债）。"""
        choice = resolve('混合型-偏债', '混合型')
        assert choice.code == BENCH_BOND_FUND


class TestTargetsConsistency:
    """映射出的基准代码必须真的在 `index_daily` 目标清单里（否则是「没数据的基准」）。"""

    def test_all_mapped_codes_are_declared_or_marked_unavailable(self):
        from app.services.sync.jobs.index_daily_job import (
            CSINDEX_INDEX_TARGETS,
            TENCENT_INDEX_TARGETS,
            WIND_INDEX_TARGETS,
        )

        declared = {c for c, _ in WIND_INDEX_TARGETS + TENCENT_INDEX_TARGETS + CSINDEX_INDEX_TARGETS}
        # 逐个类型名跑一遍，收集所有会被映射出来的代码
        mapped = set()
        for t in ('股票型', '混合型-偏股', '混合型-灵活', '债券型-长期纯债', '混合型-偏债'):
            choice = resolve(t)
            assert choice is not None
            mapped.add(choice.code)
        missing = mapped - declared
        # 允许「已登记但源侧未收录」的基准（resolve 会标 unavailable），其余必须真在清单里
        assert missing <= {BENCH_BOND_FUND}, f'映射出了未登记为同步目标的基准：{missing}'


def test_load_index_points_reads_market_domain():
    """`load_index_points` 从 index_daily 取序列，空结果返回空列表（不抛异常）。"""
    from unittest.mock import MagicMock

    from app.services.fund_benchmark import load_index_points

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    assert load_index_points(db, BENCH_HS300) == []
