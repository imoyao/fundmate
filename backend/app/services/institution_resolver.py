# -*- coding: utf-8 -*-
# app/services/institution_resolver.py
"""销售机构（AMAC 名录）名称匹配的**唯一实现**。

## 为什么需要它

名录侧是**法人全称**（`珠海盈米基金销售有限公司`），而导入侧给的是**渠道简称**
（`珠海盈米基金销售`，来自基金E账户导出）。历史上两处调用各自写了一份「org_name 等值 →
display_name 等值」的两步精确匹配：

- `importer/orchestrator_holdings._get_or_create_channel_ledger`（建渠道 Ledger）
- 影子记录派生机构 id（本模块的 `resolve_sales_institution_id`）

于是只要名字少「有限公司」几个字就必然落空：前者静默走「不关联机构」的回退，
建出一堆 `sales_institution_id=NULL` 的孤儿渠道账户（2026-10-28 实测 13 个渠道 8 个落空）；
后者让影子记录的机构维度全部为空。**同一实体两处各写一份判据，必然漂移**——
本模块把判据收成一份，两个调用方共用。

## 判据（宁可漏配，不可误配）

1. `org_name` 精确 → 2. `display_name` 精确 → 3. 手工别名 → 4. **归一化名 + 业务族**唯一命中。

第 4 步复用 `sync/company_resolver.normalize_company_name`（全仓唯一的法人后缀剥离实现），
它会把括号内容与「有限公司 / 股份有限公司 / 基金 / 证券 / 资管」等后缀迭代剥掉。

**为什么必须带业务族**：归一化会撞键——「招商银行」与「招商证券」都收敛到 `招商`。
族盲匹配会把银行渠道挂到证券公司主体上，那比漏配贵得多（错配的外键几乎不可能被发现）。
因此同键多候选一律判**歧义 → 不匹配**，并把候选 id 打进 warning，等人去补别名。

漏配的后果是可见的（warning + 孤儿账户），误配的后果是不可见的——判据方向由此确定。
"""

from typing import Dict, List, Optional, Tuple

from loguru import logger

from app.domains.positions.models import SalesInstitution
from app.services.sync.company_resolver import normalize_company_name

# 业务族关键字（顺序即优先级：先判银行，避免「招商银行信用卡」之类被「证券」等误吞）
_FAMILY_KEYWORDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ('bank', ('银行',)),
    ('securities', ('证券',)),
    ('futures', ('期货',)),
    ('insurance', ('保险',)),
    ('fund', ('基金',)),
)

# 实测确认的形态差异（原文名 → AMAC 权威全称）：品牌词完全不同，任何归一化规则都收敛不了。
# 新增条件：必须拿真实名录核对过「该全称确实存在」，禁止凭推测登记。
_MANUAL_ALIASES: Dict[str, str] = {
    # 浦发银行：AMAC 全称用「上海浦东发展银行」，与用户口中的「浦发银行」无公共前缀
    '浦发银行': '上海浦东发展银行',
}


def institution_family(name: str) -> str:
    """按名称推断机构业务族：bank / securities / futures / insurance / fund / other。

    只做「够用」的判定——它不用于展示与入库，只用于**消歧**（见模块 docstring）。

    为什么不用 `sync/company_resolver.company_business_family`：那个只区分「基金管理人 / 其他」
    （服务的是基金公司归并），而这里的消歧对象是销售机构——「招商银行」与「招商证券」在
    服务销售机构名录里都是真实存在的主体，只判 fund/other 会把它们同时归成 `other`，
    于是两家一起变成「歧义 → 不匹配」，渠道账户会全部退回不关联机构的孤儿状态。
    两者目标不同、粒度不同，故分别实现；**归一化（剥后缀）仍共用同一份实现**。
    """
    text = name or ''
    for family, keywords in _FAMILY_KEYWORDS:
        if any(k in text for k in keywords):
            return family
    return 'other'


def _name_forms(name: str) -> List[str]:
    """名称的归一化候选形态（按优先级去重）。

    第二个形态剥掉前导「中国」：AMAC 名录里「银河证券」与导入侧的「中国银河证券」是同一主体，
    但「中国」不属于任何法人后缀，归一化函数不会剥它。只在**加前缀**这一种成因下启用，
    因此不引入歧义（「中国银行」剥完是「银行」，不会与任何全称唯一命中）。
    """
    base = normalize_company_name(name)
    if not base:
        return []
    forms = [base]
    if base.startswith('中国') and len(base) > 2:
        forms.append(base[2:])
    return list(dict.fromkeys(forms))


