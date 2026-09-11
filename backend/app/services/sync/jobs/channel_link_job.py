# -*- coding: utf-8 -*-
"""跨渠道关联同步（#1285 设计 §3.8）：指数↔ETF + ETF↔场外联接。

── 为什么靠名称匹配 ──
ETF 的「跟踪标的」在免 cookie 数据源里**不存在**（2026-09-11 实测：`fund_etf_spot_em`
1606 只全无该字段，交易所 ETF 规模表亦无），故只能靠名称匹配。实测与选型依据
（含「换文本源比调算法收益大一个量级」的量化结论）见 `services/sync/name_match.py`。

── 第一版（PR #1399）的降级 ──
用东财**场内简称**做子串匹配，总覆盖 41.1%（<90% 门槛）→ 降级为 13 个宽基白名单，
实跑仅落库 274 条，且白名单关键词过宽：
「沪深300价值ETF申万菱信」「A500红利低波ETF华宝」被记到**母指数**名下（错配）。

── 本版做了什么 ──
1. **换文本源**：优先取同花顺**基金全称**（「国泰中证全指通信设备ETF」），
   东财简称仅作回退 —— 覆盖率 45.2% → 89.0%（毛）/ 66.4%（过滤后落库口径）。
2. **最长核心名匹配**：同时修掉母指数吞掉主题指数的问题（长核心名优先）。
3. **补第二层 `etf_feeder`**：场外联接基金 ↔ 场内 ETF。联接名归一后与 ETF 归一核心名
   比对，**同核心多 ETF 时用「管理人一致」消歧**（联接基金必须由同一管理人发起），
   实测可落库 1486/2177 = 68.3%（此前该层**完全没做**）。
4. 白名单**退役**：母指数不再靠关键词特判，改由匹配器统一产出（覆盖面反而更大）。

── 残留缺口（记在 #1419，不在此处硬凑）──
跨境/商品 ETF（纳斯达克100、标普500、黄金、豆粕…）的跟踪标的**不在 `index_catalog`
范围内**（名录只收录境内 CSI/CNI/SH/SZ 指数），名称再准也匹配不上；故这部分保持 `—`。
「ETF↔联接」另有约 26% 因命名不含指数名（「南方小康ETF联接」）或跨市场而无法自动配对。

写入策略：**覆盖式重建**（只删 `source='auto'` 的行，保护人工维护的关联）。
"""

from typing import Dict, List, Optional, Sequence, Tuple

from loguru import logger

from app.domains.funds.models import ChannelLink, Fund, FundCompany
from app.domains.indices.models import IndexCatalog
from app.services.sync.jobs.base import SyncJob
from app.services.sync.name_match import ChannelNameMatcher, pick_manager

# 联接基金识别：场外联接的产品名固定含「联接」（如「华夏沪深300ETF联接A」）。
_FEEDER_NAME_PATTERN = '%联接%'


def _digits(value) -> str:
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def _dedup_hits(candidates: Sequence[Tuple[str, str]], manager: Optional[str]) -> Optional[Tuple[str, str]]:
    """同核心多候选时用管理人消歧；**消歧不唯一就放弃**（宁可留 `—` 也不错配）。"""
    codes = {code for code, _ in candidates}
    if len(codes) == 1:
        return candidates[0]
    if not manager:
        return None
    filtered = {code: name for code, name in candidates if manager in name}
    if len(filtered) == 1:
        code = next(iter(filtered))
        return (code, filtered[code])
    return None


