# -*- coding: utf-8 -*-
"""基金经理资料聚合（#1970 · 详情页经理详情区块）。

重点覆盖四件事：

1. **入参是 ``mgr_code`` 而非姓名** —— 库内实测 119 组重名（最多「吴昊」6 位），
   故必须能按 ``mgr_code`` 精确命中，且**同名不同码互不串**（最易写错的点）；
2. **未落库字段返回 None 而不是 0** —— 生产库实测 ``appointment_date`` / ``sum_scale`` /
   ``best_return`` / ``start_date`` / ``end_date`` 填充率**全为 0%**，若返回 0
   会被前端读成「管理规模 0 亿」，是假数值；
3. **列表带公司名消歧** —— 有重名，不带公司分不出谁是谁；
4. **``fund_count`` 是总数而非返回条数** —— 列表有 ``fund_limit`` 上限，
   两者混淆会让「共几只」显示成「最多 20 只」。

⚠️ 测试数据一律造在 **market 域**会话：``managers`` / ``funds`` / ``fund_managers``
属 market 域，生产下是独立引擎。
"""

from contextlib import closing

from app.core.db_factory import market_session_factory
from app.domains.funds.models import Fund, FundCompany, FundManager, Manager
from app.services.manager_profile import build_manager_profile

PROFILE_URL = '/api/products/manager-profile/?mgr_code='


def _seed_company(name='测试基金公司', code='T9001'):
    """建基金公司。``code`` 是 NOT NULL 唯一键，漏了会撞外键/非空约束。"""
    with closing(market_session_factory()()) as db:
        company = db.query(FundCompany).filter(FundCompany.name == name).first()
        if company is None:
            company = FundCompany(code=code, name=name)
            db.add(company)
            db.commit()
            return company.id
        return company.id


def _seed_manager(mgr_code, name, company_id=None, **fields):
    """建经理，返回 mgr_code。已存在则更新字段。

    只回 ``mgr_code``（字符串）而非 ORM 实例：commit 后实例属性过期
    （expire_on_commit），session 关闭后再取属性会抛 DetachedInstanceError。
    """
    with closing(market_session_factory()()) as db:
        mgr = db.query(Manager).filter(Manager.mgr_code == mgr_code).first()
        if mgr is None:
            mgr = Manager(mgr_code=mgr_code, name=name, company_id=company_id, **fields)
            db.add(mgr)
        else:
            mgr.name = name
            for k, v in fields.items():
                setattr(mgr, k, v)
        db.commit()
        return mgr_code


def _seed_fund(fund_code, name):
    with closing(market_session_factory()()) as db:
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if fund is None:
            fund = Fund(fund_code=fund_code, name=name)
            db.add(fund)
            db.commit()
            return fund.id
        return fund.id


def _link(mgr_code, fund_code, is_classic=False):
    with closing(market_session_factory()()) as db:
        mgr = db.query(Manager).filter(Manager.mgr_code == mgr_code).first()
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        exists = db.query(FundManager).filter(FundManager.mgr_id == mgr.id, FundManager.fund_id == fund.id).first()
        if exists is None:
            db.add(FundManager(mgr_id=mgr.id, fund_id=fund.id, is_classic=is_classic))
            db.commit()


def test_returns_none_for_unknown_mgr_code():
    """经理不存在返回 None（由调用方转 404），不抛异常。"""
    with closing(market_session_factory()()) as db:
        assert build_manager_profile(db, 'deadbeef0000') is None


def test_raises_on_empty_mgr_code():
    """空入参抛 ValueError（由调用方转 400）。"""
    with closing(market_session_factory()()) as db:
        try:
            build_manager_profile(db, '  ')
        except ValueError:
            return
        raise AssertionError('空 mgr_code 应抛 ValueError')


def test_lookup_by_mgr_code_not_name():
    """重名时按 mgr_code 精确命中，不串到同名另一个人。"""
    company_id = _seed_company()
    _seed_manager('aaa111', '吴昊', company_id)
    _seed_manager('bbb222', '吴昊', company_id)

    with closing(market_session_factory()()) as db:
        a = build_manager_profile(db, 'aaa111')
        b = build_manager_profile(db, 'bbb222')

    assert a['mgr_code'] == 'aaa111'
    assert b['mgr_code'] == 'bbb222'


def test_unfilled_fields_are_none_not_zero():
    """未落库字段必须 None —— 0 会被前端读成「规模 0 亿」这种假数值。"""
    company_id = _seed_company()
    _seed_manager('ccc333', '张三', company_id)

    with closing(market_session_factory()()) as db:
        data = build_manager_profile(db, 'ccc333')

    # 生产库这四项填充率实测 0%
    assert data['appointment_date'] is None
    assert data['sum_scale'] is None
    assert data['best_return'] is None
    # 有值时必须原样透出（不能被 None 逻辑误伤）
    assert data['name'] == '张三'
    assert data['company'] == '测试基金公司'


def test_filled_fields_are_returned():
    """字段有值时正常返回（防止「一律None」的实现蒙混过关）。"""
    from datetime import date

    company_id = _seed_company()
    _seed_manager('ddd444', '李四', company_id, appointment_date=date(2015, 3, 1), sum_scale=123.45, best_return=88.8)

    with closing(market_session_factory()()) as db:
        data = build_manager_profile(db, 'ddd444')

    assert data['appointment_date'] == '2015-03-01'
    assert data['sum_scale'] == 123.45
    assert data['best_return'] == 88.8


def test_funds_list_with_company_and_total():
    """任职基金列表：带公司名、含 is_classic，且 fund_count 是总数而非返回条数。"""
    company_id = _seed_company()
    _seed_manager('eee555', '王五', company_id)
    for i in range(3):
        code = f'9{i:05d}'
        _seed_fund(code, f'测试基金{i}')
        _link('eee555', code, is_classic=(i == 0))

    with closing(market_session_factory()()) as db:
        data = build_manager_profile(db, 'eee555')

    assert data['fund_count'] == 3
    assert len(data['funds']) == 3
    names = [f['name'] for f in data['funds']]
    assert '测试基金0' in names
    classic = [f['is_classic'] for f in data['funds'] if f['name'] == '测试基金0']
    assert classic == [True]
    # 任期起止实测全空，仍须返回 key（前端统一降级「—」）
    for item in data['funds']:
        assert 'start_date' in item and item['start_date'] is None
        assert 'end_date' in item and item['end_date'] is None


def test_fund_count_is_total_not_limited():
    """fund_count 是**总数**，与 fund_limit 截断无关（否则「共几只」会说成 20）。"""
    company_id = _seed_company()
    _seed_manager('fff666', '赵六', company_id)
    for i in range(5):
        code = f'8{i:05d}'
        _seed_fund(code, f'批量基金{i}')
        _link('fff666', code)

    with closing(market_session_factory()()) as db:
        data = build_manager_profile(db, 'fff666', fund_limit=2)

    assert data['fund_count'] == 5  # 总数
    assert len(data['funds']) == 2  # 被 fund_limit 截断


def test_manager_without_fund():
    """没有关联基金的经理：fund_count=0、列表为空，不报错（前端空态）。"""
    _seed_manager('ggg777', '无关联经理')
    with closing(market_session_factory()()) as db:
        data = build_manager_profile(db, 'ggg777')

    assert data['fund_count'] == 0
    assert data['funds'] == []
