# -*- coding: utf-8 -*-
"""同步目标池必须包含已清仓标的（#2773 守卫）。

WHY
    清仓后涨跌幅依赖「该标的的净值还在被继续拉取」。而净值同步的目标池是从
    ``positions ∪ watchlist_items`` 取的，**没有任何 ownership_status 过滤**——
    清仓行因 #2343「清仓不删行」仍留在表里，所以净值会照常更新。

    但这是**隐式副作用**：那条 query 上没有注释，也没有断言。任何人给它加一句
    看起来极其自然的 ``filter(Position.ownership_status == 'active')``，清仓后
    涨跌幅就会静默退化成 ``no_nav_after`` —— 不报错、不告警、不失败。
    本文件就是那个断言。

判据：清仓行（``ownership_status='cleared'``）的 symbol 必须仍在返回值里。
"""

from app.services.sync.orchestrator import DataSyncOrchestrator


def test_cleared_position_still_in_sync_pool(db, make_position):
    """已清仓的持仓行必须仍在同步池内（否则清仓后涨跌幅永远算不出）。"""
    make_position(symbol='000001', name='仍持有', quantity=100, avg_price=1.0, ownership_status='active')
    make_position(symbol='000002', name='已清仓', quantity=0, avg_price=1.0, ownership_status='cleared')

    codes = DataSyncOrchestrator(db)._load_codes_from_database()

    assert '000001' in codes
    assert '000002' in codes, '已清仓标的掉出同步池：清仓后涨跌幅会静默变成 no_nav_after'
