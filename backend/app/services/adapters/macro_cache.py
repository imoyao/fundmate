# -*- coding: utf-8 -*-
"""Wind EDB 宏观序列的复用缓冲层（成本闸门，#1502 步骤 2）。

## 为什么必须有这一层

上游 ``economic_query_indicator_series`` 是**按积分计费的高消耗接口**：2026-11-16 两次
手工探针（换手率一次、GDP 一次）就把账户额度耗到不可用。而在此之前，Agent 侧每次提问
都要真调一次——同一句「CPI 多少」问三遍就烧三遍。缓存在这里不是性能优化，是**成本红线**。

## 三条判据

1. **新鲜度**：按指标频率给 TTL（日 6h / 周 1d / 月 3d / 季 7d / 年 30d）。宏观指标有
   固定发布日历，月频指标一个月才动一次，按小时级 TTL 重取纯属浪费。
2. **覆盖度**：缓存窗口必须覆盖请求窗口（起点早于等于请求起点；终点不早于「请求终点
   − TTL」，即只容忍一个发布周期内的落后）。
3. **兜底**：上游失败（**尤其额度耗尽**）时回退到过期缓存并标 ``stale``。
   额度被打光时这是唯一还能出数的路径，比抛错让用户看到「结构异常」有用得多。

## 频率从哪来（不额外调接口）

上游 ``meta.freq`` 在**首次取数时随载荷返回**，顺手落进缓存；缺失或不可识别时用点间隔
中位数反推（:func:`infer_freq`）。两者都进缓存后，TTL 判定全在本地——**不需要为了
「这个指标多久更新一次」再花一次积分**。

## 两条纪律

- **键用原始精确名，绝不归一化**：``normalize`` 会把「GDP 现价」与「GDP 不变价」压成
  同一个键，那是最坏的一种串数据（同一句问话拿到别的口径的缓存）。
- **缓存实例在调用期构造**（#1531）：import 期固化目录会让 ``CACHE_FILE_DIR`` 只对部分
  实现生效，测试的 ``tmp_path`` 隔离退化成假隔离。
"""

import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.core.cache import CacheService

#: 命名空间：与温度计 / 拥挤度等缓存隔离，删起来互不影响
_NAMESPACE = 'wind_macro'
#: 物理保留期（秒）：逻辑过期由 TTL 判，物理过期只防无限堆积
_KEEP_SECONDS = 30 * 86400
#: 频率 → 单期天数（与 ``tools_macro._window_days`` 同一张表：日频按交易日取 3 天余量）
_PERIOD_DAYS = (
    (('日', 'd'), 3),
    (('周', 'w'), 10),
    (('月', 'm'), 31),
    (('季', 'q'), 92),
    (('年', 'y', 'a'), 366),
)
#: 频率类别 → 新鲜期（秒）。数值取「下一个数据点最早可能出现的间隔」的下界：
#: 月频给 3 天，是因为同月内重取的边际收益几乎为零，而每次重取都要扣积分。
_TTL_BY_CLASS = {
    'day': 6 * 3600,
    'week': 86400,
    'month': 3 * 86400,
    'quarter': 7 * 86400,
    'year': 30 * 86400,
    'unknown': 86400,
}
#: search 侧缓存：指标库本身几乎不变（改名/停更以月计），给 30 天
_SEARCH_TTL = 30 * 86400


def _cache() -> CacheService:
    """调用期构造缓存实例（#1531：不要在 import 期固化目录）。

    每轮新建的代价是 LRU 层不跨调用共享，但文件层仍命中——宏观序列一次调用几百个点，
    pickle 读盘是毫秒级，比扣一次积分便宜太多。
    """
    return CacheService(namespace=_NAMESPACE, default_ttl=_KEEP_SECONDS)


def period_days(freq: Optional[str]) -> int:
    """频率 → 单期天数；认不出按季（宏观最常见，且窗口偏大只多取、不会取空）。"""
    text = str(freq or '').strip().lower()
    for keys, days in _PERIOD_DAYS:
        if text.startswith(keys):
            return days
    return 92


def freq_class(freq: Optional[str]) -> str:
    """频率 → ``day/week/month/quarter/year/unknown``（TTL 分类键）。"""
    text = str(freq or '').strip().lower()
    if not text:
        return 'unknown'
    for keys, name in ((('日', 'd'), 'day'), (('周', 'w'), 'week'), (('月', 'm'), 'month')):
        if text.startswith(keys):
            return name
    if text.startswith(('季', 'q')):
        return 'quarter'
    if text.startswith(('年', 'y', 'a')):
        return 'year'
    return 'unknown'


def ttl_seconds(freq: Optional[str]) -> int:
    """频率 → 新鲜期（秒）。"""
    return _TTL_BY_CLASS[freq_class(freq)]


