# -*- coding: utf-8 -*-
"""天天基金「投顾组合」数据适配器（#1167）。

数据源为公开接口（零鉴权，免登录/签名/浏览器），逆向结论与接口契约见
docs/working-notes/advisor-ttfund-holdings-api-2026-09-08.md：

- POST https://uni-fundts.1234567.com.cn/combine/investAdviserInfo/getAdjustWarehouse
    tag=0 → latestAdjust（最新一次调仓 = 当前基金级持仓）
    tag=1 → adjustHistory（历次调仓的基金级前后占比）
- POST .../getHoldWarehouseIndustryRatio  持仓行业配置
- POST .../getTGQuoteByFavor              业绩/净值（需 tgCodeWithDateStr）
- GET  https://dataapi.1234567.com.cn/dataapi/IAAGGR/FundIATGInfoAggr  概览（字段最全）

健壮性约定（线上需长期自动化维护，非一次性脚本）：
- 模块级节流：相邻任意请求间隔 ≥ REQUEST_INTERVAL 秒，避免高频触发风控；
- 指数退避重试：单接口最多 MAX_RETRIES 次（2s/4s/8s），仍失败则该接口本轮
  返回空并由上层记 skipped，不炸整个 job；
- requests.Session 复用连接；UA 伪装为 App 端 okhttp 请求（仅 User-Agent，未伪造 Referer）；
- 通用表单参数 product/mobileKey/version/plat 来自 App 抓包（公开可见，无敏感信息）。
"""

import json
import threading
import time
from typing import Any, List, Optional

import requests
from loguru import logger

from app.core.time_utils import now_shanghai

COMBINE_HOST = 'https://uni-fundts.1234567.com.cn'
DATAPI_HOST = 'https://dataapi.1234567.com.cn'
API_QUOTE = COMBINE_HOST + '/combine/investAdviserInfo/getTGQuoteByFavor'
API_INDUSTRY = COMBINE_HOST + '/combine/investAdviserInfo/getHoldWarehouseIndustryRatio'
API_ADJUST = COMBINE_HOST + '/combine/investAdviserInfo/getAdjustWarehouse'
API_AGGR = DATAPI_HOST + '/dataapi/IAAGGR/FundIATGInfoAggr'

# App 抓包所得通用表单参数（mobileKey 为占位值即可）
COMMON_FORM = {'product': 'EFund', 'mobileKey': '123', 'version': '6.5.9', 'plat': 'Android'}
HEADERS = {
    'User-Agent': 'okhttp/4.9.3',  # App 端为原生请求，okhttp UA 最贴近真实流量
    'Content-Type': 'application/x-www-form-urlencoded',
}

REQUEST_INTERVAL = 2.0  # 相邻请求最小间隔（秒）
MAX_RETRIES = 3
RETRY_BACKOFF = (2, 4, 8)  # 指数退避（秒）
TIMEOUT = 20

# operationInt → 操作名
ADJUST_OP_NAME = {1: '建仓', 2: '加仓', 3: '减仓', 4: '新增', 5: '持平'}

# 模块级节流：同一进程内所有请求共享（适配器可能被多 job 实例化）
_throttle_lock = threading.Lock()
_last_request_ts = 0.0


def _to_float(v: Any) -> Optional[float]:
    try:
        if v in (None, ''):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


