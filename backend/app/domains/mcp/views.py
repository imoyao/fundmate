# -*- coding: utf-8 -*-
"""MCP 连接管理 API（S5c）：列出 / 连接 / 断开。

鉴权：除 OAuth 回调外都需登录，且所有读写都用 ``g.current_user.id`` 隔离，
**不接受请求里传 user_id**——那是跨用户串号的入口。

OAuth 回调是浏览器独立请求，没有 JWT：授权安全性由一次性 state 保证
（见 ``services/mcp/oauth.py``），所以回调路径在 ``core.auth.PUBLIC_EXACT``
里单独放行，其他路径仍走全局门禁。
"""

import os
from urllib.parse import urlencode

from apiflask import APIBlueprint
from flask import abort, g, jsonify, redirect, request
from pydantic import BaseModel, Field, ValidationError

from app.core.validation import parse_body
from app.domains.mcp.schemas import OAuthBeginIn, StaticTokenIn
from app.services.mcp.connection_check import check_connection
from app.services.mcp.errors import McpAuthError, McpError, McpUserTokenMissing
from app.services.mcp.oauth import begin, callback, client_id_for, provider_config, revoke, supported_providers
from app.services.mcp.registry import provider_names
from app.services.mcp.user_credentials import delete_credential, list_connections, save_static_token

mcp_bp = APIBlueprint('mcp', __name__, url_prefix='/api/mcp')


class CallbackQuery(BaseModel):
    """OAuth 回调参数；provider 由 state 绑定，不从查询参数信任。"""

    state: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=500)


def _user_id() -> int:
    user = getattr(g, 'current_user', None)
    if user is None:
        abort(401, description='未登录')
    return user.id


def _known_provider(provider: str) -> None:
    """只接受代码登记的服务；未登记的 provider 不能写进凭据表。"""
    if provider not in provider_names() and provider not in supported_providers():
        abort(422, description='不支持的服务')


def _success_redirect(params: dict):
    """授权完成后的前端回跳；只允许站内相对路径，杜绝开放重定向。

    默认路径必须带 ``/#/`` 前缀：本项目路由是 hash 模式（``VITE_ROUTER_HISTORY=hash``），
    普通路径 ``/settings/mcp-connections?...`` 会让 SPA 加载后 hash 为空 → 守卫重定向到
    登录页，用户授权成功却看不到结果。query 放在 hash 段之后，前端 ``useRoute().query``
    才读得到（history 模式部署可用 env 覆盖本默认值）。
    """
    default = '/#/settings/mcp-connections'
    target = (os.getenv('MCP_OAUTH_SUCCESS_REDIRECT') or default).strip()
    if not target.startswith('/') or target.startswith('//'):
        target = default
    return redirect(f'{target}?{urlencode(params)}')


@mcp_bp.get('/connections/')
def list_mcp_connections():
    """当前用户已连接的 MCP 服务（不含任何 token / 密文）。"""
    return jsonify({'data': list_connections(_user_id()), 'message': 'ok'})


@mcp_bp.post('/connections/static/')
def connect_static_token():
    """保存用户自带 API Key（静态凭据型 MCP）。"""
    data = parse_body(StaticTokenIn)
    _known_provider(data.provider)
    try:
        save_static_token(_user_id(), data.provider, data.api_key)
    except ValueError as exc:
        abort(422, description=str(exc))
    return jsonify({'data': {'provider': data.provider, 'auth_type': 'static_token'}, 'message': 'ok'})


@mcp_bp.delete('/connections/<provider>/')
def disconnect(provider: str):
    """断开连接：删除本用户凭据，并通知上游撤销（失败不阻断）。"""
    _known_provider(provider)
    user_id = _user_id()
    if provider in supported_providers():
        revoke(provider, user_id)
    else:
        delete_credential(user_id, provider)
    return jsonify({'data': {'provider': provider, 'connected': False}, 'message': 'ok'})


@mcp_bp.post('/connections/<provider>/verify/')
def verify_connection(provider: str):
    """校验当前用户与该服务的连接：向上游握手并拉工具清单。

    连接的价值是能调通上游，不是表里有一行凭据 —— 校验把「授权过期」「Key 失效」
    变成用户点一下就看到的明确文案，并把上游工具清单直接展示给用户。
    """
    _known_provider(provider)
    try:
        return jsonify({'data': check_connection(provider, _user_id()), 'message': 'ok'})
    except McpUserTokenMissing as exc:
        abort(422, description=exc.user_message)
    except McpAuthError as exc:
        # 凭据过期 / 上游拒绝：4xx 保留后端文案（拦截器只覆盖 5xx 的 message），
        # 「授权已过期，请重新连接」是可操作指引，不能被通用文案吃掉。
        abort(400, description=exc.user_message)
    except McpError as exc:
        # 其余上游失败不是客户端的错：502 保留「这不是你填错了」的语义
        abort(502, description=exc.user_message)


@mcp_bp.post('/oauth/begin/')
def begin_oauth():
    """发起浏览器授权：返回授权 URL，前端直接跳转。"""
    data = parse_body(OAuthBeginIn)
    if data.provider not in supported_providers():
        abort(422, description='该服务不支持浏览器授权')
    # DCR 失败要在跳浏览器之前暴露，而不是等用户授权完才在回调里炸。
    client_id_for(provider_config(data.provider))
    return jsonify({'data': begin(data.provider, _user_id()), 'message': 'ok'})


@mcp_bp.get('/oauth/callback/')
def oauth_callback():
    """OAuth 回调：免登录，凭一次性 state 认领用户并落库。"""
    try:
        query = CallbackQuery.model_validate(dict(request.args))
    except ValidationError:
        abort(400, description='授权回调参数不完整')

    # provider 只从 state 记录里读，不信查询参数（回调 URL 是用户可控的）。
    provider = request.args.get('provider') or supported_providers()[0]
    try:
        provider_config(provider)
        callback(provider, query.state, query.code)
    except McpError as exc:
        abort(400, description=exc.user_message)
    except ValueError:
        abort(400, description='授权服务未登记')

    return _success_redirect({'mcp_connected': '1', 'provider': provider})
