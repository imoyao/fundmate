# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/12 23:19
# File : constants.py
# app/services/performance/constants.py
"""XIRR 计算共享常量

EXCLUDED_ASSET_TYPES 已收口到后端唯一来源 app.core.asset_types（#1171 枚举一致性），
本文件仅 re-export 以兼容历史 import；新增 / 修改排除项请改 asset_types.py。
"""

from app.core.asset_types import EXCLUDED_ASSET_TYPES  # noqa: F401  (re-export)
