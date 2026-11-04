# -*- coding: utf-8 -*-
"""集思录**可转债下修历史**适配器（#2585）。

数据源：``GET https://www.jisilu.cn/data/cbnew/adj_logs/?bond_id=<6 位转债代码>``

实测契约（2026-10-24 首测 / 2026-10-26 全市场 1062 只复测，免 cookie / 免登录，纯 GET）：

- 有记录 → 返回一段 **HTML 片段**（不是 JSON）：``<table class="tablesorter">``；
- 无记录 → 纯文本 ``暂无数据``（12 字节，**没有** ``<table>``）；
- 响应体是 **UTF-8**（按 gbk 解码会乱码；与集思录主列表的 JSON 接口不同）。

``tbody`` 的行有**三种**形态（全市场实测：已生效 321 只 / 其余 741 只里绝大多数是
「暂无数据」，少量是下面两种非下修行）：

1. **已生效下修**——6 列：转债名称 / 股东大会日 / 下修前转股价 / 下修后转股价 /
   新转股价生效日期 / 下修底价。``kind='adjusted'``。
2. **未生效（源侧预估值）**——同样 6 列，但生效日期是 ``-``，且下修后转股价与
   下修底价带灰色斜体（页脚注：「灰色斜体为预估值（取 20 日均价和 T-1 日均价的高值）」）。
   实测 ``110095 双良转债`` 的股东大会日在未来。``kind='pending'``。
3. **非下修决议**——``<td colspan="4">股东大会未通过</td>`` 这种合并行，只有
   名称 / 股东大会日 / 结论文本。实测结论文本有「股东大会未通过」「股东大会不通过」
   「股价上涨，股东大会取消」「无需调整」「正股转债均退市」。``kind='not_passed'``。

## 为什么第 2、3 类不能抛错（2026-10-26 全市场实测修正）

首版把「单元格数 != 6」与「日期是 ``-``」一律当结构变更抛错。全市场跑一轮后
28 只失败，逐只看原始响应发现**它们都是上面第 2、3 类合法形态**，而且第 3 类
**常与已生效行同表**（如 ``110060 天路转债``：2022-08-12 已生效 + 2022-05-31 未通过；
``113654 永02转债``：2024-09-11 已生效 + 2025-02-13 无需调整）。整响应抛错
⇒ 这两只**已生效的那条也一起丢掉**，列表里显示 `—`，与「从未下修」无法区分。

所以判据改成「**认得的形态分类，不认得的形态抛错**」：三种行各有 ``kind``，
job 只把 ``adjusted`` 落库，其余两类计数上报（不静默）。真正的结构变更
（表头变了 / 单元格数既非 6 也非合并行 / 关键日期不可解析）仍然抛 ``ValueError``。

## 为什么「无生效日」不算已生效下修

「历史下修」要的是**已生效**的转股价调整；把预估（可能被股东大会否掉）计入
「下修次数」，等于把未发生的事写成事实。故 ``kind='pending'`` 不落库，由 job
在统计里显性报出条数。
"""

import threading
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

ADJ_LOGS_URL = 'https://www.jisilu.cn/data/cbnew/adj_logs/'

#: 落库时写进 ``source`` 列的值（与 `get_name()` 区分：后者是数据源适配器名）
SOURCE = 'jisilu_adj_logs'

#: 「无下修记录」的唯一合法空态标记（源侧原文）
_EMPTY_MARKER = '暂无数据'

#: 表头必须含这一列，否则判定拿到了另一张表（页面结构变更）
_REQUIRED_HEADER = '股东大会日'

#: 单元格数固定 6 列；既非 6 列也非合并行即为结构变更
_EXPECTED_CELLS = 6

#: 行形态（见模块 docstring）：已生效下修 / 未生效预估 / 非下修决议
ROW_ADJUSTED = 'adjusted'
ROW_PENDING = 'pending'
ROW_NOT_PASSED = 'not_passed'

