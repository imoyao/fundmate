# -*- coding: utf-8 -*-
"""站内通知域：消息表 + 读写接口。

蓝图在 `views.py`，由 `app/main.py` 注册；表登记见 `core/db_factory.py`
的 `DATA_DOMAIN_REGISTRY`（user 域，含 family_id）。

读写分工：
  - 写：`services/notification_service.emit`（幂等，按 dedup_key 去重）
  - 读：`GET /api/notifications/` 列表 + 未读数，前端 `lay-notice` 消费

范围边界：本域只做**站内**消息。#508（站外推送：App / 邮件 / SocketIO）不在本期，
见 docs/working-notes/investment-strategy-engine-requirements-2026-10-15.md §528-536。
"""
