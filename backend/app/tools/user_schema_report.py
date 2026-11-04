#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""user 域结构漂移**只读**报告（``pdm run user-schema-report``，#2498）。

背景：``init_db()`` 里的存量迁移只对 SQLite 生效，Postgres（生产的 Supabase）路径一律
``[SKIP]``，于是 prod 的 user 域永远补不上列；``_validate_schema`` 每次启动报同一处漂移，
但报错只说「缺列」，说不出「修起来是补列还是重建表」。本命令补的就是这一半事实。

用法::

    pdm run user-schema-report            # 人话报告
    pdm run user-schema-report --json     # 机器可读（同一份事实）

只读保证：不建表、不补列、不写任何一行、不执行迁移；只做 ``inspect()`` + 对**需要改身份**的表
``COUNT(*)``。连接串**不打印**（可能含密码），只打印方言名。

退出码
------
====  ================================================================
0     没有漂移，且**所有待检表都真的存在**（结论完整）
2     有漂移（报告已给出「可直接补列」与「需要改身份」两类结论）
3     读不到结构（连不上 / 元数据没注册）或**空库**——**本次没有结论**，
      不得读成「无漂移」（空库上 collect() 也返回空列表，两者必须分开说）
====  ================================================================
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

# 将项目根目录（backend/）加入 Python 路径 —— 必须在 import app 之前。
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(dotenv_path=BACKEND_DIR / '.env')

# user 域的模型必须显式 import 才会进 Base.metadata（与 entitlements_cli 同一做法：
# 注册靠 import，不靠某个包自动扫描——扫描失败是静默的，缺表会被读成「没有漂移」）。
import app.domains.assets.models  # noqa: E402,F401
import app.domains.entitlements.models  # noqa: E402,F401
import app.domains.families.models  # noqa: E402,F401
import app.domains.ledgers.models  # noqa: E402,F401
import app.domains.portfolios.models  # noqa: E402,F401
import app.domains.positions.models  # noqa: E402,F401
import app.domains.securities.models  # noqa: E402,F401
import app.domains.strategy.models  # noqa: E402,F401
import app.domains.summary.models  # noqa: E402,F401
import app.domains.transactions.models  # noqa: E402,F401
import app.domains.watchlist.models  # noqa: E402,F401
from app.core.database import Base, get_engine  # noqa: E402
from app.core.db_factory import DOMAIN_USER, DatabaseFactory  # noqa: E402
from app.core.schema_drift import collect, render, split_tables  # noqa: E402


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='user-schema-report',
        description='user 域结构漂移只读报告（不建表、不补列、不写数据）',
    )
    parser.add_argument('--json', action='store_true', help='输出机器可读 JSON（同一份事实）')
    return parser


def _as_dict(drift) -> dict:
    return {
        'table': drift.table,
        'missing_columns': list(drift.missing_columns),
        'extra_columns': list(drift.extra_columns),
        'db_primary_key': list(drift.db_primary_key),
        'model_primary_key': list(drift.model_primary_key),
        'row_count': drift.row_count,
        'auto_addable_columns': list(drift.auto_addable_columns),
        'requires_identity_change': drift.requires_identity_change,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ns = _build_arg_parser().parse_args(argv)

    engine = get_engine(DOMAIN_USER)
    if engine is None:
        print('user 域引擎未配置，本次没有结论（不是「没有漂移」）', file=sys.stderr)
        return 3

    try:
        tables = DatabaseFactory.tables_by_domain(Base.metadata).get(DOMAIN_USER, [])
    except Exception as exc:  # noqa: BLE001 - 元数据没注册齐时不能当成「无漂移」
        print(f'取不到 user 域表清单，本次没有结论：{exc}', file=sys.stderr)
        return 3

    # 只打印方言名：URL 可能含密码（红线）
    print(f'user 域引擎: {engine.dialect.name}（连接串不打印），待检表 {len(tables)} 张')
    try:
        drifts = collect(engine, tables)
        present, absent = split_tables(engine, tables)
    except Exception as exc:  # noqa: BLE001 - 连不上 ≠ 没漂移
        print(f'读取结构失败，本次没有结论：{exc}', file=sys.stderr)
        return 3

    print(f'已存在表: {len(present)}/{len(tables)}')

    if ns.json:
        print(json.dumps([_as_dict(drift) for drift in drifts], ensure_ascii=False, indent=2))
    else:
        print(render(drifts, absent_tables=absent))
    if drifts:
        return 2
    # 一张表的存量结构都没查到 ⇒ 没有结论，不得退化成「无漂移」（#171 同族）
    return 3 if absent else 0


if __name__ == '__main__':
    raise SystemExit(main())
