# -*- coding: utf-8 -*-
"""探市 · 大类资产观察 聚合服务（#1436 / #1444 收口后的实现）。

设计依据：docs/features/market-explorer.md（2026-09-12 实测结论）。
核心约束（来自该文档 §2.1 通道健康度）：
- 新浪通道 ✅ 全通 → 本服务主通道（港股 / 美股 / 商品 / 汇率）
- 东财 push2 / push2his ❌ 全挂 → 凡依赖东财的资产一律换源或软占位
- 中债 ✅ 通 → 债券收益率轨

硬性决策（2026-09-12 用户拍板，issue #1451 记录）：
- 离岸人民币 USDCNH：取不到离岸口径 → 用 currency_boc_sina('美元') 的**在岸**中行牌价/央行中间价
  做替代展示，并明确标注「口径：在岸」（与离岸 CNH 有点差，方向通常一致）。
- 比特币：akshare 无稳定日频源（仅 crypto_js_spot 实时快照）→ 软占位（置灰 + — + 原因）。

数据底座（每日定时任务）按决策 4 后置；本服务为**按需实时取数 + 进程内缓存**，
首屏可能较慢（多源串行），之后命中缓存秒回。任一取数失败**降级为软占位**而非 500，
保证页面永远可渲染。
"""

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.core.akshare_lazy import get_akshare
from app.core.cache import CacheService
from app.core.time_utils import now_shanghai

# ─────────────────────────── 缓存 ───────────────────────────
# 单资产序列缓存 30 分钟；整份 overview 缓存 10 分钟。
_SERIES_TTL = 1800
_OVERVIEW_TTL = 600
_cache = CacheService(namespace='market_overview')


