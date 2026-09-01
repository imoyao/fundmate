# -*- coding: utf-8 -*-
"""证券 asset_type 回填测试（#1264 / #1266 数据修正）。"""

from app.domains.positions.models import Position
from app.domains.securities.models import Security
from app.services.securities_type_backfill import backfill_securities_asset_type

_TEST_SYMBOLS = ('SH510050', 'SZ159915', 'SH600519', 'SH110067', 'SZ128063', 'SH511990', '110011', 'SH588000')


def _cleanup(db):
    for p in db.query(Position).filter(Position.symbol.in_(_TEST_SYMBOLS)).all():
        db.delete(p)
    for s in db.query(Security).filter(Security.symbol.in_(_TEST_SYMBOLS)).all():
        db.delete(s)
    db.commit()


def test_backfill_securities_asset_type(db, make_position):
    """存量证券持仓按代码前缀回填 stock/etf/bond，不动 fund/money_fund。"""
    _cleanup(db)

    # 被误标为 stock 的证券持仓
    make_position(symbol='SH510050', name='50ETF', asset_type='stock', account_name='a')
    make_position(symbol='SZ159915', name='创业板ETF', asset_type='stock', account_name='a')
    make_position(symbol='SH600519', name='贵州茅台', asset_type='stock', account_name='a')
    make_position(symbol='SH110067', name='浦发转债', asset_type='stock', account_name='a')  # 可转债误标
    make_position(symbol='SZ128063', name='转债2', asset_type='stock', account_name='a')
    # 不应被改动：货币基金 / 公募基金
    make_position(symbol='SH511990', name='华宝添益', asset_type='money_fund', account_name='a')
    make_position(symbol='110011', name='易方达中小盘', asset_type='fund', account_name='a')

    # 证券元数据：get-or-create 并强制从 stock 起步，保证断言幂等
    sec = db.query(Security).filter_by(symbol='SH588000').first()
    if sec is None:
        sec = Security(symbol='SH588000', name='测试ETF', market='CN_A', type='stock')
        db.add(sec)
    else:
        sec.type = 'stock'
    db.commit()

    summary = backfill_securities_asset_type(db, apply=True)

    def at(sym):
        return db.query(Position).filter_by(symbol=sym).first().asset_type

    assert at('SH510050') == 'etf'
    assert at('SZ159915') == 'etf'
    assert at('SH600519') == 'stock'  # 本就是股票，未变
    assert at('SH110067') == 'bond'
    assert at('SZ128063') == 'bond'
    assert at('SH511990') == 'money_fund'  # 不动
    assert at('110011') == 'fund'  # 不动
    assert db.query(Security).filter_by(symbol='SH588000').first().type == 'etf'


def test_backfill_securities_asset_type_dry_run(db, make_position):
    """dry-run 不写入。"""
    _cleanup(db)
    make_position(symbol='SH510050', name='50ETF', asset_type='stock', account_name='a')
    db.commit()

    summary = backfill_securities_asset_type(db, apply=False)
    assert summary['positions_updated'] == 0
    assert db.query(Position).filter_by(symbol='SH510050').first().asset_type == 'stock'
