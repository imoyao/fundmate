# -*- coding: utf-8 -*-
"""东财引导的「申购代码 → 上市代码」别名解析器（打新折叠器的第二阶段接入）。

## 它解决什么

招商/同花顺等交割单的打新链只给**申购代码**（072/370/754/783 段），而上市后的
卖出用的是**上市代码**（113/123/127/118 段）。折叠器把 N 行中签链折成一条标准
``buy`` 记录时，必须知道上市代码才能和日后的卖出对上成本。交割单文件内**无法可靠
推导**这一映射（实证：同名配对 0 对、流水号不共享），故由本解析器从外部补齐。

## 为什么是「引导源」而不是「运行时实时调用」

fundmate 是本地优先。把东财接口直接塞进解析器 = 导入链路从此依赖外网。本解析器的
形态是**一次性引导**：

- ``warm(codes)``：对本地表还没有的申购码，向东财 ``RPT_BOND_CB_LIST`` 拉一次全量
  （分页），把 ``(apply_code → listed_code, issue_date)`` 落进 ``security_code_aliases``；
- ``resolve(apply_code, trade_date, name)``：先查本地表，**离线/无网也能用**；命中即返回，
  未命中（含订阅码跨年复用的日期消歧失败）返回 ``None``，由折叠器回落到
  ``link_warning`` 手动补全，**绝不静默算错成本归属**。

落库后，跨文件、跨券商、离线导入都走本地表，不再联网——本地优先的承诺没有被打破，
联网只是首次引导。

## 跨年复用消歧（关键正确性）

订阅码会跨年份复用（实证 ``070887`` → 2011 年中海转债）。``resolve`` 取同 ``apply_code``
下 ``issue_date`` 与中签日 ``trade_date`` **最近**的一条；若最近一条也超出
``date_window_days``（默认 5 年），视为无可靠匹配，返回 ``None`` 走人工补全，而不是
把一个 2011 年的老债错配给 2023 年的中签。

## 可测试性

``session_factory`` 与 ``http_get`` 均可注入：测试注入应用的 ``SessionLocal``（走路由到
测试库的会话工厂，表由 conftest 的 ``app`` fixture 建好）+ 假 http 即可，**不真联网**。
``requests`` 已被 ``app.core.requests_patch`` 在 app 导入期打上东财头与退避重试，
默认 ``http_get=requests.get`` 直接复用这套韧性。
"""

from datetime import date, datetime
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests
from loguru import logger
from sqlalchemy.orm import Session

from app.domains.securities.models import SecurityCodeAlias

EM_URL = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
EM_REPORT = 'RPT_BOND_CB_LIST'
EM_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
    )
}