# ─────────────────────────── 20 资产配置 ───────────────────────────
# category：6 大分组（A股 / 港股 / 海外 / 债券 / 商品 / 汇率）
# source：akshare 函数名；args：传给该函数的位置参数
# position_basis：相对位置口径（价格分位 / 收益率分位）
# caliber：口径提示（商品含夜盘 / 汇率非 DXY 等），前端 tooltip 展示
# available=False：软占位资产（缺源或用户决策占位），reason 说明原因
ASSET_CONFIG: List[Dict[str, Any]] = [
    # ───────── A股 ─────────
    {
        'key': 'sh000001',
        'name': '上证指数',
        'category': 'A股',
        'source': 'stock_zh_index_daily',
        'args': ('sh000001',),
        'position_basis': '价格分位',
        'position_window': 500,
    },
    {
        'key': 'sh000300',
        'name': '沪深300',
        'category': 'A股',
        'source': 'stock_zh_index_daily',
        'args': ('sh000300',),
        'position_basis': '价格分位',
        'position_window': 500,
    },
    {
        'key': 'sh000905',
        'name': '中证500',
        'category': 'A股',
        'source': 'stock_zh_index_daily',
        'args': ('sh000905',),
        'position_basis': '价格分位',
        'position_window': 500,
    },
    {
        'key': 'sh932000',
        'name': '中证2000',
        'category': 'A股',
        'available': False,
        'reason': '交易所不披露成分股行情，暂无可靠日频源（降级）',
    },
    # ───────── 港股 ─────────
    {
        'key': 'HSI',
        'name': '恒生指数',
        'category': '港股',
        'source': 'stock_hk_index_daily_sina',
        'args': ('HSI',),
        'position_basis': '价格分位',
        'position_window': 500,
    },
    {
        'key': 'HSTECH',
        'name': '恒生科技',
        'category': '港股',
        'source': 'stock_hk_index_daily_sina',
        'args': ('HSTECH',),
        'position_basis': '价格分位',
        'position_window': 500,
    },
    # ───────── 海外 ─────────
    {
        'key': '.INX',
        'name': '标普500',
        'category': '海外',
        'source': 'index_us_stock_sina',
        'args': ('.INX',),
        'position_basis': '价格分位',
        'position_window': 500,
    },
    {
        'key': '.IXIC',
        'name': '纳斯达克',
        'category': '海外',
        'source': 'index_us_stock_sina',
        'args': ('.IXIC',),
        'position_basis': '价格分位',
        'position_window': 500,
        'caliber': '纳指综合（.IXIC）',
    },
    {
        'key': '.N225',
        'name': '日经225',
        'category': '海外',
        'available': False,
        'reason': '新浪通道不覆盖日股（list index out of range）',
    },
    {
        'key': '.FTSE',
        'name': '富时100',
        'category': '海外',
        'available': False,
        'reason': '新浪通道不覆盖英股（list index out of range）',
    },
    {
        'key': '.GDAXI',
        'name': '德国DAX',
        'category': '海外',
        'available': False,
        'reason': '新浪通道不覆盖德股（list index out of range）',
    },
    {
        'key': '.FCHI',
        'name': '法国CAC40',
        'category': '海外',
        'available': False,
        'reason': '新浪通道不覆盖法股（无对应代码）',
    },
    # ───────── 债券（价格轨：ETF；收益率轨单独取 bond_zh_us_rate）─────────
    {
        'key': 'sh511010',
        'name': '国债ETF',
        'category': '债券',
        'source': 'fund_etf_hist_sina',
        'args': ('sh511010',),
        'track': 'price',
        'position_basis': '价格分位',
        'position_window': 500,
    },
    {
        'key': 'TLT',
        'name': '美债ETF',
        'category': '债券',
        'source': 'stock_us_daily',
        'args': ('TLT', ''),
        'track': 'price',
        'position_basis': '价格分位',
        'position_window': 500,
    },
    # ───────── 商品（国内口径 · 含夜盘）─────────
    {
        'key': 'AU0',
        'name': '黄金',
        'category': '商品',
        'source': 'futures_main_sina',
        'args': ('AU0',),
        'caliber': '国内口径·含夜盘',
        'position_basis': '价格分位',
        'position_window': 500,
    },
    {
        'key': 'AG0',
        'name': '白银',
        'category': '商品',
        'source': 'futures_main_sina',
        'args': ('AG0',),
        'caliber': '国内口径·含夜盘',
        'position_basis': '价格分位',
        'position_window': 500,
    },
    {
        'key': 'SC0',
        'name': '原油',
        'category': '商品',
        'source': 'futures_main_sina',
        'args': ('SC0',),
        'caliber': '国内口径·含夜盘',
        'position_basis': '价格分位',
        'position_window': 500,
    },
    {
        'key': 'BTC',
        'name': '比特币',
        'category': '商品',
        'available': False,
        'reason': 'akshare 无稳定日频源（仅 crypto_js_spot 实时快照），按决策软占位',
    },
    # ───────── 汇率 ─────────
    {
        'key': 'USD_INDEX',
        'name': '美元指数',
        'category': '汇率',
        'source': 'currency_boc_sina',
        'args': ('美元',),
        'caliber': '口径：中行牌价（非 DXY）',
        'position_basis': '价格分位',
        'position_window': 500,
    },
    {
        'key': 'USDCNH',
        'name': '离岸人民币',
        'category': '汇率',
        'source': 'currency_boc_sina',
        'args': ('美元',),
        'caliber': '口径：在岸中行牌价（替代离岸 CNH）',
        'position_basis': '价格分位',
        'position_window': 500,
    },
]


def _safe_float(v: Any) -> Optional[float]:
    """把任意值安全转 float，失败返回 None。"""
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _normalize_series(df: Any) -> Tuple[List[str], List[float]]:
    """把 akshare 返回的 DataFrame 规范为 (dates, closes) 两个等长列表。

    兼容多套列名（close / 收盘 / 中行折算价 等），找不到则抛 ValueError 触发降级。
    """
    if df is None or getattr(df, 'empty', True):
        raise ValueError('空数据')

    # 1) 找收盘列
    close_col = None
    for cand in ('close', '收盘', '中行折算价', '现汇买入价'):
        if cand in df.columns:
            close_col = cand
            break
    if close_col is None:
        # 退而求其次：第一个看起来数值型的列（跳过日期列）
        skip = {'date', '日期', '时间', 'symbol', '品种'}
        for col in df.columns:
            if col not in skip:
                close_col = col
                break
    if close_col is None:
        raise ValueError('无法识别收盘列')

    # 2) 找日期列
    date_col = None
    for cand in ('date', '日期'):
        if cand in df.columns:
            date_col = cand
            break
    if date_col is None:
        date_col = df.columns[0]

    dates: List[str] = []
    closes: List[float] = []
    for _, row in df.iterrows():
        c = _safe_float(row[close_col])
        if c is None:
            continue
        d = str(row[date_col])
        dates.append(d)
        closes.append(c)
    if len(closes) < 2:
        raise ValueError('有效数据点不足')
    return dates, closes


