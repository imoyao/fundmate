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

import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.core.akshare_lazy import get_akshare
from app.core.cache import CacheService
from app.core.time_utils import now_shanghai

# ─────────────────────────── 缓存 ───────────────────────────
# 单资产序列缓存 30 分钟（overview 由各序列现算组装，不整体缓存）。
_SERIES_TTL = 1800
_cache = CacheService(namespace='market_overview')

# 债券收益率轨：只取近 N 个自然日。
# 2026-09-12 实测：不传 start_date 时 akshare 会翻 19 页拉全部历史（≈9500 行，单次 ~29s），
# 是该接口首屏超时（前端 timeout 10s）的主因；传近月起点后降至 ~2.5s（30 行）。
_BOND_SERIES_DAYS = 30

# 资产序列取数并发度。
# 2026-09-12 实测：清缓存后 14 个资产**串行**取数合计 ~40s（各源网络往返之和），
# 是首屏超时的另一半根因（bond 修好后仍不够）。改并发后总耗时 ≈ 最慢单源耗时。
# 取 6 而非全量 14：避免瞬时打爆对端（新浪/东财）与本地连接池；akshare 各函数互不共享状态。
_FETCH_WORKERS = 6

# 单个资产 / 债券收益率轨的取数上限（秒）。
# 2026-09-12 实测踩坑：并发取数偶发「单源长时间挂住」——14 个资产全部取数成功并落缓存后，
# 线程池仍 11 分钟不回收。若沿用 `with ThreadPoolExecutor(...)`（退出时隐式 wait=True），
# 会把整个请求拖死，比超时更糟。故：逐个 future 设超时 + 显式 shutdown(wait=False)，
# 超时项降级为软占位，使响应时间有确定上界。
_PER_FETCH_TIMEOUT = 20

# ─────────────────── ⚡ 异动双线参数（docs/features/market-explorer.md §5.5）───────────────────
# 线 1（相对 / 自适应）：|当日涨跌| > ANOMALY_SIGMA_MULTIPLE × σ(过去 ANOMALY_SIGMA_WINDOW 个交易日日收益)
# 线 2（绝对 / 兜底）：  |当日涨跌| >= ANOMALY_ABS_THRESHOLD
# 任一触发 → 亮 ⚡。
# 取值依据（2026-09-12 用 index_daily 的 10 个万得指数长历史 + 14 个在观察资产实测）：
#   k=2.5 命中约 7.6~8.3 次/年/资产（k=2.0 约 15 次/年偏滥，k=3.0 约 4 次/年偏吝）；
#   且 k=2.5 + abs=3.0 能复现原文样例——原油 +3.5%/σ≈2% 亮（走线 2）、日经 +2% 不亮。
# 三者均为模块级常量，如需按资产覆盖可在 ASSET_CONFIG 单项里加同名键。
ANOMALY_SIGMA_WINDOW = 250
ANOMALY_SIGMA_MULTIPLE = 2.5
ANOMALY_ABS_THRESHOLD = 3.0
# 线 1 至少要有这么多个历史日收益样本才启用（否则只用线 2，避免新资产被小样本 σ 误判）
ANOMALY_MIN_SAMPLES = 60

# 10 年期列名精确匹配：必须排除同日发布的「10年-2年」期限利差列。
# 2026-09-12 实测的取列 bug：原实现按 `'10年' in col` 匹配，遍历到后面的
# 「中国国债收益率10年-2年」会把已匹配到的「中国国债收益率10年」覆盖掉，
# 导致前端把期限利差（0.44%）当成 10 年收益率展示（美债同理显示 0.33%）。
_CN_10Y_RE = re.compile(r'^中国国债收益率\s*10\s*年$')
_US_10Y_RE = re.compile(r'^美国国债收益率\s*10\s*年$')


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
        if f != f or f in (float('inf'), float('-inf')):  # NaN / ±inf
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


def _fetch_bond_yield_10y_uncached() -> Optional[Dict[str, Any]]:
    """实际取数（无缓存层）：中美国债 10Y 收益率 + 日变动(bp)。best-effort，失败返回 None。

    列名随 akshare 版本变化，这里用锚定 ^…$ 的正则精确匹配「10年」列，
    以免被同名后缀的「10年-2年」期限利差列覆盖（见 _CN_10Y_RE 注释）。
    """
    try:
        ak = get_akshare()
        # 只取近 N 天：不传 start_date 会翻 19 页拉全历史，单次 ~29s（首屏超时主因）
        start = (now_shanghai() - timedelta(days=_BOND_SERIES_DAYS)).strftime('%Y%m%d')
        df = ak.bond_zh_us_rate(start_date=start)
        if df is None or getattr(df, 'empty', True):
            return None

        cn_col = us_col = None
        for col in df.columns:
            c = str(col).strip()
            if cn_col is None and _CN_10Y_RE.match(c):
                cn_col = col
            elif us_col is None and _US_10Y_RE.match(c):
                us_col = col
        if cn_col is None:
            logger.warning('债券收益率轨：未匹配到「中国国债收益率10年」列，跳过。列名={}', list(df.columns))
            return None

        def _tail2(col: Any) -> List[float]:
            """按时间升序取该列最后两个有效值。"""
            out: List[float] = []
            for v in df[col].tolist():
                f = _safe_float(v)
                if f is not None:
                    out.append(f)
            return out

        cn_vals = _tail2(cn_col)
        if len(cn_vals) < 2:
            return None
        result: Dict[str, Any] = {
            'cn_10y': round(cn_vals[-1], 2),
            'cn_10y_change_bp': round((cn_vals[-1] - cn_vals[-2]) * 100, 1),
        }
        if us_col is not None:
            us_vals = _tail2(us_col)
            if len(us_vals) >= 2:
                result['us_10y'] = round(us_vals[-1], 2)
                result['us_10y_change_bp'] = round((us_vals[-1] - us_vals[-2]) * 100, 1)
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning('债券收益率轨取数失败（best-effort 跳过）: {}', e)
        return None


