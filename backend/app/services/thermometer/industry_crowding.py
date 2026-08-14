# -*- coding: utf-8 -*-
"""
行业拥挤度（"韭菜投资学"方法）· v2 接入版 · 三维并列
====================================================
原理： 拥挤度 = 各行业 PB 相对 A 股整体 PB 的倍数，在历史(2010-06起)中的百分位。
       倍数 = 行业PB / 全A中位PB；分位越低=相对A股越便宜(适合埋伏)，越高=越热门。

三维口径（均以历史百分位呈现，见 issue #892）：
  1. PB 倍数百分位（估值视角，现有）：行业PB / 全A中位PB 的历史百分位。
  2. 成交额占比百分位（资金热度）：行业成交额 / 全A成交额占比的历史百分位。
  3. 换手率百分位（资金热度）：行业换手率的历史百分位。

 数据源：
  · PB 维度（默认 legulegu 免费，无需 token）：覆盖部分申万行业（消费/医药/金融/信息…）。
     · 分母(全A中位PB)：优先 ak.stock_a_all_pb()（legulegu，2005+全历史，免费无 token）。
     · 分子(行业PB)：legulegu index-basic-pb（免费，需 token，由 akshare 内置 JS 生成）。
     · 分母兜底链：legulegu 不可用 → 本地缓存 → baostock 批量当日全A中位PB → 东财实时 → 全失败整组标灰。
     · 分子全覆盖路径（可选，预留）：baostock(申万一级全行业)/tushare(申万一级31行业)，
       需本机直连 baostock 或 TUSHARE_TOKEN，沙箱网络不可达故默认不走。
  · 成交额/换手率维度（东财 push2his K线接口）：legulegu 的 sw-congestion / sw-amount-ratio
    为 VIP 接口（免费 token 返回 {"vip": false}，拿不到数据），故改用东财行业指数历史
    （2011-08 起，15 年，满足分位窗口）；成交额分母用中证全指 000985（覆盖沪深全A）。

 请求规范（东财 WAF 敏感，防封禁，见 core/requests_patch.py 文件头）：
  · 本地缓存优先（cache/em_industry_hist/，运行时缓存不入库）：缓存新鲜直接复用，0 请求；
  · 缓存过期只拉增量（beg=缓存最新日期），不重复全量拉取；
  · 请求间隔克制：行业循环 1.5s，请求前 0.5s，失败退避 2s 后最多重试 1 次；
  · 完整浏览器请求头伪装（UA/Referer/Accept/Accept-Language）。
  教训：连续 9 次全量请求会触发东财 IP 级 RemoteDisconnected 封禁（限流窗口 5+ 分钟），
        请求必须克制、伪装、带缓存，绝不能一上来就打流量。

健壮性：所有网络调用均 try/except + timeout，失败整组返回 stale 占位；
        东财两维失败仅对应字段为 None 并在 note 标注，绝不抛异常阻塞
        TemperatureJob 主链路（与 README 降级设计一致）。

接入方式（供 TemperatureJob 调用）：
    from app.services.thermometer.industry_crowding import fetch_industry_crowding
    records = fetch_industry_crowding()   # List[dict], 扁平 multi 格式，可直接 save_multi_items
"""

import datetime
import json
import os
import re
import time
from typing import List, Optional

from loguru import logger

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
ALLPB_CACHE = os.path.join(
    HERE, 'data', 'all_pb.csv'
)  # 全A中位PB历史基线(跨源复用分母)；是基线数据非运行时缓存，禁止删除(见 data/README.md)

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
    """把全A中位PB序列(按日期索引)落盘缓存，供后续复用 / 限流时回退。

    防护：data/all_pb.csv 是受保护的历史基线（见 data/README.md，禁止删除/清理）。
    若磁盘已存在明显更长的历史文件（>1000 行且新序列不足其一半），视为降级/污染，
    拒绝用短序列覆盖，避免误删基线（例如兜底分支只产出一个当日点、或测试误写）。
    仅在基线文件缺失/为空时才允许新建。
    """
    try:
        if os.path.exists(ALLPB_CACHE):
            existing_rows = 0
            try:
                with open(ALLPB_CACHE, encoding='utf-8') as _f:
                    existing_rows = max(existing_rows, sum(1 for _ in _f) - 1)
            except Exception:  # noqa
                existing_rows = 0
            if existing_rows > 1000 and len(s) < existing_rows / 2:
                logger.warning(
                    f'[分母] 拒绝覆盖 all_pb.csv：新序列 {len(s)} 行 < 现有 {existing_rows} 行，'
                    f'疑似降级或污染，跳过写入以保留基线'
                )
                return
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


