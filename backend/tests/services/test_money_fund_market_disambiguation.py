# -*- coding: utf-8 -*-
"""#1661 货基判定的品种/市场维度回归测试。

被覆盖的缺陷：货基判定链路丢失「品种 / 交易所」维度，只看归一化后的 6 位数字，
于是**股票、场外基金、沪市可转债**被判为货币基金；该标记落 `positions.is_money_fund`
后被 `sync/jobs/position_price_job.py:293` 优先采信，按面值 1.0000 回写 `current_price`
（持仓市值塌成「份额数」）。

用例分三类（缺一不可，见 AGENTS.md「静态审计器会悄悄给错答案」的教训）：
- **反向**：旧实现会给出 True 的场景，现在必须是 False；
- **正向**：真货基仍然判真（防「一刀切改成 False」的假修）；
- **防过度抑制**：名字里带「货币/现金」但其实是普通基金/证券的，不得被扩大化。
"""

import pytest

from app.services.fund_utils import is_money_fund_symbol, normalize_fund_code
from app.services.position_service import _resolve_money_fund_flag

pytestmark = pytest.mark.usefixtures('app')


@pytest.fixture(autouse=True)
def _clear_money_fund_cache():
    """`fund_utils._cache` 是**模块级全局**缓存：不清会让前一个用例的名录结论污染后一个。"""
    from app.services import fund_utils

    fund_utils._cache.clear()
    yield
    fund_utils._cache.clear()


@pytest.fixture
def market_db(app):
    """market 域会话（`app` 夹具已把它重定向到内存库）。"""
    from app.core.db_factory import market_session_factory

    session = market_session_factory()()
    yield session
    session.close()


def _seed_fund(market_db, code: str, name: str, type_name: str | None):
    """往 market 域名录塞一只基金；`type_name=None` 模拟 `fund_type_id` 为空。"""
    from app.domains.funds.models import Fund, FundType

    type_id = None
    if type_name is not None:
        row = market_db.query(FundType).filter_by(name=type_name).one_or_none()
        if row is None:
            row = FundType(name=type_name)
            market_db.add(row)
            market_db.flush()
        type_id = row.id
    market_db.add(Fund(fund_code=code, name=name, fund_type_id=type_id))
    market_db.commit()


# ══════════════════════════════════════════════════════════════════════
# 一、反向：旧实现判真、现在必须判假
# ══════════════════════════════════════════════════════════════════════


def test_stock_not_money_fund_even_when_code_collides_with_money_fund(market_db):
    """`000651` 既是格力电器（深市股票）也是某只货基 —— 显式 stock 必须判假。

    原实现：`_resolve_money_fund_flag` 丢传 `asset_type`，落到 `is_money_fund_symbol(symbol)`
    查名录命中「货币型」→ True → 持仓按面值 1.0000 计价。
    """
    _seed_fund(market_db, '000651', '某货基B', '货币型')
    assert _resolve_money_fund_flag('SZ000651', 'stock', None) is False
    assert _resolve_money_fund_flag('000651', 'stock', None) is False
    # 同一个代码作为「基金」时仍应判真（命名空间由 asset_type 决定，不是由数字决定）
    assert _resolve_money_fund_flag('000651', 'fund', None) is True


@pytest.mark.parametrize('symbol', ['SH110081', 'SH113050', 'SH110067'])
def test_shanghai_convertible_bond_not_money_fund(symbol):
    """沪市可转债落在 `1[01]xxxx` 段内，但不是货币基金。

    `SH110081` 闻泰转债、`SH113050` 南银转债、`SH110067` 华安转债 —— 原实现因
    `_CODE_FALLBACK_RE = ^(?:1[01]\\d{4}|97\\d{4})$` 无交易所维度而全部判真。
    """
    assert _resolve_money_fund_flag(symbol, 'bond', None) is False
    assert is_money_fund_symbol(symbol, 'bond') is False


