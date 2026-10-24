# -*- coding: utf-8 -*-
"""集思录**可转债下修历史**适配器（#2585）。

数据源：``GET https://www.jisilu.cn/data/cbnew/adj_logs/?bond_id=<6 位转债代码>``

实测契约（2026-10-24，免 cookie / 免登录，纯 GET）：

- 有记录 → 返回一段 **HTML 片段**（不是 JSON）：``<table class="tablesorter">``，
  ``tbody`` 每行 6 列 —— 转债名称 / 股东大会日 / 下修前转股价 / 下修后转股价 /
  新转股价生效日期 / 下修底价；
- 无记录 → 纯文本 ``暂无数据``（12 字节，**没有** ``<table>``）；
- 响应体是 **UTF-8**（按 gbk 解码会乱码；与集思录主列表的 JSON 接口不同）。

## 为什么解析失败一律抛错，不返回空列表

「这只债从没下修过」与「我们没抓到」在数据层必须能区分开。若把源形态变更
（风控页 / 改版 / 空 body）降级成 ``[]``，下修列会静默显示「无下修记录」，
而它读起来与事实完全一样——这是 #2543（列名漂移被吞成空）的同一类坑。
故本模块只把**明确的** ``暂无数据`` 认作空列表，其余一律 ``ValueError``。
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

#: 单元格数固定 6 列；不等即为结构变更
_EXPECTED_CELLS = 6

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
    """``2021-02-23`` → ``date``；空串 → None；其它形态抛错（结构变更）。

    为什么不像条款 job 那样宽松容错：这里是结构化 HTML 表格，日期列格式由
    页面模板固定。宽松解析会让「格式变了」表现为「日期为空」，最终落库 NULL，
    而唯一键含股东大会日 —— 空值会绕过幂等约束长出重复行。
    """
    s = (text or '').strip()
    if not s:
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
    """解析 adj_logs 的 HTML 片段 → 下修记录列表（寄存器序：源侧按日倒序）。

    返回每项：``name`` / ``shareholder_meeting_date`` / ``convert_price_before``
    / ``convert_price_after`` / ``effective_date`` / ``adjust_floor_price``。

    空态只有一种：响应体含 ``暂无数据`` 且没有表格 → ``[]``。
    其余异常（空 body / 有表格但表头不是下修表 / 单元格数不符 / 数值日期不可解析）
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
        cells = [td.get_text(strip=True) for td in tr.find_all('td')]
        if not cells:
            continue  # 空白分隔行
        if len(cells) != _EXPECTED_CELLS:
            raise ValueError(f'adj_logs 行单元格数 {len(cells)} != {_EXPECTED_CELLS}: {cells!r}')
        name, meeting, before, after, effective, floor = cells
        out.append(
            {
                'name': name or None,
                'shareholder_meeting_date': _parse_date(meeting),
                'convert_price_before': _parse_price(before, '下修前转股价'),
                'convert_price_after': _parse_price(after, '下修后转股价'),
                'effective_date': _parse_date(effective),
                'adjust_floor_price': _parse_price(floor, '下修底价'),
            }
        )
    return out


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
