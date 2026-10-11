# -*- coding: utf-8 -*-
"""好买（howbuy）「投顾组合」数据适配器（#1910，Port 契约见 #1392）。

实现 :class:`~app.services.adapters.advisor_source.AdvisorPortfolioSource`：
把好买四个数据面翻译成 canonical，平台黑话（``zhdm`` / ``syxx`` / ``zxgd`` / ``cpzbList``）
不出本文件。

数据源为公开接口（零鉴权，免登录/签名/浏览器），实测见 #1910 评论（2026-10-06）：

- GET ``v717z/clcpday.json``       概览：基本信息 + 最新持仓 + 资产分类 + 区间收益
- GET ``v717z/clcphbzst.json``     风险指标（年化/波动率/夏普/最大回撤）
- GET ``v731z/clcplsgd.json``      历次调仓（含前后占比）
- GET ``v717z/clcplshb.json``      净值序列（实测可用，但 **Ports 接口没有净值位**，
  天天/且慢/好买三个适配器均未接入该面；故本文件不保留该端点的常量，
  免得留一行没人调的死代码、让后来者以为「净值接了其实没接」）

**端点版本号不统一是实测结论，不是笔误**：概览/指标/净值在 ``v717z``，调仓在 ``v731z``；
把指标写成 ``v731z/clcphbzst.json`` 会 404（#1910 正文原先就是这么写的，已更正）。

健壮性约定（与天天适配器同型，线上需长期自动化维护）：

- 模块级节流：相邻任意请求间隔 ≥ ``REQUEST_INTERVAL`` 秒；
- 指数退避重试：单接口最多 ``MAX_RETRIES`` 次（2s/4s/8s），仍失败则该数据面返回空，
  由上层记 skipped，不炸整个 job；
- ``requests.Session`` 复用连接。

与天天适配器的两处差异：

1. 好买是纯 GET + query 参数（天天是 POST 表单），故这里只有 ``_get_json``；
2. **好买不返回调仓操作码**（天天给 ``operationInt``），故 :meth:`_flatten_funds` 按
   前后占比推导 op_code/op_name——语义对齐 :data:`ADVISOR_ADJUST_OP_NAME`。
"""

import json
import threading
import time
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from app.core.constants import ADVISOR_ADJUST_OP_NAME as ADJUST_OP_NAME
from app.services.adapters.advisor_source import (
    EXTRA_KEY,
    AdvisorPortfolioSource,
    register_advisor_source,
)

BASE_URL = 'https://data.howbuy.com/cgi/fund/'
API_OVERVIEW = BASE_URL + 'v717z/clcpday.json'
API_INDICATOR = BASE_URL + 'v717z/clcphbzst.json'
API_REBALANCE = BASE_URL + 'v731z/clcplsgd.json'

# 实测：不带 UA 也能通；带上 App 端 UA 更贴近真实流量，顺带避开未声明的风控
HEADERS = {'User-Agent': 'okhttp/3.12.0'}

REQUEST_INTERVAL = 2.0  # 相邻请求最小间隔（秒）
MAX_RETRIES = 3
RETRY_BACKOFF = (2, 4, 8)  # 指数退避（秒）
TIMEOUT = 20

#: 调仓接口单页条数：一次取全（实测 total=33 → pages=11@size=3，取 size=200 一页够用）。
#: 好买不提供「全量」开关，分页拉全反而要多轮请求、更容易踩节流。
REBALANCE_PAGE_SIZE = 200

# 模块级节流：同一进程内所有请求共享（适配器可能被多 job 实例化）
_throttle_lock = threading.Lock()
_last_request_ts = 0.0

#: 区间收益：``jdsybx.dataList[].rangeName`` → canonical 列。
#: 「近3年 / 近5年」不在本表：``CANONICAL_OVERVIEW_COLUMNS`` 没有对应列，
#: 按 Port 约定走 ``extra``，不硬塞进不存在的列。
RANGE_TO_INTERVAL = {
    '近1周': 'return_1w',
    '近1月': 'return_1m',
    '近3月': 'return_1q',
    '近6月': 'return_6m',
    '近1年': 'return_1y',
    '今年以来': 'return_ytd',
    '创建以来': 'return_since_incep',
}

