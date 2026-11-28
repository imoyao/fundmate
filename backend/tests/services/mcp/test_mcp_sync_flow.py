# -*- coding: utf-8 -*-
"""数据同步流（#3304）回归网。

判定口径：同步 = 账户选择契约 + 置信度判定 + 审计留痕，三件事都不能静默失效。
覆盖（对应 issue 验收标准的四类分支 + 契约细节）：

- 账户发现：五组归一化（组缺失按空组）、scope 必传、畸形条目丢弃；
- 参数装配：选中的传 id、**未选组传空串**（上游契约，不是省略）、类型错位响亮拒绝；
- 置信度：正常匹配 high / 空持仓 low / 结构错位 low / 零重合 low；
- 强制导入：force=True 才 imported + forced，审计行留痕；
- 上游异常（isError / 非 JSON）：类型化上抛 + 审计记 error，不吞错。

桩模式与 ``test_mcp_connection_check.py`` 同族：把 ``_post_factory`` 打成桩，
只认 MCP 协议形状（initialize → notifications/initialized → tools/call），不出网。
"""

import json
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from app.core.database import user_session
from app.models.mcp_sync_audit import McpSyncAudit
from app.services.mcp import sync_flow
from app.services.mcp.errors import McpBadResponse
from app.services.mcp.sync_flow import build_tool_args, fetch_accounts, run_sync
from app.services.mcp.user_credentials import save_static_token


@pytest.fixture(autouse=True)
def credential_key(monkeypatch):
    monkeypatch.setenv('MCP_CREDENTIAL_KEY', Fernet.generate_key().decode('ascii'))
    monkeypatch.setenv('MCP_CREDENTIAL_KEY_VERSION', '1')


def _fake_response(payload, status=200):
    return SimpleNamespace(
        status_code=status,
        headers={'content-type': 'application/json'},
        text=json.dumps(payload),
        json=lambda: payload,
    )


def _call_result(text: str, is_error: bool = False):
    return {'result': {'isError': is_error, 'content': [{'type': 'text', 'text': text}]}}


@pytest.fixture
def tzzb_key(db):
    save_static_token(1, 'tzzb', 'user-key-1')


@pytest.fixture
def fake_upstream(monkeypatch):
    """协议桩：记录 tools/call 的参数，按 box['responses'] 返回配置的载荷。"""
    calls: list = []
    box: dict = {'responses': {}}

    def factory(provider, token, route=None):
        def post(payload, sid):
            calls.append({'payload': payload, 'sid': sid})
            method = payload.get('method')
            if method == 'initialize':
                return SimpleNamespace(status_code=200, headers={}, text='{}', json=lambda: {'result': {}})
            if method == 'notifications/initialized':
                return SimpleNamespace(status_code=200, headers={}, text='', json=lambda: {})
            if method == 'tools/call':
                name = payload['params']['name']
                resp = box['responses'].get(name)
                if resp is None:
                    raise AssertionError(f'桩未配置工具 {name} 的返回')
                return _fake_response(resp)
            raise AssertionError(f'意外的 MCP 方法：{method}')

        return post

    monkeypatch.setattr(sync_flow, '_post_factory', factory)
    return {'calls': calls, 'box': box}


def _last_audit() -> McpSyncAudit | None:
    with user_session() as session:
        return session.query(McpSyncAudit).order_by(McpSyncAudit.id.desc()).first()


_ACCOUNTS = {
    'fund_key': [{'id': '80381665', 'name': '股票账户', 'param': 'fundKey', 'lastSyncTime': '2026-11-27 19:39:12'}],
    'rzrq_fund_key': [],
    'manual_id': [{'id': '406776', 'name': '招商证券', 'param': 'manualId'}],
    'fund_id': [{'id': '27789642', 'name': '手工基金 - 稳稳的幸福', 'param': 'fundId'}],
    'cust_id': [],
}

_STOCK_POSITIONS = {
    'totalAsset': '369847.963000000',
    'totalMarketValue': '361720.343000000',
    'availableFunds': '8127.616800000',
    'holdings': [
        {'stockCode': '159316', 'stockName': '创新药E', 'marketValue': '13581.000', 'holdQuantity': '13500'},
        {'stockCode': '600519', 'stockName': '贵州茅台', 'marketValue': '1600.00', 'holdQuantity': '100'},
    ],
}


