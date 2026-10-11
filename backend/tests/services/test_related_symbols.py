# -*- coding: utf-8 -*-
"""跨渠道关联标的（#1976 · 详情页关联标的区块）。

重点覆盖四件事：

1. **双向查询** —— `channel_links` 存有向关系（index→etf），但查指数要返回 ETF、
   查 ETF 要返回指数，前端不能自己判断方向；
2. **角色决定标签** —— 同一条 `index_etf` 关系，站在指数侧叫「同标的 ETF」，
   站在 ETF 侧叫「跟踪指数」；
3. **裸代码匹配** —— 入参带前缀（SH/CSI/OF）都要能命中同一批关系；
4. **无关联不报错、返回空列表** —— 覆盖率约 66.4%，无关联是正常情形（缺口见 #1419），
   前端据此降级 `—`，不是 404。

## 为什么用 `9900xx` 专用代码段 + `_seed_links` 批量插（踩过两个坑）

初版测试直接用真实存在的 `510650` / `931637`，断言写死 `== 1`。单跑本文件时通过，
与守卫测试**同批跑**时红：真实库里 `510650` 已有 2 条 ETF 关联、`931637` 有 15 条，
断言被存量数据顶成 3 / 16。

`market` 域库在测试间**共享**（conftest 的 `clean_db` 只清当前会话引擎实际存在的表，
market 域残留不保证被清），所以**不能用真实存在的标的做精确计数断言**。现全部改用
`9900xx` 段——实测真实库该段为空。

第二个坑：清理逻辑放在 `_seed_link` 内部（每次插前清两端代码），结果**同一用例内**第二条
关系会把第一条也删掉（两条共享 `IDX`），`multiple_etfs` 只剩 1 条。故改为
`_seed_links(*links)`：**先一次性清完、 再批量插**，由调用方把本用例要建的关系一次传进来。

⚠️ 两种顺序都验过：单跑 9 passed；与守卫同批 38 passed。

⚠️ 测试数据造在 **market 域**会话：`channel_links` 属 market 域，生产下是独立引擎。
"""

from contextlib import closing

from sqlalchemy import or_

from app.core.db_factory import market_session_factory
from app.domains.funds.models import ChannelLink
from app.services.related_symbols import build_related_symbols

# 专用测试代码段：真实库为空（实测），避免存量关系顶坏精确计数断言
IDX = '990001'
ETF_A = '990002'
ETF_B = '990003'
FEEDER = '990004'
ORPHAN = '990009'  # 从不建关系，用于「无关联」用例


def _seed_links(*links):
    """批量写入关系：**先一次性清掉涉及的全部代码，再统一插入**。

    两种坑都踩过（都表现为精确计数断言被顶掉）：

    1. 早期只删「即将写入的那一条」，结果 `test_etf_has_both_index_and_feeder`
       给 ETF_A 建的联接关系留在库里，后续只查该代码的用例多出 1 条；
    2. 改在`_seed_link` 内调 `_reset_links(from, to)`，结果**同一用例内**第二条关系
       会把第一条也删掉（两条共享 `IDX`），`multiple_etfs` 只剩 1 条。

    故：清一次、插一批，由调用方把本用例要建的关系一次性传进来。
    """
    codes = set()
    for link_type, from_symbol, to_symbol, from_name, to_name in links:
        codes.add(from_symbol)
        codes.add(to_symbol)

    with closing(market_session_factory()()) as db:
        db.query(ChannelLink).filter(
            or_(
                ChannelLink.from_symbol.in_(codes),
                ChannelLink.to_symbol.in_(codes),
            )
        ).delete(synchronize_session=False)
        db.flush()
        for link_type, from_symbol, to_symbol, from_name, to_name in links:
            db.add(
                ChannelLink(
                    link_type=link_type,
                    from_symbol=from_symbol,
                    to_symbol=to_symbol,
                    from_name=from_name,
                    to_name=to_name,
                )
            )
        db.commit()


def _codes_of(symbol):
    with closing(market_session_factory()()) as db:
        return [x['code'] for x in build_related_symbols(db, symbol)['links']]


def test_returns_empty_when_no_relation():
    """无关联返回空列表而不是 None / 报错（覆盖率 66.4%，无关联是正常情形）。"""
    with closing(market_session_factory()()) as db:
        result = build_related_symbols(db, ORPHAN)
    assert result == {'links': [], 'groups': []}


