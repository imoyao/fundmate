# -*- coding: utf-8 -*-
"""
行业拥挤度（"韭菜投资学"方法）· v2 接入版
============================================
原理： 拥挤度 = 各行业 PB 相对 A 股整体 PB 的倍数，在历史(2010-06起)中的百分位。
      倍数 = 行业PB / 全A中位PB；分位越低=相对A股越便宜(适合埋伏)，越高=越热门。

 数据源（默认 legulegu 免费，无需 token）：覆盖部分申万行业（消费/医药/金融/信息…）。
  · 分母(全A中位PB)：优先 ak.stock_a_all_pb()（legulegu，2005+全历史，免费无 token）。
  · 分子(行业PB)：legulegu index-basic-pb（免费，需 token，由 akshare 内置 JS 生成）。
  · 分母兜底链：legulegu 不可用 → 本地缓存 → baostock 批量当日全A中位PB → 东财实时 → 全失败整组标灰。
  · 分子全覆盖路径（可选，预留）：baostock(申万一级全行业)/tushare(申万一级31行业)，
    需本机直连 baostock 或 TUSHARE_TOKEN，沙箱网络不可达故默认不走。

健壮性：所有网络调用均 try/except + timeout，失败整组返回 stale 占位，
        绝不抛异常阻塞 TemperatureJob 主链路（与 README 降级设计一致）。

接入方式（供 TemperatureJob 调用）：
    from app.services.thermometer.industry_crowding import fetch_industry_crowding
    records = fetch_industry_crowding()   # List[dict], 扁平 multi 格式，可直接 save_multi_items
"""

import datetime
import json
import logging
import os
import re
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    import akshare as ak
    import pandas as pd
    import requests

    HAS_AK = True
except Exception as e:  # noqa
    HAS_AK = False
    logger.warning(f'行业拥挤度依赖缺失(akshare/pandas/requests)，将整组标灰: {e}')

try:
    from app.core.time_utils import now_shanghai
except Exception:  # noqa

    def now_shanghai():
        return datetime.datetime.now()


HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, 'cache', 'baostock_pb')  # baostock 路径的本地 PB 缓存
ALLPB_CACHE = os.path.join(HERE, 'cache', 'all_pb.csv')  # 全A中位PB历史缓存(跨源复用分母)

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


def _log(*a):
    """诊断信息走 logger（原为 stderr，避免污染聚合器 stdout）。"""
    logger.debug(' '.join(str(x) for x in a))


# 申万一级行业（用于 tushare / 展示）
SW_INDUSTRY = {
    '农林牧渔': '801010.SH',
    '采掘': '801020.SH',
    '化工': '801030.SH',
    '钢铁': '801040.SH',
    '有色金属': '801050.SH',
    '电子': '801080.SH',
    '家用电器': '801110.SH',
    '食品饮料': '801120.SH',
    '纺织服装': '801130.SH',
    '轻工制造': '801140.SH',
    '医药生物': '801150.SH',
    '公用事业': '801160.SH',
    '交通运输': '801170.SH',
    '房地产': '801180.SH',
    '商业贸易': '801200.SH',
    '休闲服务': '801210.SH',
    '综合': '801230.SH',
    '建筑材料': '801710.SH',
    '建筑装饰': '801720.SH',
    '电气设备': '801730.SH',
    '国防军工': '801740.SH',
    '计算机': '801750.SH',
    '传媒': '801760.SH',
    '通信': '801770.SH',
    '银行': '801780.SH',
    '非银金融': '801790.SH',
    '汽车': '801880.SH',
    '机械设备': '801890.SH',
}
# legulegu 免费路径：实测可用的行业指数（覆盖不均，但方法完整可跑）
LEGULEGU_INDUSTRY = {
    '中证消费': '000990.SH',
    '中证医药': '000991.SH',
    '中证金融': '000992.SH',
    '中证信息': '000993.SH',
    '中证白酒': '399997.SZ',
    '中证煤炭': '399998.SZ',
    '中证主要消费': '000932.SH',
    '中证金融地产': '000934.SH',
}


# ───────────────── 市场整体 PB（分母，三路径共用）─────────────────
def _save_allpb_cache(s: pd.Series):
    """把全A中位PB序列(按日期索引)落盘缓存，供后续复用 / 限流时回退。"""
    try:
        os.makedirs(os.path.dirname(ALLPB_CACHE), exist_ok=True)
        s.index.name = 'date'
        s.rename('middlePB').to_frame().to_csv(ALLPB_CACHE)
    except Exception as e:  # noqa
        _log('  [warn] 缓存全A PB 失败:', str(e)[:60])


