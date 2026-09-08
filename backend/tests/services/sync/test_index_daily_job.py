# -*- coding: utf-8 -*-
"""测试 IndexDailySyncJob + JiucaishuoAdapter 解析（#275/#1365）。

解析用例的 fixture 形态来自 2026-09-08 实测（见
docs/working-notes/index-catalog-sources-research-2026-09-08.md）。
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.core.db_factory import DATA_DOMAIN_REGISTRY
from app.domains.indices.models import IndexDaily
from app.services.sync.adapters.jiucaishuo_adapter import JiucaishuoAdapter
from app.services.sync.jobs.index_daily_job import DEFAULT_TARGETS, IndexDailySyncJob


def test_index_daily_registered_as_market():
    assert DATA_DOMAIN_REGISTRY.get('index_daily') == 'market'


BASIC_RESP = {
    'code': 0,
    'data': {
        'gu_name': '万得全A',
        'table': [
            {'name': '收盘价', 'new_value': '6457.3'},
            {'name': '市盈率', 'new_value': '21.52', 'new_percent_value': {'value': '77.49%'}},
            {'name': '市净率', 'new_value': '1.84'},
        ],
    },
}

DETAIL_RESP = {
    'code': 0,
    'data': {
        'tb_data': {
            'x_data': ['2025-12-31', '2026-01-04', '2026-09-07'],
            'series': [{'data': ['0', '1.5', '48.32']}],
        }
    },
}


class TestJiucaishuoParse:
    def test_parse_index_basic(self):
        out = JiucaishuoAdapter.parse_index_basic(BASIC_RESP)
        assert out['gu_name'] == '万得全A'
        assert out['close'] == 6457.3
        assert out['pe'] == 21.52
        assert out['pe_pct'] == '77.49%'
        assert out['pb'] == 1.84

    def test_parse_index_basic_missing_close_raises(self):
        with pytest.raises(ValueError):
            JiucaishuoAdapter.parse_index_basic({'code': 0, 'data': {'table': []}})

    def test_parse_return_series(self):
        xs, rets = JiucaishuoAdapter.parse_return_series(DETAIL_RESP)
        assert xs[-1] == '2026-09-07'
        assert rets[-1] == 48.32

    def test_parse_return_series_length_mismatch_raises(self):
        bad = {'code': 0, 'data': {'tb_data': {'x_data': ['a', 'b'], 'series': [{'data': [1]}]}}}
        with pytest.raises(ValueError):
            JiucaishuoAdapter.parse_return_series(bad)

    def test_reverse_derivation(self):
        """反推公式：P(t) = P_now × (1+r(t)) / (1+r_end)，锚定最新收盘。"""
        adapter = JiucaishuoAdapter()
        adapter._post = MagicMock(side_effect=[BASIC_RESP, DETAIL_RESP])
        result = adapter.fetch_index_daily('881001.WI', months=12)
        rows = result['rows']
        # 末端点位必须等于当前收盘（r=r_end）
        assert rows[-1]['close'] == pytest.approx(6457.3, abs=0.01)
        # 起点 ret=0 → base = 6457.3 / 1.4832
        assert rows[0]['close'] == pytest.approx(6457.3 / 1.4832, abs=0.01)
        assert result['gu_name'] == '万得全A'


class TestIndexDailySyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        adapter.fetch_index_daily.return_value = {
            'gu_code': '881001.WI',
            'gu_name': '万得全A',
            'snapshot': {'close': 6457.3},
            'rows': [
                {'trade_date': date(2026, 9, 5), 'close': 6400.0, 'ret_pct': 47.0},
                {'trade_date': date(2026, 9, 8), 'close': 6457.3, 'ret_pct': 48.32},
            ],
        }
        return IndexDailySyncJob(adapter, db)

    def test_upsert_and_no_duplicate(self, job, db):
        """同 (index_code, trade_date) 重跑应更新而非重复插入。"""
        assert job.run(full_sync=True, targets=['881001.WI'])['status'] == 'success'
        assert job.run(full_sync=True, targets=['881001.WI'])['status'] == 'success'
        assert db.query(IndexDaily).count() == 2
        row = db.query(IndexDaily).filter_by(trade_date=date(2026, 9, 8)).one()
        assert row.index_code == '881001.WI'
        assert float(row.close) == 6457.3

    def test_single_target_failure_tolerated(self, job, db):
        """单目标失败不阻断（best-effort 数据源）。"""
        job.adapter.fetch_index_daily.side_effect = RuntimeError('down')
        result = job.run(full_sync=True, targets=['881001.WI'])
        assert result['status'] == 'success'
        assert db.query(IndexDaily).count() == 0

    def test_default_targets_is_wdqa(self):
        assert DEFAULT_TARGETS == ['881001.WI']
