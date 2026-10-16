# -*- coding: utf-8 -*-
"""基金经理代表作重仓（#1970 扩展 · 详情页经理区块）。

重点覆盖四件「错了不会报错」的事：

1. **代表作怎么选** —— ``is_classic`` 优先；无标记则取任期最长的那只，
   且**不取规模最大**（否则与头部「管理规模」指标读成同一件事）；
2. **口径优先级** —— 同报告期``full`` 与 ``top10`` 并存时优先 ``full``，
   与 ``penetration._load_holding_map`` 严格一致（不能出现两套口径）；
3. **口径标签必须下发** —— 前端要能说清「季报前十大」还是「半年报全量」，
   否则「只披露 10 只」会被误读成「只买了 10 只」；
4. **空态固定契约** —— 无数据返回 ``rows: []`` + ``empty_reason`` 而非 None，
   前端才能区分「无数据」与「接口 404」。

⚠️ 测试数据一律造在 **market 域**会话（``fund_holdings`` 属 market 域）。
"""

from contextlib import closing
from datetime import date

from app.core.db_factory import market_session_factory
from app.domains.funds.models import Fund, FundCompany, FundHolding, FundManager, Manager, ManagerTenure
from app.services.manager_holdings import build_manager_holdings


def _seed_company(name='重仓测试基金公司', code='T9100'):
    with closing(market_session_factory()()) as db:
        c = db.query(FundCompany).filter(FundCompany.name == name).first()
        if c is None:
            c = FundCompany(code=code, name=name)
            db.add(c)
            db.commit()
            return c.id
        return c.id


def _seed_manager(mgr_code, name, company_id):
    with closing(market_session_factory()()) as db:
        if db.query(Manager).filter(Manager.mgr_code == mgr_code).first() is None:
            db.add(Manager(mgr_code=mgr_code, name=name, company_id=company_id))
            db.commit()


def _seed_fund(code, name):
    with closing(market_session_factory()()) as db:
        f = db.query(Fund).filter(Fund.fund_code == code).first()
        if f is None:
            f = Fund(fund_code=code, name=name)
            db.add(f)
            db.commit()
            return f.id
        return f.id


def _link(mgr_code, fund_code, is_classic=False, start_date=None):
    """建经理-基金关联（+ 可选一段任期）。**幂等**：测试库复用持久化 SQLite。

    #2239 之后任期不在关联表上：``start_date`` 改为往 ``manager_tenures`` 落一段
    **在任**任期（``end_date=None``），正是「任期长度」聚合的输入。
    ``start_date=None`` 表示**任期未回填** → 不落任期行（代表作挑选应跳过它）。

    已存在时补写 ``is_classic`` —— 否则上一轮留下的旧值会让本次断言读到陈旧数据。
    """
    with closing(market_session_factory()()) as db:
        m = db.query(Manager).filter(Manager.mgr_code == mgr_code).first()
        f = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        exists = db.query(FundManager).filter(FundManager.mgr_id == m.id, FundManager.fund_id == f.id).first()
        if exists is None:
            db.add(FundManager(mgr_id=m.id, fund_id=f.id, is_classic=is_classic))
        else:
            exists.is_classic = is_classic
        db.commit()

        if start_date is None:
            return
        tenure = (
            db.query(ManagerTenure)
            .filter(
                ManagerTenure.mgr_id == m.id,
                ManagerTenure.fund_id == f.id,
                ManagerTenure.start_date == start_date,
            )
            .first()
        )
        if tenure is None:
            db.add(
                ManagerTenure(
                    fund_id=f.id,
                    mgr_id=m.id,
                    start_date=start_date,
                    end_date=None,
                    current=True,
                    source='test',
                )
            )
        else:
            tenure.end_date = None
            tenure.current = True
        db.commit()


