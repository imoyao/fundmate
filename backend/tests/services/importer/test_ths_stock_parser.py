# tests/services/importer/test_ths_stock_parser.py
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from app.core.venues import EXCHANGE, OTC
from app.services.importer.parsers.ths_stock import THSStockParser

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


# 真实样本暂不使用，因为集成测试依赖旧解析器生成 CSV，此处跳过
# FIXTURE_PATH = BASE_DIR / "tests" / "fixtures" / "ths_sample.csv"


class TestTHSStockParserRowLogic:
    """测试 _parse_row 核心解析逻辑"""

    @pytest.fixture
    def parser(self):
        return THSStockParser()

    def _make_series(self, **kwargs):
        """构造同花顺格式的 Series，列名用中文（原始列名），值按需覆盖"""
        defaults = {
            '证券代码': '600519',
            '证券名称': '测试股票',
            '操作': '证券买入',
            '成交数量': '100',
            '成交均价': '1650.00',
            '成交金额': '165000.00',
            '发生金额': '-165015.00',
            '佣金': '5.00',
            '印花税': '8.50',
            '过户费': '1.00',
            '其他杂费': '0.50',
            '币种': 'CNY',
            '交收日期': '20220101',
            '合同编号': '123',
            'fee': '15.00',  # 模拟 parse() 合并后的总费用
        }
        defaults.update(kwargs)
        return pd.Series(defaults)

    def test_parse_buy(self, parser):
        """买入：金额应为发生金额绝对值（已含费）"""
        row = self._make_series()
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.business_type == 'buy'
        assert record.symbol == 'SH600519'
        assert record.shares == Decimal('100')
        assert record.nav == Decimal('1650.00')
        assert record.fee == Decimal('15.00')
        # 买入金额 = abs(发生金额) = 165015
        assert record.amount == Decimal('165015.00')

    # ── 费用拆分（#2137）────────────────────────────────
    def test_parse_buy_carries_fee_breakdown(self, parser):
        """交割单四列费用明细逐类透传（佣金/印花税/过户费/其他杂费）。"""
        row = self._make_series()
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.fee_commission == Decimal('5.00')
        assert record.fee_stamp_duty == Decimal('8.50')
        assert record.fee_transfer_fee == Decimal('1.00')
        assert record.fee_other == Decimal('0.50')

    def test_parse_fee_breakdown_missing_column_falls_back_unsplit(self, parser):
        """源文件缺任一费用列（老模板）→ 整体回落未拆分（四列全 None），不按 0 编。"""
        row = self._make_series()
        del row['过户费']
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.fee_commission is None
        assert record.fee_stamp_duty is None
        assert record.fee_transfer_fee is None
        assert record.fee_other is None
        # 聚合 fee 仍是合并值（存量行为不变）
        assert record.fee == Decimal('15.00')

    def test_parse_zero_fee_rows_keep_zero_breakdown(self, parser):
        """分红等零费用行：四列在且均为 0（显式 0 ≠ 未拆分）。"""
        row = self._make_series(
            操作='红利入账',
            成交数量='0',
            成交均价='0',
            成交金额='0',
            发生金额='500.00',
            佣金='0',
            印花税='0',
            过户费='0',
            其他杂费='0',
            fee='0',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.fee_commission == Decimal('0')
        assert record.fee_stamp_duty == Decimal('0')
        assert record.fee_transfer_fee == Decimal('0')
        assert record.fee_other == Decimal('0')

    def test_parse_sell(self, parser):
        """卖出：金额应为发生金额本身（到账金额）"""
        row = self._make_series(
            操作='证券卖出',
            成交金额='80000.00',
            发生金额='79985.00',
            佣金='3.00',
            印花税='10.00',
            过户费='1.00',
            其他杂费='1.00',
            fee='15.00',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.business_type == 'sell'
        # 卖出金额 = 发生金额 = 79985
        assert record.amount == Decimal('79985.00')

    def test_parse_dividend(self, parser):
        """分红：发生金额直接取绝对值"""
        row = self._make_series(
            操作='红利入账',
            成交数量='0',
            成交均价='0',
            成交金额='0',
            发生金额='500.00',
            佣金='0',
            印花税='0',
            过户费='0',
            其他杂费='0',
            fee='0',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.business_type == 'dividend_cash'
        assert record.amount == Decimal('500.00')

    def test_contract_id_format(self, parser):
        assert parser._format_contract_id('123') == '0000000123'
        assert parser._format_contract_id(None) == ''
        assert parser._format_contract_id('') == ''

    def test_parse_money_fund(self, parser):
        """银河水星现金添利应被识别为 money_fund"""
        row = self._make_series(
            证券代码='970164',
            证券名称='银河水星现金添利',
            操作='基金申购拨出',
            成交数量='0',
            成交均价='0',
            成交金额='0',
            发生金额='-10000',
            佣金='0',
            印花税='0',
            过户费='0',
            其他杂费='0',
            fee='0',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.asset_type == 'money_fund', f'期望 money_fund，实际 {record.asset_type}'
        assert record.symbol == 'SH970164'

    # ── 无代码收益行的类型兜底（#2843）────────────────────
    #
    # 同花顺对「券商自己不给代码」的收益行，会把 证券代码 / 证券名称 两列留空。
    # 这类行走不到 normalizer，以前一律掉进 `else: asset_type = 'stock'`：
    # 显示成股票、计入投资收益、又因 symbol 为空被判「代码未匹配」而勾不上。

    def test_parse_fund_dividend_without_code_is_money_fund(self, parser):
        """基金红利拨入（无代码）→ money_fund，不是 stock

        依据：开发库中同源的 12 笔历史流水全部是 asset_type='money_fund'
        + position_name='银河水星现金添利' + symbol=NULL（970164 的月度收益结转）。
        """
        row = self._make_series(
            证券代码='',
            证券名称='',
            操作='基金红利拨入',
            成交数量='0',
            成交均价='0',
            成交金额='0',
            发生金额='2.10',
            佣金='0',
            印花税='0',
            过户费='0',
            其他杂费='0',
            fee='0',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.asset_type == 'money_fund', f'期望 money_fund，实际 {record.asset_type}'
        assert record.business_type == 'dividend_cash'
        assert record.symbol == ''
        assert record.amount == Decimal('2.10')

    def test_parse_fund_dividend_with_code_keeps_normalizer_type(self, parser):
        """带代码的基金红利仍由 normalizer 定类型，兜底不外溢。

        970164 → money_fund（本来就是这个类型）；带股票代码的同类行走
        suggested_type → stock。判据：THS_NO_CODE_INCOME_ASSET_TYPES 只在
        `suggested_type` 缺失时才生效，不会把「有代码的行」也一律推成货基。
        """
        money_fund_row = self._make_series(
            证券代码='970164',
            证券名称='银河水星现金添利',
            操作='基金红利拨入',
            成交数量='0',
            成交均价='0',
            成交金额='0',
            发生金额='2.10',
            佣金='0',
            印花税='0',
            过户费='0',
            其他杂费='0',
            fee='0',
        )
        rec = parser._parse_row(money_fund_row, line_num=2)
        assert rec is not None
        assert rec.asset_type == 'money_fund'
        assert rec.symbol == 'SH970164'

        # 有代码 ⇒ 以 normalizer 的 suggested_type 为准，兜底表不参与
        stock_row = self._make_series(
            证券代码='603327',
            证券名称='福蓉科技',
            操作='基金红利拨入',
            成交数量='0',
            成交均价='0',
            成交金额='0',
            发生金额='100.00',
            佣金='0',
            印花税='0',
            过户费='0',
            其他杂费='0',
            fee='0',
        )
        rec2 = parser._parse_row(stock_row, line_num=3)
        assert rec2 is not None
        assert rec2.asset_type == 'stock', f'有代码时不该被兜底表覆盖，实际 {rec2.asset_type}'

    def test_parse_interest_income_without_code_stays_cash(self, parser):
        """利息归本（无代码）→ cash：两融利息没有标的，不该被 #2843 的改动带偏。"""
        row = self._make_series(
            证券代码='',
            证券名称='',
            操作='利息归本',
            成交数量='0',
            成交均价='0',
            成交金额='0',
            发生金额='0.90',
            佣金='0',
            印花税='0',
            过户费='0',
            其他杂费='0',
            fee='0',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.asset_type == 'cash'
        assert record.business_type == 'dividend_cash'

    def test_parse_reverse_repo(self, parser):
        """GC007 应被识别为 reverse_repo"""
        row = self._make_series(
            证券代码='204001',
            证券名称='GC007',
            操作='通用回购逆回',
            成交数量='10',
            成交均价='2.5',
            成交金额='10000',
            发生金额='-10000',
            佣金='0',
            印花税='0',
            过户费='0',
            其他杂费='0',
            fee='0',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.asset_type == 'reverse_repo', f'期望 reverse_repo，实际 {record.asset_type}'
        assert record.symbol == 'SH204001'

    # ── venue（#1662）────────────────────────────────
    def test_open_fund_subscription_is_otc_with_bare_code(self, parser):
        """场外开放式基金申购 → venue=OTC，代码落**裸 6 位**（不得加交易所前缀）。"""
        row = self._make_series(
            证券代码='004369',
            证券名称='前海开源聚财宝B',
            操作='开放基金申购',
            成交数量='0',
            成交均价='0',
            成交金额='0',
            发生金额='-10000',
            佣金='0',
            印花税='0',
            过户费='0',
            其他杂费='0',
            fee='0',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.venue == OTC, f'期望 OTC，实际 {record.venue!r}'
        assert record.symbol == '004369', f'场外必须落裸码，实际 {record.symbol}'
        assert record.asset_type == 'fund'

    def test_otc_fund_code_never_gets_exchange_prefix(self, parser):
        """反向：场外申购的 1xxxxx 码不得被推成 SH 前缀（沪市转债段）。

        误判链示例（#1662）：场外货基 `121011` 曾被推成 `SZ121011` → 当成深市可转债。
        """
        row = self._make_series(
            证券代码='110081',
            证券名称='某场外基金',
            操作='开放基金申购',
            成交数量='0',
            成交均价='0',
            成交金额='0',
            发生金额='-10000',
            佣金='0',
            印花税='0',
            过户费='0',
            其他杂费='0',
            fee='0',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.symbol == '110081', f'场外禁猜交易所，实际 {record.symbol}'
        assert not record.symbol.startswith(('SH', 'SZ', 'BJ'))

    def test_security_buy_is_exchange(self, parser):
        """正向：证券买入属场内 → venue=EXCHANGE。"""
        record = parser._parse_row(self._make_series(), line_num=2)
        assert record is not None
        assert record.venue == EXCHANGE

    def test_exchange_money_fund_keeps_prefix_and_venue(self, parser):
        r"""防过度抑制：`基金申购拨出` 的 970164 属 SH 场内货基段，**不得**当场外处理。

        970164 命中 `^97\d{4}$`（SH 场内货基），当场外会剥掉 SH 前缀 → 场内货基误判。
        这也是 THS_OTC_OPS 刻意只收 `开放基金申购` 的原因。
        """
        row = self._make_series(
            证券代码='970164',
            证券名称='银河水星现金添利',
            操作='基金申购拨出',
            成交数量='0',
            成交均价='0',
            成交金额='0',
            发生金额='-10000',
            佣金='0',
            印花税='0',
            过户费='0',
            其他杂费='0',
            fee='0',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.venue == EXCHANGE, f'970164 属场内货基，实际 {record.venue!r}'
        assert record.symbol == 'SH970164'
        assert record.asset_type == 'money_fund'


class TestTHSStockParserIntegration:
    """集成测试：完整 parse 流程"""

    @pytest.fixture
    def parser(self):
        return THSStockParser()

    def test_parse_cash_transfer_integration(self, parser):
        """资金划转集成测试"""
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t发生金额\t'
            '佣金\t印花税\t过户费\t其他杂费\t币种\t交收日期\t合同编号\n'
            '\t\t银行转证券\t0\t0\t0\t100000\t0\t0\t0\t0\tCNY\t20220101\t\n'
        )
        records, _ = parser.parse(csv_content.encode('gbk'))
        assert len(records) == 1
        assert records[0].asset_type == 'cash'
        assert records[0].business_type == 'deposit'

    def test_parse_empty_file(self, parser):
        records, errors = parser.parse(b'')
        assert len(records) == 0
        assert len(errors) == 1

    def test_parse_real_csv_sample(self, parser):
        """使用 Tab 分隔的 UTF-8 样本进行集成测试"""
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t发生金额\t佣金\t印花税\t过户费\t其他杂费\t合同编号\t交收日期\n'
            '600519\t测试股票\t证券买入\t100\t1650.00\t165000.00\t-165015.00\t5.00\t8.50\t1.00\t0.50\t123\t20220101\n'
        )
        records, _ = parser.parse(csv_content.encode('utf-8'))
        assert len(records) == 1
        assert records[0].fee == Decimal('15.00')
        assert records[0].transaction_id == '0000000123'

    def test_parse_integration_carries_fee_breakdown(self, parser):
        """#2137：完整 parse 流程（DataFrame 路径）费用四列明细幸存。"""
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t发生金额\t佣金\t印花税\t过户费\t其他杂费\t合同编号\t交收日期\n'
            '600519\t测试股票\t证券买入\t100\t1650.00\t165000.00\t-165015.00\t5.00\t8.50\t1.00\t0.50\t123\t20220101\n'
        )
        records, errors = parser.parse(csv_content.encode('utf-8'))
        assert len(errors) == 0
        assert len(records) == 1
        r = records[0]
        assert r.fee == Decimal('15.00')
        assert r.fee_commission == Decimal('5.00')
        assert r.fee_stamp_duty == Decimal('8.50')
        assert r.fee_transfer_fee == Decimal('1.00')
        assert r.fee_other == Decimal('0.50')


class TestFeeGapFallback:
    """费用列缺失时用「发生金额 − 成交额」差额兜补手续费（2026-11-02）。

    口径来自用户决策：不按费率估算（本仓 ledgers.fee_config 16 个账户全为空，
    估出来是假精度），而是「实际多付/少收的钱就是手续费」——交割单能算出来的实测值。

    反向约束同样重要：方向不符 / 差额过大时**不推导**，让校验层照旧报错，
    否则真错误（金额录错、数量单位错）会被静默吃成手续费。
    """

    @pytest.fixture
    def parser(self):
        return THSStockParser()

    FEE_COLS = ('佣金', '印花税', '过户费', '其他杂费')

    def _row_without_fee_columns(self, **kwargs):
        """模拟交割单没有费用列：四列与合并 fee 全部缺席。"""
        defaults = {
            '证券代码': '600519',
            '证券名称': '测试股票',
            '操作': '证券买入',
            '成交数量': '100',
            '成交均价': '1650.00',
            '成交金额': '165000.00',
            '发生金额': '-165015.00',
            '币种': 'CNY',
            '交收日期': '20220101',
            '合同编号': '123',
        }
        defaults.update(kwargs)
        return pd.Series(defaults)

    def test_buy_derives_fee_from_positive_gap(self, parser):
        """买入：发生额 165015 − 成交额 165000 = 15 → fee 15。"""
        row = self._row_without_fee_columns()
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.fee == Decimal('15.0')
        # 四列仍为未拆分：推导值只进聚合 fee，不伪造明细归属
        assert record.fee_commission is None

    def test_sell_derives_fee_from_negative_gap(self, parser):
        """卖出：发生额 79985 − 成交额 80000 = −15 → fee 15（卖到账已扣费）。"""
        row = self._row_without_fee_columns(
            操作='证券卖出',
            成交均价='800.00',
            成交金额='80000.00',
            发生金额='79985.00',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.business_type == 'sell'
        assert record.fee == Decimal('15.0')

    def test_wrong_direction_is_not_treated_as_fee(self, parser):
        """买入却「少付」：方向不符说明不是费用（金额录错），不推导。"""
        row = self._row_without_fee_columns(发生金额='-164985.00')
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.fee == Decimal('0')

    def test_gap_over_ratio_cap_is_not_treated_as_fee(self, parser):
        """差额 15000 / 成交额 165000 = 9% > 5% 上限，判为数据错误，不推导。"""
        row = self._row_without_fee_columns(发生金额='-180000.00')
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.fee == Decimal('0')

    def test_explicit_breakdown_wins_over_gap(self, parser):
        """四列有值（15）而差额 100：以交割单为准，不覆盖。"""
        row = pd.Series(
            {
                '证券代码': '600519',
                '证券名称': '测试股票',
                '操作': '证券买入',
                '成交数量': '100',
                '成交均价': '1650.00',
                '成交金额': '165000.00',
                '发生金额': '-165100.00',
                '佣金': '5.00',
                '印花税': '8.50',
                '过户费': '1.00',
                '其他杂费': '0.50',
                'fee': '15.00',  # 真实链路由 _preprocess_dataframe 合并四列得出
                '交收日期': '20220101',
                '合同编号': '123',
            }
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.fee == Decimal('15.00')
        assert record.fee_commission == Decimal('5.00')

    def test_falls_back_to_shares_times_price_without_trade_amount(self, parser):
        """没有「成交金额」列时用 数量 × 均价 作差额基准。"""
        row = self._row_without_fee_columns()
        del row['成交金额']
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.fee == Decimal('15.0')

    def test_dividend_row_not_affected(self, parser):
        """非买卖行（分红）不参与推导：本来就没有成交对手方。"""
        row = self._row_without_fee_columns(
            操作='红利入账',
            成交数量='0',
            成交均价='0',
            成交金额='0',
            发生金额='500.00',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.business_type == 'dividend_cash'
        assert record.fee == Decimal('0')

    def test_integration_derives_fee_through_full_parse(self, parser):
        """端到端：交割单没有费用列时，走完整 parse() 也能补出手续费。

        WHY 单独一条：`_parse_row` 直调绕过了 `_preprocess_dataframe`（那里会给
        缺失的 fee 列补 0.0）。真实链路必须先经过它，推导才有可能被触发或误触发。
        """
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t发生金额\t合同编号\t交收日期\n'
            '600519\t测试股票\t证券买入\t100\t1650.00\t165000.00\t-165015.00\t123\t20220101\n'
        )
        records, errors = parser.parse(csv_content.encode('utf-8'))
        assert len(errors) == 0
        assert len(records) == 1
        assert records[0].fee == Decimal('15.0')
        # 推导值不伪造明细归属：四列仍是未拆分
        assert records[0].fee_commission is None
