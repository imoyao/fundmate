# -*- coding: utf-8 -*-
"""韭圈儿行业恐贪（ins-emotion）接入测试（离线、确定性）。

覆盖（对应设计文档验收标准 #1/#3/#4）：
  - fetch_industry_emotion：正常解析 / 空数据抛错（接口形态变更）/ 数值异常项跳过由 job 层处理
  - 落库语义：source='jiucaishuo_industry' 每行业一条 single，按日唯一（同天重复 save 不重复）
  - 查询语义：get_all_latest_singles / get_history 可取回（single 不被清理，历史可累积）

数据源契约：POST api.jiucaishuo.com/v2/guzhi-new2/ins-emotion（免登录，2026-10-20 实测）。
"""

from datetime import date, timedelta

import pytest

from app.domains.temperature.models import MarketSingleValue
from app.services.adapters.jiucaishuo_adapter import API_EMOTION, JiucaishuoAdapter
from app.services.thermometer.service import TemperatureService

SOURCE = 'jiucaishuo_industry'

_MOCK_RESP = {
    'code': 0,
    'msg': '请求成功',
    'data': [
        {
            'name': '军工PH值',
            'num': 42,
            'img_url': 'https://file.jiucaishuo.com/x.png',
            'color': '',
            'target_url': '/pagesA/tool/fear_greed',
        },
        {'name': '券商PH值', 'num': 18, 'color': '#1890FF', 'target_url': '/pagesA/tool/fear_greed?kt_type=3'},
        {'name': '新能源TF值', 'num': 9, 'color': '#f5222D', 'target_url': '/pagesA/tool/fear_greed?kt_type=4'},
        {'name': '芯片PH值', 'num': 99.85, 'color': '', 'target_url': '/pagesA/tool/fear_greed'},
    ],
}


def test_api_emotion_endpoint_is_ins_emotion():
    """端点常量指向实测可用的 ins-emotion（防误改为付费端点）。"""
    assert API_EMOTION.endswith('/v2/guzhi-new2/ins-emotion')


def test_fetch_industry_emotion_parses_rows(monkeypatch):
    """正常响应 → 原样返回上游行（name 保留原文，不做本地枚举）。"""

    def fake_post(self, path, payload):
        assert path == API_EMOTION
        return _MOCK_RESP

    monkeypatch.setattr(JiucaishuoAdapter, '_post', fake_post)
    rows = JiucaishuoAdapter().fetch_industry_emotion()
    assert len(rows) == 4
    assert rows[0]['name'] == '军工PH值'
    assert rows[0]['num'] == 42


def test_fetch_industry_emotion_empty_raises(monkeypatch):
    """空 data（接口形态变更）→ 抛错，由 job 层记 errors 不阻断。"""

    def fake_post(self, path, payload):
        return {'code': 0, 'data': []}

    monkeypatch.setattr(JiucaishuoAdapter, '_post', fake_post)
    with pytest.raises(ValueError, match='ins-emotion'):
        JiucaishuoAdapter().fetch_industry_emotion()


def _emotion_records(collected_at: date) -> list:
    """模拟 job #2b 段的记录构造（与 jobs.py 保持同构）。"""
    return [
        {
            'kind': 'single',
            'source': SOURCE,
            'name': row['name'],
            'value': float(row['num']),
            'label': '',
            'unit': '',
            'collected_at': collected_at,
            'stale': False,
        }
        for row in _MOCK_RESP['data']
    ]


def test_industry_emotion_saved_and_queried(db):
    """落库后可查回：多行业各一条 + get_history 按日可取。"""
    today = date.today()
    assert TemperatureService.save_singles(_emotion_records(today)) == 4

    latest = TemperatureService.get_all_latest_singles(sources=[SOURCE])
    assert len(latest) == 4
    names = {r['name'] for r in latest}
    assert names == {'军工PH值', '券商PH值', '新能源TF值', '芯片PH值'}
    assert all(r['collected_at'] == today.strftime('%Y-%m-%d') for r in latest)

    hist = TemperatureService.get_history(SOURCE, days=90)
    assert hist['source'] == SOURCE
    assert len(hist['dates']) >= 1


def test_industry_emotion_same_day_dedup(db):
    """同一天重复 save（重跑/并发）不产生重复行——(source,name,collected_at) 唯一。"""
    today = date.today()
    TemperatureService.save_singles(_emotion_records(today))
    TemperatureService.save_singles(_emotion_records(today))  # 同日重跑

    rows = db.query(MarketSingleValue).filter(MarketSingleValue.source == SOURCE).all()
    assert len(rows) == 4  # 不重复


def test_industry_emotion_history_accumulates(db):
    """跨日落库 → 历史逐日累积（自建历史的前提：single 不被清理）。"""
    today = date.today()
    for i in (2, 1, 0):
        TemperatureService.save_singles(_emotion_records(today - timedelta(days=i)))

    hist = TemperatureService.get_history(SOURCE, days=90)
    # get_history 契约（service.py L357+）：single 源按**行**返回——每 name 一行、
    # limit(days) 是行数上限而非日期窗口。故 3 天 × 4 行业 = 12 行，去重日期 = 3。
    # 注意：这意味着多名称源（行业恐贪 30+ 行业）若直接调 get_history(days=90)，
    # 只能取回最新约 90/行业数 天的数据——每行业趋势图需另做按 name 的查询，
    # 不能复用本接口（设计文档 §10 第 ③ 项的已知约束）。
    assert len(hist['dates']) == 12
    assert sorted(set(hist['dates'])) == sorted((today - timedelta(days=i)).strftime('%Y-%m-%d') for i in (2, 1, 0))
    assert len(hist['values']) == 12
