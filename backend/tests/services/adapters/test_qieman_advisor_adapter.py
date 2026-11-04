# -*- coding: utf-8 -*-
"""且慢投顾适配器：**官方**历史调仓（`/alfa/v1/graphql`）的解析与翻页。

## 为什么这个文件必须存在（2026-11-03）

本适配器曾经写着「且慢无历史调仓接口」，调仓只能由持仓快照推导。那句话是**探错端点族**
得出的错结论：当时只试了 `qieman.com/pmapi/**`，从未试 `/alfa/v1/graphql`。
真接口匿名可取，唯一门槛是 `x-sign`。于是这里要钉住四件**会静默出错**的事：

1. **`x-sign` 的算法**——算错不会报错，只会让服务端回 `200 + data:null`，
   看起来像「这个组合没有调仓」。故用固定时间戳做确定性断言；
2. **取 `parts[].movementName` 而不是 `groups[].movementName`**——后者是分类汇总，
   同一 group 里可同时有持平/调出/调增；取错会给整组基金套同一个动作，
   页面上每只基金的方向全错，而数据「看着很合理」；
3. **比例是小数要 ×100**——库内 `pre_ratio` / `after_ratio` 是百分点，
   不转换会把 4% 显示成 0.04%；
4. **「拿不到」必须与「确实没有」分开**——前者要为失败的可见性负责（打 WARNING、
   上层回退快照推导），后者是计划型组合（`LONG_WIN`）的正常形态。

不发真实网络请求：`_post_graphql` 在本文件里被替换成桩。
"""

from typing import Dict, List, Optional

import pytest

from app.services.adapters.qieman_advisor_adapter import (
    _MOVEMENT_NOOP,
    QiemanAdvisorAdapter,
    _pct,
    x_sign,
)

# ── 真实响应节选（2026-11-03 实网抓取，ZH012926「远足」，只留字段裁掉无关 __typename）──

_RAW_ADJUSTMENT = {
    'date': '2026-10-30',
    'comment': '本次调出 华宝中证银行ETF联接A，调增 招商中证白酒指数A',
    'adjustmentId': 20261030,
    'article': {'text': '调仓说明', 'link': 'https://qieman.com/alfa/article/1'},
    'groups': [
        {
            # 分类汇总动作：整组是「调出」，但 parts 里同时有一条持平
            'categoryCode': '000001',
            'categoryCodeLevel1': '000002',
            'movementName': '调出',
            'parts': [
                {
                    'fund': {'fundCode': '012345', 'fundName': '华宝中证银行ETF联接A'},
                    'movementName': '调出',
                    'beforePercent': 0.04,  # 小数：4%
                    'afterPercent': 0.0,
                },
                {
                    'fund': {'fundCode': '009999', 'fundName': '留着的基金'},
                    'movementName': _MOVEMENT_NOOP,
                    'beforePercent': 0.10,
                    'afterPercent': 0.10,
                },
                {
                    'fund': {'fundCode': '005827', 'fundName': '易方达蓝筹精选混合'},
                    'movementName': '调增',
                    'beforePercent': 0.1031,
                    'afterPercent': 0.12,
                },
            ],
        }
    ],
}


def _adapter() -> QiemanAdvisorAdapter:
    return QiemanAdvisorAdapter()


# ── x-sign ────────────────────────────────────────────────────────────────


def test_x_sign_is_deterministic_for_fixed_timestamp():
    """固定时间戳 → 固定签名。算错不会报错，只会拿到 `data:null`（静默空结果）。"""
    # 手算：floor(1.01 * 1700000000000) = 1717000000000
    # SHA256('1717000000000') 的前 32 位大写十六进制（浏览器 bundle 的 substring(0, 32)）
    sig = x_sign(1700000000000)
    assert sig.startswith('1700000000000')
    assert len(sig) == len('1700000000000') + 32
    assert sig == sig.upper()
    assert sig == _expected_sign(1700000000000)


def test_x_sign_changes_with_time():
    assert x_sign(1700000000000) != x_sign(1700000000001)


