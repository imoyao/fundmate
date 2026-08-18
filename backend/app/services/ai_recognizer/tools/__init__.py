# -*- coding: utf-8 -*-
"""账本精灵工具包（ToolExecutor + 工具注册表）。

见 executor.py。本包不触碰账本 DB，只做数值计算（D19 铁律：模型只叙事，数值靠代码算）。
"""

from app.services.ai_recognizer.tools.executor import TOOLS_METADATA, ToolExecutor, register_tool

__all__ = ['TOOLS_METADATA', 'ToolExecutor', 'register_tool']