def test_fetch_accounts_normalizes_five_groups(fake_upstream, tzzb_key):
    fake_upstream['box']['responses'] = {'promptAccountSelection': _call_result(json.dumps(_ACCOUNTS))}
    result = fetch_accounts('tzzb', 1)

    assert result['provider'] == 'tzzb'
    groups = {g['group']: g for g in result['groups']}
    # 五组恒在（上游只回非空组，缺失按空组兜底）
    assert set(groups) == {'fund_key', 'rzrq_fund_key', 'manual_id', 'fund_id', 'cust_id'}
    assert groups['fund_key']['label'] == '证券账户'
    assert groups['fund_key']['param'] == 'fundKey'
    assert groups['fund_key']['accounts'][0]['id'] == '80381665'
    assert groups['fund_key']['accounts'][0]['lastSyncTime'] == '2026-11-27 19:39:12'
    assert groups['rzrq_fund_key']['accounts'] == []
    # scope 是上游 schema 的 required 字段，不能省
    tools_calls = [c for c in fake_upstream['calls'] if c['payload'].get('method') == 'tools/call']
    assert tools_calls[0]['payload']['params']['arguments'] == {'scope': 'all'}


def test_fetch_accounts_drops_malformed_entries(fake_upstream, tzzb_key):
    payload = {**_ACCOUNTS, 'fund_key': [{'name': '缺 id 应被丢弃'}, '不是字典也应被丢弃']}
    fake_upstream['box']['responses'] = {'promptAccountSelection': _call_result(json.dumps(payload))}
    groups = {g['group']: g for g in fetch_accounts('tzzb', 1)['groups']}
    assert groups['fund_key']['accounts'] == []


def test_fetch_accounts_bad_json_is_typed(fake_upstream, tzzb_key):
    fake_upstream['box']['responses'] = {'promptAccountSelection': _call_result('不是 JSON')}
    with pytest.raises(McpBadResponse):
        fetch_accounts('tzzb', 1)


def test_fetch_accounts_requires_account_tool(fake_upstream, tzzb_key):
    # qieman 没有登记 promptAccountSelection ⇒ 不能发起同步（不支持就明说，不猜）
    with pytest.raises(ValueError, match='不支持账户选择'):
        fetch_accounts('qieman', 1)


def test_build_args_selected_pass_id_unselected_pass_empty_string():
    accounts = [
        {'group': 'fund_key', 'id': '80381665'},
        {'group': 'manual_id', 'id': '406776'},
    ]
    args = build_tool_args('queryStockPosition', accounts)
    # 上游契约：账户参数**必传**，未选的类型传空串（不是省略键）
    assert args == {'fundKey': '80381665', 'rzrqFundKey': '', 'manualId': '406776'}


def test_build_args_group_mismatch_is_rejected():
    # 证券同步选了基金账户 = 类型错位，装配层响亮拒绝
    with pytest.raises(ValueError, match='不匹配'):
        build_tool_args('queryStockPosition', [{'group': 'fund_id', 'id': '27789642'}])


def test_run_sync_high_confidence_matches_local(fake_upstream, tzzb_key, monkeypatch):
    fake_upstream['box']['responses'] = {'queryStockPosition': _call_result(json.dumps(_STOCK_POSITIONS))}
    # 本地持仓里有 159316 ⇒ 有重合，全部信号健康
    monkeypatch.setattr(sync_flow, '_local_position_codes', lambda user_id: {'159316', '004369'})

    result = run_sync(
        'tzzb',
        1,
        [{'group': 'fund_key', 'id': '80381665'}, {'group': 'manual_id', 'id': '406776'}],
    )

    assert result['confidence'] == 'high'
    assert result['reasons'] == []
    assert result['imported'] is True
    assert result['forced'] is False
    assert result['summary']['count'] == 2
    assert result['summary']['overlap'] == 1
    assert result['items'][0]['code'] == '159316'
    row = _last_audit()
    assert row is not None
    assert row.confidence == 'high'
    assert row.imported is True
    assert row.forced is False
    assert '80381665' in row.accounts_json


