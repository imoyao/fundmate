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
    BENCH_BALANCED_HYBRID_FUND,
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
            ('混合型-平衡', BENCH_BALANCED_HYBRID_FUND),
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

    def test_平衡混合_benchmark_does_not_overclaim_balance(self):
        """平衡混合族改用中证混合型基金指数（#2476），展示名**不得**写成「平衡」。

        中证混合型基金指数比「平衡」宽（混含偏股/偏债/灵活）。若把展示名写成
        「平衡混合型基金指数」，就是用旧名字掩盖替换事实——用户无从分辨自己比的
        到底是同类平衡基金还是整个混合族。
        """
        choice = resolve('混合型-平衡')
        assert choice is not None
        assert choice.code == BENCH_BALANCED_HYBRID_FUND
        assert '平衡' not in choice.name


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
    """映射出的基准代码必须**真能取到序列**，而不是「在目标清单里就算数」（#2476）。

    旧判据只校验「代码出现在 `index_daily_job` 的目标清单里」，而 `885002.WI` 恰恰
    **在清单里、源侧却 0 行**——判据漏过的正是它自己（卡片原话：「清单里有、序列没有」）。
    现在改成按**规则表全集**判定，并叠加两条硬约束：
    ① 每个映射码都必须是同步目标；② 不得是 `KNOWN_UNLISTED`（已逐码实测取不到的码）。
    """

    @staticmethod
    def _mapped_codes():
        from app.services.fund_benchmark import _RULES

        return {code for _name, _needles, code in _RULES if code}

    def test_rules_table_is_not_empty(self):
        # 反向锚：规则表解析为空时，下面两条会「因为集合是空」而假绿
        assert self._mapped_codes(), '规则表解析为空——判据会假绿'

    def test_all_mapped_codes_are_sync_targets(self):
        from app.services.sync.jobs.index_daily_job import (
            CSINDEX_INDEX_TARGETS,
            TENCENT_INDEX_TARGETS,
            WIND_INDEX_TARGETS,
        )

        declared = {c for c, _ in WIND_INDEX_TARGETS + TENCENT_INDEX_TARGETS + CSINDEX_INDEX_TARGETS}
        missing = self._mapped_codes() - declared
        assert not missing, f'映射出了未登记为同步目标的基准：{sorted(missing)}'

    def test_no_mapped_code_is_known_unlisted(self):
        """映射不得指向「源侧确实未收录」的码——那是「选了一个我们没数据的基准」。

        本卡（#2476）的成因就是这条：`885002.WI` 既在目标清单里、又在 `KNOWN_UNLISTED` 里，
        映射照样指向它 ⇒ 前端只能显示「基准已选定但暂无数据」。
        变异探针：把 `BENCH_BALANCED_HYBRID_FUND` 改回 `'885002.WI'`，本用例必须转红。
        """
        from app.services.sync.jobs.index_daily_job import KNOWN_UNLISTED

        offenders = self._mapped_codes() & set(KNOWN_UNLISTED)
        assert not offenders, f'映射指向源侧未收录的代码：{sorted(offenders)}；前端会显示「基准已选定但暂无数据」'


def test_load_index_points_reads_market_domain():
    """`load_index_points` 从 index_daily 取序列，空结果返回空列表（不抛异常）。"""
    from unittest.mock import MagicMock

    from app.services.fund_benchmark import load_index_points

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    assert load_index_points(db, BENCH_HS300) == []