def _load_allpb_cache():
    if not os.path.exists(ALLPB_CACHE):
        return None
    try:
        df = pd.read_csv(ALLPB_CACHE, parse_dates=['date']).dropna()
        return df.set_index('date')['middlePB']
    except Exception:
        return None


def _baostock_market_median_pb():
    """兜底：用 baostock 批量取某日全 A 股 pbMRQ 的中位数（当日分位点）。

    走 `query_daily_history_k_AStock(date)` 单次批量接口（含 pbMRQ 字段），
    一次网络往返即得全市场中位 PB，无需逐股遍历。
    仅在 legulegu 不可达且无本地缓存时触发，作为东财的替代兜底。

    baostock 底层为无超时的阻塞 socket，服务器不可达时会无限挂起，
    因此在线程内执行并施加超时，超时/异常一律返回 None（进入下一级兜底）。
    """
    import statistics as _st

    try:
        from concurrent.futures import ThreadPoolExecutor
        from concurrent.futures import TimeoutError as _FutureTimeout

        def _run():
            import baostock as bs

            bs.login()
            try:
                rs = bs.query_daily_history_k_AStock(date=datetime.date.today().isoformat())
                rows = []
                while rs.next():
                    d = rs.get_row_data()
                    # 字段通常含 date,code,...,pbMRQ；逐列名定位 pbMRQ 更稳
                    try:
                        fields = rs.fields
                        idx = fields.index('pbMRQ')
                        v = float(d[idx])
                        if v > 0:
                            rows.append(v)
                    except (ValueError, TypeError, IndexError):
                        continue
                return float(_st.median(rows)) if rows else None
            finally:
                try:
                    bs.logout()
                except Exception:
                    pass

        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_run)
            return fut.result(timeout=20)
    except (_FutureTimeout, Exception) as e:  # noqa: BLE001 - 任一失败都降级
        _log('  [warn] baostock 分母兜底失败:', str(e)[:60])
        return None


def _eastmoney_current_median_pb():
    """兜底：用东财 push2 全A 实时 PB(f23) 算【当前】中位PB（无历史）。
    仅在 legulegu 不可用且本地无缓存时调用，作为当日分母的最新点。"""
    try:
        import statistics as _st

        r = requests.get(
            'https://push2.eastmoney.com/api/qt/clist/get',
            params={'pn': 1, 'pz': 5000, 'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23', 'fields': 'f12,f14,f23'},
            headers={'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/'},
            timeout=8,
        )
        rows = (r.json().get('data') or {}).get('diff') or {}
        pbs = []
        for v in rows.values():
            try:
                x = float(v.get('f23'))
                if x > 0:
                    pbs.append(x)
            except Exception:
                pass
        if not pbs:
            return None
        return float(_st.median(pbs))
    except Exception as e:  # noqa
        _log('  [warn] 东财实时PB兜底失败:', str(e)[:60])
        return None


