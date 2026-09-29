# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/12 22:13
# File : test_symbol_utils.py
"""全面测试证券代码标准化工具 StockCodeNormalizer"""

import pytest

from app.core.symbol_utils import (
    StockCodeNormalizer,
    derive_security_type,
    get_normalizer,
    market_of_cn_a_code,
    symbol_identity,
)
from app.core.venues import EXCHANGE, NO_VENUE, OTC, get_venue_label, venue_of_row


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

    def test_fund_11xxxx_with_market_prefix(self, normalizer):
        """带 `SZ` 前缀的 11xxxx 才是深市货基（#1661：裸码不许再猜深市）。"""
        norm, market, stype = normalizer.normalize('SZ119931')
        assert norm == 'SZ119931'
        assert market == 'SZ'
        assert stype == 'money_fund'

    @pytest.mark.parametrize(
        'code',
        ['110067', '110081', '111000', '113050', '113052', '118000', '119931'],
    )
    def test_bare_11xxxx_is_shanghai_convertible_bond(self, normalizer, code):
        """#1661 反向用例：裸 11xxxx 必须归**沪市可转债**，不得发成深市货基。

        原 `SPECIAL_CODES` 的 `^11[1-9]\\d{3}$ → SZ/money_fund` 抢在主模式之前，
        把沪市 111xxx/113xxx/118xxx/119xxx 段转债判成深市货币基金（实测 10 只样本误判 7 只），
        与同文件的 `market_of_cn_a_code()` / `derive_security_type()` 自相矛盾，
        且公司债/转债导入后拿错交易所前缀（`SZ113050` 南银转债）→ 价格链路取不到行情。
        """
        norm, market, stype = normalizer.normalize(code)
        assert (norm, market, stype) == (f'SH{code}', 'SH', 'bond')
        # 与同文件的市场消歧口径保持一致（防止两条规则再次分叉）
        assert market_of_cn_a_code(code) == 'SH'
        assert derive_security_type(code, 'SH') == 'bond'

    def test_sz_10xxxx_still_money_fund(self, normalizer):
        """防过度抑制：带 `SZ` 前缀的 10xxxx 仍是深市货基，未被上面的收紧误伤。"""
        norm, market, stype = normalizer.normalize('SZ100016')
        assert norm == 'SZ100016'
        assert market == 'SZ'
        assert stype == 'money_fund'


class TestSingleton:
    """全局单例测试"""

    def test_singleton(self):
        norm1 = get_normalizer()
        norm2 = get_normalizer()
        assert norm1 is norm2


class TestVenueOfRow:
    """`venue_of_row`（#1662 后续）：存量行的 venue 解析 —— 显式 > 场内货基特例 > asset_type。"""

    def test_declared_venue_wins(self):
        assert venue_of_row('004369', 'fund', OTC) == OTC
        assert venue_of_row('SZ004369', 'fund', EXCHANGE) == EXCHANGE

    def test_declared_venue_is_case_insensitive(self):
        assert venue_of_row('004369', 'fund', 'otc') == OTC

    def test_illegal_declared_venue_degrades_instead_of_raising(self):
        """存量脏值只降级不抛错 —— 审计脚本要能把它们报出来，不能在审计途中崩掉。"""
        assert venue_of_row('004369', 'fund', 'BROKER') == OTC

    def test_asset_type_inference(self):
        assert venue_of_row('004369', 'fund') == OTC
        assert venue_of_row('SZ159915', 'etf') == EXCHANGE

    def test_sh_exchange_money_fund_beats_asset_type_default(self):
        """场内货基是 `asset_type → venue` 唯一一处缺省必然判错的例外，须显式纠偏。"""
        assert venue_of_row('SH970164', 'money_fund') == EXCHANGE
        # 同码段的场外货基仍走缺省（裸码即场外）
        assert venue_of_row('970164', 'money_fund') == OTC

    def test_unknown_asset_type_yields_no_venue(self):
        assert venue_of_row('004369', None) == NO_VENUE
        assert venue_of_row('MGR_001', 'manager') == NO_VENUE

    def test_get_venue_label_is_case_insensitive(self):
        assert get_venue_label('otc') == '场外'
        assert get_venue_label(EXCHANGE) == '场内'
        assert get_venue_label('') == ''
        assert get_venue_label('BROKER') == 'BROKER'


