# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/12 22:13
# File : test_symbol_utils.py
"""全面测试证券代码标准化工具 StockCodeNormalizer"""

import pytest

from app.core.symbol_utils import StockCodeNormalizer, get_normalizer


@pytest.fixture
def normalizer():
    return StockCodeNormalizer()


class TestNormalizeHK:
    """港股标准化测试"""

    def test_hk_with_prefix(self, normalizer):
        norm, market, _ = normalizer.normalize('HK00700')
        assert norm == 'HK00700'
        assert market == 'HK'

    def test_hk_with_suffix_dot_hk(self, normalizer):
        norm, market, _ = normalizer.normalize('00700.HK')
        assert norm == 'HK00700'
        assert market == 'HK'

    def test_hk_pure_digits_five(self, normalizer):
        norm, market, _ = normalizer.normalize('00700')
        assert norm == 'HK00700'
        assert market == 'HK'

    def test_hk_short_digits(self, normalizer):
        norm, market, _ = normalizer.normalize('700')
        assert norm == 'HK00700'
        assert market == 'HK'

    def test_hk_short_with_prefix(self, normalizer):
        norm, market, _ = normalizer.normalize('HK700')
        assert norm == 'HK00700'
        assert market == 'HK'

    def test_hk_lowercase(self, normalizer):
        norm, market, _ = normalizer.normalize('hk00700')
        assert norm == 'HK00700'
        assert market == 'HK'

    def test_hk_single_digit(self, normalizer):
        norm, market, _ = normalizer.normalize('1')
        assert norm == 'HK00001'
        assert market == 'HK'

    def test_hk_pure_digits_too_long(self, normalizer):
        # 超过5位数字不符合港股规则，应返回 None
        norm, market, _ = normalizer.normalize('123456')
        assert norm == 'SZ123456'
        assert market == 'SZ'


class TestNormalizeSH:
    """上交所标准化测试"""

    def test_sh_with_prefix(self, normalizer):
        norm, market, _ = normalizer.normalize('SH600519')
        assert norm == 'SH600519'
        assert market == 'SH'

    def test_sh_with_suffix(self, normalizer):
        norm, market, _ = normalizer.normalize('600519.SH')
        assert norm == 'SH600519'
        assert market == 'SH'

    def test_sh_pure_digits_six(self, normalizer):
        norm, market, _ = normalizer.normalize('600519')
        assert norm == 'SH600519'
        assert market == 'SH'

    def test_sh_etf(self, normalizer):
        norm, market, _ = normalizer.normalize('510050')
        assert norm == 'SH510050'
        assert market == 'SH'

    def test_sh_star_market(self, normalizer):
        norm, market, _ = normalizer.normalize('688001')
        assert norm == 'SH688001'
        assert market == 'SH'

    def test_sh_lowercase(self, normalizer):
        norm, market, _ = normalizer.normalize('sh600519')
        assert norm == 'SH600519'
        assert market == 'SH'

    def test_sh_convertible_bond(self, normalizer):
        norm, market, _ = normalizer.normalize('110067')
        assert norm == 'SH110067'
        assert market == 'SH'


class TestNormalizeSZ:
    """深交所标准化测试"""

    def test_sz_with_prefix(self, normalizer):
        norm, market, _ = normalizer.normalize('SZ000001')
        assert norm == 'SZ000001'
        assert market == 'SZ'

    def test_sz_with_suffix(self, normalizer):
        norm, market, _ = normalizer.normalize('000001.SZ')
        assert norm == 'SZ000001'
        assert market == 'SZ'

    def test_sz_pure_digits(self, normalizer):
        norm, market, _ = normalizer.normalize('000001')
        assert norm == 'SZ000001'
        assert market == 'SZ'

    def test_sz_gem(self, normalizer):
        norm, market, _ = normalizer.normalize('300750')
        assert norm == 'SZ300750'
        assert market == 'SZ'

    def test_sz_lowercase(self, normalizer):
        norm, market, _ = normalizer.normalize('sz000001')
        assert norm == 'SZ000001'
        assert market == 'SZ'


class TestNormalizeBJ:
    """北交所标准化测试"""

    def test_bj_with_prefix(self, normalizer):
        norm, market, _ = normalizer.normalize('BJ920185')
        assert norm == 'BJ920185'
        assert market == 'BJ'

    def test_bj_with_suffix(self, normalizer):
        norm, market, _ = normalizer.normalize('920185.BJ')
        assert norm == 'BJ920185'
        assert market == 'BJ'

    def test_bj_pure_digits(self, normalizer):
        norm, market, _ = normalizer.normalize('920185')
        assert norm == 'BJ920185'
        assert market == 'BJ'

    def test_bj_eight_head(self, normalizer):
        norm, market, _ = normalizer.normalize('830001')
        assert norm == 'BJ830001'
        assert market == 'BJ'


