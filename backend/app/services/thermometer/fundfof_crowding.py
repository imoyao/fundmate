# -*- coding: utf-8 -*-
"""fundfof 行业拥挤度外部源（**临时**，可一键关停）
====================================================
定位（务必先读）：这是**过渡方案**，不是长期数据源。

背景（#1431 决策）：行业拥挤度的目标维度（换手率 / 60 日线上占比 / 60 日新高占比 /
融资买入占比 / 百万大单）在免费栈里拿不到——
  · 申万官网 `index_hist_sw` 无换手率字段；
  · 拿不到申万一级成分股（akshare 无 `sw_index_first_cons`，`sw_index_third_cons` 实测 0 行），
    故 60 日线上/新高占比无法自算；
  · 东财个股日线受限流（RemoteDisconnected）。
而 `www.fundfof.com` 的公开接口恰好提供上述全部维度（申万代码 + 名称 + 分位），
先接入把表补齐，等我方自有数据（付费源 / 自建成分股映射）就位后**直接切掉**。

合规与风险（诚实交代）：
  · 该接口为其自家后端服务，**未授权**使用；对方随时可能加签名 / 限流 / 改结构 / 封 IP；
  · 因此本模块只做「低频 + 磁盘缓存 + 失败静默降级」，绝不重试轰炸，也绝不绕过任何鉴权；
  · 仅用于个人自用验证，**不应对外发布**；对外形态必须换成自有或授权数据源。

开关：环境变量 `FUNDFOF_CROWDING_ENABLED`（默认开启；置 `0/false/no/off` 即关停 → 回落原三路径）。
      环境变量 `FUNDFOF_CROWDING_MERGE_SW_BIAS`（默认开启）用申万官网源补 BIASn（该接口无乖离率）。

接口（匿名 GET，无需鉴权，实测 200）：
  · GET /api/market/crowding/latest      —— 31 个申万一级行业全维度快照
  · GET /api/market/crowding/indicators  —— 指标清单（key/label/has_pct）
  · GET /api/market/crowding/history     —— 各行业时间序列（本期未用）

字段映射（→ 我们 industry_crowding 的 data 结构）：
  crowding_pct(综合拥挤度分位) → crowding_pct；crowding → crowding_value
  turnover_ratio/turnover_pct  → amount_pct / amount_pct_rank（成交额占全A比例及其分位）
  turnover_rate/turnover_rate_pct → turnover / turnover_rank（换手率及其分位）
  ma60_ratio/ma60_pct          → ma60_ratio / ma60_ratio_pct（60 日均线上占比）
  high60_ratio/high60_pct      → high60_ratio / high60_ratio_pct（60 日新高占比）
  margin_ratio/margin_pct      → margin_ratio / margin_ratio_pct（融资买入占比）
  big_order/big_order_pct      → big_order / big_order_pct（百万大单）
  PB 三列（ind_pb/multiple/mkt_pb）该接口不提供 → 保持 None（口径不混用）。
"""

import datetime
import json
import os
from typing import Any, Dict, List, Optional

from loguru import logger

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


HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, 'cache', 'fundfof_crowding')  # 运行时缓存，不入库
CACHE_FILE = os.path.join(CACHE_DIR, 'latest.json')

BASE = 'https://www.fundfof.com'
LATEST_PATH = '/api/market/crowding/latest'
REQUIRED_FIELDS = {'code', 'name', 'crowding'}

TIMEOUT = 20
CACHE_TTL_HOURS = 6  # 该接口为日频数据（带 trading_day），6 小时内复用缓存、避免重复请求
NOTE = '数据来自 fundfof.com 公开接口（临时外部源，未授权，仅供自用验证；口径为其综合拥挤度体系）'

_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
)

_TRUTHY_OFF = {'0', 'false', 'no', 'off'}


def enabled() -> bool:
    """外部源开关：默认开启，显式置 0/false/no/off 即关停（回落原三路径）。"""
    return os.getenv('FUNDFOF_CROWDING_ENABLED', '1').strip().lower() not in _TRUTHY_OFF


def _merge_sw_bias_enabled() -> bool:
    """是否用申万官网源补 BIASn（该接口无乖离率字段）。"""
    return os.getenv('FUNDFOF_CROWDING_MERGE_SW_BIAS', '1').strip().lower() not in _TRUTHY_OFF


def _log(*a):
    logger.debug(' '.join(str(x) for x in a))


# ───────────────── 磁盘缓存 ─────────────────
def _read_cache(max_age_hours: float = CACHE_TTL_HOURS) -> Optional[Dict[str, Any]]:
    """读缓存；超过 max_age_hours 视为过期返回 None（过期不删，留作降级兜底）。"""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, encoding='utf-8') as fh:
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