# ───────────────── 东财两维：成交额占比分位 + 换手率分位 ─────────────────
# legulegu 的 sw-congestion / sw-amount-ratio 为 VIP 接口（免费 token 拿不到数据），
# 改用东财 push2his K线接口拉行业指数历史（2011-08 起，15 年，满足分位窗口）。
#
# 请求规范（东财 WAF 敏感，防封禁，见 core/requests_patch.py 文件头）：
#   · 本地缓存优先（cache/em_industry_hist/，运行时缓存不入库）：新鲜直接复用，0 请求；
#   · 缓存过期只拉增量（beg=缓存最新日期），不重复全量拉取；
#   · 请求间隔克制：行业循环 1.5s，请求前 0.5s，失败退避 2s 后最多重试 1 次；
#   · 完整浏览器请求头伪装（UA/Referer/Accept/Accept-Language）。
#   教训：连续 9 次全量请求会触发东财 IP 级 RemoteDisconnected 封禁（限流窗口 5+ 分钟），
#         请求必须克制、伪装、带缓存，绝不能一上来就打流量。

EM_HIST_CACHE_DIR = os.path.join(HERE, 'cache', 'em_industry_hist')  # 东财行业指数历史缓存（运行时缓存，不入库）

# 东财浏览器化请求头（与 requests_patch._EM_HEADERS 一致；requests_patch 会合并东财头，调用方头覆盖）
_EM_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    ),
    'Referer': 'https://quote.eastmoney.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}


def _em_secid(code: str) -> str:
    """中证指数代码 -> 东财 secid（沪市前缀 1，深市前缀 0）。"""
    base = code.split('.')[0]
    return ('1.' if code.endswith('.SH') else '0.') + base


def _em_cache_path(code: str) -> str:
    """东财历史缓存文件路径：code 中的点替换为下划线（如 000985_SH.parquet）。"""
    return os.path.join(EM_HIST_CACHE_DIR, code.replace('.', '_') + '.parquet')


def _em_cache_load(code: str) -> Optional[pd.DataFrame]:
    """读东财历史缓存（date 列 -> 索引）；优先 parquet，无引擎环境回退 CSV；缺失/损坏返回 None。"""
    try:
        path = _em_cache_path(code)
        if not os.path.exists(path):
            csv_path = path[: -len('.parquet')] + '.csv'
            if not os.path.exists(csv_path):
                return None
            path = csv_path
        df = pd.read_csv(path, parse_dates=['date']) if path.endswith('.csv') else pd.read_parquet(path)
        df['date'] = pd.to_datetime(df['date'])
        df = df.dropna(subset=['amount', 'turnover']).set_index('date').sort_index()
        return df if not df.empty else None
    except Exception as e:  # noqa
        _log(f'  [warn] 东财历史缓存读取失败({code}):', str(e)[:60])
        return None


def _em_cache_save(code: str, df: pd.DataFrame) -> None:
    """写东财历史缓存（date 列落盘）；优先 parquet，无引擎环境回退 CSV；失败仅记日志，绝不抛异常。"""
    try:
        os.makedirs(EM_HIST_CACHE_DIR, exist_ok=True)
        out = df.reset_index()
        out.columns = ['date', 'amount', 'turnover']
        path = _em_cache_path(code)
        try:
            out.to_parquet(path, index=False)
        except ImportError:
            # 环境无 pyarrow/fastparquet 时回退 CSV（读侧按扩展名自动识别）
            out.to_csv(path[: -len('.parquet')] + '.csv', index=False)
    except Exception as e:  # noqa
        _log(f'  [warn] 东财历史缓存写入失败({code}):', str(e)[:60])


