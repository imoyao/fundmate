# -*- coding: utf-8 -*-
"""回归网：`index_*` 数据 job 必须**批量写库**，不许再逐行 `db.add`（#2522 同族）。

## 为什么需要

生产市场域是 Turso（libsql over Hrana/HTTP）：**一行一次往返≈0.2s**。原实现
`_save_data` 逐行 `self.db.add(...)`，于是 run `39943903338`（2026-10-23）实测：

| job | 行数 | 耗时 |
|---|---|---|
| `index_daily` | 24 个指数共约 1.3 万行 | **58.8 分钟** |
| `index_constituents` | 每次全量重建 | 27 分钟仍未完成，被 90 分钟 job 超时掐死 |

同时 `fund_nav` / `price_history` / `asset_snapshot` 等核心 job 全部**秒级**完成——
说明慢的不是抓取而是写库，与 #2522（名录类 job）同一速率（0.2s/行）。

## 本文件钉住什么

1. 四个 job 的写入路径**真的调用了** `bulk_insert_rows`（改回逐行 `db.add` 即红）；
2. 批量写之后**语义不变**：幂等不重复、成分整体替换、`None` 不覆盖已落库值、
   `source` 默认值不被显式 NULL 抹掉。
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import event

from app.domains.indices.models import (
    IndexConstituent,
    IndexDaily,
    IndexValuation,
    IndexValuationBaseline,
)
from app.services.sync.bulk_ops import set_if_changed
from app.services.sync.jobs import (
    index_constituent_job as constituent_module,
)
from app.services.sync.jobs import (
    index_daily_job as daily_module,
)
from app.services.sync.jobs import (
    index_valuation_job as valuation_module,
)
from app.services.sync.jobs import (
    index_valuation_lg_job as valuation_lg_module,
)
from app.services.sync.jobs.index_constituent_job import IndexConstituentSyncJob
from app.services.sync.jobs.index_daily_job import IndexDailySyncJob
from app.services.sync.jobs.index_valuation_job import IndexValuationSyncJob
from app.services.sync.jobs.index_valuation_lg_job import IndexValuationLgSyncJob

D1 = date(2026, 10, 21)
D2 = date(2026, 10, 22)


def _spy(monkeypatch, module):
    """把模块内的 `bulk_insert_rows` 换成「记录 + 真执行」的探针。

    只记录不执行会让「落库正确性」失去验证；只执行不记录则钉不住「是否走了批量」。
    """
    calls = []
    real = module.bulk_insert_rows

    def spy(db, model, rows, **kwargs):
        calls.append({'model': model.__name__, 'rows': [dict(r) for r in rows], 'kwargs': kwargs})
        return real(db, model, rows, **kwargs)

    monkeypatch.setattr(module, 'bulk_insert_rows', spy)
    return calls


# --------------------------------------------------------------------------- #
# index_daily
# --------------------------------------------------------------------------- #
def test_index_daily_uses_bulk_insert(db, monkeypatch):
    calls = _spy(monkeypatch, daily_module)
    job = IndexDailySyncJob(MagicMock(), db)

    job._save_data(
        [
            {
                'gu_code': '881001.WI',
                'source': 'jiucaishuo',
                'price_mode': 'anchored',
                'rows': [
                    {'trade_date': D1, 'close': 6400.0, 'ret_pct': 47.0},
                    {'trade_date': D2, 'close': 6457.3, 'ret_pct': 48.32},
                ],
            }
        ]
    )

    assert len(calls) == 1, f'整批应合并成一次批量写，实际 {len(calls)} 次'
    assert calls[0]['model'] == 'IndexDaily'
    assert len(calls[0]['rows']) == 2
    assert '指数日线 881001.WI' in calls[0]['kwargs']['log_scope']
    assert db.query(IndexDaily).filter_by(index_code='881001.WI').count() == 2
    assert float(db.query(IndexDaily).filter_by(trade_date=D2).one().close) == pytest.approx(6457.3)


def test_index_daily_second_run_writes_no_insert(db, monkeypatch):
    """同 (index_code, trade_date) 重跑：不该再发批量 INSERT（幂等）。"""
    job = IndexDailySyncJob(MagicMock(), db)
    payload = [
        {
            'gu_code': '881001.WI',
            'source': 'jiucaishuo',
            'price_mode': 'anchored',
            'rows': [{'trade_date': D1, 'close': 6400.0}, {'trade_date': D2, 'close': 6457.3}],
        }
    ]

    calls = _spy(monkeypatch, daily_module)
    job._save_data(payload)
    assert len(calls) == 1

    job._save_data(payload)
    assert len(calls) == 1, '第二次全是更新，不该再走批量 INSERT'
    assert db.query(IndexDaily).count() == 2, '不许重复插入'


def test_index_daily_updates_changed_close(db, monkeypatch):
    """已有行只改值：落库生效且仍不新增行。"""
    job = IndexDailySyncJob(MagicMock(), db)
    _spy(monkeypatch, daily_module)
    job._save_data(
        [{'gu_code': 'X.WI', 'rows': [{'trade_date': D1, 'close': 1.0}], 'source': 'jiucaishuo', 'price_mode': 'raw'}]
    )
    job._save_data(
        [{'gu_code': 'X.WI', 'rows': [{'trade_date': D1, 'close': 2.0}], 'source': 'jiucaishuo', 'price_mode': 'raw'}]
    )

    row = db.query(IndexDaily).filter_by(index_code='X.WI', trade_date=D1).one()
    assert float(row.close) == pytest.approx(2.0)
    assert db.query(IndexDaily).count() == 1


# --------------------------------------------------------------------------- #
# index_constituents
# --------------------------------------------------------------------------- #
def test_index_constituent_uses_bulk_insert_and_replaces(db, monkeypatch):
    calls = _spy(monkeypatch, constituent_module)
    job = IndexConstituentSyncJob(MagicMock(), db)

    job._save_data(
        [
            {'index_code': '000300', 'index_name': '沪深300', 'symbol': '600519', 'stock_name': '贵州茅台'},
            {'index_code': '000300', 'index_name': '沪深300', 'symbol': '000001', 'stock_name': '平安银行'},
        ]
    )
    assert len(calls) == 1 and calls[0]['model'] == 'IndexConstituent'
    assert len(calls[0]['rows']) == 2
    assert db.query(IndexConstituent).count() == 2

    # 调样：整体替换，旧成分必须消失
    job._save_data([{'index_code': '000300', 'index_name': '沪深300', 'symbol': '600036', 'stock_name': '招商银行'}])
    symbols = {r.symbol for r in db.query(IndexConstituent).filter_by(index_code='000300').all()}
    assert symbols == {'600036'}, f'应整体替换，实际 {symbols}'
    assert len(calls) == 2


# --------------------------------------------------------------------------- #
# index_valuation
# --------------------------------------------------------------------------- #
def test_index_valuation_bulk_insert_and_skip_redundant(db, monkeypatch):
    calls = _spy(monkeypatch, valuation_module)
    job = IndexValuationSyncJob(MagicMock(), db)

    rows = [
        {'index_code': '000300', 'trade_date': D1, 'index_name': '沪深300', 'pe_1': 12.5, 'pe_2': 13.0},
        {'index_code': '000905', 'trade_date': D1, 'index_name': '中证500', 'pe_2': 22.0},
    ]
    job._save_data(rows)

    assert len(calls) == 1 and calls[0]['model'] == 'IndexValuation'
    keys = {frozenset(r.keys()) for r in calls[0]['rows']}
    assert len(keys) == 1, f'批量写要求整批键集一致，实际 {keys}'
    assert all('source' in r for r in calls[0]['rows']), 'source 必须显式给默认值，不能留 None'

    got = db.query(IndexValuation).filter_by(index_code='000300', trade_date=D1).one()
    assert float(got.pe_1) == pytest.approx(12.5)
    assert got.source == 'csindex'

    # 重跑且新值为 None：不许把已落库的 pe_1 抹成 NULL，也不许再发 INSERT
    job._save_data([{'index_code': '000300', 'trade_date': D1, 'pe_1': None, 'pe_2': 13.2}])
    assert len(calls) == 1, '已有行不该再走批量 INSERT'
    db.expire_all()
    got = db.query(IndexValuation).filter_by(index_code='000300', trade_date=D1).one()
    assert float(got.pe_1) == pytest.approx(12.5), 'None 不得覆盖已落库值'
    assert float(got.pe_2) == pytest.approx(13.2), '非 None 新值必须覆盖'


# --------------------------------------------------------------------------- #
# index_valuation_lg
# --------------------------------------------------------------------------- #
def test_index_valuation_lg_bulk_insert(db, monkeypatch):
    calls = _spy(monkeypatch, valuation_lg_module)
    job = IndexValuationLgSyncJob(MagicMock(), db)

    job._save_data(
        [
            {'index_code': '000300', 'trade_date': D1, 'pe_ttm': 12.1, 'index_name': '沪深300'},
            {'index_code': '000905', 'trade_date': D1, 'pe_ttm': 21.3, 'index_name': '中证500'},
        ]
    )

    assert len(calls) == 1 and calls[0]['model'] == 'IndexValuationBaseline'
    assert len(calls[0]['rows']) == 2
    assert db.query(IndexValuationBaseline).count() == 2
    got = db.query(IndexValuationBaseline).filter_by(index_code='000905').one()
    assert float(got.pe_ttm) == pytest.approx(21.3)
    assert got.source == 'lg'


def test_index_valuation_lg_second_run_no_insert(db, monkeypatch):
    job = IndexValuationLgSyncJob(MagicMock(), db)
    payload = [{'index_code': '000300', 'trade_date': D1, 'pe_ttm': 12.1}]

    calls = _spy(monkeypatch, valuation_lg_module)
    job._save_data(payload)
    job._save_data(payload)

    assert len(calls) == 1, '重跑不该再插入'
    assert db.query(IndexValuationBaseline).count() == 1


# --------------------------------------------------------------------------- #
# 稳态写库：同一批数据重跑必须**一条 UPDATE 都不发**（run 39958611684 的 2957 秒就花在这）
# --------------------------------------------------------------------------- #
def _record_updates(db):
    """在 session 绑定的 engine 上挂监听，收集 flush 出来的 UPDATE 语句。"""
    engine = db.get_bind()

    def recorder(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip()[:6].upper() == 'UPDATE':
            collected.append(statement)

    collected = []
    event.listen(engine, 'before_cursor_execute', recorder)
    return engine, recorder, collected


def test_decimal_float_equality_is_the_trap():
    """根因钉子：`Decimal('6457.3') != 6457.3`，所以裸 setattr 必然判脏。"""
    assert Decimal('6457.3') != 6457.3
    # 反例：二进制可精确表示的数（12.5）两边相等，所以造数据必须用「不整」的值才测得出陷阱
    assert Decimal('12.5') == 12.5
    assert Decimal('6457.300000') == Decimal('6457.3'), '尾随零不影响数值相等'


def test_set_if_changed_ignores_equal_value():
    """数值相等（Decimal vs float）时不赋值、返回 False。"""
    row = IndexDaily(close=Decimal('6457.300000'), ret_pct=None)
    assert set_if_changed(row, 'close', 6457.3) is False
    assert set_if_changed(row, 'ret_pct', None) is False
    assert row.__dict__.get('close') == Decimal('6457.300000')


def test_set_if_changed_writes_real_change():
    """真的变了才赋值，并返回 True。"""
    row = IndexDaily(close=Decimal('6457.3'), ret_pct=Decimal('1.0'))
    assert set_if_changed(row, 'close', 6458.0) is True
    assert Decimal(str(row.close)) == Decimal('6458.0')
    assert set_if_changed(row, 'ret_pct', None) is True, 'None 覆盖非 None 也是变更'


def test_index_daily_second_run_emits_no_update(db):
    """同数据重跑：0 条 UPDATE（改回裸 setattr 必红）。"""
    job = IndexDailySyncJob(MagicMock(), db)
    payload = [
        {
            'gu_code': '881001.WI',
            'source': 'jiucaishuo',
            'price_mode': 'anchored',
            'rows': [
                {'trade_date': D1, 'close': 6400.13, 'ret_pct': 47.31},
                {'trade_date': D2, 'close': 6457.3, 'ret_pct': 48.32},
            ],
        }
    ]
    job._save_data(payload)

    engine, recorder, updates = _record_updates(db)
    try:
        job._save_data(payload)
    finally:
        event.remove(engine, 'before_cursor_execute', recorder)

    assert updates == [], f'数值没变却发了 {len(updates)} 条 UPDATE（Turso 上每行 0.2s）'


def test_index_daily_changed_value_emits_update(db):
    """反向护栏：真有变化时必须发 UPDATE（防止「跳过一切」被当成功）。"""
    job = IndexDailySyncJob(MagicMock(), db)
    job._save_data(
        [
            {
                'gu_code': 'X.WI',
                'source': 'jiucaishuo',
                'price_mode': 'anchored',
                'rows': [{'trade_date': D1, 'close': 100.0, 'ret_pct': 1.0}],
            }
        ]
    )

    engine, recorder, updates = _record_updates(db)
    try:
        job._save_data(
            [
                {
                    'gu_code': 'X.WI',
                    'source': 'jiucaishuo',
                    'price_mode': 'anchored',
                    'rows': [{'trade_date': D1, 'close': 101.5, 'ret_pct': 1.0}],
                }
            ]
        )
    finally:
        event.remove(engine, 'before_cursor_execute', recorder)

    assert len(updates) == 1, f'真变化应恰好 1 条 UPDATE，实际 {len(updates)}'
    db.expire_all()
    assert float(db.query(IndexDaily).filter_by(index_code='X.WI', trade_date=D1).one().close) == pytest.approx(101.5)


def test_index_valuation_second_run_emits_no_update(db):
    """估值 job 同样：同数据重跑 0 条 UPDATE。"""
    job = IndexValuationSyncJob(MagicMock(), db)
    payload = [
        {'index_code': '000300', 'trade_date': D1, 'index_name': '沪深300', 'pe_1': 12.53, 'pe_2': 13.07},
    ]
    job._save_data(payload)

    engine, recorder, updates = _record_updates(db)
    try:
        job._save_data(payload)
    finally:
        event.remove(engine, 'before_cursor_execute', recorder)

    assert updates == [], f'数值没变却发了 {len(updates)} 条 UPDATE'


def test_index_valuation_lg_second_run_emits_no_update(db):
    job = IndexValuationLgSyncJob(MagicMock(), db)
    payload = [{'index_code': '000300', 'trade_date': D1, 'pe_ttm': 12.13, 'index_name': '沪深300'}]
    job._save_data(payload)

    engine, recorder, updates = _record_updates(db)
    try:
        job._save_data(payload)
    finally:
        event.remove(engine, 'before_cursor_execute', recorder)

    assert updates == [], f'数值没变却发了 {len(updates)} 条 UPDATE'
