# -*- coding: utf-8 -*-
"""数据同步流（#3304）：账户发现 → 工具调用 → 置信度校验 → 审计留痕。

解决的事实（全部 2026-11-28 真机采样）：tzzb 的 15 个工具都要求账户参数
（fundKey/rzrqFundKey/manualId/fundId/custId），**未用的类型必须传空串**（不是省略）；
账户键必须先调 ``promptAccountSelection``（required ``scope``）动态获取，
返回按 param 分组的五组列表。选错账户类型（证券同步选了基金账户）会让
上游返回与所选账户对不上的数据——静默落库 = 污染本地账本。

所以同步必须三段走，**不信任用户的单次选择**：

1. ``fetch_accounts``：拉账户清单，按五组归一化（每组附中文名与工具参数名）；
2. ``run_sync``：按工具契约装配参数（选中的传 id、未选的传空串）调上游，
   返回结构跑置信度判定——高置信正常放行，低置信**不落库**、把差异摘要
   交给前端让用户二次决定（仍要导入 / 换账户重试）；
3. 每次尝试写一行 :class:`~app.models.mcp_sync_audit.McpSyncAudit`
   （账户、置信度、强制标志），污染可溯源。

v1 边界（有意留空）：「导入」= 审计行记 ``imported`` + 快照留痕，
**不写 positions/transactions**——上游持仓直接造 Position 会破坏份额完整性
不变量（#3135 要求成对流水），真实写账本通道另开卡对账后再接。

置信度判定维度（首版）：结构形状（持仓列表 / 总资产字段）、空持仓、
字段完整性、与本地持仓的重合度（完全零重合 = 可疑信号）。
上游异常（``isError`` / 非 JSON）由传输层类型化抛出（``McpError`` 家族），
审计行记 ``confidence='error'`` 后原样上抛，不吞错。
"""

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.database import user_session
from app.models.mcp_sync_audit import PAYLOAD_MAX_CHARS, McpSyncAudit
from app.services.mcp.connection_check import _post_factory
from app.services.mcp.credentials import DataScope, resolve_token
from app.services.mcp.errors import McpBadResponse, McpError
from app.services.mcp.oauth_connection_routes import resolve_connection_route
from app.services.mcp.registry import get_provider
from app.services.mcp.transport import McpTransport
from app.services.mcp.user_credentials import credential_auth_type

#: 账户发现工具（真机 schema：required=['scope']；scope=all 返回全部账户）
ACCOUNT_TOOL = 'promptAccountSelection'

#: 账户分组 → (中文名, 工具参数名)。顺序即前端展示顺序；组键是上游原文，
#: **不要**改成本地概念（前端直接展示这里的 label）。
ACCOUNT_GROUPS: Dict[str, Tuple[str, str]] = {
    'fund_key': ('证券账户', 'fundKey'),
    'rzrq_fund_key': ('融资融券', 'rzrqFundKey'),
    'manual_id': ('手工券商', 'manualId'),
    'fund_id': ('手工基金', 'fundId'),
    'cust_id': ('爱基金客户号', 'custId'),
}

#: 可同步工具 → (工具族, 允许的账户分组)。参数集由组参数名推导：
#: 证券工具的 schema 就是 fundKey/rzrqFundKey/manualId，基金工具是 fundId/custId
#: ——按组推导参数恰好与 schema 对齐，不用再维护一份参数清单。
SYNC_TOOLS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    'queryStockPosition': ('stock', ('fund_key', 'rzrq_fund_key', 'manual_id')),
    'queryFundAccount': ('fund', ('fund_id', 'cust_id')),
}

#: 账户分组 → 同步工具（从 SYNC_TOOLS 反推，唯一真相）。交互层只让用户选
#: 「账户类型（组）→ 账户」，用哪个工具是本模块的实现细节，前端不传工具名。
GROUP_TOOL: Dict[str, str] = {group: tool for tool, (_, allowed) in SYNC_TOOLS.items() for group in allowed}


class SyncSelectionError(ValueError):
    """账户选择不合法（未选账户 / 类型与工具错位）。视图层转 422。"""


