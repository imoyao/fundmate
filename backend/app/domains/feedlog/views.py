# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/24
# File : views.py
"""FeedLog SSO 身份令牌端点（#1998 任务 B）。

端点契约：`GET|POST /api/feedlog-token/` → `{"data": {"token": "<JWT>"|null}, "message": "ok"}`。

三条设计决定（都不是随手写的，各有具体后果）：

1. **未登录返回 200 + `{"token": null}`，绝不返回 401。**
   401 在前端 `utils/http/index.ts` 的响应拦截器里会触发 `forceLogout()`——把
   「widget 顺手探测一下登录态」变成「用户被踢下线」。widget 的 `getToken()`
   契约本来就是「确认登出才返回 null，网络/异常必须 throw」（见
   `@feedlog/widget` 的 `WidgetAuth` 注释），所以「未登录」是**正常答案**，
   不是错误。该端点因此挂在 `core/auth.py` 的 `OPTIONAL_AUTH_PREFIXES`：
   匿名请求由中间件放行（不设 `g.current_user`），由本端点自己回 `null`。
   同理**未配置 `FEEDLOG_SSO_SECRET`** 也回 `null`——缺部署配置不该 500。

2. **GET 与 POST 同时注册。**
   卡面写的是 POST（动作语义），但全局鉴权中间件对 `viewer` 只读角色的**写方法**
   一律 403（D1 分权），而「读一个属于自己的身份令牌」没有任何写副作用——把它
   挡在 403 外面，只需再注册一个 GET，不必去改 D1 那条核心红线。widget 内部
   走 GET，还顺带避开前端 403 的全局 toast（「没有权限执行此操作」会在反馈
   面板里突然弹出来打断用户）。

3. **身份只认服务端会话。**
   claims（email / name / picture）全部取自 `g.current_user`——那是中间件用
   Supabase JWT 验签后解析出的服务端身份。浏览器只能证明「我带着合法会话」，
   不能自证「我是谁」；请求体里的任何身份字段一律不读。
"""

import os

from apiflask import APIBlueprint
from flask import g
from loguru import logger

from app.services.feedlog import sign_feedlog_token

feedlog_bp = APIBlueprint('feedlog', __name__, url_prefix='/api')

# SSO secret 只存服务端环境变量；未配置时本端点降级为「无身份」，不报错。
_SECRET_ENV = 'FEEDLOG_SSO_SECRET'


@feedlog_bp.route('/feedlog-token/', methods=['GET', 'POST'], strict_slashes=False)
def feedlog_token():
    """签发 FeedLog SSO 令牌（HS256，exp ≤ 24h）。

    已登录且配置了 secret → 返回 JWT；未登录 / 未配置 secret / 用户无邮箱 →
    返回 `{"token": null}`（widget 据此按游客模式运行）。
    """
    secret = (os.getenv(_SECRET_ENV) or '').strip()
    user = getattr(g, 'current_user', None)

    if user is None:
        # 未登录（中间件匿名放行）。这是正常答案，不是错误——见文件头第 1 条。
        return {'data': {'token': None}, 'message': 'ok'}

    if not secret:
        logger.info('FeedLog SSO secret 未配置（{}），本次令牌签发降级为无身份', _SECRET_ENV)
        return {'data': {'token': None}, 'message': 'ok'}

    email = (user.email or '').strip()
    if not email:
        # 用户没邮箱 → 无法作为 FeedLog 身份主键，诚实降级（不编造身份）
        logger.info('当前用户无邮箱，FeedLog 令牌签发降级为无身份（user_id={}）', user.id)
        return {'data': {'token': None}, 'message': 'ok'}

    token = sign_feedlog_token(
        email=email,
        secret=secret,
        name=user.nickname or user.username,
        picture=user.avatar,
    )
    # 只记身份与结果，不记令牌本身（令牌等价于凭证）
    logger.debug('已签发 FeedLog SSO 令牌（user_id={}, email={}）', user.id, email)
    return {'data': {'token': token}, 'message': 'ok'}
