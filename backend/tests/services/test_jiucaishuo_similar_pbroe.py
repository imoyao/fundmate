# -*- coding: utf-8 -*-
"""韭圈儿相似基金（simfund）+ 行业 PB-ROE（pbroe-sg2）接入测试（离线、确定性）。

覆盖（对应 issue #2480 / #2481 验收标准）：
  - adapter 解析：相似基金 name/相似度/收益（含 null 相似度不补 0）；
    PB-ROE 全行业矩阵（含负 ROE 行业不剔除）
  - 形态变更：data/series 缺失即抛错（不静默返空）
  - service 降级：上游失败 → 空列表 + degraded=true（不 500）
  - job 落库：market_composites 按 (source, collected_at) 幂等
  - 读服务：无快照返回 None；有快照透出上游字段 + collected_at

数据源契约（均免登录，2026-10-21 实测 code=0）：
  - POST api.jiucaishuo.com/v2/fund-lists/simfund（fund_code）
  - POST api.jiucaishuo.com/v2/guzhi-new2/pbroe-sg2
"""

from datetime import date

import pytest

from app.domains.temperature.models import MarketComposite
from app.services.adapters.jiucaishuo_adapter import (
    API_PBROE,
    API_SIMILAR_FUNDS,
    PBROE_SOURCE,
    SIMILAR_SOURCE,
    JiucaishuoAdapter,
)
from app.services.industry_pbroe_service import get_latest_industry_pbroe
from app.services.similar_fund_service import get_similar_funds

# ── 模拟响应（结构对齐 2026-10-21 实测样本，数值同） ──

_SIMILAR_RESP = {
    'code': 0,
    'message': '相似基金',
    'data': [
        {
            'fund_code': '210004',
            'fund_simple_name': '金鹰稳健成长混合',
            'fund_income_12': '8.33',
            'fund_income_1000': '3.3974',
            'param': '近1年',
            'sml_topn_fd': '100',
        },
        {
            'fund_code': '012428',
            'fund_simple_name': '华夏核心制造混合A',
            'fund_income_12': '-7.39',
            'fund_income_1000': '0.1454',
            'param': '近1年',
            'sml_topn_fd': '97',
        },
        {
            'fund_code': '000549',
            'fund_simple_name': '华安大国新经济股票A',
            'fund_income_12': '0.73',
            'fund_income_1000': '2.4730',
            'param': '近1年',
            'sml_topn_fd': None,
        },
    ],
}

_PBROE_RESP = {
    'code': 0,
    'message': '请求成功',
    'data': {
        'title': 'A股行业PB-ROE',
        'desc': 'PB-ROE模型……',
        '_x': 'ROE(%)',
        '_y': 'PB',
        'update_time': '2026-10-21',
        'series': [
            {'x1': 2.71, 'y1': 2.4, 'name': '农林牧渔', 'color': '#FF5B5B', 'bg': 'rgba(255,91,91,0.1)'},
            {'x1': 16.34, 'y1': 2.59, 'name': '有色金属', 'color': '#7DC1FF', 'bg': 'rgba(125,193,255,0.1)'},
            {'x1': -16.78, 'y1': 0.78, 'name': '房地产', 'color': '#FFD249', 'bg': 'rgba(255,210,73,0.1)'},
        ],
    },
}


# ── 相似基金 ──


def test_endpoint_constants():
    assert API_SIMILAR_FUNDS.endswith('/v2/fund-lists/simfund')
    assert API_PBROE.endswith('/v2/guzhi-new2/pbroe-sg2')


def test_parse_similar_funds_fields():
    items = JiucaishuoAdapter.parse_similar_funds(_SIMILAR_RESP)
    assert len(items) == 3
    first = items[0]
    assert first['fund_code'] == '210004'
    assert first['fund_name'] == '金鹰稳健成长混合'
    assert first['similarity'] == 100.0
    assert first['income_1y_pct'] == 8.33
    assert first['window'] == '近1年'


def test_parse_similar_funds_null_similarity_stays_none():
    """上游只给前若干名打分：没打分 ≠ 得分 0，None 原样保留。"""
    items = JiucaishuoAdapter.parse_similar_funds(_SIMILAR_RESP)
    assert items[-1]['similarity'] is None
    assert items[-1]['income_1y_pct'] == 0.73  # 收益照常解析


def test_parse_similar_funds_empty_list_ok():
    """空 data 是合法形态（上游无相似基金），不抛错。"""
    assert JiucaishuoAdapter.parse_similar_funds({'code': 0, 'data': []}) == []


def test_parse_similar_funds_missing_data_raises():
    """data 键缺失 = 接口形态变更，抛错（由 service 转降级）。"""
    with pytest.raises(ValueError, match='simfund'):
        JiucaishuoAdapter.parse_similar_funds({'code': 0})