class TiantianAdvisorAdapter:
    """天天基金投顾组合数据源。"""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.logger = logger.bind(adapter='tiantian_advisor')

    # ── HTTP 基础（节流 + 重试） ──

    @staticmethod
    def _throttle() -> None:
        global _last_request_ts
        with _throttle_lock:
            wait = REQUEST_INTERVAL - (time.time() - _last_request_ts)
            if wait > 0:
                time.sleep(wait)
            _last_request_ts = time.time()

    def _request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """带节流与指数退避重试的请求；全部失败返回 None。"""
        for attempt in range(MAX_RETRIES):
            self._throttle()
            try:
                resp = self.session.request(method, url, timeout=TIMEOUT, **kwargs)
                if resp.status_code == 200:
                    return resp
                self.logger.warning(f'HTTP {resp.status_code} {url}（第 {attempt + 1}/{MAX_RETRIES} 次）')
            except requests.RequestException as e:
                self.logger.warning(f'请求异常 {url}: {e}（第 {attempt + 1}/{MAX_RETRIES} 次）')
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
        return None

    def _post_json(self, url: str, form: dict) -> Optional[dict]:
        resp = self._request('POST', url, data=form)
        if resp is None or not resp.text.strip().startswith('{'):
            return None
        try:
            return json.loads(resp.text)
        except ValueError:
            return None

    # ── 各数据面（互相独立，单面失败不影响其余） ──

    # SYL_* → 中文区间（实测核对，2026-09：Y=月 N=年 Z=周 JN=今年 LN=成立，与
    # getTGQuoteByFavor 带标签区间交叉验证自洽）。API 仅提供区间收益，不含回撤/超额。
    SYL_TO_INTERVAL = {
        'SYL_Z': 'return_1w',
        'SYL_Y': 'return_1m',
        'SYL_1N': 'return_1y',
        'SYL_JN': 'return_ytd',
        'SYL_LN': 'return_since_incep',
    }

    def fetch_overview(self, tgcode: str) -> dict:
        """投顾概览（dataapi FundIATGInfoAggr，GET，字段最全）。

        返回 {name, risk_level, strategy_desc, estab_date, returns:{区间列:值}, raw}。
        returns 由 SYL_* 实测映射而来（见 SYL_TO_INTERVAL）。
        """
        params = {
            'FIELDS': ('TGNAME,RISKLEVEL,STRATEGY_RATE,STGCONCEPT,ESTABDATE,STATUS,SYL_Z,SYL_Y,SYL_1N,SYL_JN,SYL_LN'),
            'TGCODE': tgcode,
        }
        resp = self._request('GET', API_AGGR, params=params)
        if resp is None:
            return {}
        try:
            j = json.loads(resp.text)
            data = j.get('data') if j.get('success') else None
            if isinstance(data, list) and data:
                d = data[0]
                returns = {col: _to_float(d.get(syl)) for syl, col in self.SYL_TO_INTERVAL.items()}
                return {
                    'name': d.get('TGNAME'),
                    'risk_level': str(d.get('RISKLEVEL')) if d.get('RISKLEVEL') is not None else None,
                    'strategy_desc': d.get('STGCONCEPT'),
                    'estab_date': d.get('ESTABDATE'),
                    'returns': returns,
                    'raw': d,
                }
        except (ValueError, TypeError) as e:
            self.logger.warning(f'概览解析失败 {tgcode}: {e}')
        return {}

    def fetch_industry(self, tgcode: str) -> List[dict]:
        """持仓行业配置 [{industry_name, ratio}]。"""
        form = dict(COMMON_FORM)
        form['tgCode'] = tgcode
        j = self._post_json(API_INDUSTRY, form)
        out = []
        if j and j.get('Succeed'):
            for row in j.get('Data') or []:
                name = row.get('industryName')
                if not name:
                    continue
                out.append({'industry_name': name, 'ratio': _to_float(row.get('ratio'))})
        return out

    def fetch_current_holdings(self, tgcode: str) -> dict:
        """当前基金级持仓（最新一次调仓后的占比快照）。

        返回 {'adjust_date': date_str|None, 'funds': [{fund_code, fund_name,
        pre_ratio, after_ratio, op_code, op_name}]}。
        """
        adj = self._fetch_adjust(tgcode, tag=0)
        latest = (adj or {}).get('latestAdjust') or {}
        return {
            'adjust_date': latest.get('dateStr'),
            'funds': self._flatten_funds(latest),
        }

    def fetch_adjust_history(self, tgcode: str) -> List[dict]:
        """历史调仓列表 [{adjust_date, reason, funds: [...]}]。"""
        adj = self._fetch_adjust(tgcode, tag=1)
        out = []
        for node in (adj or {}).get('adjustHistory') or []:
            out.append(
                {
                    'adjust_date': node.get('dateStr'),
                    'reason': node.get('reason'),
                    'funds': self._flatten_funds(node),
                }
            )
        return out

    # ── 内部 ──

    def _fetch_adjust(self, tgcode: str, tag: int) -> Optional[dict]:
        form = dict(COMMON_FORM)
        form.update({'tgCode': tgcode, 'tag': str(tag), 'useNewFundType': 'true'})
        j = self._post_json(API_ADJUST, form)
        if j and j.get('Succeed'):
            return j.get('Data') or {}
        return None

    @staticmethod
    def _flatten_funds(node: dict) -> List[dict]:
        """把 adjustList[].fundList 摊平为基金级列表。"""
        funds = []
        for grp in (node or {}).get('adjustList') or []:
            for f in grp.get('fundList') or []:
                code = str(f.get('fundCode') or '').strip()
                if not code:
                    continue
                op = f.get('operationInt')
                funds.append(
                    {
                        'fund_code': code,
                        'fund_name': f.get('fundName'),
                        'pre_ratio': _to_float(f.get('preRatio')),
                        'after_ratio': _to_float(f.get('afterRatio')),
                        'op_code': op,
                        'op_name': ADJUST_OP_NAME.get(op) if op is not None else None,
                    }
                )
        return funds

    def healthcheck(self, tgcode: str) -> dict:
        """链路健康检查（精简版 H3–H6：三接口可达 + 数据可解析）。

        bundle 可达性（H1/H2）与前端资源相关，由 scripts/fund_advisor_holdings.py
        的完整 healthcheck 负责；本方法只验证数据面（线上自动化关注点）。
        """
        today = now_shanghai().strftime('%Y-%m-%d')
        form = dict(COMMON_FORM)
        form['tgCodeWithDateStr'] = f'{tgcode}_{today}'
        j = self._post_json(API_QUOTE, form)
        quote_ok = bool(j and j.get('Succeed') and j.get('Data'))
        industry = self.fetch_industry(tgcode)
        holdings = self.fetch_current_holdings(tgcode)
        history = self.fetch_adjust_history(tgcode)
        checks = {
            'quote': quote_ok,
            'industry': bool(industry),
            'holdings': bool(holdings['funds']),
            'history': bool(history),
        }
        failed = [k for k, ok in checks.items() if not ok]
        return {
            'status': 'healthy' if not failed else ('degraded' if len(failed) < len(checks) else 'unhealthy'),
            'checks': checks,
            'failed': failed,
        }
