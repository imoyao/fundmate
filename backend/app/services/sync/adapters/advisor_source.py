# -*- coding: utf-8 -*-
"""投顾组合数据源 Port：平台无关契约 + 适配器注册表（#1392）。

## 为什么需要这一层

#1167 接入天天基金、#1468 接入且慢时，两条链路是**直接写进同步任务**的——
``AdvisorPortfolioSyncJob`` 里按 ``platform`` 做 if/else 分支，两个适配器的方法名也
并不统一（``fetch_current_holdings`` / ``fetch_holdings``、``fetch_industry`` /
``fetch_adjust_history``）。后果是：

- 「新增一个平台」= 改同步任务，「只加适配器、不改调用方」无法成立；
- 每个新平台都要重新验证落库语义（覆盖式快照 / 快照推导调仓 / 策展字段不被抓取覆盖），
  而这些语义**与平台无关**，本不该跟着平台一起改。

本模块把「平台差异」收进适配器、把「落库语义」留在 job：

- **Port**：:class:`AdvisorPortfolioSource` 声明 4 个数据面 + 1 个能力位；
- **Adapter**：每平台一个（``tiantian_advisor_adapter`` / ``qieman_advisor_adapter``），
  负责把平台原始响应翻译成 canonical；
- **Registry**：``platform → 适配器类``（:func:`register_advisor_source` 装饰器注册），
  job 只按 platform 取源，**不再认识任何具体平台**。

新增平台（如蛋卷）的完整改动 = 写一个适配器 + 挂装饰器，**不改 job、不改表**
（canonical 覆盖不到的字段进 :data:`EXTRA_KEY`）。

## canonical 概览字段

键名与 ``advisor_portfolios`` 的列名**逐字一致**（见 :data:`CANONICAL_OVERVIEW_COLUMNS`）——
少一次「canonical 名 ↔ 列名」的翻译，也就少一处可漂移的映射表。
适配器**可以把拿不到的字段置 None**（或干脆不返回该键）：落库层只覆盖非 None 值，
接口缺字段 / 抓取失败都不会把库内已有数据冲成空。

canonical 之外的平台特有字段放 :data:`EXTRA_KEY`，原样落 ``advisor_portfolios.extra``
（JSON 列），供日后「补一个新列」时回填，避免为拿单个字段重新抓一遍。

区间收益命名遵循仓库规范（英文 snake_case、自解释）：``return_1d/1w/1m/1q/6m/1y/ytd/since_incep``；
平台黑话（如天天基金的 ``SYL_1N``）只允许出现在适配器内部。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

#: canonical 概览字段（= ``advisor_portfolios`` 列名）——单一真相源。
#: 新增平台先看这里有没有可复用的列；确实没有的才进 extra（不得随手加列）。
CANONICAL_OVERVIEW_COLUMNS: tuple[str, ...] = (
    'name',
    'org_name',
    'risk_level',
    'estab_date',
    'strategy_summary',
    'strategy_desc',
    'source_url',
    'nav',
    'nav_date',
    'annual_return',
    'cum_return',
    'max_drawdown',
    'excess_return',
    'volatility',
    'sharpe_ratio',
    'return_1d',
    'return_1w',
    'return_1m',
    'return_1q',
    'return_6m',
    'return_1y',
    'return_ytd',
    'return_since_incep',
)

#: canonical 概览里需要按日期解析的键（字符串 → date 由落库层统一处理）
OVERVIEW_DATE_KEYS: frozenset = frozenset({'estab_date', 'nav_date'})

#: **策展字段**：由 ``app/domains/funds/advisor_catalog.py`` 注册表人工维护
#: （host 主理人 / allocation 五笔钱 / product_type 产品类型），
#: 抓取结果**不得覆盖**——接口给的值往往粗糙或为空，覆盖即丢策展质量（#1468 结论）。
CURATED_OVERVIEW_KEYS: frozenset = frozenset({'host', 'allocation', 'product_type'})

#: 平台特有字段在概览 dict 里的键名（落 ``advisor_portfolios.extra``）
EXTRA_KEY = 'extra'

#: 平台归属无法判定时的兜底平台（库内未建档 + 注册表未收录）
DEFAULT_ADVISOR_PLATFORM = 'TIANTIAN'


class UnknownAdvisorPlatform(RuntimeError):
    """平台没有注册适配器——要么补适配器，要么由调用方决定是否忽略该组合。"""


class AdvisorPortfolioSource(ABC):
    """投顾组合数据源契约（Ports & Adapters 的 Port）。

    取值口径：

    - ``platform`` 必须与 ``AdvisorPortfolio.platform`` 一致（大写，如 ``QIEMAN``）；
    - 数据面方法**无该数据面时返回空集合**（``[]`` / ``{}``），不要抛错——
      job 对空集合天然无操作，这样「平台能力差异」不需要额外的能力开关；
    - 唯一需要显式声明的能力位是 :attr:`derive_rebalances_from_snapshots`：
      它描述的是「**没有**官方调仓接口，须由落库层用快照序列推导」，
      推导算法在 job 侧统一实现，适配器无法自给，故必须声明。
    """

    #: 平台标识（与 ``AdvisorPortfolio.platform`` 取值一致）
    platform: str = ''

    #: 是否有**官方**历史调仓数据面；False 时只能靠 :attr:`derive_rebalances_from_snapshots`
    has_official_rebalances: bool = False

    #: 无官方调仓接口时，是否允许由持仓快照序列推导调仓明细（落库层统一实现）
    derive_rebalances_from_snapshots: bool = False

    @abstractmethod
    def get_name(self) -> str:
        """数据源标识（落 ``sync_logs.data_source``，不得为空）。"""

    @abstractmethod
    def get_version(self) -> str:
        """数据源版本（接口契约变更时递增）。"""

    @abstractmethod
    def fetch_overview(self, code: str) -> Dict[str, Any]:
        """组合概览 / 风险收益指标。

        返回 canonical 字典，键取 :data:`CANONICAL_OVERVIEW_COLUMNS` 的子集
        （值为 None 的键允许存在，落库层会跳过），拿不到的字段**不要编造**：
        宁可为空，也不要填 0 或猜一个数。
        """

    @abstractmethod
    def fetch_holdings(self, code: str) -> Dict[str, Any]:
        """当前基金级持仓快照。

        返回 ``{'as_of_date': 'YYYY-MM-DD' | None, 'funds': [...]}``，
        ``funds`` 每条为 ``{fund_code, fund_name, pre_ratio, after_ratio, op_code, op_name}``
        （无该字段置 None）。``as_of_date`` 是**字符串**：日期解析统一由落库层负责，
        适配器不做类型转换（各平台日期形态不一，收口在一处更好维护）。
        """

    @abstractmethod
    def fetch_industries(self, code: str) -> List[Dict[str, Any]]:
        """行业配置 ``[{industry_name, ratio}]``；无该数据面返回 ``[]``。"""

    @abstractmethod
    def fetch_rebalances(self, code: str) -> List[Dict[str, Any]]:
        """官方历史调仓 ``[{adjust_date, reason, funds: [...]}]``；无该数据面返回 ``[]``。"""


#: platform → 适配器类（由 :func:`register_advisor_source` 填充）
_SOURCES: Dict[str, type] = {}
#: 内置适配器是否已导入。用独立标志而非 ``if _SOURCES``：测试若先注册假平台，
#: 后者会让内置适配器永远不加载（静默漏掉天天/且慢）。
_BUILTINS_LOADED = False


def register_advisor_source(cls: type) -> type:
    """注册平台适配器（类装饰器；适配器模块被 import 即完成注册）。"""
    if not issubclass(cls, AdvisorPortfolioSource):
        raise TypeError(f'{cls.__name__} 必须继承 AdvisorPortfolioSource 才能注册')
    platform = str(getattr(cls, 'platform', '') or '').strip().upper()
    if not platform:
        raise ValueError(f'{cls.__name__} 必须声明非空 platform（与 AdvisorPortfolio.platform 取值一致）')
    cls.platform = platform
    _SOURCES[platform] = cls
    return cls


def _ensure_builtin_sources() -> None:
    """导入内置适配器模块（模块级 ``@register_advisor_source`` 即完成注册）。

    放在函数内 import：``advisor_source`` 是被各适配器 import 的底座，
    模块级反向 import 适配器会构成循环依赖。
    """
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    _BUILTINS_LOADED = True
    # 导入即注册（isort 会按字母序排列，此处保留 noqa 以防 ruff 误判未使用）
    from app.services.sync.adapters import qieman_advisor_adapter, tiantian_advisor_adapter  # noqa: F401


def registered_platforms() -> tuple[str, ...]:
    """已注册适配器的平台列表（升序）。"""
    _ensure_builtin_sources()
    return tuple(sorted(_SOURCES))


def get_advisor_source(platform: str) -> AdvisorPortfolioSource:
    """按平台构造数据源实例（每次调用新建；需要复用请用 :class:`AdvisorSourceRegistry`）。"""
    _ensure_builtin_sources()
    key = str(platform or '').strip().upper()
    cls = _SOURCES.get(key)
    if cls is None:
        raise UnknownAdvisorPlatform(
            f'投顾平台 {platform!r} 未注册数据源——请先写适配器并挂 @register_advisor_source；'
            f'已注册：{list(registered_platforms())}'
        )
    return cls()


class AdvisorSourceRegistry:
    """多平台数据源注册表，同时充当同步任务的 ``adapter``（审计口径）。

    ``SyncJob`` 的 ``adapter`` 槽位被 ``orchestrator._save_sync_log`` 用来写
    ``sync_logs.data_source`` / ``data_source_version``，故本类必须提供
    ``get_name`` / ``get_version``；单平台适配器不再适合这个槽位（一轮同步可能跨平台）。

    实例缓存：天天适配器持有 ``requests.Session``、且慢是 MCP 客户端，
    按平台缓存可避免每个组合都新建连接对象。
    """

    def __init__(self, sources: Optional[Dict[str, AdvisorPortfolioSource]] = None) -> None:
        """``sources`` 为显式注入的 ``{platform: 适配器实例}``（测试 / 特殊场景）。"""
        self._sources: Dict[str, AdvisorPortfolioSource] = {
            str(platform).strip().upper(): src for platform, src in (sources or {}).items()
        }

    def get(self, platform: str) -> AdvisorPortfolioSource:
        """取平台数据源：显式注入优先，否则按注册表懒构造并缓存。"""
        key = str(platform or '').strip().upper()
        src = self._sources.get(key)
        if src is None:
            src = get_advisor_source(key)
            self._sources[key] = src
        return src

    def platforms(self) -> tuple[str, ...]:
        """本注册表可覆盖的平台（显式注入的 ∪ 已注册的）。"""
        return tuple(sorted(set(self._sources) | set(registered_platforms())))

    def get_name(self) -> str:
        return 'advisor_multi'

    def get_version(self) -> str:
        return 'v1'
