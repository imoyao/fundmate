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
from app.services.adapters.jiucaishuo_adapter import JiucaishuoAdapter
from app.services.bias.constants import BENCHMARK_INDICES
from app.services.sync.jobs import index_daily_job as index_daily_job_module
from app.services.sync.jobs.index_daily_job import (
    DEFAULT_TARGETS,
    TENCENT_INDEX_TARGETS,
    WIND_INDEX_TARGETS,
    IndexDailySyncJob,
)


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

    def test_parse_index_basic_missing_close_is_fund_index_shape(self):
        """基金指数（885 系）无估值表/收盘价属正常形态，解析不报错（#275 双模式）。"""
        out = JiucaishuoAdapter.parse_index_basic(
            {'code': 0, 'data': {'gu_name': '万得普通股票型基金指数', 'table': []}}
        )
        assert out['gu_name'] == '万得普通股票型基金指数'
        assert 'close' not in out

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
        assert result['price_mode'] == 'anchored'

    def test_normalized_mode_for_fund_index(self):
        """基金指数（885 系）无估值锚 → 起点归一化 1000，price_mode='normalized'。"""
        adapter = JiucaishuoAdapter()
        basic_no_close = {'code': 0, 'data': {'gu_name': '万得普通股票型基金指数', 'table': []}}
        adapter._post = MagicMock(side_effect=[basic_no_close, DETAIL_RESP])
        result = adapter.fetch_index_daily('885000.WI', months=12)
        assert result['price_mode'] == 'normalized'
        rows = result['rows']
        # 起点 ret=0 → 归一化 1000
        assert rows[0]['close'] == pytest.approx(1000.0, abs=0.01)
        # 末端 = 1000 × 1.4832
        assert rows[-1]['close'] == pytest.approx(1483.2, abs=0.1)

    def test_full_history_all_mode_filters_placeholder(self):
        """date='all' 全量模式：1970-01-01 占位伪点被剔除（#1365 实测）。"""
        adapter = JiucaishuoAdapter()
        all_resp = {
            'code': 0,
            'data': {
                'tb_data': {
                    'x_data': ['1970-01-01', '2000-01-04', '2026-09-07'],
                    'series': [{'data': ['0', '3.1', '545.73']}],
                }
            },
        }
        adapter._post = MagicMock(side_effect=[BASIC_RESP, all_resp])
        result = adapter.fetch_index_daily('881001.WI', months='all')
        dates = [r['trade_date'].isoformat() for r in result['rows']]
        assert '1970-01-01' not in dates
        assert dates[0] == '2000-01-04'
        # payload 断言：date 原样传 'all'（字符串）
        detail_payload = adapter._post.call_args_list[1][0][1]
        assert detail_payload['date'] == 'all'


class TestIndexDailySyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        adapter.fetch_index_daily.return_value = {
            'gu_code': '881001.WI',
            'gu_name': '万得全A',
            'price_mode': 'anchored',
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

    def test_default_targets_cover_wind_family(self):
        """默认目标 = #275 定稿的万得系全家桶（含万得全A）+ 韭圈儿已收录的宽基/风格指数。

        不硬编码条数：清单会随「源侧收录情况」增删（新增一行即可），
        断言只锁定「必须覆盖」的品种，避免每次补品种都要改数字。
        """
        for gu in ('881001.WI', '885000.WI', '885001.WI'):
            assert gu in DEFAULT_TARGETS
        # 2026-09-09 复核补齐：用户在韭圈儿可见、此前漏抓的 5 只（实测均可取）
        for gu in ('881003.WI', '881007.WI', '8841425.WI', '8841431.WI', '889033.WI'):
            assert gu in DEFAULT_TARGETS
        # 2026-10-01：默认清单 = 万得系（韭圈儿）+ 交易所指数（腾讯）
        assert DEFAULT_TARGETS == [c for c, _ in WIND_INDEX_TARGETS] + [c for c, _ in TENCENT_INDEX_TARGETS]

