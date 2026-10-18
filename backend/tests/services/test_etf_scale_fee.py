# -*- coding: utf-8 -*-
"""ETF 规模 / 费率取数（#2333）。

重点覆盖七件事：
1. **规模解析**：上交所整表 JSON（``SEC_CODE``/``TOT_VOL`` 万份）、深交所 xlsx DataFrame
   （数值型代码补零 / 千分位逗号 / 自带净值）、腾讯批量快照（``[2]``/``[45]``，坏行丢弃）；
2. **规模口径**：沪市 万份 × 对比表净值 / 1e4；深市 份 × 源内净值 / 1e8；
3. **规模降级**：交易所源挂 → 腾讯兜底；腾讯也挂 → 缺席（None → 前端 —）；
4. **费率解析**：东财 F10 一行四列、同花顺 ``ul.g-dialog``；风控页/改版 → 源失败 None；
5. **费率降级链**：新值(≤30d)零请求 → em → ths → 旧值 → null，每步 log 不静默；
6. **小表读写**：upsert 幂等（唯一键）、新鲜旧值直用零外部请求、超 30 天重抓失败沿用；
7. **域登记**：``etf_fee_rates`` 登记 market 域（DATA_DOMAIN_REGISTRY 硬规则）。

聚合测试一律不联网（monkeypatch 全量）。
"""

from contextlib import closing
from datetime import datetime, timedelta

import pandas as pd

from app.core import db_factory
from app.domains.funds.models import EtfFeeRate
from app.services import etf_scale_fee as sf
from app.services.etf_scale_fee import (
    build_fee_map,
    build_scale_map,
    parse_fee_em,
    parse_fee_ths,
    parse_sse_scale,
    parse_szse_scale,
    parse_tencent_scale,
)

# ── 录制样例（2026-10-18 本机实测响应裁剪，字段形态与真实源一致）──────────
_SSE_PAYLOAD = {
    'pageHelp': {
        'data': [
            {'SEC_CODE': '510300', 'SEC_NAME': '沪深300ETF', 'TOT_VOL': '1275234.56'},
            {'SEC_CODE': '588880', 'SEC_NAME': '科创100ETF', 'TOT_VOL': '303742.10'},
            {'SEC_CODE': '51030', 'SEC_NAME': '坏代码', 'TOT_VOL': '100.0'},  # 非 6 位丢弃
            {'SEC_CODE': '590010', 'SEC_NAME': '坏份额', 'TOT_VOL': 'n/a'},  # 份额非数值丢弃
            {'SEC_CODE': '590011', 'SEC_NAME': '零份额', 'TOT_VOL': '0'},  # 非正丢弃
        ]
    }
}


def _tencent_line(flag: str, name: str, code: str, last: str, scale: str) -> str:
    """构造腾讯快照单行：字段 0~4 固定，中间补零，[45]=总市值（与实测 46 字段形态一致）。

    行名（``v_xxx=`` 左侧）解析器不读，用 ``v_test{code}`` 占位即可。
    """
    head = '~'.join([flag, name, code, last, scale])
    zeros = '~'.join(['0'] * 40)  # 5 + 40 + 1 = 46 字段，[45] = scale
    return f'v_test{code}="{head}~{zeros}~{scale}"'


_TENCENT_TEXT = ';'.join(
    [
        _tencent_line('1', '沪深300ETF', '510300', '4.236', '1209.50'),
        _tencent_line('0', '创业板ETF', '159915', '2.789', '710.37'),
        'v_sh999999="1~坏行~999999~1.0"',  # 字段不足丢弃
    ]
)


def _szse_df():
    """深交所 xlsx 实测列名形态（数值型代码、千分位份额、自带净值）。"""
    return pd.DataFrame(
        [
            {'基金代码': 159915.0, '基金简称': '创业板ETF', '当前规模(份)': '25,936,454,936', '净值': 2.8016},
            {'基金代码': 159191.0, '基金简称': '港股创新药ETF', '当前规模(份)': '3,100,000,000', '净值': 'bad'},
            {'基金代码': 'bad', '基金简称': '坏行', '当前规模(份)': '1,000', '净值': 1.0},
        ]
    )


