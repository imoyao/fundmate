# -*- coding: utf-8 -*-
"""为 index_catalog 补「编制/发布机构」列并按来源回填（#1425 方案 B）。

- publisher VARCHAR(20)：存机构**代码**（CSI=中证指数公司 / CNI=国证指数 / WIND=万得…），
  中文名由后端 `INDEX_PUBLISHER_LABELS` 统一映射后经搜索 extra 下发。
- 回填：source='csindex' → CSI；source='cni' → CNI；sina（行情转发源）留空 NULL，
  前端不展示该维度（宁缺勿错：错误的发布方比没有更糟）。

SQLite 支持直接 ADD COLUMN，幂等：列已存在时跳过加列、只补回填（仅补空值，
不覆盖人工/后续权威源写入的值）。

用法（在 backend/ 目录下）：
    pdm run python scripts/migrate_index_publisher.py
"""

from sqlalchemy import inspect, text

from app.core.db_factory import DOMAIN_MARKET, DatabaseFactory
from app.domains.indices.models import PUBLISHER_BY_SOURCE


def main() -> None:
    engine = DatabaseFactory.create(DOMAIN_MARKET)
    insp = inspect(engine)
    if 'index_catalog' not in insp.get_table_names():
        print('[SKIP] index_catalog 表不存在（init_db 建表后即含新列）')
        return
    cols = {c['name'] for c in insp.get_columns('index_catalog')}
    with engine.connect() as conn:
        if 'publisher' not in cols:
            conn.execute(text('ALTER TABLE index_catalog ADD COLUMN publisher VARCHAR(20)'))
            conn.commit()
            print('[OK] 已加列: publisher')
        else:
            print('[SKIP] publisher 列已存在，仅补回填')
        # 按来源回填（只补空值：publisher 是权威维度，不覆盖已有人工写入）
        for source, code in PUBLISHER_BY_SOURCE.items():
            res = conn.execute(
                text(
                    'UPDATE index_catalog SET publisher = :code '
                    "WHERE source = :source AND (publisher IS NULL OR publisher = '')"
                ),
                {'code': code, 'source': source},
            )
            conn.commit()
            print(f'[OK] source={source} → publisher={code}，回填 {res.rowcount} 条')
        left = conn.execute(
            text("SELECT count(*) FROM index_catalog WHERE publisher IS NULL OR publisher = ''")
        ).scalar()
        print(f'[INFO] publisher 仍为空 {left} 条（sina 等行情转发源，宁缺勿错，前端不展示）')
        print('[HINT] 重跑指数名录同步（pdm run sync --job index_catalog）可让新抓取数据带 publisher')


if __name__ == '__main__':
    main()
