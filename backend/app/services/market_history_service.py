# -*- coding: utf-8 -*-
"""探市大类资产「长历史日线」的按需回填编排（#1460 P2）。

与 P1 的分工：P1 落的是「每日一份结论快照」（涨跌 / 分位 / 异动），读库即回；
本模块落的是**原始日线序列**，只在某个资产真正被查看（详情曲线 / 后续简报消费）时
才向源拉一次全历史，此后每次只补缺失日期——这是 #1460 第 2 步「按需回填」的口径，
不是「20 个资产每天全量翻页拉一遍」（那会把数据源压力摊到每一天，数据策略明确反对）。

三条判据：

1. **库空 → 回填**：该品种第一次被查看，取一次全历史并落库；
2. **库内落后 → 增量补数**：最新交易日早于「该分类此刻应已收盘的最近一个交易日」时再取一次，
   源返回的是全量序列，但写库只写缺失日期（唯一键去重）；
3. **取数失败 → 库内兜底**：库里有历史就继续用（``stale=True`` 如实标注），
   库空才报错——「源挂了就整页空白」是 #1460 要消掉的问题。

「应已收盘」按分类收盘时刻近似（见 ``_CATEGORY_CLOSE_HOUR``），只做**是否值得再取一次**的
判断，不追求精确交易日历：节假日最多多取一次，周末回退到周五，宁可多取一次也不让序列停在
半年前。
"""

from contextlib import contextmanager
from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any, Dict, Iterator, List, Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from app.core.database import market_session
from app.core.exceptions import ErrorCode, SBException
from app.core.time_utils import now_shanghai
from app.services import market_history_store
from app.services.market_service import ASSET_CONFIG, fetch_asset_series, invalidate_asset_series

#: 详情曲线的默认回看交易日数（与相对位置分位窗口一致）
DEFAULT_DAYS = 500
#: 回看窗口上下限：太小画不出曲线，太大会把一次响应撑成几 MB
MIN_DAYS = 10
MAX_DAYS = 5000

#: 各分类「当日日线已可用」的收盘时刻（北京时间，整点近似）
#: - 海外（美股）：日线日期是**美东日期**，北京 05:00 收盘后才出现「昨天」那一根，故单独处理
#: - 商品：国内期货日线含夜盘，早上 08:00 后前一日数据稳定
#: - 汇率：中行牌价每个工作日上午更新，取 10:00
_CATEGORY_CLOSE_HOUR: Dict[str, int] = {
    'A股': 15,
    '港股': 16,
    '债券': 18,
    '商品': 8,
    '汇率': 10,
}


def _prev_weekday(d: date_cls) -> date_cls:
    """周末回退到最近的周五（无交易日历可用时的最小近似）。"""
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def expected_latest_date(asset: Dict[str, Any], now: Optional[datetime] = None) -> date_cls:
    """该资产「此刻库里最高应该到哪天」。

    只用于决定「要不要再向源取一次」：判松了会多取（无害），判紧了会让曲线停在旧日期。
    既然宁可多取，就按「已过收盘时刻 ⇒ 今天应有数据」来算，末了再把周末回退掉。
    """
    now = now or now_shanghai()
    today = now.date()

    if asset.get('category') == '海外':
        # 美股日线日期取美东日期：北京 05:00 收盘后最新的那根是「昨天」，
        # 05:00 之前只到「前天」（此时美东还在上一个交易日盘中）。
        latest = today - timedelta(days=1 if now.hour >= 5 else 2)
    else:
        close_hour = _CATEGORY_CLOSE_HOUR.get(asset.get('category'), 15)
        latest = today if now.hour >= close_hour else today - timedelta(days=1)

    return _prev_weekday(latest)


@contextmanager
def _session(db: Optional[Session]) -> Iterator[Session]:
    """复用调用方会话（测试 / 请求内多次调用），否则开一个 market 域会话。"""
    if db is not None:
        yield db
        return
    with market_session() as session:
        yield session


def _find_asset(asset_key: str) -> Optional[Dict[str, Any]]:
    for asset in ASSET_CONFIG:
        if asset['key'] == asset_key:
            return asset
    return None


def resolve_asset_history(
    asset_key: str,
    days: int = DEFAULT_DAYS,
    force: bool = False,
    now: Optional[datetime] = None,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """返回某资产的近 N 个交易日收盘序列（按需回填 + 增量补数 + 失败兜底）。

    失败语义（与探市页「永远可渲染」的硬约束一致）：
    - 库里已有历史、本次取数失败 ⇒ 正常返回库内数据，``stale=True`` + ``reason`` 说明；
    - 库里没有任何历史且取数失败 ⇒ 抛 SBException(DATA_SOURCE_ERROR, 503)，
      由视图转成错误信封，前端显示「暂时取不到」而不是空图。
    """
    asset = _find_asset(asset_key)
    if asset is None:
        raise SBException(ErrorCode.RESOURCE_NOT_FOUND.code, f'未知资产：{asset_key}', 404)
    if not asset.get('available', True):
        raise SBException(
            ErrorCode.RESOURCE_NOT_FOUND.code,
            asset.get('reason') or '该资产暂无可靠数据源',
            404,
        )

    days = max(MIN_DAYS, min(int(days or DEFAULT_DAYS), MAX_DAYS))
    expected = expected_latest_date(asset, now)

    with _session(db) as session:
        count, last_date = market_history_store.coverage(session, asset_key)

    added = 0
    fetched = False
    stale = False
    reason: Optional[str] = None
    need_fetch = force or count == 0 or (last_date is not None and last_date < expected)

    if need_fetch:
        fetched = True
        try:
            if force:
                invalidate_asset_series(asset_key)
            dates, closes = fetch_asset_series(asset)
            with _session(db) as session:
                added = market_history_store.save_series(
                    session,
                    asset_key,
                    dates,
                    closes,
                    source=str(asset.get('source') or 'akshare')[:20],
                )
        except Exception as e:  # noqa: BLE001 - 取数失败一律走库内兜底 / 明确报错
            if count == 0:
                logger.warning('资产 {}({}) 历史行情取数失败且库内无历史: {}', asset['name'], asset_key, e)
                raise SBException(
                    ErrorCode.DATA_SOURCE_ERROR.code,
                    f'{asset["name"]}的历史行情暂时取不到，请稍后再试',
                    503,
                )
            logger.warning('资产 {}({}) 取数失败，回落库内历史（共 {} 行）: {}', asset['name'], asset_key, count, e)
            stale = True
            reason = '当日行情暂时取不到，这里显示的是库内已有历史'

    with _session(db) as session:
        dates, closes = market_history_store.load_series(session, asset_key, limit=days)
        count, last_date = market_history_store.coverage(session, asset_key)

    points: List[Tuple[str, float]] = list(zip(dates, closes))
    return {
        'key': asset['key'],
        'name': asset['name'],
        'category': asset['category'],
        'position_basis': asset.get('position_basis', '价格分位'),
        'position_window': asset.get('position_window', DEFAULT_DAYS),
        'points': [{'date': d, 'close': c} for d, c in points],
        'count': len(points),
        'last_date': dates[-1] if dates else None,
        'total_rows': count,
        'expected_latest_date': expected.strftime('%Y-%m-%d'),
        'fetched': fetched,
        'added': added,
        'stale': stale,
        'reason': reason,
    }