def test_otc_fund_in_1xxxx_segment_not_money_fund(market_db):
    """`110001` 易方达平稳增长混合、`100016` 富国天源沪港深平衡混合 落在 `1[01]xxxx` 段内。

    实测：本机 `funds` 名录中命中该段的 106 个代码里 **0 个**是货币型。
    """
    _seed_fund(market_db, '110001', '易方达平稳增长混合', '混合型')
    _seed_fund(market_db, '100016', '富国天源沪港深平衡混合A', None)
    assert _resolve_money_fund_flag('110001', 'fund', None) is False
    # 名录有记录但 fund_type_id 为空 → 类型未知，不猜
    assert _resolve_money_fund_flag('100016', 'fund', None) is False


def test_bare_code_without_exchange_prefix_never_guessed():
    """名录无该代码时，裸 6 位数字不得靠代码段猜货基（场外编码与交易所段无关）。"""
    assert is_money_fund_symbol('110001') is False
    assert is_money_fund_symbol('100016') is False
    assert is_money_fund_symbol('001010') is False


@pytest.mark.parametrize('symbol', ['110001', '111000', '119931', '110003'])
def test_bare_code_in_1xxxx_segment_not_money_fund(symbol):
    """裸码 + 名录无记录：`110/111/119xxxx` 被消歧为**沪市**，而沪市现金管理段只有 `97xxxx`。

    「目录代码段兜底必须先判交易所」的最小守卫：一旦退回「按归一化 6 位数字匹配
    `1[01]xxxx`」（原 `_CODE_FALLBACK_RE` 写法），本组四条会全部变红——这四条恰恰是
    沪市可转债与场外基金代码，旧实现把它们全判成货基。
    """
    assert is_money_fund_symbol(symbol) is False
    assert _resolve_money_fund_flag(symbol, 'fund', None) is False


def test_market_record_of_other_type_vetoes_code_segment(market_db):
    """名录**有**该代码但非「货币型」→ 可否决代码段兜底（名录是唯一权威）。

    `SZ101234` 命中深市货基段，而名录登记为「混合型」。若名录失去否决权
    （退回 `命中集 or 代码段`），本用例变红。
    """
    _seed_fund(market_db, '101234', '某场外混合基金', '混合型')
    assert is_money_fund_symbol('SZ101234') is False
    assert _resolve_money_fund_flag('SZ101234', 'fund', None) is False


def test_market_record_without_type_vetoes_code_segment(market_db):
    """名录有该代码但 `fund_type_id` 为空 → 类型未知**不猜**，同样否决代码段。"""
    _seed_fund(market_db, '101235', '某类型缺失基金', None)
    assert is_money_fund_symbol('SZ101235') is False


# ══════════════════════════════════════════════════════════════════════
# 二、正向：真货基必须仍然判真
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ('code', 'name'),
    [
        ('000198', '天弘余额宝货币'),
        ('001010', '易方达增金宝货币市场基金A类'),
        ('003003', '华夏现金增利证券投资基金'),
        ('001937', '兴银现金增利'),
        ('100025', '富国天时货币A'),
    ],
)
def test_real_money_fund_still_true(market_db, code, name):
    """名录标为「货币型」的场外货基仍判真（含名字里没有「货币」的 `001937` 兴银现金增利）。"""
    _seed_fund(market_db, code, name, '货币型')
    assert _resolve_money_fund_flag(code, 'fund', None) is True


def test_explicit_money_fund_type_always_true():
    """显式 `asset_type='money_fund'` 直接判真，不看代码也不查名录。"""
    assert _resolve_money_fund_flag('000651', 'money_fund', None) is True
    assert is_money_fund_symbol('SH110081', 'money_fund') is True


@pytest.mark.parametrize('symbol', ['SZ111000', 'SZ100016'])
def test_sz_prefixed_money_fund_segment_fallback(symbol):
    """名录无该代码时，带 `SZ` 前缀的 `1[01]xxxx` 仍走代码段兜底判真。"""
    assert is_money_fund_symbol(symbol) is True


def test_sh_prefixed_cash_management_segment_fallback():
    """带 `SH` 前缀的 `97xxxx`（沪市现金管理产品）仍走代码段兜底判真。"""
    assert is_money_fund_symbol('SH970164') is True