def _fetch_close_series(asset: Dict[str, Any]) -> Tuple[List[str], List[float]]:
    """取某资产的 (dates, closes)。带 30 分钟缓存，失败抛异常由调用方降级。"""
    cache_key = f'series:{asset["key"]}'
    ak = get_akshare()
    fn = getattr(ak, asset['source'], None)
    if fn is None:
        raise ValueError(f'未知数据源 {asset["source"]}')

    def producer() -> Tuple[List[str], List[float]]:
        df = fn(*asset['args'])
        return _normalize_series(df)

    return _cache.get_or_set(cache_key, ttl=_SERIES_TTL, producer=producer)


def _calc_daily_change(dates: List[str], closes: List[float]) -> Tuple[Optional[float], str, str]:
    """计算当日涨跌幅(%) 与交易日/数据截止（北京时间字符串）。

    取最后两个有效收盘点：change = (last - prev) / prev * 100。
    trade_date = 最后一根 K 线的日期；data_asof = 进程当前北京时间。
    """
    if len(closes) < 2:
        return None, '', ''
    last, prev = closes[-1], closes[-2]
    if prev == 0:
        return None, dates[-1], ''
    change = (last - prev) / prev * 100.0
    now = now_shanghai()
    data_asof = now.strftime('%Y-%m-%d %H:%M:%S')
    return round(change, 2), str(dates[-1]), data_asof


def _calc_percentile(closes: List[float], window: int) -> Optional[float]:
    """经验分位：最后一根收盘价在最近 window 根中的相对位置（0~100）。

    用 empirical CDF（低于当前值的比例），比 min-max 更稳健。
    """
    if len(closes) < 2:
        return None
    seq = closes[-window:] if window and len(closes) > window else closes
    last = seq[-1]
    below = sum(1 for x in seq if x < last)
    pct = below / len(seq) * 100.0
    return round(pct, 1)


def _position_label(pct: Optional[float]) -> str:
    if pct is None:
        return '暂无'
    if pct < 33:
        return '偏低'
    if pct > 66:
        return '偏高'
    return '适中'


def _fetch_bond_yield_10y() -> Optional[Dict[str, Any]]:
    """债券收益率轨：中美国债 10Y 收益率 + 日变动(bp)。best-effort，失败返回 None。

    bond_zh_us_rate 列名随 akshare 版本变化，这里做宽匹配 + 异常兜底，
    解析不出也不影响价格轨展示。
    """
    try:
        ak = get_akshare()
        df = ak.bond_zh_us_rate()
        if df is None or getattr(df, 'empty', True):
            return None
        # 找含「10年」的中美国债收益率列（先判美国，避免「美国国债」被「国债」误归入中国）
        cn_col = us_col = None
        for col in df.columns:
            c = str(col)
            if '10年' not in c:
                continue
            if '美国' in c:
                us_col = col
            elif '中国' in c:
                cn_col = col
        if cn_col is None:
            return None
        vals = [_safe_float(v) for v in df[cn_col].tolist() if _safe_float(v) is not None]
        if len(vals) < 2:
            return None
        last, prev = vals[-1], vals[-2]
        bp = round((last - prev) * 100, 1)  # 收益率变动（基点）
        result: Dict[str, Any] = {
            'cn_10y': round(last, 2),
            'cn_10y_change_bp': bp,
        }
        if us_col is not None:
            us_vals = [_safe_float(v) for v in df[us_col].tolist() if _safe_float(v) is not None]
            if len(us_vals) >= 2:
                result['us_10y'] = round(us_vals[-1], 2)
                result['us_10y_change_bp'] = round((us_vals[-1] - us_vals[-2]) * 100, 1)
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning(f'债券收益率轨取数失败（best-effort 跳过）: {e}')
        return None


