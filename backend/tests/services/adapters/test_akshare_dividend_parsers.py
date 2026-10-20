# backend/tests/services/adapters/test_akshare_dividend_parsers.py
"""#541 回归：分红/配股上游字段解析。

上游把口径写在**中文字符串**里（「每10份派现金0.0500元」「10配3.0」），解析错了
不会报错，只会静默算出 0 或错一个数量级——故这里逐条钉住。
"""

from app.services.adapters.akshare_adapter import AkshareAdapter


class TestFundDividendPerShare:
    def test_parses_per_share_from_per_10_shares(self):
        """「每10份派现金0.0500元」→ 每份 0.005 元（除以 10，不是原样返回）。"""
        assert AkshareAdapter._parse_fund_div_per_share('每10份派现金0.0500元') == 0.005

    def test_parses_without_cash_word(self):
        assert AkshareAdapter._parse_fund_div_per_share('每10份派0.1元') == 0.01

    def test_unparsable_returns_none_not_zero(self):
        """解析不出来必须返回 None——返回 0 会被下游当成「不分红」静默吞掉。"""
        assert AkshareAdapter._parse_fund_div_per_share(None) is None
        assert AkshareAdapter._parse_fund_div_per_share('每10份送1份') is None
        assert AkshareAdapter._parse_fund_div_per_share('') is None


class TestRightsRatio:
    def test_parses_common_forms(self):
        assert AkshareAdapter._parse_rights_ratio('10配3.0') == 3.0
        assert AkshareAdapter._parse_rights_ratio('10配2.8') == 2.8
        assert AkshareAdapter._parse_rights_ratio('10 配 10.0') == 10.0

    def test_unparsable_returns_none(self):
        assert AkshareAdapter._parse_rights_ratio(None) is None
        assert AkshareAdapter._parse_rights_ratio('--') is None


class TestStockDividendSymbolForm:
    """#541 实测：巨潮接口只认裸 6 位码，带前缀会返回缺列空表。

    真因藏在报错里——它写成 `KeyError: '实施方案公告日期'`，完全指不到
    「代码带了前缀」这件事，表现为「这只股票的历年分红一条都抓不到」。
    """

    def test_prefix_is_stripped_before_calling_upstream(self, monkeypatch):
        import pandas as pd

        import app.services.adapters.akshare_adapter as mod

        seen = {}

        class _FakeAk:
            @staticmethod
            def stock_dividend_cninfo(symbol):
                seen['symbol'] = symbol
                return pd.DataFrame(
                    [
                        {
                            '除权日': '2026-07-16',
                            '送股比例': None,
                            '转增比例': None,
                            '派息比例': 4.2,
                            '股权登记日': '2026-07-15',
                            '派息日': '2026-07-16',
                            '股份到账日': None,
                            '实施方案分红说明': '10派4.2元(含税)',
                            '分红类型': '年度分红',
                        }
                    ]
                )

        monkeypatch.setattr(mod.AkshareAdapter, 'fetch_stock_dividend', mod.AkshareAdapter.fetch_stock_dividend)
        monkeypatch.setitem(
            __import__('sys').modules,
            'app.core.akshare_lazy',
            type('m', (), {'get_akshare': staticmethod(lambda: _FakeAk)}),
        )

        adapter = mod.AkshareAdapter()
        out = adapter.fetch_stock_dividend('SH600000')
        assert seen['symbol'] == '600000', '传给上游的必须是裸 6 位码'
        assert out and out[0]['cash_ratio'] == 4.2
        assert out[0]['symbol'] == 'SH600000', '回来的事件仍要带前缀，与持仓同形态'


class TestUpstreamFailureIsNotSilenced:
    """#1179：上游异常必须向上抛，不能降级成空列表。

    空列表 = 「这只标的确实没有分红」；异常 = 「接口坏了」。两者在 job 层
    必须能区分——旧写法一律 `return []`，于是接口腐烂时 job 天天报 success。
    """

    def test_fund_dividend_raises_instead_of_returning_empty(self, monkeypatch):
        import sys

        import app.services.adapters.akshare_adapter as mod

        class _BoomAk:
            @staticmethod
            def fund_open_fund_info_em(**kwargs):
                raise RuntimeError('upstream broken')

        monkeypatch.setitem(
            sys.modules,
            'app.core.akshare_lazy',
            type('m', (), {'get_akshare': staticmethod(lambda: _BoomAk)}),
        )

        import pytest

        adapter = mod.AkshareAdapter()
        with pytest.raises(RuntimeError):
            adapter.fetch_fund_dividend('000001')
        with pytest.raises(RuntimeError):
            adapter.fetch_fund_split('000001')

    def test_stock_dividend_raises_instead_of_returning_empty(self, monkeypatch):
        import sys

        import pytest

        import app.services.adapters.akshare_adapter as mod

        class _BoomAk:
            @staticmethod
            def stock_dividend_cninfo(symbol):
                raise RuntimeError('upstream broken')

        monkeypatch.setitem(
            sys.modules,
            'app.core.akshare_lazy',
            type('m', (), {'get_akshare': staticmethod(lambda: _BoomAk)}),
        )

        adapter = mod.AkshareAdapter()
        with pytest.raises(RuntimeError):
            adapter.fetch_stock_dividend('600000')
