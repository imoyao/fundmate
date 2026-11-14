# -*- coding: utf-8 -*-
"""基金级只读工具（#3111）：注册一致性 / 只读保证 / 缺数据如实 / 出参投影。

为什么单开一个文件：基金级工具与账户级工具（``test_tools.py``）的纪律不同——
只读是**硬**约束（``build_fund_profile`` 默认会回填并 commit）、出参必须投影、
缺数据分 ``found`` / ``applicable`` / ``has_data`` 三档。混进账户级断言里，
「哪条纪律被破坏」会看不出来。

⚠️ 种子一律写 **market 库**（``market`` 夹具），不能用 ``db`` 夹具：``db`` 绑的是
app 库，基金档案 / 持仓 / 风格四张表在生产读的是 market 库，两边在测试里是两个
引擎（conftest 的 ``_engines`` 只覆盖 domain 工厂，不覆盖 ``SessionLocal``）。
用 ``db`` 种下去，工具会看不到数据并回 ``found: false``——那会让所有用例「绿着」测
不到东西。
"""

from datetime import date

import pytest

from app.core import db_factory
from app.domains.funds.models import Fund, FundHolding, FundIndustryAlloc, FundStyleExposure
from app.services.ai_recognizer import tools as tools_mod
from app.services.ai_recognizer import tools_fund
from app.services.ai_recognizer.tools import TOOLS_METADATA, ToolExecutor
from app.services.fund_profile import build_fund_profile

CODE = '110011'


@pytest.fixture
def market(app):
    """market 域会话（与工具内部 session 同一引擎），用例结束自动关闭。"""
    with db_factory.market_session_factory()() as session:
        yield session


def _seed_fund(session, code=CODE, name='测试基金', company_id=None):
    session.add(Fund(fund_code=code, name=name, company_id=company_id))
    session.commit()


def _seed_industry(session, code=CODE, period='2026Q2', rows=()):
    for scheme, ind_code, ind_name, ratio in rows:
        session.add(
            FundIndustryAlloc(
                fund_code=code,
                report_period=period,
                report_date=date(2026, 6, 30),
                industry_code=ind_code,
                industry_name=ind_name,
                scheme=scheme,
                ratio=ratio,
                source='eastmoney',
            )
        )
    session.commit()


def _seed_holding(session, code=CODE, period='2026Q2', basis='top10', rows=()):
    for rank, stock_code, stock_name, ratio in rows:
        session.add(
            FundHolding(
                fund_code=code,
                report_period=period,
                report_date=date(2026, 6, 30),
                holding_basis=basis,
                stock_code=stock_code,
                stock_name=stock_name,
                ratio=ratio,
                rank=rank,
                source='eastmoney',
            )
        )
    session.commit()


def _seed_box(session, code=CODE, stat_date=date(2026, 10, 31), box=None):
    for style_name, value in (box or {}).items():
        session.add(FundStyleExposure(fund_code=code, stat_date=stat_date, style_name=style_name, value=value))
    session.commit()


# ── 注册与参数闸门 ───────────────────────────────────────────────────────
def test_fund_tools_registered_in_both_places():
    """元数据 / 实现函数 / 全局清单三处名字集合必须完全相等。

    这是「已接线」的唯一判据：``tools.py`` 只调一次 ``install_fund_tools``，
    漏注册时模型能看到工具名却执行不了（或反之），单测必须挡住。
    """
    names = {m['name'] for m in tools_fund.FUND_TOOLS_METADATA}
    assert names == set(tools_fund._FUND_TOOL_FUNCS)
    assert names <= {m['name'] for m in TOOLS_METADATA}
    assert names <= set(tools_mod._FUNCTION_MAP)
    assert names == {'get_fund_profile', 'get_fund_performance', 'get_fund_holdings', 'get_fund_style'}


def test_fund_code_is_required():
    r = ToolExecutor.run('get_fund_profile', {})
    assert r['status'] == 'error'
    assert 'fund_code' in r['msg']


def test_fund_code_must_be_six_digits():
    r = ToolExecutor.run('get_fund_holdings', {'fund_code': '11001'})
    assert r['status'] == 'error'
    assert '不匹配格式' in r['msg']


def test_scopeless_tool_rejects_injected_family_id():
    """基金级工具不吃 family_id：被塞进来会被当未知参数拒绝（P1 覆盖不适用）。"""
    r = ToolExecutor.run('get_fund_profile', {'fund_code': CODE, 'family_id': 1})
    assert r['status'] == 'error'
    assert '未知参数' in r['msg']


# ── 档案：只读是硬约束 ───────────────────────────────────────────────────
def test_profile_not_found_is_honest():
    r = ToolExecutor.run('get_fund_profile', {'fund_code': '999999'})
    assert r['status'] == 'success'
    assert r['data'] == {'fund_code': '999999', 'found': False}


