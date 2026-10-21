# -*- coding: utf-8 -*-
"""MCP provider 注册表（Ports & Adapters 的 registry 侧）。

范本对齐 ``app/services/adapters/advisor_source.py`` 的
``register_advisor_source`` / ``get_advisor_source``（`:173-189`）：注册用装饰器、
未知名字抛明确的异常（不返回 ``None`` —— 让调用点在栈上就暴露，而不是在业务层变成空数据）。

**内置 provider 惰性加载**：注册表本身不 import ``providers`` 下任何模块，
首次 :func:`get_provider` 时才加载，避免「provider 依赖基类 → 基类依赖注册表 →
注册表依赖 provider」的循环。
"""

from typing import Dict, Tuple, Type

from app.services.mcp.base import McpProvider

_PROVIDERS: Dict[str, Type[McpProvider]] = {}
_BUILTINS_LOADED = False


class UnknownMcpProvider(RuntimeError):
    """没有注册的 MCP provider —— 要么补 provider 子类，要么由调用方决定是否忽略。"""


def register_provider(cls: Type[McpProvider]) -> Type[McpProvider]:
    """注册 provider 子类（装饰器用法）。"""
    name = getattr(cls, 'name', '')
    if not name:
        raise ValueError(f'{cls.__name__} 未定义 name，无法注册为 MCP provider')
    _PROVIDERS[name] = cls
    return cls


def get_provider(name: str) -> McpProvider:
    """按名字取 provider 实例（无状态，每次新建；会话缓存属于传输层，不属于 provider）。"""
    _load_builtins()
    try:
        return _PROVIDERS[name]()
    except KeyError:
        known = ', '.join(sorted(_PROVIDERS)) or '无'
        raise UnknownMcpProvider(f'未注册的 MCP provider：{name}（已注册：{known}）') from None


def provider_names() -> Tuple[str, ...]:
    """已注册的 provider 名字（用于报错信息与诊断输出）。"""
    _load_builtins()
    return tuple(sorted(_PROVIDERS))


def _load_builtins() -> None:
    """首次使用时加载内置 provider 模块（模块 import 时完成注册）。"""
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    # 局部 import：注册表不持有对 provider 的模块级依赖（见模块 docstring）
    from app.services.mcp.providers import qieman  # noqa: F401  # 导入即注册

    _BUILTINS_LOADED = True