class MarketOverviewService:
    """探市大类资产观察聚合服务（薄视图可直接调用）。"""

    CATEGORY_ORDER = ['A股', '港股', '海外', '债券', '商品', '汇率']

    @classmethod
    def get_overview(cls, force_refresh: bool = False) -> Dict[str, Any]:
        """返回探市页所需的 20 资产观察数据。

        结构：{ updated_at, as_of_note, groups:[{category, assets:[...]}],
                unavailable_count, bond_yield, notes }
        失败资产降级为 available=false 的软占位，绝不整体 500。
        """
        if force_refresh:
            # 无 clear() 方法：逐个失效本 namespace 下各资产序列缓存键
            for asset in ASSET_CONFIG:
                if asset.get('available', True):
                    _cache.invalidate(f'series:{asset["key"]}')

        groups_map: Dict[str, List[Dict[str, Any]]] = {c: [] for c in cls.CATEGORY_ORDER}
        unavailable_count = 0
        bond_yield = None

        for asset in ASSET_CONFIG:
            item = cls._build_asset_item(asset)
            if not item.get('available'):
                unavailable_count += 1
            groups_map.setdefault(asset['category'], []).append(item)

        # 债券收益率轨（best-effort，独立取数）
        try:
            bond_yield = _fetch_bond_yield_10y()
        except Exception as e:  # noqa: BLE001
            logger.warning(f'债券收益率轨跳过: {e}')

        groups = [{'category': c, 'assets': groups_map[c]} for c in cls.CATEGORY_ORDER if groups_map.get(c)]

        return {
            'updated_at': now_shanghai().strftime('%Y-%m-%d %H:%M:%S'),
            'as_of_note': (
                '各市场数据截止：A股 15:00 / 港股 16:00 / 美股 05:00（北京）；'
                '商品·加密按北京 08:00 快照（国内口径·含夜盘）。软占位项表示当前无可靠源。'
            ),
            'groups': groups,
            'unavailable_count': unavailable_count,
            'bond_yield': bond_yield,
            'notes': [
                '商品（黄金/白银/原油）采用国内主力连续口径，与海外 ETF 代理口径可能方向相反，仅供参考。',
                '离岸人民币 USDCNH 取不到离岸口径，以在岸中行牌价替代并标注；与离岸价有点差。',
                '比特币无稳定日频源，按决策软占位。',
            ],
        }

    @classmethod
    def _build_asset_item(cls, asset: Dict[str, Any]) -> Dict[str, Any]:
        """构造单个资产项；不可得资产返回软占位。"""
        base = {
            'key': asset['key'],
            'name': asset['name'],
            'category': asset['category'],
            'available': True,
            'change_pct': None,
            'trade_date': None,
            'data_asof': None,
            'position': None,
            'caliber': asset.get('caliber'),
            'reason': None,
        }

        if not asset.get('available', True):
            base['available'] = False
            base['reason'] = asset.get('reason', '暂无可靠数据源')
            return base

        try:
            dates, closes = _fetch_close_series(asset)
            change, trade_date, data_asof = _calc_daily_change(dates, closes)
            base['change_pct'] = change
            base['trade_date'] = trade_date
            base['data_asof'] = data_asof

            window = asset.get('position_window', 500)
            basis = asset.get('position_basis', '价格分位')
            pct = _calc_percentile(closes, window)
            if pct is not None:
                base['position'] = {
                    'percentile': pct,
                    'label': _position_label(pct),
                    'basis': basis,
                    'window': window,
                }
        except Exception as e:  # noqa: BLE001
            # 取数失败 → 软占位（不 500）
            logger.warning(f'资产 {asset["name"]}({asset["key"]}) 取数失败，降级为软占位: {e}')
            base['available'] = False
            base['reason'] = f'取数失败（已降级）: {type(e).__name__}'
        return base