class SalesInstitutionResolver:
    """AMAC 名录的内存索引 + 匹配入口（一次构建、多次复用）。

    为什么要索引：E账户对账对**每一行持仓**都要解析渠道，若每次都全表扫 394 行
    （外加 `display_name` 再扫一遍），一次导入就是几百次全表扫描。索引在首个 `resolve`
    时惰性构建，之后只做字典查找。

    设计边界：索引只读、不缓存跨请求（机构名录由低频 job 更新，进程内长期缓存会让新上架
    的机构在本次进程生命周期内不可见）。对账编排器一次导入持有一个实例即可。
    """

    def __init__(self, db):
        self.db = db
        self._by_org: Optional[Dict[str, SalesInstitution]] = None
        self._by_display: Optional[Dict[str, SalesInstitution]] = None
        self._by_norm: Optional[Dict[Tuple[str, str], List[SalesInstitution]]] = None

    # ── 索引 ──

    def _load(self) -> None:
        if self._by_org is not None:
            return
        rows = self.db.query(SalesInstitution).filter(SalesInstitution.is_active.is_(True)).all()
        by_org: Dict[str, SalesInstitution] = {}
        by_display: Dict[str, SalesInstitution] = {}
        by_norm: Dict[Tuple[str, str], List[SalesInstitution]] = {}
        for row in rows:
            by_org.setdefault(row.org_name, row)
            if row.display_name:
                by_display.setdefault(row.display_name, row)
            for form in _name_forms(row.org_name):
                by_norm.setdefault((form, institution_family(row.org_name)), []).append(row)
        self._by_org, self._by_display, self._by_norm = by_org, by_display, by_norm

    # ── 匹配 ──

    def resolve(self, source_broker: Optional[str]) -> Optional[SalesInstitution]:
        """渠道名 → AMAC 机构行；无法唯一确定时返回 None（调用方决定是否回退建账户）。"""
        if not source_broker:
            return None
        self._load()
        assert self._by_org is not None and self._by_display is not None and self._by_norm is not None

        # 1) 原文精确（权威全称）
        row = self._by_org.get(source_broker)
        if row is not None:
            return row
        # 2) 别名精确（display_name，如「支付宝」「且慢」）
        row = self._by_display.get(source_broker)
        if row is not None:
            return row
        # 3) 手工别名（品牌词不同的形态差异）
        alias = _MANUAL_ALIASES.get(source_broker)
        if alias:
            row = self._by_org.get(alias)
            if row is not None:
                return row
            logger.warning(f'机构别名指向的全称不在名录内: {source_broker} -> {alias}')
        # 4) 归一化名 + 业务族，唯一命中才算数
        family = institution_family(source_broker)
        for form in _name_forms(source_broker):
            candidates = self._by_norm.get((form, family)) or []
            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1:
                # 歧义不猜：错配外键几乎不可能被发现，宁可漏配留 warning。
                logger.warning(
                    f'销售机构「{source_broker}」归一化后命中多个候选'
                    f'（键={form}/{family}, ids={[c.id for c in candidates]}），跳过匹配待人工确认'
                )
                return None
        return None


def resolve_sales_institution(db, source_broker: Optional[str]) -> Optional[SalesInstitution]:
    """一次性解析（供单条调用方使用；批量场景请自行复用 `SalesInstitutionResolver`）。"""
    return SalesInstitutionResolver(db).resolve(source_broker)


def resolve_sales_institution_id(db, source_broker: Optional[str]) -> Optional[int]:
    """同 `resolve_sales_institution`，只取 id（`PositionImportMeta.sales_institution_id` 用）。

    **为什么它在这里而不在 `domains/positions/models.py`**：分层依赖方向是
    `core ← domains.{models,schemas} ← services ← domains.views`，models 属叶子层，
    反向 import `app.services.*` 会踩 R3（`scripts/guard_layer_direction.py` 判红）。
    这个函数本身只是一个 `.id` 取值，语义上就是机构解析的一部分，故与判据同住 services 层。
    """
    institution = SalesInstitutionResolver(db).resolve(source_broker)
    return institution.id if institution else None
