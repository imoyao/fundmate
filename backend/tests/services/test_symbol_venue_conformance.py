# -*- coding: utf-8 -*-
"""#1662 回归：venue（交易场所）维度 —— 同一标的不得因「写法不同」并存两行。

卡面问题：`positions` 的唯一约束是**字面量** `UNIQUE(ledger_id, symbol)`，历史上同一只
场外基金并存 `SZ004369` 与 `004369` 两种写法（本机实测 2 组）。根因是归一化器**靠 6 位
数字猜交易所**——场外基金代码与交易所代码段共用同一数字空间（本机 `securities` 名录里与
某只货基 6 位数字完全相同的证券有 111 条），猜必错。修法：**写入侧由入口显式传 venue，
归一化器不许猜**（见 `app/core/venues.py`）。

用例分三类（项目约定：正向 / 反向 / 防过度抑制）：
- 正向：显式 venue 生效；场外归一到裸码、场内归一到带前缀；
- 反向：场外路径**禁止**交易所推断；跨形态写法必须复用同一行、不得新增重复持仓；
- 防过度抑制：同一 6 位码在场内 / 场外是**不同标的**（`000651` 格力电器 vs 场外基金），
  场所不同不得互相复用；venue 判不出时也不得因为过滤条件而漏掉既有持仓。
"""

from decimal import Decimal

import pytest

from app.core.money import Money
from app.core.symbol_utils import normalize_by_venue, strip_exchange_prefix
from app.core.venues import (
    EXCHANGE,
    NO_VENUE,
    OTC,
    VENUE_VALUES,
    asset_types_of_venue,
    normalize_venue,
    resolve_venue,
    venue_of_asset_type,
)
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.services.position_service import PositionService, _find_existing_position


# ── 辅助 ──────────────────────────────────────────────
def _ledger_id(db, name='测试账户'):
    ledger = db.query(Ledger).filter_by(name=name, family_id=1).first()
    if not ledger:
        ledger = Ledger(name=name, ledger_type='bank', family_id=1)
        db.add(ledger)
        db.flush()
    return ledger.id


def _holding_data(ledger_id, symbol, *, venue=None, qty='100', price='1.0', asset_type='fund'):
    data = {
        'symbol': symbol,
        'name': '测试基金',
        'asset_type': asset_type,
        'ledger_id': ledger_id,
        'family_id': 1,
        'quantity': Decimal(qty),
        'avg_price': Decimal(price),
        'source': 'e_account_holding',
    }
    if venue is not None:
        data['venue'] = venue
    return data


def _buy_data(ledger_id, symbol, *, venue=None, qty='10', price='1.0', asset_type='fund'):
    data = {
        'symbol': symbol,
        'name': '测试标的',
        'asset_type': asset_type,
        'ledger_id': ledger_id,
        'family_id': 1,
        'quantity': Decimal(qty),
        'avg_price': Decimal(price),
        'op_type': 'buy',
        'source': 'manual',
    }
    if venue is not None:
        data['venue'] = venue
    return data


# ── A. venue 取值与推断（正向）────────────────────────
@pytest.mark.parametrize('asset_type', ['fund', 'money_fund', 'FUND', 'fund '])
def test_asset_type_fund_family_defaults_to_otc(asset_type):
    """缺省推断：基金 / 货基 → 场外（场内 LOF、场内货基是例外，必须显式传 venue）。"""
    assert venue_of_asset_type(asset_type) == OTC


@pytest.mark.parametrize('asset_type', ['stock', 'etf', 'bond', 'reverse_repo'])
def test_asset_type_exchange_family_defaults_to_exchange(asset_type):
    assert venue_of_asset_type(asset_type) == EXCHANGE


@pytest.mark.parametrize('asset_type', ['manager', 'portfolio', 'index', '', None, 'nonsense'])
def test_asset_type_without_venue_is_empty(asset_type):
    """无交易场所实体 / 未知类型 → 空串，绝不猜。"""
    assert venue_of_asset_type(asset_type) == NO_VENUE


def test_explicit_venue_beats_asset_type_inference():
    """显式入参优先：入口本来就知道场内 / 场外，不许被 asset_type 覆盖。"""
    assert resolve_venue(OTC, 'stock') == OTC
    assert resolve_venue(EXCHANGE, 'fund') == EXCHANGE
    assert resolve_venue('otc', 'stock') == OTC  # 大小写归一


def test_missing_venue_falls_back_to_asset_type():
    assert resolve_venue(None, 'fund') == OTC
    assert resolve_venue('', 'etf') == EXCHANGE
    assert resolve_venue(None, None) == NO_VENUE


def test_invalid_venue_raises_instead_of_silently_misstoring():
    """非法 venue 宁可报错，也不落错形态。"""
    with pytest.raises(ValueError):
        normalize_venue('SH')
    with pytest.raises(ValueError):
        resolve_venue('SH', 'stock')


def test_venue_values_are_exactly_the_two_declared_kinds():
    assert VENUE_VALUES == (EXCHANGE, OTC)


