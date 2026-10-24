# -*- coding: utf-8 -*-
# File : __init__.py
# app/services/insight/__init__.py
"""规则驱动静态诊断（#1017）。

对外只有两个入口：`build_tips`（取数 + 跑规则）与 `RULES`（规则登记表）。
"""

from app.services.insight.engine import build_snapshot, build_tips
from app.services.insight.rules import RULES, Rule, evaluate

__all__ = ['build_tips', 'build_snapshot', 'RULES', 'Rule', 'evaluate']
