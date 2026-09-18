# -*- coding: utf-8 -*-
"""fundfof 拥挤度外部源（**临时**，可一键关停）· 行业 + 赛道
============================================================
定位（务必先读）：这是**过渡方案**，不是长期数据源。

背景（#1431 决策）：行业拥挤度的目标维度（换手率 / 60 日线上占比 / 60 日新高占比 /
融资买入占比 / 百万大单）在免费栈里拿不到——
  · 申万官网 `index_hist_sw` 无换手率字段；
  · 拿不到申万一级成分股（akshare 无 `sw_index_first_cons`，`sw_index_third_cons` 实测 0 行），
    故 60 日线上/新高占比无法自算；
  · 东财个股日线受限流（RemoteDisconnected）；PB 行业分位无免费源。
而 `www.fundfof.com` 的公开接口恰好提供上述全部维度（申万代码 + 名称 + 分位），
先接入把表补齐，等我方自有数据（付费源 / 自建成分股映射）就位后**直接切掉**。

合规与风险（诚实交代）：
  · 该接口为其自家后端服务，**未授权**使用；对方随时可能加签名 / 限流 / 改结构 / 封 IP；
  · 因此本模块只做「低频 + 磁盘缓存 + 失败静默降级」，绝不重试轰炸，也绝不绕过任何鉴权；
  · 仅用于个人自用验证，**不应对外发布**；对外形态必须换成自有或授权数据源。

开关：环境变量 `FUNDFOF_CROWDING_ENABLED`（默认开启；置 `0/false/no/off` 即关停 → 回落原三路径）。
      环境变量 `FUNDFOF_CROWDING_MERGE_SW_BIAS`（默认开启；置 `0/false/no/off` 即关停）：BIASn 补齐会调
      akshare `index_hist_sw`，已按 #1566 验收标准 4 恢复默认开启；关掉可省掉每次温度任务的这次额外请求。
      ⚠️ 归因更正（#1566）：原注释称该路径会触发 `py_mini_racer` 内嵌 V8 的原生 FATAL 崩溃
      （引用 #1511），**不成立**——`index_hist_sw` 全程只有 `requests.get`，不碰 V8。
      真因是并发构造 `MiniRacer`（#1566），已由 `app/core/v8_guard.py` 进程级修复。

维度（category）：
  · `sw`    → 申万一级 31 行业，落 `source='industry_crowding'` / `item_type='industry'`
              （BIASn 由申万官网源补齐；乖离率该接口不提供）
  · `track` → 18 个热门赛道（概念指数 + 申万细分，如 光通信 / AI芯片 / 半导体设备），
              落 `source='track_crowding'` / `item_type='concept'`（无 BIASn，该维度不适用）

接口（匿名 GET，无需鉴权，实测 200）：
  · GET /api/market/crowding/latest?category=sw|track   —— 快照（实测 sw=31 行 / track=18 行）
  · GET /api/market/crowding/indicators                 —— 指标清单
  · GET /api/market/crowding/history                    —— 时间序列（本期未用）
  注：参数名是 `category`（不是 `cat`）；`concept` / `hot` 等取值实测 422，勿用。

字段映射（→ 我们 market_multi_items 的 data 结构）：
  crowding_pct(综合拥挤度分位) → crowding_pct；crowding → crowding_value
  turnover_ratio/turnover_pct  → amount_pct / amount_pct_rank（成交额占全A比例及其分位）
  turnover_rate/turnover_rate_pct → turnover / turnover_rank（换手率及其分位）
  ma60_ratio/ma60_pct          → ma60_ratio / ma60_ratio_pct（60 日均线上占比）
  high60_ratio/high60_pct      → high60_ratio / high60_ratio_pct（60 日新高占比）
  margin_ratio/margin_pct      → margin_ratio / margin_ratio_pct（融资买入占比）
  big_order/big_order_pct      → big_order / big_order_pct（百万大单）
  PB 三列（ind_pb/multiple/mkt_pb）该接口不提供 → 保持 None（口径不混用，前端文案已注明）。
  数值缺失一律 None（前端显示 `--`），绝不用 0 顶替；赛道的 big_order / margin 存在整列为空的情况。
"""