#: 风险指标：``qjzb.dataList[].mc``（指标名）→ canonical 列。``sz1`` = 组合值。
#: 注意 ``sz2`` 是**业绩基准**值，不是组合，映射时别取错。
METRIC_TO_FIELD = {
    '年化收益率': 'annual_return',
    '年化波动率': 'volatility',
    '夏普比率': 'sharpe_ratio',
    '最大回撤': 'max_drawdown',
}

#: 风险指标取数的区间。**必须用 ``CL``（创建以来），不能用 ``1N``（近1年）**——
#: 实测 ``range=1N`` 的「年化收益率」返回 ``-0.41``，与区间收益的「近1年」完全相同，
#: 说明该档位下它是「近1年收益」而非年化口径；换成 ``CL`` 返回 ``7.83``，
#: **与概览 ``syxx.nhhbcl``（年化回报）逐位一致**，才真正对齐 canonical 的 ``annual_return``。
#: 最大回撤同理：``1N`` 给 -16.37（近1年回撤），``CL`` 给 -46.91（成立以来）。
METRIC_RANGE = 'CL'


def _to_iso_date(v: Any) -> Optional[str]:
    """把 howbuy 的紧凑日期 ``YYYYMMDD`` 规整成 ISO 字符串 ``YYYY-MM-DD``。

    为什么适配器要管这个（而不是留给落库层）：job 的 ``_parse_date`` 用
    ``strptime(s, '%Y-%m-%d')``，**只认 ISO 格式**；好买概览的 ``cjrq`` / ``jzrq``
    与持仓的 ``gdqsrq`` 都是 ``20170905`` 这种紧凑写法，直接下发会解析失败、
    静默落成 NULL（端到端用例抓到的第一个真问题）。

    注意这**不是**在适配器里做类型转换——返回值仍是字符串，符合
    ``advisor_source.OVERVIEW_DATE_KEYS`` 的约定（「字符串 → date 由落库层统一处理」）。
    适配器只负责「平台格式 → ISO 格式」，落库层负责「ISO 字符串 → date」。
    解析不了的返回 None，不猜。
    """
    if v in (None, ''):
        return None
    s = str(v).strip()
    if len(s) == 8 and s.isdigit():
        return f'{s[0:4]}-{s[4:6]}-{s[6:8]}'
    return s or None


def _to_float(v: Any) -> Optional[float]:
    """平台用空字符串表示「无数据」（持仓的 ``sccczb`` 常见），必须转成 None 而不是 0。"""
    try:
        if v in (None, ''):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


