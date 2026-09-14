# -*- coding: utf-8 -*-
# app/services/sync/company_resolver.py
"""
基金公司名称/code 解析与回填（#1168 P1，2026-09-10 扩展为主数据匹配枢纽）。

数据源：天天基金基金公司列表 http://fund.eastmoney.com/js/jjjz_gs.js
实测返回：var gs={op:[["80163340","安信基金"],["81608035","安联基金"],...]}
即 [code(8位), name(简称)] 数组。

为什么单独成模块：akshare 全链路只给公司"名"不给"code"，导致 fund_companies
表大量 code==name 占位。本模块集中负责"名 →（真值 code, 东财简称）"的解析，
供各 Job 与 backfill 脚本复用，避免逻辑散落。简称同样必要：`FundCompany.name`
的列语义是简称，而 akshare 给的是法人全称，只解析 code 会让 name 永久停在错误形态。

名称匹配难点：akshare 的 基金管理人 是全称（"易方达基金管理有限公司"），而
jjjz_gs.js 是简称（"易方达基金"），精确匹配会大量失配。故先做后缀归一化再匹配；
仍未命中则查手动映射 _MANUAL_MAPPING；最后保留 code=name 占位并打 warning
（设计文档明确接受的回退）。

2026-09-10 起本模块同时是**跨来源公司主体匹配的唯一实现**：
`normalize_company_name` / `build_fund_company_index` / `match_fund_company`
三件套供 AMAC 名录回填（`amac_institution_job`）与历史数据合并
（`scripts/migrate_fund_company_merge.py`）共用。命名与业务族判定规则见各函数
docstring——同一实体只允许一处匹配逻辑，避免两份实现漂移。

手动映射适用场景：东财 jjjz_gs.js 使用简称（如"国泰海通资管"），与
fund_companies 全称（"上海国泰海通证券资产管理有限公司"）无法通过后缀
归一化匹配。已实测确认可映射的公司列入 _MANUAL_MAPPING。
"""

import json
import re
from typing import Dict, List, Optional, Sequence

import requests
from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.funds.models import FundCompany

_EASTMONEY_COMPANY_URL = 'http://fund.eastmoney.com/js/jjjz_gs.js'
# 归一化时剥除的常见法人主体后缀（只剥一层最长的匹配）
_COMPANY_SUFFIXES = (
    '基金管理有限公司',
    '基金管理公司',
    '资产管理有限公司',
    '资产管理公司',
    '基金管理',
    '资产管理',
    '有限公司',
    '有限责任公司',
    '股份有限公司',
    '基金',
    '资管',
    '证券',
)

# 东财列表加载后构建的两个索引（一次抓取；`_cache` 兼作「已加载」哨兵）：
#   `_cache`        ：{东财原文名(=简称): code}——精确名快路径，无歧义
#   `_family_index` ：{(归一化名, 业务族): (code, 简称)}——族感知，跨形态/跨来源解析用
# 为什么归一化键必须带业务族：东财 jjjz_gs.js 本身也含券商资管（招商证券资管 / 中银证券 /
# 东方红资产管理…），它们与被同名基金公司归一化后同键（`招商` / `中银`）。族盲索引按
# 先见先得，会让两者取到**对方的** code（2026-09-10 实测：`招商` 键落在招商证券资管上）。
_cache: Optional[Dict[str, str]] = None
_family_index: Optional[Dict[tuple, tuple]] = None

# 手动映射：东财简称与法人全称的**品牌词不一致**（后缀归一化无法收敛，不是形态差异），
# 或东财名录里压根没有该主体。值为 (code, 东财简称)——简称用于写 `name` 列（列语义是简称），
# 只给 code 会让该行的 `name` 永远停在法人全称。
_MANUAL_MAPPING: Dict[str, tuple] = {
    '上海国泰海通证券资产管理有限公司': ('80156175', '国泰海通资管'),
    '浙江浙商证券资产管理有限公司': ('80403111', '浙商证券资管'),
    '新疆前海联合基金管理有限公司': ('80468996', '前海联合'),
    '中国人保资产管理有限公司': ('80061431', '人保资产'),
    '财通证券资产管理有限公司': ('80404701', '财通资管'),
    # 品牌词不一致：东财登记为「中邮基金」「浦银基金」，法人全称核心词是「中邮创业」「浦银安盛」
    '中邮创业基金管理股份有限公司': ('80075936', '中邮基金'),
    '浦银安盛基金管理有限公司': ('80091787', '浦银基金'),
    # 东财把「上海东方证券资产管理」（东方红）登记为「东方红资产管理」
    '上海东方证券资产管理有限公司': ('80145102', '东方红资产管理'),
    # 东财把「中银国际证券」登记为「中银证券」（归一化后前者为「中银国际」、后者为「中银」，无法收敛）
    '中银国际证券股份有限公司': ('80000200', '中银证券'),
}

