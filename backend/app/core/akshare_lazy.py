# -*- coding: utf-8 -*-
"""akshare 延迟导入与全局限速配置（避免应用启动期就加载 akshare）。

此前 app/__init__.py 在包导入期就 `import akshare as ak` 并 `set_option(...)`，
导致每次应用启动（含 flask reloader 每次文件变更重载）都要白白多付约 3s 加载
akshare 及其上百个子模块。改为「首次真正用到时」才导入并应用全局限速配置，
进程内仅执行一次。
"""

_AKSHARE = None


def get_akshare():
    """返回已配置的 akshare 模块（进程内首次调用时导入并应用全局限速配置）。"""
    global _AKSHARE
    if _AKSHARE is None:
        import akshare as ak

        # 防御性限速：降低单 IP 请求频率，缓解东财按 IP 限流/临时封。
        # request_interval=3 表示相邻请求至少间隔 3 秒；use_thread=False 避免并发连接触发风控。
        ak.set_option('request_interval', 3)
        ak.set_option('use_thread', False)
        _AKSHARE = ak
    return _AKSHARE
