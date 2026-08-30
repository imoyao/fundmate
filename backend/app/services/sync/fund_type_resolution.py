# -*- coding: utf-8 -*-
"""基金类型解析：将外部数据源的原始类型文本映射为内部 canonical ID。

职责单一（高内聚）：本模块只负责「原始类型文本 -> (fund_type_id, fund_variety_id)」，
不涉及抓取、批量落库等其它同步细节，便于 enrich job 与 backfill job 复用（低耦合）。

设计（对齐 importer/parsers 的「策略 + 注册表」模板）：
- RawFundTypeDecomposer（策略接口）：把原始类型串拆成 (大类名, 小类名)。
  不同数据源格式不同（akshare 为「大类-细分」），通过注册表注入，符合开闭原则。
- FundTypeResolver（解析器）：组合 decomposer + 领域内 get-or-create，
  对外暴露 resolve(raw_type, raw_variety=None) -> (fund_type_id, fund_variety_id)。
"""

from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.domains.funds.models import FundType, FundVariety


class RawFundTypeComponents:
    """原始类型串的拆分结果：大类名 + 小类名（均可为空）。"""

    __slots__ = ('variety_name', 'type_name')

    def __init__(self, variety_name: Optional[str], type_name: Optional[str]):
        self.variety_name = variety_name
        self.type_name = type_name


class RawFundTypeDecomposer:
    """策略接口：将原始类型串拆分为 (大类名, 小类名)。"""

    def decompose(self, raw: str) -> RawFundTypeComponents:
        raise NotImplementedError


class AkshareRawTypeDecomposer(RawFundTypeDecomposer):
    """akshare fund_name_em / fund_detail 的类型串解析。

    akshare 形如「混合型-灵活」「指数型-股票」「货币型-普通货币」——
    以首个「-」为界，左边为大类（variety），整串为小类（type）。
    无「-」时（如「ETF」「LOF」「联接基金」「股票型」）大类=小类=原串。
    """

    _SEP = '-'

    def decompose(self, raw: str) -> RawFundTypeComponents:
        text = (raw or '').strip()
        if not text:
            return RawFundTypeComponents(None, None)
        if self._SEP in text:
            variety = text.split(self._SEP, 1)[0].strip()
            return RawFundTypeComponents(variety or text, text)
        return RawFundTypeComponents(text, text)


# 数据源 -> 拆分策略（注册表；新增数据源只需在此登记一个实现）
_DECOMPOSERS: Dict[str, RawFundTypeDecomposer] = {
    'akshare': AkshareRawTypeDecomposer(),
}


def get_decomposer(source: str = 'akshare') -> RawFundTypeDecomposer:
    """按数据源名取得拆分策略，未知源回退默认 akshare。"""
    return _DECOMPOSERS.get(source, _DECOMPOSERS['akshare'])


class FundTypeResolver:
    """基金类型解析器：原始类型文本 -> 内部 canonical ID。

    只依赖数据库会话，不触碰抓取与批量更新，便于在多个 Job 间复用（低耦合）。
    """

    def __init__(self, db: Session, decomposer: Optional[RawFundTypeDecomposer] = None):
        self.db = db
        self._decomposer = decomposer or get_decomposer('akshare')

    def resolve(self, raw_type: str, raw_variety: Optional[str] = None) -> Tuple[Optional[int], Optional[int]]:
        """返回 (fund_type_id, fund_variety_id)。

        raw_variety 优先作为大类名；否则从 raw_type 拆分得到。
        小类名取 raw_type 原串（保证与既有 fund_types 命名一致）。
        大类与小类均无有效文本时返回 (None, None)。
        """
        type_name = (raw_type or '').strip()
        if raw_variety:
            variety_name: Optional[str] = raw_variety.strip()
        else:
            variety_name = self._decomposer.decompose(raw_type).variety_name

        if not type_name and not variety_name:
            return None, None

        variety_id = self._resolve_variety(variety_name) if variety_name else None
        type_id = self._resolve_type(type_name, variety_id) if type_name else None
        return type_id, variety_id

    def _resolve_variety(self, variety_name: str) -> Optional[int]:
        variety = self.db.query(FundVariety).filter_by(name=variety_name).first()
        if variety is None:
            variety = FundVariety(name=variety_name)
            self.db.add(variety)
            self.db.flush()
        return variety.id

    def _resolve_type(self, type_name: str, variety_id: Optional[int]) -> Optional[int]:
        fund_type = self.db.query(FundType).filter_by(name=type_name).first()
        if fund_type is None:
            fund_type = FundType(name=type_name, variety_id=variety_id)
            self.db.add(fund_type)
            self.db.flush()
        elif variety_id is not None and fund_type.variety_id is None:
            # 已有小类但未关联大类，补全关联（保持大类/小类一致）
            fund_type.variety_id = variety_id
            self.db.flush()
        return fund_type.id
