# -*- coding: utf-8 -*-
"""提醒能力（自选到价 / 单日跌幅 / 回撤）。

三层分包，互不反向依赖：

- :mod:`app.services.alerts.rules`   纯判据与文案（无 DB，可单测）
- :mod:`app.services.alerts.quotes`  行情供给（批量取价，只读）
- :mod:`app.services.alerts.service` 编排（家庭隔离 + 通知投递）

放在 `alerts/` 而不是 `watchlist_*`：提醒是**跨域能力**——今天由自选触发，
将来持仓诊断、策略规则也会用同一套「判据 → 候选 → 通知」链路；
`watchlist*` 模块另受持仓口径守卫约束（`guard_watchlist_active_scope`），
本包不碰 `Position`，不应被那条守卫的 TARGETS 绑住。
"""