def test_run_sync_empty_positions_is_low_confidence(fake_upstream, tzzb_key, monkeypatch):
    fake_upstream['box']['responses'] = {
        'queryStockPosition': _call_result(json.dumps({'totalAsset': '0', 'holdings': []}))
    }
    monkeypatch.setattr(sync_flow, '_local_position_codes', lambda user_id: set())

    result = run_sync('tzzb', 1, [{'group': 'fund_key', 'id': '80381665'}])

    assert result['confidence'] == 'low'
    assert result['imported'] is False  # 默认不落库
    assert any('空' in reason for reason in result['reasons'])
    row = _last_audit()
    assert row is not None
    assert row.imported is False


def test_run_sync_zero_overlap_is_suspicious(fake_upstream, tzzb_key, monkeypatch):
    fake_upstream['box']['responses'] = {'queryStockPosition': _call_result(json.dumps(_STOCK_POSITIONS))}
    monkeypatch.setattr(sync_flow, '_local_position_codes', lambda user_id: {'999999'})

    result = run_sync('tzzb', 1, [{'group': 'fund_key', 'id': '80381665'}])

    assert result['confidence'] == 'low'
    assert any('重合' in reason for reason in result['reasons'])


def test_run_sync_structure_mismatch_is_low(fake_upstream, tzzb_key, monkeypatch):
    # 选了基金账户但上游返回的不是基金形状（结构错位的一种）：缺 funds 列表 ⇒ low
    fake_upstream['box']['responses'] = {'queryFundAccount': _call_result(json.dumps({'account': {}}))}
    monkeypatch.setattr(sync_flow, '_local_position_codes', lambda user_id: set())

    result = run_sync('tzzb', 1, [{'group': 'fund_id', 'id': '27789642'}])

    assert result['confidence'] == 'low'
    assert any('funds' in reason for reason in result['reasons'])


def test_run_sync_force_imports_and_audits(fake_upstream, tzzb_key, monkeypatch):
    fake_upstream['box']['responses'] = {
        'queryStockPosition': _call_result(json.dumps({'totalAsset': '0', 'holdings': []}))
    }
    monkeypatch.setattr(sync_flow, '_local_position_codes', lambda user_id: set())

    result = run_sync('tzzb', 1, [{'group': 'fund_key', 'id': '80381665'}], force=True)

    assert result['confidence'] == 'low'
    assert result['imported'] is True
    assert result['forced'] is True
    row = _last_audit()
    assert row is not None
    assert row.forced is True
    assert row.imported is True


def test_run_sync_iserror_raises_but_audits(fake_upstream, tzzb_key):
    fake_upstream['box']['responses'] = {'queryStockPosition': _call_result('账户不存在', is_error=True)}
    with pytest.raises(McpBadResponse):
        run_sync('tzzb', 1, [{'group': 'fund_key', 'id': '80381665'}])

    row = _last_audit()
    assert row is not None
    assert row.confidence == 'error'
    assert row.imported is False
    assert row.tool == 'queryStockPosition'


def test_run_sync_rejects_empty_selection(fake_upstream, tzzb_key):
    # 双层校验的服务层兜底：就算绕过 pydantic 直达这里，空选也进不来
    with pytest.raises(ValueError, match='选择'):
        run_sync('tzzb', 1, [])


def test_run_sync_rejects_unknown_group(fake_upstream, tzzb_key):
    # 组清单由账户发现下发，未知组 = 请求伪造或版本错位 ⇒ 拒绝
    with pytest.raises(ValueError, match='未知的账户类型'):
        run_sync('tzzb', 1, [{'group': 'nope', 'id': '1'}])


def test_run_sync_rejects_mixed_family_selection(fake_upstream, tzzb_key):
    # 证券账户和基金账户混选 = 不是同一类数据，兜底拒绝（UI 层只允许单选）
    with pytest.raises(ValueError, match='同一类数据'):
        run_sync(
            'tzzb',
            1,
            [{'group': 'fund_key', 'id': '80381665'}, {'group': 'fund_id', 'id': '27789642'}],
        )