class ChannelLinkSyncJob(SyncJob):
    """跨渠道关联回填：指数↔ETF（第一层）+ ETF↔场外联接（第二层）。"""

    @property
    def _allow_empty_data(self) -> bool:
        return True

    def get_name(self) -> str:
        return 'channel_link'

    # ── 取数 ──

    def _build_matcher(self) -> ChannelNameMatcher:
        """公司名 + 指数名录 → 匹配器。两者都来自本库（market 域已同步的数据）。"""
        company_names = [
            value for row in self.db.query(FundCompany.name, FundCompany.full_name).all() for value in row if value
        ]
        index_entries = [
            (code, name) for code, name in self.db.query(IndexCatalog.index_code, IndexCatalog.name).all() if name
        ]
        return ChannelNameMatcher(company_names, index_entries)

    def _fetch_etf_names(self) -> Dict[str, str]:
        """ETF 裸代码 → 匹配用名称。同花顺全称优先，东财简称兜底。

        为什么必须两者都取：同花顺名录（1719）与东财名录（1606）**并非包含关系**，
        各有个别代码缺失；两者并集才是完整候选集（实测并集 1722）。
        """
        names: Dict[str, str] = {}
        for item in self.adapter.fetch_etf_list():  # 东财简称（兜底）
            code, name = _digits(item.get('code')), (item.get('name') or '').strip()
            if code and name:
                names[code] = name
        # 同花顺全称覆盖同名 code —— 这是覆盖率提升的关键（见 name_match docstring）
        for item in self.adapter.fetch_etf_list_ths():
            code, name = _digits(item.get('code')), (item.get('name') or '').strip()
            if code and name:
                names[code] = name
        return names

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        matcher = self._build_matcher()
        etf_names = self._fetch_etf_names()
        if not etf_names:
            self.logger.warning('ETF 名录为空，无法建立跨渠道关联')
            return []

        out: List[dict] = []
        out.extend(self._build_index_etf_links(matcher, etf_names))
        out.extend(self._build_etf_feeder_links(matcher, etf_names))
        self.logger.info(
            f'跨渠道关联候选 {len(out)} 条（ETF {len(etf_names)} 只 / 可匹配指数 {matcher.index_count} 个）'
        )
        return out

    def _build_index_etf_links(self, matcher: ChannelNameMatcher, etf_names: Dict[str, str]) -> List[dict]:
        """第一层：指数 → 场内 ETF。"""
        out, unmatched = [], 0
        for code, name in etf_names.items():
            hit = matcher.match_index(name)
            if hit is None:
                unmatched += 1
                continue
            out.append(
                {
                    'link_type': 'index_etf',
                    'from_symbol': hit.index_code,
                    'from_name': hit.index_name,
                    'to_symbol': code,
                    'to_name': name,
                    'match_type': 'name_longest_core',
                    'source': 'auto',
                }
            )
        self.logger.info(
            f'指数↔ETF：命中 {len(out)} / {len(etf_names)} = {len(out) / len(etf_names):.1%}（未命中 {unmatched}）'
        )
        return out

    def _build_etf_feeder_links(self, matcher: ChannelNameMatcher, etf_names: Dict[str, str]) -> List[dict]:
        """第二层：场内 ETF → 场外联接基金。

        联接基金名（「嘉实中证500ETF联接A」）与 ETF 名（「中证500ETF嘉实」/「嘉实中证500ETF」）
        归一后同核心名；同核心多只 ETF 时以**管理人一致**消歧——联接基金由 ETF 的同一管理人发起，
        这是硬约束（跨管理人联接不存在）。
        """
        etf_by_core: Dict[str, List[Tuple[str, str]]] = {}
        for code, name in etf_names.items():
            core = matcher.clean(name)
            if core:
                etf_by_core.setdefault(core, []).append((code, name))

        out, ambiguous = [], 0
        linkers = self.db.query(Fund.fund_code, Fund.name).filter(Fund.name.like(_FEEDER_NAME_PATTERN)).all()
        for fund_code, fund_name in linkers:
            if not fund_name:
                continue
            core = matcher.clean(fund_name)
            candidates = etf_by_core.get(core) if core else None
            if not candidates:
                continue
            picked = _dedup_hits(candidates, pick_manager(fund_name, matcher.company_tokens))
            if picked is None:
                ambiguous += 1
                continue
            etf_code, etf_name = picked
            out.append(
                {
                    'link_type': 'etf_feeder',
                    'from_symbol': etf_code,
                    'from_name': etf_name,
                    'to_symbol': _digits(fund_code),
                    'to_name': fund_name,
                    'match_type': 'feeder_core_manager',
                    'source': 'auto',
                }
            )
        total = len(linkers)
        ratio = f'{len(out) / total:.1%}' if total else 'n/a'
        self.logger.info(f'ETF↔联接：命中 {len(out)} / {total} = {ratio}（歧义放弃 {ambiguous}）')
        return out

    # ── 校验 / 去重 / 落库 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        out = []
        for r in raw_data:
            from_code = _digits(r.get('from_symbol'))
            to_code = _digits(r.get('to_symbol'))
            if not from_code or not to_code:
                continue
            out.append(dict(r, from_symbol=from_code, to_symbol=to_code))
        return out

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        seen = set()
        out = []
        for r in data:
            key = (r['link_type'], r['from_symbol'], r['to_symbol'])
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    def _save_data(self, new_data: List[dict]) -> None:
        # 覆盖式重建：只清 auto 行，人工维护的关联（source='manual'）必须保留
        self.db.query(ChannelLink).filter(ChannelLink.source == 'auto').delete(synchronize_session=False)
        for r in new_data:
            self.db.add(ChannelLink(**r))
        self.db.commit()
        logger.info(f'写入跨渠道关联 {len(new_data)} 条')
