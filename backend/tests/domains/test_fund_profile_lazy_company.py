# -*- coding: utf-8 -*-
"""端到端：走**真实 HTTP 端点**验证按需回填接线（#2037 · 方案 A）。

为什么 service 单测之外还要这个：单测分别验了 `ensure_fund_company` 与
`fetch_fund_company_of`，但「`build_fund_profile` 真的接上了回填、且回填的 commit
与视图层的会话管理不打架」这件事，只有从端点打进来才算数——中间隔着
`products/views.py` 的 `closing(market_session_factory()())`。若回填的 `commit`
让外层会话进入异常状态，端点会 500，而上面两层单测照样全绿。

全程**不触网**：只把取数口 `fetch_fund_company_of` 换成固定答案，
写库链路（`get_or_create_fund_company` → `funds.company_id` → commit）走真实的。
"""

from contextlib import closing

import pytest

from app.core.db_factory import market_session_factory
from app.domains.funds.models import Fund
from app.services import fund_company_backfill as backfill_module
from app.services.fund_company_backfill import reset_miss_cache
from app.services.sync import company_resolver as resolver_module

CODE = '004373'
URL = f'/api/products/fund-profile/?code={CODE}'
COMPANY = '端到端测试基金'
COMPANY_CODE = 'E2E001'


@pytest.fixture
def blank_company_fund():
    """造一只 `company_id` 为空的基金（返回 code）。"""
    with closing(market_session_factory()()) as db:
        fund = db.query(Fund).filter(Fund.fund_code == CODE).first()
        if fund is None:
            fund = Fund(fund_code=CODE, name='端到端测试基金')
            db.add(fund)
        fund.company_id = None
        db.commit()
    return CODE


@pytest.fixture
def offline_company_source(monkeypatch):
    """把两处外部取数换成固定答案，公司行仍走真实唯一写入口。**返回 monkeypatch 本身**。

    - `fetch_fund_company_of`：本卡新增的单只取数口；
    - `fetch_fund_company_list`：`resolve_company_identity` 解析权威 code 时用（否则真抓）。

    返回 monkeypatch 是为了让单个用例能在此基础上再覆盖某个点（见
    `test_endpoint_second_call_skips_backfill`）；不用它的用例忽略返回值即可。
    """
    reset_miss_cache()
    resolver_module.reset_cache()
    monkeypatch.setattr(
        backfill_module,
        'fetch_fund_company_of',
        lambda *a, **k: {'name': COMPANY, 'code': COMPANY_CODE},
    )
    monkeypatch.setattr(
        resolver_module,
        'fetch_fund_company_list',
        lambda: [{'code': COMPANY_CODE, 'name': COMPANY}],
    )
    yield monkeypatch
    reset_miss_cache()
    resolver_module.reset_cache()


def _company_id_of(code=CODE):
    with closing(market_session_factory()()) as db:
        fund = db.query(Fund).filter(Fund.fund_code == code).first()
        return fund.company_id if fund else None


def test_endpoint_backfills_company_end_to_end(client, db, blank_company_fund, offline_company_source):
    """空 company_id → 端点 200 且带公司名，且已落库。"""
    assert _company_id_of() is None

    resp = client.get(URL)

    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()['data']
    assert data['company'] == COMPANY
    assert data['fund_code'] == CODE
    assert _company_id_of() is not None, '回填必须落库，否则每次冷开都要重抓'


def test_endpoint_second_call_skips_backfill(client, db, blank_company_fund, offline_company_source):
    """已落库 → 第二次打端点不再触发回填（不重复请求外部）。"""
    assert client.get(URL).status_code == 200

    def _boom(*a, **k):
        raise AssertionError('已有 company_id 时不应再触发回填')

    # 取数口换成会炸的替身：被调用即失败（回填层本身若仍被调用则返回已有值，
    # 不算失败——判定「不重复抓」的依据是取数口没被碰）
    offline_company_source.setattr(backfill_module, 'fetch_fund_company_of', _boom)

    resp = client.get(URL)
    assert resp.status_code == 200
    assert resp.get_json()['data']['company'] == COMPANY


def test_endpoint_degrades_when_source_unavailable(client, db, blank_company_fund, monkeypatch):
    """取数口返回 None（源不可用）→ 端点仍 200，其余字段完整。

    这是本方案的核心承诺：外部不可用只损失「基金公司」一栏（降级「—」），
    不让整个详情页失败。
    """
    reset_miss_cache()
    resolver_module.reset_cache()
    monkeypatch.setattr(backfill_module, 'fetch_fund_company_of', lambda *a, **k: None)

    resp = client.get(URL)

    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()['data']
    assert data['company'] is None
    # 其余字段不受影响
    assert data['fund_code'] == CODE
    assert 'unit_nav' in data and 'managers' in data and data['source'] == '天天基金'
    assert _company_id_of() is None, '取数失败不得写库（一次抖动不该固化成永久留白）'


def test_endpoint_unknown_fund_still_404(client, db, offline_company_source):
    """基金不存在 → 404（回填不得把「不存在」变成「公司查不到」的 200）。"""
    resp = client.get('/api/products/fund-profile/?code=NOPE00')
    assert resp.status_code == 404