import datetime
import json
import os
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.cache import resolve_cache_subdir

try:
    import requests

    HAS_REQUESTS = True
except Exception as e:  # noqa: BLE001
    HAS_REQUESTS = False
    logger.warning(f'fundfof 外部源依赖 requests 缺失，将跳过（回落原路径）: {e}')

try:
    from app.core.time_utils import now_shanghai
except Exception:  # noqa: BLE001

    def now_shanghai():
        return datetime.datetime.now()


def fundfof_cache_dir() -> str:
    """fundfof 拥挤度的本地缓存目录（#1539）。

    原先硬编码为 `HERE/cache/fundfof_crowding`（**源码树内**），不认 env `CACHE_FILE_DIR`：
    按环境指定缓存目录（容器 / 只读文件系统 / CI）时只生效一半。现经
    `resolve_cache_subdir()` 与其它缓存同源。

    ⚠️ **必须调用期解析**，不要退回模块级常量——常量在 import 那一刻就绑定了环境，
    之后再设 `CACHE_FILE_DIR` 完全无效（#1531 / #1537 / #1539 同一个坑，已连犯三次）。
    """
    return str(resolve_cache_subdir('fundfof_crowding'))


CACHE_FILE_NAME = 'latest.json'  # 行业（sw）缓存文件名；赛道缓存由它派生（纯字符串，不绑环境）

BASE = 'https://www.fundfof.com'
LATEST_PATH = '/api/market/crowding/latest'
REQUIRED_FIELDS = {'code', 'name', 'crowding'}

TIMEOUT = 20
CACHE_TTL_HOURS = 6  # 该接口为日频数据（带 trading_day），6 小时内复用缓存、避免重复请求

# 来源标注（前端据此显示「数据来源」提示条；不依赖对 note 文案做字符串解析）
SRC_EXTERNAL = 'fundfof'

NOTE = '数据来自 fundfof.com 公开接口（临时外部源，未授权，仅供自用验证；口径为其综合拥挤度体系）'


def _note(category: str) -> str:
    """按维度给出说明（赛道维度无 BIASn，且部分维度存在整列为空）。"""
    if category == 'track':
        return NOTE + '；赛道维度无行业乖离率，且部分赛道的大单/融资维度本身为空'
    return NOTE + '；行业乖离率由申万宏源官网源补齐'


# 维度配置：category 参数 → 落库的 source / item_type / 中文名
CATEGORY_SPECS: Dict[str, Dict[str, str]] = {
    'sw': {
        'param': 'sw',
        'source': 'industry_crowding',
        'item_type': 'industry',
        'label': '申万一级行业',
    },
    'track': {
        'param': 'track',
        'source': 'track_crowding',
        'item_type': 'concept',
        'label': '热门赛道',
    },
}

_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'

_TRUTHY_OFF = {'0', 'false', 'no', 'off'}


def enabled() -> bool:
    """外部源开关：默认开启，显式置 0/false/no/off 即关停（回落原三路径）。"""
    return os.getenv('FUNDFOF_CROWDING_ENABLED', '1').strip().lower() not in _TRUTHY_OFF