def market_pb_series():
    """
    全A中位PB（行业拥挤度的分母），返回 (Series|None, meta)。
      meta = {'src': 'legulegu'|'cache'|'baostock'|'eastmoney-live'|'unavailable',
              'hist_ok': bool   # True=有2010+历史(可算百分位); False=仅当日点}
    健壮策略：
      1) 优先 ak.stock_a_all_pb()（legulegu，2005+全历史）→ 成功即落盘缓存。
      2) legulegu 限流/宕机 → 读本地缓存（上次成功的历史）。
      3) 既无限流恢复也无缓存 → baostock 批量取当日全 A 中位 PB（替代已封的东财兜底），
         追加进缓存，之后每天跑都补一个点，历史会随时间自增长（hist_ok=False，分位暂不可用）。
      4) baostock 也不可达 → 东财实时PB（历史遗留兜底，目前出口 IP 被封，实际不可用）。
      5) 全失败 → 返回 (None, unavailable)，由上层优雅标灰，绝不抛异常阻塞主链路。
    """
    # 1) legulegu 全历史
    try:
        df = ak.stock_a_all_pb()[['date', 'middlePB']].copy()
        df['date'] = pd.to_datetime(df['date'])
        s = df.dropna().set_index('date')['middlePB']
        if not s.empty:
            _save_allpb_cache(s)
            _log(f'  [分母] legulegu 全A中位PB 成功，{len(s)} 个交易日，最新={s.iloc[-1]:.2f}')
            return s, {'src': 'legulegu', 'hist_ok': True}
    except Exception as e:  # noqa
        _log('  [分母] legulegu(stock_a_all_pb) 暂不可用:', str(e)[:70])

    # 2) 本地缓存（上次成功的历史）
    cached = _load_allpb_cache()
    if cached is not None and not cached.empty:
        _log(f'  [分母] 复用本地缓存全A中位PB，{len(cached)} 个交易日，最新={cached.iloc[-1]:.2f}')
        return cached, {'src': 'cache', 'hist_ok': True}

    # 3) baostock 实时兜底（仅当日点，替代已封的东财）
    cur = _baostock_market_median_pb()
    src_prefix = 'baostock'
    if cur is None:
        # 3b) baostock 不可达 → 东财实时PB（历史遗留兜底，目前出口 IP 被封，实际不可用）
        cur = _eastmoney_current_median_pb()
        src_prefix = 'eastmoney-live'
    if cur is not None:
        s = pd.Series({pd.Timestamp.today().normalize(): round(cur, 3)})
        _save_allpb_cache(s)
        _log(f'  [分母] {src_prefix}中位PB={cur:.2f}（仅当日点，分位待历史积累）')
        return s, {'src': src_prefix, 'hist_ok': False}

    # 4) 全失败
    _log('  [分母] 全A中位PB 所有来源均不可用')
    return None, {'src': 'unavailable', 'hist_ok': False}


# ───────────────── 路径A：legulegu（免费，部分行业）─────────────────
def _legulegu_token():
    from py_mini_racer import MiniRacer

    akdir = os.path.dirname(ak.__file__)
    txt = open(akdir + '/stock_feature/stock_a_pe_and_pb.py', encoding='utf-8', errors='ignore').read()
    hash_code = re.search(r'hash_code\s*=\s*"""(.*?)"""', txt, re.S).group(1)
    js = MiniRacer()
    js.eval(hash_code)
    return js.call('hex', datetime.date.today().isoformat()).lower()


def industry_pb_legulegu(code):
    from akshare.stock_feature.stock_a_pe_and_pb import get_cookie_csrf

    try:
        token = _legulegu_token()
        kw = get_cookie_csrf(url='https://legulegu.com/stockdata/sz50-ttm-lyr')
        r = requests.get(
            'https://legulegu.com/api/stockdata/index-basic-pb',
            params={'token': token, 'indexCode': code},
            **kw,
            timeout=10,
        )
        d = r.json().get('data') or []
        if not d:
            return None
        df = pd.DataFrame(d)
        df['date'] = (
            pd.to_datetime(df['date'], unit='ms', utc=True)
            .dt.tz_convert('Asia/Shanghai')
            .dt.tz_localize(None)
            .dt.normalize()
        )
        df = df.dropna(subset=['pb']).set_index('date')['pb']
        return df if not df.empty else None
    except Exception:
        return None


# ───────────────── 路径B：baostock（免费，全申万一级行业，预留）─────────────────
try:
    import baostock as bs

    BAO_OK = True
except Exception:
    BAO_OK = False


