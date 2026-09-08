# -*- coding: utf-8 -*-
"""韭圈儿（funddb.cn = jiucaishuo.com）指数数据适配器（#1365 / #275）。

数据源为公开 H5 接口（免登录、无签名），接口契约实测留档见
docs/working-notes/index-catalog-sources-research-2026-09-08.md「韭圈儿专项结论」。
决策修订记录：2026-09-08 曾定调「不逆向韭圈儿」；2026-09-09 实测确认
index-basic / fundindex/detail 为免登录公开端点（无签名机制），属公开源
best-effort 接入，非逆向。**稳定性风险自担**：私有接口可能无通知变更，
930950（中证偏股基金）/ 399317（国证A指）始终是权威 fallback。

接口（POST application/json）：
- /v2/guzhi-new2/index-basic   最新收盘价 + PE/PB/估值分位（免登录）
- /v2/fundindex/detail         近 N 月累计收益率序列（date=月数，上限 120=10 年）

万得全A（881001.WI）点位为**反推派生数据**：P(t) = P_now × (1+r(t)) / (1+r_end)。
口径为价格指数（非全收益）；锚点随最新收盘平移，区间越长累积误差越大——
每日增量自愈，不做跨年回测级依赖（回测口径另议，#275）。

健壮性约定（与 TiantianAdvisorAdapter 同源）：
- 模块级节流：相邻任意请求间隔 ≥ REQUEST_INTERVAL 秒；
- 指数退避重试：单接口最多 MAX_RETRIES 次，仍失败抛 RuntimeError 由上层容错；
- requests.Session 复用连接；UA/Referer 伪装为韭圈儿 H5 端（公开可见）。
"""

import json
import threading
import time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import requests
from loguru import logger

API_BASE = 'https://api.jiucaishuo.com'
API_BASIC = API_BASE + '/v2/guzhi-new2/index-basic'
API_DETAIL = API_BASE + '/v2/fundindex/detail'

HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': (
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
    ),
    'Referer': 'https://app.jiucaishuo.com/',
}

REQUEST_INTERVAL = 2.0
MAX_RETRIES = 3
RETRY_BACKOFF = (2, 4, 8)
TIMEOUT = 25

# 韭圈儿 H5 端固定版本参数（公开抓包可见，无敏感信息）
COMMON_PAYLOAD = {'type': 'h5', 'version': '2.5.9', 'ss': ''}

_throttle_lock = threading.Lock()
_last_request_at = 0.0


class JiucaishuoAdapter:
    """韭圈儿指数数据适配器（独立于 akshare/xalpha 数据源体系）。"""

    def get_name(self) -> str:
        return 'jiucaishuo'

    def get_version(self) -> str:
        return '1.0.0'

    def __init__(self) -> None:
        self.logger = logger
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    # ── HTTP ──

    def _post(self, path: str, payload: dict) -> Dict[str, Any]:
        global _last_request_at
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        last_error: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            with _throttle_lock:
                wait = REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
                if wait > 0:
                    time.sleep(wait)
                try:
                    resp = self._session.post(
                        path if path.startswith('http') else API_BASE + path, data=body, timeout=TIMEOUT
                    )
                finally:
                    _last_request_at = time.monotonic()
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') != 0:
                    raise RuntimeError(f'{path} 业务失败: {data}')
                return data
            last_error = RuntimeError(f'{path} HTTP {resp.status_code}')
            backoff = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
            self.logger.warning(f'{path} 第 {attempt + 1} 次请求失败（{last_error}），{backoff}s 后重试')
            time.sleep(backoff)
        raise RuntimeError(f'{path} 重试 {MAX_RETRIES} 次仍失败: {last_error}')

    # ── 纯解析（便于单测，不触网） ──

    @staticmethod
    def parse_index_basic(resp: Dict[str, Any]) -> Dict[str, Any]:
        """解析 index-basic 响应 → {gu_name, close, pe, pb, pe_pct}。"""
        d = resp.get('data') or {}
        out: Dict[str, Any] = {'gu_name': d.get('gu_name')}
        for row in d.get('table') or []:
            name = row.get('name')
            try:
                if name == '收盘价':
                    out['close'] = float(row['new_value'])
                elif name == '市盈率':
                    out['pe'] = float(row['new_value'])
                    pct = (row.get('new_percent_value') or {}).get('value')
                    out['pe_pct'] = pct
                elif name == '市净率':
                    out['pb'] = float(row['new_value'])
            except (KeyError, TypeError, ValueError):
                continue
        if 'close' not in out:
            raise ValueError('index-basic 响应中无收盘价（接口形态可能已变更）')
        return out

    @staticmethod
    def parse_return_series(resp: Dict[str, Any]) -> Tuple[List[str], List[float]]:
        """解析 fundindex/detail 响应 → (日期列表, 累计收益率%列表)。series[0]=本指数。"""
        tb = ((resp.get('data') or {}).get('tb_data')) or {}
        xs = tb.get('x_data') or []
        series = tb.get('series') or []
        if not xs or not series:
            raise ValueError('fundindex/detail 响应无序列数据（接口形态可能已变更）')
        rets = [float(v) for v in series[0].get('data') or []]
        if len(xs) != len(rets):
            raise ValueError(f'x_data({len(xs)}) 与 series({len(rets)}) 长度不一致')
        return [str(x) for x in xs], rets

    # ── 面向 Job 的高层接口 ──

    def fetch_index_daily(self, gu_code: str, months: int = 120) -> Dict[str, Any]:
        """获取指数点位序列（反推派生）+ 最新快照。

        返回 {gu_code, gu_name, snapshot, rows}；
        rows = [{'trade_date': 'YYYY-MM-DD', 'close': float, 'ret_pct': float}]。
        """
        basic_resp = self._post(
            API_BASIC,
            {'gu_code': gu_code, 'category': 'pe', 'year': 10, **COMMON_PAYLOAD},
        )
        basic = self.parse_index_basic(basic_resp)

        detail_resp = self._post(
            API_DETAIL,
            {
                'gu_code': gu_code,
                'date': months,
                'ben': '',
                'search_code': '',
                's_time': '',
                'e_time': '',
                'line_type': 'sy',
                'is_close': 2,
                **COMMON_PAYLOAD,
            },
        )
        xs, rets = self.parse_return_series(detail_resp)

        # 反推：P(t) = P_now × (1 + r(t)/100) / (1 + r_end/100)
        r_end = rets[-1]
        base = basic['close'] / (1 + r_end / 100)
        rows = []
        for x, v in zip(xs, rets):
            try:
                trade_date = date.fromisoformat(x)
            except ValueError:
                self.logger.warning(f'无法解析日期 {x!r}，跳过该行')
                continue
            rows.append({'trade_date': trade_date, 'close': round(base * (1 + v / 100), 4), 'ret_pct': v})
        if not rows:
            raise ValueError('收益率序列解析后为空（日期格式可能已变更）')
        self.logger.info(f'韭圈儿 {gu_code} 序列 {len(rows)} 条（近 {months} 月），最新收盘 {basic["close"]}')
        return {
            'gu_code': gu_code,
            'gu_name': basic.get('gu_name'),
            'snapshot': basic,
            'rows': rows,
        }
