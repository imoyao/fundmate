# -*- coding: utf-8 -*-
"""账本精灵·域工具装配器。

为什么需要这一层
----------------
``tools.py`` 被 ``scripts/guard_service_size.py`` 冻结在 ``lines: 644``（只减不增）。
每新增一个工具域（基金 #3111 / 宏观 #1502 / 将来的投顾）若直接在 ``tools.py`` 里加
「一行 import + 一行 install」，第二域就必然顶破基线。把装配集中到这里后，
``tools.py`` 恒定只有一处 ``install_domain_tools`` 调用——新增域不再动主文件。

装配顺序即 ``TOOLS_METADATA`` 顺序，也就是 prompt 里工具清单的呈现顺序（按域分块，
账户级在前、域级在后），改动顺序属于行为变更，不是纯重构。
"""

from typing import Callable, List

from app.services.ai_recognizer.tools_fund import install_fund_tools
from app.services.ai_recognizer.tools_macro import install_macro_tools

#: 装配顺序：账户级工具由 tools.py 自带，这里只排「域」工具
_DOMAIN_INSTALLERS: tuple = (install_fund_tools, install_macro_tools)


def install_domain_tools(register: Callable[[str, Callable], None], metadata: List[dict]) -> None:
    """按顺序把各域工具接进注册表与元数据清单。

    显式调用而非 import 副作用：「是否真的接上了」由 ``test_tool_budget`` 的集合相等
    断言与 ``test_tools_macro`` 的注册断言钉住，不靠 import 顺序碰运气。
    """
    for install in _DOMAIN_INSTALLERS:
        install(register, metadata)


__all__ = ['install_domain_tools']
