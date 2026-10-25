# -*- coding: utf-8 -*-
"""fetch_fund_scale 的上游列名契约（#2543）。

背景：2026-10-23 生产 run ``39971621884`` 里 akshare 抛
``"['基金代码', '基金简称', ...] not in index"``——上游改列名了。旧实现用
``row.get(...)`` 取值，列名一变就静默返回 ``[]``，与「上游今天没数据」无从区分。

本文件钉住改后的行为：**契约漂移必须显性抛错**，同时不误伤合法形态
（上游真的返回空表、上游新增未知列）。
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.adapters.akshare_adapter import (
    FUND_SCALE_KNOWN_COLUMNS,
    FUND_SCALE_REQUIRED_COLUMNS,
    AkshareAdapter,
)
from app.services.adapters.contract import UpstreamContractError, assert_columns


@pytest.fixture
def adapter():
    return AkshareAdapter()


def _frame(rows):
    """按契约列构造上游 DataFrame（缺列用 ``drop`` 造，见各用例）。"""
    return pd.DataFrame(rows, columns=list(FUND_SCALE_KNOWN_COLUMNS))


def _patch_ak(df=None, *, raises=None):
    """把 akshare 惰性入口替换成返回 df（或抛 raises）的假对象。"""
    ak = MagicMock()
    if raises is not None:
        ak.fund_scale_open_sina.side_effect = raises
    else:
        ak.fund_scale_open_sina.return_value = df
    return patch('app.core.akshare_lazy.get_akshare', return_value=ak)


# ── 契约常量本身 ──


def test_assert_columns_accepts_pandas_index_without_truthiness_error():
    """回归：``Index`` 的真值是歧义的，``columns or []`` 会抛 ValueError。

    本模块首次接入时正是由这条踩出来的（7 个用例连带红）。契约校验自己
    先踩「静默失败」的坑就太讽刺了，故钉在这里。
    """
    assert_columns(
        pd.Index(list(FUND_SCALE_KNOWN_COLUMNS)),
        required=FUND_SCALE_REQUIRED_COLUMNS,
        known=FUND_SCALE_KNOWN_COLUMNS,
        source='test',
    )

    with pytest.raises(UpstreamContractError):
        assert_columns(None, required=FUND_SCALE_REQUIRED_COLUMNS, known=(), source='test')


def test_required_columns_are_subset_of_known():
    """必填列必须是已知列的子集——否则「缺列」永远判不出来。"""
    assert set(FUND_SCALE_REQUIRED_COLUMNS) <= set(FUND_SCALE_KNOWN_COLUMNS)
    assert '基金代码' in FUND_SCALE_REQUIRED_COLUMNS


# ── 正常路径 ──


def test_returns_rows_when_columns_match(adapter):
    df = _frame(
        [
            ['000001', '华夏成长', 1.5, 10.0, 1.0e9, '2001-12-18', '张三', '2026-10-23'],
            ['510300', '沪深300ETF', 4.6, 300.0, 1.8e10, '2012-05-04', '李四', '2026-10-23'],
        ]
    )
    with _patch_ak(df):
        out = adapter.fetch_fund_scale()

    assert [o['fund_code'] for o in out] == ['000001', '510300']
    assert out[0]['shares'] == 1.0e9
    assert out[0]['nav'] == 1.5


def test_unknown_extra_column_does_not_raise(adapter):
    """上游加列不是漂移：不得判红（只走 warning）。"""
    df = _frame([['000001', '华夏成长', 1.5, 10.0, 1.0e9, '2001-12-18', '张三', '2026-10-23']])
    df['新增列_上游刚加的'] = 'x'
    with _patch_ak(df):
        out = adapter.fetch_fund_scale()

    assert len(out) == 1


def test_empty_upstream_returns_empty_list(adapter):
    """上游真的返回空表 → 返回 []，不得误报成契约漂移。"""
    with _patch_ak(pd.DataFrame(columns=list(FUND_SCALE_KNOWN_COLUMNS))):
        assert adapter.fetch_fund_scale() == []


# ── 漂移必须显性失败 ──


def test_missing_required_column_raises(adapter):
    """缺必填列即抛错，且异常里带齐「缺什么 / 现在有什么」。"""
    df = _frame([['000001', '华夏成长', 1.5, 10.0, 1.0e9, '2001-12-18', '张三', '2026-10-23']])
    df = df.drop(columns=['最近总份额'])

    with _patch_ak(df), pytest.raises(UpstreamContractError) as ei:
        adapter.fetch_fund_scale()

    assert ei.value.missing == ('最近总份额',)
    assert '最近总份额' in str(ei.value)
    # 「现有哪些列」必须一并给出：否则值班只能重新抓一次上游才知道变成了什么
    assert '基金代码' in ei.value.present


def test_renamed_code_column_raises(adapter):
    """列名整体改名（本次事故的真实形态）⇒ 抛错，不是静默空列表。"""
    df = _frame([['000001', '华夏成长', 1.5, 10.0, 1.0e9, '2001-12-18', '张三', '2026-10-23']])
    df = df.rename(columns={'基金代码': 'code', '最近总份额': 'shares', '单位净值': 'nav'})

    with _patch_ak(df), pytest.raises(UpstreamContractError) as ei:
        adapter.fetch_fund_scale()

    assert set(ei.value.missing) == {'基金代码', '最近总份额', '单位净值'}


def test_all_rows_unparsable_raises(adapter):
    """列名都在但**语义**变了（代码列不再 6 位数字）⇒ 抛错。

    旧实现里这条路的终点是静默的 []：契约列名齐了，但一行都取不出。
    """
    df = _frame([['000001.OF', '华夏成长', 1.5, 10.0, 1.0e9, '2001-12-18', '张三', '2026-10-23']])

    with _patch_ak(df), pytest.raises(UpstreamContractError) as ei:
        adapter.fetch_fund_scale()

    assert '列语义漂移' in str(ei.value)


def test_partially_unparsable_keeps_valid_rows(adapter):
    """个别脏行跳过是合法的，不得因为「有跳过」就整体抛错。"""
    rows = [
        ['000001', '华夏成长', 1.5, 10.0, 1.0e9, '2001-12-18', '张三', '2026-10-23'],
        ['-', '某只代码脏的基金', 1.0, 1.0, 1.0e8, '2020-01-01', '王五', '2026-10-23'],
    ]
    with _patch_ak(_frame(rows)):
        out = adapter.fetch_fund_scale()

    assert [o['fund_code'] for o in out] == ['000001']


# ── 异常不吞 ──


def test_upstream_exception_is_reraised_not_swallowed(adapter):
    """网络/上游异常原样抛出：不得再伪装成「返回空数据」。"""
    boom = ConnectionError('RemoteDisconnected')
    with _patch_ak(raises=boom), pytest.raises(ConnectionError):
        adapter.fetch_fund_scale()


def test_contract_error_is_not_downgraded_to_empty(adapter):
    """契约漂移不得被 except 链吞掉（UpstreamContractError 优先于通用 except）。"""
    df = _frame([['000001', '华夏成长', 1.5, 10.0, 1.0e9, '2001-12-18', '张三', '2026-10-23']])
    df = df.drop(columns=['单位净值'])

    with _patch_ak(df), pytest.raises(UpstreamContractError):
        adapter.fetch_fund_scale()