def _fetch_bond_yield_10y() -> Optional[Dict[str, Any]]:
    """债券收益率轨（带 30 分钟缓存）。

    此前该函数**没有任何缓存**，每个请求都会打一次东财接口；
    叠加无 start_date 的 29s 全量翻页，是 /api/market/overview 首屏超时的根因。
    """
    return _cache.get_or_set('bond_yield:10y', producer=_fetch_bond_yield_10y_uncached, ttl=_SERIES_TTL)


def _calc_anomaly(change_pct: Optional[float], closes: List[float]) -> Optional[Dict[str, Any]]:
    """⚡ 异动双线判定（docs/features/market-explorer.md §5.5）。

    线 1（相对 / 自适应）：|当日涨跌| > k × σ(过去 window 个交易日日收益)
    线 2（绝对 / 兜底）：  |当日涨跌| >= 绝对阈值
    任一触发即 triggered=True。判不出（数据不足 / 无当日涨跌）返回 None。

    返回结构（前端渲染 ⚡ 徽标与「异动解读」用）：
      {triggered, rule, today_pct, sigma, multiple, sigma_window,
       sigma_multiple, abs_threshold, basis_note}
    """
    if change_pct is None:
        return None

    # 由收盘价序列现算日收益（不依赖 index_daily.ret_pct —— 该列实测量纲错乱，不可用）
    rets: List[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev:
            rets.append((closes[i] - prev) / prev * 100.0)

    sigma: Optional[float] = None
    multiple: Optional[float] = None
    # 历史窗口不含当日（rets[-1] 即当日）
    hist = rets[-(ANOMALY_SIGMA_WINDOW + 1) : -1]
    if len(hist) >= ANOMALY_MIN_SAMPLES:
        mean = sum(hist) / len(hist)
        var = sum((x - mean) ** 2 for x in hist) / (len(hist) - 1)  # 样本方差（n-1）
        sd = var**0.5
        if sd > 0:
            sigma = round(sd, 2)
            multiple = round(abs(change_pct) / sd, 2)

    # 注意：sigma 是 round(sd, 2) 的结果，当 sd 极小（0 < sd < 0.005%）时会被舍入成 0.0，
    # 此时若只用 round 值比较会退化为 abs(change_pct) > 0，把任何非零涨跌都误判为 σ 异动。
    # 故必须额外要求 sigma > 0（用原始 sd 比较更精确，这里用 round 值的 0 守卫已足够挡住退化情形）。
    hit_sigma = sigma is not None and sigma > 0 and abs(change_pct) > ANOMALY_SIGMA_MULTIPLE * sigma
    hit_abs = abs(change_pct) >= ANOMALY_ABS_THRESHOLD
    if not (hit_sigma or hit_abs):
        return None

    if hit_sigma and hit_abs:
        rule = 'both'
    elif hit_sigma:
        rule = 'sigma'
    else:
        rule = 'abs'

    # 规则自述（原文要求的「异动解读」是当日新闻事实，本项目暂无新闻源，
    # 故此处只给可实证的规则解释，不编造新闻——见 notes 与文档 §5.5 的说明）
    parts: List[str] = []
    if hit_abs:
        parts.append(f'单日 {change_pct:+.2f}%，超过 {ANOMALY_ABS_THRESHOLD:g}% 绝对阈值')
    if hit_sigma and multiple is not None and sigma is not None:
        parts.append(
            f'{"且" if hit_abs else ""}为其近 {ANOMALY_SIGMA_WINDOW} 个交易日日波动（σ={sigma:.2f}%）'
            f'的 {multiple:.2f} 倍，超过 {ANOMALY_SIGMA_MULTIPLE:g}σ 上限'
        )

    return {
        'triggered': True,
        'rule': rule,
        'today_pct': change_pct,
        'sigma': sigma,
        'multiple': multiple,
        'sigma_window': ANOMALY_SIGMA_WINDOW,
        'sigma_multiple': ANOMALY_SIGMA_MULTIPLE,
        'abs_threshold': ANOMALY_ABS_THRESHOLD,
        'basis_note': '，'.join(parts),
    }


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
            # 债券收益率轨也有 30 分钟缓存，一并失效，避免 force=true 拿到旧值
            _cache.invalidate('bond_yield:10y')

        groups_map: Dict[str, List[Dict[str, Any]]] = {c: [] for c in cls.CATEGORY_ORDER}
        unavailable_count = 0
        anomaly_count = 0
        bond_yield = None

        # 资产序列取数并发执行：串行时 14 个源合计 ~40s（见 _FETCH_WORKERS 注释），
        # 是首屏超时的主要来源；债券收益率轨一并丢进池里，不额外占用关键路径时间。
        #
        # 超时与退出策略（见 _PER_FETCH_TIMEOUT 注释）：**所有资产共享同一个 deadline**
        # —— `future.result(timeout=T)` 的 T 是从「调用时刻」起算，逐个传常量会让 14 个
        # 资产的超时累加（实测 14×20s=280s）；改用统一 deadline 后总等待有确定上界。
        # 超时项降级为软占位；显式 shutdown(wait=False) 而非 `with`（后者 exit 时 wait=True
        # 会被挂死线程拖住）。
        pool = ThreadPoolExecutor(max_workers=_FETCH_WORKERS)
        items: List[Dict[str, Any]] = []
        try:
            futures = [(asset, pool.submit(cls._build_asset_item, asset)) for asset in ASSET_CONFIG]
            bond_future = pool.submit(_fetch_bond_yield_10y)
            deadline = time.monotonic() + _PER_FETCH_TIMEOUT
            for asset, fut in futures:
                try:
                    items.append(fut.result(timeout=max(0.0, deadline - time.monotonic())))
                except Exception as e:  # noqa: BLE001
                    logger.warning('资产 {}({}) 取数超时/失败，降级为软占位: {}', asset['name'], asset['key'], e)
                    items.append(cls._unavailable_item(asset, f'取数超时（>{_PER_FETCH_TIMEOUT}s）或失败，已降级'))
            try:
                bond_yield = bond_future.result(timeout=max(0.0, deadline - time.monotonic()))
            except Exception as e:  # noqa: BLE001
                logger.warning('债券收益率轨跳过: {}', e)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        for asset, item in zip(ASSET_CONFIG, items):
            if not item.get('available'):
                unavailable_count += 1
            if item.get('anomaly'):
                anomaly_count += 1
            groups_map.setdefault(asset['category'], []).append(item)

        groups = [{'category': c, 'assets': groups_map[c]} for c in cls.CATEGORY_ORDER if groups_map.get(c)]

        return {
            'updated_at': now_shanghai().strftime('%Y-%m-%d %H:%M:%S'),
            'as_of_note': (
                '各市场数据截止：A股 15:00 / 港股 16:00 / 美股 05:00（北京）；'
                '商品·加密按北京 08:00 快照（国内口径·含夜盘）。软占位项表示当前无可靠源。'
            ),
            'groups': groups,
            'unavailable_count': unavailable_count,
            'anomaly_count': anomaly_count,
            'bond_yield': bond_yield,
            'notes': [
                '商品（黄金/白银/原油）采用国内主力连续口径，与海外 ETF 代理口径可能方向相反，仅供参考。',
                '离岸人民币 USDCNH 取不到离岸口径，以在岸中行牌价替代并标注；与离岸价有点差。',
                '比特币无稳定日频源，按决策软占位。',
                '⚡ 异动按「双线规则」判定（|当日涨跌| > 2.5σ(近250日) 或 >= 3% 绝对值），'
                '解读行是规则自述；原文要求的「当日新闻事实解释」需新闻源，尚未接入。',
            ],
        }

    @staticmethod
    def _base_item(asset: Dict[str, Any]) -> Dict[str, Any]:
        """资产项的公共骨架（可取数 / 软占位共用）。"""
        return {
            'key': asset['key'],
            'name': asset['name'],
            'category': asset['category'],
            'available': True,
            'change_pct': None,
            'trade_date': None,
            'data_asof': None,
            'position': None,
            'anomaly': None,
            'caliber': asset.get('caliber'),
            'reason': None,
        }

    @classmethod
    def _unavailable_item(cls, asset: Dict[str, Any], reason: str) -> Dict[str, Any]:
        """构造软占位项（缺源 / 取数失败 / 超时降级）。"""
        item = cls._base_item(asset)
        item['available'] = False
        item['reason'] = reason
        return item

    @classmethod
    def _build_asset_item(cls, asset: Dict[str, Any]) -> Dict[str, Any]:
        """构造单个资产项；不可得资产返回软占位。"""
        if not asset.get('available', True):
            return cls._unavailable_item(asset, asset.get('reason', '暂无可靠数据源'))

        base = cls._base_item(asset)
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

            # ⚡ 异动双线判定（§5.5）：未命中返回 None，前端据此决定是否显示徽标
            base['anomaly'] = _calc_anomaly(change, closes)
        except Exception as e:  # noqa: BLE001
            # 取数失败 → 软占位（不 500）
            logger.warning('资产 {}({}) 取数失败，降级为软占位: {}', asset['name'], asset['key'], e)
            base['available'] = False
            base['reason'] = f'取数失败（已降级）: {type(e).__name__}'
        return base