def _expected_sign(ts: int) -> str:
    import hashlib
    import math

    digest = hashlib.sha256(str(int(math.floor(1.01 * ts))).encode()).hexdigest().upper()[:32]
    return f'{ts}{digest}'


# ── 比例换算 ───────────────────────────────────────────────────────────────


def test_pct_converts_fraction_to_percentage_points():
    """官方是小数（0.04 = 4%），库内是百分点（4.0）。不乘 100 会显示成 0.04%。"""
    assert _pct(0.04) == pytest.approx(4.0)
    assert _pct(0.1031) == pytest.approx(10.31)


def test_pct_keeps_none_and_survives_garbage():
    assert _pct(None) is None
    assert _pct('abc') is None
    assert _pct('') is None


def test_pct_trims_float_tail():
    """0.1031*100 = 10.310000000000001，四舍五入到 4 位消掉尾巴（不引入展示误差）。"""
    assert _pct(0.1031) == 10.31


# ── 单次调仓解析 ────────────────────────────────────────────────────────────


def test_parse_adjustment_takes_movement_from_parts_not_groups():
    """取 `parts[].movementName`：group 的 `调出` 不能套到同组的 `调增` 基金上。"""
    node = QiemanAdvisorAdapter._parse_adjustment(_RAW_ADJUSTMENT)

    assert node is not None
    assert node['adjust_date'] == '2026-10-30'
    by_code = {f['fund_code']: f for f in node['funds']}
    assert by_code['005827']['op_name'] == '调增'
    assert by_code['012345']['op_name'] == '调出'
    # 若取 group 的动作名，这条会变成「调出」——正是本用例要拦的形态
    assert by_code['005827']['op_name'] != '调出'


def test_parse_adjustment_drops_flat_rows():
    """持平行占官方的 50%~70%，落库会把列表淹没；库内推导口径也只记真实变化。"""
    node = QiemanAdvisorAdapter._parse_adjustment(_RAW_ADJUSTMENT)
    assert '009999' not in {f['fund_code'] for f in node['funds']}


def test_parse_adjustment_converts_ratios_to_percentage_points():
    node = QiemanAdvisorAdapter._parse_adjustment(_RAW_ADJUSTMENT)
    by_code = {f['fund_code']: f for f in node['funds']}
    assert by_code['012345']['pre_ratio'] == pytest.approx(4.0)
    assert by_code['012345']['after_ratio'] == pytest.approx(0.0)
    assert by_code['005827']['pre_ratio'] == pytest.approx(10.31)


def test_parse_adjustment_maps_movement_to_op_code_but_keeps_official_wording():
    """`op_name` 原样保留官方用词（调入≠调增），只按语义补 `op_code`。"""
    node = QiemanAdvisorAdapter._parse_adjustment(_RAW_ADJUSTMENT)
    by_code = {f['fund_code']: f for f in node['funds']}
    assert by_code['005827']['op_code'] == 2  # 调增 → 加仓
    assert by_code['012345']['op_code'] == 3  # 调出 → 减仓


def test_parse_adjustment_returns_none_when_all_flat():
    """全是持有平的调仓日 → 不落库（否则前端出现「0 只调整」的空壳分组）。"""
    raw = {
        'date': '2026-10-31',
        'comment': '',
        'groups': [
            {
                'movementName': '持平',
                'parts': [
                    {
                        'fund': {'fundCode': '000001', 'fundName': 'A'},
                        'movementName': _MOVEMENT_NOOP,
                        'beforePercent': 0.1,
                        'afterPercent': 0.1,
                    }
                ],
            }
        ],
    }
    assert QiemanAdvisorAdapter._parse_adjustment(raw) is None


def test_parse_adjustment_normalizes_comment_whitespace():
    raw = dict(_RAW_ADJUSTMENT, comment='  第一行\n\n第二行\t\t')
    node = QiemanAdvisorAdapter._parse_adjustment(raw)
    assert node['reason'] == '第一行 第二行'


def test_parse_adjustment_empty_comment_does_not_fabricate_text():
    """实测 ZH000129 138 条里 25 条 `comment` 为空——不得编造理由。"""
    raw = dict(_RAW_ADJUSTMENT, comment='')
    node = QiemanAdvisorAdapter._parse_adjustment(raw)
    assert node['reason'] == ''