def bao_industry_map():
    """全市场 股票->申万一级行业 映射（缓存到 json）。"""
    path = os.path.join(CACHE_DIR, 'industry_map.json')
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    os.makedirs(CACHE_DIR, exist_ok=True)
    bs.login()
    rs = bs.query_stock_industry()  # 无 code => 返回全市场
    m = {}
    while r := rs.next():
        code, ind = r[0], (r[1] if len(r) > 1 else '')
        if ind:
            m[code] = ind  # ind 即申万一级（如 '食品加工','银行'…）
    bs.logout()
    json.dump(m, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    return m


def bao_backfill_pb(start='2010-06-01', end=None):
    """一次性回补：全市场每支股票每日 pbMRQ -> 存 parquet。仅本机可直连 baostock 时运行。"""
    end = end or datetime.date.today().isoformat()
    os.makedirs(CACHE_DIR, exist_ok=True)
    bs.login()
    rs = bs.query_all_stock(day=datetime.date.today().isoformat())
    codes = [r[0] for r in iter(rs.next, None)]
    _log(f'共 {len(codes)} 支股票，开始回补 pbMRQ({start}~{end})…')
    for code in codes:
        f = os.path.join(CACHE_DIR, code.replace('.', '_') + '.parquet')
        if os.path.exists(f):
            continue
        r2 = bs.query_history_k_data_plus(code, 'date,pbMRQ', start_date=start, end_date=end, frequency='d')
        rows = [r for r in iter(r2.next, None)]
        if rows:
            pd.DataFrame(rows, columns=['date', 'pbMRQ']).to_parquet(f)
    bs.logout()
    _log('回补完成。')


def industry_pb_baostock(industry_name):
    """聚合某申万一级行业成分股的每日 pbMRQ 中位数 -> 行业PB序列。"""
    m = bao_industry_map()
    codes = [c for c, ind in m.items() if ind == industry_name]
    if not codes:
        return None
    frames = []
    for code in codes:
        f = os.path.join(CACHE_DIR, code.replace('.', '_') + '.parquet')
        if not os.path.exists(f):
            continue
        d = pd.read_parquet(f).copy()
        d['date'] = pd.to_datetime(d['date'])
        d['pbMRQ'] = pd.to_numeric(d['pbMRQ'], errors='coerce')
        d = d.dropna(subset=['pbMRQ']).set_index('date')['pbMRQ'].rename(code)
        frames.append(d)
    if not frames:
        return None
    panel = pd.concat(frames, axis=1)
    s = panel.median(axis=1).dropna()  # 每日取成分股 PB 中位数 = 行业PB（抗极端值）
    return s.sort_index() if not s.empty else None


# ───────────────── 路径C：tushare（申万一级全覆盖，预留）─────────────────
def industry_pb_tushare(code):
    import tushare as ts

    pro = ts.pro_api(os.getenv('TUSHARE_TOKEN'))
    df = pro.index_pb(ts_code=code, start_date='20100601')
    if df is None or df.empty:
        return None
    df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
    return df.dropna(subset=['pb']).set_index('trade_date')['pb'].sort_index()


# ───────────────── 拥挤度计算（三路径共用）─────────────────
def crowding(ind_pb: pd.Series, mkt_pb: pd.Series, hist_ok: bool = True) -> Optional[dict]:
    """
    拥挤度 = 行业PB / 全A中位PB 的【当前倍数】在历史(2010-06起)的百分位。
      · 倍数(multiple) 只要有当日行业PB与当日分母即可算 —— 始终返回。
      · 百分位(crowding_pct) 需要分母有 2010+ 历史；hist_ok=False 时返回 None，
        并在 note 标注「分位待历史积累」，避免用单日历史给出误导性的百分位。
    """
    ind_pb = ind_pb.dropna()
    mkt_pb = mkt_pb.dropna()
    if ind_pb.empty or mkt_pb.empty:
        return None
    ind_last = ind_pb.iloc[-1]
    mkt_last = mkt_pb.iloc[-1]
    if mkt_last <= 0:
        return None
    mult = ind_last / mkt_last

    if hist_ok:
        df = pd.concat([ind_pb.rename('ind'), mkt_pb.rename('mkt')], axis=1).dropna()
        df = df[df.index >= '2010-06-01']
        if len(df) < 200:
            return {
                'multiple': round(mult, 3),
                'crowding_pct': None,
                'ind_pb': round(ind_last, 2),
                'mkt_pb': round(mkt_last, 2),
                'history_days': len(df),
                'hist_ok': False,
            }
        df['mult'] = df['ind'] / df['mkt']
        cur = df['mult'].iloc[-1]
        return {
            'multiple': round(cur, 3),
            'crowding_pct': round((df['mult'] < cur).mean() * 100, 1),
            'ind_pb': round(ind_last, 2),
            'mkt_pb': round(mkt_last, 2),
            'history_days': len(df),
            'hist_ok': True,
        }
    # 分母仅当日点：只能给倍数，分位不可用
    return {
        'multiple': round(mult, 3),
        'crowding_pct': None,
        'ind_pb': round(ind_last, 2),
        'mkt_pb': round(mkt_last, 2),
        'history_days': 1,
        'hist_ok': False,
    }


# ───────────────── v2 接入封装 ─────────────────
def _placeholder(note: str = '行业拥挤度数据暂不可用') -> dict:
    """整组标灰占位：分母/分子缺失或不支持时返回单条 stale 记录，供前端提示。"""
    return {
        'kind': 'multi',
        'source': 'industry_crowding',
        'item_type': 'industry',
        'item_code': '__NA__',
        'item_name': '行业拥挤度',
        'data': {'crowding_pct': None, 'note': note},
        'collected_at': now_shanghai(),
        'stale': True,
    }


def _record(name: str, code: str, c: dict) -> dict:
    """单行业有效记录 -> 扁平 multi 格式。"""
    note = f"倍数{c.get('multiple')} 行业PB{c.get('ind_pb')} " f"全A中位PB{c.get('mkt_pb')}" + (
        '' if c.get('hist_ok') else '；分位待历史积累'
    )
    return {
        'kind': 'multi',
        'source': 'industry_crowding',
        'item_type': 'industry',
        'item_code': code,
        'item_name': name,
        'data': {
            'crowding_pct': c.get('crowding_pct'),
            'multiple': c.get('multiple'),
            'ind_pb': c.get('ind_pb'),
            'mkt_pb': c.get('mkt_pb'),
            'history_days': c.get('history_days'),
            'hist_ok': c.get('hist_ok'),
            'note': note,
        },
        'collected_at': now_shanghai(),
        'stale': False,
    }


def fetch_industry_crowding() -> List[dict]:
    """
    给 TemperatureJob 用的行业拥挤度抓取（legulegu 免费行情自算）。

    Returns:
        List[dict] —— 扁平 multi 记录（每条一个行业；失败时为单条 stale 占位）。
        可直接喂给 TemperatureService.save_multi_items，无需再包装。

    任何来源失败/分母缺失 → 返回单条 stale 占位（整组优雅标灰），
    绝不抛异常阻塞 TemperatureJob 主链路。
    """
    if not HAS_AK:
        return [_placeholder('行业拥挤度依赖(akshare/pandas/requests)未安装')]

    try:
        mkt, meta = market_pb_series()
        if mkt is None or mkt.dropna().empty:
            return [
                _placeholder(
                    '分母(全A中位PB)数据源暂不可用：legulegu 限流/不可达且本环境无东财实时PB，'
                    '建议本机运行一次以建立历史缓存，届时行业拥挤度自动恢复。'
                )
            ]
        _log(f'市场分母: 全A中位PB={mkt.iloc[-1]:.2f} ({mkt.index[-1].date()}) 来源={meta["src"]}')

        # 选路径：默认 legulegu（免费·部分行业）；baostock/tushare 覆盖更全但需本机/ token。
        if os.getenv('TUSHARE_TOKEN'):
            mode, src, fetcher = 'tushare', SW_INDUSTRY, industry_pb_tushare
            _log('路径: Tushare(申万一级 31 行业全覆盖)')
        elif BAO_OK and os.path.exists(os.path.join(CACHE_DIR, 'industry_map.json')):
            return _fetch_baostock_all(mkt, meta)
        else:
            mode, src, fetcher = 'legulegu', LEGULEGU_INDUSTRY, industry_pb_legulegu
            _log('路径: legulegu(免费·部分行业)')

        records = []
        for name, code in src.items():
            try:
                s = fetcher(code)
                time.sleep(0.3)
                if s is None or s.empty:
                    continue
                c = crowding(s, mkt, meta.get('hist_ok', False))
                if c is None:
                    continue
                records.append(_record(name, code, c))
            except Exception as e:  # noqa
                _log(f'  {name} 异常: {str(e)[:40]}')
                continue
        return records or [_placeholder('行业PB数据源(legulegu)暂不可用，未取到任何行业；建议本机运行一次建立缓存。')]
    except Exception as e:  # noqa
        logger.warning(f'行业拥挤度计算失败（已优雅标灰）: {e}')
        return [_placeholder(f'行业拥挤度计算异常: {str(e)[:80]}')]


def _fetch_baostock_all(mkt, meta) -> List[dict]:
    """baostock 路径：聚合全申万一级行业（覆盖更全）。"""
    from collections import Counter

    m = bao_industry_map()
    keep = {k: c for k, c in Counter(m.values()).items() if c >= 10}
    records = []
    for name in sorted(keep):
        try:
            s = industry_pb_baostock(name)
            if s is None or s.empty:
                continue
            c = crowding(s, mkt, meta.get('hist_ok', False))
            if c is None:
                continue
            records.append(_record(name, name, c))
        except Exception as e:  # noqa
            _log(f'  {name} 异常: {str(e)[:40]}')
            continue
        time.sleep(0.05)
    return records or [_placeholder('baostock 缓存缺失：需先运行 bao_backfill_pb 建立历史')]
