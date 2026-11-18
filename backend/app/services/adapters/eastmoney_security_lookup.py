# -*- coding: utf-8 -*-
# app/services/adapters/eastmoney_security_lookup.py
"""按代码查**单只**场内证券（代码 → 名称/品类），供名录缺口定向补录使用。

## 为什么需要它

`securities` 名录只靠 `stock_list` 全量刷新（`_NOT_SCHEDULED` 登记为「月度 / 手动」）。
于是「流水里有、名录里没有」的标的会被 `PriceHistorySyncJob._get_security_map`
**静默丢掉** —— 它只返回名录里存在的行，查不到的标的连一次请求都发不出去，
表现是「这笔持仓永远没有日线」（`price_history_job.py` 的 `unlisted` 字段即此形态，
本机实测 8 个 LOF 中招）。

新股把这个缺口放大成不可用：上市后要等下一次 `stock_list`，而它是月度/手动。

## 为什么是单只查询，而不是再拉一次全量

实测（2026-11-08）：

- `stock_info_a_code_name()` 全量 5579 行：**11.67s**
- `fetch_security_catalog()` 三源合并（A股 + ETF + 可转债）：**29.4 分钟**
  （东财 ETF 名录 502 后回退同花顺）
- 东财 `push2/qt/stock/get` 单只：**0.17s**

补 3 个标的用全量是 11.67s 起步，用单只是 0.5s。名录变动本来就是日均个位数，
拿全量去追 0.1% 的增量是杠杆用错了 —— 全量仍保留，但降级为「灾备重建」。

## 为什么必须用模块级 Session

`requests_patch` 的注释记着实测：首次请求要付 TLS 握手 + DNS **1.8~2.8s**，
连接复用后单次只要 **43~87ms**。补录是**逐只**循环，不复用连接的话 10 只就是 20s+，
「0.17s/只」这个前提直接失效。故照 `eastmoney_adapter._get_suggest_session`
的同一套做法：模块级 Session + 锁（`requests.Session` 不是线程安全的）。

## 覆盖边界（已实测）

- A 股（沪深）、ETF、可转债、北交所均可查（`0.920019` → 铜冠矿建）；
- **未上市**代码返回 `NO DATA` —— 上游自己也没有。打新缴款日这种「还没上市」的标的
  补不了，只能靠手填；这不是本模块的缺陷，是数据的物理边界。
"""

import threading
from typing import Any, Dict, Optional

import requests
from loguru import logger

from app.core.symbol_utils import derive_security_type, market_of_cn_a_code

#: 单只行情接口。`fields` 只要代码与名称：
#: - `f57` 代码、`f58` 名称。其余字段（价格等）本模块不消费，不请求即为最省。
_QUOTE_URL = 'https://push2.eastmoney.com/api/qt/stock/get'

#: 上游接口版本：改动 secid 规则或字段映射时必须 +1（会记进 sync_logs）。
QUOTE_FORMAT = 'em-push2-quote-v1'

_QUOTE_TIMEOUT = 6.0

_session: Optional[requests.Session] = None
_session_lock = threading.Lock()


def _get_session() -> requests.Session:
    """取模块级 Session（惰性建 + 双检锁），复用 TLS 连接。"""
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                # requests_patch（应用启动时安装）会给 Session 挂重试适配器与东财头，
                # 此处直接新建即可继承，无需自己配。
                _session = requests.Session()
    return _session


def to_secid(symbol: str) -> Optional[str]:
    """`SH600519` / `600519` → 东财 `1.600519`；无法判定市场返回 None。

    东财 secid 的市场位：沪市 `1`，深市与北交所同为 `0`
    （实测 `0.920019` → 铜冠矿建，故北交所不能按「9 开头 → 沪市」类推）。

    裸码走 `market_of_cn_a_code` 判定 —— 它与 `fetch_security_catalog` 落库时
    用的是同一套规则，避免「补录时判成沪、名录里存的是深」这种对不上的分裂。
    """
    text = (symbol or '').strip().upper()
    if not text:
        return None

    if len(text) == 8 and text[:2] in ('SH', 'SZ', 'BJ') and text[2:].isdigit():
        return ('1.' if text[:2] == 'SH' else '0.') + text[2:]

    if len(text) == 6 and text.isdigit():
        market = market_of_cn_a_code(text)
        if market:
            return ('1.' if market == 'SH' else '0.') + text

    return None


