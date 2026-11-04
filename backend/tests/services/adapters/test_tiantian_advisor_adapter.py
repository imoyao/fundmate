# -*- coding: utf-8 -*-
"""天天投顾适配器：字段映射与「两接口合并」契约（投顾详情页 P0，2026-10-29）。

## 为什么这个文件必须存在

2026-10-29 复测发现一个持续了几个月的误解：`models.py` 里写着「回撤 / 超额 API 不直接提供」，
而真相是**适配器只请求了 `FundIATGInfoAggr` 一个接口**（回撤 / 夏普 / 运行天数都在
`getTGQuoteByFavor` 里）。那段时间天天组合的 `max_drawdown` / `sharpe_ratio` /
`running_days` / `estab_date` 全部 0% 填充。

所以这里的用例不是在测「解析字符串」，而是在钉三件**会静默退化**的事：

1. **两个接口都要请求、都要映射**——少调一个，对应字段就静默变空，而日志全绿；
2. **日期方言的翻译在适配器内完成**——AGGR 的 `ESTABDATE` 是毫秒时间戳（`"1658764800000"`），
   落库层 `_parse_date` 只认 `YYYY-MM-DD` 前 10 位，不转就是「解析失败 → 字段为空」；
3. **缺失不落 0**——`RUN_DATE` 是空串时要给 `None`，给 0 会渲染成「运行 0 天」。

不发真实网络请求：`_request` / `_post_json` 在本文件里被替换成桩。
"""

import pytest

from app.services.adapters.tiantian_advisor_adapter import (
    TiantianAdvisorAdapter,
    _to_date_str,
    _to_float,
    _to_int,
)

# ── 真实响应节选（2026-10-29 实网抓取，XCOVSEX「越海」）──

_AGGR_PAYLOAD = {
    'success': True,
    'data': [
        {
            'TGNAME': '越海',
            'RISKLEVEL': 3,
            'STGCONCEPT': '以绝对收益为目标的多元资产配置',
            'ESTABDATE': '1658764800000',  # 毫秒时间戳 → 2022-07-26
            'STATUS': 1,
            'NAV': 1.18,
            'JZRQ': '2026-10-28',
            'ANNSYL_LN': '4.19',
            'SYL_D': '1.10',
            'SYL_Z': '-1.28',
            'SYL_Y': '-5.79',
            'SYL_3Y': '-5.85',
            'SYL_6Y': '-9.46',
            'SYL_JN': '-3.83',
            'SYL_1N': '-3.02',
            'SYL_2N': '25.39',
            'SYL_3N': '35.12',
            'SYL_LN': '18.46',
            'BENCHSYL_D': 1.03,
            'BENCHSYL_Z': -1.14,
            'BENCHSYL_Y': -6.37,
            'BENCHSYL_3Y': -9.51,
            'BENCHSYL_6Y': -13.79,
            'BENCHSYL_JN': -9.99,
            'BENCHSYL_1N': -10.4,
            'BENCHSYL_2N': 6.12,
            'BENCHSYL_3N': 16.87,
            'BENCHSYL_LN': 1.17,
            # 反例：AGGR 的 RUN_DATE 是空串，回撤 / 夏普根本没有这两个键
            'RUN_DATE': '',
        }
    ],
}

_QUOTE_PAYLOAD = {
    'Succeed': True,
    'ErrCode': 0,
    'Expansion': {'GZTIME': '2026-10-29', 'FSRQ': '2026-10-28'},
    # 实测 Data 是**单元素列表**，不是 dict —— 按 dict 写会 AttributeError
    'Data': [
        {
            'TGCODE': 'XCOVSEX',
            'TGNAME': '越海',
            'ESTABDATE': '2022-07-26 00:00:00',
            'JZRQ': '2026-10-28',
            'SYRQ': '2026-10-28',
            'RUN_DATE': 1556,
            'MAXRETRA_LN': '24.33',
            'SHARPE_LN': '0.16',
            'ANNSYL_LN': '4.19',
            'SYL_LN': '18.46',
            'SYL_Y': '-5.79',
            'STYPE': 0,
        }
    ],
}


class _Resp:
    """只实现 `_overview_from_aggr` 用到的 `.text`。"""

    def __init__(self, payload):
        import json

        self.text = json.dumps(payload, ensure_ascii=False)