# ── 1/2. 规模解析与口径 ─────────────────────────────────────────────────
def test_parse_sse_scale():
    out = parse_sse_scale(_SSE_PAYLOAD)
    assert out == {'510300': 1275234.56, '588880': 303742.10}
    assert parse_sse_scale(None) == {}
    assert parse_sse_scale({'pageHelp': {}}) == {}  # 空整表防御（正常源不可能）


def test_parse_szse_scale():
    out = parse_szse_scale(_szse_df())
    assert set(out) == {'159915', '159191'}  # 数值型代码补零；坏行丢弃
    assert out['159915'] == {'shares': 25936454936.0, 'nav': 2.8016}  # 千分位已去
    assert out['159191'] == {'shares': 3100000000.0}  # 净值坏 → 不带 nav 键，不编数
    assert parse_szse_scale(pd.DataFrame()) == {}


def test_parse_tencent_scale():
    out = parse_tencent_scale(_TENCENT_TEXT)
    assert out == {'510300': 1209.50, '159915': 710.37}  # 坏行（字段不足）丢弃
    assert parse_tencent_scale('') == {}


def test_build_scale_map_szse_self_contained(monkeypatch):
    """深市自带净值直乘（不依赖 nav_map）；沪市用对比表净值；腾讯不被调用。"""
    monkeypatch.setattr(sf, '_cached_sse_shares', lambda: {'510300': 1275234.56})
    monkeypatch.setattr(sf, '_cached_szse_scale', lambda: {'159915': {'shares': 25936454936.0, 'nav': 2.8016}})
    tencent_calls = []
    monkeypatch.setattr(sf, 'fetch_tencent_scale', lambda codes: tencent_calls.append(list(codes)) or {})

    out = build_scale_map(['510300', '159915'], {'510300': {'nav': 4.01}})

    assert out['159915'] == round(25936454936.0 * 2.8016 / 1e8, 2)  # ≈ 726.75
    assert out['510300'] == round(1275234.56 * 4.01 / 1e4, 2)  # 万份×净值/1e4 ≈ 511.37
    assert tencent_calls == []  # 两所都命中 → 零兜底请求


def test_build_scale_map_szse_nav_fallback_to_map(monkeypatch):
    """深市源内净值缺失 → 落对比表 nav_map；再缺 → 腾讯兜底。"""
    monkeypatch.setattr(sf, '_cached_sse_shares', lambda: {})
    monkeypatch.setattr(sf, '_cached_szse_scale', lambda: {'159915': {'shares': 2800000000.0}})
    monkeypatch.setattr(sf, 'fetch_tencent_scale', lambda codes: {'588880': 99.9})

    out = build_scale_map(['159915', '588880'], {'159915': {'nav': 2.5}})

    assert out['159915'] == round(2800000000.0 * 2.5 / 1e8, 2)  # 70.0
    assert out['588880'] == 99.9  # 交易所整表缺席 → 腾讯兜底
    assert build_scale_map([], {}) == {}  # 空 codes 零请求


# ── 3. 规模降级 ────────────────────────────────────────────────────────
def test_build_scale_map_exchange_down_tencent_fallback(monkeypatch):
    """交易所源挂 → 该侧全部落腾讯兜底；腾讯也挂 → 缺席（None 语义由调用方 .get 保证）。"""
    monkeypatch.setattr(sf, '_cached_sse_shares', lambda: (_ for _ in ()).throw(RuntimeError('sse down')))
    monkeypatch.setattr(sf, '_cached_szse_scale', lambda: (_ for _ in ()).throw(RuntimeError('szse down')))
    monkeypatch.setattr(sf, 'fetch_tencent_scale', lambda codes: {'510300': 1209.5, '159915': 710.37})

    out = build_scale_map(['510300', '159915'], {})
    assert out == {'510300': 1209.5, '159915': 710.37}

    monkeypatch.setattr(sf, 'fetch_tencent_scale', lambda codes: (_ for _ in ()).throw(RuntimeError('tencent down')))
    out = build_scale_map(['510300'], {})
    assert '510300' not in out  # 全链挂 → 缺席 → 前端 —


