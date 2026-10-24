# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/24
# File : feedlog.py
"""FeedLog SSO 身份令牌签发（#1998 任务 B）。

FeedLog 侧是 **SSO 消费端**：`/api/sso/jwt` 用 HS256 验签，密钥是 workspace 的
`FEEDLOG_SSO_SECRET`（见 `docs/spec/site-architecture-and-traffic-routing.md` §4.2）。
本模块是**签发方**：把本仓已登录用户的身份，用同一把密钥签成 JWT 交给前端 widget，
让反馈帖带上真实身份而不再匿名。

三条纪律（#1998 卡面硬性约束，逐条对应实现）：
1. **claims 一律从服务端会话推导**——前端只能证明「我带着合法会话」（中间件验签后
   注入 `g.current_user`），不能自证「我是谁」。本模块只接受调用方传入的、已由
   服务端解析出的身份字段，不读任何请求参数；
2. **`exp` 不得超过 24 小时**——FeedLog 消费端拒收更长的令牌；
3. **secret 只存服务端**（环境变量），绝不随响应回传前端。

本模块是**纯函数**（不碰 db / flask / request），便于单测直接验签与边界断言。
"""

import time
from typing import Optional

import jwt

# 令牌有效期上限：卡面规定 exp 不得超过 24 小时（FeedLog 消费端拒收更长的令牌）。
DEFAULT_TTL_SECONDS = 24 * 3600

# 签名算法：FeedLog 消费端固定 HS256（对称密钥）。
ALGORITHM = 'HS256'


def sign_feedlog_token(
    *,
    email: str,
    secret: str,
    name: Optional[str] = None,
    picture: Optional[str] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: Optional[int] = None,
) -> str:
    """签一个 FeedLog SSO JWT（HS256）。

    Args:
        email: 用户邮箱，**必填**——FeedLog 以它作为身份主键。
        secret: workspace 的 SSO secret（服务端环境变量，不外泄）。
        name: 显示名，可选；为空则不写进 claims（而非写 null）。
        picture: 头像 URL，可选；为空则不写进 claims。
        ttl_seconds: 有效期秒数，上限 24 小时。
        now: 当前 Unix 秒（可注入，便于测试断言 exp）。

    Returns:
        编码后的 JWT 字符串。

    Raises:
        ValueError: email / secret 为空，或 ttl_seconds 超过 24 小时上限。
    """
    email = (email or '').strip()
    if not email:
        raise ValueError('email 不能为空：FeedLog 以邮箱作为身份主键')
    if not (secret or '').strip():
        raise ValueError('secret 不能为空：SSO secret 只存服务端，未配置时不得签发令牌')
    if ttl_seconds <= 0 or ttl_seconds > DEFAULT_TTL_SECONDS:
        raise ValueError(f'ttl_seconds 必须在 (0, {DEFAULT_TTL_SECONDS}] 区间内')

    issued_at = int(time.time()) if now is None else int(now)
    payload = {
        'email': email,
        'iat': issued_at,
        'exp': issued_at + int(ttl_seconds),
    }
    # 可选字段：**缺省就不出现**（写 null 会让消费端拿到一个"存在但为空"的字段）
    if name and name.strip():
        payload['name'] = name.strip()
    if picture and picture.strip():
        payload['picture'] = picture.strip()

    return jwt.encode(payload, secret, algorithm=ALGORITHM)