def test_hint_beats_everything():
    """显式 hint（含 False）优先于类型与名录解析。"""
    assert _resolve_money_fund_flag('001010', 'fund', True) is True
    assert _resolve_money_fund_flag('001010', 'money_fund', False) is False


# ══════════════════════════════════════════════════════════════════════
# 三、防过度抑制：不许把普通证券/基金扩大化误伤
# ══════════════════════════════════════════════════════════════════════


def test_sz_convertible_bond_not_money_fund():
    """深市可转债 `12xxxx` 不得命中深市货基段。"""
    assert is_money_fund_symbol('SZ128145', 'bond') is False
    assert is_money_fund_symbol('SZ123111') is False


def test_etf_not_money_fund():
    """普通 ETF 与场内货基 ETF 都按场内处理（有连续竞价价格，不走面值 1.0000）。"""
    assert is_money_fund_symbol('SH510300', 'etf') is False
    assert is_money_fund_symbol('SZ159915', 'etf') is False


def test_market_unreachable_degrades_without_raising(monkeypatch):
    """market 域不可达时降级为代码段兜底、不抛错，也不把「查不到」固化成结论。"""

    def boom():
        raise RuntimeError('market 域不可达')

    monkeypatch.setattr('app.core.db_factory.market_session_factory', boom)
    assert is_money_fund_symbol('SZ111000') is True  # 带前缀 → 代码段兜底仍成立
    assert is_money_fund_symbol('110001') is False  # 裸码 → 不猜


def test_cache_is_keyed_by_code_not_by_symbol_form(market_db):
    """同一代码的不同形态（`SZ004369` / `004369`）必须得到一致结论，缓存不得互相污染。"""
    _seed_fund(market_db, '004369', '前海开源聚财宝B', '货币型')
    assert is_money_fund_symbol('SZ004369') is True
    assert is_money_fund_symbol('004369') is True
    assert normalize_fund_code('SZ004369') == '004369'


# ══════════════════════════════════════════════════════════════════════
# 四、端到端：标记落库 + 价格任务落桶
# ══════════════════════════════════════════════════════════════════════


def _post_buy(client, symbol: str, name: str, asset_type: str):
    return client.post(
        '/api/positions/',
        json={
            'symbol': symbol,
            'name': name,
            'type': asset_type,
            'market': 'CN_A',
            'account_name': '测试',
            'quantity': 100,
            'avg_price': 40,
            'currency': 'CNY',
            'trade_date': '2026-05-01',
            'op_type': 'buy',
        },
    )


@pytest.mark.parametrize(
    ('symbol', 'name', 'asset_type', 'bucket'),
    [
        ('000651', '格力电器', 'stock', 'intraday'),
        ('110081', '闻泰转债', 'bond', 'intraday'),
    ],
)
def test_created_position_is_not_flagged_money_fund(client, db, market_db, symbol, name, asset_type, bucket):
    """端到端：建仓后 `is_money_fund` 必须为假，且价格任务不得归入货基桶。

    价格任务 `_classify` 只要看到 `is_money_fund is True` 就返回 `'money_fund'`，
    随后按 `MONEY_FUND_FACE_VALUE = 1.0000` 回写 `current_price`。
    """
    from app.domains.positions.models import Position
    from app.services.sync.jobs.position_price_job import PositionPriceSyncJob

    # 制造最坏的撞号：名录里存在同号「货币型」基金
    _seed_fund(market_db, normalize_fund_code(symbol), '同号货基', '货币型')

    resp = _post_buy(client, symbol, name, asset_type)
    assert resp.status_code == 200, resp.get_json()

    position = db.query(Position).order_by(Position.id.desc()).first()
    assert position is not None
    assert position.asset_type == asset_type
    assert position.is_money_fund is False, '证券持仓被标记为货币基金 → 价格会按面值 1.0000 回写'
    assert PositionPriceSyncJob._classify(None, position) == bucket
