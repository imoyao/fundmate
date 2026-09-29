# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/9/26
# File : __init__.py
"""账本精灵对话域（#1121 S1）.

无模型无迁移：只承载 POST /api/agent/chat/ 端点与请求 schema，
对话循环与工具执行在 services/ai_recognizer（D19：模型只叙事，数值靠代码算）。
"""