def _seed_holding(fund_code, stock_code, stock_name, ratio, rank, period='2026Q2', basis='full', **extra):
    """写入一条重仓。

    **必须幂等**：测试库是复用持久化的 SQLite 文件（不每次重建），而``fund_holdings``
    的唯一键是 ``(fund_code, report_period, holding_basis, stock_code)`` ——
    上一轮跑过的数据仍在，重复插入会直接撞 UNIQUE 约束，让**一批测试一起红**，
    且报错与真正的逻辑错误毫无关系（已踩过一次：改动本身没问题，却看到 9 个失败）。
    """
    with closing(market_session_factory()()) as db:
        exists = (
            db.query(FundHolding)
            .filter(
                FundHolding.fund_code == fund_code,
                FundHolding.report_period == period,
                FundHolding.holding_basis == basis,
                FundHolding.stock_code == stock_code,
            )
            .first()
        )
        if exists is not None:
            exists.stock_name = stock_name
            exists.ratio = ratio
            exists.rank = rank
            db.commit()
            return
        db.add(
            FundHolding(
                fund_code=fund_code,
                report_period=period,
                report_date=extra.get('report_date', date(2026, 6, 30)),
                holding_basis=basis,
                stock_code=stock_code,
                stock_name=stock_name,
                ratio=ratio,
                rank=rank,
                market_value=extra.get('market_value', 1000.0),
                source='eastmoney',
            )
        )
        db.commit()


# ── 基本查询与 404 语义 ────────────────────────────────────────


def test_returns_none_for_unknown_mgr_code():
    """经理不存在返回 None → 视图层转 404（与 manager_profile 同语义）。"""
    with closing(market_session_factory()()) as db:
        assert build_manager_holdings(db, 'deadbeef0000') is None


def test_raises_on_empty_mgr_code():
    """空入参抛 ValueError → 视图层转 400。"""
    with closing(market_session_factory()()) as db:
        try:
            build_manager_holdings(db, '   ')
        except ValueError:
            return
        raise AssertionError('空 mgr_code 应抛 ValueError')


def test_manager_without_fund_returns_empty_contract():
    """无关联基金：返回固定契约空态（rows=[] + empty_reason），不是 None。"""
    _seed_manager('mh001', '无关联经理', _seed_company())
    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh001')

    assert data is not None
    assert data['rows'] == []
    assert data['empty_reason']
    assert data['basis'] is None
    assert data['basis_label'] is None


def test_fund_without_holdings_returns_empty_contract():
    """代表作基金未到披露期 / 抓取未覆盖 → 空态，不是报错。"""
    cid = _seed_company()
    _seed_manager('mh002', '无重仓经理', cid)
    _seed_fund('6A0001', '无持仓基金')
    _link('mh002', '6A0001', is_classic=True)

    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh002')

    assert data['rows'] == []
    assert data['fund_code'] == '6A0001'
    assert data['empty_reason']


# ── 代表作选择：最容易写错的一环 ──────────────────────────────


def test_prefers_is_classic_over_longer_tenure():
    """标记了代表作时，即使另一只任期更长也要选代表作。"""
    cid = _seed_company()
    _seed_manager('mh003', '代表作优先经理', cid)
    _seed_fund('6A0002', '任期最长但非代表作')
    _seed_fund('6A0003', '标记的代表作')
    _link('mh003', '6A0002', start_date=date(2015, 1, 1))
    _link('mh003', '6A0003', is_classic=True, start_date=date(2024, 1, 1))

    for i in range(1, 11):
        _seed_holding('6A0002', f'90{i:04d}', f'长任期股{i}', 5.0, i, period='2026Q2')
        _seed_holding('6A0003', f'80{i:04d}', f'代表作股{i}', 5.0, i, period='2026Q2')

    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh003')

    assert data['fund_code'] == '6A0003'
    assert data['rows'][0]['stock_name'] == '代表作股1'


def test_falls_back_to_longest_tenure_without_classic_flag():
    """无 is_classic 标记 → 取任期最长的那只。"""
    cid = _seed_company()
    _seed_manager('mh004', '无标记经理', cid)
    _seed_fund('6A0004', '任期短')
    _seed_fund('6A0005', '任期长')
    _link('mh004', '6A0004', start_date=date(2023, 1, 1))
    _link('mh004', '6A0005', start_date=date(2016, 1, 1))

    _seed_holding('6A0005', '600001', '任期长基金持股', 8.0, 1)

    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh004')

    assert data['fund_code'] == '6A0005'