def test_parse_adjustment_rejects_malformed_date():
    raw = dict(_RAW_ADJUSTMENT, date='2026-1-3')
    assert QiemanAdvisorAdapter._parse_adjustment(raw) is None


# ── 翻页与错误分流 ──────────────────────────────────────────────────────────


def _graphql_body(items: List[dict], has_more: bool, cursor: Optional[str]) -> Dict:
    return {
        'data': {
            'portfolio': {
                'adjustments': {
                    'adjustments': items,
                    'totalCount': len(items),
                    'pageInfo': {'hasMore': has_more, 'cursor': cursor},
                }
            }
        }
    }


def test_fetch_adjustments_follows_cursor_until_has_more_false():
    """单页上限是 50（实测 totalCount=118 只回 50），必须按 cursor 翻完。"""
    a = _adapter()
    calls: List[Optional[str]] = []
    pages = [
        _graphql_body([dict(_RAW_ADJUSTMENT, date='2026-10-30')], True, 'MQ=='),
        _graphql_body([dict(_RAW_ADJUSTMENT, date='2026-10-29')], False, None),
    ]

    def fake_post(code, cursor):
        calls.append(cursor)
        return pages[len(calls) - 1]

    a._post_graphql = fake_post  # type: ignore[method-assign]
    nodes, err = a._fetch_adjustments('ZH012926')

    assert err is None
    assert calls == [None, 'MQ==']
    assert [n['adjust_date'] for n in nodes] == ['2026-10-30', '2026-10-29']


def test_fetch_adjustments_reports_graphql_error_instead_of_empty_success():
    """`data:null` + errors 必须变成错误串——退化成空列表会被读成「这个组合没调仓」。"""
    a = _adapter()
    a._post_graphql = lambda code, cursor: {  # type: ignore[method-assign]
        'data': None,
        'errors': [{'message': 'Internal Server Error', 'extensions': {'code': 'INTERNAL_SERVER_ERROR'}}],
    }
    nodes, err = a._fetch_adjustments('ZH012926')
    assert nodes == []
    assert err is not None and 'INTERNAL_SERVER_ERROR' in err


def test_fetch_adjustments_reports_missing_portfolio_namespace():
    """计划型组合（LONG_WIN）不在 `alfa/portfolio` 命名空间 → portfolio 为 null。"""
    a = _adapter()
    a._post_graphql = lambda code, cursor: {'data': {'portfolio': None}}  # type: ignore[method-assign]
    nodes, err = a._fetch_adjustments('LONG_WIN')
    assert nodes == []
    assert err is not None and 'alfa/portfolio' in err


def test_fetch_adjustments_surfaces_transport_failure():
    a = _adapter()

    def boom(code, cursor):
        raise RuntimeError('HTTP 502')

    a._post_graphql = boom  # type: ignore[method-assign]
    nodes, err = a._fetch_adjustments('ZH012926')
    assert nodes == []
    assert err == 'HTTP 502'


# ── fetch_rebalances 契约 ──────────────────────────────────────────────────


def test_fetch_rebalances_falls_back_to_empty_on_error():
    """契约要求数据面不抛错：失败返回 `[]`，由上层回退快照推导（不是让页面挂掉）。"""
    a = _adapter()

    def boom(code, cursor):
        raise RuntimeError('HTTP 502')

    a._post_graphql = boom  # type: ignore[method-assign]
    assert a.fetch_rebalances('ZH012926') == []


def test_fetch_rebalances_empty_code_makes_no_request():
    a = _adapter()

    def should_not_be_called(code, cursor):
        raise AssertionError('空代码不该发请求')

    a._post_graphql = should_not_be_called  # type: ignore[method-assign]
    assert a.fetch_rebalances('') == []
    assert a.fetch_rebalances('   ') == []


def test_adapter_declares_both_capability_flags():
    """且慢是「官方接口 + 计划型组合降级推导」并存，两个能力位必须同时为真。"""
    a = _adapter()
    assert a.has_official_rebalances is True
    assert a.derive_rebalances_from_snapshots is True
    assert a.official_rebalance_source == 'qieman_official'