def test_fetch_similar_funds_uses_endpoint(monkeypatch):
    seen = {}

    def fake_post(self, path, payload):
        seen['path'] = path
        seen['fund_code'] = payload.get('fund_code')
        return _SIMILAR_RESP

    monkeypatch.setattr(JiucaishuoAdapter, '_post', fake_post)
    result = JiucaishuoAdapter().fetch_similar_funds('000001')
    assert seen['path'] == API_SIMILAR_FUNDS
    assert seen['fund_code'] == '000001'
    assert result['source'] == SIMILAR_SOURCE
    assert len(result['items']) == 3


def test_similar_funds_service_degraded_on_failure(monkeypatch):
    """上游失败 → 降级回空（验收 #3：不 500），且 degraded 标记可见。"""

    def boom(self, code):
        raise RuntimeError('连接超时')

    monkeypatch.setattr(JiucaishuoAdapter, 'fetch_similar_funds', boom)
    data = get_similar_funds('000001')
    assert data['items'] == []
    assert data['degraded'] is True
    assert '连接超时' in data['error']


def test_similar_funds_service_bad_code():
    """无法归一化的代码直接降级，不打上游。"""
    data = get_similar_funds('not-a-code')
    assert data['items'] == []
    assert data['degraded'] is True


def test_similar_funds_service_cached(monkeypatch, tmp_path):
    """命中缓存不打上游（二次调用零请求）。"""
    from app.core.cache import CacheService
    from app.services import similar_fund_service

    calls = {'n': 0}

    def fake_fetch(self, code):
        calls['n'] += 1
        return {'fund_code': code, 'items': [{'fund_code': '210004'}], 'source': SIMILAR_SOURCE}

    monkeypatch.setattr(JiucaishuoAdapter, 'fetch_similar_funds', fake_fetch)
    # 注入 tmp_path 做用例级文件缓存隔离（CacheService 契约，#1531）
    monkeypatch.setattr(
        similar_fund_service, '_SIMILAR_CACHE', CacheService(namespace='similar_funds', file_dir=tmp_path)
    )

    first = get_similar_funds('000001')
    second = get_similar_funds('000001')
    assert calls['n'] == 1
    assert first['items'] == second['items']
    assert first['degraded'] is False


# ── 行业 PB-ROE ──


def test_parse_industry_pbroe_full():
    parsed = JiucaishuoAdapter.parse_industry_pbroe(_PBROE_RESP)
    assert parsed['title'] == 'A股行业PB-ROE'
    assert parsed['x_label'] == 'ROE(%)'
    assert parsed['y_label'] == 'PB'
    assert parsed['update_time'] == '2026-10-21'
    assert len(parsed['series']) == 3
    assert parsed['series'][0] == {'industry': '农林牧渔', 'roe': 2.71, 'pb': 2.4}


def test_parse_industry_pbroe_negative_roe_kept():
    """负 ROE 行业（房地产实测 -16.78）在 PB-ROE 模型下有效，不剔除。"""
    parsed = JiucaishuoAdapter.parse_industry_pbroe(_PBROE_RESP)
    fdc = next(p for p in parsed['series'] if p['industry'] == '房地产')
    assert fdc['roe'] == -16.78


def test_parse_industry_pbroe_empty_raises():
    with pytest.raises(ValueError, match='pbroe'):
        JiucaishuoAdapter.parse_industry_pbroe({'code': 0, 'data': {'series': []}})


def test_pbroe_job_saves_snapshot(db, monkeypatch):
    """job 跑一次 → market_composites 落一行；同日重跑幂等（删旧写新）。"""
    from app.services.sync.jobs.industry_pbroe_job import IndustryPbroeSyncJob

    def fake_fetch(self):
        return JiucaishuoAdapter.parse_industry_pbroe(_PBROE_RESP)

    monkeypatch.setattr(JiucaishuoAdapter, 'fetch_industry_pbroe', fake_fetch)
    job = IndustryPbroeSyncJob(JiucaishuoAdapter(), db)

    # targets=None = 无外部目标列表，走全量自取路径（与 daily_scheduler 调用一致）
    result = job.run(full_sync=False, targets=None)
    assert result['status'] in ('success', 'SUCCESS')

    rows = db.query(MarketComposite).filter(MarketComposite.source == PBROE_SOURCE).all()
    assert len(rows) == 1
    assert rows[0].collected_at == date.today()
    assert rows[0].data['update_time'] == '2026-10-21'
    assert len(rows[0].data['series']) == 3

    # 同日重跑：仍是 1 行（按 source+日期幂等）
    job.run(full_sync=False, targets=None)
    rows = db.query(MarketComposite).filter(MarketComposite.source == PBROE_SOURCE).all()
    assert len(rows) == 1


def test_pbroe_read_service_none_when_empty(db):
    assert get_latest_industry_pbroe(db) is None


def test_pbroe_read_service_returns_latest(db):
    parsed = JiucaishuoAdapter.parse_industry_pbroe(_PBROE_RESP)
    db.add(MarketComposite(source=PBROE_SOURCE, data=parsed, collected_at=date.today(), stale=False))
    db.commit()

    data = get_latest_industry_pbroe(db)
    assert data is not None
    assert data['collected_at'] == date.today().isoformat()
    assert data['source'] == PBROE_SOURCE
    assert len(data['series']) == 3