HEADERS = {
    'accept': 'text/html, */*; q=0.01',
    'origin': 'https://www.jisilu.cn',
    'referer': 'https://www.jisilu.cn/data/cbnew/',
    'user-agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36'
    ),
    'x-requested-with': 'XMLHttpRequest',
}

#: 相邻任意两个请求的最小间隔（秒）。逐只抓取型 job 的礼貌节流；
#: 全市场（约 550 只）按 2s 跑一轮约 18 分钟，属一次性回填可接受量级。
REQUEST_INTERVAL = 2.0
MAX_RETRIES = 3
RETRY_BACKOFF = (2, 4, 8)
TIMEOUT = 20

_throttle_lock = threading.Lock()
_last_request_at = 0.0


def _parse_date(text: str) -> Optional[date]:
    """``2021-02-23`` → ``date``；空串 / ``-`` → None；其它形态抛错（结构变更）。

    为什么不像条款 job 那样宽松容错：这里是结构化 HTML 表格，日期列格式由
    页面模板固定。宽松解析会让「格式变了」表现为「日期为空」，最终落库 NULL，
    而唯一键含股东大会日 —— 空值会绕过幂等约束长出重复行。

    ``-`` 是源侧对「尚未生效」的**显式**占位（实测 4 只预估值行），与空串同义；
    它只出现在**生效日期**列，股东大会日若为 ``-`` 会在 job 校验里被记错误。
    """
    s = (text or '').strip()
    if not s or s in ('-', '--'):
        return None
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'股东大会日/生效日期格式非法: {s!r}') from exc


def _parse_price(text: str, label: str) -> Optional[Decimal]:
    """``3.100`` → ``Decimal('3.100')``；空串 → None；非数字抛错。"""
    s = (text or '').strip().replace(',', '')
    if not s or s in ('--', '-'):
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'{label} 非数值: {s!r}') from exc


def parse_adjust_logs(html: str) -> List[Dict[str, Any]]:
    """解析 adj_logs 的 HTML 片段 → 下修事件列表（保持源侧寄存器序：按日倒序）。

    每项都带 ``kind``（见模块 docstring）：

    - ``adjusted``：已生效下修，字段齐全（``name`` / ``shareholder_meeting_date``
      / ``convert_price_before`` / ``convert_price_after`` / ``effective_date``
      / ``adjust_floor_price``）；
    - ``pending``：6 列但生效日期为 ``-``/空（源侧预估值，尚未生效），数值列可能是预估；
    - ``not_passed``：``colspan`` 合并行（未通过 / 取消 / 无需调整 / 退市），
      只有名称、股东大会日与 ``status_text``。

    空态只有一种：响应体含 ``暂无数据`` 且没有表格 → ``[]``。
    其余异常（空 body / 有表格但表头不是下修表 / 行形态无法识别 / 数值日期不可解析）
    一律抛 ``ValueError``。
    """
    text = (html or '').strip()
    if not text:
        raise ValueError('adj_logs 响应为空（空 body 属上游异常，不是「无下修记录」）')

    if '<table' not in text.lower():
        if _EMPTY_MARKER in text:
            return []
        raise ValueError(f'adj_logs 响应既无表格也无「{_EMPTY_MARKER}」：{text[:120]!r}')

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(text, 'lxml')
    table = soup.find('table')
    if table is None:
        raise ValueError('adj_logs 响应含 <table 字样但解析不出表格节点')

    head = table.find('thead')
    header_text = head.get_text(' ', strip=True) if head else ''
    if _REQUIRED_HEADER not in header_text:
        raise ValueError(f'adj_logs 表头缺「{_REQUIRED_HEADER}」，疑似接口形态变更: {header_text[:120]!r}')

    body = table.find('tbody')
    if body is None:
        raise ValueError('adj_logs 表格缺 tbody')

    out: List[Dict[str, Any]] = []
    for tr in body.find_all('tr'):
        tds = tr.find_all('td')
        cells = [td.get_text(strip=True) for td in tds]
        if not cells:
            continue  # 空白分隔行

        if len(cells) == _EXPECTED_CELLS:
            name, meeting, before, after, effective, floor = cells
            effective_date = _parse_date(effective)
            out.append(
                {
                    'kind': ROW_ADJUSTED if effective_date is not None else ROW_PENDING,
                    'name': name or None,
                    'shareholder_meeting_date': _parse_date(meeting),
                    'convert_price_before': _parse_price(before, '下修前转股价'),
                    'convert_price_after': _parse_price(after, '下修后转股价'),
                    'effective_date': effective_date,
                    'adjust_floor_price': _parse_price(floor, '下修底价'),
                }
            )
            continue

        # 合并行：名称 + 股东大会日 + 结论（colspan 跨过其余 4 列）。
        # 判据是**结构**（最后一格 colspan >= 2），不是枚举结论文本 —— 源侧文本
        # 至少出现过 5 种写法（未通过 / 不通过 / 取消 / 无需调整 / 均退市）。
        if len(cells) == 3 and _has_colspan(tds[-1]):
            out.append(
                {
                    'kind': ROW_NOT_PASSED,
                    'name': cells[0] or None,
                    'shareholder_meeting_date': _parse_date(cells[1]),
                    'status_text': cells[2] or None,
                }
            )
            continue

        raise ValueError(f'adj_logs 行单元格数 {len(cells)} 无法识别（既非 {_EXPECTED_CELLS} 列也非合并行）: {cells!r}')
    return out


