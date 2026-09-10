# -*- coding: utf-8 -*-
"""跨渠道关联同步（#1285 设计 §3.8：指数↔ETF，主流宽基）。

**为什么是白名单而不是全量**：2026-09-11 实测 akshare `fund_etf_spot_em` **没有
「跟踪标的」字段**（1605 只 ETF 全无），交易所 ETF 规模表也无标的指数；退而用
「ETF 名称 ↔ `index_catalog` 名称」子串匹配，总覆盖仅 **41.1%**（660/1605），
低于设计要求的 90% 门槛 → 按既定规则**降级为「先覆盖主流宽基」**：
用人工策展的宽基白名单按关键词匹配，其余 ETF 不做关联（前端留 `—`）。

匹配规则：**取最长命中关键词**对应的指数——避免「中证100」吞掉「中证1000」、
「红利」吞掉「中证红利」等歧义。

写入策略：**整体覆盖式重建**（只删 `source='auto'` 的行，保护人工维护的关联）。
"""

from typing import List, Optional, Tuple

from loguru import logger

from app.domains.funds.models import ChannelLink
from app.services.sync.jobs.base import SyncJob

# (指数裸代码, 指数名, 匹配关键词列表)
INDEX_ETF_WHITELIST: List[Tuple[str, str, List[str]]] = [
    ('000300', '沪深300', ['沪深300']),
    ('000905', '中证500', ['中证500']),
    ('000852', '中证1000', ['中证1000']),
    ('000016', '上证50', ['上证50']),
    ('000510', '中证A500', ['中证A500', 'A500']),
    ('000688', '科创50', ['科创50', '科创板50']),
    ('399006', '创业板指', ['创业板指', '创业板']),
    ('932000', '中证2000', ['中证2000']),
    ('000922', '中证红利', ['中证红利']),
    ('000903', '中证100', ['中证100']),
    ('000906', '中证800', ['中证800']),
    ('399330', '深证100', ['深证100']),
    ('000010', '上证180', ['上证180']),
]


def match_index_for_etf(name: str) -> Optional[Tuple[str, str, str]]:
    """ETF 名称 → (指数裸代码, 指数名, 命中关键词)；无命中返回 None。

    取**最长命中关键词**，避免短关键词吞掉更长语义（中证100 vs 中证1000）。
    """
    best: Optional[Tuple[str, str, str]] = None
    for code, index_name, keywords in INDEX_ETF_WHITELIST:
        for kw in keywords:
            if kw in name and (best is None or len(kw) > len(best[2])):
                best = (code, index_name, kw)
    return best


def _digits(value) -> str:
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


class ChannelLinkSyncJob(SyncJob):
    """跨渠道关联（指数↔ETF，主流宽基）回填。"""

    @property
    def _allow_empty_data(self) -> bool:
        return True

    def get_name(self) -> str:
        return 'channel_link'

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        etfs = self.adapter.fetch_etf_list()
        out: List[dict] = []
        for e in etfs:
            hit = match_index_for_etf(e['name'])
            if not hit:
                continue
            index_code, index_name, _kw = hit
            out.append(
                {
                    'link_type': 'index_etf',
                    'from_symbol': index_code,
                    'from_name': index_name,
                    'to_symbol': e['code'],
                    'to_name': e['name'],
                    'match_type': 'whitelist_keyword',
                    'source': 'auto',
                }
            )
        logger.info(
            f'指数↔ETF 关联候选 {len(out)} 条（ETF 总数 {len(etfs)}，白名单 {len(INDEX_ETF_WHITELIST)} 个指数）'
        )
        return out

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
