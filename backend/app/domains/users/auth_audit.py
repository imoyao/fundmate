# -*- coding: utf-8 -*-
"""认证端点的请求流水（D76 / #2780，`auth_audit.source='backend'`）。

## 为什么不写在视图里

`domains/auth/views.py` 的行数已顶满视图厚度基线（`scripts/check_view_thickness.py`
对存量文件只减不增），在 `resolve` / `logout` 里加一行记账就会判红。但更根本的理由
是职责：审计是**观察者**，不是业务步骤——业务编排不该为了「让台账好看」而多一条分支。

## 两阶段（顺序不能反）

1. :func:`capture`，挂 `after_request`：只判断「这个请求值不值得记」并采集字段，
   暂存到 ``flask.g``，**全程不碰数据库**；
2. :func:`flush`，挂 `teardown_request`：请求级会话被 `teardown_request_session`
   提交 / 关闭**之后**，用独立会话、独立事务落库。

为什么不能在第 1 步直接写：`PATCH /api/users/me/` 这类写请求此刻还持有未提交事务，
另一条连接去写同一个 SQLite 文件就是撞写锁——等满 5s timeout 后 OperationalError，
台账变成随机丢行。两阶段还有个附带好处：审计失败只丢一行台账，既不会连带回滚已提交的
业务写入，也不会把 Session 打成 invalid 状态反过来毒化业务事务（#1632 请求级单会话）。

**注册顺序是硬约束**：Flask 的 teardown 钩子按「后注册先执行」运行，所以 `flush`
必须注册在 `teardown_request_session` 之前，才能排在它之后执行（见 `app/main.py`）。

## 失败语义（D76 裁决二）

**记账失败绝不阻断请求**：采集与落库各自 try/except，失败只记 WARNING。
代价要说清楚——**台账缺行 ≠ 没发生**。排查「发起过但没落库」时以 Supabase 侧
`auth.users` 触发器（`source='supabase'`）为准；两处都没有记录，才是真的没有证据。

## 不写什么

密码、refresh token、邮箱 / 用户名明文一律不写。`identifier` 存打码串（人眼可辨域名），
`detail.identifier_sha256` 存归一化后的哈希前缀（机器可精确检索同一个标识）。
"""

import hashlib
import ipaddress
import json

from flask import g, has_request_context, request
from loguru import logger

from app.core.request_context import client_ip
from app.domains.users.models import AuthAuditLog

#: `g` 上的暂存槽位。用字符串常量而非属性名硬编码，便于测试清理。
_PENDING_KEY = '_auth_audit_pending'

#: UA 入库截断长度（模型列为 String(200)，留余量给将来的格式化）。
_UA_MAX_LEN = 120

#: `resolve` 的状态码 → 事件名。**只映射有审计意义的状态**：
#: 400（body 不合法）不记——它通常连 identifier 都没有，只会给台账灌噪声；
#: 5xx 也不记，那属于「服务自己坏了」，去看应用日志比看台账快。
_RESOLVE_EVENTS = {
    200: 'auth.resolve.hit',
    404: 'auth.resolve.miss',
    409: 'auth.resolve.ambiguous',
    429: 'auth.resolve.ratelimited',
}


def mask_identifier(raw: str | None) -> tuple[str | None, str | None]:
    """把登录标识转成「打码串 + 可检索哈希前缀」。

    返回 ``(masked, sha256_prefix)``。两者都给是有意的分工：

    - 打码串（`al***@example.com`）给人看，能一眼认出是哪个邮箱域；
    - 哈希前缀给机器用，`WHERE detail LIKE '%<hash>%'` 就能把同一个标识的
      所有尝试串起来——**打码会碰撞**（`al***@a.com` 与 `al***@b.com` 不同域，
      但 `ab***@x.com` 与 `ac***@x.com` 打码后都可能是 `a***@x.com`），只靠打码
      查不准，而这正是「同一个人被反复枚举」要回答的问题。

    哈希前先 ``casefold()``：`resolve` 的匹配本身大小写不敏感，若按原样哈希，
    `Alice@x.com` 与 `alice@x.com` 会落成两个指纹，检索时得逐个试。
    """
    text = (raw or '').strip()
    if not text:
        return None, None
    digest = hashlib.sha256(text.casefold().encode('utf-8')).hexdigest()[:16]
    if '@' in text:
        local, _, domain = text.partition('@')
        head = local[:2] if len(local) > 2 else ''
        return f'{head}***@{domain}', digest
    if len(text) <= 3:
        return '***', digest
    return f'{text[0]}***{text[-1]}', digest


