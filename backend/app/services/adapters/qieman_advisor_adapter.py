# -*- coding: utf-8 -*-
"""且慢投顾组合适配器（#1392）：复用且慢 MCP（stargate.yingmi.com）自动抓组合持仓与概览。

实现 :class:`~app.services.adapters.advisor_source.AdvisorPortfolioSource`：
把 MCP 归一化结果翻译成 canonical（差异只在少量别名），平台细节（工具名 / 中文键 / 百分号串）
全部留在 ``thermometer/fetchers.QiemanFetcher`` 与本文件内。

前置：QIEMAN_API_KEY 已配置（与温度计同 key）。

- 组合持仓：BatchGetStrategiesComposition，真实返回结构（实测 2026-09）：
    {"<code>": {"<基金类别>": {"持有成分":[{基金代码,基金名称,持仓占比,
    最新净值,调仓时间,...}], "分类占比":...}, ...}}
  解析由 QiemanFetcher.fetch_strategy_composition 完成（已按该结构实现，遍历类别打平）。
- 组合概览：GetStrategyDetails（#1468），提供名称/管理人/风险等级/成立日/区间收益/
  最大回撤/波动率/夏普等，解析由 QiemanFetcher.fetch_strategy_details 完成。
  组合代码命名空间不统一（ZHxxxx / LONG_WIN / J7 / WALLET / SIxxxx），
  故平台归属一律由调用方按 DB 的 platform 判定，不得按代码前缀猜。
- **行业配置**：MCP 无该工具，恒返回空（契约要求空集合而非报错）。
- **历史调仓：有官方数据面**，走且慢 Web 的 GraphQL（见下节），不再只能靠快照推导。

## 官方历史调仓（`/alfa/v1/graphql`，2026-11-03 实测确认）

此前本适配器写着「且慢无历史调仓接口」，那是**探错端点族**得出的错结论：当时只试了
``qieman.com/pmapi/**``（五个候选路径都落回 SPA HTML），从未试 ``/alfa/v1/graphql``。
真相是：

- 端点 ``POST https://qieman.com/alfa/v1/graphql``，``operationName: "Adjustment"``；
- **匿名可取**：不需要 cookie、登录、MCP token；
- 唯一门槛是请求头 ``x-sign``，**且无密钥**——算法就在公开 bundle
  ``zeus-dist-po/js/app.<hash>.js`` 里（webpack 模块 54165 = ``js-sha256``）：:

      x-sign = str(now_ms) + SHA256(str(floor(1.01 * now_ms))).upper()[:32]

  （``.substring(0, 32)`` 是把 64 位十六进制**截前 32 位**，不是 MD5。）
  已用浏览器抓包的两组 ``(时间戳, 签名)`` 反算验证，两组均 MATCH。

为什么仍然保留快照推导：官方接口**不是所有代码都有调仓**。实测 21 个「库内有推导行」
的组合里 18 个有官方数据、2 个是计划型（``LONG_WIN`` / ``LONG_WIN_S`` 长赢计划，
不属于 ``alfa/portfolio``，返回空）、1 个是测试夹具。计划型组合的调仓只能继续推导。

本适配器替代原 import_qieman_holdings 手动 JSON 导入。
"""

import hashlib
import math
import threading
import time
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from app.services.adapters.advisor_source import (
    CANONICAL_OVERVIEW_COLUMNS,
    EXTRA_KEY,
    AdvisorPortfolioSource,
    register_advisor_source,
)
from app.services.adapters.qieman_fetcher import QiemanFetcher

#: 且慢 Web 的 GraphQL 入口（与 MCP ``stargate.yingmi.com`` 是两条独立链路）。
_ADJUST_URL = 'https://qieman.com/alfa/v1/graphql'

#: 服务端单页上限：实测 ``size=50`` 是能拿到的最大页（``totalCount=118`` 的 ``ZH012636``
#: 也只回 50 条），写 100 不会多给，故按 50 翻页。
_ADJUST_PAGE_SIZE = 50

#: 翻页防御上限。实测历史最长的组合 138 条 = 3 页；给到 20 页只为防死循环，
#: 不是「预期会翻 20 页」。
_ADJUST_MAX_PAGES = 20

#: 请求间隔（秒）：111 个组合 × 1~3 页，串行发；对齐天天基金适配器的节流口径。
_ADJUST_REQUEST_INTERVAL = 0.3