# 手动映射的「归一化名」索引（惰性构建）：兼容「有限公司 / 股份有限公司」等法人后缀写法差异。
_MANUAL_INDEX: Optional[Dict[str, tuple]] = None


def normalize_company_name(name: str) -> str:
    """剥除常见法人主体后缀，保留品牌核心词用于匹配（**全仓唯一实现**）。

    采用迭代剥离：单次剥离会把「股份有限公司」+「证券」这类组合后缀拆成多级，
    必须反复剥到不再变化（如「银华基金管理股份有限公司」→「银华基金」→「银华」），
    才能与天天基金列表简称（「银华基金」归一化后为「银华」）对齐。同时去掉
    「(中国)」这类属地括号，避免其阻断后缀剥离（#1199 实测失配样本归因）。

    跨来源同主体识别的公共入口：`company_resolver`（东财 code 解析）、
    `amac_institution_job`（AMAC 名录 enrich 回填）、`migrate_fund_company_merge`
    （历史数据合并）三处共用，**不要再写第二份**——两处实现必然漂移
    （2026-09-10 展示名解析链两次实现导致首页/列表页不一致的同类教训）。

    注意：归一化结果是**匹配键**，不是展示名，禁止入库或下发前端。
    """
    if not name:
        return ''
    n = name.strip()
    # 去掉法人属地括号，如「(中国)」「（中国）」
    n = re.sub(r'[（(][^（）()]*[）)]', '', n)
    changed = True
    while changed:
        changed = False
        # 每轮选最长的可剥后缀，避免「有限公司」先于「股份有限公司」被误剥
        # （如「银华基金管理股份有限公司」应剥「股份有限公司」而非「有限公司」）
        best = None
        for suffix in _COMPANY_SUFFIXES:
            if n.endswith(suffix) and len(n) > len(suffix):
                if best is None or len(suffix) > len(best):
                    best = suffix
        if best:
            n = n[: -len(best)]
            changed = True
    return n


# 兼容旧私有名（本模块内部历史调用点），新代码一律用公开名。
_normalize_company_name = normalize_company_name


def company_business_family(name: str) -> str:
    """业务族标记：区分「基金管理人」与「券商/资管系」。

    必要性（2026-09-10 实测）：后缀归一化会把「招商证券资产管理有限公司」与
    「招商基金管理有限公司」**同时**收敛到键 `招商`。若不区分业务族，
    AMAC 的「招商基金管理有限公司」可能被回填到券商资管那行（反之亦然）——
    这类错配会让「公司官网/客服电话」张冠李戴，且因为同名不易被察觉。
    """
    return 'fund' if '基金' in (name or '') else 'other'


# 兼容旧私有名，新代码一律用公开名。
_business_family = company_business_family


_FULL_NAME_SUFFIXES = ('股份有限公司', '有限责任公司', '有限公司', '公司')


def looks_like_full_name(name: str) -> bool:
    """是否「法人全称」形态（以公司后缀结尾）。

    `fund_companies.name` 的列语义是**简称**（全称归 `full_name`），所以形态判断
    是择规范行的第一准则，而不是引用数——2026-09-10 实测 8 组重复里两行的引用
    分布恰好互补（全称行持 funds 引用、简称行持 managers 引用，是 fund_list_job 与
    fund_manager_job 两个来源名形态不同造成的），按引用数合并会在「招商」那组
    算错方向（全称行 114 funds + 9 managers 反而多过简称行 103 managers），
    把规范行选成全称行，最终 `name` 里留着全称、简称丢失。
    """
    return bool(name) and name.endswith(_FULL_NAME_SUFFIXES)


def canonical_company_order(row_id: int, name: str, ref_count: int) -> tuple:
    """重复实体的「规范行」排序键（升序取第一个）。

    规则：
    1. **形态**：已是简称者优先（`name` 列语义是简称，全称属于 `full_name`）——
       这条是主准则，见 `looks_like_full_name` 的实测说明；
    2. **被引用多者优先**（`ref_count` = 挂在行下的经理数 + 基金数）——
       同形态时说明哪一行在真正被使用；
    3. id 小者（兜底，保证同输入同输出）。

    实测 8 组重复的简称行同时持有东财权威 code（`jjjz_gs.js` 逐行校验），与本规则一致。
    """
    return (1 if looks_like_full_name(name) else 0, -ref_count, row_id)


