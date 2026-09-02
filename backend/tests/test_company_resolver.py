# -*- coding: utf-8 -*-
# backend/tests/test_company_resolver.py
"""company_resolver 与 Job 层 code 回填单元测试（#1168 P1）。

为什么这样测：
- 解析/匹配逻辑是纯函数，可离线验证，不依赖网络；
- 网络抓取（jjjz_gs.js）用 FakeResponse mock，避免测试真发请求；
- Job 层只验证"创建公司时优先用真值 code"，逻辑已被 get_company_code_by_name
  覆盖，故 job 单测聚焦"落库后的 code 字段"而非重复测匹配。
"""

import importlib

import app.core.config as config_mod
import app.services.sync.company_resolver as company_resolver
from app.domains.funds.models import FundCompany
from app.services.sync.company_resolver import (
    backfill_fund_company_codes,
    fetch_fund_company_list,
    get_company_code_by_name,
)
from app.services.sync.jobs.fund_detail_enrich_job import FundDetailEnrichJob


class FakeResponse:
    """最小 requests.Response 替身：支持 .encoding 赋值与 .text 读取。"""

    def __init__(self, text: str):
        self.encoding = None
        self.text = text


def test_parse_jjjz_gs(monkeypatch):
    """解析 jjjz_gs.js 的 op 数组，提取 [code, name]。"""
    html = 'var gs={op:[["80163340","安信基金"],["81608035","安联基金"]]}'
    monkeypatch.setattr(company_resolver.requests, 'get', lambda *a, **k: FakeResponse(html))
    result = fetch_fund_company_list()
    assert len(result) == 2
    assert result[0] == {'code': '80163340', 'name': '安信基金'}
    assert result[1] == {'code': '81608035', 'name': '安联基金'}


def test_normalize_and_match(monkeypatch):
    """全称经归一化可命中简称 code；简称精确命中；不存在返回 None。"""
    monkeypatch.setattr(
        company_resolver,
        'fetch_fund_company_list',
        lambda: [{'code': '80560407', 'name': '朱雀基金'}],
    )
    # 每次调用前清空模块级缓存，确保重新拉取（mock）列表
    company_resolver._cache = None
    assert get_company_code_by_name('朱雀基金管理有限公司') == '80560407'
    company_resolver._cache = None
    assert get_company_code_by_name('朱雀基金') == '80560407'
    company_resolver._cache = None
    assert get_company_code_by_name('根本不存在的基金公司') is None


def test_job_uses_real_code(db, monkeypatch):
    """FundDetailEnrichJob 创建公司时，code 应为真值 code 而非名称占位。"""
    monkeypatch.setattr(
        'app.services.sync.jobs.fund_detail_enrich_job.get_company_code_by_name',
        lambda name: '80560407',
    )
    job = FundDetailEnrichJob(None, None, db)
    cid = job._get_or_create_company('某基金公司全称')
    inst = db.query(FundCompany).filter_by(id=cid).first()
    assert inst is not None
    assert inst.code == '80560407'
    assert inst.name == '某基金公司全称'


def test_config_default(monkeypatch):
    """未配置 SYNC__FUND_LIST_SOURCE 时，默认 'eastmoney'。"""
    monkeypatch.delenv('SYNC__FUND_LIST_SOURCE', raising=False)
    importlib.reload(config_mod)
    assert config_mod.SYNC__FUND_LIST_SOURCE == 'eastmoney'


def test_backfill_iterative_normalization_hits(db, monkeypatch):
    """「基金管理股份有限公司」经迭代归一化剥离到品牌词，命中简称 code（#1199）。"""
    monkeypatch.setattr(
        company_resolver,
        'fetch_fund_company_list',
        lambda: [{'code': '80000221', 'name': '银华基金'}],
    )
    company_resolver._cache = None
    db.add(FundCompany(code='银华基金管理股份有限公司', name='银华基金管理股份有限公司'))
    db.commit()
    res = backfill_fund_company_codes(db, dry_run=True)
    assert res['total_placeholders'] == 1
    assert len(res['matched']) == 1
    assert res['matched'][0]['new_code'] == '80000221'
    assert len(res['unmatched']) == 0


def test_backfill_paren_suffix_normalization(db, monkeypatch):
    """「(中国)」属地括号被去除后，摩根士丹利基金管理(中国) 命中摩根士丹利基金。"""
    monkeypatch.setattr(
        company_resolver,
        'fetch_fund_company_list',
        lambda: [{'code': '80560407', 'name': '摩根士丹利基金'}],
    )
    company_resolver._cache = None
    db.add(FundCompany(code='摩根士丹利基金管理(中国)有限公司', name='摩根士丹利基金管理(中国)有限公司'))
    db.commit()
    res = backfill_fund_company_codes(db, dry_run=True)
    assert len(res['matched']) == 1
    assert res['matched'][0]['new_code'] == '80560407'


def test_backfill_code_conflict_goes_unmatched(db, monkeypatch):
    """真值 code 已被占用时，占位行进入 unmatched 而非误写（避免唯一约束冲突）。"""
    monkeypatch.setattr(
        company_resolver,
        'fetch_fund_company_list',
        lambda: [{'code': '80431710', 'name': '国都证券'}],
    )
    company_resolver._cache = None
    # 一行已是真值 code，一行同名占位
    db.add(FundCompany(code='80431710', name='国都证券'))
    db.add(FundCompany(code='招商证券资产管理有限公司', name='招商证券资产管理有限公司'))
    db.commit()
    res = backfill_fund_company_codes(db, dry_run=True)
    assert res['total_placeholders'] == 1
    assert len(res['matched']) == 0
    assert len(res['unmatched']) == 1
    assert res['unmatched'][0]['name'] == '招商证券资产管理有限公司'


def test_manual_mapping():
    """手动映射 _MANUAL_MAPPING 优先于缓存命中。"""
    # 清空缓存，确保不依赖网络/缓存
    company_resolver._cache = None
    # 国泰海通：东财简称"国泰海通资管"，无法通过后缀归一化匹配全称
    assert (
        company_resolver.get_company_code_by_name(
            '上海国泰海通证券资产管理有限公司',
        )
        == '80156175'
    )
    # 浙商证券：东财简称"浙商证券资管"
    assert (
        company_resolver.get_company_code_by_name(
            '浙江浙商证券资产管理有限公司',
        )
        == '80403111'
    )
    # 前海联合：东财简称"前海联合"
    assert (
        company_resolver.get_company_code_by_name(
            '新疆前海联合基金管理有限公司',
        )
        == '80468996'
    )
    # 人保资产：东财简称"人保资产"
    assert (
        company_resolver.get_company_code_by_name(
            '中国人保资产管理有限公司',
        )
        == '80061431'
    )
    # 财通证券：东财简称"财通资管"
    assert (
        company_resolver.get_company_code_by_name(
            '财通证券资产管理有限公司',
        )
        == '80404701'
    )
    # 未在手动映射中的公司应返回 None（不依赖网络）
    assert company_resolver.get_company_code_by_name('不存在的公司') is None
