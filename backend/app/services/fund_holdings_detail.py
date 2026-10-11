# -*- coding: utf-8 -*-
"""基金行业配置 + 持仓明细（#2029 卡 C · 详情页行业配置卡 + 持仓明细卡）。

一次返回两张卡要的全部数据（设计卡 §4.1 #4 #5）：**行业配置**（环形图 + 表格）与
**持仓明细**（个股表格）。两者同属「基金持仓穿透」语义、同一个端点，
拆两个请求会让详情页多一次往返，而两者的「取最新报告期」逻辑完全一致。

口径全部**复用既有实现，不自造第二套**
------------------------------------------------
- 行业配置：``penetration._load_industry_map`` 的分区口径 —— csrc（证监会门类）与
  gics（GICS 板块）**禁止跨体系相加**（模型注释 `FundIndustryAlloc` 已定此硬规则）；
  且取「该基金自身最新报告期」而非全局 ``max(report_period)``。
- 持仓明细：``manager_holdings._load_latest_holdings`` 的口径 —— 同期内
  ``full`` 优先、无 ``full`` 才用 ``top10`` 并据此打标（``_BASIS_LABELS`` 复用）。

为什么不复用 ``build_penetration``
----------------------------------
它是**家庭级**穿透：入口要 ``family_id``、依赖用户持仓做市值定值与加权，
回答的是「我家这只基金在行业里占多少」。本卡要回答的是「这只基金自己持有哪些行业 /
哪些股票」，**没有任何用户持仓语义**。强行复用会把详情页的基金维度
耦合到用户持仓维度上 —— 用户没持仓时整卡直接空，这是错的方向。
但穿透层里两条「取哪个报告期 / 哪个口径」的规则必须一致，否则同一只基金
在「穿透视图」和「详情页」会显示两份不同的持仓。故此处复用 loader 层口径，
而非聚合层入口。

诚实降级（设计§6）
-----------------
字段缺失一律返回 ``None`` 由前端降级为「—」，不编造占位值。
``applicable: false`` 表示该基金根本没有这两类披露数据（未到披露期 / 抓取未覆盖），
与「基金不存在」（返回 ``None`` → 调用方转 404）是两回事。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.data_sources import data_source_label
from app.services.manager_holdings import _BASIS_LABELS, _load_latest_holdings
from app.services.penetration import DEFAULT_SCHEME, SCHEME_LABELS

# 行业配置表格展示上限。csrc 门类最多 19 个（S~Z 实际用不满），全展示也不会撑爆；
# 超出时保留 Top N + 合并「其他」，避免出现一列看不见的表格行。
DEFAULT_INDUSTRY_TOP_N = 12

# 「其他」合并项的名字。刻意不用「其他」以外的花样，避免与真实行业名混淆。
_OTHER_LABEL = '其他'

# 两张表的落库来源码（``fund_position_job.HOLDING_SOURCE`` / ``INDUSTRY_SOURCE``
# 均为 'eastmoney'：东财 f10/ccmx 与 f10/HYPZ）。
# ⚠️ **不是** ``FUND_NAV_SOURCE_LABEL``（那是净值链路的「天天基金」）—— 标错来源
# 比不标更糟，用户会拿它当数据溯源依据。
_HOLDING_SOURCE = 'eastmoney'


def _iso(value) -> Optional[str]:
    """日期 → ISO 字符串；``None`` 原样返回。"""
    if value is None:
        return None
    return value.isoformat()


def _to_float(value) -> Optional[float]:
    """``SafeNumeric`` → ``float``；空值返回 ``None``（不编造 0）。"""
    return float(value) if value is not None else None


def _industry_buckets(db: Session, fund_code: str, top_n: int = 0) -> List[Dict[str, Any]]:
    """按 ``scheme`` 分区读该基金最新报告期的行业配置。

    每个分区一项：``{scheme, scheme_label, report_period, report_date, items[], total}``。

    **分区而非合并**（硬口径）：csrc 是证监会门类（单字母 A~S），gics 是 GICS 板块
    （两位数字，港股等走这套）。两套体系语义不重叠 —— GICS 的「非必需消费品」在
    证监会门类里并入了「制造业」，跨体系相加会得出「制造业与非必需消费品同级并列」
    的荒谬结论。故主口径 csrc 单列，其余体系只作参考披露、不参与合计。

    Args:
        top_n: 条数上限，``<=0`` 表示不截断。截断时保留前 N 并把余下合并成一条
            ``其他``（占比为其和）—— **合计必须仍等于截断前的总和**，否则脚注里的
            「合计 xx%」会与扇形图对不上。
    """
    from app.domains.funds.models import FundIndustryAlloc

    # 一次性把该基金所有体系的行捞出来，Python 侧分区（SQL 侧分组要多发一次请求，
    # 而这只基金最多几十行，量级差着数量级）。
    rows = (
        db.query(FundIndustryAlloc)
        .filter(FundIndustryAlloc.fund_code == fund_code)
        .order_by(FundIndustryAlloc.report_period.desc())
        .all()
    )
    if not rows:
        return []

    # 各体系的「最新报告期」独立取：可能只有 csrc 有数据而 gics 缺，
    # 此时不能拿全局 max 当 gics 的报告期（会取到一个不存在的期次）。
    latest_by_scheme: Dict[str, str] = {}
    for row in rows:
        cur = latest_by_scheme.get(row.scheme)
        if cur is None or row.report_period > cur:
            latest_by_scheme[row.scheme] = row.report_period

    buckets: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row.report_period != latest_by_scheme.get(row.scheme):
            continue
        bucket = buckets.get(row.scheme)
        if bucket is None:
            bucket = {
                'scheme': row.scheme,
                'scheme_label': SCHEME_LABELS.get(row.scheme, row.scheme),
                'report_period': row.report_period,
                'report_date': _iso(row.report_date),
                'items': [],
            }
            buckets[row.scheme] = bucket
        bucket['items'].append(
            {
                'industry_code': row.industry_code,
                'industry_name': row.industry_name or row.industry_code,
                'ratio': _to_float(row.ratio),
            }
        )

    out: List[Dict[str, Any]] = []
    # 主口径排第一（csrc），其余按 scheme 名排序，保证响应稳定可复现。
    for scheme in sorted(buckets, key=lambda s: (s != DEFAULT_SCHEME, s)):
        bucket = buckets[scheme]
        items = sorted(
            bucket['items'],
            key=lambda it: (it['ratio'] is None, -(it['ratio'] or 0)),
        )
        # 合计只累加有ratio 的行；缺失占比的行不按 0 参与（会把合计算低却看不出来）
        total = round(sum(it['ratio'] for it in items if it['ratio'] is not None), 2)
        if top_n > 0 and len(items) > top_n:
            head, tail = items[:top_n], items[top_n:]
            # 「其他」= 余下各项占比之和；只把**有ratio** 的计入（有值的缺失行
            # 静默吞掉会让合计对不上，而这里宁可少给一个空「其他」也不谎报）。
            tail_ratio = round(sum(it['ratio'] for it in tail if it['ratio'] is not None), 2)
            rest = [{'industry_code': '', 'industry_name': _OTHER_LABEL, 'ratio': tail_ratio or None}]
            if not tail_ratio:
                # 余下各项全无占比 → 不编造「其他 0%」，只标出「还有 N 项未计入占比」
                rest = [{'industry_code': '', 'industry_name': f'其他 {len(tail)} 项（无占比）', 'ratio': None}]
            items = head + rest
        bucket['items'] = items
        bucket['total_ratio'] = total or None
        bucket['is_primary'] = scheme == DEFAULT_SCHEME
        out.append(bucket)
    return out


def _holding_rows(db: Session, fund_code: str, top_n: Optional[int]) -> Dict[str, Any]:
    """持仓明细（个股层）。口径复用 ``manager_holdings._load_latest_holdings``。

    ``top_n`` 为 ``None`` 时**不截断**（全量口径下可能有几十上百只，
    详情页表格本来就要滚动，不需要人为砍断）；给定时按 ``rank`` 取前 N。
    """
    record = _load_latest_holdings(db, fund_code)
    if record is None:
        return {'rows': [], 'basis': None, 'basis_label': None, 'report_period': None, 'report_date': None}

    basis, holdings = record
    holdings = sorted(holdings, key=lambda h: h.rank if h.rank is not None else 9999)
    if top_n is not None and top_n > 0:
        holdings = holdings[:top_n]

    first = holdings[0] if holdings else None
    return {
        'rows': [
            {
                'rank': h.rank,
                'stock_code': h.stock_code,
                'stock_name': h.stock_name or None,
                'ratio': _to_float(h.ratio),
                'shares': _to_float(h.shares),
                'market_value': _to_float(h.market_value),
            }
            for h in holdings
        ],
        'basis': basis,
        # basis_label 必须下发：用户看到明细表时需要知道这是季报前十大还是半年报全量，
        # 否则会把「只披露了 10 只」误读成「只买了 10 只」（penetration 硬口径 7）。
        'basis_label': _BASIS_LABELS.get(basis, basis or '未知口径'),
        'report_period': first.report_period if first else None,
        'report_date': _iso(first.report_date) if first else None,
        # 前 N 条合计占比：给用户一个「集中度」锚点。top10 口径下是十大合计，
        # full 口径下是被截断的那部分的合计 —— 故字段名不写「十大合计」，只写「所示合计」。
        'shown_total_ratio': (
            round(sum(float(h.ratio) for h in holdings if h.ratio is not None), 2) if holdings else None
        ),
    }


def build_fund_holdings_detail(
    db: Session,
    fund_code: str,
    *,
    industry_top_n: int = DEFAULT_INDUSTRY_TOP_N,
    holding_top_n: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """构建单只基金的行业配置 + 持仓明细。

    Args:
        db: market 域会话。
        fund_code: 基金代码（业务键）。
        industry_top_n: 行业表格展示条数上限，超出合并为「其他」；``<=0`` 表示不截断。
        holding_top_n: 持仓明细展示条数上限；``None`` 表示不截断（全量口径可能几十上百只）。

    Returns:
        ``None`` 表示**基金不存在**（调用方转 404）；否则返回字典，
        其中 ``applicable`` 为 ``False`` 表示基金存在但无任何披露数据。

    Raises:
        ValueError: ``fund_code`` 为空。
    """
    from app.domains.funds.models import Fund

    code = (fund_code or '').strip()
    if not code:
        raise ValueError('缺少 fund_code')

    fund = db.query(Fund).filter(Fund.fund_code == code).first()
    if fund is None:
        return None

    industries = _industry_buckets(db, code, industry_top_n)
    holdings = _holding_rows(db, code, holding_top_n)

    has_industry = any(b['items'] for b in industries)
    has_holding = bool(holdings['rows'])

    return {
        'fund_code': code,
        'fund_name': fund.name,
        'applicable': has_industry or has_holding,
        # 两张卡各自独立可用：只有持仓没有行业配置（如 ETF 底层只有个股无行业映射）
        # 时，前端该显示哪张就显示哪张，而不是整块降级成「暂无数据」。
        'has_industry': has_industry,
        'has_holding': has_holding,
        'industries': industries,
        # 前端环形图直接吃这个形状（name/value），省得前端自己映射一层
        'industry_chart': [
            {'name': it['industry_name'], 'value': it['ratio']}
            for it in (industries[0]['items'] if industries else [])
            if it['ratio'] is not None and it['ratio'] > 0
        ],
        'holdings': holdings,
        'as_of': holdings.get('report_date') or (industries[0]['report_date'] if industries else None),
        'source': data_source_label(_HOLDING_SOURCE),
    }