#: 失败重试次数与退避（秒）。
_ADJUST_MAX_RETRIES = 3
_ADJUST_RETRY_BACKOFF = (1, 3, 6)

#: 官方 ``movementName`` → 库内 ``op_code``（词表见 ``constants.ADVISOR_ADJUST_OP_NAME``）。
#: ``op_name`` 原样保留官方用词（调入/调出/调增/调减）——「调入」与「调增」对用户是两件事，
#: 压成「加仓」会丢掉「这是新建仓」这一信息。
_MOVEMENT_TO_OP_CODE = {'调入': 4, '调增': 2, '调出': 3, '调减': 3}

#: 「没有发生动作」的官方取值：整组回传是为了给调前/调后做全量快照，
#: 落库只需要真正动过的基金（与快照推导口径一致，否则列表被持平行淹没）。
_MOVEMENT_NOOP = '持平'

#: ``Adjustment`` 查询。**必须整段照抄浏览器发出的 query**：GraphQL 会校验
#: 「变量声明了却未使用」，删掉某个块却留着对应变量声明会直接 400
#: （实测 ``$needPreference`` 未使用 → ``GRAPHQL_VALIDATION_FAILED``）。
_ADJUST_QUERY = """query Adjustment($poCode: String!, $page: Pagination = null, $needPreference: Boolean! = false, $needCategoryDict: Boolean! = false, $isModelPo: Boolean = false, $categoryType: FundCategoryType) {
  portfolio(poCode: $poCode, isModelPo: $isModelPo) {
    isSupportSmartAip
    adjustments(page: $page, categoryType: $categoryType) {
      adjustments {
        date
        comment
        adjustmentId
        article {
          text
          link
          __typename
        }
        groups {
          categoryCode
          categoryCodeLevel1
          movementName
          parts {
            fund {
              fundCode
              fundName
              __typename
            }
            movementName
            beforePercent
            afterPercent
            categoryCode
            categoryCodeLevel1
            __typename
          }
          beforePercent
          afterPercent
          __typename
        }
        __typename
      }
      totalCount
      pageInfo {
        hasMore
        cursor
        __typename
      }
      __typename
    }
    __typename
  }
  preferences @include(if: $needPreference) {
    portfolio(poCode: $poCode, isModelPo: $isModelPo) {
      adjustmentDetailListSeries
      adjustmentDetailDimensions
      __typename
    }
    __typename
  }
  dicts @include(if: $needCategoryDict) {
    portfolioCompositionCategoryNames
    portfolioRiskLevelNames
    fundCategoryLevel1Names
    __typename
  }
}"""


def x_sign(now_ms: Optional[int] = None) -> str:
    """且慢 ``x-sign``：``str(now_ms) + SHA256(str(floor(1.01*now_ms))).upper()[:32]``。

    无密钥、与请求体无关（同一次页面加载里 body 长度 1716 与 359 的两个请求签名相同），
    因此可以按需现算，不必从浏览器搬运。
    """
    ts = int(time.time() * 1000) if now_ms is None else int(now_ms)
    preimage = str(int(math.floor(1.01 * ts)))
    digest = hashlib.sha256(preimage.encode('utf-8')).hexdigest().upper()[:32]
    return f'{ts}{digest}'


class _Throttle:
    """跨实例的请求节流（同步 job 单线程，但要防并发脚本同时打同一端点）。"""

    def __init__(self, interval: float) -> None:
        self._interval = interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            delay = self._interval - (time.time() - self._last)
            if delay > 0:
                time.sleep(delay)
            self._last = time.time()


def _pct(v: Any) -> Optional[float]:
    """官方比例（小数）→ 库内百分点；``None`` / 非数值原样返回 ``None``。

    官方 ``afterPercent: 0.1031`` 表示 10.31%，库内同名列存的是 ``10.31``。
    保留 4 位小数只为消掉 ``0.1031 * 100 = 10.310000000000001`` 这类浮点尾巴。
    """
    if v is None:
        return None
    try:
        return round(float(v) * 100, 4)
    except (TypeError, ValueError):
        return None