def test_missing_start_date_not_picked_as_representative():
    """**未回填任期（start_date=None）不应被选成代表作**。

    这是最容易漏的边界：库内任期只对目标池回填，大量行start_date 为空，
    若排序时 None 参与比较会把它当成「最早/最长」而误选。
    """
    cid = _seed_company()
    _seed_manager('mh005', '空任期经理', cid)
    _seed_fund('6A0006', '有任期')
    _seed_fund('6A0007', '无任期')
    _link('mh005', '6A0006', start_date=date(2016, 5, 1))
    _link('mh005', '6A0007', start_date=None)  # 未回填

    _seed_holding('6A0006', '600002', '有任期基金持股', 7.0, 1)
    _seed_holding('6A0007', '600003', '无任期基金持股', 9.0, 1)

    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh005')

    assert data['fund_code'] == '6A0006'


# ── 口径：full优先 + 标签下发 ─────────────────────────────────


def test_prefers_full_basis_over_top10_in_same_period():
    """同报告期 full 与 top10 并存时**优先 full**（与 penetration 一致）。"""
    cid = _seed_company()
    _seed_manager('mh006', '双口径经理', cid)
    _seed_fund('6A0008', '双口径基金')
    _link('mh006', '6A0008', is_classic=True)

    # top10 口径先插入 —— 顺序不应影响结果，若被选中说明优先级反了
    _seed_holding('6A0008', '700001', '季报股', 4.0, 1, basis='top10')
    _seed_holding('6A0008', '600004', '半年报股', 6.0, 1, basis='full')

    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh006')

    assert data['basis'] == 'full'
    assert data['basis_label'] == '全量披露（半年报/年报）'
    names = [r['stock_name'] for r in data['rows']]
    assert '半年报股' in names
    assert '季报股' not in names


def test_falls_back_to_top10_and_labels_it():
    """只有 top10 时用它，且标签要说清是「季报前十大」。"""
    cid = _seed_company()
    _seed_manager('mh007', '仅季报经理', cid)
    _seed_fund('6A0009', '仅季报基金')
    _link('mh007', '6A0009', is_classic=True)

    _seed_holding('6A0009', '700002', '季报持仓', 5.0, 1, basis='top10')

    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh007')

    assert data['basis'] == 'top10'
    assert data['basis_label'] == '前十大（季报）'
    assert data['basis_label']  # 非空：前端需要它说清口径


def test_uses_latest_report_period_only():
    """只取最新报告期，不混合历史期（否则「重仓变化」会被算成一堆）。"""
    cid = _seed_company()
    _seed_manager('mh008', '多期经理', cid)
    _seed_fund('6A0010', '多期基金')
    _link('mh008', '6A0010', is_classic=True)

    _seed_holding('6A0010', '600005', '旧期股', 3.0, 1, period='2026Q1')
    _seed_holding('6A0010', '600006', '新期股', 8.0, 1, period='2026Q2')

    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh008')

    assert data['report_period'] == '2026Q2'
    names = [r['stock_name'] for r in data['rows']]
    assert names == ['新期股']


# ── 行内容与排序 ──────────────────────────────────────────────


def test_all_missing_start_dates_falls_back_deterministically():
    """**全部**无任期时稳定取第一只（而非因空值比较而随机选中）。

    库内任期只对目标池回填，一个经理的所有关联基金都可能没回填。此时「任期最长」
    无从比较，返回任一只都是任意的 —— 但**必须可复现**（同一请求两次结果不同
    会让前端渲染跳动）。该行为由「取 rows[0]」这条明确规则锁住。
    """
    cid = _seed_company()
    _seed_manager('mh012', '全部无任期经理', cid)
    _seed_fund('6A0014', '无任期甲')
    _seed_fund('6A0015', '无任期乙')
    _link('mh012', '6A0014', start_date=None)
    _link('mh012', '6A0015', start_date=None)
    _seed_holding('6A0014', '600008', '甲基金持股', 5.0, 1)
    _seed_holding('6A0015', '600009', '乙基金持股', 5.0, 1)

    with closing(market_session_factory()()) as db:
        first = build_manager_holdings(db, 'mh012')
    with closing(market_session_factory()()) as db:
        second = build_manager_holdings(db, 'mh012')

    assert first['fund_code'] == second['fund_code']  # 可复现
    assert first['fund_code'] in ('6A0014', '6A0015')


def test_rows_sorted_by_rank_and_capped_at_top_n():
    """按 rank 升序，且受 top_n 截断。"""
    cid = _seed_company()
    _seed_manager('mh009', '排序经理', cid)
    _seed_fund('6A0011', '排序基金')
    _link('mh009', '6A0011', is_classic=True)

    for i in [5, 1, 3, 2, 4]:
        _seed_holding('6A0011', f'7100{i:02d}', f'第{i}名', 3.0, i)

    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh009')

    assert [r['rank'] for r in data['rows']] == [1, 2, 3, 4, 5]