class TestSymbolIdentity:
    """`symbol_identity`（#1662 后续）：归一身份键 —— `positions.symbol_norm` 的构造。

    本类**最重要的一组断言是「同一只基金的多种写法必须收敛到同一个身份」**：
    那正是 #1662「同一基金两行」的根因（字面量唯一约束挡不住写法变体）。
    """

    @pytest.mark.parametrize(
        'raw',
        ['004369', 'SZ004369', 'sz004369', ' SZ004369 ', 'SH.004369', '004369.SZ'],
    )
    def test_otc_fund_writing_variants_converge_to_one_identity(self, raw):
        """场外基金的写法变体（前缀 / 大小写 / 空白 / 分隔符）全部收敛到同一身份。"""
        assert symbol_identity(raw, 'fund') == 'OTC:004369'

    def test_otc_bare_code_has_no_prefix(self):
        assert symbol_identity('004369', 'fund') == 'OTC:004369'

    def test_exchange_gets_market_prefix(self):
        assert symbol_identity('SZ159915', 'etf') == 'EXCHANGE:SZ159915'
        assert symbol_identity('600519', 'stock') == 'EXCHANGE:SH600519'
        assert symbol_identity('sh600519', 'stock') == 'EXCHANGE:SH600519'

    def test_exchange_writing_variants_converge(self):
        """场内：大小写 / 空白 / 缺前缀（asset_type 已定为场内）也收敛。"""
        assert symbol_identity(' sz159915 ', 'etf') == symbol_identity('SZ159915', 'etf') == 'EXCHANGE:SZ159915'
        assert symbol_identity('159915', 'etf') == 'EXCHANGE:SZ159915'

    def test_money_fund_venue_depends_on_asset_type_not_code(self):
        """`asset_type` 是**必需**入参：`SH970164`（场内货基）与 `970164`（场外货基）
        代码段相同、场所不同，只看 symbol 无法区分 —— 必须给出不同身份。"""
        assert symbol_identity('SH970164', 'money_fund') == 'EXCHANGE:SH970164'
        assert symbol_identity('970164', 'money_fund') == 'OTC:970164'
        assert symbol_identity('SH970164', 'money_fund') != symbol_identity('970164', 'money_fund')

    def test_no_venue_entities_keep_their_own_namespace(self):
        assert symbol_identity('MGR_001', 'manager') == 'NO_VENUE:MGR_001'
        assert symbol_identity('CSI000300', 'index') == 'NO_VENUE:CSI000300'
        assert symbol_identity('ZH012345', 'portfolio') == 'NO_VENUE:ZH012345'

    def test_explicit_venue_overrides_asset_type(self):
        """显式 venue 优先（写入侧本来就知道场所，不该被 asset_type 缺省覆盖）。"""
        assert symbol_identity('SZ004369', 'fund', venue=EXCHANGE) == 'EXCHANGE:SZ004369'

    def test_unknown_asset_type_does_not_guess_venue(self):
        """判不出场所时进 `NO_VENUE` 命名空间，**绝不**猜成场外（不猜是本模块的红线）。"""
        assert symbol_identity('004369', None) == 'NO_VENUE:004369'
        assert symbol_identity('SZ004369', None) == 'NO_VENUE:SZ004369'

    def test_empty_symbol_yields_empty_identity(self):
        """空 symbol 返回空串，而不是 `NO_VENUE:` —— 否则一堆空行会互撞唯一约束。"""
        assert symbol_identity('', 'fund') == ''
        assert symbol_identity('   ', 'fund') == ''
        assert symbol_identity(None, 'fund') == ''

    def test_pure_function_is_stable(self):
        """纯函数（只读 symbol + asset_type）：重复调用结果一致，`before_update` 重算才幂等。"""
        first = symbol_identity('SZ004369', 'fund')
        assert all(symbol_identity('SZ004369', 'fund') == first for _ in range(5))
