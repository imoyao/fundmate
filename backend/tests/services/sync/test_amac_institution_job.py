# -*- coding: utf-8 -*-
"""AMAC 销售机构同步 job 的常用机构策展逻辑测试（#1081）。

策展语义（设计文档 sales-institution-common-group-2026-08-24.md §4）：
- 命中 CURATED_INSTITUTIONS 的行覆写 is_common/common_sort/display_name
  （代码即 source of truth，保证本地/生产/灾备重建各环境收敛）；
- 未命中行不触碰这三个字段（display_name 维持「仅首次写入」既有语义）。

2026-09-10 扩充：基金管理人（house）不再落独立表，而是 **enrich 进 fund_companies**
（公司主数据唯一表）——全称写 full_name、地址/官网/电话入列，且**不新建公司行**。
"""

from loguru import logger

from app.domains.funds.models import FundCompany
from app.domains.positions.models import SalesInstitution
from app.services.sync.jobs.amac_institution_job import CURATED_INSTITUTIONS, AmacInstitutionJob


def _make_job(db):
    """绕过 __init__（免 adapter/抓取依赖），仅注入 _upsert_* 所需状态。"""
    job = AmacInstitutionJob.__new__(AmacInstitutionJob)
    job.db = db
    job.logger = logger
    job.stats = {'success': 0, 'skipped': 0}
    job._pre_run()
    return job


def _house_item(house_name: str, **extra) -> dict:
    item = {'kind': 'house', 'houseName': house_name}
    item.update(extra)
    return item


def _sales_item(org_name: str, org_type: str = '独立基金销售机构') -> dict:
    return {'kind': 'sales', 'orgName': org_name, 'orgType': org_type}


def test_upsert_new_curated_row(db):
    """新机构命中策展表：is_common/common_sort/display_name 三件套落库。"""
    job = _make_job(db)
    job._save_data([_sales_item('蚂蚁（杭州）基金销售有限公司')])
    row = db.query(SalesInstitution).filter_by(org_name='蚂蚁（杭州）基金销售有限公司').one()
    assert row.is_common is True
    assert row.common_sort == 1
    assert row.display_name == '支付宝'


def test_upsert_new_non_curated_row_defaults(db):
    """未命中策展表的新机构：默认值，不误标常用。"""
    job = _make_job(db)
    job._save_data([_sales_item('某无名机构')])
    row = db.query(SalesInstitution).filter_by(org_name='某无名机构').one()
    assert row.is_common is False
    assert row.common_sort is None
    assert row.display_name is None


def test_curated_overwrites_existing_row(db):
    """已存在行命中策展表：覆写三件套（代码即 source of truth，保证多环境收敛）。"""
    job = _make_job(db)
    db.add(SalesInstitution(org_name='蚂蚁（杭州）基金销售有限公司', display_name='旧别名', is_common=False))
    db.commit()
    job._save_data([_sales_item('蚂蚁（杭州）基金销售有限公司')])
    row = db.query(SalesInstitution).filter_by(org_name='蚂蚁（杭州）基金销售有限公司').one()
    assert row.is_common is True
    assert row.common_sort == 1
    assert row.display_name == '支付宝'


def test_non_curated_existing_row_display_name_preserved(db):
    """未命中策展表的已存在行：display_name 维持「仅首次写入」语义不被清掉。"""
    job = _make_job(db)
    db.add(SalesInstitution(org_name='某无名机构', display_name='用户别名'))
    db.commit()
    job._save_data([_sales_item('某无名机构')])
    row = db.query(SalesInstitution).filter_by(org_name='某无名机构').one()
    assert row.display_name == '用户别名'
    assert row.is_common is False


def test_curation_idempotent(db):
    """重复同步结果一致（幂等），不产生重复行。"""
    job = _make_job(db)
    item = _sales_item('北京雪球基金销售有限公司')
    job._save_data([item])
    job._save_data([item])
    rows = db.query(SalesInstitution).filter_by(org_name='北京雪球基金销售有限公司').all()
    assert len(rows) == 1
    assert rows[0].is_common is True
    assert rows[0].common_sort == 36
    assert rows[0].display_name == '雪球基金'


def test_curated_registry_has_15_entries():
    """策展名单 15 家（中基协 Top10 + 5 互联网平台），防误删/误增。"""
    assert len(CURATED_INSTITUTIONS) == 15


