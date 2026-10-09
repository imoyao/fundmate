# -*- coding: utf-8 -*-
"""持仓列表按 symbol / market 过滤（#1966 · 产品详情页「我的持仓」区块）。

验收要点：**过滤必须下推到 SQL**，不能取全表后内存筛（数据策略硬约束 §6）。
故最后一条用例用 `before_cursor_execute` 抓真实执行的语句、断言 WHERE 带条件——
只断言返回结果的话，「全表 + Python 过滤」也能蒙混过关。
"""

from sqlalchemy import event


def _capture_sql(db):
    """开始抓取该 session 引擎上执行的所有 SQL。用完必须 event.remove。"""
    captured: list[str] = []
    engine = db.get_bind()

    def _listener(conn, cursor, statement, parameters, context, executemany):
        captured.append(statement)

    event.listen(engine, 'before_cursor_execute', _listener)
    return captured, _listener, engine


def test_symbol_filter_hits_matching_position(client, db, make_position):
    make_position(symbol='SZ000001', name='平安银行', asset_type='stock', market='CN_A')
    make_position(symbol='SH600519', name='贵州茅台', asset_type='stock', market='CN_A')

    resp = client.get('/api/positions/?symbol=SZ000001')

    assert resp.status_code == 200
    rows = resp.get_json()['data']
    assert len(rows) == 1
    assert rows[0]['symbol'] == 'SZ000001'


def test_symbol_filter_unmatched_returns_empty(client, db, make_position):
    make_position(symbol='SZ000001', name='平安银行', asset_type='stock', market='CN_A')

    resp = client.get('/api/positions/?symbol=SZ999999')

    assert resp.status_code == 200
    assert resp.get_json()['data'] == []


def test_symbol_filter_matches_normalized_identity(client, db, make_position):
    """`000001.SZ` 与 `SZ000001` 是同一只产品——靠 #1662 的 symbol_norm 归一身份键命中。

    只按 symbol 字面量比的话，这条会被漏掉，详情页于是显示「无持仓」。
    """
    make_position(symbol='000001.SZ', name='平安银行', asset_type='stock', market='CN_A')

    resp = client.get('/api/positions/?symbol=SZ000001')

    assert resp.status_code == 200
    rows = resp.get_json()['data']
    assert len(rows) == 1
    assert rows[0]['name'] == '平安银行'


def test_market_filter_narrows_same_symbol_rows(client, db, make_position):
    """同码跨市场时 market 参与消歧（避免把别处的同码持仓算进来）。"""
    make_position(symbol='000001', name='A股基金', asset_type='fund', market='CN_A')
    make_position(symbol='000001', name='港股基金', asset_type='fund', market='CN_HK')

    resp = client.get('/api/positions/?symbol=000001&market=CN_HK')

    assert resp.status_code == 200
    rows = resp.get_json()['data']
    assert len(rows) == 1
    assert rows[0]['name'] == '港股基金'


def test_symbol_filter_is_pushed_to_sql(client, db, make_position):
    """过滤下推到 SQL：抓真实语句断言 WHERE 带条件，而非 .all() 后内存筛。"""
    make_position(symbol='SZ000001', name='平安银行', asset_type='stock', market='CN_A')

    captured, listener, engine = _capture_sql(db)
    try:
        resp = client.get('/api/positions/?symbol=SZ000001')
    finally:
        event.remove(engine, 'before_cursor_execute', listener)

    assert resp.status_code == 200
    selects = [s for s in captured if 'FROM positions' in s]
    assert selects, '未捕获到持仓查询语句'
    assert any('symbol' in s.lower() for s in selects), selects