def test_exchange_venue_covers_money_fund_for_read_back():
    """防过度抑制（读侧）：场内货基资产类型是货基却属交易所（`^97\\d{4}$`）。

    EXCHANGE 的反查集合必须**双向覆盖** money_fund，否则 `_find_existing_position`
    找不到既有场内货基行 → 每次写入新建重复持仓。
    """
    assert 'money_fund' in asset_types_of_venue(EXCHANGE)
    assert 'money_fund' in asset_types_of_venue(OTC)
    # 注意：NO_VENUE 的反查集合是「无场所实体」，**非空** —— 写侧不能直接拿它当
    # 过滤条件，_find_existing_position 必须显式写 if venue else ()（见防过度抑制用例）。
    assert asset_types_of_venue(NO_VENUE) == ('manager', 'portfolio', 'index')


# ── B. symbol 归一（正向 + 反向）──────────────────────
@pytest.mark.parametrize(
    'raw',
    ['004369', 'SZ004369', 'sz004369', 'SH004369', 'BJ004369', 'sz.004369', 'SH:004369', '004369.SZ'],
)
def test_otc_symbol_always_converges_to_bare_code(raw):
    """正向：场外一律收敛到裸 6 位码 —— 任何前缀 / 分隔符写法都归一。

    这正是 #1662 本机重复行的根因形态（`SZ004369` 与 `004369` 并存）。
    """
    symbol, _market, _atype = normalize_by_venue(raw, OTC)
    assert symbol == '004369'


@pytest.mark.parametrize('raw', ['110081', '113050', '110067', '111000', '119931'])
def test_otc_never_guesses_exchange(raw):
    """反向：场外路径**禁止**交易所推断 —— 1xxxxx 在场外不得被推成 SH 前缀（沪市转债段）。

    误判链示例（#1662）：场外货基 `121011` 曾被推成 `SZ121011` → 当成深市可转债。
    """
    symbol, market, _atype = normalize_by_venue(raw, OTC)
    assert symbol == raw
    assert market == 'CN_A'
    assert not symbol.startswith(('SH', 'SZ', 'BJ'))


def test_exchange_symbol_gets_market_prefix():
    assert normalize_by_venue('600519', EXCHANGE)[:2] == ('SH600519', 'SH')
    assert normalize_by_venue('159915', EXCHANGE)[:2] == ('SZ159915', 'SZ')
    # 已带前缀 → 幂等
    assert normalize_by_venue('SH600519', EXCHANGE)[0] == 'SH600519'
    assert normalize_by_venue('SZ159915', EXCHANGE)[0] == 'SZ159915'


def test_strip_exchange_prefix_handles_prefix_and_separators():
    assert strip_exchange_prefix('SZ004369') == '004369'
    assert strip_exchange_prefix('004369') == '004369'
    assert strip_exchange_prefix('sz.004369') == '004369'
    assert strip_exchange_prefix('SH:004369') == '004369'
    assert strip_exchange_prefix('004369.SZ') == '004369'


# ── C. 写入侧去重（端到端，调真实函数）────────────────
def test_upsert_holding_reuses_prefixed_row_for_bare_symbol(db, make_position):
    """反向：既有行是带前缀写法时，裸码快照必须**复用同一行**，不得新增重复持仓。"""
    ledger_id = _ledger_id(db)
    make_position(
        symbol='SZ004369',
        name='前海开源聚财宝B',
        market='CN_A',
        asset_type='fund',
        ledger_id=ledger_id,
        quantity=50,
        avg_price=1.0,
        current_price=1.0,
    )
    PositionService.upsert_from_holding(db, _holding_data(ledger_id, '004369', venue=OTC, qty='100'))
    db.flush()

    rows = db.query(Position).filter(Position.ledger_id == ledger_id).all()
    assert len(rows) == 1, f'跨形态写法不得新增重复行，实际 {[r.symbol for r in rows]}'
    # SET 语义：命中的是同一行 → 份额被整条替换
    assert Money.min_unit_to_shares(rows[0].quantity) == Decimal('100')


def test_upsert_holding_normalizes_new_row_symbol(db):
    """正向：全新持仓按 venue 落规范形态（场外 → 裸码）。"""
    ledger_id = _ledger_id(db)
    PositionService.upsert_from_holding(db, _holding_data(ledger_id, 'SZ016462', venue=OTC, qty='100'))
    db.flush()
    rows = db.query(Position).filter(Position.ledger_id == ledger_id).all()
    assert [r.symbol for r in rows] == ['016462']


