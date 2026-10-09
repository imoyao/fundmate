# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/9
# File : test_product_resolve.py
# tests/domains/products/test_product_resolve.py
"""`GET /api/products/resolve/` 契约测试（#1963）。

覆盖 issue 验收的三种情形 + 关键边界：

1. 已知 symbol（已登录）→ 权威 asset_type / 展示名 + 私有状态；
2. 未知 symbol → 404 空态（不是白屏，也不是 200 + 空 data）；
3. 未登录 → 只回公开字段，``in_watchlist`` / ``has_position`` 恒为 null；
4. 前端路径段传来的 ``asset_type`` 只是提示，与后端判定冲突时**以后端为准**；
5. 身份来源优先级（自选 > 持仓 > 提示 > 目录反查）与 ETF 判定。
"""

from contextlib import closing

import pytest

from app.core.db_factory import market_session_factory, user_session_factory
from app.domains.positions.models import Position
from app.domains.securities.models import Security
from app.domains.watchlist.models import WatchlistItem

RESOLVE_URL = '/api/products/resolve/'

# 本文件会读写的 symbol（跨用例必须清干净，见 _isolate_product_rows）
_TEST_SYMBOLS = ('SZ000001', 'SZ159915', 'SH601899')


@pytest.fixture(autouse=True)
def _isolate_product_rows():
    """每个用例前按 symbol 清掉本文件关心的业务行。

    conftest 的 ``clean_db`` 只清「当前会话引擎实际存在的表」，**market 域与部分
    user 域行会跨用例残留**；而 ``securities.symbol`` 与
    ``watchlist(family_id, symbol, market, venue)`` 都有唯一约束——残留既会让插入
    撞约束，也会让「身份来源」判定串味（上个用例加的自选，会把本用例期望的
    ``source == 'position'`` 变成 ``'watchlist'``，看起来像实现错了，其实是脏数据）。
    故在此按 symbol 显式清理，不依赖全局 clean_db 的覆盖面。
    """
    with closing(user_session_factory()()) as db:
        db.query(WatchlistItem).filter(WatchlistItem.symbol.in_(_TEST_SYMBOLS)).delete()
        db.query(Position).filter(Position.symbol.in_(_TEST_SYMBOLS)).delete()
        db.commit()
    with closing(market_session_factory()()) as db:
        db.query(Security).filter(Security.symbol.in_(_TEST_SYMBOLS)).delete()
        db.commit()


def _seed_security(symbol='SZ000001', name='平安银行', sec_type='stock'):
    """market 域种子（公开证券名录）。

    幂等：conftest 的 ``clean_db`` 只清当前会话引擎实际存在的表，**market 域残留不保证被清**，
    故这里先查后插——否则重复 symbol 会撞 ``securities.symbol`` 唯一约束。
    """
    with closing(market_session_factory()()) as db:
        if db.query(Security.id).filter(Security.symbol == symbol).first() is None:
            db.add(Security(symbol=symbol, name=name, market='CN_A', type=sec_type))
            db.commit()


def _seed_watchlist(family_id=1, symbol='SZ000001', asset_type='stock', name='平安银行'):
    """user 域种子（自选行，含名称快照）。同样幂等（唯一键 family+symbol+market+venue）。"""
    with closing(user_session_factory()()) as db:
        exists = (
            db.query(WatchlistItem.id)
            .filter(
                WatchlistItem.family_id == family_id,
                WatchlistItem.symbol == symbol,
                WatchlistItem.market == 'CN_A',
                WatchlistItem.venue == 'EXCHANGE',
            )
            .first()
        )
        if exists is None:
            db.add(
                WatchlistItem(
                    family_id=family_id,
                    symbol=symbol,
                    market='CN_A',
                    venue='EXCHANGE',
                    asset_type=asset_type,
                    name=name,
                )
            )
            db.commit()


# ── 1. 已知 symbol（已登录）────────────────────────────────────────────
def test_resolve_known_symbol_returns_identity(client):
    """已登录 + 自选里有这只股票 → 回权威身份与私有状态。"""
    _seed_security()
    _seed_watchlist()

    resp = client.get(RESOLVE_URL, query_string={'symbol': 'SZ000001'}, headers={'X-User-Id': '1'})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['message'] == 'ok'
    data = body['data']
    assert data['symbol'] == 'SZ000001'
    assert data['asset_type'] == 'stock'
    assert data['display_name'] == '平安银行'
    assert data['in_watchlist'] is True
    assert data['has_position'] is False
    # 身份来自用户自己录入的自选行，不是目录反查
    assert data['source'] == 'watchlist'