def test_pinyin_short_computed(db):
    """拼音简拼派生列：汉字取首字母大写、英文数字保留（供前端检索过滤，#1081）。"""
    job = _make_job(db)
    job._save_data(
        [
            _sales_item('华泰证券', org_type='证券公司'),
            _sales_item('北京雪球基金销售有限公司'),
        ]
    )
    ht = db.query(SalesInstitution).filter_by(org_name='华泰证券').one()
    assert ht.pinyin_short == 'HTZQ'
    xq = db.query(SalesInstitution).filter_by(org_name='北京雪球基金销售有限公司').one()
    assert xq.pinyin_short == 'BJXQJJXSYXGS'


# ─────────── 基金管理人回填 fund_companies（2026-09-10）───────────


def test_upsert_house_enriches_fund_company(db):
    """AMAC 全称落 full_name，地址/官网/电话入列；不新建公司行。"""
    db.add(FundCompany(code='80000228', name='华安基金'))
    db.commit()
    job = _make_job(db)
    job._save_data(
        [
            _house_item(
                '华安基金管理有限公司',
                registerAddr='上海市',
                officeAddr='上海市浦东新区',
                website='www.huaan.com.cn',
                phone='400-885-0099',
            )
        ]
    )
    row = db.query(FundCompany).filter_by(name='华安基金').one()
    assert row.full_name == '华安基金管理有限公司'
    assert row.register_addr == '上海市'
    assert row.office_addr == '上海市浦东新区'
    assert row.website == 'www.huaan.com.cn'
    assert row.phone == '400-885-0099'
    assert row.is_active is True
    assert db.query(FundCompany).count() == 1  # 未新建行


def test_upsert_house_does_not_overwrite_short_name(db):
    """`name` 属东财链路写权，AMAC 不得改动（单一写者原则）。"""
    db.add(FundCompany(code='80036782', name='招商基金'))
    db.commit()
    job = _make_job(db)
    job._save_data([_house_item('招商基金管理有限公司')])
    row = db.query(FundCompany).filter_by(code='80036782').one()
    assert row.name == '招商基金'
    assert row.full_name == '招商基金管理有限公司'


def test_upsert_house_unmatched_not_created(db):
    """AMAC 有、主数据没有的管理人：只累计告警，不新建行（AMAC 不提供东财编码）。"""
    db.add(FundCompany(code='80000228', name='华安基金'))
    db.commit()
    job = _make_job(db)
    job._save_data([_house_item('施罗德基金管理（中国）有限公司')])
    assert db.query(FundCompany).count() == 1
    assert job._unmatched_houses == ['施罗德基金管理（中国）有限公司']
    assert job.stats['skipped'] == 1


def test_upsert_house_does_not_cross_business_family(db):
    """同归一化键但业务族不同（券商资管）不得被回填覆盖。"""
    db.add(FundCompany(code='80036782', name='招商基金'))
    db.add(FundCompany(code='80408086', name='招商证券资产管理有限公司'))
    db.commit()
    job = _make_job(db)
    job._save_data([_house_item('招商基金管理有限公司', website='www.cmfchina.com')])
    assert db.query(FundCompany).filter_by(name='招商基金').one().website == 'www.cmfchina.com'
    assert db.query(FundCompany).filter_by(name='招商证券资产管理有限公司').one().website is None


def test_post_run_deactivation_scoped_to_amac_managed_companies(db):
    """is_active 失效只作用于「曾被 AMAC 认领」的行（full_name 非空），不误伤东财行。"""
    db.add(SalesInstitution(org_name='某销售机构'))
    db.add(FundCompany(code='80000228', name='华安基金', full_name='华安基金管理有限公司'))
    db.add(FundCompany(code='80408086', name='招商证券资产管理有限公司'))  # 从未被 AMAC 认领
    db.commit()
    job = _make_job(db)
    job._seen_org_names = {'某销售机构'}
    job._seen_house_names = set()  # 本次 AMAC 名单为空 → 已认领行应失效
    job._post_run()
    assert db.query(FundCompany).filter_by(name='华安基金').one().is_active is False
    assert db.query(FundCompany).filter_by(name='招商证券资产管理有限公司').one().is_active is True