def _recent_trading_day() -> datetime.date:
    """最近交易日：今天若非周末则为今天，否则上一个工作日（周五）。

    节假日无法精确判断，由 _em_cache_fresh 以「今天-3天」兜底放宽。
    """
    today = datetime.date.today()
    if today.weekday() < 5:
        return today
    return today - datetime.timedelta(days=today.weekday() - 4)


def _em_cache_fresh(cached: pd.DataFrame) -> bool:
    """缓存是否新鲜：最新日期 >= 最近交易日；节假日兜底放宽为 >= 今天-3天。"""
    last = cached.index[-1].date()
    if last >= _recent_trading_day():
        return True
    # 节假日（长假）无法精确判断最近交易日：缓存落在 3 天内视为新鲜，避免无谓请求
    return last >= datetime.date.today() - datetime.timedelta(days=3)


def _em_session() -> requests.Session:
    """东财专用会话：覆盖 requests_patch 挂的 total=3 自动重试适配器。

    requests_patch 会给所有 Session 挂重试适配器，失败时立刻重试 3 次，叠加多行业请求
    极易触发东财 IP 级封禁；此处用无重试适配器覆盖，重试节奏由 _em_fetch 自己控制。
    """
    from requests.adapters import HTTPAdapter

    s = requests.Session()
    s.mount('https://', HTTPAdapter())
    s.mount('http://', HTTPAdapter())
    return s


def _em_fetch(code: str, beg) -> Optional[pd.DataFrame]:
    """东财 K线接口单次拉取（beg=0 全量 / beg='YYYYMMDD' 增量）。

    请求规范：完整浏览器头伪装；请求前 sleep 0.5s；失败 sleep 2s 退避后重试最多 1 次；
    用无重试适配器的专用会话，避免 requests_patch 的 total=3 自动重试在失败时连续轰炸 WAF。
    """
    params = {
        'secid': _em_secid(code),
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
        'klt': 101,
        'fqt': 0,
        'beg': beg,
        'end': 20500101,
    }
    session = _em_session()
    for attempt in range(2):  # 首次 + 最多 1 次重试
        time.sleep(0.5)
        try:
            r = session.get(
                'https://push2his.eastmoney.com/api/qt/stock/kline/get',
                params=params,
                headers=dict(_EM_HEADERS),
                timeout=10,
            )
            klines = (r.json().get('data') or {}).get('klines') or []
            if not klines:
                return None
            rows = []
            for line in klines:
                parts = line.split(',')
                # f51=日期, f57=成交额, f61=换手率（CSV 顺序：日期,开,收,高,低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率）
                rows.append({'date': parts[0], 'amount': parts[6], 'turnover': parts[10]})
            df = pd.DataFrame(rows)
            df['date'] = pd.to_datetime(df['date'])
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
            df['turnover'] = pd.to_numeric(df['turnover'], errors='coerce')
            df = df.dropna(subset=['amount', 'turnover']).set_index('date')
            return df if not df.empty else None
        except Exception as e:  # noqa
            _log(f'  [warn] 东财行业指数历史抓取失败({code}) 第{attempt + 1}次:', str(e)[:60])
            if attempt == 0:
                time.sleep(2)  # 退避后重试一次
    return None


def _em_industry_hist(code: str) -> Optional[pd.DataFrame]:
    """东财 push2his K线接口拉行业指数历史（带本地缓存 + 增量 + 限速）。

    请求规范（东财 WAF 敏感，防封禁，见模块 docstring）：
      · 本地缓存优先：缓存新鲜（最新日期 >= 最近交易日）直接返回，0 网络请求；
      · 缓存过期只拉增量（beg=缓存最新日期），不重复全量拉取；
      · 拉取失败/无新数据时降级用缓存旧数据（无缓存则返回 None），绝不抛异常。

    返回 DataFrame（date 索引），含 amount(成交额) 与 turnover(换手率) 两列。
    """
    cached = _em_cache_load(code)
    if cached is not None and _em_cache_fresh(cached):
        _log(f'  [东财] {code} 缓存新鲜（最新 {cached.index[-1].date()}），直接复用，0 请求')
        return cached

    # 增量起点：有缓存则从缓存最新日期拉增量；无缓存则全量（beg=0）
    beg = cached.index[-1].strftime('%Y%m%d') if cached is not None else 0
    df = _em_fetch(code, beg)
    if df is None or df.empty:
        # 拉取失败/无新数据：有缓存则降级用缓存旧数据，无缓存返回 None
        if cached is not None:
            _log(f'  [东财] {code} 增量拉取失败/无新数据，降级用缓存（最新 {cached.index[-1].date()}）')
            return cached
        return None

    if cached is not None:
        # 合并增量并去重（东财 beg 可能包含起点当天），保留最新
        merged = pd.concat([cached, df])
        merged = merged[~merged.index.duplicated(keep='last')].sort_index()
        df = merged
    _em_cache_save(code, df)
    return df