def test_index_side_returns_etf():
    """站在指数侧：返回该指数对应的 ETF，标签为「同标的 ETF」。"""
    _seed_links(('index_etf', IDX, ETF_A, '测试指数', '测试ETF'))

    with closing(market_session_factory()()) as db:
        result = build_related_symbols(db, IDX)

    assert len(result['links']) == 1
    link = result['links'][0]
    assert link['code'] == ETF_A
    assert link['name'] == '测试ETF'
    assert link['link_type'] == 'index_etf'
    assert link['label'] == '同标的 ETF'
    # #1974：对端角色决定前端跳 /etf/ 还是 /fund/，必须由后端给出而非前端猜
    assert link['peer_role'] == 'etf'


def test_etf_side_returns_index_with_tracking_label():
    """站在 ETF 侧：反向返回指数，标签应为「跟踪指数」而非「同标的 ETF」。"""
    _seed_links(('index_etf', IDX, ETF_A, '测试指数', '测试ETF'))

    with closing(market_session_factory()()) as db:
        result = build_related_symbols(db, ETF_A)

    assert len(result['links']) == 1
    link = result['links'][0]
    assert link['code'] == IDX
    # 角色反转 → 标签必须跟着变，否则用户看到「ETF 的同标的 ETF」这种错话
    assert link['label'] == '跟踪指数'
    assert link['peer_role'] == 'index'


def test_bare_code_strips_prefix():
    """入参带市场前缀也能命中（关系表存裸代码，自选行前缀形态不统一）。"""
    _seed_links(('index_etf', IDX, ETF_A, '测试指数', '测试ETF'))

    with closing(market_session_factory()()) as db:
        for symbol in (ETF_A, f'SH{ETF_A}', f'CSI{ETF_A}'):
            result = build_related_symbols(db, symbol)
            assert len(result['links']) == 1, f'{symbol} 应命中同一批关系'


def test_etf_has_both_index_and_feeder():
    """ETF 同时关联指数与联接基金：两类关系都要返回，且分组标签都出现。"""
    _seed_links(
        ('index_etf', IDX, ETF_A, '测试指数', '测试ETF'),
        ('etf_feeder', ETF_A, FEEDER, '测试ETF', '测试ETF联接'),
    )

    with closing(market_session_factory()()) as db:
        result = build_related_symbols(db, ETF_A)

    assert {x['code'] for x in result['links']} == {IDX, FEEDER}
    assert {x['label'] for x in result['links']} == {'跟踪指数', '场外联接'}
    assert set(result['groups']) == {'跟踪指数', '场外联接'}
    # 两端角色不同 → 前端要跳不同路径：指数暂无详情页（#2028），联接跳 /fund/
    assert {x['peer_role'] for x in result['links']} == {'index', 'feeder'}


def test_index_multiple_etfs_all_returned():
    """一个指数可对应多只 ETF（实测最多的指数有数十条），全部返回。"""
    _seed_links(
        ('index_etf', IDX, ETF_A, '测试指数', 'ETF甲'),
        ('index_etf', IDX, ETF_B, '测试指数', 'ETF乙'),
    )

    with closing(market_session_factory()()) as db:
        result = build_related_symbols(db, IDX)

    assert len(result['links']) == 2
    assert {x['label'] for x in result['links']} == {'同标的 ETF'}


def test_link_missing_name_is_none_not_empty_string():
    """关联标的名称缺失时返回 None（前端降级显示代码），不是空串。"""
    _seed_links(('index_etf', IDX, ETF_A, '测试指数', None))

    with closing(market_session_factory()()) as db:
        result = build_related_symbols(db, IDX)

    assert result['links'][0]['name'] is None


def test_order_is_stable():
    """排序稳定：同 link_type 内按代码升序，避免刷新时顺序抖动。"""
    _seed_links(
        ('index_etf', IDX, ETF_B, '测试指数', 'B'),
        ('index_etf', IDX, ETF_A, '测试指数', 'A'),
    )

    first = _codes_of(IDX)
    second = _codes_of(f'SH{IDX}')
    assert first == [ETF_A, ETF_B]
    assert first == second  # 带前缀查也同序


def test_invalid_symbol_returns_empty():
    """无法抽出裸代码的入参返回空列表，不抛异常。"""
    with closing(market_session_factory()()) as db:
        assert build_related_symbols(db, '') == {'links': [], 'groups': []}
        assert build_related_symbols(db, '---') == {'links': [], 'groups': []}