    def test_incremental_uses_12_months(self, job, db):
        """非全量跑 12 月增量；全量跑成立来（'all'）。"""
        job.run(full_sync=False, targets=['881001.WI'])
        assert job.adapter.fetch_index_daily.call_args[0][1] == 12


class TestBenchmarkAlignment:
    """交易所清单必须覆盖乖离率侧的全部宽基基准（同一批「常用基准」的两处登记）。

    刻意用**测试**而非 import 锁一致性：`index_daily_job`（sync 家族）反向 import
    `bias.constants`（bias 家族）会违反 `architecture.md` §6 的家族边界。
    """

    def test_covers_all_bias_benchmarks(self):
        tencent_codes = {code for code, _ in TENCENT_INDEX_TARGETS}
        missing = set(BENCHMARK_INDICES) - tencent_codes
        assert not missing, f'交易所清单缺基准：{sorted(missing)}'

    def test_names_match_bias_benchmarks(self):
        mapping = dict(TENCENT_INDEX_TARGETS)
        for code, name in BENCHMARK_INDICES.items():
            assert mapping[code] == name, f'{code} 名称两侧不一致：{mapping[code]} != {name}'


class TestTencentRouting:
    """`.SH` / `.SZ` 走腾讯直连；`.WI` 仍走韭圈儿（分流按后缀，不靠清单查表）。"""

    @pytest.fixture
    def job(self, db):
        return IndexDailySyncJob(MagicMock(), db)

    def test_exchange_code_routes_to_tencent(self, job, db, monkeypatch):
        calls = []

        def fake_fetch(symbol, start_date=None, **kwargs):
            calls.append((symbol, start_date))
            return [('2026-09-29', 4300.0), ('2026-09-30', 4357.62)]

        monkeypatch.setattr(index_daily_job_module, 'fetch_daily_tencent', fake_fetch)
        result = job.run(full_sync=False, targets=['000300.SH'])

        assert result['status'] == 'success'
        assert calls[0][0] == '000300.SH'
        # 增量（非全量）必须传 12 月起点，不能退化成「成立以来」全量翻页
        assert calls[0][1] is not None
        rows = db.query(IndexDaily).filter_by(index_code='000300.SH').order_by(IndexDaily.trade_date).all()
        assert [r.source for r in rows] == ['tencent', 'tencent']
        assert [r.price_mode for r in rows] == ['raw', 'raw']
        assert float(rows[-1].close) == 4357.62
        # 韭圈儿通道一次都不该被碰
        job.adapter.fetch_index_daily.assert_not_called()

    def test_full_sync_asks_tencent_for_all_history(self, job, db, monkeypatch):
        seen = {}

        def fake_fetch(symbol, start_date=None, **kwargs):
            seen['start_date'] = start_date
            return [('2026-09-30', 4357.62)]

        monkeypatch.setattr(index_daily_job_module, 'fetch_daily_tencent', fake_fetch)
        job.run(full_sync=True, targets=['000300.SH'])
        assert seen['start_date'] is None, '全量应翻到源侧耗尽（start_date=None）'

    def test_wind_code_still_uses_jiucaishuo(self, job, db, monkeypatch):
        job.adapter.fetch_index_daily.return_value = {
            'gu_code': '881001.WI',
            'gu_name': '万得全A',
            'price_mode': 'anchored',
            'rows': [{'trade_date': date(2026, 9, 30), 'close': 6457.3, 'ret_pct': 48.32}],
        }

        def boom(*args, **kwargs):
            raise AssertionError('万得系不该走腾讯通道')

        monkeypatch.setattr(index_daily_job_module, 'fetch_daily_tencent', boom)
        job.run(full_sync=False, targets=['881001.WI'])
        row = db.query(IndexDaily).one()
        assert row.source == 'jiucaishuo'
        assert row.price_mode == 'anchored'

    def test_tencent_empty_is_tolerated(self, job, db, monkeypatch):
        """腾讯取空（通道异常 / 非交易日）不得让整个 job 失败。"""
        monkeypatch.setattr(index_daily_job_module, 'fetch_daily_tencent', lambda *a, **k: [])
        result = job.run(full_sync=False, targets=['000300.SH'])
        assert result['status'] == 'success'
        assert db.query(IndexDaily).count() == 0
