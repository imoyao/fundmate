# -*- coding: utf-8 -*-
"""投资分档判据（``core/investment_tiers``）单测。

这一层的价值全在「表对不对」上：判据错一位，整条收益口径就错位，而且**不报错**——
用户看到的是三个看起来都合理的年化，只有它们加不上时才隐约不对。

故用例分三类：
1. **完备性 / 互斥性**：新增 asset_type 忘登记必须红，否则它会静默落进 other；
2. **关键归类的理由**被钉住（可转债归 active、银行理财不排除出投资收益）；
3. **与其它维度的边界**：货基标记优先于 asset_type、venue 不落 OTC、只允许 balance。
"""

from datetime import date
from types import SimpleNamespace

import pytest

from app.core.asset_types import ASSET_TYPE_LABELS, ASSET_TYPE_VALUES, EXCLUDED_ASSET_TYPES
from app.core.investment_tiers import (
    TIER_ACTIVE,
    TIER_LABELS,
    TIER_OTHER,
    TIER_SCOPES,
    TIER_STABLE,
    TIER_VALUES,
    tier_completeness,
    tier_of_asset_type,
    tier_of_position,
    unregistered_asset_types,
)
from app.core.venues import NO_VENUE, venue_of_asset_type
from app.domains.positions.models import Position
from app.services.position_service import _SPECIFIC_ASSET_TYPES, PositionService


# ───────────────────────── 完备性与互斥性 ─────────────────────────
def test_all_asset_types_are_registered():
    """每个 asset_type 都必须显式登记 tier。

    反向验证过：把 'bank_wealth' 从 ASSET_TYPE_TIER 删掉，本用例立刻红。
    这就是「新增品类忘登记」的唯一拦截点——落进 other 不会报错，只会让理财
    从主动投资口径里静默消失。
    """
    assert unregistered_asset_types() == ()


def test_tiers_are_mutually_exclusive_and_complete():
    """三档互斥（dict 天然保证）且完备（加总 == 全量）。

    互斥性不测「两档交集为空」——dict 的一个 key 只能有一个 tier，这一点由数据结构
    保证。真正会坏的是**完备性**：漏登记一个类型，它就掉出所有分档。
    """
    counts = tier_completeness()
    assert sum(counts.values()) == len(ASSET_TYPE_VALUES)
    assert counts[TIER_ACTIVE] > 0 and counts[TIER_STABLE] > 0 and counts[TIER_OTHER] > 0
    assert set(counts) == set(TIER_VALUES)


def test_tier_labels_and_scopes_cover_public_surface():
    """对外暴露的三个口径（主动 / 稳健 / 全账户）都要有中文标签来源。"""
    assert set(TIER_SCOPES) == {TIER_ACTIVE, TIER_STABLE, 'all'}
    assert 'all' not in TIER_VALUES, 'all 是口径而非分档，混进 TIER_VALUES 会让判据表多出一条假档'
    for tier in TIER_VALUES:
        assert TIER_LABELS[tier]


def test_unregistered_reports_missing_key_instead_of_passing_when_table_empty():
    """表整体为空时也必须报错（差集 vs 存在性检查）。

    「遍历已登记项断言非空」这类写法在表为空时反而通过——与 AGENTS.md
    「已登记类守卫禁止全文 includes」同一条教训。此处用差集，空表 → 全量未登记。
    """
    from app.core import investment_tiers as module

    original = module.ASSET_TYPE_TIER
    try:
        module.ASSET_TYPE_TIER = {}
        assert module.unregistered_asset_types() == ASSET_TYPE_VALUES
    finally:
        module.ASSET_TYPE_TIER = original


# ───────────────────────── 关键归类 ─────────────────────────
def test_bond_is_convertible_bond_so_it_belongs_to_active():
    """``bond`` 在本仓**特指可转债**，不是纯债，故归第一梯队。

    这是判据表里最容易读错的一行：看到 "bond" 就想归稳健，但可转债股性强、
    波动等同正股。若将来引入纯债，必须新增独立 asset_type，不能复用 bond。
    """
    assert ASSET_TYPE_LABELS['bond'] == '可转债'
    assert tier_of_asset_type('bond') == TIER_ACTIVE


