# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/24
# File : __init__.py
"""FeedLog 反馈域：SSO 身份令牌端点（#1998 任务 B）。

只负责「把本仓已登录身份签成 FeedLog 认的 JWT」这一件事；签发规则见
`app/services/feedlog.py`，端点契约见 `views.py`。
"""
