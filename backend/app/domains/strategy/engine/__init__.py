# -*- coding: utf-8 -*-
"""策略引擎接口子包。

WHY 独立子包
    `domains/strategy/views.py` 已被**视图厚度守卫基线冻结（只减不增）**，
    新增端点只能落在新文件；且「策略引擎（诊断 / 行为反推）」与原有
    「策略标签 CRUD」不是同一件事，分开更符合单一职责。

放在 `domains/strategy/engine/views.py` 而非 `engine_views.py`，是为了让
`scripts/check_api_conventions.py` 的 `domains/**/views.py` 扫描仍能覆盖到，
新增端点不会从 api.md 里漏登记。
"""