class TestNormalizeUS:
    """美股标准化测试"""

    def test_us_plain_code(self, normalizer):
        norm, market, _ = normalizer.normalize('AAPL')
        assert norm == 'US:AAPL'
        assert market == 'US'

    def test_us_with_dot_us_suffix(self, normalizer):
        norm, market, _ = normalizer.normalize('AAPL.US')
        assert norm == 'US:AAPL'
        assert market == 'US'

    def test_us_with_prefix(self, normalizer):
        norm, market, _ = normalizer.normalize('US:AAPL')
        assert norm == 'US:AAPL'
        assert market == 'US'

    def test_us_with_special_char(self, normalizer):
        # 美股代码可包含点号
        norm, market, _ = normalizer.normalize('BRK.B')
        assert norm == 'US:BRK.B'
        assert market == 'US'

    def test_us_with_hint(self, normalizer):
        norm, market, _ = normalizer.normalize('AAPL', hint_market='US')
        assert norm == 'US:AAPL'
        assert market == 'US'

    def test_us_unknown_with_hint(self, normalizer):
        # 即使代码不符合模式，也能用 hint 强制
        norm, market, _ = normalizer.normalize('XYZ', hint_market='US')
        assert norm == 'US:XYZ'
        assert market == 'US'


class TestNormalizeCrypto:
    """加密货币标准化测试"""

    def test_crypto_with_hint(self, normalizer):
        norm, market, _ = normalizer.normalize('BTC', hint_market='CRYPTO')
        assert norm == 'CRYPTO:BTC'
        assert market == 'CRYPTO'

    def test_crypto_with_prefix(self, normalizer):
        norm, market, _ = normalizer.normalize('CRYPTO:BTC')
        assert norm == 'CRYPTO:BTC'
        assert market == 'CRYPTO'

    def test_crypto_eth_with_hint(self, normalizer):
        norm, market, _ = normalizer.normalize('ETH', hint_market='CRYPTO')
        assert norm == 'CRYPTO:ETH'
        assert market == 'CRYPTO'

    def test_crypto_without_hint(self, normalizer):
        # 无 hint，纯字母代码被识别为美股
        norm, market, _ = normalizer.normalize('BTC')
        assert norm == 'US:BTC'
        assert market == 'US'


class TestNormalizeEdgeCases:
    """边缘情况测试"""

    def test_empty_string(self, normalizer):
        norm, market, _ = normalizer.normalize('')
        assert norm is None
        assert market is None

    def test_none_input(self, normalizer):
        norm, market, _ = normalizer.normalize(None)
        assert norm is None
        assert market is None

    def test_whitespace_input(self, normalizer):
        norm, market, _ = normalizer.normalize('    ')
        assert norm is None
        assert market is None

    def test_unknown_format(self, normalizer):
        norm, market, _ = normalizer.normalize('INVALID')
        # 无效格式，可能被识别为美股（纯字母）
        # 根据规则，美股匹配纯字母，所以会返回 "US:INVALID"
        norm, market, _ = normalizer.normalize('INVALID')
        assert norm == 'US:INVALID'
        assert market == 'US'

    def test_hint_override_ambiguous(self, normalizer):
        # 5位数字默认港股，但用 SH hint 应识别为沪市
        norm, market, _ = normalizer.normalize('12345', hint_market='SH')
        # 实际规则：hint 转换时，会提取数字并补齐6位，前缀为 hint_market
        # 但 hint 强制转换要求 hint_market 不是 HK 且数字长度<=6，应该会转换成 SH012345
        assert norm == 'SH012345'
        assert market == 'SH'


