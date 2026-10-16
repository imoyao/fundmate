# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/10
# File : manager_tenure.py
# app/services/adapters/manager_tenure.py
"""基金经理任期抓取（天天基金 F10 经理页，#1970 扩展）。

回答「某人从哪天起管这只基金、管到哪天」，产出 `fund_managers.start_date` /
`end_date` 两个**已存在的模型列**。此前两列填充率为 0%，原因不是拿不到
（见下文「实测坑位」），而是无人写入。

## 为什么需要单独一个模块（而不是塞进 akshare_adapter）

1. **akshare 没有这个接口。** ``dir(akshare)`` 中与经理相关的只有
   ``fund_manager_em``（无任期维度）与 ``amac_manager_*``（管理人资质名录，非任职），
   故只能直连。
2. **返回 HTML 片段而非 JSON**，解析要剥 ``<td>``，与 akshare 的 DataFrame 通道
   是两类代码。
3. **依赖方向保持叶子**：仅依赖 ``requests`` + 标准库，不引入 akshare
   （避免把 V8 构造与限流风险带进一条纯 HTTP 通道）。

## 页面结构（2026-10-10 实测）

页面里有**两张列数不同的表**，语义完全不同，这是本解析器最容易写错的地方：

==========  ==================================================================
表列数      语义
==========  ==================================================================
**5 列**   **本基金**的分段任职：``任职日期 | 离任日期 | 经理姓名 | 天数 | 任期回报``
9 列       该经理**管过的其他基金**：``基金代码 | 名称 | 类型 | 任职日期 | ...``
==========  ==================================================================

**本模块只消费 5 列表（表 A）。** 理由：

- 表 A 每行就是「**某人 × 本基金**」的一任期，正是 ``fund_managers`` 要的粒度；
- 表 B 的行是「该经理 × 别的基金」，跨基金，需另抓该经理的每个基金页面才能拼全，
  成本高一个数量级；
- 表 A 的「经理姓名」可能是**多人**（如 ``'张坤 杨思亮 何一铖'``，共管）。

## 实测坑位（每条都真实踩过，改动前请读完）

1. **「历任基金经理」这个词组在页面上不存在。** 早期用它作段落锚点，
   ``t.count('历任')==3`` 但均不构成该词组 → 切片为空 → 解析恒为空列表。
   **改为不依赖任何文字锚点**，直接对全页 ``<tr>`` 按**列数**分流。
2. **页面是 UTF-8，且 ``apparent_encoding`` 会判成 gbk。** 按它解码会把「张坤」
   全解成乱码，进而误判为「无经理数据」→ 任期静默不更新。固定 ``utf-8``。
3. **「至今」是字符串不是空值**，必须转 ``None``；原样入库会让 ``end_date`` 变文本，
   后续任何日期比较抛 ``TypeError``。
4. **同一经理在同一基金可有多段任期。** 实测张坤在 005827 有两段
   （``2018-09-05 ~ 2026-05-22`` 与 ``2026-05-23 ~ 至今``）——他已卸任蓝筹精选、
   转任优质精选 QDII。所以**不能用「首次出现的那段」，必须取「该经理仍在任的那段」**。
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

_JJJL_URL = 'https://fundf10.eastmoney.com/jjjl_{code}.html'
_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120',
    'Referer': 'https://fundf10.eastmoney.com/',
}

_TIMEOUT = 20
# 与 direct_feeds 的东财通道同级：HTML 页面而非配额接口，但同属东财出口，
# 按限流型通道处理，不做高频连打。
_BACKOFF_BASE = 2.0
_RETRIES = 2

_CELL_CLEAN = re.compile(r'<.*?>', re.S)
_NAME_SPLIT = re.compile(r'[\s、,，/]+')

# 表 A 列数（表 B 为 9 列，不在此常量内）
_SEGMENT_COLS = 5
_IDX_START = 0
_IDX_END = 1
_IDX_NAMES = 2


def _clean(cell: str) -> str:
    """HTML 片段 → 纯文本（去标签、去不换行空格、去首尾空白）。"""
    return _CELL_CLEAN.sub('', cell).replace('\xa0', ' ').strip()


def _to_date(text: str) -> Optional[date]:
    """'2026-09-30' → date；非日期文本（含「至今」/空）一律 ``None``。

    **「至今」与「解析失败」返回同一个值是有意的**：业务上同义——「当前仍在任」。
    若要区分「仍在任」与「取不到」，由调用方用「本次是否解析到该经理的行」判断，
    不要靠 ``end_date`` 推断。
    """
    text = (text or '').strip()
    if not text or text in {'至今', '-', '--'}:
        return None
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except ValueError:
        return None


def _split_names(raw: str) -> List[str]:
    """'张坤 杨思亮 何一铖' → ['张坤', '杨思亮', '何一铖']（共管时多人）。

    分隔符覆盖实测出现过的空格、全角顿号、逗号、斜杠；空片段丢弃。
    """
    return [n for n in _NAME_SPLIT.split((raw or '').strip()) if n]


def _parse_page(html: str) -> List[Dict[str, Any]]:
    """抽出「本基金 × 各经理 × 各任期」分段（表 A）。

    **不依赖任何文字锚点**（坑位 1）：遍历全页 ``<tr>``，以「列数为 5 且首列是
    合法日期」作为分段行判据。表 B（9 列）被列数判据自动排除。
    """
    out: List[Dict[str, Any]] = []
    for row in re.findall(r'<tr>(.*?)</tr>', html, re.S):
        cells = [_clean(c) for c in re.findall(r'<td.*?>(.*?)</td>', row, re.S)]
        if len(cells) != _SEGMENT_COLS:
            continue
        start = _to_date(cells[_IDX_START])
        if start is None:
            continue
        names = _split_names(cells[_IDX_NAMES])
        if not names:
            continue
        for name in names:
            out.append(
                {
                    'manager_name': name,
                    'start_date': start,
                    # 「至今」→ None（仍在任）
                    'end_date': _to_date(cells[_IDX_END]),
                    'tenure_days_text': cells[3].strip(),
                    'tenure_return_text': cells[4].strip(),
                }
            )
    return out


def fetch_manager_tenures(fund_code: str) -> List[Dict[str, Any]]:
    """抓某只基金的经理任期分段（表 A）。

    Args:
        fund_code: 6 位基金代码（场外裸码，不带交易所前缀）。

    Returns:
        每段任期一条 dict，含 ``manager_name`` / ``start_date`` / ``end_date``；
        **解析失败或网络失败一律返回空列表**，由调用方降级为「—」，
        绝不用占位值顶替（诚实降级原则，详情页设计 §6）。
    """
    code = (fund_code or '').strip()
    if not code:
        return []

    url = _JJJL_URL.format(code=code)
    last_error: Optional[Exception] = None

    for attempt in range(_RETRIES + 1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            if resp.status_code != 200:
                raise RuntimeError(f'HTTP {resp.status_code}')
            # 坑位 2：固定 utf-8，不碰 apparent_encoding
            return _parse_page(resp.content.decode('utf-8', errors='replace'))
        except Exception as e:  # noqa: BLE001
            last_error = e
            if attempt < _RETRIES:
                time.sleep(_BACKOFF_BASE * (attempt + 1))

    logger.warning(f'抓取 {code} 任期失败（已重试 {_RETRIES} 次）: {last_error}')
    return []


def find_tenure(rows: List[Dict[str, Any]], manager_name: str) -> Optional[Dict[str, Any]]:
    """从任期分段里挑出「某经理**当前**在该基金的那一段」。

    **必须取仍在任的那段，而不是首次出现的那段**（坑位 4）：实测张坤在 005827
    有两段任期（``2018-09-05 ~ 2026-05-22`` 已卸任 / ``2026-05-23 ~ 至今`` 在任）。
    取错段会让「现任基金经理」显示成已离任的人。

    Args:
        rows: :func:`fetch_manager_tenures` 的返回值。
        manager_name: 经理姓名。

    Returns:
        命中的任期 dict（``end_date is None`` 表示仍在任）；未命中返回 ``None``。
    """
    name = (manager_name or '').strip()
    if not name:
        return None
    mine = [r for r in rows if r.get('manager_name') == name]
    if not mine:
        return None
    active = [r for r in mine if r.get('end_date') is None]
    return active[0] if active else mine[-1]


class ManagerTenureAdapter:
    """把本模块的抓取函数包成 SyncJob 认的「数据源」形状（#2082）。

    ## 为什么不直接借 ``NullAdapter``

    ``ManagerTenureSyncJob`` **确实在抓天天基金 F10**，而 ``NullAdapter`` 会让
    ``sync_logs.data_source`` 记成 ``'null'`` —— 审计表上看不出数据来自哪里，
    与「抓不到也不编」的口径自相矛盾。

    ## 为什么 ``get_version`` 报的是页面形态版本而不是代码版本

    F10 经理页的表格结构变过一次（见模块 docstring「实测坑位」：5 列 = 本基金任期、
    9 列 = 该经理管过的其他基金）。把它带进 ``sync_logs``，才能事后判断
    「某个时间点之后任期开始对不上」是不是**上游改版**导致 —— 而不是回头去猜。
    """

    #: 上游页面结构版本：改动 :func:`_parse_page` 的解析假设时必须 +1
    PAGE_FORMAT = 'f10-jjjl-v1'

    def get_name(self) -> str:
        return 'tiantian_f10'

    def get_version(self) -> str:
        return self.PAGE_FORMAT

    @staticmethod
    def fetch_tenures(fund_code: str) -> List[Dict[str, Any]]:
        """抓某只基金的任期分段（:func:`fetch_manager_tenures` 的实例方法形态）。"""
        return fetch_manager_tenures(fund_code)