# ── 2. 未知 symbol → 404 空态 ──────────────────────────────────────────
def test_resolve_unknown_symbol_returns_404(client):
    """任何表都查不到的代码 → 404 + 错误信封三字段（前端走空态，不是白屏）。"""
    resp = client.get(RESOLVE_URL, query_string={'symbol': 'NOSUCHCODE'}, headers={'X-User-Id': '1'})

    assert resp.status_code == 404
    body = resp.get_json()
    assert 'data' in body
    assert body['error_code'] == 1002  # ErrorCode.RESOURCE_NOT_FOUND


# ── 3. 未登录 → 只回公开字段 ───────────────────────────────────────────
def test_resolve_anonymous_returns_public_fields_only(client):
    """未登录：仍能拿到公开身份，但私有状态恒为 null（且不泄露他家自选）。"""
    _seed_security()
    _seed_watchlist()

    resp = client.get(RESOLVE_URL, query_string={'symbol': 'SZ000001'})

    assert resp.status_code == 200
    data = resp.get_json()['data']
    # 公开字段照常给（目录反查即可判定品类）
    assert data['asset_type'] == 'stock'
    assert data['display_name'] == '平安银行'
    assert data['source'] == 'catalog'
    # 家庭私有状态必须为 null
    assert data['in_watchlist'] is None
    assert data['has_position'] is None


# ── 4. 路径段 asset_type 只是提示，与后端冲突时以后端为准 ──────────────
def test_resolve_hint_conflicting_with_backend_defers_to_backend(client):
    """用户手输 /fund/SZ000001 这类错误路径 → 以后端判定的 stock 为准。"""
    _seed_security()

    resp = client.get(
        RESOLVE_URL,
        query_string={'symbol': 'SZ000001', 'asset_type': 'fund'},
        headers={'X-User-Id': '1'},
    )

    assert resp.status_code == 200
    data = resp.get_json()['data']
    # 自选/持仓都没有该行 → 走目录反查（不采信提示）
    assert data['asset_type'] == 'stock'
    assert data['source'] == 'catalog'


def test_resolve_hint_accepted_when_no_other_evidence(client):
    """既不在自选/持仓、目录也查不到时，入口提示可作为兜底判定（标 source=hint）。"""
    resp = client.get(
        RESOLVE_URL,
        query_string={'symbol': 'ZH000001', 'asset_type': 'portfolio'},
        headers={'X-User-Id': '1'},
    )

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['asset_type'] == 'portfolio'
    assert data['source'] == 'hint'


# ── 5. 缺参数 / 非法提示 ───────────────────────────────────────────────
@pytest.mark.parametrize('symbol', ['', '   '])
def test_resolve_blank_symbol_rejected(client, symbol):
    """空 / 纯空白 symbol → 400（不是 404，避免把「参数缺失」说成「产品不存在」）。"""
    resp = client.get(RESOLVE_URL, query_string={'symbol': symbol}, headers={'X-User-Id': '1'})

    assert resp.status_code in (400, 422)


def test_resolve_invalid_asset_type_hint_returns_400(client):
    """asset_type 走权威枚举校验，非法值直接 400，不静默降级。"""
    resp = client.get(
        RESOLVE_URL,
        query_string={'symbol': 'SZ000001', 'asset_type': 'not_a_type'},
        headers={'X-User-Id': '1'},
    )

    # pydantic 层字段校验失败由 apiflask 拦下 → 422（不落到视图，故不是三字段信封）
    assert resp.status_code in (400, 422)


# ── 6. ETF 走 securities.type 判定，不误标成 stock ────────────────────
def test_resolve_etf_from_security_type(client):
    """场内 ETF 在 securities 表里 type=etf → asset_type 应为 etf 而非 stock。"""
    _seed_security(symbol='SZ159915', name='创业板ETF', sec_type='etf')

    resp = client.get(RESOLVE_URL, query_string={'symbol': 'SZ159915'}, headers={'X-User-Id': '1'})

    assert resp.status_code == 200
    assert resp.get_json()['data']['asset_type'] == 'etf'