class TestConversionMethods:
    """输出格式转换方法测试"""

    def test_to_xalpha_code_hk(self, normalizer):
        assert normalizer.to_xalpha_code('HK00700') == 'HK00700'

    def test_to_xalpha_code_sh(self, normalizer):
        assert normalizer.to_xalpha_code('SH600519') == 'SH600519'

    def test_to_xalpha_code_sz(self, normalizer):
        assert normalizer.to_xalpha_code('SZ000001') == 'SZ000001'

    def test_to_xalpha_code_us(self, normalizer):
        assert normalizer.to_xalpha_code('US:AAPL') == 'AAPL'

    def test_to_xalpha_code_crypto(self, normalizer):
        assert normalizer.to_xalpha_code('CRYPTO:BTC') == 'BTC'

    def test_to_display_code_hk(self, normalizer):
        assert normalizer.to_display_code('HK00700') == '00700.HK'

    def test_to_display_code_sh(self, normalizer):
        assert normalizer.to_display_code('SH600519') == '600519'

    def test_to_display_code_us(self, normalizer):
        assert normalizer.to_display_code('US:AAPL') == 'AAPL'

    def test_to_akshare_code_sh(self, normalizer):
        assert normalizer.to_akshare_code('SH600519') == '600519'

    def test_to_akshare_code_sz(self, normalizer):
        assert normalizer.to_akshare_code('SZ000001') == '000001'

    def test_to_akshare_code_hk(self, normalizer):
        assert normalizer.to_akshare_code('HK00700') == '00700'

    def test_get_market_name(self, normalizer):
        assert normalizer.get_market_name('HK') == '港股'
        assert normalizer.get_market_name('SH') == '上交所'
        assert normalizer.get_market_name('SZ') == '深交所'
        assert normalizer.get_market_name('BJ') == '北交所'
        assert normalizer.get_market_name('US') == '美股'
        assert normalizer.get_market_name('CRYPTO') == '加密货币'
        assert normalizer.get_market_name('XX') is None


class TestBatchNormalize:
    """批量标准化测试"""

    def test_batch(self, normalizer):
        codes = ['HK00700', '600519', 'AAPL']
        result = normalizer.normalize_batch(codes)
        assert result['HK00700'] == ('HK00700', 'HK', None)
        assert result['600519'] == ('SH600519', 'SH', None)
        assert result['AAPL'] == ('US:AAPL', 'US', None)

    def test_batch_with_hint(self, normalizer):
        codes = ['BTC', 'ETH']
        result = normalizer.normalize_batch(codes, hint_market='CRYPTO')
        assert result['BTC'] == ('CRYPTO:BTC', 'CRYPTO', None)
        assert result['ETH'] == ('CRYPTO:ETH', 'CRYPTO', None)


class TestSpecialCodeRecognition:
    """券商现金管理产品、逆回购等特殊代码识别测试"""

    def test_money_fund_97xxxx(self, normalizer):
        """970164 应识别为沪市现金理财"""
        norm, market, stype = normalizer.normalize('970164')
        assert norm == 'SH970164'
        assert market == 'SH'
        assert stype == 'money_fund'

    def test_reverse_repo_1318xx(self, normalizer):
        """131801 应识别为深市逆回购"""
        norm, market, stype = normalizer.normalize('131801')
        assert norm == 'SZ131801'
        assert market == 'SZ'
        assert stype == 'reverse_repo'

    def test_reverse_repo_204xxx(self, normalizer):
        """204001 应识别为沪市逆回购"""
        norm, market, stype = normalizer.normalize('204001')
        assert norm == 'SH204001'
        assert market == 'SH'
        assert stype == 'reverse_repo'

    def test_money_fund_97xxxx_with_prefix(self, normalizer):
        """SH970164 也应按规则识别（通过前缀直接匹配）"""
        norm, market, stype = normalizer.normalize('SH970164')
        # 原逻辑会走常规匹配（6位数字，5开头），识别为沪市股票，但无特殊类型
        assert norm == 'SH970164'
        assert market == 'SH'
        assert stype == 'money_fund'

    def test_normal_stock_not_affected(self, normalizer):
        """正常股票代码不应被特殊识别影响"""
        norm, market, stype = normalizer.normalize('600519')
        assert norm == 'SH600519'
        assert market == 'SH'
        assert stype is None

    def test_edge_case_970000_not_confused(self, normalizer):
        """边缘情况：970000 如果存在，也应按规则识别"""
        norm, market, stype = normalizer.normalize('970000')
        assert norm == 'SH970000'
        assert market == 'SH'
        assert stype == 'money_fund'

    def test_fund_11xxxx(self, normalizer):
        """119931 应识别为深市基金"""
        norm, market, stype = normalizer.normalize('119931')
        assert norm == 'SZ119931'
        assert market == 'SZ'
        assert stype == 'money_fund'


class TestSingleton:
    """全局单例测试"""

    def test_singleton(self):
        norm1 = get_normalizer()
        norm2 = get_normalizer()
        assert norm1 is norm2