@pytest.fixture
def adapter(monkeypatch):
    """把两个数据面都换成桩：AGGR 走 `_request`（Response），QUOTE 走 `_post_json`（dict）。"""
    a = TiantianAdvisorAdapter()
    monkeypatch.setattr(a, '_request', lambda method, url, **kw: _Resp(_AGGR_PAYLOAD))
    monkeypatch.setattr(a, '_post_json', lambda url, form: _QUOTE_PAYLOAD)
    return a


# ── 基础类型转换 ──


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('1658764800000', '2022-07-26'),  # AGGR 的 ESTABDATE：毫秒时间戳
        (1658764800000, '2022-07-26'),  # 万一是 int
        ('2022-07-26 00:00:00', '2022-07-26'),  # QUOTE 的 ESTABDATE
        ('2026-10-28', '2026-10-28'),
        ('', None),
        (None, None),
    ],
)
def test_to_date_str_normalizes_platform_dialects(raw, expected):
    """毫秒时间戳必须在这里转掉——落库层 `_parse_date` 只认 `YYYY-MM-DD`。"""
    assert _to_date_str(raw) == expected


def test_to_int_does_not_turn_empty_into_zero():
    """`RUN_DATE` 空串 → None。给 0 会让页面显示「运行 0 天」。"""
    assert _to_int('') is None
    assert _to_int(None) is None
    assert _to_int('abc') is None
    assert _to_int(1556) == 1556
    assert _to_int('1556') == 1556
    assert _to_int('1556.0') == 1556


def test_to_float_keeps_missing_as_none():
    assert _to_float('') is None
    assert _to_float(None) is None
    assert _to_float('-6.37') == pytest.approx(-6.37)


# ── 两个数据面的映射 ──


def test_aggr_face_maps_all_interval_and_benchmark_columns(adapter):
    """8 个基准区间 + 2/3 年区间 + 净值/净值日/年化都要映射出来。

    `BENCHSYL_D` / `BENCHSYL_Z` **刻意无列**（业绩表不展示日/周），不应凭空造 key。
    """
    ov = adapter._overview_from_aggr('XCOVSEX')

    assert ov['name'] == '越海'
    assert ov['nav'] == pytest.approx(1.18)
    assert ov['nav_date'] == '2026-10-28'
    assert ov['annual_return'] == pytest.approx(4.19)
    assert ov['return_2y'] == pytest.approx(25.39)
    assert ov['return_3y'] == pytest.approx(35.12)
    assert ov['return_1q'] == pytest.approx(-5.85)  # SYL_3Y = 近 3 月
    assert ov['return_6m'] == pytest.approx(-9.46)
    assert ov['benchmark_return_1m'] == pytest.approx(-6.37)
    assert ov['benchmark_return_2y'] == pytest.approx(6.12)
    assert ov['benchmark_return_3y'] == pytest.approx(16.87)
    assert ov['benchmark_return_since_incep'] == pytest.approx(1.17)
    assert 'benchmark_return_1d' not in ov
    assert 'benchmark_return_1w' not in ov


def test_aggr_face_converts_millisecond_estab_date(adapter):
    """这是天天组合 `estab_date` 长期 0% 的根因：`1658764800000` 直接入库解析失败。"""
    ov = adapter._overview_from_aggr('XCOVSEX')
    assert ov['estab_date'] == '2022-07-26'


def test_aggr_face_does_not_invent_drawdown(adapter):
    """AGGR 没有回撤 / 夏普 / 运行天数 —— 不能凭空给 0，必须缺席（或 None）。"""
    ov = adapter._overview_from_aggr('XCOVSEX')
    assert 'max_drawdown' not in ov
    assert 'sharpe_ratio' not in ov
    assert 'running_days' not in ov


def test_quote_face_maps_metrics_and_tolerates_list_data(adapter):
    """`Data` 是单元素 list；回撤 / 夏普 / 运行天数就在这里。"""
    ov = adapter._overview_from_quote('XCOVSEX')

    assert ov['max_drawdown'] == pytest.approx(24.33)
    assert ov['sharpe_ratio'] == pytest.approx(0.16)
    assert ov['running_days'] == 1556
    assert ov['estab_date'] == '2022-07-26'
    assert ov['annual_return'] == pytest.approx(4.19)


def test_quote_face_tolerates_dict_data(monkeypatch):
    """接口形态变了（list → dict）也要能读，不静默返回空。"""
    a = TiantianAdvisorAdapter()
    monkeypatch.setattr(a, '_post_json', lambda url, form: {**_QUOTE_PAYLOAD, 'Data': _QUOTE_PAYLOAD['Data'][0]})
    assert a._overview_from_quote('XCOVSEX')['running_days'] == 1556


# ── 合并契约 ──


