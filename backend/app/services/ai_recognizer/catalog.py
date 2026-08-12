# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/13
# File : catalog.py
"""AI 识别域类型/名称反查：识别结果 → 资产类型/市场/场所（证券/基金表消歧）。

从旧 `ocr_service.py` 的 `_enrich_items` 迁出（P1 抽象），供自选/持仓两个场景共用：
持仓候选（含 business_type/金额/份额等字段）通过本层反查 type/venue/symbol 后，
前端才能决定按基金还是股票的精度规则展示与入库。

设计要点（迁出时全量保留，行为不变）：
1. Securities 命中且 Funds 未命中（normalizer 标准化后精确匹配）→ 场内品种；
2. Funds 命中且 Securities 未命中 → 场外基金；
3. 两表同时命中 → 用 OCR/正则名称消歧（002910 股票庄园牧场 vs 基金易方达供给侧改革混合），
   都不命中默认基金（用户导入以基金为主）；
4. 都未命中但符合场内基金代码模式（5/159/16x）→ 场内 ETF/LOF；
5. 兜底 → 默认场外基金。
"""

from typing import List


def name_hits(name: str, table_name: str) -> bool:
    """OCR/正则名称与表名的模糊匹配（用于代码冲突消歧）。

    证券与基金共用同一段 6 位数字空间（如 002910 既是深市股票庄园牧场、
    也是基金易方达供给侧改革混合），仅凭代码无法区分，必须结合名称：
    去掉常见基金后缀词（混合/基金）后比较包含关系或前 4 字，容忍 OCR 漏字
    （如「易方达供给改革混合」漏了「侧」）。
    """
    if not name or not table_name:
        return False

    def _clean(s: str) -> str:
        return s.replace(' ', '').replace('基金', '').replace('混合', '')

    n, t = _clean(name), _clean(table_name)
    if n and t and (n in t or t in n):
        return True
    return len(n) >= 4 and len(t) >= 4 and n[:4] == t[:4]


def is_listed_fund_code(code: str) -> bool:
    """6 位数字代码是否符合「场内基金」模式（无需查表即可判定）。

    - 5 开头：沪市 ETF/LOF/Reits/货币（510xxx-589xxx）
    - 159 开头：深市 ETF
    - 16x 开头：深市 LOF（160xxx-169xxx）

    场外开放式基金（110011、005827、270xxx 等）不落入上述区段。
    """
    return code.startswith('5') or code.startswith('159') or code.startswith('16')


def _normalize_code(code: str):
    """号码标准化（symbol_utils.normalizer），失败返回 (None, None, None) 不抛错。"""
    try:
        from app.core.symbol_utils import get_normalizer

        return get_normalizer().normalize(code)
    except Exception:
        return None, None, None


def enrich(items: List[dict]) -> List[dict]:
    """为识别结果补充资产类型/市场/场所（Security 表命中 → 场内代码规则 → Funds 表 → 兜底）。

    结果行为与旧 ocr_service._enrich_items 完全一致；额外保留输入中的其他字段
    （持仓场景的 business_type/金额/份额等会透传，供下游入库管线使用）。
    """
    from app.core.database import SessionLocal
    from app.domains.funds.models import Fund
    from app.domains.securities.models import Security

    enriched: List[dict] = []
    with SessionLocal() as db:
        for it in items:
            code = it['code']
            name = it.get('name', '')
            info = dict(it)  # 保留场景额外字段（如 txn 的 business_type/金额/份额）
            # 号码标准化统一走 normalizer（symbol_utils），不在此自行判断市场/拼接前缀
            normalized, market, _ = _normalize_code(code)
            sec = db.query(Security).filter_by(symbol=normalized).first() if normalized else None
            fund = db.query(Fund).filter_by(fund_code=code).first()

            # 3) 两表同时命中 → 名称消歧（002910 股票庄园牧场 vs 基金易方达供给侧改革混合）
            if fund and sec:
                if name_hits(name, sec.name) and not name_hits(name, fund.name):
                    info.update(
                        {
                            'symbol': sec.symbol,
                            'name': sec.name or info['name'],
                            'type': sec.type,
                            'market': sec.market,
                            'venue': 'EXCHANGE',
                        }
                    )
                else:
                    # 名称命中基金或都不命中 → 默认基金（用户 OCR 导入以基金为主）
                    info.update(
                        {
                            'symbol': code,
                            'name': fund.name or info['name'],
                            'type': 'fund',
                            'market': 'CN_A',
                            'venue': 'OTC',
                        }
                    )
                enriched.append(info)
                continue
            # 1) 仅 Securities 命中 → 场内品种
            if sec:
                info.update(
                    {
                        'symbol': sec.symbol,
                        'name': sec.name or info['name'],
                        'type': sec.type,
                        'market': sec.market,
                        'venue': 'EXCHANGE',
                    }
                )
                enriched.append(info)
                continue
            # 4) 场内基金（ETF/LOF）：场内代码模式优先于 Funds 表——
            #    基金主表会收录 ETF（如 510300 沪深300ETF华泰柏瑞），仅凭 Funds 命中会误判为 OTC
            if is_listed_fund_code(code):
                fund_type = 'etf' if (code.startswith('5') or code.startswith('159')) else 'fund'
                info.update(
                    {
                        'symbol': normalized or code,
                        'name': fund.name if fund else info['name'],
                        'type': fund_type,
                        'market': market or 'CN_A',
                        'venue': 'EXCHANGE',
                    }
                )
                enriched.append(info)
                continue
            # 2) 仅 Funds 命中 → 场外基金
            if fund:
                info.update(
                    {
                        'symbol': code,
                        'name': fund.name or info['name'],
                        'type': 'fund',
                        'market': 'CN_A',
                        'venue': 'OTC',
                    }
                )
                enriched.append(info)
                continue
            # 5) 兜底：默认场外基金
            info.update({'symbol': code, 'type': 'fund', 'market': 'CN_A', 'venue': 'OTC'})
            enriched.append(info)
    return enriched


# 兼容旧命名（旧 ocr_service 模块的内置名，供既有调用/测试引用）
_name_hits = name_hits
_is_listed_fund_code = is_listed_fund_code
_enrich_items = enrich
