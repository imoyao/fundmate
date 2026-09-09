# -*- coding: utf-8 -*-
"""自选表唯一键回归迁移的手动 CLI 入口（#1286 / #1362 评审 #3）。

迁移逻辑已收敛到 app/core/migrations.py::migrate_watchlist_unique_key，
init_db 启动时会自动按 user 域执行该迁移（存量库静默回归基线）。
本脚本保留为「手动补跑 / 排查」入口：例如本地单跑某库、或 CI 单独校验。

频等：已含新约束（建表 SQL 中出现 uk_watchlist_symbol_market_venue）时跳过。

用法（在 backend 目录）：
    pdm run python scripts/migrate_watchlist_unique_key.py
"""

from app.core.db_factory import DOMAIN_USER, DatabaseFactory
from app.core.migrations import migrate_watchlist_unique_key


def main() -> None:
    # watchlist 属 user 域（默认单库时与 market 同引擎）
    engine = DatabaseFactory.create(DOMAIN_USER)
    print(migrate_watchlist_unique_key(engine))


if __name__ == '__main__':
    main()
