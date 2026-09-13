# -*- coding: utf-8 -*-
"""akshare 延迟导入与全局限速配置（避免应用启动期就加载 akshare）。

此前 app/__init__.py 在包导入期就 `import akshare as ak` 并 `set_option(...)`，
导致每次应用启动（含 flask reloader 每次文件变更重载）都要白白多付约 3s 加载
akshare 及其上百个子模块。改为「首次真正用到时」才导入并应用全局限速配置，
进程内仅执行一次。
"""

_AKSHARE = None


def get_akshare():
    """返回已配置的 akshare 模块（进程内首次调用时导入）。

    本函数是全仓 akshare 的**唯一收口点**，因此 V8 并发守卫（`app.core.v8_guard`）也挂在这里：
    akshare 有 40 个模块用 `py_mini_racer` 解密新浪/巨潮系 JS 数据，且每次调用新建 V8 isolate，
    多线程并发首次创建会让进程 `FATAL` abort（C++ 层，抓不住）。放在收口点意味着**任何**
    取数路径都自动免疫，不依赖开发者记得手动预热。详见 `app/core/v8_guard.py` 的实测对照。
    """
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

        # 在把 ak 交出去之前串行初始化一次 V8（双检锁 + 结果缓存，仅首次真正执行）
        from app.core.v8_guard import ensure_v8_ready

        ensure_v8_ready()

        _AKSHARE = ak
    return _AKSHARE
