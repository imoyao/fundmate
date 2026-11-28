# -*- coding: utf-8 -*-
"""一次性探针（#3304）：采样 tzzb promptAccountSelection / 持仓工具的真实返回形状。

用法（跨 worktree 跑真库，见 .workbuddy/memory 惯例）::

    cd 主仓/backend
    PYTHONPATH=<wt>/backend APP_INSTANCE_GUARD=0 .venv/Scripts/python.exe \
        <wt>/backend/scripts/probe_tzzb_sync_sample.py

只读不写：除 mcp_call_logs 审计（transport 自动）外不落任何业务表。
输出强制 UTF-8，避免 GBK 乱码污染断言。
"""

import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

from loguru import logger  # noqa: E402  探针要先设 stdout 编码再 import

logger.remove()  # 探针只要 print，别让日志刷屏

# 显式 import 关联模型（否则 SQLAlchemy mapper 配置缺名字报 InvalidRequestError）
from app.core.database import user_session  # noqa: E402
from app.domains.funds.models import Fund  # noqa: E402,F401
from app.domains.ledgers.models import Ledger  # noqa: E402,F401
from app.models.user_mcp_credential import UserMcpCredential  # noqa: E402
from app.services.mcp.connection_check import _post_factory  # noqa: E402
from app.services.mcp.oauth_connection_routes import resolve_connection_route  # noqa: E402
from app.services.mcp.providers.tzzb import TzzbProvider  # noqa: E402
from app.services.mcp.transport import McpTransport  # noqa: E402
from app.services.mcp.user_credentials import credential_auth_type  # noqa: E402


def main() -> int:
    with user_session() as db:
        row = db.query(UserMcpCredential).filter(UserMcpCredential.provider == 'tzzb').first()
    if row is None:
        print('NO_CREDENTIAL: 库里没有 tzzb 凭据')
        return 1
    print(
        f'credential: user_id={row.user_id} status={row.status} expires_at={row.expires_at} auth_type={row.auth_type}'
    )
    if row.status != 'active':
        print('CREDENTIAL_INACTIVE: 凭据非 active，探针终止')
        return 1

    user_id = row.user_id
    provider = TzzbProvider()
    route = resolve_connection_route('tzzb', credential_auth_type(user_id, 'tzzb'), None)
    # token 在 _post_factory 里只用于鉴权头；这里从凭据表走统一入口拿
    from app.services.mcp.credentials import DataScope, resolve_token

    token = resolve_token('tzzb', DataScope.USER_PRIVATE, user_id=user_id)
    route = resolve_connection_route('tzzb', credential_auth_type(user_id, 'tzzb'), token)
    transport = McpTransport(_post_factory(provider, token, route), provider)

    def call(tool: str, arguments: dict) -> str:
        print(f'\n===== {tool} args={json.dumps(arguments, ensure_ascii=False)} =====')
        try:
            text = transport.call_tool(tool, arguments, token=token)
        except Exception as e:  # noqa: BLE001 - 探针要看到一切异常原文
            print(f'CALL_FAILED: {type(e).__name__}: {e}')
            return ''
        print(text[:3000])
        if len(text) > 3000:
            print(f'...[截断，全长 {len(text)}]')
        return text

    raw_accounts = call('promptAccountSelection', {})
    # 尝试解析五组结构，供后续持仓调用映射参数
    selected: dict[str, str] = {}
    try:
        parsed = json.loads(raw_accounts)
        print('\n----- 解析出的账户分组 -----')
        content = parsed.get('content', parsed)
        print(json.dumps(content, ensure_ascii=False, indent=1)[:2000])
    except (ValueError, AttributeError):
        print('PARSE_FAILED: promptAccountSelection 返回不是 JSON')

    # 持仓工具：契约是 5 个账户参数全传（未用的传空串）
    for tool in ('queryStockPosition', 'queryPnlSummary'):
        args = {k: selected.get(k, '') for k in ('fundKey', 'rzrqFundKey', 'manualId', 'fundId', 'custId')}
        call(tool, args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
