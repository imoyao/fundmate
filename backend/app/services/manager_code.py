# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/11
# File : manager_code.py
# app/services/manager_code.py
"""``managers.mgr_code`` 入参归一化（唯一实现）。

## 为什么需要它（2026-10-11 实测：**每一张经理详情页都是空白**）

``managers.mgr_code`` 是 12 位**小写**十六进制派生码（张坤 = ``4202a53a90fb``）。
但同一个经理在链路上有两种写法：

- **裸 code**：``4202a53a90fb`` —— ``managers`` 表原值；
- **watchlist / 搜索 symbol**：``MGR_4202a53a90fb`` —— #1286 命名空间约定，
  见 :data:`app.core.constants.MANAGER_SYMBOL_PREFIX`。

详情页路由 ``/:assetType/:symbol`` 拿到的 symbol 还会被
:func:`app.services.product_identity.resolve_product_identity` **大写化**
（``symbol.strip().upper()``），所以最终传到 ``manager-profile`` / ``manager-holdings``
的入参是 ``MGR_4202A53A90FB``（带前缀）或 ``4202A53A90FB``（裸但大写）。

两个 service 都只做了 ``(mgr_code or '').strip()`` 就等值匹配
``Manager.mgr_code == code``，于是**两种形态全部落空**。实测：

===============  ==============================
入参              接口结果
===============  ==============================
``4202a53a90fb``  200（4 只任职基金、公司=易方达基金）
``4202A53A90FB``  404「基金经理不存在」
``MGR_4202a53a90fb``  404
``MGR_4202A53A90FB``  404
===============  ==============================

即**从任何入口进经理详情页都是空的**（自选/搜索结果里点进去带 ``MGR_`` 前缀，
手输裸码又被大写化）。

``core/constants.py`` 早就写过「展示名解析须剥离该前缀回查 ``managers`` 表，
见 ``services/watchlist_service.lookup_manager`` 唯一实现」——本模块把这件
「唯一实现」真拎出来，免得再出现第三个漏做的调用点。

## 口径

归一 = **去 ``MGR_`` 前缀 + 转小写**，**只用于比较**，不改库内原值；
``mgr_code`` 是十六进制派生码，大小写不承载语义，故忽略大小写是安全的
（与 ``watchlist_service.lookup_manager`` 的既有做法一致，理由见其 docstring：
搜索侧原样输出、历史行存在大小写混存，等值匹配会漏查）。
"""

from __future__ import annotations

from app.core.constants import MANAGER_SYMBOL_PREFIX


def bare_manager_code(symbol_or_code: str | None) -> str:
    """把 ``MGR_<mgr_code>`` 或裸 ``mgr_code`` 归一成**用于比较**的裸小写 code。

    Args:
        symbol_or_code: ``MGR_4202a53a90fb`` / ``4202A53A90FB`` / ``4202a53a90fb``
            三种形态都要吃下；``None`` / 空串 / 只有前缀都返回空串。

    Returns:
        去前缀并转小写后的裸 code；入参无有效内容时返回 ``''``，由调用方决定
        是报「缺少 mgr_code」（写路径）还是回空（读路径）。
    """
    code = (symbol_or_code or '').strip()
    if code[: len(MANAGER_SYMBOL_PREFIX)].upper() == MANAGER_SYMBOL_PREFIX:
        code = code[len(MANAGER_SYMBOL_PREFIX) :]
    return code.lower()
