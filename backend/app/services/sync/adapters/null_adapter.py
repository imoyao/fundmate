# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/23 22:40
# File : null_adapter.py
# backend/app/services/sync/adapters/null_adapter.py

"""
空适配器，用于不需要数据源的同步任务（如 TemperatureJob）。
"""


class NullAdapter:
    """空适配器——不做任何事情，仅提供元数据占位。"""

    def get_name(self) -> str:
        return 'null'

    def get_version(self) -> str:
        return '0.0.0'
