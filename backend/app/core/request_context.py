# -*- coding: utf-8 -*-
"""请求上下文取数（当前只有来源 IP 一处，#2780）。

**为什么单独成模块**：来源 IP 的口径以前只存在于
`domains/auth/views.py::_client_ip`，服务于 `resolve` 的限流桶。审计流水
（`domains/users/auth_audit.py`）也要记「是谁从哪来」，如果各写一份，就会造出
两个口径——将来按下面的迁移指引改回 `remote_addr` 时，改一处漏一处，结果是
「限流按 A 判、台账按 B 记」，出事后反而对不上谁在什么时候被限过。

限流与审计必须看同一个事实，所以只允许一个实现。
"""

from flask import has_request_context, request


def client_ip() -> str:
    """当前请求的来源 IP；非请求上下文返回 `'unknown'`。

    优先 `X-Forwarded-For` 第一跳：后端实际部署在反向代理（容器平台）后面时，
    `remote_addr` 是**代理**的地址，全站共用一个桶会把正常用户一起卡死。
    代价是伪造该头即可绕过限流——但绕过限流只是「枚举得更快」，不扩大数据暴露面，
    比「所有人共享配额」可接受得多。

    迁移指引：若将来在反向代理后面配上 `ProxyFix`（`app.wsgi_app =
    ProxyFix(...)`），`remote_addr` 就是真实客户端地址，**本函数应改回只读
    `remote_addr` 并删掉下面这段**——届时留着 `X-Forwarded-For` 反而重新打开
    伪造口。改这里即同时改掉限流与审计，这是把它抽出来的目的。
    """
    if not has_request_context():
        return 'unknown'
    forwarded = (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
    return forwarded or (request.remote_addr or 'unknown')
