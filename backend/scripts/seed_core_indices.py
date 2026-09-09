# -*- coding: utf-8 -*-
"""核心指数白名单种子（#1365）。

把调研文档（docs/working-notes/index-catalog-sources-research-2026-09-08.md §二）
策展的高价值指数 upsert 进 index_catalog 的 is_core / core_rank 字段，
服务聚合搜索置顶排序与自选「指数」分组的展示优先级。

前置：先跑 `pdm run sync --job index_catalog` 回填名录（脚本只打标，不建档）。

幂等：按 index_code upsert，可重复执行；名录重建（job）会保留这两个字段。

用法（在 backend/ 目录下）：
    pdm run python scripts/seed_core_indices.py
"""

import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.core.database import market_session  # noqa: E402
from app.domains.indices.models import IndexCatalog  # noqa: E402

# (index_code, core_rank) —— rank 越小越靠前；层级语义见调研文档 §二
CORE_INDICES = [
    ('000300', 1),  # 沪深300（大盘基准）
    ('000905', 2),  # 中证500（中盘）
    ('000852', 3),  # 中证1000（小盘）
    ('000510', 4),  # 中证A500（新宽基）
    ('399317', 5),  # 国证A指（全市场基准，万得全A 881001 的免费替代）
    ('000985', 6),  # 中证全指（全市场基准）
    ('000922', 7),  # 中证红利（防御/价值）
    ('399006', 8),  # 创业板指（成长）
    ('000688', 9),  # 科创50（科技成长）
    ('399020', 10),  # 创业板200（小盘成长弹性）
    ('000698', 11),  # 科创100（中小盘科创）
    ('399303', 12),  # 国证2000（小微盘）
    ('932000', 13),  # 中证2000（小微盘）
    ('930950', 14),  # 中证偏股基金指数（基金投资基准）
]


def main() -> None:
    with market_session() as db:
        marked = missing = 0
        for index_code, rank in CORE_INDICES:
            row = db.query(IndexCatalog).filter_by(index_code=index_code).one_or_none()
            if row is None:
                # 名录未回填或该代码三源均缺（如名录尚未跑过同步）
                print(f'[!] 名录中不存在 {index_code}，跳过（请先 pdm run sync --job index_catalog）')
                missing += 1
                continue
            row.is_core = True
            row.core_rank = rank
            marked += 1
        db.commit()
        print(f'完成：标记核心指数 {marked} 只，缺失 {missing} 只')


if __name__ == '__main__':
    main()
