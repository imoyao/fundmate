# -*- coding: utf-8 -*-
"""家庭财务规划域（财务晴雨表 v2）：预估年支出 / 预估年收入。

这是家庭级用户配置（一家庭一条），只存两个「预估」标量，不记流水——
自由度公式的分母（年支出/年收入）无法从投资流水推导，必须由用户填报。
蓝图在 `views.py`，由 `app/main.py` 注册；表登记见 `core/db_factory.py`
的 `DATA_DOMAIN_REGISTRY`（DOMAIN_USER，与 dividend_targets 同域）。
派生口径（自由度 = 可投资资产×3%/分母）在前端 financialHealth.ts，
后端只负责配置的读写，不跨端重复算比率。
"""
