# -*- coding: utf-8 -*-
"""akshare 延迟导入与全局限速配置（避免应用启动期就加载 akshare）。

此前 app/__init__.py 在包导入期就 `import akshare as ak` 并 `set_option(...)`，
导致每次应用启动（含 flask reloader 每次文件变更重载）都要白白多付约 3s 加载
akshare 及其上百个子模块。改为「首次真正用到时」才导入并应用全局限速配置，
进程内仅执行一次。
"""

_AKSHARE = None


def get_akshare():
    """返回已配置的 akshare 模块（进程内首次调用时导入）。"""
    global _AKSHARE
    if _AKSHARE is None:
        import akshare as ak

        # akshare>=1.14 已移除顶层 set_option，请求限速/重试现由 app/core/requests_patch.py
        # 的全局补丁负责（按域名注入头 + 连接重试 + 屏蔽系统代理）。此处仅对仍提供该 API
        # 的旧版本做防御性限速，避免新版 import 后直接 AttributeError 崩溃。
        _set_option = getattr(ak, 'set_option', None)
        if _set_option is not None:
            _set_option('request_interval', 3)
            _set_option('use_thread', False)
        _AKSHARE = ak
    return _AKSHARE