def pick_canonical_company(rows: Sequence[tuple]) -> tuple:
    """从 `[(id, name, ref_count), ...]` 里选出规范行（纯函数，job 与迁移脚本共用）。

    纯函数的原因：同一规则若在同步任务与迁移脚本里各写一份，必然漂移（本仓
    2026-09-10 已因「展示名解析两份实现」踩过一次同类坑）。
    """
    return sorted(rows, key=lambda r: canonical_company_order(*r))[0]


def build_fund_company_index(db: Session) -> Dict[tuple, FundCompany]:
    """构建「归一化名 → FundCompany 行」索引，供跨来源批量 matching。

    同一个归一化键命中多行 = `fund_companies` 内部有重复实体（2026-09-10 实测 8 组，
    简称/全称各一行；招商基金的经理甚至分裂在两行 103 + 9）。索引**不改数据**，
    只按 `pick_canonical_company` 确定性择一并告警，把重复暴露给数据治理任务
    （`scripts/migrate_fund_company_merge.py`）。
    """
    from app.domains.funds.models import Fund, Manager

    # 引用数 = 经理数 + 基金数（两个 consumer 都算，且与迁移脚本口径一致）
    ref_counts = dict(
        db.query(Manager.company_id, func.count(Manager.id))
        .filter(Manager.company_id.isnot(None))
        .group_by(Manager.company_id)
        .all()
    )
    for cid, cnt in (
        db.query(Fund.company_id, func.count(Fund.id)).filter(Fund.company_id.isnot(None)).group_by(Fund.company_id)
    ):
        ref_counts[cid] = ref_counts.get(cid, 0) + cnt
    grouped: Dict[tuple, List[FundCompany]] = {}
    for row in db.query(FundCompany).all():
        if not row.name:
            continue
        grouped.setdefault(company_index_key(row.name), []).append(row)

    index: Dict[tuple, FundCompany] = {}
    for key, rows in grouped.items():
        if len(rows) > 1:
            canonical_id = pick_canonical_company([(r.id, r.name, ref_counts.get(r.id, 0)) for r in rows])[0]
            logger.warning(
                '基金公司存在重复实体（键 %r，ids=%s），暂择 id=%s 为准；需数据合并',
                key,
                [r.id for r in rows],
                canonical_id,
            )
            rows = [r for r in rows if r.id == canonical_id]
        index[key] = rows[0]
    return index


def company_index_key(name: str) -> tuple:
    """匹配键 = （归一化名, 业务族）。业务族进键，使「招商基金」与
    「招商证券资产管理」永不可能互相命中（二者归一化名同为 `招商`）。"""
    return (normalize_company_name(name), company_business_family(name))


def match_fund_company(index: Dict[tuple, FundCompany], name: str) -> Optional[FundCompany]:
    """按名称在索引里查同一法人主体；无匹配返回 None。

    匹配键含业务族，等价于两道闸同时满足——**宁可漏配（调用方记 warning，缺失可见）
    也不误配**（把 A 公司的官网/客服电话写到 B 公司上，是最难发现的一类数据腐蚀）。
    """
    if not name:
        return None
    return index.get(company_index_key(name))


def fetch_fund_company_list() -> List[Dict[str, str]]:
    """抓取并解析天天基金基金公司列表，返回 [{code, name}, ...]。"""
    resp = requests.get(_EASTMONEY_COMPANY_URL, timeout=15)
    resp.encoding = 'utf-8'
    text = resp.text
    m = re.search(r'op:(\[.*?\])\s*}', text, re.DOTALL)
    if not m:
        logger.warning('解析基金公司列表失败：未找到 op 数组')
        return []
    arr = json.loads(m.group(1))
    return [{'code': str(row[0]), 'name': str(row[1])} for row in arr if len(row) >= 2]


def reset_cache() -> None:
    """清空东财列表索引缓存（测试与需强制重取的场景用；下一次解析会重新抓取）。"""
    global _cache, _family_index
    _cache = None
    _family_index = None


def _manual_index() -> Dict[str, tuple]:
    """手动映射的归一化名索引（惰性构建，兼容法人后缀写法差异）。"""
    global _MANUAL_INDEX
    if _MANUAL_INDEX is None:
        _MANUAL_INDEX = {normalize_company_name(k): v for k, v in _MANUAL_MAPPING.items()}
    return _MANUAL_INDEX


