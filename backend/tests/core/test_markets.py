# -*- coding: utf-8 -*-
"""市场归一的回归（`app/core/markets.py` · #1969 P0）。

锁两件事：

1. `to_contract_market()` 把交易所形态（SH/SZ/BJ/HK/CR）归一为**契约市场**，
   缺值时按 symbol 前缀补全、识别不了就返回空串（不编造）；
2. ⚠️ **写入侧刻意不归一**——`watchlist.market` 存的是 normalizer 命名空间
   （SH/SZ/BJ/HK），那是 `cross_domain` 跨域键的契约形态。这条用**反向断言**钉住，
   免得后人（包括我）看着「两套词表」不顺眼又来"顺手统一"一次。
"""

import pytest

from app.core.markets import market_aliases, to_contract_market
from app.services.watchlist_service import normalize_and_infer_venue


# ── 归一函数 ──────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('SH', 'CN_A'),
        ('SZ', 'CN_A'),
        ('BJ', 'CN_A'),
        ('HK', 'CN_HK'),
        ('CR', 'CRYPTO'),
        ('US', 'US'),
        # 契约市场原样通过（归一必须幂等，否则出口二次调用会漂）
        ('CN_A', 'CN_A'),
        ('CN_HK', 'CN_HK'),
        ('CRYPTO', 'CRYPTO'),
        # 指数名录的命名空间不是市场词表，原样保留
        ('CSI', 'CSI'),
        ('CNI', 'CNI'),
        # 大小写不敏感
        ('sh', 'CN_A'),
    ],
)
def test_to_contract_market(raw, expected):
    assert to_contract_market(raw) == expected


def test_to_contract_market_falls_back_to_symbol_prefix():
    """不带 market 时按 symbol 前缀推断——手输 `/stock/600519` 的唯一兜底。"""
    assert to_contract_market('', 'SH601899') == 'CN_A'
    assert to_contract_market(None, 'SZ000001') == 'CN_A'
    assert to_contract_market('', 'HK00700') == 'CN_HK'


def test_to_contract_market_does_not_invent_market():
    """认不出来就返回空串，由调用方决定怎么兜底——本函数**不编造**市场。"""
    assert to_contract_market('', 'NOSUCH') == ''
    assert to_contract_market('', '') == ''


def test_market_aliases_covers_legacy_values():
    """读侧别名必须含存量脏值形态，否则迁移完成前会把「已自选」误判成未自选。"""
    assert market_aliases('CN_A') == ('CN_A', 'SH', 'SZ', 'BJ')
    assert market_aliases('CN_HK') == ('CN_HK', 'HK')
    # 未收录的退化为单值，不会把查询放宽成空集合（那会导致恒查不到）
    assert market_aliases('CSI') == ('CSI',)


# ── 写入路径（#1969 P0 根治）───────────────────────────────────────────
@pytest.mark.parametrize(
    ('symbol', 'expected_market'),
    [
        ('SH601899', 'SH'),
        ('SZ000001', 'SZ'),
        ('BJ830799', 'BJ'),
        ('HK00700', 'HK'),
    ],
)
def test_watchlist_write_keeps_namespace_market(symbol, expected_market):
    """⚠️ 写入侧**刻意存 normalizer 命名空间**（SH/SZ/BJ/HK），不是契约市场。

    这条曾经被我改成断 `CN_A`（"顺手统一两套词表"），核实后撤回：
    `cross_domain._join_key` 直接拿 `watchlist.market` 当跨域冗余键，而
    `to_security_key` 的映射表只认 `SH`/`SZ`/`BJ`/`HK`——存 `CN_A` 会让场内自选的
    **市场侧资料 / 估值全部取不到**。

    详情页那个「已持有 vs 暂无持仓记录」的口径问题在**出口**修
    （resolve 返回前经 `to_contract_market` 归一），写入口径保持不动。
    """
    out = normalize_and_infer_venue(symbol, 'EXCHANGE', 'stock')

    assert out['market'] == expected_market
    assert out['venue'] == 'EXCHANGE'


def test_watchlist_write_keeps_otc_and_non_traded_branches():
    """场外与「非交易实体」两条既有分支不受本次归一影响。"""
    assert normalize_and_infer_venue('004369', 'OTC', 'fund')['market'] == 'CN_A'
    # 经理 / 投顾组合无市场实体，约定空串（存 NULL 会让唯一性失效）
    assert normalize_and_infer_venue('MGR_001', None, 'manager')['market'] == ''
    assert normalize_and_infer_venue('ZH0001', None, 'portfolio')['market'] == ''


def test_watchlist_write_index_branch_untouched():
    """指数按命名空间前缀定 market（CN_A / CSI / CNI），不属于本次归一范围。"""
    assert (
        normalize_and_infer_venue('SH000300', 'EXCHANGE', 'index')['market'] == 'CN_A'
    )
    assert normalize_and_infer_venue('CSI930950', '', 'index')['market'] == 'CSI'
