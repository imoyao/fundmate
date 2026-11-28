# -*- coding: utf-8 -*-
"""MCP 工具目录（S5g）回归网。

判定口径：``mcp_provider_tools`` 是 provider 级共享缓存，**以最近一次 verify
的上游响应为真相源做全量对齐**，不是采样历史：

- 新工具插入、描述变化更新、上游下线的删除；
- 目录读侧不依赖用户在线；未采样过返回空列表；
- tzzb 的能力标注（``TOOL_CAPABILITIES``）只登记真机采样过的名字。
"""

import pytest

from app.models.mcp_provider_tool import McpProviderTool
from app.services.mcp.providers.tzzb import TOOL_CAPABILITIES
from app.services.mcp.tools_catalog import list_tools, sync_tools


def _rows(db, provider):
    return {
        row.tool_name: row.description for row in db.query(McpProviderTool).filter(McpProviderTool.provider == provider)
    }


def test_sync_inserts_updates_and_prunes(db):
    sync_tools(
        'tzzb',
        [{'name': 'queryFundAccount', 'description': '查询账户'}, {'name': 'old_tool', 'description': '将被下线'}],
    )

    # 第二次：改描述、加新工具、去掉 old_tool（模拟上游下线）
    sync_tools(
        'tzzb',
        [
            {'name': 'queryFundAccount', 'description': '查询账户（改版）'},
            {'name': 'new_tool', 'description': '新工具'},
        ],
    )

    rows = _rows(db, 'tzzb')
    assert rows == {'queryFundAccount': '查询账户（改版）', 'new_tool': '新工具'}


def test_list_tools_sorted_and_empty(db):
    assert list_tools('never-sampled') == []
    sync_tools('qieman', [{'name': 'b_tool', 'description': ''}, {'name': 'a_tool', 'description': '先注册但名字靠后'}])
    names = [tool['name'] for tool in list_tools('qieman')]
    assert names == sorted(names)
    # 两个 provider 互不串目录
    assert 'a_tool' not in [tool['name'] for tool in list_tools('tzzb')]


def test_sync_ignores_blank_entries(db):
    sync_tools(
        'qieman',
        [{'name': '', 'description': '无名'}, {'description': '缺 name'}, {'name': 'valid', 'description': ''}],
    )
    assert list(_rows(db, 'qieman')) == ['valid']


def test_sync_requires_provider():
    with pytest.raises(ValueError):
        sync_tools('', [{'name': 'x', 'description': ''}])


def test_tzzb_capabilities_only_sampled_names():
    # 纪律：没真机采过样的名字不进映射。2026-11-28 17:20 全链路 tools/list
    # 实测采到全部 15 个（verify 先采到 6 个，17:20 补齐），这里钉全集：
    # 登记超出本集合 = 登记了没采过的名字；少了 = 采样丢了没回填。
    sampled = {
        'promptAccountSelection',
        'queryFundAccount',
        'queryStockPosition',
        'queryClearedPosition',
        'queryFundHoldingReturns',
        'queryPnlSummary',
        'queryDayProfitSummary',
        'queryDayCalendarSummary',
        'queryMonthCalendarSummary',
        'queryMoneyHistory',
        'queryFundSummaryHistory',
        'queryAssetChangeSummary',
        'queryFundFeeRate',
        'queryFundConfirmNav',
        'queryStockMarketRemark',
    }
    assert set(TOOL_CAPABILITIES) == sampled
    assert TOOL_CAPABILITIES['queryAssetChangeSummary'] == '交易对账'
