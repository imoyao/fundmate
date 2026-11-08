# -*- coding: utf-8 -*-
"""招商交割单 × 打新折叠 × 申购代码别名：**端到端**集成用例。

前面的单测各测一段（`test_cms_stock_parser` 测行解析、`test_ipo_events` 测折叠纯逻辑、
`test_eastmoney_alias_resolver` 测 resolver 自身）。本文件把它们串成生产真实链路：

    GB18030 交割单字节
      → CMSStockParser.parse（表头定位 / 公式外壳剥离 / 手→张换算）
      → IpoEventFolder.finalize（N 行折叠成 1 条 buy；warm 批量引导）
      → EastMoneyAliasResolver（东财 `RPT_BOND_CB_LIST` 作引导源，假 http）
      → security_code_aliases 落库
      → 折叠出的 buy 记录带**上市代码**，无 link_warning

## 覆盖的四个判据

1. **别名命中**：申购码经引导源补全后，折叠记录直接是上市代码（成本可被日后卖出匹配）。
2. **本地优先**：落库后换一个新的 resolver 实例 + **断网**再解析，仍然命中且零联网——
   证明「东财只是一次性引导源，不是运行期依赖」这个承诺是真的，而不只是注释里写着。
3. **未命中不猜**：无网、库里也没有 → 保留申购码 + `link_warning`，且记录不被
   `validate` 丢掉（用户可在预览页改 `symbol` 补全）。
4. **优先级**：别名表 > 文件内唯一「新股入账」候选 > 告警。别名与文件内候选冲突时，
   以别名表为准（它是跨文件确认过的持久化事实）。

## 隐私

按 `test_cms_stock_parser.py` 的既有约定：**所有值均为虚构**（代码、名称、金额、
流水号、股东代码），只照搬真实导出的**结构**（21 列列序、`="..."` 公式外壳、尾部截断、
5~6 行打新链），不含任何真实账户信息。
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.database import SessionLocal
from app.services.importer.eastmoney_alias_resolver import EastMoneyAliasResolver
from app.services.importer.parsers.cms_stock import CMSStockParser

# ── 虚构标的：申购码取深市 370 段，上市码取深市转债 123 段（段位与真实样本同构）──
APPLY_CODE = '370181'
LISTED_CODE = '123291'
ALT_LISTED_CODE = '127999'
ANCHOR_DATE = '20221220'

HEADER = [
    '币种',
    '证券名称',
    '成交日期',
    '成交价格',
    '成交数量',
    '发生金额',
    '资金余额',
    '剩余数量',
    '合同编号',
    '流水号',
    '业务名称',
    '印花税',
    '佣金',
    '经手费',
    '证管费',
    '结算费',
    '过户费',
    '其他费用',
    '证券代码',
    '股东代码',
    '备注',
]


def q(value) -> str:
    """券商防科学计数法的 Excel 公式文本外壳。"""
    return f'="{value}"'


def row(**overrides) -> list:
    defaults = {
        '币种': '人民币',
        '证券名称': '',
        '成交日期': ANCHOR_DATE,
        '成交价格': q('0.0000'),
        '成交数量': q('0'),
        '发生金额': '0.00',
        '资金余额': q('0.00'),
        '剩余数量': q('0'),
        '合同编号': q('0'),
        '流水号': q('000000000001'),
        '业务名称': '证券买入',
        '印花税': q('0.00'),
        '佣金': q('0.00'),
        '经手费': q('0.00'),
        '证管费': q('0.00'),
        '结算费': q('0.00'),
        '过户费': q('0.00'),
        '其他费用': q('0.00'),
        '证券代码': '',
        '股东代码': q('0000000000'),
        '备注': '',
    }
    defaults.update(overrides)
    return [defaults[name] for name in HEADER]


def ipo_chain(*, with_credit: bool = False, credit_code: str = LISTED_CODE) -> list:
    """一笔中签的完整链（结构照搬真实样本，值全虚构）。

    净现金流 = 0 − 1000 − 1000 + 1000 + 0 = −1000 ⇒ 本金 1000、中签价 100 ⇒ 10 张。
    """
    rows = [
        row(
            证券名称='模拟发债',
            业务名称='市值申购中签',
            成交价格=q('100.0000'),
            成交数量=q('10'),
            成交日期='20221220',
            流水号=q('000000000101'),
            证券代码=APPLY_CODE,
        ),
        row(
            证券名称='模拟发债',
            业务名称='市值申购中签扣款',
            发生金额='-1000.00',
            成交日期='20221221',
            流水号=q('000000000102'),
            证券代码=APPLY_CODE,
        ),
        row(
            证券名称='模拟发债',
            业务名称='新股申购确认缴款',
            发生金额='-1000.00',
            成交日期='20221221',
            流水号=q('000000000103'),
            证券代码=APPLY_CODE,
        ),
        row(
            证券名称='模拟发债',
            业务名称='市值申购中签扣款回冲',
            发生金额='1000.00',
            成交日期='20221221',
            流水号=q('000000000104'),
            证券代码=APPLY_CODE,
        ),
        row(
            证券名称='模拟发债',
            业务名称='托管转出',
            成交日期='20221221',
            流水号=q('000000000105'),
            证券代码=APPLY_CODE,
        ),
    ]
    if with_credit:
        rows.append(
            row(
                证券名称='模拟转债',
                业务名称='新股入账',
                成交价格=q('100.0000'),
                成交数量=q('10'),
                成交日期='20221226',
                流水号=q('000000000106'),
                证券代码=credit_code,
            )
        )
    return rows


def to_file(rows) -> bytes:
    """21 列完整导出（含备注列）的 GB18030 制表符文本。"""
    lines = ['\t'.join(HEADER)] + ['\t'.join(cells) for cells in rows]
    return ('\n'.join(lines) + '\n').encode('gb18030')


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def fake_http(store, calls=None, fail=False):
    """东财 `RPT_BOND_CB_LIST` 的假实现；`fail=True` 模拟断网。"""

    def _get(url, params=None, headers=None, timeout=None):
        if calls is not None:
            calls.append((params or {}).get('pageNo', 1))
        if fail:
            raise RuntimeError('network down')
        if int((params or {}).get('pageNo', 1)) > 1:
            return FakeResp({'result': {'data': []}})
        data = [
            {'SECURITY_CODE': listed, 'CORRECODE': apply, 'PUBLIC_START_DATE': f'{issue} 00:00:00'}
            for apply, listed, issue in store
        ]
        return FakeResp({'result': {'data': data}})

    return _get


@pytest.fixture
def db_factory(app):
    """复用应用路由会话工厂——与生产 `cms_stock.py` 的默认接线一致。"""
    return SessionLocal


def make_parser(db_factory, http_get=None, enabled=True) -> CMSStockParser:
    resolver = EastMoneyAliasResolver(
        session_factory=db_factory,
        http_get=http_get or fake_http([], fail=True),
        enabled=enabled,
    )
    return CMSStockParser(alias_resolver=resolver)


class TestAliasHit:
    def test_bootstrap_fills_listed_code_and_folds_into_one_buy(self, db_factory):
        calls = []
        parser = make_parser(db_factory, fake_http([(APPLY_CODE, LISTED_CODE, '2022-12-20')], calls))
        records, errors = parser.parse(to_file(ipo_chain()))

        assert errors == []
        assert len(records) == 1
        rec = records[0]

        # 代码归一：折叠出来的建仓直接挂在上市代码下，日后卖出才能匹配成本。
        assert rec.symbol == f'SZ{LISTED_CODE}'
        assert rec.asset_type == 'bond'
        assert rec.link_warning in (None, '')
        assert parser.pending_alias_count == 0

        # 经济事实：本金取组内净额，份额取 本金 ÷ 中签价，沪市手/张差天然抹平。
        assert rec.business_type == 'buy'
        assert rec.amount == Decimal('1000')
        assert rec.net_amount == Decimal('1000')
        assert rec.trade_amount == Decimal('1000')
        assert rec.nav == Decimal('100')
        assert rec.shares == Decimal('10')
        assert rec.fee == Decimal('0')

        # 幂等键用事件维度，不依赖会被多行共用的券商流水号。
        assert rec.transaction_id == f'IPO-{ANCHOR_DATE}-{APPLY_CODE}'
        assert rec.trade_date == date(2022, 12, 21)
        assert parser.folded_event_count == 1
        # 引导只拉一页就够（假数据不足一页）。
        assert calls == [1]

    def test_row_count_identity_holds_after_folding(self, db_factory):
        parser = make_parser(db_factory, fake_http([(APPLY_CODE, LISTED_CODE, '2022-12-20')]))
        rows = ipo_chain() + [
            row(
                证券名称='模拟转债',
                业务名称='证券买入',
                成交价格=q('116.5000'),
                成交数量=q('80'),
                发生金额='-9329.32',
                佣金=q('8.95'),
                成交日期='20230105',
                流水号=q('000000000201'),
                证券代码='127001',
            )
        ]
        records, errors = parser.parse(to_file(rows))
        assert len(records) == 2
        # #2854：折叠消耗的 4 行计入 ignored，恒等式不因折叠而破。
        assert parser.source_row_count == len(records) + len(errors) + parser.ignored_row_count
        assert parser.ignored_row_count == 4


class TestLocalFirst:
    def test_second_import_is_offline_and_still_resolves(self, db_factory):
        """落库后再导入：新实例 + 断网仍命中，且**零联网**——本地优先不是注释里的口号。"""
        first_calls = []
        make_parser(db_factory, fake_http([(APPLY_CODE, LISTED_CODE, '2022-12-20')], first_calls)).parse(
            to_file(ipo_chain())
        )
        assert first_calls == [1]

        offline_calls = []
        parser = make_parser(db_factory, fake_http([], offline_calls, fail=True))
        records, errors = parser.parse(to_file(ipo_chain()))

        assert errors == []
        assert records[0].symbol == f'SZ{LISTED_CODE}'
        assert records[0].link_warning in (None, '')
        # 已落库 ⇒ warm 判定 known，根本不发请求（断网也测不出失败）。
        assert offline_calls == []


class TestUnresolved:
    def test_no_alias_and_no_credit_keeps_apply_code_with_warning(self, db_factory):
        parser = make_parser(db_factory)
        records, errors = parser.parse(to_file(ipo_chain()))

        assert errors == []
        assert len(records) == 1
        rec = records[0]

        # 纪律：候选不唯一/不存在时绝不猜，保留申购码并显式告警。
        assert APPLY_CODE in rec.symbol
        assert rec.link_warning and '上市代码' in rec.link_warning
        # 跨层契约：前端 ProductCell.vue 用这个前缀决定「代码可否就地编辑」并同步
        # 资产类型（改成 11x/12x 时把 type 从 stock 纠正为 bond）。改文案会让补全闭环
        # 静默失效——只在有测试锁住时才算契约。
        assert rec.link_warning.startswith('打新中签建仓')
        assert parser.pending_alias_count == 1
        assert parser.folded_event_count == 1

        # 告警不等于丢弃：记录仍可通过 validate，用户可在预览页把 symbol 改对。
        valid, verrors = parser.validate(records)
        assert verrors == []
        assert valid == [rec]

        # 行数对账在「未命中」路径同样成立。
        assert parser.source_row_count == len(records) + len(errors) + parser.ignored_row_count

    def test_disabled_switch_skips_network_entirely(self, db_factory):
        calls = []
        parser = make_parser(db_factory, fake_http([(APPLY_CODE, LISTED_CODE, '2022-12-20')], calls), enabled=False)
        records, _ = parser.parse(to_file(ipo_chain()))
        assert calls == []  # IMPORTER__EASTMONEY_ALIAS=0 时一次都不联网
        assert records[0].link_warning


class TestPriority:
    def test_default_wiring_uses_eastmoney_resolver_not_null(self):
        """不注入时默认接东财引导源——若有人改回 NullAliasResolver，本用例转红。

        刻意不断言 ``enabled`` 的布尔值：它由 `IMPORTER__EASTMONEY_ALIAS` 环境变量
        决定，CI 里可能显式关掉；断言「类型 + 有 session_factory + 有 warm」即可，
        这三者才是「默认会尝试引导」的实质。
        """
        parser = CMSStockParser()
        assert isinstance(parser.alias_resolver, EastMoneyAliasResolver)
        assert parser.alias_resolver._session_factory is not None
        assert callable(parser.alias_resolver.warm)

    def test_in_file_unique_credit_row_used_when_alias_missing(self, db_factory):
        """无别名表时，文件内唯一的「新股入账」候选可自动采用（折叠器优先级 2）。"""
        parser = make_parser(db_factory)
        records, errors = parser.parse(to_file(ipo_chain(with_credit=True)))

        assert errors == []
        assert len(records) == 1
        assert records[0].symbol == f'SZ{LISTED_CODE}'
        assert records[0].link_warning in (None, '')
        # 入账行的上市简称更准，名称应对齐到它。
        assert records[0].name == '模拟转债'

    def test_persisted_alias_wins_over_in_file_credit(self, db_factory):
        """别名表是跨文件确认过的事实，与文件内候选冲突时以它为准（优先级 1 > 2）。"""
        parser = make_parser(db_factory, fake_http([(APPLY_CODE, ALT_LISTED_CODE, '2022-12-20')]))
        records, _ = parser.parse(to_file(ipo_chain(with_credit=True, credit_code=LISTED_CODE)))
        assert records[0].symbol == f'SZ{ALT_LISTED_CODE}'
        assert records[0].link_warning in (None, '')
