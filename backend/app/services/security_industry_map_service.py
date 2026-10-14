# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/12
# File : security_industry_map_service.py
# app/services/security_industry_map_service.py
"""证券 → 行业映射的**采集与落库**（#1981 · 组合穿透补强）。

读侧在 :mod:`app.services.penetration`，那里是纯读（不触网不写库）；本模块负责把
外部数据源变成 ``security_industry_maps`` 的行。两者严格分开，故读侧仍可在请求路径上
安全调用。

## 为什么是这两个源（#1981 选型实测，2026-10-12）

| 体系 | 通道 | 全量成本 | 实测 |
|---|---|---|---|
| ``sw1`` 申万一级 | 申万宏源研究官网 ``www.swsresearch.com`` | **31 个请求**（31 个一级行业 × 1） | 3/3 通过 |
| ``csrc`` 证监会门类 | 巨潮资讯 ``webapi.cninfo.com.cn`` | 5000+ 请求（逐只） | 3/3 通过 |
| —— 东财 | —— | —— | **已否决** |

**东财为什么否决**（实测，非推断）：同一端点 ``stock_board_industry_name_em`` 在数分钟内
从成功（496 行）变成 ``RemoteDisconnected``，重跑即挂；且项目 ``core/requests_patch`` 已
给足（东财浏览器头 + ``Referer: https://quote.eastmoney.com/`` + 3 次指数退避+
``trust_env=False`` 强制直连）仍然失败——**不是缺 Referer，是端点级/时段级不稳定**。
批量同步一旦中途断掉就会留下半截数据（#1431 的后果：行业拥挤度表停更 40 天零行），
故不作批量通道。详见 #1431 / #897。

**换上游而非换封装**（#897 核心）：akshare 的这些函数是各上游的不同封装，真冗余必须换
上游。这里用的是**巨潮**与**申万宏源**两家，与被否决的东财互不相干。

## 为什么两套体系并存，而不是只留一套

它们回答的不是同一个问题：

- ``csrc``（证监会门类，19 个）：粒度粗，但**与基金穿透现有口径一致**
  （``fund_industry_allocs.scheme='csrc'``）。只有同口径才能把「基金穿透出的行业」与
  「直持股票的行业」相加，得到**全组合真实行业暴露**——这是 #1981 的原始目标。
- ``sw1``（申万一级，31 个）：粒度细、市场研究的事实标准、行业 ETF 的编制口径。
  但与 ``csrc`` **语义不重叠，禁止相加**（否则会得出「制造业与非必需消费品荒谬同级
  并列」这类结论，见 ``penetration`` 模块 docstring 口径 3）。

故读侧主口径用 ``csrc``（守恒成立），``sw1`` 走 ``other_schemes`` 单列。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.securities.models import SecurityIndustryMap
from app.services.fund_utils import normalize_fund_code

SCHEME_CSRC = 'csrc'
SCHEME_SW1 = 'sw1'

SOURCE_CNINFO = 'cninfo'
SOURCE_SWSRESEARCH = 'swsresearch'

#: 证监会门类（2012 版，现行 19 个）**中文名 → 单字母代码**。
#:
#: 为什么需要这张字典：巨潮 ``stock_profile_cninfo`` 的「所属行业」给的是**中文门类名**
#: （实测 600519→「制造业」、000001→「金融业」），而本项目基金侧
#: ``fund_industry_allocs.industry_code`` 存的是**单字母**（``C`` / ``J``）。不做这层
#: 对齐，直持与基金就是两套不可比的编码，验收第 1 条「并入主口径行业分布」无从谈起。
#:
#: 为何敢硬编码而不查表：证监会门类是**监管口径**，2012 年发布至今未做结构性调整，
#: 且它本身就是一张**封闭的 19 项**清单——没有「新增一个门类」这种变更模式。
#: 键统一去顿号后匹配（源偶尔返回「农、林、牧、渔业」这种形态），见 :func:`csrc_code_of`。
CSRC_SECTOR_BY_NAME: Dict[str, str] = {
    '农林牧渔业': 'A',
    '采矿业': 'B',
    '制造业': 'C',
    '电力热力燃气及水生产和供应业': 'D',
    '建筑业': 'E',
    '批发和零售业': 'F',
    '交通运输仓储和邮政业': 'G',
    '住宿和餐饮业': 'H',
    '信息传输软件和信息技术服务业': 'I',
    '金融业': 'J',
    '房地产业': 'K',
    '租赁和商务服务业': 'L',
    '科学研究和技术服务业': 'M',
    '水利环境和公共设施管理业': 'N',
    '居民服务修理和其他服务业': 'O',
    '教育': 'P',
    '卫生和社会工作': 'Q',
    '文化体育和娱乐业': 'R',
    '综合': 'S',
}

#: 别名：源侧偶尔带顿号（如「电力、热力、燃气及水生产和供应业」），去掉顿号即可命中主表。
CSRC_SECTOR_ALIASES: Dict[str, str] = {
    '电力、热力、燃气及水生产和供应业': 'D',
    '信息传输、软件和信息技术服务业': 'I',
}


def csrc_code_of(industry_name: Optional[str]) -> Optional[str]:
    """中文门类名 → 证监会单字母代码；认不出返回 ``None``（**不猜**）。

    认不出就返回 None 而不是回退到某个字母：宁可让该标的留在
    ``industry_map_missing``，也不能把它错归到「制造业」那种什么都往里装的大类里——
    错归会污染行业分布且**极难被发现**（数字看起来仍然守恒，事后没人知道为什么）。
    """
    if not industry_name:
        return None
    raw = str(industry_name).strip()
    if not raw:
        return None
    if raw in CSRC_SECTOR_ALIASES:
        return CSRC_SECTOR_ALIASES[raw]
    squeezed = raw.replace('、', '').replace('，', '').replace(',', '').strip()
    return CSRC_SECTOR_BY_NAME.get(squeezed)


@dataclass
class IndustryMapRow:
    """一条待落库的映射。"""

    symbol: str
    industry_code: str
    industry_name: Optional[str] = None
    source_ref: Optional[str] = None
    effective_date: Optional[date] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol,
            'industry_code': self.industry_code,
            'industry_name': self.industry_name,
            'source_ref': self.source_ref,
            'effective_date': self.effective_date,
        }


def _norm_symbol(raw: Any) -> str:
    """来源侧代码归一为**裸 6 位码**，与 :func:`penetration._business_code` 对齐。

    实测两源的「证券代码」已是裸码（申万 ``000505``、巨潮 ``600519``），但仍走统一归一：
    任一来源改用 ``SH600000`` 形态时，读侧就不必跟着改。
    """
    return normalize_fund_code(str(raw or '').strip())


def _parse_date(value: Any) -> Optional[date]:
    """把来源侧日期字符串（``2021-12-13`` / 带时间）解析成 ``date``；认不出返回 None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y%m%d'):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