def test_equity_types_are_active():
    for asset_type in ('stock', 'etf', 'fund', 'crypto', 'portfolio'):
        assert tier_of_asset_type(asset_type) == TIER_ACTIVE, asset_type


def test_stable_types_are_cash_and_wealth_management():
    for asset_type in ('money_fund', 'reverse_repo', 'bank_wealth', 'bank', 'cash'):
        assert tier_of_asset_type(asset_type) == TIER_STABLE, asset_type


def test_bank_wealth_not_excluded_from_investment():
    """银行理财是**投资**，不是现金等价物。

    这条是整张表最容易踩的坑：tier=stable 只表示「稳健梯队」，不表示「不计入投资」。
    若有人图省事把 bank_wealth 塞进 EXCLUDED_ASSET_TYPES，理财收益会被错算成
    「现金管理收益」，用户看到的年化会少掉理财那一块且看不出错。
    """
    assert 'bank_wealth' in ASSET_TYPE_VALUES
    assert 'bank_wealth' not in EXCLUDED_ASSET_TYPES


def test_bank_wealth_and_bank_are_distinct_products():
    """存款与理财是两个品类：同档（stable）但不能合并。

    合并的后果不是分类不好看，而是**收益口径错**——存款利息是利息收入，
    理财收益是投资收益，混成一类后两者都算不准。
    """
    assert ASSET_TYPE_LABELS['bank_wealth'] == '银行理财'
    assert ASSET_TYPE_LABELS['bank'] == '银行存款'
    assert 'bank_wealth' != 'bank'


# ───────────────────────── 边界：货基标记优先 ─────────────────────────
def test_money_fund_flag_overrides_asset_type():
    """货基持仓的 asset_type 是 'fund'，只看 asset_type 会把它错分进主动投资。

    真实库实测：231 行 fund 持仓里 20 行 is_money_fund=1。
    """
    pos = SimpleNamespace(asset_type='fund', is_money_fund=True)
    assert tier_of_position(pos) == TIER_STABLE
    # 同一个 asset_type，没有标记 → 主动投资
    assert tier_of_position(SimpleNamespace(asset_type='fund', is_money_fund=False)) == TIER_ACTIVE


def test_null_money_fund_flag_is_not_money_fund(db):
    """``is_money_fund = NULL``（普通持仓的大部分行）不能被当成货基。

    SQL 三值逻辑：NULL 既不是 True 也不是 False。判据只认 `is True`，
    故 NULL 与 False 行为一致（都归主动投资）。若写成 truthy 判断，某些
    ORM / DB 组合下会把 NULL 读成假值以外的含义，导致整批普通基金误入稳健档。
    """
    pos = Position(symbol='000001', name='华夏成长', asset_type='fund', is_money_fund=None)
    db.add(pos)
    db.commit()
    assert pos.is_money_fund is None
    assert tier_of_position(pos) == TIER_ACTIVE


def test_money_fund_position_row_is_stable(db):
    pos = Position(symbol='970164', name='银河水星现金添利', asset_type='fund', is_money_fund=True)
    db.add(pos)
    db.commit()
    assert tier_of_position(pos) == TIER_STABLE


# ───────────────────────── 边界：兜底与 venue ─────────────────────────
def test_unknown_or_empty_asset_type_falls_back_to_other():
    """未知 / 空值归 other 而不是抛错：脏数据不该阻断整个收益页。"""
    assert tier_of_asset_type('not_a_type') == TIER_OTHER
    assert tier_of_asset_type('') == TIER_OTHER
    assert tier_of_asset_type(None) == TIER_OTHER
    assert tier_of_asset_type('  STOCK  ') == TIER_ACTIVE  # 大小写 / 空白归一