def _ensure_indexes() -> None:
    """确保东财列表索引已加载（一次网络请求，同时构建 `_cache` 与 `_family_index`）。

    失败时置为空 dict（而非保持 None）——`_cache` 是「已加载」哨兵，否则每条记录都会重试网络。
    """
    global _cache, _family_index
    if _cache is not None:
        return
    try:
        companies = fetch_fund_company_list()
    except Exception as e:  # 网络/解析失败不应阻断同步主流程
        logger.warning(f'获取基金公司列表失败，跳过 code/简称 解析: {e}')
        _cache, _family_index = {}, {}
        return
    _cache, _family_index = {}, {}
    for c in companies:
        name, code = c.get('name'), c.get('code')
        if not name or not code:
            continue
        _cache.setdefault(name, code)  # 东财原文名即简称，精确命中无歧义
        norm = normalize_company_name(name)
        if norm:
            _family_index.setdefault((norm, company_business_family(name)), (code, name))


def resolve_company_identity(name: str) -> tuple:
    """公司名 → (东财权威 code, 东财简称)；解析不到返回 `(None, None)`。

    **全仓唯一的「公司名 → 权威标识 + 简称」解析入口**：`get_company_code_by_name`
    是只取 code 的薄封装，`get_or_create_fund_company`（写库）与回填脚本共用本函数。

    解析顺序：
    1. `_MANUAL_MAPPING`——按原文名，再按归一化名各查一次（兼容「有限公司 /
       股份有限公司」写法差异）；
    2. 东财原文名精确命中（此时简称即原文名）；
    3. 归一化名 + 业务族（`company_index_key`）——把「招商基金管理有限公司」归到
       「招商基金」，同时**拦住**同名券商资管（「招商证券资产管理有限公司」归到
       「招商证券资管」）。族盲归一化会让二者互相取到对方的 code（2026-09-10 实测）。

    为什么必须同时返回简称：`FundCompany.name` 的列语义是**简称**（全称归 `full_name`），
    而 akshare 链路（基金经理 / 基金详情）给的是法人全称。只返回 code 时调用方只能把全称
    写进 `name`，该行就永久停在错误形态（2026-09-10 实测存量 6 行，其中 4 行可自动修复）。
    """
    if not name:
        return (None, None)
    manual = _MANUAL_MAPPING.get(name) or _manual_index().get(normalize_company_name(name))
    if manual:
        return manual
    _ensure_indexes()
    if _cache:
        code = _cache.get(name)
        if code:
            return (code, name)  # 东财原文名即简称
    if _family_index:
        hit = _family_index.get(company_index_key(name))
        if hit:
            return hit
    return (None, None)


def get_company_code_by_name(name: str) -> Optional[str]:
    """按公司名解析真值 code；未命中返回 None（`resolve_company_identity` 的薄封装）。"""
    return resolve_company_identity(name)[0]


def get_code_short_name_map() -> Dict[str, str]:
    """东财 `code → 简称` 映射（加载索引后返回）。

    给维护脚本做「code → 简称」收敛用：与 `resolve_company_identity` 共享同一份抓取结果，
    避免脚本自己再抓一次、或自建第二份简称标准（两处实现必然漂移）。网络不可用时返回 `{}`。
    """
    _ensure_indexes()
    return {code: name for name, code in (_cache or {}).items()}


