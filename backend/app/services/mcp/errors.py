# -*- coding: utf-8 -*-
"""MCP 错误模型（S2）：把「失败了」变成「哪一类失败、能不能重试、用户该做什么」。

设计文档 ``docs/dev/mcp-integration.md`` §5.2 的落地。存在的理由只有一个：
**失败必须可分类**。在 S1 之前，传输层的失败统一是 ``RuntimeError``，到了 fetcher 被
``except Exception → return []`` 吞掉，上层读成「这只组合没有持仓」——故障与「真的没有数据」
在类型上不可区分（#1179 / #171 同族形态）。

三条约定：

1. ``McpError`` 继承 ``RuntimeError``：既有调用点与测试里 ``pytest.raises(RuntimeError)``
   仍然成立，S2 不靠改测试来"通过"；
2. ``user_message`` 是**已脱敏的中文人话**，直接可以进 ``sync_logs`` / 前端提示；
   ``str(exc)`` 带上 kind 与截断后的上游细节，供排查；
3. 分类**只按已实测的事实**：且慢只有 401/403/429/5xx 的形态；Wind 的「额度用尽 / 欠费」
   真实报文尚未采样（探测阶段未触发限额），故 429 默认按 **频控**（可重试）处理，
   仅当报文里出现额度/欠费关键词时才升级为不可重试 —— 不凭猜写死分类。
"""

import re
from enum import StrEnum
from typing import Optional

#: provider → 中文显示名（只用于人话文案与审计，不参与任何逻辑分支）
_PROVIDER_DISPLAY = {
    'qieman': '且慢',
    'wind': 'Wind',
    'wind_stock': 'Wind（股票域）',
    'wind_fund': 'Wind（基金域）',
    'wind_index': 'Wind（指数域）',
}

#: 报文里出现这些词 ⇒ 额度用尽（不可重试，等额度恢复）
_QUOTA_WORDS = ('额度', '配额', 'quota', 'exceed', 'limit reached', '超出限制')
#: 报文里出现这些词 ⇒ 欠费 / 未订阅 / 到期（不可重试，需联系服务商）
_BILLING_WORDS = ('欠费', '未订阅', '已到期', '余额不足', 'arrear', 'subscription', 'insufficient balance')

#: 脱敏：上游报文里可能夹带凭据（header 回显 / 调试信息 / dict repr），进日志前先抹掉。
#: 允许键名两侧带引号、值带引号（``{'x-api-key': 'sk-…'}`` / ``{"Authorization": "Bearer …"}``）——
#: 这两种是最常见的回显形态，早期只匹配 ``key: value`` 的写法会把它们整条漏掉。
_SECRET_RE = re.compile(
    r'(?i)\b(api[_-]?key|token|authorization|x-api-key|secret)\b\s*["\']?\s*[:=]\s*["\']?([^\r\n"\',}]+)'
)


class McpErrorKind(StrEnum):
    """错误种类（落 ``mcp_call_logs.error_kind``，也是 health 段判断依据）。"""

    TOKEN_MISSING = 'token_missing'  # 本地没配 Token（可选组件，不算故障）
    USER_TOKEN_MISSING = 'user_token_missing'  # 用户私有能力但用户没配 Token（S5）
    AUTH = 'auth'  # Token 无效 / 无权限
    QUOTA = 'quota'  # 额度用尽
    BILLING = 'billing'  # 欠费 / 未订阅 / 到期
    RATE_LIMIT = 'rate_limit'  # 频控（退避后可重试）
    UNAVAILABLE = 'unavailable'  # 5xx / 超时 / 网络
    BAD_RESPONSE = 'bad_response'  # 结构不符 / 空结果 / 协议错


def display_name(provider: str) -> str:
    """provider 的中文名（未知 provider 原样返回，不猜）。"""
    return _PROVIDER_DISPLAY.get(provider or '', provider or 'MCP')