def test_bank_wealth_has_no_venue():
    """银行理财不落 OTC。

    OTC 在本仓的语义是「场外公募基金销售渠道」，symbol 按裸 6 位码存。
    银行理财没有基金代码，落 OTC 会被套上「裸码 = 基金代码」的归一逻辑，
    读侧反查还会把它当成基金行。
    """
    assert venue_of_asset_type('bank_wealth') == NO_VENUE


def test_bank_wealth_is_a_specific_asset_type():
    """显式传入的 bank_wealth 不能被代码推断覆盖成 stock。

    银行理财产品名多为中文、无代码，漏在 `_SPECIFIC_ASSET_TYPES` 之外就会落到
    `_get_asset_type` 的默认分支（stock）——理财被记成一只股票。
    """
    assert 'bank_wealth' in _SPECIFIC_ASSET_TYPES


# ───────────────────────── 边界：只允许 balance ─────────────────────────
def test_bank_wealth_rejects_nav_mode(db):
    """银行理财落 nav 模式不会报错，而是市值恒为 0（拿不到净值）。必须在写入侧拒绝。"""
    with pytest.raises(ValueError, match='balance'):
        PositionService.process_buy_or_deposit(
            db,
            {
                'symbol': '招银理财招睿',
                'name': '招银理财招睿',
                'asset_type': 'bank_wealth',
                'quantity': 1,
                'avg_price': 100000.0,
                'valuation_mode': 'nav',
                'family_id': 1,
            },
        )


def test_bank_wealth_accepts_balance_mode(db):
    """balance 模式下应能正常建仓，并把市值落到 market_value_override。

    #2875：data 必须带 ledger_id——前端真实路径总带账本，此前夹具漏传会静默
    落成「无账本持仓 + 无账本流水」，现在被写入守卫拦截。写入汇点还会校验
    这个 id 必须指向真实账本，故夹具补建。
    """
    from app.domains.ledgers.models import Ledger

    db.add(Ledger(id=1, name='测试账户', ledger_type='fund', family_id=1))
    db.commit()
    pos = PositionService.process_buy_or_deposit(
        db,
        {
            'symbol': '招银理财招睿',
            'name': '招银理财招睿',
            'asset_type': 'bank_wealth',
            'amount': 100000.0,
            'valuation_mode': 'balance',
            'family_id': 1,
            'ledger_id': 1,
            'trade_date': date(2026, 11, 3),
            'confirm_date': date(2026, 11, 3),
        },
    )
    assert pos is not None
    assert pos.asset_type == 'bank_wealth'
    assert tier_of_position(pos) == TIER_STABLE


# ───────────────────────── 前端契约 ─────────────────────────
def test_enums_endpoint_exposes_bank_wealth(client):
    """前端不手抄枚举（走 /api/utils/enums），故下发端必须带上新值。

    漏下发的后果：后端能存 bank_wealth，前端下拉框里选不到，用户只能把它记成
    「其他」（static），分层判据随即认不出这笔理财。
    """
    data = client.get('/api/utils/enums/').get_json()['data']
    assert 'bank_wealth' in data['asset_type']
    assert data['asset_type']['bank_wealth'] == '银行理财'


def test_enums_endpoint_exposes_full_tier_map(client):
    """分档映射的**下发覆盖面**必须等于全量 asset_type。

    前端的三层展示直接读这份映射（不手抄第二份）。若下发是残缺的，缺失类型会被前端
    渲染成原键（`bank_wealth` 而非「银行理财」），且分层时静默掉进 other —— 而页面上
    看不出任何异常，只是那笔钱的收益不见了。故这里断言集合相等，不是「包含几个关键键」。
    """
    data = client.get('/api/utils/enums/').get_json()['data']

    assert set(data['investment_tier']) == set(ASSET_TYPE_VALUES)
    assert data['investment_tier']['stock'] == TIER_ACTIVE
    assert data['investment_tier']['bank_wealth'] == TIER_STABLE
    assert data['investment_tier']['real_estate'] == TIER_OTHER
    assert data['investment_tier_labels'] == TIER_LABELS
    assert data['investment_tier_values'] == list(TIER_VALUES)
    assert data['investment_tier_scopes'] == list(TIER_SCOPES)