def _normalize_symbol(raw_code: str, requested_symbol: str) -> Optional[str]:
    """上游回传的 6 位代码 → 落库形态 `SH600519`（与 `fetch_security_catalog` 一致）。

    ## 市场优先取**请求侧**，不是从代码反推

    实测（2026-11-08）：请求 `0.110001`（深市）上游照样回 `f57='110001'`。若按代码
    反推，`market_of_cn_a_code('110001')` 给出 `SH` —— 于是一次「深市查不到」被写成
    「沪市可转债」，凭空造出一条错品类记录。以请求侧为准后，品类判定会得到
    `derive_security_type('110001', 'SZ') == None`，正确落到「保留缺口」。

    只有两种情况才回落到代码反推：调用方给的是裸码（`600519`），或上游回了
    **另一个**代码（说明请求的那个 secid 已失效，此时以上游为准更可信）。
    """
    code = (raw_code or '').strip()
    if len(code) != 6 or not code.isdigit():
        return None

    requested = (requested_symbol or '').strip().upper()
    if len(requested) == 8 and requested[:2] in ('SH', 'SZ', 'BJ') and requested[2:].isdigit():
        if requested[2:] == code:
            return f'{requested[:2]}{code}'

    market = market_of_cn_a_code(code)
    return f'{market}{code}' if market else None


def fetch_security_by_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """查单只证券的规范记录；查不到或出错返回 None（**绝不编造**）。

    Args:
        symbol: `SH600519` / `SZ000001` / 裸 6 位代码。

    Returns:
        `{'symbol', 'name', 'market', 'type', 'currency'}` —— 与
        `AkshareAdapter.fetch_security_catalog` 的记录形状一致，可直接喂
        `StockListSyncJob._save_data` 的 upsert。
        `type` 无法判定（如深市 11xxxx 这种既非转债也非 ETF 的边角）时返回 None，
        由调用方按「补不了」处理 —— 宁可留着缺口让它可见，也不写一条错品类的记录。
    """
    secid = to_secid(symbol)
    if not secid:
        return None

    try:
        resp = _get_session().get(
            _QUOTE_URL,
            params={'secid': secid, 'fields': 'f57,f58'},
            timeout=_QUOTE_TIMEOUT,
        )
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001 — 单只失败不阻断整批补录
        logger.warning(f'名录补录：{symbol} 查询失败（按缺口保留）：{exc}')
        return None

    data = (payload or {}).get('data')
    if not data:
        # 未上市 / 已退市 / 代码不存在，上游明确没有
        return None

    code = str(data.get('f57') or '').strip()
    name = str(data.get('f58') or '').strip()
    if not code or not name:
        return None

    normalized = _normalize_symbol(code, symbol)
    if not normalized:
        return None

    # 交易所直接取归一结果的前缀（与落库形态同源），不再从代码反推一次：
    # 两处各判一次就会分叉，理由见 `_normalize_symbol` 的 docstring。
    sec_type = derive_security_type(code, normalized[:2])
    if not sec_type:
        logger.warning(f'名录补录：{normalized} 品类无法判定，跳过（保留缺口）')
        return None

    return {
        'symbol': normalized,
        'name': name[:100],
        'market': 'CN_A',
        'type': sec_type,
        'currency': 'CNY',
    }


class EastmoneySecurityLookupAdapter:
    """把本模块包成 `SyncJob` 认的「数据源」形状。

    ## 为什么不直接借 ``AkshareAdapter``

    `SecuritiesBackfillJob` 确实在打东财 push2，而借 ``NullAdapter`` 会让
    `sync_logs.data_source` 记成 ``'null'`` —— 审计表上看不出这批名录是哪来的。
    与 `ManagerTenureAdapter`（#2082）同一理由。

    ## 为什么 ``get_version`` 报的是接口形态版本

    可以把「某个时间点之后补录开始失败」与「上游改了 secid 规则 / 字段映射」
    对上号，而不必回头猜。改 :func:`fetch_security_by_symbol` 的解析假设时 +1。
    """

    def get_name(self) -> str:
        return 'eastmoney_push2'

    def get_version(self) -> str:
        return QUOTE_FORMAT

    @staticmethod
    def fetch_security_by_symbol(symbol: str) -> Optional[Dict[str, Any]]:
        return fetch_security_by_symbol(symbol)