def sanitize(text: object, limit: int = 200) -> str:
    """把任意上游文本压成一行、抹掉凭据痕迹、截断到 ``limit``。

    为什么必须做：``McpError`` 的细节会进 ``sync_logs.error_detail`` 与日志，
    而上游报文不可控 —— 既可能夹带 header 回显（凭据红线），也可能是几百 KB 的 HTML。
    """
    if text is None:
        return ''
    flat = re.sub(r'\s+', ' ', str(text)).strip()
    flat = _SECRET_RE.sub(lambda m: f'{m.group(1)}=***', flat)
    return flat if len(flat) <= limit else flat[: limit - 1] + '…'


class McpError(RuntimeError):
    """MCP 调用失败的基类（字段与语义见设计文档 §5.2）。

    Attributes:
        kind: 错误种类，落库与 health 判断都读它。
        provider: 服务标识（``qieman`` / ``wind``）。
        retryable: 是否值得重试（退避 / 下一轮）。
        action: 人该做什么 —— ``configure_token`` / ``wait`` / ``contact`` / ``report``。
        user_message: 已脱敏的中文人话。
        http_status: 有 HTTP 语义时记录，供 ``mcp_call_logs`` 采样（S3 的报文映射依据）。
    """

    kind: McpErrorKind = McpErrorKind.BAD_RESPONSE
    retryable: bool = False
    action: str = 'report'
    _TEMPLATE: str = '{who} 调用返回异常'

    def __init__(self, detail: object = '', *, provider: str = '', http_status: Optional[int] = None) -> None:
        self.provider = provider or ''
        self.http_status = http_status
        who = display_name(self.provider)
        self.user_message = self._TEMPLATE.format(who=who)
        self.detail = sanitize(detail)
        text = f'{who} MCP[{self.kind}] {self.user_message}'
        if self.detail:
            text = f'{text}：{self.detail}'
        super().__init__(text)


class McpTokenMissing(McpError):
    """本地（env）没有配置 Token —— **可选组件不可用**，不是服务故障。

    health 段据此报 ``disabled``（与 ``SCHEDULER_ENABLED`` 关闭时的口径一致，#1720：
    关闭态必须可见，但不能报成 unhealthy，否则真故障会被淹没）。
    """

    kind = McpErrorKind.TOKEN_MISSING
    retryable = False
    action = 'configure_token'
    _TEMPLATE = '{who} 未配置 Token，相关数据不更新（可选组件，不影响主流程）'


class McpUserTokenMissing(McpError):
    """用户私有能力但该用户没配 Token —— **绝不回退系统 Token**。

    这是设计文档 §5.1 的「类型级保证」：回退会让系统额度被用户私有请求消耗，
    且数据归属错乱（把别人的账户数据算到系统头上）。
    """

    kind = McpErrorKind.USER_TOKEN_MISSING
    retryable = False
    action = 'configure_token'
    _TEMPLATE = '{who} 需要你本人配置 Token 后才能使用（不使用系统凭据代取）'


class McpAuthError(McpError):
    """Token 无效 / 过期 / 无权限（401、403）。"""

    kind = McpErrorKind.AUTH
    retryable = False
    action = 'configure_token'
    _TEMPLATE = '{who} 授权已失效，请更新 Token'


class McpQuotaExceeded(McpError):
    """额度用尽（不可重试：重试只会继续消耗/继续失败）。"""

    kind = McpErrorKind.QUOTA
    retryable = False
    action = 'wait'
    _TEMPLATE = '{who} 今日调用额度已用尽，数据暂停更新'


class McpBillingError(McpError):
    """欠费 / 未订阅 / 服务到期。"""

    kind = McpErrorKind.BILLING
    retryable = False
    action = 'contact'
    _TEMPLATE = '{who} 账户欠费或服务已到期，数据暂停更新'


class McpRateLimited(McpError):
    """频控（429），退避后可重试。"""

    kind = McpErrorKind.RATE_LIMIT
    retryable = True
    action = 'wait'
    _TEMPLATE = '{who} 调用过于频繁，稍后自动重试'


class McpUnavailable(McpError):
    """服务端 5xx / 超时 / 网络不可达（可重试）。"""

    kind = McpErrorKind.UNAVAILABLE
    retryable = True
    action = 'wait'
    _TEMPLATE = '{who} 服务暂时不可用，稍后自动重试'


