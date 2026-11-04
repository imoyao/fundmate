# -*- coding: utf-8 -*-
"""#2844 回归：收益类流水的展示名称兜底。

现场：同花顺交割单里「基金红利拨入」「红利入账」这类收益行，券商原文的
「证券代码」「证券名称」两列本来就是空的（table1101.xls 实测 33 笔 302.59 元）。
快照、持仓、名录三处都查不到名字，列表里就只剩「未知资产」——用户看到一笔
2.10 元的「分红 / 未知资产」，既不知道钱从哪来，也判断不出这是数据缺失还是账目错乱。

口径：兜底只说**能确认的**那部分——资产类型（库里存的）+ 收益种类（txn_type 给的），
不猜具体产品；且只在**展示层**兜底，不写库（`position_name` 仍是快照）。
"""

from datetime import date

from app.core.money import Money
from app.services.transaction_service import build_transaction_list
from app.services.txn_name_resolver import display_asset_name

TODAY = date(2026, 11, 3)


# ── 纯函数：文案与优先级 ──────────────────────────────────────────────────


def test_snapshot_name_wins():
    """有快照就用快照，任何兜底都不该盖掉真实名称。"""
    assert (
        display_asset_name(position_name='银河水星现金添利', asset_type='money_fund', txn_type='dividend')
        == '银河水星现金添利'
    )


def test_money_fund_dividend_uses_type_label():
    """无名称的货基分红 → 「货币基金分红」：类型来自库里，不猜是哪只基金。"""
    assert display_asset_name(position_name=None, asset_type='money_fund', txn_type='dividend') == '货币基金分红'
    assert display_asset_name(position_name='', asset_type='money_fund', txn_type='dividend_cash') == '货币基金分红'


def test_uppercase_business_type_from_importer():
    """导入记录里的 business_type 是大写枚举（DIVIDEND_CASH），归一前比会静默漏判。"""
    assert display_asset_name(position_name=None, asset_type='money_fund', txn_type='DIVIDEND_CASH') == '货币基金分红'


def test_stock_dividend_and_tax():
    """红利税是另一档文案：叫「股票分红」会让用户以为这笔钱是到账的收益。"""
    assert display_asset_name(position_name=None, asset_type='stock', txn_type='dividend') == '股票分红'
    assert display_asset_name(position_name=None, asset_type='stock', txn_type='dividend_tax') == '股票红利税'


def test_missing_asset_type_degrades_to_kind_only():
    """连 asset_type 都没有（历史流水）时退到「分红」，不编造资产类型。"""
    assert display_asset_name(position_name=None, asset_type=None, txn_type='dividend') == '分红'


def test_non_income_rows_stay_unknown():
    """买入 / 卖出缺名称是另一类问题（标的真丢了），「未知资产」是诚实的。

    兜底不能外溢：把这类行也叫「现金分红」会把数据缺口继续藏起来。
    """
    assert display_asset_name(position_name=None, asset_type='cash', txn_type='deposit') == '未知资产'
    assert display_asset_name(position_name=None, asset_type='stock', txn_type='buy') == '未知资产'


# ── 集成：列表接口真的用上了它 ────────────────────────────────────────────


def test_transaction_list_shows_type_label_instead_of_unknown(db, make_transaction):
    """列表里 33 笔无标的的分红行现在读作「货币基金分红」，不再是一句「未知资产」。"""
    txn = make_transaction(
        position_id=None,
        ledger_id=None,
        txn_type='dividend',
        asset_type='money_fund',
        symbol='',
        position_name=None,
        quantity=0,
        price=0,
        amount=Money.yuan_to_cents(2.10),
        confirm_date=TODAY,
        trade_date=TODAY,
    )
    db.commit()

    result = build_transaction_list(db, family_id=1, page=1, per_page=50, filters={})
    row = next(r for r in result['data'] if r['id'] == txn.id)
    assert row['position_name'] == '货币基金分红'
    # 只是展示兜底，不写库：快照仍是空的（改写会让搜索 / 分组 / 去重一起失准）
    assert txn.position_name is None
