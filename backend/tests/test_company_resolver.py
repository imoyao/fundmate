# -*- coding: utf-8 -*-
# backend/tests/test_company_resolver.py
"""company_resolver 与 Job 层 code 回填单元测试（#1168 P1）。

为什么这样测：
- 解析/匹配逻辑是纯函数，可离线验证，不依赖网络；
- 网络抓取（jjjz_gs.js）用 FakeResponse mock，避免测试真发请求；
- Job 层只验证"创建公司时优先用真值 code/东财简称"，逻辑已被 resolve_company_identity
  覆盖，故 job 单测聚焦"落库后的 code/name 字段"而非重复测匹配。

2026-09-10 扩充：`fund_companies` 主数据匹配（归一化名 + 业务族）与唯一写入口
`get_or_create_fund_company` 的防重复行为——历史上正是「四个 job 各写一份查名建行」
导致同一公司长出简称/全称两行、经理归属被分裂。同日续查「名称形态是否会来回写」
（用户质疑）后追加：族感知解析（防同名券商资管串码）、新建行写简称、存量行不改名、
回填顺带简称化四组断言。
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
    company_resolver.reset_cache()
    assert get_company_code_by_name('朱雀基金管理有限公司') == '80560407'
    company_resolver.reset_cache()
    assert get_company_code_by_name('朱雀基金') == '80560407'
    company_resolver.reset_cache()
    assert get_company_code_by_name('根本不存在的基金公司') is None


def test_job_uses_real_code(db, monkeypatch):
    """FundDetailEnrichJob 创建公司时，code 应为真值 code 而非名称占位。"""
    # 唯一写入口 get_or_create_fund_company 内部引用 company_resolver 的全局函数，
    # 故 patch 该模块属性（job 模块已不再直接持有该符号）
    monkeypatch.setattr(company_resolver, 'resolve_company_identity', lambda name: ('80560407', None))
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
    company_resolver.reset_cache()
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
    company_resolver.reset_cache()
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
    company_resolver.reset_cache()
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
    company_resolver.reset_cache()
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


# ─────────── 基金公司主数据匹配（2026-09-10）───────────


def test_normalize_company_name_collapses_short_and_full_forms():
    """简称/全称/属地括注三种写法归一化到同一匹配键。"""
    n = company_resolver.normalize_company_name
    assert n('招商基金') == n('招商基金管理有限公司') == '招商'
    assert n('富达基金(中国)') == n('富达基金管理（中国）有限公司') == '富达'
    assert n('银华基金管理股份有限公司') == '银华'
    assert n('') == ''
    assert n(None) == ''


def test_company_index_key_separates_business_family():
    """业务族进匹配键：基金管理人不会与同名券商/资管互相命中。

    实测风险：后缀归一化会把「招商基金管理有限公司」和「招商证券资产管理有限公司」
    同时收敛到 `招商`——若不区分业务族，AMAC 回填会把官网/客服电话写到券商资管行上。
    """
    key = company_resolver.company_index_key
    assert key('招商基金') == key('招商基金管理有限公司')
    assert key('招商基金') != key('招商证券资产管理有限公司')
    assert key('财通基金管理有限公司') != key('财通证券资产管理有限公司')


def test_pick_canonical_prefers_short_name_over_higher_refs():
    """规范行按列语义取简称行，而不是引用数更多的全称行。

    实测 8 组重复的两行引用恰好互补（全称行持 funds 引用、简称行持 managers 引用），
    按引用数会在招商那组选成全称行（123 > 103），最终 name 里留着全称、简称丢失。
    """
    rows = [(41, '招商基金管理有限公司', 123), (176, '招商基金', 103)]
    assert company_resolver.pick_canonical_company(rows)[0] == 176
    # 同为简称形态时才看引用数
    assert company_resolver.pick_canonical_company([(1, '华安基金', 3), (2, '华安基金', 9)])[0] == 2
    assert company_resolver.looks_like_full_name('招商基金管理有限公司') is True
    assert company_resolver.looks_like_full_name('招商基金') is False


def test_build_index_and_match_by_normalized_name(db):
    """索引按归一化名命中：全称入参可查到库内简称行。"""
    db.add(FundCompany(code='80000228', name='华安基金'))
    db.commit()
    index = company_resolver.build_fund_company_index(db)
    assert company_resolver.match_fund_company(index, '华安基金管理有限公司').name == '华安基金'
    assert company_resolver.match_fund_company(index, '根本不存在的公司') is None


def test_get_or_create_matches_full_name_to_existing_short_row(db, monkeypatch):
    """全称入参命中既有简称行，不新建第二行（八组重复的根因回归）。"""
    monkeypatch.setattr(company_resolver, 'resolve_company_identity', lambda name: ('80036782', None))
    db.add(FundCompany(code='80036782', name='招商基金'))
    db.commit()
    cid = company_resolver.get_or_create_fund_company(db, '招商基金管理有限公司')
    assert db.query(FundCompany).count() == 1
    assert cid == db.query(FundCompany).filter_by(name='招商基金').one().id


def test_get_or_create_does_not_cross_business_family(db, monkeypatch):
    """跨业务族不得复用：券商资管不并入同名基金公司。"""
    monkeypatch.setattr(company_resolver, 'resolve_company_identity', lambda name: (None, None))
    db.add(FundCompany(code='80036782', name='招商基金'))
    db.commit()
    cid = company_resolver.get_or_create_fund_company(db, '招商证券资产管理有限公司')
    assert db.query(FundCompany).count() == 2
    assert db.query(FundCompany).filter_by(id=cid).one().name == '招商证券资产管理有限公司'


def test_get_or_create_reuses_row_by_code(db, monkeypatch):
    """权威 code 已被同机构变体行占用时复用该行，避免 unique(code) 冲突。"""
    monkeypatch.setattr(company_resolver, 'resolve_company_identity', lambda name: ('80000235', None))
    db.add(FundCompany(code='80000235', name='银华基金'))
    db.commit()
    cid = company_resolver.get_or_create_fund_company(db, '银华基金管理股份有限公司')
    assert db.query(FundCompany).count() == 1
    assert cid == db.query(FundCompany).filter_by(name='银华基金').one().id


def test_get_or_create_placeholder_code_not_duplicated(db, monkeypatch):
    """占位 code=name 跨批次重复调用只建一行（幂等）。"""
    monkeypatch.setattr(company_resolver, 'resolve_company_identity', lambda name: (None, None))
    first = company_resolver.get_or_create_fund_company(db, '某冷门基金公司')
    second = company_resolver.get_or_create_fund_company(db, '某冷门基金公司')
    assert first == second
    assert db.query(FundCompany).count() == 1


def test_get_or_create_uses_cache(db, monkeypatch):
    """传入 cache 时复用结果，不重复建行。"""
    monkeypatch.setattr(company_resolver, 'resolve_company_identity', lambda name: (None, None))
    cache = {}
    cid = company_resolver.get_or_create_fund_company(db, '缓存基金', cache=cache)
    assert cache == {'缓存基金': cid}
    assert company_resolver.get_or_create_fund_company(db, '缓存基金', cache=cache) == cid
    assert db.query(FundCompany).count() == 1


# ─────────── 名称形态与业务族解析（2026-09-10 加固）───────────

# 东财 jjjz_gs.js 实测片段：券商资管与同名基金公司并存，且归一化后同键
_EM_WITH_BROKER = [
    {'code': '80036782', 'name': '招商基金'},
    {'code': '80431710', 'name': '招商证券资管'},
    {'code': '80048752', 'name': '中银基金'},
    {'code': '80000200', 'name': '中银证券'},
]


def _mock_em(monkeypatch, items):
    monkeypatch.setattr(company_resolver, 'fetch_fund_company_list', lambda: items)
    company_resolver.reset_cache()


def test_resolve_identity_is_family_aware(monkeypatch):
    """同名基金公司与券商资管不得互相取到对方的 code（族盲索引会串码）。

    实测复现：`招商` / `中银` 两个归一化键下各有基金公司与券商两条，族盲缓存按
    「先见先得」落键，`招商证券资产管理有限公司` 会拿到招商基金的 code（或反之），
    把 A 公司官网/客服电话写到 B 公司上——最难发现的一类数据腐蚀。
    """
    _mock_em(monkeypatch, _EM_WITH_BROKER)
    # 精确名快路径
    assert company_resolver.resolve_company_identity('招商基金') == ('80036782', '招商基金')
    # 归一化 + 业务族：基金入参归到基金行，券商入参归到券商行
    assert company_resolver.resolve_company_identity('招商基金管理有限公司') == ('80036782', '招商基金')
    assert company_resolver.resolve_company_identity('招商证券资产管理有限公司') == ('80431710', '招商证券资管')
    assert company_resolver.resolve_company_identity('中银国际证券股份有限公司') == ('80000200', '中银证券')
    assert company_resolver.resolve_company_identity('中银基金管理有限公司') == ('80048752', '中银基金')
    assert company_resolver.resolve_company_identity('查无此公司') == (None, None)


def test_resolve_identity_manual_mapping_tolerates_suffix_form(monkeypatch):
    """手动映射按归一化名兜底：品牌词不一致时，「有限公司/股份有限公司」两种写法都能命中。"""
    _mock_em(monkeypatch, [{'code': '80091787', 'name': '浦银基金'}])
    assert company_resolver.resolve_company_identity('浦银安盛基金管理有限公司') == ('80091787', '浦银基金')
    # 东财列表里没有中邮创业的条目（东财叫「中邮基金」），只能靠手动映射
    assert company_resolver.resolve_company_identity('中邮创业基金管理股份有限公司') == ('80075936', '中邮基金')
    # 简称与法人后缀两种写法都命中不了普通公司时返回空
    assert company_resolver.resolve_company_identity('') == (None, None)


def test_get_or_create_writes_eastmoney_short_name(db, monkeypatch):
    """akshare 给法人全称时，新建行的 `name` 写东财简称（列语义是简称）。

    若不如此，该行 `name` 会永久停在法人全称——同步路径从不改存量行，没有第二处纠正它。
    """
    monkeypatch.setattr(company_resolver, 'resolve_company_identity', lambda name: ('80560407', '朱雀基金'))
    cid = company_resolver.get_or_create_fund_company(db, '朱雀基金管理有限公司')
    row = db.query(FundCompany).filter_by(id=cid).one()
    assert row.name == '朱雀基金'
    assert row.code == '80560407'


def test_get_or_create_does_not_rename_existing_row(db, monkeypatch):
    """既有行不被改名：同步路径只写新建行，否则抓取与修复会来回改写同一列。

    这是「简称被下一次抓取覆写成全称」担忧的反向保护，也是防数据来回写的核心断言。
    """
    monkeypatch.setattr(company_resolver, 'resolve_company_identity', lambda name: ('80036782', '某别的简称'))
    db.add(FundCompany(code='80036782', name='招商基金'))
    db.commit()
    cid = company_resolver.get_or_create_fund_company(db, '招商基金管理有限公司')
    row = db.query(FundCompany).filter_by(id=cid).one()
    assert row.name == '招商基金'  # 未被 '某别的简称' 覆写
    assert db.query(FundCompany).count() == 1


def test_backfill_shortens_full_name(db, monkeypatch):
    """占位回填顺带把 `name` 由法人全称收敛为东财简称（与迁移脚本阶段 4 同一权威来源）。"""
    monkeypatch.setattr(company_resolver, 'resolve_company_identity', lambda name: ('80075936', '中邮基金'))
    db.add(FundCompany(code='中邮创业基金管理股份有限公司', name='中邮创业基金管理股份有限公司'))
    db.commit()
    res = company_resolver.backfill_fund_company_codes(db, dry_run=True)
    assert res['matched'][0]['new_code'] == '80075936'
    assert res['matched'][0]['new_name'] == '中邮基金'
    # dry_run 不落库
    assert db.query(FundCompany).one().name == '中邮创业基金管理股份有限公司'

    company_resolver.backfill_fund_company_codes(db, dry_run=False)
    row = db.query(FundCompany).one()
    assert (row.code, row.name) == ('80075936', '中邮基金')


def test_backfill_keeps_name_when_already_short(db, monkeypatch):
    """已是简称形态的行不被回填改动（幂等：第二次跑没有可改的东西）。"""
    monkeypatch.setattr(company_resolver, 'resolve_company_identity', lambda name: ('80000235', '银华基金'))
    db.add(FundCompany(code='银华基金', name='银华基金'))
    db.commit()
    company_resolver.backfill_fund_company_codes(db, dry_run=False)
    row = db.query(FundCompany).one()
    assert (row.code, row.name) == ('80000235', '银华基金')