def get_or_create_fund_company(db: Session, name: str, cache: Optional[Dict[str, int]] = None) -> Optional[int]:
    """按名称取公司 id，不存在才新建（**全仓唯一写入口，四个 job 共用**）。

    为什么要收口：基金列表 / 基金详情 / 基金经理 三个同步任务都会带来公司名，
    此前各自实现「查名 → 建行」，而各来源给的形态不同——东财基金列表给简称
    （「招商基金」），akshare 基金经理给全称（「招商基金管理有限公司」）——
    精确匹配全部落空，于是同一家公司在库里长出两行（2026-09-10 实测 8 组，
    招商基金的经理被分裂挂在 103 + 9 两行上）。**同一实体只能有一个写入口**，
    四个 job 各写一份必然漂移。

    匹配顺序：
    1. `name` 精确相等（快路径）；
    2. 归一化名 + 业务族相等（`match_fund_company`）——「招商基金管理有限公司」
       归一到与库内简称行「招商基金」同键，命中既有行、不再新建；
    3. 仍未命中才新建：`name` 写**东财简称**（`resolve_company_identity` 的第 2 个返回值，
       保证列语义成立；东财未收录时才退回调用方原名），`code` 优先天天基金权威 code，
       未命中保留 `code=name` 占位（由 `backfill_fund_company_codes` 后续补齐）。

    **已存在行绝不被改名**（本函数无任何 UPDATE）：同步路径里 `name` 只在建行时写一次，
    存量形态不对的行由显式维护脚本修（`backfill_fund_company_codes` /
    `migrate_fund_company_merge`），这样「抓取」不会与「修复」来回改写同一列。

    `full_name` / 地址 / 官网等 AMAC 字段不在本函数写权内（单一写者原则，
    见 `FundCompany` docstring）；本函数只负责「找到或创建那一行」。
    """
    if not name:
        return None
    if cache is not None and name in cache:
        return cache[name]

    inst = db.query(FundCompany).filter_by(name=name).first()
    if inst is None:
        # 跨来源形态差异（全称 ↔ 简称）靠归一化收敛，避免为同一主体建第二行
        inst = match_fund_company(build_fund_company_index(db), name)
    if inst is None:
        real_code, short_name = resolve_company_identity(name)
        if not real_code:
            logger.warning(f'基金公司「{name}」未匹配到权威 code，暂以名称占位')
        # `name` 列语义是简称：能解析到东财简称就写简称，解析不到才退回调用方原名
        display_name = short_name or name
        candidate_code = real_code or name
        # unique(code) 闸：占位 code=name 跨批次/跨运行可能已存在；权威 code 也可能
        # 被同机构的简称/全称变体行占用（#1286 全量回填实测：银华基金 80000235）
        inst = db.query(FundCompany).filter_by(code=candidate_code).first()
        if inst is None:
            inst = FundCompany(name=display_name, code=candidate_code)
            db.add(inst)
            db.flush()

    if cache is not None:
        cache[name] = inst.id
        cache.setdefault(inst.name, inst.id)  # 简称/全称两种入参都能命中缓存
    return inst.id


def backfill_fund_company_codes(db: Session, dry_run: bool = True) -> Dict[str, object]:
    """
    回填 fund_companies 表中 code==name 的占位行（幂等）。

    仅处理 code 仍等于 name 的行（占位行）；按名解析权威身份，命中则同时更新
    code 与 name——`name` 列语义是简称，占位行的 name 是法人全称，故顺手收敛为
    东财简称（与 `migrate_fund_company_merge` 阶段 4 同一权威来源，不引入第二份标准）。
    若真值 code 已被别的行占用，跳过并告警（避免唯一约束冲突）。dry_run=True 只统计不落库。

    为什么由本函数承担「顺带简称化」：同步路径（`get_or_create_fund_company`）只写新建行、
    从不改存量行，否则抓取与修复会来回改写同一列；存量形态修复必须走这种显式脚本。

    返回结构化结果（#1199 用于实测命中率并留档）：
        {
            'total_placeholders': int,                       # code==name 占位总行数
            'matched':  [{'id','name','old_code','new_code','new_name'}, ...],  # 命中待回填
            'unmatched':[{'id','name','code'}, ...],          # 失配/冲突跳过，仍保留占位
        }
    hit_rate = len(matched) / total_placeholders。
    """
    placeholders = db.query(FundCompany).filter(FundCompany.code == FundCompany.name).all()
    # 已存在的真值 code 集合，用于冲突检测
    taken_codes = {row[0] for row in db.query(FundCompany.code).all()}
    matched: List[dict] = []
    unmatched: List[dict] = []
    for inst in placeholders:
        real_code, short_name = resolve_company_identity(inst.name)
        if not real_code:
            unmatched.append({'id': inst.id, 'name': inst.name, 'code': inst.code})
            logger.warning(f'基金公司「{inst.name}」未匹配到权威 code，保留占位')
            continue
        if real_code in taken_codes and real_code != inst.code:
            unmatched.append({'id': inst.id, 'name': inst.name, 'code': inst.code})
            logger.warning(f'真值 code {real_code} 已被占用，跳过「{inst.name}」')
            continue
        matched.append(
            {
                'id': inst.id,
                'name': inst.name,
                'old_code': inst.code,
                'new_code': real_code,
                'new_name': short_name or inst.name,
            }
        )
        if not dry_run:
            inst.code = real_code
            if short_name and short_name != inst.name:
                inst.name = short_name
            taken_codes.add(real_code)
    if not dry_run and matched:
        db.commit()
        logger.info(f'回填 {len(matched)} 条基金公司 code（name 同步收敛为东财简称）')
    return {'total_placeholders': len(placeholders), 'matched': matched, 'unmatched': unmatched}