def _read_cache_any_age() -> Optional[Dict[str, Any]]:
    """读缓存（忽略时效）：接口不可达时用最近一次成功结果降级，不让整表变空。"""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def _write_cache(payload: Dict[str, Any]) -> None:
    """写缓存：失败仅记日志，绝不抛异常（缓存不可写不应影响主链路）。"""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        body = dict(payload)
        body['_cached_at'] = datetime.datetime.now().isoformat()
        with open(CACHE_FILE, 'w', encoding='utf-8') as fh:
            json.dump(body, fh, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        _log('  [warn] fundfof 缓存写入失败:', str(e)[:80])


# ───────────────── 网络 ─────────────────
def fetch_latest(force: bool = False) -> Optional[Dict[str, Any]]:
    """取最新快照（优先缓存；force=True 跳过时效检查直接请求）。

    Returns:
        `{'trading_day': str, 'items': [...]}`,不可达且无缓存时返回 None。
    """
    if not HAS_REQUESTS:
        return None
    if not force:
        cached = _read_cache()
        if cached and cached.get('items'):
            _log('  fundfof 拥挤度命中缓存（{} 行）'.format(len(cached['items'])))
            return cached

    try:
        resp = requests.get(
            BASE + LATEST_PATH,
            headers={'User-Agent': _UA, 'Referer': BASE + '/market-crowding', 'Accept': 'application/json, */*'},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:  # noqa: BLE001
        _log('  [warn] fundfof 接口不可达（已降级）:', str(e)[:100])
        stale = _read_cache_any_age()
        if stale and stale.get('items'):
            _log('  fundfof 降级为历史缓存（{} 行）'.format(len(stale['items'])))
        return stale

    if not payload.get('success') or not isinstance(payload.get('data'), list):
        _log('  [warn] fundfof 返回结构异常:', str(payload)[:120])
        return _read_cache_any_age()

    body = {'trading_day': payload.get('trading_day') or '', 'items': payload['data']}
    _write_cache(body)
    return body


# ───────────────── 映射 ─────────────────
def _norm_code(code: str) -> str:
    """申万代码归一化：`801010.SI` / `801010.SH` → `801010`（与 sw_industry_source 口径一致）。"""
    return str(code or '').split('.')[0].strip()


def _num(v: Any) -> Optional[float]:
    """数值安全转换：None / 非数值 → None（前端显示 `--`）。"""
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def to_records(payload: Dict[str, Any]) -> List[dict]:
    """把 fundfof 快照映射为我们 industry_crowding 的扁平 multi 记录。

    只保留字段齐备（code/name/crowding）的行；数值缺失一律 None，不用 0 顶替。
    """
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
                'source': 'industry_crowding',
                'item_type': 'industry',
                'item_code': code,
                'item_name': name,
                'data': {
                    # 综合拥挤度（该接口为多维度合成口径；与我方「PB 倍数分位」口径不同，故另存原始分）
                    'crowding_pct': _num(row.get('crowding_pct')),
                    'crowding_value': _num(row.get('crowding')),
                    'crowd_src': 'fundfof',
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
                    # 融资买入占比及其分位
                    'margin_ratio': _num(row.get('margin_ratio')),
                    'margin_ratio_pct': _num(row.get('margin_pct')),
                    # 百万大单及其分位（该接口 big_order_pct 实测为 null）
                    'big_order': _num(row.get('big_order')),
                    'big_order_pct': _num(row.get('big_order_pct')),
                    'amount_src': 'fundfof',
                    'note': NOTE,
                },
                'collected_at': now_shanghai(),
                'stale': False,
            }
        )
    return out


def _merge_sw_bias(records: List[dict]) -> None:
    """用申万官网源补 BIASn（就地修改；失败静默，不影响主数据）。

    该接口无乖离率字段，而我方表有「乖离 6/20/60 日」列，故复用 `sw_industry_source`
    的简单 MA 口径补齐；申万源不可达时该三列留空（不阻塞）。
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


def fetch_fundfof_crowding() -> List[dict]:
    """外部源主入口：开关 + 缓存 + 映射（+ 可选 BIAS 补齐）。

    Returns:
        List[dict]：31 行扁平 multi 记录；开关关闭 / 依赖缺失 / 接口与缓存都不可用时返回 `[]`
        （由调用方 `fetch_industry_crowding` 回落原三路径，行为与接入前一致）。
    """
    if not enabled():
        _log('fundfof 外部源已关闭（FUNDFOF_CROWDING_ENABLED=0）')
        return []
    if not HAS_REQUESTS:
        return []

    payload = fetch_latest()
    if not payload or not payload.get('items'):
        return []

    records = to_records(payload)
    if not records:
        return []

    if _merge_sw_bias_enabled():
        _merge_sw_bias(records)

    if payload.get('trading_day'):
        _log(f'fundfof 拥挤度接入：{len(records)} 行业（trading_day={payload["trading_day"]}）')
    return records