# ── 传输 ──
def _transport_for(provider: str, user_id: int) -> Tuple[McpTransport, str]:
    """构造打用户凭据的传输层（与连接校验同构；route 按认证方式选路）。"""
    provider_obj = get_provider(provider)
    token = resolve_token(provider, DataScope.USER_PRIVATE, user_id=user_id)
    route = resolve_connection_route(provider, credential_auth_type(user_id, provider), token)
    transport = provider_obj.build_transport(_post_factory(provider_obj, token, route))
    return transport, token


def _parse_json_result(text: str, provider: str, what: str) -> Dict[str, Any]:
    """工具返回的文本片段 → dict；不是 JSON / 不是对象都按坏响应类型化上抛。"""
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise McpBadResponse(f'{what}返回不是 JSON', provider=provider) from exc
    if not isinstance(payload, dict):
        raise McpBadResponse(f'{what}返回不是对象', provider=provider)
    return payload


# ── 第一步：账户发现 ──
def fetch_accounts(provider: str, user_id: int) -> Dict[str, Any]:
    """拉上游账户清单并按五组归一化；组缺失按空组处理（上游只回非空组）。

    Raises:
        SyncSelectionError: provider 没有账户发现工具（不支持同步）。
        McpError: 凭据缺失 / 上游失败 / 返回结构异常（均已脱敏）。
    """
    capabilities = getattr(get_provider(provider), 'tool_capabilities', None) or {}
    if ACCOUNT_TOOL not in capabilities:
        raise SyncSelectionError('该服务暂不支持账户选择，无法发起同步')
    transport, token = _transport_for(provider, user_id)
    text = transport.call_tool(
        ACCOUNT_TOOL,
        {'scope': 'all'},
        token=token,
        capability='sync_account_selection',
        scope=str(user_id),
    )
    raw = _parse_json_result(text, provider, '账户清单')
    groups = []
    for group, (label, param) in ACCOUNT_GROUPS.items():
        entries = raw.get(group)
        accounts = []
        for item in entries if isinstance(entries, list) else []:
            if not isinstance(item, dict) or not item.get('id'):
                continue  # 畸形条目丢弃，不让一条脏数据炸掉整页账户
            accounts.append(
                {
                    'id': str(item['id']),
                    'name': str(item.get('name') or ''),
                    'lastSyncTime': item.get('lastSyncTime') or None,
                }
            )
        groups.append({'group': group, 'label': label, 'param': param, 'accounts': accounts})
    return {'provider': provider, 'groups': groups}


# ── 参数装配 ──
def tool_for_accounts(accounts: List[Dict[str, Any]]) -> str:
    """所选账户 → 同步工具：组的工具归属必须一致（混族 = 前端漏拦，这里兜底）。

    组键未知同样拒绝——组清单是账户发现下发的，前端不存映射，出现未知组
    说明请求被伪造或版本错位。
    """
    tools = set()
    for acc in accounts:
        group = str(acc.get('group') or '')
        tool = GROUP_TOOL.get(group)
        if tool is None:
            label = ACCOUNT_GROUPS.get(group, (group, ''))[0]
            raise SyncSelectionError(f'未知的账户类型（{label}），请重新拉取账户清单')
        tools.add(tool)
    if len(tools) > 1:
        raise SyncSelectionError('所选账户类型不属于同一类数据，请分开同步')
    return tools.pop()


def build_tool_args(tool: str, accounts: List[Dict[str, Any]]) -> Dict[str, str]:
    """所选账户 → 工具参数：同组多个 id 逗号拼接，未选组传**空串**（上游契约）。

    组不在工具允许范围内 = 用户选错了账户类型（证券同步选了基金账户），
    在这里响亮拒绝——这是 API 层的双层校验（UI 层由选择器按工具过滤）。
    """
    _, allowed = SYNC_TOOLS[tool]
    by_group: Dict[str, List[str]] = {}
    for acc in accounts:
        group = str(acc.get('group') or '')
        if group not in allowed:
            label = ACCOUNT_GROUPS.get(group, (group, ''))[0]
            raise SyncSelectionError(f'所选账户类型（{label}）与该同步工具不匹配')
        acc_id = str(acc.get('id') or '')
        if acc_id:
            by_group.setdefault(group, []).append(acc_id)
    args: Dict[str, str] = {}
    for group in allowed:
        ids = dict.fromkeys(by_group.get(group, []))  # 去重保序
        args[ACCOUNT_GROUPS[group][1]] = ','.join(ids)
    return args