# ── 7. 持仓行也能作为身份来源（无自选时）──────────────────────────────
def test_resolve_from_position_when_not_in_watchlist(client):
    """只在持仓里、没加自选 → source=position，in_watchlist=False / has_position=True。"""
    _seed_security()
    with closing(user_session_factory()()) as db:
        exists = db.query(Position.id).filter(Position.family_id == 1, Position.symbol == 'SZ000001').first()
        if exists is None:
            db.add(
                Position(
                    family_id=1,
                    symbol='SZ000001',
                    market='CN_A',
                    asset_type='stock',
                    name='平安银行',
                    quantity=100,
                )
            )
            db.commit()

    resp = client.get(RESOLVE_URL, query_string={'symbol': 'SZ000001'}, headers={'X-User-Id': '1'})

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['source'] == 'position'
    assert data['in_watchlist'] is False
    assert data['has_position'] is True


# ── 8. 市场词表口径统一（#1969 P0：详情页「已持有」与「暂无持仓记录」同屏）──────
def _seed_watchlist_row(
    family_id=1,
    symbol='SH601899',
    market='SH',
    venue='EXCHANGE',
    asset_type='stock',
    name='紫金矿业',
):
    """按**给定 market 原样**写自选行。

    与 `_seed_watchlist` 的区别：那个固定写契约市场 `CN_A`，本函数用来复现存量库里
    「场内自选存交易所形态」的历史事实（本机实测 `SH` 13 行 / `SZ` 22 行）。
    """
    with closing(user_session_factory()()) as db:
        exists = (
            db.query(WatchlistItem.id)
            .filter(
                WatchlistItem.family_id == family_id,
                WatchlistItem.symbol == symbol,
                WatchlistItem.market == market,
                WatchlistItem.venue == venue,
            )
            .first()
        )
        if exists is None:
            db.add(
                WatchlistItem(
                    family_id=family_id,
                    symbol=symbol,
                    market=market,
                    venue=venue,
                    asset_type=asset_type,
                    name=name,
                )
            )
            db.commit()


def _seed_position(symbol='SH601899', market='CN_A', quantity=100):
    """写一行持仓（**契约市场**）。实测 `positions.market` 155/155 都是 `CN_A`。"""
    with closing(user_session_factory()()) as db:
        exists = (
            db.query(Position.id)
            .filter(Position.family_id == 1, Position.symbol == symbol, Position.market == market)
            .first()
        )
        if exists is None:
            db.add(
                Position(
                    family_id=1,
                    symbol=symbol,
                    market=market,
                    asset_type='stock',
                    name='紫金矿业',
                    quantity=quantity,
                )
            )
            db.commit()


def test_resolve_normalizes_exchange_market_to_contract(client):
    """自选行存**交易所**形态（`SH`）→ 出口必须归一为契约市场 `CN_A`。

    这条是 #1969 P0 的根因锁：resolve 回 `SH` 而 `positions.market` 一律 `CN_A`，
    详情页拿它去过滤持仓恒为空 —— 于是 hero 说「持仓 已持有」、下一个区块说
    「当前产品暂无持仓记录」，同一页面对同一事实给出相反结论。
    """
    _seed_security(symbol='SH601899', name='紫金矿业')
    _seed_watchlist_row(symbol='SH601899', market='SH')

    resp = client.get(RESOLVE_URL, query_string={'symbol': 'SH601899'}, headers={'X-User-Id': '1'})

    assert resp.status_code == 200
    assert resp.get_json()['data']['market'] == 'CN_A'


def test_resolve_keeps_watchlist_state_with_legacy_market(client):
    """归一后的 market 回传（`CN_A`）不得把存量为 `SH` 的自选行漏掉。

    这是归一化的**连带面**：`market` 入参参与自选查询过滤，只比契约值会让存量的
    `SH` 行查不到，结果是「修好了持仓、却把已自选弄丢」。
    """
    _seed_security(symbol='SH601899', name='紫金矿业')
    _seed_watchlist_row(symbol='SH601899', market='SH')

    resp = client.get(
        RESOLVE_URL, query_string={'symbol': 'SH601899', 'market': 'CN_A'}, headers={'X-User-Id': '1'}
    )

    assert resp.status_code == 200
    assert resp.get_json()['data']['in_watchlist'] is True


def test_resolve_position_state_survives_contract_market_filter(client):
    """详情页主链路：用 resolve 回的 market 过滤持仓**必须命中**（持仓区块不再恒空）。

    市场词表一旦再分叉，此处直接红灯。
    """
    _seed_security(symbol='SH601899', name='紫金矿业')
    _seed_position(symbol='SH601899', market='CN_A')

    resp = client.get(
        RESOLVE_URL, query_string={'symbol': 'SH601899', 'market': 'CN_A'}, headers={'X-User-Id': '1'}
    )

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['has_position'] is True
    assert data['market'] == 'CN_A'