def _merge_sw_bias_enabled() -> bool:
    """是否用申万官网源补行业 BIASn（该接口无乖离率字段）。

    默认开启，显式置 `0/false/no/off` 才关停（白名单逻辑保留：空值 / 乱值不改变默认，
    避免误设空串意外关掉补齐路径）。

    ⚠️ 归因更正（#1566）：本开关原注释称「akshare 在部分 Windows 环境会触发 `py_mini_racer`
    （内嵌 V8）的原生 FATAL 崩溃」（#1512 / commit 73d052e05 据此默认关闭），**该归因不成立**——
    `index_hist_sw` 实现在 `akshare/index/index_research_sw.py`，全程只有 `requests.get` +
    `r.json()`，既不 import 也不调用 `py_mini_racer`。关掉它只丢功能、对崩溃零作用
    （这正是 9/17 照崩的原因）。真因见 #1566，已由 `app/core/v8_guard.py` 进程级修复；
    故本开关已按 #1566 验收标准 4 恢复默认开启（申万源可用性与数据质量仍按该标准另行核验）。
    """
    return os.getenv('FUNDFOF_CROWDING_MERGE_SW_BIAS', '1').strip().lower() not in _TRUTHY_OFF


def _log(*a):
    logger.debug(' '.join(str(x) for x in a))


def _spec(category: str) -> Dict[str, str]:
    """取维度配置；未知维度回落行业（保证调用方永不因拼错而崩）。"""
    spec = CATEGORY_SPECS.get(category)
    if spec is None:
        _log(f'  [warn] 未知 category={category!r}，回落 sw')
        return CATEGORY_SPECS['sw']
    return spec


def _cache_file(category: str) -> str:
    """缓存路径：sw 用 `CACHE_FILE_NAME`，其余按后缀派生。

    目录经 `fundfof_cache_dir()` **调用期**解析（#1539）——测试要隔离只需设 env
    `CACHE_FILE_DIR`（见 `tests/conftest.py::_isolate_cache_file_dir`），不必再 patch 模块常量。
    """
    name = CACHE_FILE_NAME if category == 'sw' else CACHE_FILE_NAME.replace('.json', f'_{category}.json')
    return os.path.join(fundfof_cache_dir(), name)


# ───────────────── 磁盘缓存 ─────────────────
def _read_cache(category: str = 'sw', max_age_hours: float = CACHE_TTL_HOURS) -> Optional[Dict[str, Any]]:
    """读缓存；超过 max_age_hours 视为过期返回 None（过期不删，留作降级兜底）。"""
    path = _cache_file(category)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as fh:
            payload = json.load(fh)
        ts = payload.get('_cached_at')
        if not ts:
            return None
        age = (datetime.datetime.now() - datetime.datetime.fromisoformat(ts)).total_seconds() / 3600
        if age > max_age_hours:
            return None
        return payload
    except Exception as e:  # noqa: BLE001
        _log('  [warn] fundfof 缓存读取失败:', str(e)[:80])
        return None