# ── 置信度判定 ──
def _to_float(value: Any) -> Optional[float]:
    """上游数值字段全是字符串（"369847.963000000"），解析失败返回 None。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _digits(code: Any) -> str:
    """代码归一：只留数字（本地持仓 symbol 是带市场前缀的展示形态）。"""
    return ''.join(ch for ch in str(code or '') if ch.isdigit())


def _local_position_codes(user_id: int) -> Set[str]:
    """用户家庭的本地持仓代码集（数字形态），用于重合度判定。"""
    from app.domains.positions.models import Position
    from app.domains.users.models import User

    with user_session() as db:
        user = db.get(User, user_id)
        if user is None or not user.family_id:
            return set()
        rows = db.query(Position.symbol).filter(Position.family_id == user.family_id).all()
    return {code for code in (_digits(r[0]) for r in rows) if code}


def _item_field(item: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        if item.get(key):
            return str(item[key])
    return None


def _assess_holdings(
    payload: Dict[str, Any],
    *,
    list_key: str,
    code_key: str,
    name_key: str,
    summary_keys: Tuple[str, ...],
    what: str,
    local_codes: Set[str],
) -> Tuple[List[str], Dict[str, Any], List[Dict[str, Any]]]:
    """持仓类返回的通用判定：结构 / 空仓 / 字段完整性 / 本地重合度。"""
    reasons: List[str] = []
    entries = payload.get(list_key)
    if not isinstance(entries, list):
        reasons.append(f'返回结构里没有{what}列表（{list_key}），不像一次成功的{what}查询')
        entries = []
    summary: Dict[str, Any] = {'count': len(entries)}
    for key in summary_keys:
        value = _to_float(payload.get(key))
        summary[key] = value
        if value is None:
            reasons.append(f'缺少汇总字段（{key}）')
    items: List[Dict[str, Any]] = []
    bad_entries = 0
    for entry in entries[:50]:
        if not isinstance(entry, dict):
            bad_entries += 1
            continue
        items.append(
            {
                'code': _item_field(entry, code_key),
                'name': _item_field(entry, name_key),
                'marketValue': _item_field(entry, 'marketValue'),
                'quantity': _item_field(entry, 'holdQuantity', 'holdAmount'),
            }
        )
    if bad_entries:
        reasons.append(f'{what}里有 {bad_entries} 条无法解析的条目')
    if not items:
        reasons.append(f'{what}为空（该账户可能没有{what}，或账户类型选错了）')
    codes = {_digits(i['code']) for i in items if i['code']}
    summary['overlap'] = len(codes & local_codes) if codes else 0
    if codes and summary['overlap'] == 0:
        reasons.append('返回的代码与本地持仓完全无重合（全是全新代码，可疑信号）')
    return reasons, summary, items


def assess_confidence(
    tool: str, payload: Dict[str, Any], local_codes: Set[str]
) -> Tuple[str, List[str], Dict[str, Any], List[Dict[str, Any]]]:
    """返回 (置信度, 理由, 汇总, 预览条目)；理由非空即低置信。"""
    family = SYNC_TOOLS[tool][0]
    if family == 'stock':
        reasons, summary, items = _assess_holdings(
            payload,
            list_key='holdings',
            code_key='stockCode',
            name_key='stockName',
            summary_keys=('totalAsset', 'totalMarketValue'),
            what='持仓',
            local_codes=local_codes,
        )
    else:
        reasons, summary, items = _assess_holdings(
            payload,
            list_key='funds',
            code_key='fundCode',
            name_key='fundName',
            summary_keys=('totalAsset',),
            what='基金持仓',
            local_codes=local_codes,
        )
    return ('high' if not reasons else 'low'), reasons, summary, items


# ── 审计 ──
def _write_audit(
    user_id: int,
    provider: str,
    tool: str,
    accounts: List[Dict[str, Any]],
    confidence: str,
    reasons: List[str],
    forced: bool,
    imported: bool,
    payload: Optional[Dict[str, Any]],
) -> None:
    """审计行**永不抛**：留痕失败不能让同步流程白跑（同 call_log.persist 纪律）。

    提交语义照 ``user_credentials._session_for_write``：请求上下文里由 teardown
    统一提交；job / CLI / 探针（非请求上下文）里 ``user_session()`` 只关闭不提交，
    **必须在这里补 commit**，否则留痕随连接关闭静默丢失（实测转红的坑）。
    """
    try:
        snapshot = json.dumps(payload, ensure_ascii=False)[:PAYLOAD_MAX_CHARS] if payload else None
        with user_session() as db:
            try:
                db.add(
                    McpSyncAudit(
                        user_id=user_id,
                        provider=provider,
                        tool=tool,
                        accounts_json=json.dumps(accounts, ensure_ascii=False),
                        confidence=confidence,
                        reasons_json=json.dumps(reasons, ensure_ascii=False),
                        forced=forced,
                        imported=imported,
                        payload=snapshot,
                    )
                )
                from flask import has_request_context

                if not has_request_context():
                    db.commit()
            except Exception:  # noqa: BLE001 - 写失败回滚后仍不打断业务流
                db.rollback()
                raise
    except Exception:  # noqa: BLE001 - 审计失败不允许打断业务流
        from loguru import logger

        logger.exception(f'同步审计落库失败 provider={provider} tool={tool}')


# ── 主流程 ──
def run_sync(
    provider: str,
    user_id: int,
    accounts: List[Dict[str, Any]],
    force: bool = False,
) -> Dict[str, Any]:
    """执行一次同步：推导工具 → 装配参数 → 调上游 → 置信度判定 → 审计 → 返回。

    工具由所选账户的组推导（:func:`tool_for_accounts`）——交互层只暴露
    「账户类型 → 账户名称」两级选择，工具名不进请求体。
    高置信自动导入；低置信默认不导入（``imported=False``），前端展示差异摘要后
    由用户决定「仍要导入」（``force=True`` 重发，审计记强制标志）或换账户重试。
    上游异常（McpError 家族）：审计记 ``error`` 后原样上抛，视图层透出上游文案。

    Raises:
        SyncSelectionError: 未选账户 / 组未知 / 混族选择。
        McpError: 凭据缺失 / 上游失败（``isError``、非 JSON 等）。
    """
    if not accounts:
        raise SyncSelectionError('请先选择要同步的账户')
    tool = tool_for_accounts(accounts)
    capabilities = getattr(get_provider(provider), 'tool_capabilities', None) or {}
    if tool not in capabilities:
        raise SyncSelectionError('该服务没有这个同步工具')
    args = build_tool_args(tool, accounts)
    transport, token = _transport_for(provider, user_id)
    try:
        text = transport.call_tool(tool, args, token=token, capability=f'sync_{tool}', scope=str(user_id))
        payload = _parse_json_result(text, provider, '同步结果')
    except McpError as exc:
        _write_audit(user_id, provider, tool, accounts, 'error', [exc.user_message], False, False, None)
        raise
    local_codes = _local_position_codes(user_id)
    confidence, reasons, summary, items = assess_confidence(tool, payload, local_codes)
    imported = confidence == 'high' or bool(force)
    forced = confidence == 'low' and bool(force)
    _write_audit(user_id, provider, tool, accounts, confidence, reasons, forced, imported, payload)
    return {
        'tool': tool,
        'confidence': confidence,
        'reasons': reasons,
        'summary': summary,
        'items': items,
        'imported': imported,
        'forced': forced,
    }