class EastMoneyAliasResolver:
    """实现 ``SymbolAliasResolver`` 协议（结构子类型：有 ``resolve`` 即可），并附带
    ``warm`` 做批量引导。``NullAliasResolver`` / ``InMemoryAliasResolver`` 没有 ``warm``，
    折叠器用 ``hasattr`` 探测，缺失即跳过引导。"""

    def __init__(
        self,
        *,
        session_factory: Optional[Callable[[], Session]] = None,
        http_get: Callable[..., requests.Response] = requests.get,
        enabled: bool = True,
        date_window_days: int = 5 * 365,
        page_size: int = 1000,
        max_pages: int = 12,
    ):
        self._session_factory = session_factory
        self._http_get = http_get
        self.enabled = enabled
        self._date_window_days = date_window_days
        self._page_size = page_size
        self._max_pages = max_pages
        # apply_code -> [(listed_code, issue_date), ...]（空列表 = 已确认无匹配）。
        # 缓存的是「候选行」而非最终上市代码：跨年复用消歧依赖 trade_date，必须每次
        # 按中签日重选，不能把第一次 resolve 的结果钉死给同一个申购码的所有中签。
        self._cache: Dict[str, List[Tuple[str, Optional[date]]]] = {}

    # ── 协议方法 ──

    def resolve(self, apply_code: str, trade_date: date, name: str) -> Optional[str]:
        """返回上市代码；无匹配返回 None（折叠器回落 link_warning）。

        同一导入里同一申购码可能对应不同年份的多笔中签，每笔的中签日不同，
        故每次都按 ``trade_date`` 在候选行里重选最近的一条，而不是命中一次缓存就钉死。
        """
        if not self.enabled:
            return None
        code = (apply_code or '').strip()
        if not code:
            return None

        candidates = self._candidates(code)
        if not candidates:
            return None
        best = min(candidates, key=lambda pair: self._date_score(pair[1], trade_date))
        # 日期缺失的行仅在「无更优候选」时兜底；有日期的行超窗则判无匹配。
        if best[1] is not None and abs((best[1] - trade_date).days) > self._date_window_days:
            return None
        return best[0]

    # ── 批量引导（可选）──

    def warm(self, codes: Iterable[str]) -> None:
        """对本地表缺失的申购码，向东财拉全量可转债列表并落库。

        同一导入只调用一次；已落库的码不会重复联网。任何网络/解析异常都吞掉——
        回落到「未命中 → link_warning」，不阻断导入。
        """
        # 防御：若本次会话里 resolve 先于 warm 跑过，清掉旧缓存，让落库后的候选能生效。
        self._cache.clear()
        if not self.enabled or self._session_factory is None:
            return
        wanted = sorted({(c or '').strip() for c in codes if (c or '').strip()})
        if not wanted:
            return

        known = self._known_apply_codes(wanted)
        unknowns = [c for c in wanted if c not in known]
        if not unknowns:
            return

        try:
            fetched = self._fetch_all_cb()
        except Exception:  # noqa: BLE001 - 引导失败不应阻断导入
            logger.warning('东财可转债列表拉取失败，申购代码引导跳过，回落手动补全', exc_info=True)
            return

        self._persist(fetched)

    # ── DB 读取 ──

    def _known_apply_codes(self, codes: List[str]) -> set:
        with self._session_factory() as db:
            rows = (
                db.query(SecurityCodeAlias.apply_code)
                .filter(
                    SecurityCodeAlias.apply_code.in_(codes),
                    SecurityCodeAlias.asset_kind == 'cb',
                )
                .all()
            )
            return {r[0] for r in rows}

    def _candidates(self, code: str) -> List[Tuple[str, Optional[date]]]:
        """取某申购码的全体候选（上市码, 申购日），带缓存避免重复查库。

        返回普通元组列表（非 ORM 对象）：会话关闭后仍能安全读字段，不触发 detach 懒加载。
        """
        if code in self._cache:
            return self._cache[code]
        rows = self._rows_from_db(code)
        self._cache[code] = rows
        return rows

    def _rows_from_db(self, apply_code: str) -> List[Tuple[str, Optional[date]]]:
        if self._session_factory is None:
            return []
        with self._session_factory() as db:
            return [
                (r[0], r[1])
                for r in db.query(
                    SecurityCodeAlias.listed_code,
                    SecurityCodeAlias.issue_date,
                )
                .filter(
                    SecurityCodeAlias.apply_code == apply_code,
                    SecurityCodeAlias.asset_kind == 'cb',
                )
                .all()
            ]

    @staticmethod
    def _date_score(issue_date: Optional[date], trade_date: date) -> Tuple[int, int]:
        if issue_date is None:
            return (1, 0)  # 未知日期：次优先级，但仍可被选中
        return (0, abs((issue_date - trade_date).days))

    # ── 东财拉取 ──

    def _fetch_all_cb(self) -> Dict[str, List[Tuple[str, Optional[date]]]]:
        """分页拉全量可转债，返回 apply_code → [(listed_code, issue_date), ...]。

        全表约 2000+ 只，单页 pageSize 取 1000，循环 pageNo 直到不足一页。
        这是「一次批量」引导：一次导入只拉这一份，落库后后续导入不再联网。
        """
        out: Dict[str, List[Tuple[str, Optional[date]]]] = {}
        for page in range(1, self._max_pages + 1):
            params = {
                'reportName': EM_REPORT,
                'columns': 'SECURITY_CODE,CORRECODE,PUBLIC_START_DATE',
                'pageSize': self._page_size,
                'pageNo': page,
                'sortColumns': 'PUBLIC_START_DATE',
                'sortTypes': 1,  # 升序：先拿到最早的，翻页稳定
                'source': 'WEB',
                'client': 'WEB',
            }
            resp = self._http_get(EM_URL, params=params, headers=EM_HEADERS, timeout=20)
            resp.raise_for_status()
            result = resp.json().get('result') or {}
            data = result.get('data') or []
            for r in data:
                sub = (r.get('CORRECODE') or '').strip()
                listed = (r.get('SECURITY_CODE') or '').strip()
                if not sub or not listed:
                    continue
                out.setdefault(sub, []).append((listed, _parse_em_date(r.get('PUBLIC_START_DATE'))))
            if len(data) < self._page_size:
                break
        return out

    # ── 落库 ──

    def _persist(self, fetched: Dict[str, List[Tuple[str, Optional[date]]]]) -> None:
        if not fetched:
            return
        with self._session_factory() as db:
            for apply_code, pairs in fetched.items():
                existing = {
                    row.listed_code
                    for row in db.query(SecurityCodeAlias)
                    .filter(
                        SecurityCodeAlias.apply_code == apply_code,
                        SecurityCodeAlias.asset_kind == 'cb',
                    )
                    .all()
                }
                for listed_code, issue_date in pairs:
                    if listed_code in existing:
                        continue
                    db.add(
                        SecurityCodeAlias(
                            apply_code=apply_code,
                            listed_code=listed_code,
                            asset_kind='cb',
                            issue_date=issue_date,
                            source='eastmoney',
                            fetched_at=datetime.now(ZoneInfo('Asia/Shanghai')),
                        )
                    )
                    existing.add(listed_code)
            db.commit()


def _parse_em_date(value) -> Optional[date]:
    """东财日期形如 '2026-10-29 00:00:00'；取前 10 位按 ISO 解析，失败返回 None。"""
    if not value:
        return None
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None
