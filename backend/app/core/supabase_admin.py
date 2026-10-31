# -*- coding: utf-8 -*-
"""Supabase Admin API 薄封装（`service_role` 凭证，仅后端持有）。

为什么集中到一处：`SUPABASE_SERVICE_ROLE_KEY` 是**超级凭证**（可读写 auth schema、
可造任意用户）。散在各 view 里手写 `requests` 调用，迟早有人把它打进日志或响应。
本模块只暴露两个动作，且调用点一律是「业务已成功、同步尽力而为」：

- :func:`update_user_metadata` —— 把本地权威字段（`username`）写回 GoTrue
  `user_metadata`，避免「本地改了名、token 里还是旧名」（#2764 遗留项）；
- :func:`revoke_session` —— 服务端作废某个 access_token 对应的会话（退出登录）。

**失败语义统一为「返回 False + WARNING」，不抛异常、不回滚业务**：
本地 `users` 表是登录标识的权威（D10 / #2764），GoTrue `user_metadata` 只是冗余副本。
反过来若「同步失败就回滚改名」，用户会看到「保存失败」而本地其实已经改不了——比
两边不一致更糟；同理，登录也不该因为 metadata 没同步上而失败。

⚠️ 凭证必须在**调用期**读 `os.getenv`，不能在模块顶层固化成常量：测试用
monkeypatch 注入假凭证，import 期常量会让 patch 失效（本仓已因此踩过多次，见
`tests/conftest.py` 里关于「早绑定」的注释）。
"""

import os
from typing import Dict, Optional

import requests
from loguru import logger


def _base_url() -> Optional[str]:
    """Supabase 项目 URL（`https://<ref>.supabase.co`），未配置返回 None。"""
    url = (os.getenv('SUPABASE_URL') or '').strip()
    return url.rstrip('/') or None


def _service_key() -> Optional[str]:
    """service_role key，未配置返回 None。**只允许在本模块内出现，不外传**。"""
    key = (os.getenv('SUPABASE_SERVICE_ROLE_KEY') or '').strip()
    return key or None


def is_configured() -> bool:
    """两侧凭证是否齐备（齐备才谈得上调用 Admin API）。"""
    return bool(_base_url() and _service_key())


def _headers(key: str) -> Dict[str, str]:
    return {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
    }


def update_user_metadata(supabase_id: str, metadata: Dict, *, timeout: float = 5.0) -> bool:
    """把 `metadata` 合并进 GoTrue 用户的 `user_metadata`（幂等，可重复调用）。

    用 `PUT /auth/v1/admin/users/{id}`：Supabase 对 `user_metadata` 做**浅合并**，
    只覆盖传入的键，不会清掉 `roles` 等既有字段。

    返回 True = 已同步；False = 未配置 / 网络失败 / 非 2xx（均已记日志）。
    """
    base, key = _base_url(), _service_key()
    if not (base and key and supabase_id):
        logger.debug('未配置 Supabase Admin 凭证（或缺 supabase_id），跳过 user_metadata 同步')
        return False
    try:
        resp = requests.put(
            f'{base}/auth/v1/admin/users/{supabase_id}',
            headers=_headers(key),
            json={'user_metadata': metadata},
            timeout=timeout,
        )
    except Exception as e:  # noqa: BLE001 - 同步失败不得影响主流程
        logger.warning('同步 user_metadata 失败（sub={}）：{}', supabase_id, e)
        return False
    if resp.status_code >= 400:
        logger.warning(
            '同步 user_metadata 返回非预期状态码 {}（sub={}）：{}',
            resp.status_code,
            supabase_id,
            resp.text[:200],
        )
        return False
    logger.info('已同步 user_metadata 到 GoTrue（sub={}，字段={}）', supabase_id, sorted(metadata))
    return True


def revoke_session(access_token: str, *, timeout: float = 10.0) -> bool:
    """服务端作废指定 access_token 对应的会话（退出登录用）。

    未配置凭证时返回 False，由调用方决定「仅前端清理」即可（退出链路仍算成功）。
    """
    base, key = _base_url(), _service_key()
    if not (base and key and access_token):
        logger.debug('未配置 Supabase Admin 凭证，跳过服务端会话作废')
        return False
    try:
        resp = requests.post(
            f'{base}/auth/v1/logout',
            headers=_headers(key),
            json={'access_token': access_token},
            timeout=timeout,
        )
    except Exception as e:  # noqa: BLE001 - 作废失败不影响前端退出流程
        logger.warning('调用 Supabase 服务端登出失败: {}', e)
        return False
    if resp.status_code >= 400:
        logger.warning('Supabase 服务端登出返回非预期状态码 {}: {}', resp.status_code, resp.text[:200])
        return False
    return True
