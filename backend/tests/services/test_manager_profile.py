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
   两者混淆会让「共几只」显示成「最多 20 只」；
5. **同一 (经理, 基金) 关联存多行时按 ``fund_code`` 去重**（#2215）——
   ``fund_managers`` 无 (fund_id, mgr_id) 唯一约束，join 按关联行扇出，
   不去重就会「每只基金出现两次」，``fund_count`` 也会按行数虚高。

⚠️ 测试数据一律造在 **market 域**会话：``managers`` / ``funds`` / ``fund_managers``
属 market 域，生产下是独立引擎。
"""

from contextlib import closing
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.db_factory import market_session_factory
from app.domains.funds.models import Fund, FundCompany, FundManager, Manager, ManagerTenure
from app.services.manager_code import bare_manager_code
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


# ---------------------------------------------------------------------------
# 同一 (经理, 基金) 关联存多行时的去重 —— #2215「任职基金每只基金重复两次」回归网
# ---------------------------------------------------------------------------


def test_duplicate_relation_rows_are_impossible_now():
    """#2239：重复关联行在**新结构下造不出来**（唯一约束兜底）。

    这条用例替代了 #2215 的「硬插重复行 → 断言列表去重」：那个现场已无法复刻 ——
    `uq_fund_managers_fund_mgr` 会让第二次插入直接 IntegrityError。读侧那层按
    ``fund_code`` 的去重**保留**（迁移前的存量库与 Postgres 路径仍需要），
    但根治重复膨胀的是**约束**，所以这里改为钉住约束本身。

    为什么值得单独一条：这条约束是**静默**的 —— 少约束不会让任何查询报错，
    只会让表继续膨胀（`_validate_schema` 也只查缺列），必须靠测试钉住。
    """
    _seed_manager('dup2239x1', '唯一约束经理')
    _seed_fund('722391', '唯一约束基金')
    _link('dup2239x1', '722391')

    with closing(market_session_factory()()) as db:
        mgr = db.query(Manager).filter(Manager.mgr_code == 'dup2239x1').first()
        fund = db.query(Fund).filter(Fund.fund_code == '722391').first()
        db.add(FundManager(mgr_id=mgr.id, fund_id=fund.id))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # 约束生效后，列表与总数仍是「每只一条」
        data = build_manager_profile(db, 'dup2239x1', fund_limit=5)

    codes = [f['fund_code'] for f in data['funds']]
    assert len(codes) == len(set(codes)) == 1, f'每只基金应只出一条: {codes}'
    assert data['fund_count'] == 1

    # ---------------------------------------------------------------------------
    # 已移除：#2215 的 3 条「重复关联行取舍」用例（#2239）
    # ---------------------------------------------------------------------------
    #
    # 它们（`test_dedup_prefers_backfilled_row_over_blank_row` /
    # `test_dedup_prefers_active_row_when_equally_complete` /
    # `test_truncation_counts_distinct_funds_after_dedup`）都靠 `_force_link()`
    # **硬插重复关联行**来造现场 —— 当时的 `fund_managers` 只有自增主键、没有
    # (fund_id, mgr_id) 唯一约束，重复行是「库内既有事实」。
    #
    # #2239 补上 `uq_fund_managers_fund_mgr` 之后，第二次插入直接 `IntegrityError`：
    # **现场已不可复刻**，用例无法保留（留着只会是 `NameError` / 假红）。
    #
    # 覆盖去向（不是净损失）：
    #
    # - 「重复行本身」由上面 `test_duplicate_relation_rows_are_impossible_now` 钉在
    #   **约束**上 —— 根治重复膨胀的正是它，而它也是最容易被静默漏掉的一道
    #   （`_validate_schema` 只查缺列）；
    # - 「同一基金多段任期怎么挑」改由任期表承担：见本文件末尾
    #   `test_multi_segment_prefers_active_segment` 与 `manager_tenure` job 的用例；
    # - 「任期未回填的基金不能被漏掉」见 `test_fund_without_tenure_rows_still_listed`
    #   —— 这是拆分后**最容易退化**的边界（读侧一写成 INNER JOIN 就整批丢基金）；
    # - `_managed_funds` 里那层按 `fund_code` 的去重**保留不动**：它对「迁移前的存量库」
    #   与「Postgres 路径（不跑 SQLite 迁移）」仍是必需的，只是在新库上已没有可构造的
    #   输入 —— 属**有意保留的防御**，不是死代码疏漏。


def test_truncation_reports_total_over_returned():
    """截断口径（承接 #2215）：``fund_count`` 是**总数**，列表只给前 ``fund_limit`` 条。

    重复行已不可能存在（见上），但「共 N 只 / 仅显示前 M 只」的一致性仍需有人守：
    ``fund_count`` 若按返回条数（或按关联行数）计，就会与列表自相矛盾 —— 用户看到
    「共 2 只」却知道自己在管 3 只，比不显示更让人怀疑数据。
    """
    _seed_manager('t9a0004', '截断口径经理')
    for i, code in enumerate(('9T0004', '9T0005', '9T0006')):
        _seed_fund(code, f'截断口径基金{i}')
        _link('t9a0004', code)

    with closing(market_session_factory()()) as db:
        data = build_manager_profile(db, 't9a0004', fund_limit=2)

    assert data['fund_count'] == 3, '总数是全部任职基金，不受 limit 影响'
    assert len(data['funds']) == 2, '列表按 limit 截断'
    assert data['fund_count'] > len(data['funds'])


# ---------------------------------------------------------------------------
# 入参形态归一 —— 2026-10-11「每一张经理详情页都空白」那起事故的回归网
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('4202a53a90fb', '4202a53a90fb'),
        ('4202A53A90FB', '4202a53a90fb'),
        ('MGR_4202a53a90fb', '4202a53a90fb'),
        ('MGR_4202A53A90FB', '4202a53a90fb'),
        ('  MGR_4202a53a90fb  ', '4202a53a90fb'),
        ('mgr_4202a53a90fb', '4202a53a90fb'),
        ('MGR_', ''),
        ('', ''),
        ('   ', ''),
        (None, ''),
    ],
)
def test_bare_manager_code_normalizes_any_form(raw, expected):
    """归一函数吃下「裸码 / 大写 / `MGR_` 前缀 / 前后空格 / 只有前缀」。"""
    assert bare_manager_code(raw) == expected


@pytest.mark.parametrize(
    'raw',
    ['a1b2c3d4e5f6', 'A1B2C3D4E5F6', 'MGR_a1b2c3d4e5f6', 'MGR_A1B2C3D4E5F6', ' mgr_A1B2C3D4E5F6 '],
)
def test_accepts_watchlist_symbol_and_uppercase_code(raw):
    """`MGR_<code>` / 大写形态必须命中同一个经理（库内是 12 位**小写**派生码）。

    实测事故：自选/搜索里点进详情页带的是 `MGR_<code>`（#1286 命名空间约定），
    而详情页路由的 symbol 又被 `resolve_product_identity` **大写化**；两个 service
    当时只 `.strip()` 就等值匹配，于是这几种入参**全部 404**——
    表现是「每一张经理详情页都是空白」，而库里 4 只任职基金、公司名都在。

    ⚠️ **种子的姓名/码必须是本文件独有的合成值**（这里用 `形态归一经理` /
    `a1b2c3d4e5f6`，别用真实数据）。原因：本文件的测试**不走 `app` 夹具**，
    因此 `market_session_factory` 没被 patch 到 tmp_path —— 写入会落进
    **整轮测试共享的那个库**，并被后续文件读到。最初这里种的是「张坤」，
    结果 `test_manager_profile_chain.py::test_full_chain_from_em_row_to_display_text`
    的 `_mgr_code_of(db, '张坤')` 取到了这一行（`sum_scale` 为空）而报
    `assert None == 307.94`（2026-10-11 实测：CI 与本地干净库都稳定复现）。
    """
    _seed_manager('a1b2c3d4e5f6', '形态归一经理')
    with closing(market_session_factory()()) as db:
        data = build_manager_profile(db, raw)

    assert data is not None, f'{raw!r} 应能命中 a1b2c3d4e5f6'
    assert data['mgr_code'] == 'a1b2c3d4e5f6'
    assert data['name'] == '形态归一经理'


# ---------------------------------------------------------------------------
# 任期改从 manager_tenures 读（#2239）
# ---------------------------------------------------------------------------


def _seed_tenure(mgr_code, fund_code, start, end=None, current=None):
    """往 ``manager_tenures`` 落一段任期。**幂等**（本文件写入共享库，重复跑会累积）。

    ``current`` 缺省按是否在任推 —— 与 ``manager_tenure`` job 的写入口径一致。
    """
    with closing(market_session_factory()()) as db:
        mgr = db.query(Manager).filter(Manager.mgr_code == mgr_code).first()
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        exists = (
            db.query(ManagerTenure)
            .filter(
                ManagerTenure.mgr_id == mgr.id,
                ManagerTenure.fund_id == fund.id,
                ManagerTenure.start_date == start,
            )
            .first()
        )
        if exists is not None:
            exists.end_date = end
            exists.current = (end is None) if current is None else current
            db.commit()
            return
        db.add(
            ManagerTenure(
                fund_id=fund.id,
                mgr_id=mgr.id,
                start_date=start,
                end_date=end,
                current=(end is None) if current is None else current,
                source='test',
            )
        )
        db.commit()


def test_tenure_read_from_manager_tenures():
    """任期**从 ``manager_tenures`` 读**（#2239）。

    这条用例钉的是**数据来源**：拆分后 ``fund_managers`` 已不再有 start/end，
    若有人把读取路径改回关联表，这里会因为拿不到任期而红。
    """
    _seed_manager('t9a0001', '任期来源经理')
    _seed_fund('9T0001', '任期来源基金')
    _link('t9a0001', '9T0001')
    _seed_tenure('t9a0001', '9T0001', date(2018, 9, 5), None)

    with closing(market_session_factory()()) as db:
        data = build_manager_profile(db, 't9a0001')

    item = next(i for i in data['funds'] if i['fund_code'] == '9T0001')
    assert item['start_date'] == '2018-09-05'
    assert item['end_date'] is None
    assert item['is_active'] is True


def test_multi_segment_prefers_active_segment():
    """多段任期时取**在任**那段（#2239）：原表一行一格，根本表达不了两段。

    旧段（2015-01-01 ~ 2020-01-01，已卸任）+ 新段（2026-05-23 起，在任）→
    展示必须是新段，否则会把「现任」显示成十年前的旧任期。
    """
    _seed_manager('t9a0002', '多段任期经理')
    _seed_fund('9T0002', '多段任期基金')
    _link('t9a0002', '9T0002')
    _seed_tenure('t9a0002', '9T0002', date(2015, 1, 1), date(2020, 1, 1), current=False)
    _seed_tenure('t9a0002', '9T0002', date(2026, 5, 23), None, current=True)

    with closing(market_session_factory()()) as db:
        data = build_manager_profile(db, 't9a0002')

    item = next(i for i in data['funds'] if i['fund_code'] == '9T0002')
    assert item['start_date'] == '2026-05-23'
    assert item['end_date'] is None
    assert item['is_active'] is True, '在任段被旧段顶掉了'


def test_fund_without_tenure_rows_still_listed():
    """任期未回填（该基金**一条任期行都没有**）的基金必须照常出现在列表里。

    这是拆分后最容易退化的边界：任期搬到 ``manager_tenures`` 之后，读侧若用
    **INNER JOIN** 取任期，会把所有还没回填任期的基金整批漏掉 —— 而「没任期行」是
    **常态**（jjjl 每只基金一次 HTTP，只对目标池回填），不是异常。
    故 ``_managed_funds`` 必须按关联行取基金、任期单独查、缺了给 None。
    """
    _seed_manager('t9a0003', '无任期经理')
    _seed_fund('9T0003', '无任期基金')
    _link('t9a0003', '9T0003')

    with closing(market_session_factory()()) as db:
        data = build_manager_profile(db, 't9a0003')

    item = next(i for i in data['funds'] if i['fund_code'] == '9T0003')
    assert item['start_date'] is None
    assert item['end_date'] is None
    assert data['fund_count'] == 1, '没有任期行不等于没有任职基金'