def test_fetch_overview_merges_both_faces(adapter):
    """核心用例：少调任何一个接口，另一半字段就静默变空。

    - 回撤 / 夏普 / 运行天数只在 QUOTE；
    - `benchmark_return_*` 只在 AGGR；
    - `estab_date` 两边都有，QUOTE 的字符串形态更干净（毫秒戳已被 AGGR 转掉，两者同值）。
    """
    ov = adapter.fetch_overview('XCOVSEX')

    assert ov['max_drawdown'] == pytest.approx(24.33)
    assert ov['sharpe_ratio'] == pytest.approx(0.16)
    assert ov['running_days'] == 1556
    assert ov['benchmark_return_2y'] == pytest.approx(6.12)
    assert ov['return_2y'] == pytest.approx(25.39)
    assert ov['estab_date'] == '2022-07-26'


def test_fetch_overview_survives_quote_failure(monkeypatch):
    """QUOTE 挂了仍要返回 AGGR 那部分（落库层只覆盖非 None，不会冲掉库内已有值）。"""
    a = TiantianAdvisorAdapter()
    monkeypatch.setattr(a, '_request', lambda method, url, **kw: _Resp(_AGGR_PAYLOAD))
    monkeypatch.setattr(a, '_post_json', lambda url, form: None)

    ov = a.fetch_overview('XCOVSEX')
    assert ov['return_2y'] == pytest.approx(25.39)
    assert 'running_days' not in ov


def test_fetch_overview_survives_aggr_failure(monkeypatch):
    a = TiantianAdvisorAdapter()
    monkeypatch.setattr(a, '_request', lambda method, url, **kw: None)
    monkeypatch.setattr(a, '_post_json', lambda url, form: _QUOTE_PAYLOAD)

    ov = a.fetch_overview('XCOVSEX')
    assert ov['running_days'] == 1556
    assert 'benchmark_return_2y' not in ov


def test_fetch_overview_both_fail_returns_empty(monkeypatch):
    """两个都失败 → `{}`，由 job 记 skipped（不炸整个同步）。"""
    a = TiantianAdvisorAdapter()
    monkeypatch.setattr(a, '_request', lambda method, url, **kw: None)
    monkeypatch.setattr(a, '_post_json', lambda url, form: None)
    assert a.fetch_overview('XCOVSEX') == {}


# ── canonical 列名必须与模型列一致 ──


def test_canonical_covers_new_columns():
    """新增列必须同时进 `CANONICAL_OVERVIEW_COLUMNS`，否则落库层根本不遍历它。

    这条是「加了映射但没进 canonical ⇒ 数据取到了却没人写」的守卫。
    """
    from app.services.adapters.advisor_source import CANONICAL_OVERVIEW_COLUMNS

    expected = {
        'return_2y',
        'return_3y',
        'benchmark_return_1m',
        'benchmark_return_1q',
        'benchmark_return_6m',
        'benchmark_return_ytd',
        'benchmark_return_1y',
        'benchmark_return_2y',
        'benchmark_return_3y',
        'benchmark_return_since_incep',
    }
    assert expected <= set(CANONICAL_OVERVIEW_COLUMNS)


def test_canonical_columns_exist_on_model():
    """canonical 里的每个名字都必须是 `advisor_portfolios` 的真实列。

    反过来的漏写（有列没进 canonical）由上面的用例管；这条管笔误 ——
    `CANONICAL_OVERVIEW_COLUMNS` 写错一个字，落库时 `setattr` 会静默写到不存在的地方。
    """
    from app.domains.funds.models import AdvisorPortfolio
    from app.services.adapters.advisor_source import CANONICAL_OVERVIEW_COLUMNS

    model_cols = set(AdvisorPortfolio.__table__.columns.keys())
    assert set(CANONICAL_OVERVIEW_COLUMNS) <= model_cols


def test_run_date_is_days_not_a_date():
    """`RUN_DATE` 是**运行天数**（1556），不是运行日期。

    这个坑值得留一条：AGGR 里 `RUN_DATE` 返回空串、QUOTE 里返回 int，两种形态都容易被
    当成日期字段去做 `strptime`，结果不是报错就是得到 1970 年。
    """
    assert _to_int('1556') == 1556
    assert _to_int('') is None  # AGGR 是空串 —— 不能变成 0 天
    # `_to_date_str` 把裸 int 当毫秒时间戳（ESTABDATE 的历史形态），
    # 所以日期字段与天数**必须走不同的转换函数**，不能共用一个。
    assert _to_date_str(1556) == '1970-01-01'