@register_advisor_source
class HowbuyAdvisorAdapter(AdvisorPortfolioSource):
    """好买投顾组合数据源（公开接口，四个数据面齐全）。"""

    platform = 'HOWBUY'
    #: 有官方历史调仓接口（clcplsgd），无需快照推导
    has_official_rebalances = True

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.logger = logger.bind(adapter='howbuy_advisor')

    # ── 适配器标识（orchestrator._save_sync_log 审计落库需要，缺则 AttributeError）──

    def get_name(self) -> str:
        return 'howbuy_advisor'

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

    def _get_json(self, url: str, params: dict) -> Optional[dict]:
        """GET 并解出 ``body``；信封 ``code != '0000'`` 视为失败（返回 None）。"""
        resp = self._request('GET', url, params=params)
        if resp is None:
            return None
        try:
            payload = json.loads(resp.text)
        except ValueError:
            self.logger.warning(f'响应非 JSON: {url}')
            return None
        if str(payload.get('code')) != '0000':
            self.logger.warning(f'接口返回失败码 {payload.get("code")} {payload.get("desc")} @ {url}')
            return None
        body = payload.get('body')
        return body if isinstance(body, dict) else None

    # ── 各数据面（互相独立，单面失败不影响其余） ──

    def fetch_overview(self, code: str) -> Dict[str, Any]:
        """组合概览 + 风险指标（canonical）。

        概览**要打两个端点**：``clcpday`` 给基本信息与区间收益，``clcphbzst`` 给风险指标。
        实测 ``clcpday`` 的 ``frontInfo.cpzbList`` 是空的（只有 2 条 ``zbdm=hb`` 且
        ``zbnrValue`` 全为 null），所以指标**必须**走 ``clcphbzst``，不能从概览取。

        拿不到的键**不返回**（Port 约定：宁可为空也不填 0）；canonical 之外的原始字段
        进 ``extra``，避免日后为拿单个字段再抓一遍。
        """
        day = self._get_json(API_OVERVIEW, {'zhdm': code})
        if not day:
            return {}
        out: Dict[str, Any] = {}

        # 基本信息与收益：syxx 节点字段最密
        sy = day.get('syxx') or {}
        out.update(
            {
                'estab_date': _to_iso_date(sy.get('cjrq')),
                'nav': _to_float(sy.get('zhjz')),
                'nav_date': _to_iso_date(sy.get('jzrq')),
                'cum_return': _to_float(sy.get('hbcl')),
                'annual_return': _to_float(sy.get('nhhbcl')),
                'return_1d': _to_float(sy.get('hbdr')),
                'strategy_desc': ((day.get('cpjs') or {}).get('recommendReason') or None),
                'org_name': ((day.get('zlr') or {}).get('name') or None),
                # 组合详情页（与网页版 howbuy.com/combination/<code>/ 对应）
                'source_url': f'https://www.howbuy.com/combination/{code}/',
            }
        )

        # 组合名走指标端点的 title1：概览的 pzxx.jbxx 没有名称字段（实测）
        ind = self._get_json(API_INDICATOR, {'zhdm': code, 'range': METRIC_RANGE})
        if ind:
            out['name'] = ind.get('title1') or None
            for item in (ind.get('qjzb') or {}).get('dataList') or []:
                col = METRIC_TO_FIELD.get(str(item.get('mc') or '').strip())
                if col:
                    out[col] = _to_float(item.get('sz1'))

        # 区间收益（含超额）：rangeName 对齐，zhhb=组合 / cehb=相对基准超额
        extra_extra: Dict[str, Any] = {}
        for row in ((day.get('jdsybx') or {}).get('dataList')) or []:
            rng = str(row.get('rangeName') or '').strip()
            col = RANGE_TO_INTERVAL.get(rng)
            if col:
                out[col] = _to_float(row.get('zhhb'))
            else:
                # 近3年 / 近5年 等无对应列，原样留档而不是丢弃
                extra_extra[rng] = {
                    'zhhb': _to_float(row.get('zhhb')),
                    'jzhb': _to_float(row.get('jzhb')),
                    'cehb': _to_float(row.get('cehb')),
                }
            if rng == '近1年':
                # canonical 的 excess_return 取「近1年」超额（与天天适配器口径一致）
                out['excess_return'] = _to_float(row.get('cehb'))

        out[EXTRA_KEY] = extra_extra
        return out

    def fetch_holdings(self, code: str) -> Dict[str, Any]:
        """当前基金级持仓快照（``zxgd.fundList``）。

        好买持仓节点**不带前后占比**（只有 ``cczb`` 当前占比），故 ``pre_ratio`` 与
        ``op_code`` / ``op_name`` 一律 None——当前快照语义下它们本就无定义，
        调仓前后对比在 :meth:`fetch_rebalances` 里给。
        """
        day = self._get_json(API_OVERVIEW, {'zhdm': code})
        if not day:
            return {'as_of_date': None, 'funds': []}
        node = day.get('zxgd') or {}
        funds: List[dict] = []
        for f in node.get('fundList') or []:
            fund_code = str(f.get('jjdm') or '').strip()
            if not fund_code:
                continue
            funds.append(
                {
                    'fund_code': fund_code,
                    'fund_name': f.get('jjjc'),
                    'pre_ratio': None,
                    'after_ratio': _to_float(f.get('cczb')),
                    'op_code': None,
                    'op_name': None,
                }
            )
        return {'as_of_date': _to_iso_date(node.get('gdqsrq')), 'funds': funds}

    def fetch_industries(self, code: str) -> List[Dict[str, Any]]:
        """资产类别配置 ``[{industry_name, ratio}]``。

        **口径说明**：好买给的是 ``zcfl1List``（股票型 / 混合型 / 货币型 / 指数型……），
        即**按基金类型分的资产类别**，不是行业（天天那边是 ``getHoldWarehouseIndustryRatio``）。
        两者都回答「钱分布在哪」，Port 的 ``industry_name`` 列足够承载，故不新增字段；
        消费侧若需要区分口径，看 ``source`` 即可。
        """
        day = self._get_json(API_OVERVIEW, {'zhdm': code})
        if not day:
            return []
        out = []
        for row in day.get('zcfl1List') or []:
            name = row.get('mc')
            if not name:
                continue
            out.append({'industry_name': name, 'ratio': _to_float(row.get('zb'))})
        return out

    def fetch_rebalances(self, code: str) -> List[Dict[str, Any]]:
        """官方历史调仓 ``[{adjust_date, reason, funds: [...]}]``（``clcplsgd``）。"""
        body = self._get_json(
            API_REBALANCE,
            {'zhdm': code, 'current': 1, 'size': REBALANCE_PAGE_SIZE},
        )
        if not body:
            return []
        out = []
        for node in body.get('dataList') or []:
            out.append(
                {
                    'adjust_date': _to_iso_date(node.get('gdqsrq')),
                    'reason': (node.get('ms1') or '').strip() or None,
                    'funds': self._flatten_funds(node.get('fundList') or []),
                }
            )
        return out

    # ── 内部 ──

    @staticmethod
    def _flatten_funds(fund_list: List[dict]) -> List[dict]:
        """把调仓明细的 ``fundList`` 摊平为基金级列表，并**由前后占比推导操作码**。

        好买不返回 ``operationInt``（天天返回），只能比 ``sccczb``（上次占比）与
        ``cczb``（本次占比）。推导规则对齐 :data:`ADVISOR_ADJUST_OP_NAME`：

        ==================  =========
        情形                 op_code
        ==================  =========
        上次无、本次有       4 新增
        上次有、本次无       3 减仓（词表无「清仓」，清仓是减仓的极端）
        本次 > 上次          2 加仓
        本次 < 上次          3 减仓
        本次 = 上次          5 持平
        ==================  =========

        ``op_code`` 为 None（两侧都缺数据）时 ``op_name`` 也为 None——**不猜**。
        """
        funds = []
        for f in fund_list or []:
            fund_code = str(f.get('jjdm') or '').strip()
            if not fund_code:
                continue
            pre = _to_float(f.get('sccczb'))
            after = _to_float(f.get('cczb'))
            funds.append(
                {
                    'fund_code': fund_code,
                    'fund_name': f.get('jjjc'),
                    'pre_ratio': pre,
                    'after_ratio': after,
                    'op_code': HowbuyAdvisorAdapter._derive_op_code(pre, after),
                    'op_name': ADJUST_OP_NAME.get(HowbuyAdvisorAdapter._derive_op_code(pre, after)),
                }
            )
        return funds

    @staticmethod
    def _derive_op_code(pre: Optional[float], after: Optional[float]) -> Optional[int]:
        """由前后占比推导 ``operationInt``；判不出返回 None。"""
        if after is None:
            # 本次占比缺失时，「上次有」只能说明它不在本次名单里
            return 3 if (pre or 0) > 0 else None
        if pre is None or pre == 0:
            return 4  # 新增
        if after == 0:
            return 3  # 清仓（词表无此项，归减仓）
        if after > pre:
            return 2  # 加仓
        if after < pre:
            return 3  # 减仓
        return 5  # 持平