# ── 采集：申万一级（全量，31 个请求）────────────────────────────────────


def fetch_sw1_industry_map() -> List[IndustryMapRow]:
    """拉取**申万一级**全量成分映射（31 个一级行业 × 1 请求）。

    上游是申万宏源研究官网 ``www.swsresearch.com``（编制方本体，非二手封装）。
    实测单个行业 801010「农林牧渔」有 104 只成分。

    单个行业取数失败**不中断整体**：记 warning 后继续下一行业（少一类比全挂好，
    缺口会在下一次刷新时补上）。全部失败则返回空列表，由调用方决定是否报错。
    """
    import akshare as ak

    rows: List[IndustryMapRow] = []
    try:
        industries = ak.sw_index_first_info()
    except Exception as e:  # 清单都拿不到 = 通道不可用，本次不做任何事
        logger.warning(f'[#1981] 申万一级行业清单获取失败，跳过 sw1 全量刷新: {e}')
        return rows

    for _, ind in industries.iterrows():
        # 「行业代码」形如 `801010.SI`，后缀是申万行情系统标记，非分类代码的一部分
        raw_code = str(ind.get('行业代码') or '').strip()
        sw_code = raw_code.split('.')[0]
        name = str(ind.get('行业名称') or '').strip() or None
        eff = _parse_date(ind.get('发布日期'))
        if not sw_code:
            continue
        try:
            cons = ak.index_component_sw(symbol=sw_code)
        except Exception as e:
            logger.warning(f'[#1981] 申万 {sw_code} {name} 成分股获取失败，跳过该行业: {e}')
            continue
        expected = ind.get('成分数量')
        if expected and len(cons) < int(expected):
            # 实测 801010 声明 104 只、实取 103 行（新股/停牌口径差）。记 warning 但
            # **不阻断**：宁可少 1 只落进 industry_map_missing，也不能让整批丢掉。
            logger.warning(f'[#1981] 申万 {sw_code} 成分数不一致：声明 {expected} 实取 {len(cons)}')
        for _, row in cons.iterrows():
            symbol = _norm_symbol(row.get('证券代码'))
            if not symbol:
                continue
            rows.append(
                IndustryMapRow(
                    symbol=symbol,
                    industry_code=sw_code,
                    industry_name=name,
                    source_ref=raw_code,
                    effective_date=eff,
                )
            )
    logger.info(f'[#1981] 申万一级成分合计 {len(rows)} 条（{len(industries)} 个行业）')
    return rows


