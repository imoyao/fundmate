# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/12
# File : __init__.py
"""OCR / AI 批量导入 API（后端识别 + 用量限次）.

链路：上传图片/文本 → 后端火山方舟识别 → 返回基金候选列表（同时消耗 1 次配额）
     → 前端确认 → 复用 POST /api/watchlist/batch 入库。
"""
