# -*- coding: utf-8 -*-
"""天天基金「投顾组合」数据适配器（#1167，Port 契约见 #1392）。

实现 :class:`~app.services.adapters.advisor_source.AdvisorPortfolioSource`：
把天天基金四个数据面翻译成 canonical，平台黑话（``SYL_*`` / ``tgCode``）不出本文件。

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
from datetime import datetime
from typing import Any, List, Optional

import requests
from loguru import logger

from app.core.constants import ADVISOR_ADJUST_OP_NAME as ADJUST_OP_NAME
from app.core.time_utils import SHANGHAI_TZ, now_shanghai
from app.services.adapters.advisor_source import EXTRA_KEY, AdvisorPortfolioSource, register_advisor_source

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

# operationInt → 操作名（词表单一真相源见 app.core.constants.ADVISOR_ADJUST_OP_NAME）

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


def _to_int(v: Any) -> Optional[int]:
    """整数型字段（如 ``RUN_DATE`` = 1556）；空串 / 非数字返回 None，**不返回 0**。"""
    try:
        if v in (None, ''):
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _ms_to_date_str(ms: Any) -> Optional[str]:
    """毫秒时间戳 → ``YYYY-MM-DD``（东八区）。"""
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, SHANGHAI_TZ).strftime('%Y-%m-%d')
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _to_date_str(v: Any) -> Optional[str]:
    """平台日期方言 → ``YYYY-MM-DD``（字符串，日期解析仍归落库层）。

    实测三种形态：``'2022-07-26 00:00:00'``（QUOTE 的 ESTABDATE）、``'2026-10-28'``（JZRQ）、
    ``'1658764800000'``（AGGR 的 ESTABDATE，**毫秒时间戳**）。

    最后一种是历史缺陷的来源：原实现把它原样塞进 canonical，而落库层
    ``_parse_date`` 只认 ``YYYY-MM-DD`` ⇒ 解析失败 ⇒ 天天组合的 ``estab_date`` 长期 0%
    填充（本机 3 只天天组合实测全空）。平台方言的翻译属适配器职责，不该让落库层去猜。
    """
    if v in (None, ''):
        return None
    if isinstance(v, (int, float)):
        return _ms_to_date_str(v)
    s = str(v).strip()
    if len(s) >= 12 and s.isdigit():
        return _ms_to_date_str(s)
    return s[:10] if len(s) >= 10 else None


@register_advisor_source
class TiantianAdvisorAdapter(AdvisorPortfolioSource):
    """天天基金投顾组合数据源（公开接口，四个数据面齐全）。"""

    platform = 'TIANTIAN'
    #: 有官方历史调仓接口（getAdjustWarehouse tag=1），无需快照推导
    has_official_rebalances = True

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.logger = logger.bind(adapter='tiantian_advisor')

    # ── 适配器标识（orchestrator._save_sync_log 审计落库需要，缺则 AttributeError）──

    def get_name(self) -> str:
        return 'tiantian_advisor'

    def get_version(self) -> str:
        return 'v1'

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

    # ── 区间收益映射（2026-10-29 两个接口复测，取值一致）──
    # SYL_* → canonical 区间列。字母含义：D=日 Z=周 Y=月 N=年 JN=今年 LN=成立以来。
    # `SYL_3Y`（近 3 月）落 `return_1q`、`SYL_6Y`（近 6 月）落 `return_6m`——不是近似替换，
    # 而是口语口径本就等价（1 季度 = 3 个月），且原本 `return_1q` / `return_6m` 两列天天侧
    # 一直是空（适配器只请求了 5 个键）。
    SYL_TO_INTERVAL = {
        'SYL_D': 'return_1d',
        'SYL_Z': 'return_1w',
        'SYL_Y': 'return_1m',
        'SYL_3Y': 'return_1q',
        'SYL_6Y': 'return_6m',
        'SYL_1N': 'return_1y',
        'SYL_2N': 'return_2y',
        'SYL_3N': 'return_3y',
        'SYL_JN': 'return_ytd',
        'SYL_LN': 'return_since_incep',
    }

    #: `BENCHSYL_*` → 业绩比较基准**同区间**收益列，与 :data:`SYL_TO_INTERVAL` 逐区间配对。
    #: `D` / `Z` 两档**刻意不建列**：业绩表只展示 月/季/半年/今年/1-3 年/成立以来 八行，
    #: 存下来没有读者（数据策略硬约束 1「新列必须当场指定读者」）。
    #: 超额不存：`return_x − benchmark_return_x` 是纯派生值，读取侧现算。
    BENCHSYL_TO_COLUMN = {
        'BENCHSYL_Y': 'benchmark_return_1m',
        'BENCHSYL_3Y': 'benchmark_return_1q',
        'BENCHSYL_6Y': 'benchmark_return_6m',
        'BENCHSYL_JN': 'benchmark_return_ytd',
        'BENCHSYL_1N': 'benchmark_return_1y',
        'BENCHSYL_2N': 'benchmark_return_2y',
        'BENCHSYL_3N': 'benchmark_return_3y',
        'BENCHSYL_LN': 'benchmark_return_since_incep',
    }

    #: `FundIATGInfoAggr` 一次要回的字段：档案 + 净值/净值日（实测 `NAV` / `JZRQ` 就在本接口）
    #: + 全区间 `SYL_*` / `BENCHSYL_*` + 年化。
    #: ⚠️ **回撤 / 夏普 / 运行天数不在此接口**（复测确认缺键，`RUN_DATE` 甚至返回空串），
    #: 它们只在 `getTGQuoteByFavor` 里 —— 这就是必须同时调两个接口的原因。
    AGGR_FIELDS = (
        (
            'TGNAME',
            'RISKLEVEL',
            'STGCONCEPT',
            'ESTABDATE',
            'STATUS',
            'NAV',
            'JZRQ',
            'ANNSYL_LN',
        )
        + tuple(SYL_TO_INTERVAL)
        + tuple(BENCHSYL_TO_COLUMN)
    )

    def fetch_overview(self, tgcode: str) -> dict:
        """投顾概览（canonical）：**两个接口合并**，任一成功即返回其可得部分。

        - ``FundIATGInfoAggr``（GET）：档案、`NAV` / `JZRQ`、全区间 `SYL_*` / `BENCHSYL_*`、年化；
        - ``getTGQuoteByFavor``（POST）：最大回撤 `MAXRETRA_LN`、夏普 `SHARPE_LN`、
          运行天数 `RUN_DATE`、成立日（字符串形态，比 AGGR 的毫秒时间戳好解析）。

        **为什么必须调两个**（2026-10-29 复测）：回撤 / 夏普在 AGGR 里根本不存在、
        AGGR 的 `RUN_DATE` 是空串；而 `BENCHSYL_*` 只在 AGGR 里有。
        历史上这里只调了 AGGR，于是「回撤 / 夏普 / 运行天数」被记成「API 不提供」，
        天天组合的三列长期 0%——**那是适配器没请求，不是数据源缺失**。

        合并口径：**先 AGGR 后 QUOTE，逐键「非 None 覆盖」**。两接口重叠的键
        （`SYL_*` / `ANNSYL_LN` / `TGNAME`）实测同值，取谁都不改变结果；
        成立日两边都有，QUOTE 形态更干净，故自然由后者胜出。

        拿不到的字段一律**不出现在返回值里**（落库层只覆盖非 None，接口缺字段不会冲掉库内值）。
        """
        parts = (self._overview_from_aggr(tgcode), self._overview_from_quote(tgcode))
        merged: dict = {}
        extra: dict = {}
        for part in parts:
            if not part:
                continue
            part_extra = part.pop(EXTRA_KEY, None)
            if part_extra:
                extra.update(part_extra)
            for key, value in part.items():
                if value is not None:
                    merged[key] = value
        if not merged:
            return {}
        if extra:
            merged[EXTRA_KEY] = extra
        return merged

    def _overview_from_aggr(self, tgcode: str) -> dict:
        """`FundIATGInfoAggr` 面：档案 + 净值 + 全区间收益 + 基准收益 + 年化。"""
        params = {'FIELDS': ','.join(self.AGGR_FIELDS), 'TGCODE': tgcode}
        resp = self._request('GET', API_AGGR, params=params)
        if resp is None:
            return {}
        try:
            j = json.loads(resp.text)
            data = j.get('data') if j.get('success') else None
            if not (isinstance(data, list) and data):
                return {}
            d = data[0]
            mapped_raw = (
                {
                    'TGNAME',
                    'RISKLEVEL',
                    'STGCONCEPT',
                    'ESTABDATE',
                    'NAV',
                    'JZRQ',
                    'ANNSYL_LN',
                }
                | set(self.SYL_TO_INTERVAL)
                | set(self.BENCHSYL_TO_COLUMN)
            )
            return {
                'name': d.get('TGNAME'),
                'risk_level': str(d.get('RISKLEVEL')) if d.get('RISKLEVEL') is not None else None,
                'strategy_desc': d.get('STGCONCEPT'),
                'estab_date': _to_date_str(d.get('ESTABDATE')),
                'nav': _to_float(d.get('NAV')),
                'nav_date': _to_date_str(d.get('JZRQ')),
                'annual_return': _to_float(d.get('ANNSYL_LN')),
                # ⚠️ `cum_return` 与 `return_since_incep` 是**同一个 SYL_LN 的两个读者**，
                # 不是两个独立口径（见 models.AdvisorPortfolio.cum_return 的注释）。
                'cum_return': _to_float(d.get('SYL_LN')),
                **{col: _to_float(d.get(syl)) for syl, col in self.SYL_TO_INTERVAL.items()},
                **{col: _to_float(d.get(bench)) for bench, col in self.BENCHSYL_TO_COLUMN.items()},
                EXTRA_KEY: {k: v for k, v in d.items() if k not in mapped_raw},
            }
        except (ValueError, TypeError) as e:
            self.logger.warning(f'概览(AGGR)解析失败 {tgcode}: {e}')
        return {}

    def _overview_from_quote(self, tgcode: str) -> dict:
        """`getTGQuoteByFavor` 面：回撤 / 夏普 / 运行天数 / 成立日 + 区间收益兜底。

        响应 ``Data`` 实测是**单元素列表**（key 28 个），不是 dict——按 dict 写会
        ``AttributeError``，故此处两种形态都容忍。``RUN_DATE`` 是 int，其余多为字符串数字。
        """
        today = now_shanghai().strftime('%Y-%m-%d')
        form = dict(COMMON_FORM)
        form['tgCodeWithDateStr'] = f'{tgcode}_{today}'
        j = self._post_json(API_QUOTE, form)
        if not j or not j.get('Succeed'):
            return {}
        data = j.get('Data')
        if isinstance(data, list):
            d = data[0] if data else None
        elif isinstance(data, dict):
            d = data
        else:
            d = None
        if not d:
            return {}
        mapped_raw = {
            'TGCODE',
            'TGNAME',
            'ESTABDATE',
            'JZRQ',
            'SYRQ',
            'RUN_DATE',
            'MAXRETRA_LN',
            'SHARPE_LN',
            'ANNSYL_LN',
        } | set(self.SYL_TO_INTERVAL)
        return {
            'name': d.get('TGNAME'),
            'estab_date': _to_date_str(d.get('ESTABDATE')),
            'running_days': _to_int(d.get('RUN_DATE')),
            'max_drawdown': _to_float(d.get('MAXRETRA_LN')),
            'sharpe_ratio': _to_float(d.get('SHARPE_LN')),
            'annual_return': _to_float(d.get('ANNSYL_LN')),
            **{col: _to_float(d.get(syl)) for syl, col in self.SYL_TO_INTERVAL.items()},
            EXTRA_KEY: {k: v for k, v in d.items() if k not in mapped_raw},
        }

    def fetch_industries(self, tgcode: str) -> List[dict]:
        """持仓行业配置 ``[{industry_name, ratio}]``。"""
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

    def fetch_holdings(self, tgcode: str) -> dict:
        """当前基金级持仓（最新一次调仓后的占比快照）。

        返回 ``{'as_of_date': date_str|None, 'funds': [{fund_code, fund_name,
        pre_ratio, after_ratio, op_code, op_name}]}``。
        """
        adj = self._fetch_adjust(tgcode, tag=0)
        latest = (adj or {}).get('latestAdjust') or {}
        return {
            'as_of_date': latest.get('dateStr'),
            'funds': self._flatten_funds(latest),
        }

    def fetch_rebalances(self, tgcode: str) -> List[dict]:
        """官方历史调仓列表 ``[{adjust_date, reason, funds: [...]}]``。"""
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
        industry = self.fetch_industries(tgcode)
        holdings = self.fetch_holdings(tgcode)
        history = self.fetch_rebalances(tgcode)
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