def test_buy_reuses_prefixed_row_for_otc_venue(db, make_position):
    """反向：场外申购遇到带前缀存量行时复用，不新增重复持仓。"""
    ledger_id = _ledger_id(db)
    make_position(
        symbol='SZ121011',
        name='国投瑞银货币A',
        market='CN_A',
        asset_type='fund',
        ledger_id=ledger_id,
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    PositionService.process_buy_or_deposit(db, _buy_data(ledger_id, 'SZ121011', venue=OTC))
    db.flush()
    rows = db.query(Position).filter(Position.ledger_id == ledger_id).all()
    assert len(rows) == 1, f'不得新增重复行，实际 {[r.symbol for r in rows]}'


def test_find_existing_without_venue_does_not_overfilter(db, make_position):
    """防过度抑制（回归）：venue 判不出时**必须**退回「同归一码即同标的」。

    曾因 `asset_types_of_venue('')` 返回非空集合 `(manager/portfolio/index)` 触发场所过滤，
    把真实持仓全滤掉 → 找不到既有行 → 每次写入都新建重复持仓（把 #1662 放大）。
    """
    ledger_id = _ledger_id(db)
    make_position(
        symbol='600519',
        name='贵州茅台',
        market='CN_A',
        asset_type='stock',
        ledger_id=ledger_id,
        quantity=100,
        avg_price=1800.0,
        current_price=1800.0,
    )
    found = _find_existing_position(db, ledger_id=ledger_id, family_id=1, symbol='600519', venue=NO_VENUE)
    assert found is not None, 'venue 为空时应按归一码命中既有持仓'


def test_find_existing_respects_venue_boundary(db, make_position):
    """防过度抑制：venue 明确时不得跨场所复用 —— 同一 6 位码场内 / 场外是不同标的。

    `000651` 既是格力电器（深市股票）也是某只场外基金：把场外申购合并进股票持仓，
    会把股票的成本 / 份额改写成基金的，属静默数据污染。
    """
    ledger_id = _ledger_id(db)
    make_position(
        symbol='SZ000651',
        name='格力电器',
        market='CN_A',
        asset_type='stock',
        ledger_id=ledger_id,
        quantity=100,
        avg_price=30.0,
        current_price=30.0,
    )
    assert _find_existing_position(db, ledger_id=ledger_id, family_id=1, symbol='000651', venue=OTC) is None
    assert _find_existing_position(db, ledger_id=ledger_id, family_id=1, symbol='000651', venue=EXCHANGE) is not None


def test_same_code_different_venue_coexist_as_two_rows(db, make_position):
    """防过度抑制：场外基金与场内股票同码时**必须**并存两行，不得互相吞并。"""
    ledger_id = _ledger_id(db)
    make_position(
        symbol='SZ000651',
        name='格力电器',
        market='CN_A',
        asset_type='stock',
        ledger_id=ledger_id,
        quantity=100,
        avg_price=30.0,
        current_price=30.0,
    )
    PositionService.process_buy_or_deposit(db, _buy_data(ledger_id, '000651', venue=OTC, asset_type='fund', qty='10'))
    db.flush()
    rows = db.query(Position).filter(Position.ledger_id == ledger_id).all()
    assert len(rows) == 2, f'不同场所是不同标的，必须并存，实际 {[r.symbol for r in rows]}'
    assert {r.symbol for r in rows} == {'SZ000651', '000651'}


def test_exchange_venue_finds_existing_money_fund_row(db, make_position):
    """防过度抑制（读侧回归）：场内货基（money_fund + EXCHANGE）必须能被场所过滤命中。"""
    ledger_id = _ledger_id(db)
    make_position(
        symbol='SH970164',
        name='银河水星现金添利',
        market='CN_A',
        asset_type='money_fund',
        ledger_id=ledger_id,
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    found = _find_existing_position(db, ledger_id=ledger_id, family_id=1, symbol='970164', venue=EXCHANGE)
    assert found is not None, '场内货基属 EXCHANGE，反查集合漏掉 money_fund 会导致重复建仓'


# ── D. 解析器 venue 声明（正向）────────────────────────
def test_parsers_declare_venue():
    """解析器**声明**场所：单一场所文件必须显式声明，混合场所文件留空逐行判定。"""
    from app.services.importer.parsers.alipay_fund import AlipayFundParser
    from app.services.importer.parsers.alipay_pdf import AlipayPDFParser
    from app.services.importer.parsers.e_account_holding import EAccountHoldingParser
    from app.services.importer.parsers.standard import FundStandardParser, StockStandardParser
    from app.services.importer.parsers.ths_stock import THSStockParser
    from app.services.importer.parsers.tiantian_fund import TiantianFundParser

    assert FundStandardParser.venue == OTC
    assert TiantianFundParser.venue == OTC  # 继承 FundStandardParser
    assert AlipayFundParser.venue == OTC
    assert AlipayPDFParser.venue == OTC
    assert EAccountHoldingParser.venue == OTC
    assert StockStandardParser.venue == EXCHANGE
    # 同花顺交割单：一文件内既有场内证券、也有场外开放式基金申赎 → 留空，逐行判定
    assert THSStockParser.venue == NO_VENUE


def test_ths_otc_ops_is_deliberately_narrow():
    """防过度抑制：THS 场外操作集合必须只含**有证据**的一条。

    `基金申购拨出` / `基金赎回拨入` / `基金红利拨入` 在真实样本里对应
    `970164 银河水星现金添利`（SH 场内货基段 `^97\\d{4}$`），把它们当场外会剥掉 SH 前缀
    → 场内货基误判（`test_parse_money_fund` 会把这条钉死）。
    """
    from app.services.importer.mappings import THS_OTC_OPS

    assert THS_OTC_OPS == frozenset({'开放基金申购'})
