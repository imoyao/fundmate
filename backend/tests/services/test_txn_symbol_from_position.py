# -*- coding: utf-8 -*-
"""卖出/分红/拆分流水缺 ``symbol`` 的写入侧兜底（#2855）。

## 这张卡要钉住的是什么

卖出 / 分红 / 拆分的写路径曾直接写 ``symbol=data.get('symbol')``——请求体漏带该
字段就落 NULL。危害在读侧静默：

- 产品详情「交易记录」按 symbol 身份匹配（``symbol_scope``）⇒ 这些行永远不命中；
- 清仓周期按 ``strip_exchange_prefix(symbol)`` 分组（``cleared_cycles._group_key``）
  ⇒ 缺 symbol 的卖出被跳过，FIFO 队列永远不清空——已清仓产品「有买无卖」
  （实测 SZ002311：三笔卖出 position_id 全对、symbol 全 NULL，详情页一笔都看不到）。

判据：**交易挂在持仓上，持仓的 symbol 就是真源**。请求带 symbol 时以请求为准
（不做改写）；请求缺时按持仓兜底，绝不落 NULL。与 bond_redeem 路径
（`data.get('symbol') or existing.symbol`，先例在先）同一条纪律。
"""

import datetime as dt

from app.domains.transactions.models import Transaction
from app.services.position_service import PositionService


def _sell_data(pos, **overrides):
    data = {
        'position_id': pos.id,
        'op_type': 'sell',
        'quantity': 500,
        'avg_price': 2.0,
        'trade_date': dt.datetime(2026, 10, 27),
        'confirm_date': dt.date(2026, 10, 27),
        'family_id': 1,
    }
    data.update(overrides)
    return data


def _last_txn(db, txn_type='sell') -> Transaction:
    txn = db.query(Transaction).filter(Transaction.txn_type == txn_type).order_by(Transaction.id.desc()).first()
    assert txn is not None, f'应创建一条 {txn_type} 流水'
    return txn


class TestSellSymbolFallback:
    def test_卖出请求漏带symbol时按持仓回填(self, db, make_position):
        """核心回归：漏带 symbol 的卖出必须写上持仓的代码，不能落 NULL。"""
        pos = make_position(
            symbol='SZ002311',
            name='海大集团',
            account_name='银河证券',
            quantity=1000,
            avg_price=1.0,
            asset_type='fund',
        )

        PositionService.process_sell_or_withdraw(db, _sell_data(pos), auto_purchase=False)

        txn = _last_txn(db)
        assert txn.position_id == pos.id
        assert txn.symbol == 'SZ002311', (
            f'卖出流水 symbol 应按持仓回填为 SZ002311，实际 {txn.symbol!r}'
            '（NULL ⇒ 按 symbol 匹配的读侧看不见这笔卖出，已清仓产品「有买无卖」）'
        )

    def test_卖出请求带symbol时以请求为准(self, db, make_position):
        """请求显式给了 symbol 就不改写——兜底只补缺失，不做「纠正」。"""
        pos = make_position(
            symbol='SZ002311',
            name='海大集团',
            account_name='银河证券',
            quantity=1000,
            avg_price=1.0,
            asset_type='fund',
        )

        PositionService.process_sell_or_withdraw(db, _sell_data(pos, symbol='002311.SZ'), auto_purchase=False)

        txn = _last_txn(db)
        assert txn.symbol == '002311.SZ'

    def test_按名称兜底关联的孤儿卖出同样回填symbol(self, db, make_position):
        """orphan 卖出按名称关联到持仓后，落库的 symbol 也应取持仓的（旧路径落 NULL）。"""
        make_position(
            symbol='020106',
            name='兴业成长动力混合C',
            account_name='天天基金',
            quantity=1000,
            avg_price=1.0,
            asset_type='fund',
        )

        PositionService.process_orphan_sell_or_withdraw(
            db,
            {
                'symbol': '',  # 券商交割单没给代码，靠名称兜底关联
                'name': '兴业成长动力混合C',
                'account_name': '天天基金',
                'quantity': 500,
                'avg_price': 2.0,
                'trade_date': dt.datetime(2026, 10, 27),
                'confirm_date': dt.date(2026, 10, 27),
                'family_id': 1,
            },
        )

        txn = _last_txn(db)
        assert txn.position_id is not None, '名称兜底应关联到持仓'
        assert txn.symbol == '020106', f'关联成功的卖出流水 symbol 应为持仓代码 020106，实际 {txn.symbol!r}'


class TestDividendSymbolFallback:
    def test_分红请求漏带symbol时按持仓回填(self, db, make_position):
        pos = make_position(
            symbol='SZ002311',
            name='海大集团',
            account_name='银河证券',
            quantity=1000,
            avg_price=1.0,
            asset_type='stock',
        )

        PositionService.process_dividend(
            db,
            {
                'position_id': pos.id,
                'dividend_amount': 440.0,
                'trade_date': dt.datetime(2026, 6, 16),
                'confirm_date': dt.date(2026, 6, 16),
                'family_id': 1,
            },
        )

        txn = _last_txn(db, txn_type='dividend')
        assert txn.position_id == pos.id
        assert txn.symbol == 'SZ002311', f'分红流水 symbol 应按持仓回填为 SZ002311，实际 {txn.symbol!r}'