def _read_cache_any_age(category: str = 'sw') -> Optional[Dict[str, Any]]:
    """读缓存（忽略时效）：接口不可达时用最近一次成功结果降级，不让整表变空。"""
    path = _cache_file(category)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def _write_cache(payload: Dict[str, Any], category: str = 'sw') -> None:
    """写缓存：失败仅记日志，绝不抛异常（缓存不可写不应影响主链路）。"""
    try:
        os.makedirs(fundfof_cache_dir(), exist_ok=True)
        body = dict(payload)
        body['_cached_at'] = datetime.datetime.now().isoformat()
        with open(_cache_file(category), 'w', encoding='utf-8') as fh:
            json.dump(body, fh, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        _log('  [warn] fundfof 缓存写入失败:', str(e)[:80])


# ───────────────── 网络 ─────────────────
def fetch_latest(category: str = 'sw', force: bool = False) -> Optional[Dict[str, Any]]:
    """取最新快照（优先缓存；force=True 跳过时效检查直接请求）。

    Returns:
        `{'trading_day': str, 'items': [...]}`；不可达且无缓存时返回 None。
    """
    if not HAS_REQUESTS:
        return None
    spec = _spec(category)
    if not force:
        cached = _read_cache(category)
        if cached and cached.get('items'):
            _log('  fundfof[{}] 命中缓存（{} 行）'.format(category, len(cached['items'])))
            return cached

    try:
        resp = requests.get(
            BASE + LATEST_PATH,
            params={'category': spec['param']},
            headers={'User-Agent': _UA, 'Referer': BASE + '/market-crowding', 'Accept': 'application/json, */*'},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:  # noqa: BLE001
        _log('  [warn] fundfof[{}] 接口不可达（已降级）: {}'.format(category, str(e)[:100]))
        stale = _read_cache_any_age(category)
        if stale and stale.get('items'):
            _log('  fundfof[{}] 降级为历史缓存（{} 行）'.format(category, len(stale['items'])))
        return stale

    if not payload.get('success') or not isinstance(payload.get('data'), list):
        _log('  [warn] fundfof[{}] 返回结构异常: {}'.format(category, str(payload)[:120]))
        return _read_cache_any_age(category)

    body = {'trading_day': payload.get('trading_day') or '', 'items': payload['data']}
    _write_cache(body, category)
    return body


# ───────────────── 映射 ─────────────────
def _norm_code(code: Any) -> str:
    """代码归一化：`801010.SI` / `801010.SH` → `801010`；概念指数 `12693.0` → `12693`。

    赛道维度（track）的 code 形态混杂（概念指数为数字、申万细分为 xxx.SI），统一去小数与后缀。
    """
    text = str(code if code is not None else '').strip()
    if not text:
        return ''
    return text.split('.')[0].strip()


def _num(v: Any) -> Optional[float]:
    """数值安全转换：None / 非数值 → None（前端显示 `--`）。"""
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def to_records(payload: Dict[str, Any], category: str = 'sw') -> List[dict]:
    """把 fundfof 快照映射为 market_multi_items 的扁平记录（行业 / 赛道同一套字段）。

    只保留字段齐备（code/name/crowding）的行；数值缺失一律 None，不用 0 顶替。
    """
    spec = _spec(category)
    note = _note(category if category in CATEGORY_SPECS else 'sw')
    out: List[dict] = []
    for row in payload.get('items') or []:
        if not isinstance(row, dict) or not REQUIRED_FIELDS.issubset(row):
            continue
        code = _norm_code(row.get('code'))
        name = str(row.get('name') or '').strip()
        if not code or not name:
            continue
        out.append(
            {
                'kind': 'multi',
                'source': spec['source'],
                'item_type': spec['item_type'],
                'item_code': code,
                'item_name': name,
                'data': {
                    # 综合拥挤度（该接口为多维度合成口径；与我方「PB 倍数分位」口径不同，故另存原始分）
                    'crowding_pct': _num(row.get('crowding_pct')),
                    'crowding_value': _num(row.get('crowding')),
                    'crowd_src': SRC_EXTERNAL,
                    'source_kind': 'external_temp',  # 前端据此显示「外部临时源」提示条
                    # PB 三列该接口不提供：保持 None，绝不与其它口径混用
                    'multiple': None,
                    'ind_pb': None,
                    'mkt_pb': None,
                    'hist_ok': True,
                    'history_days': None,
                    # 成交额占全 A 比例及其分位
                    'amount_pct': _num(row.get('turnover_ratio')),
                    'amount_pct_rank': _num(row.get('turnover_pct')),
                    # 换手率及其分位
                    'turnover': _num(row.get('turnover_rate')),
                    'turnover_rank': _num(row.get('turnover_rate_pct')),
                    # 60 日均线上占比及其分位
                    'ma60_ratio': _num(row.get('ma60_ratio')),
                    'ma60_ratio_pct': _num(row.get('ma60_pct')),
                    # 60 日新高占比及其分位
                    'high60_ratio': _num(row.get('high60_ratio')),
                    'high60_ratio_pct': _num(row.get('high60_pct')),
                    # 融资买入占比及其分位（赛道维度存在整列为空）
                    'margin_ratio': _num(row.get('margin_ratio')),
                    'margin_ratio_pct': _num(row.get('margin_pct')),
                    # 百万大单及其分位（该接口 big_order_pct 实测恒为 null）
                    'big_order': _num(row.get('big_order')),
                    'big_order_pct': _num(row.get('big_order_pct')),
                    'amount_src': SRC_EXTERNAL,
                    'note': note,
                },
                'collected_at': now_shanghai(),
                'stale': False,
            }
        )
    return out


def _merge_sw_bias(records: List[dict]) -> None:
    """用申万官网源补 BIASn（就地修改；失败静默，不影响主数据）。

    该接口无乖离率字段，而我方表有「乖离 6/20/60 日」列，故复用 `sw_industry_source`
    的简单 MA 口径补齐；申万源不可达时该三列留空（不阻塞）。仅对行业维度适用。

    ⚠️ 归因更正（#1566）：本路径调的是 akshare `index_hist_sw`，**不经过 py_mini_racer**，
    与 V8 原生崩溃无关（该崩溃由并发构造 MiniRacer 引起，现由 `app/core/v8_guard.py` 兜住）；
    故不再默认关闭——需要省掉这次额外请求时显式置 `FUNDFOF_CROWDING_MERGE_SW_BIAS=0`。
    """
    try:
        from app.services.thermometer.sw_industry_source import (
            fetch_sw_metrics,
            list_sw_industries,
        )

        names = list_sw_industries()
        if not names:
            return
        metrics = fetch_sw_metrics(list(names.keys()))
        if not metrics:
            return
        patched = 0
        for rec in records:
            m = metrics.get(rec['item_code'])
            if not m:
                continue
            data = rec['data']
            data['bias6'] = _num(m.get('bias6'))
            data['bias20'] = _num(m.get('bias20'))
            data['bias60'] = _num(m.get('bias60'))
            patched += 1
        _log(f'  申万官网源补齐 BIASn：{patched} 行')
    except Exception as e:  # noqa: BLE001
        _log('  [warn] BIASn 补齐失败（不影响主数据）:', str(e)[:80])


def fetch_fundfof_crowding(category: str = 'sw') -> List[dict]:
    """外部源主入口：开关 + 缓存 + 映射（行业维度额外补 BIASn）。

    Args:
        category: `sw`（申万一级行业，默认）/ `track`（热门赛道）。

    Returns:
        List[dict]：扁平 multi 记录；开关关闭 / 依赖缺失 / 接口与缓存都不可用时返回 `[]`
        （由调用方回落原路径，行为与接入前一致，**不抛异常**）。
    """
    if not enabled():
        _log('fundfof 外部源已关闭（FUNDFOF_CROWDING_ENABLED=0）')
        return []
    if not HAS_REQUESTS:
        return []

    spec = _spec(category)
    key = category if category in CATEGORY_SPECS else 'sw'
    payload = fetch_latest(key)
    if not payload or not payload.get('items'):
        return []

    records = to_records(payload, key)
    if not records:
        return []

    if key == 'sw' and _merge_sw_bias_enabled():
        _merge_sw_bias(records)

    _log(
        'fundfof[{}] 接入：{} 条（{}，trading_day={}）'.format(
            key, len(records), spec['label'], payload.get('trading_day') or '?'
        )
    )
    return records


def fetch_fundfof_track_crowding() -> List[dict]:
    """热门赛道维度（`category=track`，18 条）：无 BIASn，失败返回 `[]`。"""
    return fetch_fundfof_crowding('track')


# ───────────────── 历史序列（趋势视图，不落库、按需代理） ─────────────────
HISTORY_PATH = '/api/market/crowding/history'

# 白名单（本机实测 2026-09-14：daily 会 422；freq 默认 weekly / mode 默认 value）
HISTORY_CATEGORIES = tuple(CATEGORY_SPECS)
HISTORY_FREQS = ('weekly', 'monthly')
HISTORY_MODES = ('value', 'pct')
HISTORY_INDICATORS = (
    'crowding',
    'turnover_ratio',
    'turnover_rate',
    'ma60_ratio',
    'high60_ratio',
    'margin_ratio',
    'big_order',
)
HISTORY_CACHE_TTL_HOURS = 6


def _history_cache_file(category: str, indicator: str, freq: str, mode: str) -> str:
    return os.path.join(fundfof_cache_dir(), f'history_{category}_{indicator}_{freq}_{mode}.json')


def fetch_history(
    category: str = 'sw',
    indicator: str = 'crowding',
    freq: str = 'weekly',
    mode: str = 'value',
) -> Optional[Dict[str, Any]]:
    """取历史序列（趋势视图用；**不落库**，按需代理 + 磁盘缓存）。

    历史序列是「按需读取」的长序列（31 行 × 30 期），塞进 `market_multi_items`（最新快照表）
    不合适，故本函数直连外部源并缓存，由视图层代理给前端。

    Args:
        category: `sw` / `track`。
        indicator: 见 `HISTORY_INDICATORS`。
        freq: `weekly` / `monthly`（实测 `daily` 会 422）。
        mode: `value`（原值）/ `pct`（分位）。

    Returns:
        `{'dates': [...], 'items': [{'code','name','values':[...]}], 'freq','mode','indicator'}`
        —— 参数非法 / 关停 / 依赖缺失 / 不可达且无缓存时返回 None（由视图层给出提示，不报错）。
    """
    if not enabled() or not HAS_REQUESTS:
        return None
    if (
        category not in HISTORY_CATEGORIES
        or indicator not in HISTORY_INDICATORS
        or freq not in HISTORY_FREQS
        or mode not in HISTORY_MODES
    ):
        _log(f'  [warn] history 参数非法：{category}/{indicator}/{freq}/{mode}')
        return None

    cache_path = _history_cache_file(category, indicator, freq, mode)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding='utf-8') as fh:
                cached = json.load(fh)
            ts = cached.get('_cached_at')
            if ts:
                age = (datetime.datetime.now() - datetime.datetime.fromisoformat(ts)).total_seconds() / 3600
                if age <= HISTORY_CACHE_TTL_HOURS and cached.get('items'):
                    return cached
        except Exception as e:  # noqa: BLE001
            _log('  [warn] history 缓存读取失败:', str(e)[:80])

    try:
        resp = requests.get(
            BASE + HISTORY_PATH,
            params={'category': category, 'indicator': indicator, 'freq': freq, 'mode': mode},
            headers={'User-Agent': _UA, 'Referer': BASE + '/market-crowding', 'Accept': 'application/json, */*'},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:  # noqa: BLE001
        _log('  [warn] history 接口不可达（已降级）:', str(e)[:100])
        return _read_history_cache_any_age(cache_path)

    if not payload.get('success') or not isinstance(payload.get('data'), list):
        _log('  [warn] history 返回结构异常:', str(payload)[:120])
        return _read_history_cache_any_age(cache_path)

    body = {
        'dates': payload.get('dates') or [],
        'items': payload['data'],
        'freq': payload.get('freq') or freq,
        'mode': payload.get('mode') or mode,
        'indicator': payload.get('indicator') or indicator,
        'category': category,
        'source_kind': 'external_temp',
        'note': NOTE,
    }
    try:
        os.makedirs(fundfof_cache_dir(), exist_ok=True)
        disk = dict(body)
        disk['_cached_at'] = datetime.datetime.now().isoformat()
        with open(cache_path, 'w', encoding='utf-8') as fh:
            json.dump(disk, fh, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        _log('  [warn] history 缓存写入失败:', str(e)[:80])
    return body


def _read_history_cache_any_age(cache_path: str) -> Optional[Dict[str, Any]]:
    """接口不可达时用旧缓存降级（忽略 TTL），让趋势图仍有内容而不是空白。"""
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, encoding='utf-8') as fh:
            cached = json.load(fh)
        return cached if cached.get('items') else None
    except Exception:  # noqa: BLE001
        return None