# ── 采集：证监会门类（单只，巨潮）──────────────────────────────────────


def fetch_csrc_industry_of(symbol: str) -> Optional[IndustryMapRow]:
    """取**单只**证券的证监会门类（巨潮资讯 ``webapi.cninfo.com.cn``）。

    只支持 A 股代码（6 位数字）。港股 / 美股 / 可转债不在巨潮该接口的覆盖范围，
    返回 ``None`` —— 它们会留在 ``industry_map_missing``，这是**诚实降级**而非缺口。

    全量刷不动（逐只 5000+ 请求），故本函数只用于**按需补**（组合里真实出现的标的）。
    """
    import akshare as ak

    code = _norm_symbol(symbol)
    if not code or not code.isdigit():
        return None
    try:
        profile = ak.stock_profile_cninfo(symbol=code)
    except Exception as e:
        logger.warning(f'[#1981] 巨潮个股档案获取失败 {code}: {e}')
        return None
    if profile is None or profile.empty:
        return None
    # 按列名定位「所属行业」：源方偶有列序调整，取列比按索引取行更耐改
    name_col = next((c for c in profile.columns if str(c).strip() == '所属行业'), None)
    if name_col is None:
        logger.warning(f'[#1981] 巨潮返回无「所属行业」列（{code}）')
        return None
    sector_name = str(profile.iloc[0][name_col] or '').strip()
    industry_code = csrc_code_of(sector_name)
    if not industry_code:
        logger.warning(f'[#1981] 证监会门类名未收录 {code}: {sector_name!r}（不猜，留 industry_map_missing）')
        return None
    return IndustryMapRow(
        symbol=code,
        industry_code=industry_code,
        industry_name=sector_name,
        source_ref='p_sysapi1133',
    )


# ── 落库 ────────────────────────────────────────────────────────────────


def upsert_industry_map(
    db: Session,
    rows: Iterable[IndustryMapRow],
    scheme: str,
    source: str,
) -> Dict[str, int]:
    """按 ``(symbol, scheme)`` 幂等 upsert，返回 ``{'inserted', 'updated', 'skipped'}``。

    **不删本次没出现的行**：先 delete-then-insert 会让「同步中途断掉」变成「表被清空」
    ——上一轮好数据一起没了（#1431 那类「停更 40 天零行」正是这么来的）。
    陈旧行的清理由同步 job 按「本次成功刷过的 code 集合」显式处理。
    """
    stats = {'inserted': 0, 'updated': 0, 'skipped': 0}
    existing = {
        (row.symbol, row.scheme): row
        for row in db.execute(select(SecurityIndustryMap).where(SecurityIndustryMap.scheme == scheme)).scalars()
    }
    for item in rows:
        if not item.symbol or not item.industry_code:
            stats['skipped'] += 1
            continue
        payload = item.as_dict()
        target = existing.get((item.symbol, scheme))
        if target is None:
            db.add(SecurityIndustryMap(scheme=scheme, source=source, **payload))
            stats['inserted'] += 1
            continue
        changed = False
        for key, value in payload.items():
            if value is not None and getattr(target, key) != value:
                setattr(target, key, value)
                changed = True
        if target.source != source:
            target.source = source
            changed = True
        if changed:
            stats['updated'] += 1
        else:
            stats['skipped'] += 1
    db.commit()
    return stats
