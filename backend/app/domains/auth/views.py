# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/1
# File : views.py
# 认证模块 API（退出登录统一入口）

import os

import requests
from apiflask import APIBlueprint
from flask import request
from loguru import logger

auth_bp = APIBlueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.post('/logout')
def logout():
    """退出登录。

    前端退出时统一调用本接口，并把当前 Supabase 的 access_token 通过
    Authorization 头带上来。若后端配置了 SUPABASE_URL 与
    SUPABASE_SERVICE_ROLE_KEY，则调用 Supabase Admin API 在**服务端**作废
    该会话（避免前端直接暴露认证请求、也保证 token 真正失效）；否则仅返回
    成功，由前端清理本地 token 完成退出。

    这样无论是否接入 Supabase 管理服务，退出链路都统一收敛到后端入口。
    """
    supabase_url = os.getenv('SUPABASE_URL')
    service_role_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

    auth_header = request.headers.get('Authorization', '')
    user_token = ''
    if auth_header.lower().startswith('bearer '):
        user_token = auth_header[7:].strip()

    if supabase_url and service_role_key and user_token:
        try:
            # 服务端作废指定会话，使用 service_role key（仅后端持有，不暴露给前端）
            resp = requests.post(
                f"{supabase_url.rstrip('/')}/auth/v1/logout",
                headers={
                    'apikey': service_role_key,
                    'Authorization': f'Bearer {service_role_key}',
                    'Content-Type': 'application/json',
                },
                json={'access_token': user_token},
                timeout=10,
            )
            if resp.status_code >= 400:
                logger.warning(
                    'Supabase 服务端登出返回非预期状态码 {}: {}',
                    resp.status_code,
                    resp.text,
                )
        except Exception as e:  # noqa: BLE001
            # 服务端作废失败不影响前端退出流程
            logger.warning('调用 Supabase 服务端登出失败: {}', e)
    else:
        logger.debug('未配置 Supabase 服务端凭证，跳过服务端会话作废')

    return {'success': True, 'message': '已退出登录'}
