# -*- coding: utf-8 -*-
"""同步目标池必须包含「持有过」的标的（#2859 守卫）。

WHY
    目标池此前只取 ``positions ∪ watchlist_items``。而 #2343（2026-10-18）之前
    清仓走的是 ``db.delete(position)``：持仓行连同它的 symbol 一起消失，流水因为
    不级联还在库里。于是标的**两张表都不在** ⇒ 永远进不了同步 ⇒ 永远零行情，
    产品详情页是空图（用户读成「数据丢了」）。

    真库实测（2026-11-03）：流水里 213 个场内标的，141 个零行情，其中 136 个不在池；
    637 条流水的 ``position_id`` 已悬空（指向不存在的持仓行）。

    这条断言防的是「静默回退」：有人把流水来源删掉、或者给它加上
    ``ownership_status == 'active'`` 之类的过滤，那 136 个标的会重新变回空图 ——
    不报错、不告警、其余测试全绿。

判据
    1. 只有流水、**没有持仓行也没有自选行**的场内标的，必须在返回值里（含
       ``position_id`` 悬空的历史遗留形态）；
    2. 场外基金 / 逆回购 / 现金不进来 —— 它们不走 ``price_history``，混进来只是
       每轮白跑请求（场外基金净值走 ``daily_worth``，是产品级、不随持仓行删）。
"""

from datetime import date

from app.domains.transactions.models import Transaction
from app.services.sync.orchestrator import DataSyncOrchestrator


def _txn(db, symbol, asset_type, position_id=None):
    """只写流水、不建持仓行 —— 复刻「清仓删行」之后库里的真实形态。"""
    db.add(
        Transaction(
            position_id=position_id,
            symbol=symbol,
            asset_type=asset_type,
            txn_type='buy',
            position_name=symbol,
            quantity=10000,
            price=10000,
            amount=1000000,
            confirm_date=date(2024, 3, 1),
            status='success',
        )
    )
    db.commit()


def test_held_symbol_without_any_row_is_in_pool(db):
    """有流水但持仓行已不在的场内标的，必须在同步池里。"""
    _txn(db, 'SH110074', 'bond')

    codes = DataSyncOrchestrator(db)._load_codes_from_database()

    assert 'SH110074' in codes, '「持有过」的标的掉出同步池：详情页走势会永远空白'


def test_held_symbol_with_dangling_position_id_is_in_pool(db):
    """``position_id`` 指向已删持仓（历史遗留疤痕）的流水同样要能进池。"""
    _txn(db, 'SZ123085', 'bond', position_id=999999)

    codes = DataSyncOrchestrator(db)._load_codes_from_database()

    assert 'SZ123085' in codes


def test_non_quote_asset_types_stay_out_of_pool(db):
    """场外基金 / 逆回购 / 现金不进行情池（它们没有 price_history）。"""
    _txn(db, '003535', 'fund')
    _txn(db, 'SH204001', 'reverse_repo')
    _txn(db, '__CASH__', 'cash')

    codes = DataSyncOrchestrator(db)._load_codes_from_database()

    assert '003535' not in codes
    assert 'SH204001' not in codes
    assert '__CASH__' not in codes


def test_blank_symbol_rows_do_not_pollute_pool(db):
    """无代码流水（理财/手工记账）不产生空串目标。"""
    _txn(db, '', 'stock')

    codes = DataSyncOrchestrator(db)._load_codes_from_database()

    assert '' not in codes