# ── 4. 费率解析 ────────────────────────────────────────────────────────
_FEE_HTML_EM = """
<html><body><table class="w782 comm lsjz">
<tr><td>管理费率</td><td>0.15%（每年）</td><td>托管费率</td><td>0.05%（每年）</td></tr>
</table></body></html>
"""

_FEE_HTML_THS = """
<html><body><ul class="g-dialog">
<li><span class="key">管理费</span><span class="value">0.50%</span></li>
<li><span class="key">托管费</span><span class="value">0.10%</span></li>
</ul></body></html>
"""


def test_parse_fee_em():
    assert parse_fee_em(_FEE_HTML_EM) == {'mgmt_fee_pct': 0.15, 'custody_fee_pct': 0.05}
    assert parse_fee_em('') is None  # 空 body
    assert parse_fee_em('<html><body>风控验证</body></html>') is None  # 无「管理费率」关键字
    # 键在但值全坏 → 源失败（不半编数）
    assert parse_fee_em('<table><tr><td>管理费率</td><td>N/A</td><td>托管费率</td><td>-</td></tr></table>') is None


def test_parse_fee_ths():
    assert parse_fee_ths(_FEE_HTML_THS) == {'mgmt_fee_pct': 0.5, 'custody_fee_pct': 0.1}
    assert parse_fee_ths('') is None
    assert parse_fee_ths('<html><body><ul class="other"></ul></body></html>') is None  # g-dialog 缺失
    # g-dialog 在但费率键缺失 → 源失败
    assert (
        parse_fee_ths(
            '<ul class="g-dialog"><li><span class="key">成立日</span><span class="value">2012</span></li></ul>'
        )
        is None
    )


# ── 5/6. 费率降级链 + 小表 ─────────────────────────────────────────────
def _seed_fee(db, code='510300', mgmt=0.5, custody=0.1, fetched_at=None):
    row = EtfFeeRate(etf_code=code, mgmt_fee_pct=mgmt, custody_fee_pct=custody, source='em')
    row.fetched_at = fetched_at or datetime(2026, 10, 1)
    db.add(row)
    db.commit()
    return row


def test_fee_fresh_row_zero_request(monkeypatch):
    """≤30 天旧值直用，零外部请求。"""
    calls = []
    monkeypatch.setattr(sf, 'fetch_fee_em', lambda code: calls.append('em') or {})
    monkeypatch.setattr(sf, 'fetch_fee_ths', lambda code: calls.append('ths') or {})
    with closing(db_factory.market_session_factory()()) as db:
        _seed_fee(db, fetched_at=datetime.now() - timedelta(days=10))
        fees = sf._resolve_fee(db, '510300')
    assert fees == {'mgmt_fee_pct': 0.5, 'custody_fee_pct': 0.1}
    assert calls == []


def test_fee_em_down_ths_success(monkeypatch):
    """主源挂 → 备源成功 → upsert 落表（source=ths）。"""
    monkeypatch.setattr(sf, 'fetch_fee_em', lambda code: (_ for _ in ()).throw(RuntimeError('em down')))
    monkeypatch.setattr(sf, 'fetch_fee_ths', lambda code: {'mgmt_fee_pct': 0.5, 'custody_fee_pct': 0.1})
    with closing(db_factory.market_session_factory()()) as db:
        fees = sf._resolve_fee(db, '510300')  # 无旧值
        assert fees == {'mgmt_fee_pct': 0.5, 'custody_fee_pct': 0.1}
        row = db.query(EtfFeeRate).filter(EtfFeeRate.etf_code == '510300').first()
        assert row is not None and row.source == 'ths'
        db.expire_all()
        # 第二次：新值 ≤30d → 零请求直用
        calls = []
        monkeypatch.setattr(sf, 'fetch_fee_em', lambda code: calls.append('em') or {})
        fees2 = sf._resolve_fee(db, '510300')
        assert fees2 == fees and calls == []