def test_row_carries_code_name_ratio_and_market_value():
    """每行须带代码/名称/占净值比/市值，且 Decimal 已转 float。

    Decimal 直接进响应 dict 会让 Flask 序列化失败（与 watchlist_display 同因）。
    """
    cid = _seed_company()
    _seed_manager('mh010', '字段经理', cid)
    _seed_fund('6A0012', '字段基金')
    _link('mh010', '6A0012', is_classic=True)
    _seed_holding('6A0012', '600007', '腾讯控股', 5.5, 1, market_value=12345.67)

    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh010')

    row = data['rows'][0]
    assert row['stock_code'] == '600007'
    assert row['stock_name'] == '腾讯控股'
    assert isinstance(row['ratio'], float)
    assert row['ratio'] == 5.5
    assert isinstance(row['market_value'], float)


def test_total_ratio_is_sum_of_returned_rows():
    """合计占比 = 返回各行之和，给用户一个集中度锚点。"""
    cid = _seed_company()
    _seed_manager('mh011', '集中度经理', cid)
    _seed_fund('6A0013', '集中度基金')
    _link('mh011', '6A0013', is_classic=True)
    for i, r in enumerate([8.5, 7.25, 6.0], start=1):
        _seed_holding('6A0013', f'7200{i:02d}', f'股{i}', r, i)

    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh011')

    assert data['total_ratio'] == 21.75


def test_accepts_watchlist_symbol_and_uppercase_code():
    """与 ``manager-profile`` 同一口径：``MGR_<code>`` / 大写形态必须命中同一经理。

    归一前这些入参一律返回 ``None``（视同「经理不存在」），表现是详情页重仓区块整块空。
    """
    cid = _seed_company()
    _seed_manager('mh012', '形态经理', cid)
    _seed_fund('6A0014', '形态基金')
    _link('mh012', '6A0014', is_classic=True)
    _seed_holding('6A0014', '720001', '形态股', 9.9, 1)

    for raw in ('mh012', 'MH012', 'MGR_mh012', 'MGR_MH012'):
        with closing(market_session_factory()()) as db:
            data = build_manager_holdings(db, raw)
        assert data is not None, f'{raw!r} 应能命中 mh012（归一前会返回 None）'
        assert data['fund_code'] == '6A0014'


# ── 风格标签（#2044）：装配侧的诚实降级 ──────────────────────
#
# 本节只测**装配**（查库 → 指标 → 纯函数判据的接线）；档位边界语义在
# tests/services/test_manager_style.py，不在这里重复。
# 造数隔离纪律：测试库持久复用，股票代码一律用合成段（QA/QC/QB 前缀），
# 避免与真实指数成分、其他用例的成员关系互相污染。


def _seed_alloc(fund_code, industry_code, ratio, scheme='csrc', period='2026Q2'):
    """幂等写入一条行业配置（唯一键 fund+period+industry_code）。"""
    from app.domains.funds.models import FundIndustryAlloc

    with closing(market_session_factory()()) as db:
        exists = (
            db.query(FundIndustryAlloc)
            .filter(
                FundIndustryAlloc.fund_code == fund_code,
                FundIndustryAlloc.report_period == period,
                FundIndustryAlloc.industry_code == industry_code,
            )
            .first()
        )
        if exists is not None:
            exists.ratio = ratio
            db.commit()
            return
        db.add(
            FundIndustryAlloc(
                fund_code=fund_code,
                report_period=period,
                industry_code=industry_code,
                industry_name='行业名',
                scheme=scheme,
                ratio=ratio,
                source='eastmoney',
            )
        )
        db.commit()


def _seed_constituent(index_code, symbol, index_name='沪深300'):
    """幂等写入一条指数成分（唯一键 index_code+symbol）。"""
    from app.domains.indices.models import IndexConstituent

    with closing(market_session_factory()()) as db:
        exists = (
            db.query(IndexConstituent)
            .filter(
                IndexConstituent.index_code == index_code,
                IndexConstituent.symbol == symbol,
            )
            .first()
        )
        if exists is not None:
            return
        db.add(IndexConstituent(index_code=index_code, index_name=index_name, symbol=symbol))
        db.commit()