def _has_colspan(td) -> bool:
    """该 ``<td>`` 是否跨列（合并行的结构判据）。"""
    try:
        return int(td.get('colspan', 1)) >= 2
    except (TypeError, ValueError):
        return False


class JslBondAdjustAdapter:
    """集思录可转债下修历史适配器（独立于 akshare / 东财数据源体系）。"""

    def get_name(self) -> str:
        return 'jisilu_adj_logs'

    def get_version(self) -> str:
        return '1.0.0'

    def __init__(self) -> None:
        self.logger = logger
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    def _get(self, bond_code: str) -> str:
        """带节流 + 指数退避的 GET；返回解码后的 HTML 文本。"""
        global _last_request_at
        url = ADJ_LOGS_URL
        params = {'bond_id': bond_code}
        last_error: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            with _throttle_lock:
                wait = REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
                if wait > 0:
                    time.sleep(wait)
                try:
                    resp = self._session.get(url, params=params, timeout=TIMEOUT)
                finally:
                    _last_request_at = time.monotonic()

            if resp.status_code == 200:
                return _decode(resp)

            last_error = RuntimeError(f'adj_logs {bond_code} HTTP {resp.status_code}')
            # 4xx（限流 429 除外）是调用侧问题，重试没有意义
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                raise last_error
            backoff = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
            self.logger.warning(f'{bond_code} 第 {attempt + 1} 次请求失败（{last_error}），{backoff}s 后重试')
            time.sleep(backoff)
        raise RuntimeError(f'adj_logs {bond_code} 重试 {MAX_RETRIES} 次仍失败: {last_error}')

    def fetch_adjust_logs(self, bond_code: str) -> List[Dict[str, Any]]:
        """抓取单只转债的下修历史；无记录返回 ``[]``（而非抛错）。"""
        return parse_adjust_logs(self._get(bond_code))


def _decode(resp: requests.Response) -> str:
    """UTF-8 优先解码（源的 Content-Type 不一定带 charset，requests 会退回 latin-1）。"""
    raw = resp.content or b''
    for encoding in ('utf-8', 'gb18030'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f'adj_logs 响应无法按 utf-8 / gb18030 解码（{len(raw)} 字节）')


__all__ = [
    'ADJ_LOGS_URL',
    'SOURCE',
    'JslBondAdjustAdapter',
    'parse_adjust_logs',
]