def test_profile_does_not_backfill_company(market, monkeypatch):
    """工具路径必须**不写库、不出网**：公司缺失时不得调 ensure_fund_company。

    反向验证：同一个 monkeypatch 下直接调 service（默认 ``allow_backfill=True``）
    必须命中回填——证明「工具没触发」是开关生效，而不是 patch 没打上。
    """
    _seed_fund(market, company_id=None)
    calls = []

    def _fake_backfill(session, code):
        calls.append(code)
        return '回填出来的公司'

    monkeypatch.setattr('app.services.fund_profile.ensure_fund_company', _fake_backfill)

    r = ToolExecutor.run('get_fund_profile', {'fund_code': CODE})
    assert r['status'] == 'success'
    assert r['data']['found'] is True
    assert r['data']['company'] is None
    assert calls == [], '工具路径不得触发基金公司回填（写库 + 可能出网）'

    assert build_fund_profile(market, CODE)['company'] == '回填出来的公司'
    assert calls == [CODE], '反向验证：默认路径确实会回填，说明上面的空调用是开关生效'


def test_profile_projects_basic_fields(market):
    _seed_fund(market, name='易方达消费行业')

    r = ToolExecutor.run('get_fund_profile', {'fund_code': CODE})
    data = r['data']
    assert data['found'] is True
    assert data['name'] == '易方达消费行业'
    # 无经理 / 无费率时给空数组，而不是 null（模型读到 null 会以为是「零费率」）
    assert data['managers'] == []
    assert data['purchase_fee_tiers'] == []
    assert data['redeem_fee_tiers'] == []


# ── 业绩：样本不足如实说 ─────────────────────────────────────────────────
def test_performance_insufficient_nav_is_not_applicable(market):
    _seed_fund(market)

    r = ToolExecutor.run('get_fund_performance', {'fund_code': CODE})
    assert r['status'] == 'success'
    assert r['data']['found'] is True
    assert r['data']['applicable'] is False
    assert r['data']['basis'] == 'insufficient'
    # 缺数据时只回最小键集，不塞 intervals / sharpe 之类空壳
    assert 'intervals' not in r['data']


# ── 持仓：分区不跨体系相加 + 口径标签 ────────────────────────────────────
def test_holdings_projection_keeps_schemes_apart(market):
    """csrc 与 gics **禁止跨体系相加**：只投影主口径，合计只算 csrc。"""
    _seed_fund(market, name='测试股票基金')
    _seed_industry(
        market,
        rows=[
            ('csrc', 'C', '制造业', 40.0),
            ('csrc', 'J', '金融业', 20.0),
            ('gics', '25', '非必需消费品', 30.0),
        ],
    )
    _seed_holding(market, rows=[(1, '600519', '贵州茅台', 9.5), (2, '000858', '五粮液', 8.1)])

    r = ToolExecutor.run('get_fund_holdings', {'fund_code': CODE})
    data = r['data']
    assert r['status'] == 'success'
    assert data['applicable'] is True
    assert data['industry_scheme'] == '证监会门类'
    # 只有主口径两行；30% 的 gics 行不得混进来
    assert [it['name'] for it in data['industries']] == ['制造业', '金融业']
    assert data['industry_total_ratio'] == 60.0
    assert data['holding_basis_label'] == '前十大（季报）'
    assert [h['stock_code'] for h in data['holdings']] == ['600519', '000858']
    assert data['holding_shown_total_ratio'] == 17.6


def test_holdings_not_applicable_without_disclosure(market):
    _seed_fund(market)

    r = ToolExecutor.run('get_fund_holdings', {'fund_code': CODE})
    assert r['data']['found'] is True
    assert r['data']['applicable'] is False


# ── 风格：主导风格与漂移序列 ─────────────────────────────────────────────
def test_style_dominant_and_drift_history(market):
    _seed_fund(market)
    _seed_box(market, stat_date=date(2026, 9, 30), box={'固收风格': 60.0, '大盘价值': 40.0})
    _seed_box(market, stat_date=date(2026, 10, 31), box={'大盘成长': 70.0, '固收风格': 30.0})

    r = ToolExecutor.run('get_fund_style', {'fund_code': CODE})
    data = r['data']
    assert r['status'] == 'success'
    assert data['has_data'] is True
    assert data['dominant_style'] == '大盘成长'
    assert data['dominant_pct'] == 70.0
    assert data['top_styles'][0] == {'style': '大盘成长', 'pct': 70.0}
    assert data['prev_dominant_style'] == '固收风格'
    assert data['dominant_changed'] is True
    # 时间正序（旧 → 新），便于模型按「先什么风格、后来变成什么」叙述
    assert [p['dominant'] for p in data['dominant_history']] == ['固收风格', '大盘成长']
    assert data['history_points'] == 2


def test_style_has_data_false_for_fund_without_box(market):
    _seed_fund(market)

    r = ToolExecutor.run('get_fund_style', {'fund_code': CODE})
    assert r['data'] == {'fund_code': CODE, 'found': True, 'has_data': False}


def test_style_unknown_fund_is_not_found():
    r = ToolExecutor.run('get_fund_style', {'fund_code': '999999'})
    assert r['data'] == {'fund_code': '999999', 'found': False, 'has_data': False}