@register_advisor_source
class QiemanAdvisorAdapter(AdvisorPortfolioSource):
    """且慢组合数据源（概览 + 持仓 MCP 抓取，调仓走 Web GraphQL）。"""

    platform = 'QIEMAN'
    #: 官方历史调仓数据面存在（``/alfa/v1/graphql`` 的 ``Adjustment``）
    has_official_rebalances = True
    #: **降级**能力位：计划型组合（``LONG_WIN`` 等）没有官方调仓，仍由快照序列推导
    derive_rebalances_from_snapshots = True
    #: 官方调仓行的 source 与快照推导区分开：否则换源后同一时段会有两套数据，
    #: 前端也无法只靠 ``source`` 判断「这行是不是推导的」。``qieman`` 保持推导语义不变。
    official_rebalance_source = 'qieman_official'

    #: QiemanFetcher 归一化键 → canonical 键（仅别名不同，其余同名直接透传）
    _OVERVIEW_ALIASES = {
        'summary': 'strategy_summary',
        'desc': 'strategy_desc',
        'url': 'source_url',
    }

    _throttle = _Throttle(_ADJUST_REQUEST_INTERVAL)

    def __init__(self) -> None:
        self._fetcher = QiemanFetcher()
        self.session = requests.Session()
        self.logger = logger.bind(adapter='qieman_advisor')

    def get_name(self) -> str:
        """数据源标识（与 orchestrator 审计落库口径一致）。"""
        return 'qieman_advisor'

    def get_version(self) -> str:
        return 'v1'

    def fetch_overview(self, strategy_code: str) -> dict:
        """组合概览 / 风险收益指标（canonical 字典）。

        键见 ``CANONICAL_OVERVIEW_COLUMNS``；canonical 未覆盖的原始字段
        （管理人简介 / 头像 / 实名认证等）进 ``extra``，不做丢弃。
        无 key / 无效 code → ``{}``（落库层不会因此清空已有数据）。
        """
        code = str(strategy_code).strip()
        return self.fetch_overviews([code]).get(code) or {}

    def fetch_overviews(self, strategy_codes: list) -> dict:
        """批量概览（且慢优化）：一次 ``GetStrategyDetails`` 拿多只，按 code 切分。

        底层 ``fetch_strategy_details`` 已按 ``QIEMAN_STRATEGY_BATCH_SIZE``（50）分批，
        故 111 只组合 = 3 次工具调用（原实现逐只调 = 111 次）。
        只返回拿到的 code（缺失即缺席），语义与 ``fetch_overview`` 的 ``{}`` 一致。
        """
        codes = [str(c).strip() for c in (strategy_codes or []) if str(c).strip()]
        if not codes:
            return {}
        rows = self._fetcher.fetch_strategy_details(codes)
        by_code = {str(r.get('code')): r for r in rows if isinstance(r, dict) and str(r.get('code') or '').strip()}
        return {c: self._to_canonical_overview(by_code[c]) for c in codes if c in by_code}

    def _to_canonical_overview(self, raw: dict) -> dict:
        """单条 fetcher 概览 → canonical（含 extra / desc 回退）。"""
        ov = {self._OVERVIEW_ALIASES.get(k, k): v for k, v in raw.items() if k != 'code'}
        # 策略描述缺失时回退策略简介：详情抽屉需要一段可读描述（既有行为，勿丢）
        if not ov.get('strategy_desc') and ov.get('strategy_summary'):
            ov['strategy_desc'] = ov['strategy_summary']
        mapped = set(self._OVERVIEW_ALIASES) | set(CANONICAL_OVERVIEW_COLUMNS)
        ov[EXTRA_KEY] = {k: v for k, v in raw.items() if k not in mapped and k != 'code' and v is not None}
        return ov

    def fetch_holdings(self, strategy_code: str) -> dict:
        """组合当前基金级持仓快照（canonical）。

        返回 ``{'as_of_date': 'YYYY-MM-DD HH:MM:SS'|None, 'funds': [...]}``；
        且慢同一组合多个类别可能给出不同调仓时间，取**最晚**者作为快照日
        （日期解析交给落库层）。且慢无调仓前占比，``pre_ratio`` / 操作类型留空。
        无 key / 无效 code → ``{'as_of_date': None, 'funds': []}``。
        """
        code = str(strategy_code).strip()
        return self.fetch_holdings_batch([code]).get(code) or {'as_of_date': None, 'funds': []}

    def fetch_holdings_batch(self, strategy_codes: list) -> dict:
        """批量持仓（且慢优化）：一次 ``BatchGetStrategiesComposition`` 传多只。

        降级逐只的判据在 fetcher 内（批量响应缺某 code 的键 ⇒ 该 code 单只重取），
        因此这里拿到的每只都是「有值或确认为空」，不会把批量失败写成空快照。
        """
        codes = [str(c).strip() for c in (strategy_codes or []) if str(c).strip()]
        if not codes:
            return {}
        rows_by_code = self._fetcher.fetch_strategy_composition_batch(codes)
        return {c: self._to_canonical_holdings(rows_by_code.get(c) or []) for c in codes}

    @staticmethod
    def _to_canonical_holdings(rows: list) -> dict:
        """单只归一化持仓列表 → canonical 快照字典。"""
        funds = []
        adj_times = []
        for h in rows or []:
            code = str(h.get('code') or '').strip()
            if not code:
                continue
            funds.append(
                {
                    'fund_code': code,
                    'fund_name': h.get('name'),
                    'pre_ratio': None,
                    'after_ratio': h.get('ratio'),
                    'op_code': None,
                    'op_name': None,
                }
            )
            if h.get('adj_time'):
                adj_times.append(str(h['adj_time']))
        return {'as_of_date': max(adj_times) if adj_times else None, 'funds': funds}

    def fetch_industries(self, strategy_code: str) -> list:
        """且慢 MCP 无行业配置工具 → 恒为空（契约要求返回空集合而非报错）。"""
        return []

    def fetch_rebalances(self, strategy_code: str) -> list:
        """官方历史调仓 ``[{adjust_date, reason, funds: [...]}]``（全量，倒序）。

        走 Web GraphQL 的 ``Adjustment``（契约口径与天天基金适配器逐字一致），
        ``funds`` 只含**真正动过**的基金（``movementName != 持平``）——
        官方把整个组合的调前/调后都回传，持平行占 50%~70%，落库会把列表淹掉。

        取不到时返回 ``[]`` **并打 WARNING**：契约要求数据面不抛错，而 ``[]`` 会让落库层
        回退到快照推导（计划型组合本来就走这条），所以「接口挂了」不会让页面变空、
        也不会制造假红——但必须在日志里留下「这次是回退，不是真没有调仓」。
        """
        code = str(strategy_code or '').strip()
        if not code:
            return []
        nodes, err = self._fetch_adjustments(code)
        if err:
            self.logger.warning(f'且慢官方调仓 {code} 取数失败（本次回退快照推导）：{err}')
            return []
        return nodes

    # ── 官方调仓：HTTP + 解析 ──

    def _post_graphql(self, code: str, cursor: Optional[str]) -> dict:
        """发一次 ``Adjustment`` 请求，返回响应 JSON（校验失败的 ``errors`` 由调用方判）。

        ``x-sign`` 每次现算（算法见 ``x_sign``）；带 ``x-broker: 0008`` 与页面同源头，
        不带 cookie —— 实测三者里只有 ``x-sign`` 是必需项。
        """
        page: Dict[str, Any] = {'size': _ADJUST_PAGE_SIZE}
        if cursor:
            page['cursor'] = cursor
        payload = {
            'operationName': 'Adjustment',
            'variables': {
                'poCode': code,
                'page': page,
                'needPreference': False,
                'needCategoryDict': False,
                'isModelPo': False,
                'categoryType': 'FundCategory',
            },
            'query': _ADJUST_QUERY,
        }
        headers = {
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'Origin': 'https://qieman.com',
            'Referer': f'https://qieman.com/alfa/portfolio/{code}/adjustment',
            'x-broker': '0008',
            'x-sign': x_sign(),
        }
        last_err: Optional[str] = None
        for attempt in range(_ADJUST_MAX_RETRIES):
            self._throttle.wait()
            try:
                resp = self.session.post(_ADJUST_URL, json=payload, headers=headers, timeout=30)
            except requests.RequestException as e:
                last_err = f'请求异常 {e}'
                self.logger.warning(f'且慢官方调仓 {code} {last_err}（第 {attempt + 1}/{_ADJUST_MAX_RETRIES} 次）')
            else:
                if resp.status_code != 200:
                    last_err = f'HTTP {resp.status_code}'
                    self.logger.warning(f'且慢官方调仓 {code} {last_err}（第 {attempt + 1}/{_ADJUST_MAX_RETRIES} 次）')
                else:
                    try:
                        return resp.json()
                    except ValueError as e:
                        last_err = f'响应非 JSON：{e}'
                        self.logger.warning(f'且慢官方调仓 {code} {last_err}')
            if attempt < _ADJUST_MAX_RETRIES - 1:
                time.sleep(_ADJUST_RETRY_BACKOFF[min(attempt, len(_ADJUST_RETRY_BACKOFF) - 1)])
        raise RuntimeError(last_err or '未知错误')

    def _fetch_adjustments(self, code: str) -> tuple:
        """翻页取全量官方调仓；返回 ``([nodes], None)`` 或 ``([], 错误说明)``。

        「拿不到」与「确实没有」**在这里必须分开**（AGENTS.md「判据必须有失败态」）：
        前者返回错误串让调用方打 WARNING，后者是 ``BAD_USER_INPUT 策略不存在`` /
        空列表（计划型组合），属于正常业务形态。
        """
        nodes: List[dict] = []
        cursor: Optional[str] = None
        for _ in range(_ADJUST_MAX_PAGES):
            try:
                body = self._post_graphql(code, cursor)
            except RuntimeError as e:
                return [], str(e)
            if body.get('errors'):
                first = (body['errors'] or [{}])[0]
                ext = first.get('extensions') or {}
                return [], f'{ext.get("code") or "GRAPHQL_ERROR"} {first.get("message")}'
            conn = ((body.get('data') or {}).get('portfolio') or {}).get('adjustments')
            if conn is None:
                # portfolio 为 null：代码不属于 alfa/portfolio（计划型 / 不存在）
                return [], 'portfolio 为空（该代码不属于 alfa/portfolio）'
            for raw in conn.get('adjustments') or []:
                node = self._parse_adjustment(raw)
                if node:
                    nodes.append(node)
            info = conn.get('pageInfo') or {}
            if not info.get('hasMore') or not info.get('cursor'):
                break
            cursor = info['cursor']
        return nodes, None

    @staticmethod
    def _parse_adjustment(raw: dict) -> Optional[dict]:
        """单次官方调仓 → canonical 调仓节点；无有效基金动作返回 ``None``。

        两个必须注意的坑（都是实测）：

        1. **``groups[].movementName`` 与 ``parts[].movementName`` 不是一回事**——前者是
           分类（股票型/混合型/货币型）的汇总动作，后者才是逐基金的真实动作。同一 group
           里可以同时出现 持平/调出/调增/调减。取 group 的动作名会给整组基金套上同一个动作。
        2. **比例是小数**（``0.04``），而库内 ``pre_ratio`` / ``after_ratio`` 存百分点
           （``4.0`` 表示 4%）。不 ×100 会显示成 ``0.04%``。
        """
        adjust_date = str(raw.get('date') or '')[:10]
        if len(adjust_date) != 10:
            return None
        parts = [p for g in (raw.get('groups') or []) for p in (g.get('parts') or [])]
        funds = []
        for p in parts:
            movement = str(p.get('movementName') or '').strip()
            if not movement or movement == _MOVEMENT_NOOP:
                continue
            fund = p.get('fund') or {}
            fund_code = str(fund.get('fundCode') or '').strip()
            if not fund_code:
                continue
            funds.append(
                {
                    'fund_code': fund_code,
                    'fund_name': fund.get('fundName'),
                    'pre_ratio': _pct(p.get('beforePercent')),
                    'after_ratio': _pct(p.get('afterPercent')),
                    'op_code': _MOVEMENT_TO_OP_CODE.get(movement),
                    'op_name': movement,
                }
            )
        if not funds:
            return None
        # 主理人原文；官方尾部常带多个制表符/换行，去掉首尾空白
        comment = ' '.join(str(raw.get('comment') or '').split())
        return {'adjust_date': adjust_date, 'reason': comment, 'funds': funds}

    def fetch_nav_history(self, strategy_code: str) -> list:
        """组合历史净值序列 ``[{nav_date, nav}]``（``GetPortfolioNavHistory``）。

        且慢是**唯一**提供组合净值序列的平台：MCP 一次调用返回成立至今全量日频净值
        （实测 ZH012926 = 2250 行）。天天基金与好买的投顾接口只给当日净值，
        未实现本方法 ⇒ 走基类默认的 ``[]``。

        Raises:
            McpTokenMissing / McpError: 与概览 / 持仓同口径——**调不通要抛**，
                不能返回 ``[]``，否则会被上层读成「这组合没有净值序列」。
        """
        code = str(strategy_code or '').strip()
        if not code:
            return []
        return self._fetcher.fetch_portfolio_nav_history(code)