def test_fee_both_down_stale_row_kept(monkeypatch):
    """双源均失败 + 有超期旧值 → 沿用旧值（不删行不编数）。"""
    monkeypatch.setattr(sf, 'fetch_fee_em', lambda code: (_ for _ in ()).throw(RuntimeError('em down')))
    monkeypatch.setattr(sf, 'fetch_fee_ths', lambda code: None)  # 解析失败（风控页）
    with closing(db_factory.market_session_factory()()) as db:
        _seed_fee(db, fetched_at=datetime.now() - timedelta(days=60))
        fees = sf._resolve_fee(db, '510300')
    assert fees == {'mgmt_fee_pct': 0.5, 'custody_fee_pct': 0.1}  # 旧值仍在


def test_fee_both_down_no_row_null(monkeypatch):
    """双源均失败 + 无旧值 → null（诚实空，不编数）。"""
    monkeypatch.setattr(sf, 'fetch_fee_em', lambda code: None)
    monkeypatch.setattr(sf, 'fetch_fee_ths', lambda code: (_ for _ in ()).throw(RuntimeError('ths down')))
    with closing(db_factory.market_session_factory()()) as db:
        fees = sf._resolve_fee(db, '510300')
        assert fees == {'mgmt_fee_pct': None, 'custody_fee_pct': None}
        assert db.query(EtfFeeRate).filter(EtfFeeRate.etf_code == '510300').first() is None  # 失败不落表


def test_upsert_fee_row_idempotent():
    """etf_code 唯一键 upsert 幂等：两次写一行，后写覆盖先写。"""
    with closing(db_factory.market_session_factory()()) as db:
        sf.upsert_fee_row(db, '510300', {'mgmt_fee_pct': 0.15, 'custody_fee_pct': 0.05}, 'em')
        sf.upsert_fee_row(db, '510300', {'mgmt_fee_pct': 0.5, 'custody_fee_pct': 0.1}, 'ths')
        rows = db.query(EtfFeeRate).filter(EtfFeeRate.etf_code == '510300').all()
        assert len(rows) == 1
        assert rows[0].mgmt_fee_pct == 0.5 and rows[0].source == 'ths'
        assert rows[0].fetched_at is not None


def test_build_fee_map_independent_per_code(monkeypatch):
    """逐只独立降级：A 只成功、B 只 null，互不影响。"""

    def _em(code):
        if code == '510300':
            return {'mgmt_fee_pct': 0.15, 'custody_fee_pct': 0.05}
        return None

    monkeypatch.setattr(sf, 'fetch_fee_em', _em)
    monkeypatch.setattr(sf, 'fetch_fee_ths', lambda code: None)
    with closing(db_factory.market_session_factory()()) as db:
        out = build_fee_map(db, ['510300', '159915'])
    assert out['510300'] == {'mgmt_fee_pct': 0.15, 'custody_fee_pct': 0.05}
    assert out['159915'] == {'mgmt_fee_pct': None, 'custody_fee_pct': None}


# ── 7. 域登记 ──────────────────────────────────────────────────────────
def test_etf_fee_rates_registered_market_domain():
    """DATA_DOMAIN_REGISTRY 硬规则：新表必须登记且归属 market。"""
    from app.core.db_factory import DATA_DOMAIN_REGISTRY

    assert DATA_DOMAIN_REGISTRY['etf_fee_rates'] == 'market'


def test_etf_fee_rate_model_table_name():
    assert EtfFeeRate.__tablename__ == 'etf_fee_rates'