def _amount_ratio_rank(ind_hist: Optional[pd.DataFrame], mkt_hist: Optional[pd.DataFrame]) -> Optional[dict]:
    """成交额占比分位：行业成交额 / 中证全指成交额 的历史占比序列 -> 当前占比的历史百分位。

    返回 {'amount_pct': 当前占比%, 'amount_pct_rank': 历史百分位}；历史不足 200 天返回 None。
    """
    if ind_hist is None or mkt_hist is None:
        return None
    df = pd.concat([ind_hist['amount'].rename('ind'), mkt_hist['amount'].rename('mkt')], axis=1).dropna()
    if len(df) < 200:
        return None
    ratio = df['ind'] / df['mkt']
    cur = ratio.iloc[-1]
    return {
        'amount_pct': round(cur * 100, 2),
        'amount_pct_rank': round((ratio < cur).mean() * 100, 1),
    }


def _turnover_rank(ind_hist: Optional[pd.DataFrame]) -> Optional[dict]:
    """换手率分位：行业换手率序列 -> 当前值的历史百分位。

    返回 {'turnover': 当前值, 'turnover_rank': 历史百分位}；历史不足 200 天返回 None。
    """
    if ind_hist is None:
        return None
    s = ind_hist['turnover'].dropna()
    if len(s) < 200:
        return None
    cur = s.iloc[-1]
    return {
        'turnover': round(cur, 2),
        'turnover_rank': round((s < cur).mean() * 100, 1),
    }


def _em_extra_dims(code: str, mkt_hist: Optional[pd.DataFrame]) -> dict:
    """东财两维（成交额占比分位 + 换手率分位）合并结果；任一失败对应字段为 None。

    内部已 try/except 兜底，绝不抛异常阻塞主链路。
    """
    out = {'amount_pct': None, 'amount_pct_rank': None, 'turnover': None, 'turnover_rank': None}
    try:
        ind_hist = _em_industry_hist(code)
        if ind_hist is None:
            return out
        ar = _amount_ratio_rank(ind_hist, mkt_hist)
        if ar:
            out.update(ar)
        tr = _turnover_rank(ind_hist)
        if tr:
            out.update(tr)
    except Exception as e:  # noqa
        _log(f'  [warn] 东财两维计算失败({code}):', str(e)[:60])
    return out


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
    note = f'倍数{c.get("multiple")} 行业PB{c.get("ind_pb")} 全A中位PB{c.get("mkt_pb")}' + (
        '' if c.get('hist_ok') else '；分位待历史积累'
    )
    if c.get('amount_pct_rank') is None or c.get('turnover_rank') is None:
        note += '；成交额/换手率分位暂不可用'
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
            'amount_pct': c.get('amount_pct'),
            'amount_pct_rank': c.get('amount_pct_rank'),
            'turnover': c.get('turnover'),
            'turnover_rank': c.get('turnover_rank'),
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
        # 东财两维分母：中证全指 000985 成交额历史（仅 legulegu 路径需要，循环外拉一次复用）
        mkt_hist = _em_industry_hist('000985.SH') if mode == 'legulegu' else None
        for name, code in src.items():
            try:
                s = fetcher(code)
                time.sleep(1.5)  # 东财请求之间保持间隔（WAF 限流敏感，见模块 docstring 请求规范）
                if s is None or s.empty:
                    continue
                c = crowding(s, mkt, meta.get('hist_ok', False))
                if c is None:
                    continue
                if mode == 'legulegu':
                    # 东财两维：成交额占比分位 + 换手率分位（失败降级 None，不阻塞主链路）
                    c.update(_em_extra_dims(code, mkt_hist))
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