def test_style_labels_only_concentration_when_no_alloc_no_membership():
    """无行业配置、无指数成分 → 只出集中度标签（其余维度缺席，不是 null 占位）。

    3 只合成股均不在任何规模指数 → 覆盖率 0 → size 按 `min_coverage` 门拒判；
    无 csrc 行业配置 → industry 缺席。
    """
    cid = _seed_company()
    _seed_manager('mh201', '风格装配一', cid)
    _seed_fund('6S0001', '风格基金一')
    _link('mh201', '6S0001', is_classic=True, start_date=date(2020, 1, 1))
    _seed_holding('6S0001', 'QA0001', '合成甲', 8.5, 1)
    _seed_holding('6S0001', 'QA0002', '合成乙', 7.25, 2)
    _seed_holding('6S0001', 'QA0003', '合成丙', 6.0, 3)

    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh201')

    labels = data['style_labels']
    assert [lb['dim'] for lb in labels] == ['concentration']
    assert labels[0]['key'] == 'concentration_low'  # 21.75% < P50 门 50
    assert labels[0]['basis'] == '前十大重仓占净值 21.8%，全库 P50 以下'
    for lb in labels:
        assert not ({'color', 'colour', 'hex'} & set(lb)), '后端不返回颜色（硬约束）'


def test_style_labels_full_dims_with_csrc_only_and_membership():
    """行业只认 csrc（gics 更大值不得混入）、市值按 300 成分归属分桶。"""
    cid = _seed_company()
    _seed_manager('mh202', '风格装配二', cid)
    _seed_fund('6S0002', '风格基金二')
    _link('mh202', '6S0002', is_classic=True, start_date=date(2020, 1, 1))
    _seed_holding('6S0002', 'QC0001', '合成申', 8.5, 1)
    _seed_holding('6S0002', 'QC0002', '合成酉', 7.25, 2)
    _seed_holding('6S0002', 'QC0003', '合成戌', 6.0, 3)
    _seed_alloc('6S0002', 'C', 70.0, scheme='csrc')
    _seed_alloc('6S0002', 'D', 5.0, scheme='csrc')
    # 诱导值：gics 体系 95% —— 若跨体系混算会翻成 industry_high，正确应忽略
    _seed_alloc('6S0002', '35', 95.0, scheme='gics')
    # 300 成分覆盖前两只：覆盖率 (8.5+7.25)/21.75 = 72.4% ≥ 60 → 判定；
    # 已覆盖中 300 占比 100% ≥ 67.4 → 偏大盘
    _seed_constituent('000300', 'QC0001')
    _seed_constituent('000300', 'QC0002')

    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh202')

    labels = {lb['dim']: lb for lb in data['style_labels']}
    assert set(labels) == {'concentration', 'industry', 'size'}
    assert labels['industry']['key'] == 'industry_mid'  # 70 落在 [60,81)，gics 95 被忽略
    assert labels['industry']['basis'] == '第一大行业占比 70.0%，全库 P50–P80'
    assert labels['size']['key'] == 'size_large'
    assert labels['size']['basis'] == '沪深300 成分占已覆盖持仓 100.0%，全库 P75'


def test_style_labels_top10_basis_incomplete_returns_empty():
    """top10 口径不足 10 行（抓取不完整）→ 集中度回 None → 无任何标签。

    与标定样本的剔除规则同一口径（标定文档 §1）：4 行合计会系统性低估集中度，
    宁可缺席也不产出误导标签。
    """
    cid = _seed_company()
    _seed_manager('mh203', '风格装配三', cid)
    _seed_fund('6S0003', '风格基金三')
    _link('mh203', '6S0003', is_classic=True, start_date=date(2020, 1, 1))
    for i in range(1, 5):
        _seed_holding('6S0003', f'QB{i:04d}', f'季报股{i}', 9.0, i, basis='top10')

    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh203')

    assert data['basis'] == 'top10'
    assert len(data['rows']) == 4
    assert data['style_labels'] == []


def test_empty_contract_carries_style_labels_key():
    """空态契约同样带 style_labels: []——前端不需要分岔处理键是否存在。"""
    _seed_manager('mh204', '风格空态经理', _seed_company())
    with closing(market_session_factory()()) as db:
        data = build_manager_holdings(db, 'mh204')
    assert data['style_labels'] == []
