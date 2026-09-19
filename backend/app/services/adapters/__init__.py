# -*- coding: utf-8 -*-
"""第三方数据适配层（`architecture.md` §2）：xalpha / akshare / 东财直连 / 韭圈儿 / 各投顾平台。

为什么在 services 顶层，而不是 `services/sync/adapters/`（#1607 批次 3）：
适配器是**独立的第三方数据层**（职责边界见 `architecture.md` §2：只负责外部数据获取、
不参与业务入库），消费方横跨多个家族——`fund_service`、`async_backfill`、`price_range_service`
以及 sync 家族的各类 job 都用它。原先寄生在 sync 家族包内，使上述消费方"反向依赖同步家族"，
是包级双向依赖的成因之一。约定：**跨家族共享件放 `services/` 顶层，家族包内只留该家族独有实现**
（决策见 `docs/spec/decisions.md` 2026-09-19 D26、`architecture.md` §6）。

本包契约：
- 基类 `base.DataSourceAdapter`（`get_name()` / 取数方法）；
- 投顾平台注册表 `advisor_source.AdvisorSourceRegistry`（新增平台 = 加一个适配器，不改 job）。
"""
