# -*- coding: utf-8 -*-
"""目标配比子域（#2237）。

与 `domains/strategy/views.py`（策略标签，**基线冻结、只减不增**）分开建子包：
配比是独立业务，塞进冻结视图文件会违反厚度守卫。子包内仍是 `views.py`，
故 `scripts/check_api_conventions.py` 的 `**/views.py` 扫描照旧能扫到。
"""