def mask_ip(raw: str | None) -> str | None:
    """截断来源 IP，保留可判「是否同一网段」的粒度。

    IPv4 抹掉主机位（`1.2.3.0/24`），IPv6 抹掉接口标识（`/64`）。
    为什么不存原值：台账的价值是「归因到某个来源」，不是「精确到某台机器」；
    而这张表在 Supabase `public` schema 里，一旦权限配错，原值 IP 是可被用来
    做地理位置画像的 PII。截断不影响「是不是同一个攻击源」的判断——同一攻击者
    在同一个 /24 内的概率远大于跳网段。

    解析不了的（`'unknown'`、被伪造的垃圾头）一律返回 `None`，不把垃圾落库。
    """
    text = (raw or '').strip()
    if not text or text == 'unknown':
        return None
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        return None
    if addr.version == 4:
        return f'{str(addr).rsplit(".", 1)[0]}.0/24'
    return str(ipaddress.ip_network(f'{addr}/64', strict=False))


def _request_json() -> dict:
    """尽力取 JSON body；取不到就返回空 dict（审计绝不能因为 body 畸形而失败）。"""
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _identity():
    """当前请求已解析出的本地用户（可能不存在：`resolve` / `logout` 都免登录）。"""
    user = getattr(g, 'current_user', None)
    if user is None:
        return None, None
    return getattr(user, 'id', None), getattr(user, 'supabase_id', None)


def _build_row(response) -> dict | None:
    """判定当前请求是否入账；入账则返回一行待写数据。

    用 ``request.endpoint`` 而不是 URL 做键：`resolve` 是 `strict_slashes=False`，
    路径有 `/api/auth/resolve` 与 `/api/auth/resolve/` 两种合法写法，按路径匹配
    会漏掉一半；endpoint 也不受 `url_prefix` 调整影响。
    """
    endpoint = request.endpoint or ''
    status = response.status_code
    detail: dict = {}
    identifier = None

    if endpoint == 'auth.resolve_identifier':
        event = _RESOLVE_EVENTS.get(status)
        if event is None:
            return None
        identifier = _request_json().get('identifier')
        # 只记状态码不记阈值：阈值会随调参变化，写死的数字迟早与代码不符；
        # 「哪一秒被限过」才是台账要回答的问题（要查当时的阈值，看对应版本的代码）。
        detail['status'] = status
    elif endpoint == 'auth.logout':
        if status >= 400:
            return None
        event = 'auth.logout'
    elif endpoint == 'users.update_me':
        if status >= 400:
            return None
        event = 'auth.profile.updated'
        # **只记字段名，不记值**：昵称与用户名是用户内容，头像 URL 里可能带签名参数。
        # 「改了哪些字段」已足够还原行为；想看得更细，去业务表比对（那里本来就有值）。
        detail['fields'] = sorted(_request_json().keys())
    else:
        return None

    masked, digest = mask_identifier(identifier if isinstance(identifier, str) else None)
    if digest:
        detail['identifier_sha256'] = digest

    user_id, supabase_id = _identity()
    return {
        'user_id': user_id,
        'supabase_id': supabase_id,
        'event': event,
        'source': 'backend',
        'identifier': masked,
        'ip': mask_ip(client_ip()),
        'user_agent': (request.user_agent.string or '')[:_UA_MAX_LEN] or None,
        'detail': json.dumps(detail, ensure_ascii=False, sort_keys=True),
    }


def capture(response):
    """`after_request` 钩子：采集，不落库（见模块 docstring「两阶段」）。"""
    try:
        row = _build_row(response)
    except Exception as exc:  # 采集失败同样不阻断请求
        logger.warning('[auth_audit] 采集失败（已忽略）：{}', exc)
        return response
    if row is None:
        return response
    pending = getattr(g, _PENDING_KEY, None)
    if pending is None:
        pending = []
        setattr(g, _PENDING_KEY, pending)
    pending.append(row)
    return response


def _write(rows: list[dict]) -> None:
    """独立会话 + 独立事务落库（**不复用请求级会话**，理由见模块 docstring）。"""
    from app.core.database import get_user_sessionmaker

    session = get_user_sessionmaker()()
    try:
        session.add_all([AuthAuditLog(**row) for row in rows])
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def flush(exc=None) -> None:
    """`teardown_request` 钩子：把暂存的行写进台账。

    必须注册在 `teardown_request_session` **之前**（Flask 后注册先执行），
    否则会在请求级会话仍持有写事务时抢写同一文件。
    """
    if not has_request_context():
        return
    pending = getattr(g, _PENDING_KEY, None)
    if not pending:
        return
    try:
        _write(pending)
    except Exception as err:  # D76 裁决二：记账失败绝不阻断请求
        logger.warning('[auth_audit] 落库失败（已忽略，台账缺 {} 行）：{}', len(pending), err)
    finally:
        # 无论成败都清空，避免 teardown 重入（异常路径下 Flask 可能再触发一次）时重复写
        setattr(g, _PENDING_KEY, [])