def infer_freq(points: Dict[date, float]) -> Optional[str]:
    """从点间隔中位数反推频率（**零调用**：只用已经拿到的数据）。

    上游 ``meta.freq`` 偶尔缺或写成看不懂的值；此时用间隔反推比「当季处理」靠谱。
    中位数而非均值：停更/补发会造成个别超长间隔，均值会被一两个洞带偏。

    Returns:
        ``'日'|'周'|'月'|'季'|'年'``；点少于 2 个时无法判断，回 ``None``。
    """
    days = sorted(points)
    if len(days) < 2:
        return None
    gaps = sorted((b - a).days for a, b in zip(days, days[1:]))
    median = gaps[len(gaps) // 2]
    if median <= 4:
        return '日'
    if median <= 11:
        return '周'
    if median <= 35:
        return '月'
    if median <= 100:
        return '季'
    return '年'


def _key(name: str) -> str:
    """序列缓存键：原始精确名（**不归一化**，理由见模块头两条纪律）。"""
    return f'series:{name}'


def _search_key(question: str) -> str:
    return f'search:{question.strip()}'


def _clip(rows: List[dict], begin: date, end: date, tag: str, fetched_at: Optional[str]) -> List[dict]:
    """按请求窗口裁剪，并给每条打上来源标记（``cache`` / ``fetched_at``）。"""
    out: List[dict] = []
    for row in rows:
        points = {d: v for d, v in (row.get('points') or {}).items() if begin <= d <= end}
        if not points:
            continue
        item = dict(row)
        item['points'] = points
        item['cache'] = tag
        item['fetched_at'] = fetched_at
        out.append(item)
    return out


def _iso(ts: Any) -> Optional[str]:
    try:
        return datetime.fromtimestamp(float(ts)).strftime('%Y-%m-%d %H:%M')
    except (TypeError, ValueError, OSError):
        return None


def _entry_of(store: CacheService, key: str) -> Optional[dict]:
    entry = store.get(key)
    return entry if isinstance(entry, dict) and isinstance(entry.get('rows'), list) else None


def read_series(name: str, begin: date, end: date, *, now: Optional[float] = None) -> Optional[List[dict]]:
    """命中返回裁剪后的条目（带 ``cache='hit'``），未命中 / 过期 / 窗口不足返回 ``None``。"""
    entry = _entry_of(_cache(), _key(name))
    if entry is None:
        return None
    ttl = ttl_seconds(entry.get('freq'))
    clock = time.time() if now is None else now
    if clock - float(entry.get('fetched_at') or 0) > ttl:
        return None
    if entry['begin'] > begin or entry['end'] < end - timedelta(seconds=ttl):
        return None
    return _clip(entry['rows'], begin, end, 'hit', _iso(entry.get('fetched_at')))


def read_series_stale(name: str, begin: date, end: date) -> Optional[List[dict]]:
    """过期缓存兜底（带 ``cache='stale'``）：只要求起点覆盖，终点落后由裁剪自然截短。"""
    entry = _entry_of(_cache(), _key(name))
    if entry is None or entry['begin'] > begin:
        return None
    return _clip(entry['rows'], begin, end, 'stale', _iso(entry.get('fetched_at'))) or None


def write_series(name: str, rows: List[dict], begin: date, end: date, *, freq: Optional[str] = None) -> None:
    """写入序列缓存；``freq`` 优先用上游给的，缺失则用点间隔反推。"""
    if not rows:
        return
    resolved = freq or rows[0].get('freq') or infer_freq(rows[0].get('points') or {})
    entry = {
        'fetched_at': time.time(),
        'begin': begin,
        'end': end,
        'freq': resolved,
        'rows': [{k: v for k, v in row.items() if k not in ('cache', 'fetched_at')} for row in rows],
    }
    _cache().set(_key(name), entry, ttl=_KEEP_SECONDS)


def read_search(question: str) -> Optional[List[dict]]:
    """检索结果缓存命中（``cache='hit'``），未命中返回 ``None``。"""
    entry = _entry_of(_cache(), _search_key(question))
    if entry is None:
        return None
    return _clip_search(entry, 'hit')


def read_search_stale(question: str) -> Optional[List[dict]]:
    return _clip_search(_entry_of(_cache(), _search_key(question)), 'stale')


def write_search(question: str, rows: List[dict]) -> None:
    if not rows:
        return
    _cache().set(
        _search_key(question),
        {'fetched_at': time.time(), 'rows': rows},
        ttl=_SEARCH_TTL,
    )


def _clip_search(entry: Optional[dict], tag: str) -> Optional[List[dict]]:
    """检索结果没有窗口，只需打来源标记（候选项本身不含数值）。"""
    if entry is None:
        return None
    fetched_at = _iso(entry.get('fetched_at'))
    out = []
    for row in entry['rows']:
        item = dict(row)
        item['cache'] = tag
        item['fetched_at'] = fetched_at
        out.append(item)
    return out or None


__all__ = [
    'freq_class',
    'infer_freq',
    'period_days',
    'read_search',
    'read_search_stale',
    'read_series',
    'read_series_stale',
    'ttl_seconds',
    'write_search',
    'write_series',
]