class McpBadResponse(McpError):
    """协议 / 结构不符 / 空结果（重试无意义，需要人看）。"""

    kind = McpErrorKind.BAD_RESPONSE
    retryable = False
    action = 'report'
    _TEMPLATE = '{who} 返回结构异常，已记录'


def _body_kind(body: str) -> McpErrorKind:
    """按报文关键词细分 429 / 4xx 的语义（无命中返回 ``None``-like 由调用方兜底）。"""
    low = (body or '').lower()
    if any(w in low for w in _BILLING_WORDS):
        return McpErrorKind.BILLING
    if any(w in low for w in _QUOTA_WORDS):
        return McpErrorKind.QUOTA
    return McpErrorKind.BAD_RESPONSE


def classify_http(status: int, body: object = '', *, provider: str = '') -> McpError:
    """HTTP 状态码 + 报文 → 具体的 ``McpError`` 实例。

    判据（与设计文档 §5.2 一一对应）：

    ==========  ==========================  ==============================
    状态        形态                        归类
    ==========  ==========================  ==============================
    401 / 403   Token 无效 / 无权限          ``McpAuthError``
    402         需要付费                     ``McpBillingError``
    429         默认频控；报文含额度/欠费词   ``McpRateLimited`` / ``McpQuotaExceeded`` / ``McpBillingError``
    5xx         服务端故障                   ``McpUnavailable``
    其余 4xx    协议 / 参数错                ``McpBadResponse``
    ==========  ==========================  ==============================

    ⚠️ 429 默认按**频控**（可重试）：且慢与 Wind 的真实「额度用尽」报文尚未采样，
    只有报文里明确出现额度 / 欠费词时才升级为不可重试。采样结果回填到 S3。
    """
    text = sanitize(body)
    if status in (401, 403):
        return McpAuthError(text, provider=provider, http_status=status)
    if status == 402:
        return McpBillingError(text, provider=provider, http_status=status)
    if status == 429:
        kind = _body_kind(text)
        cls = {
            McpErrorKind.QUOTA: McpQuotaExceeded,
            McpErrorKind.BILLING: McpBillingError,
            McpErrorKind.RATE_LIMIT: McpRateLimited,
        }.get(kind, McpRateLimited)
        return cls(text, provider=provider, http_status=status)
    if status >= 500:
        return McpUnavailable(text, provider=provider, http_status=status)
    return McpBadResponse(text, provider=provider, http_status=status)


def classify_payload(body: object, *, provider: str = '') -> McpError:
    """JSON-RPC / 业务报文里的 ``error`` 字段 → ``McpError``。

    没有 HTTP 状态可依赖时（上游 200 但 body 里带 error），只能按关键词判；
    无命中一律 ``McpBadResponse``（重试无意义，需要人看报文）。
    """
    text = sanitize(body)
    kind = _body_kind(text)
    cls = {
        McpErrorKind.QUOTA: McpQuotaExceeded,
        McpErrorKind.BILLING: McpBillingError,
    }.get(kind, McpBadResponse)
    return cls(text, provider=provider)


def classify_exception(exc: BaseException, *, provider: str = '') -> McpError:
    """任意异常 → ``McpError``（已是本家族的**原样返回**，不包一层）。

    网络类异常归 ``McpUnavailable``（可重试）；其它未知异常归 ``McpBadResponse``
    （重试无意义，要人看）。``requests`` 的判断用异常类名做，避免为了检类型
    把 ``requests`` 变成 mcp 层的硬依赖。
    """
    if isinstance(exc, McpError):
        return exc
    name = type(exc).__name__
    if name in ('Timeout', 'ConnectTimeout', 'ReadTimeout', 'ConnectionError', 'ChunkedEncodingError'):
        return McpUnavailable(str(exc), provider=provider)
    if isinstance(exc, OSError):
        return McpUnavailable(f'{name}: {exc}', provider=provider)
    return McpBadResponse(f'{name}: {exc}', provider=provider)
