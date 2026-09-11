# -*- coding: utf-8 -*-
"""跨渠道关联的名称归一与匹配（#1285 设计 §3.8 / 残留缺口跟踪 #1419）。

── 为什么需要这一层 ──
ETF 的「跟踪标的」在**任何免 cookie 数据源里都不存在**（2026-09-11 逐一实测：
`fund_etf_spot_em` 1606 只全无该字段；沪深交易所 ETF 规模表 `fund_etf_scale_sse/szse`
也无）——跨渠道关联只能靠**名称匹配**。旧实现（PR #1399）用东财场内简称做子串匹配，
总覆盖仅 41.1%（660/1605，低于设计 90% 门槛），故降级为 13 个宽基白名单（实际落库 274 条）。

── 关键实测结论：瓶颈在「文本源」而不是「算法」──
2026-09-11 以 1722 只 ETF（东财 1606 ∪ 同花顺 1719）× `index_catalog` 4100 条实测：

| 匹配文本            | 算法                  | 覆盖率 |
|--------------------|----------------------|-------|
| 东财场内简称         | 原始子串（旧实现）      | 45.2% |
| 东财场内简称         | 归一化 + 最长子串       | 63.4% |
| **同花顺基金全称**    | **归一化 + 最长子串**   | **89.0%** |
| 同花顺基金全称        | 加入精度过滤（本模块默认） | 66.4% |

东财简称是**交易所缩写**（「通信ETF国泰」），指数名被压没了；同花顺全称保留完整
指数名（「国泰中证全指通信设备ETF」），才能与 `index_catalog` 的「通信设备」(931160)
对上。**换文本源比调算法收益大一个量级。**

⚠️ 反面结论（同样实测，用于阻止重复踩坑）：#1413 里提出的
「剥离基金公司名后缀 + **全名精确匹配**」**不成立**——归一化后精确匹配只有 49.5%，
比旧实现仅高 1.1pp。真正有效的是「归一化 + **最长子串**」；而子串策略必须配
**泛词黑名单**，否则 2~4 字的泛化指数名（「中证」「红利」「创业板」「科技」
「中证工业」「中证金融」）会吞掉更长语义，产出
「招商中证稀有金属主题ETF → 中证基金」「广发标普港股通低波红利ETF → 红利指数」
这类**错配**（实测样本）。

── 第三条实测结论：仅按「长度」排序不够 ──
`中证军工`(399967) 与 `军工龙头`(931066) 核心名同为 4 字，只按长度排序时命中谁
取决于 `index_catalog` 的**行序**——「广发中证军工龙头ETF」会被错配到「中证军工」。
故 `match_index` 同长度时取**位置最靠后**者（后缀对齐，指数名通常落在 ETF 名末尾）；
回归用例见 `tests/services/sync/test_channel_link_job.py::test_match_same_length_prefers_suffix_aligned`。

── 交付口径 ──
89.0% 是「含错配」的毛覆盖，66.4% 是「过滤后」净覆盖（1722 只 ETF 并集，交付代码实测）。
本模块取**后者**：宁缺毋滥——关联浮层给错的标的比不给更糟。
未命中的留 `—`，缺口（跨境/商品标的、名录缺精确指数名）记在 #1419（远期）。
"""

from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

# ── 公司名派生：`fund_companies.name` 是简称（「易方达基金」），全称是法人口径
# （「易方达基金管理有限公司」）；而 ETF 名称里出现的是**去掉「基金」二字的简称**
# （「巴西ETF易方达」「易方达中证A500ETF」）。两条口径都要能剥。
_COMPANY_SUFFIXES = (
    '基金管理股份有限公司',
    '基金管理有限公司',
    '资产管理有限公司',
    '基金管理',
    '资产管理',
    '基金',
)

# 产品名里的**非指数**要素：交易结构（ETF/LOF/联接）、份额类别、币种、收费方式。
# 顺序敏感：长词在前，避免「ETF联接」被「ETF」先切掉而残留「联接」。
_NOISE_TOKENS = (
    'ETF联接基金',
    'ETF联接',
    'ETF',
    'LOF',
    '联接基金',
    '联接',
    '基金',
    '交易型开放式',
    '开放式',
    '证券投资基金',
    '指数型',
    '指数增强',
    '指数',
    '增强型',
    '增强',
    'QDII',
    'QFII',
    '美元',
    '现汇',
    '现钞',
    '人民币',
    '后端',
    '前端',
    '发起式',
    '期货',
)

# ── 泛词黑名单 ──
# 这些词本身是真指数名（或清洗后塌缩成真指数名），但语义太宽：任何含该词的
# 主题 ETF 都会命中，必然错配。实测错配样本见模块 docstring。
_GENERIC_INDEX_CORES = frozenset(
    {
        '中证',
        '国证',
        '上证',
        '深证',
        '全指',
        '中证全指',
        '创业板',
        '科创',
        '红利',
        '科技',
        '消费',
        '医药',
        '金融',
        '价值',
        '成长',
        '债券',
        '信用债',
        '可转债',
        '同业存单',
        '黄金',
        '恒生',
        '中概',
        '中证工业',
        '中证金融',
        '中证基金',
        '中证港股通',
    }
)

# 核心名最短长度：2 字核心（「红利」「科技」）噪声极大；3 字起误配率大幅下降。
_MIN_CORE_LEN = 3

# ETF 基金公司简称兜底表。
# 为什么需要：名称里的管理人常是**2 字缩写**（「国泰」「华安」「工银」），
# 而 `fund_companies` 里存的是「国泰基金」——剥掉「基金」后一致；但该表仅 164 家
# （市场 190+ 家，且不全是同一口径），故对常见管理人再补一份，避免依赖单表覆盖率。
_KNOWN_COMPANY_TOKENS = frozenset(
    {
        '易方达',
        '华夏',
        '南方',
        '嘉实',
        '广发',
        '富国',
        '汇添富',
        '博时',
        '招商',
        '银华',
        '华安',
        '大成',
        '天弘',
        '华泰柏瑞',
        '国泰',
        '平安',
        '兴业',
        '永赢',
        '摩根',
        '工银',
        '建信',
        '中银',
        '鹏华',
        '景顺长城',
        '诺安',
        '融通',
        '国投瑞银',
        '宝盈',
        '万家',
        '长城',
        '中欧',
        '海富通',
        '兴全',
        '交银',
        '浦银安盛',
        '信达澳亚',
        '前海开源',
        '国联安',
        '华宝',
        '申万菱信',
        '光大保德信',
        '东方',
        '泰达宏利',
        '中信保诚',
        '金鹰',
        '方正富邦',
        '华富',
        '民生加银',
        '中加',
        '中金',
        '国海富兰克林',
        '安信',
        '德邦',
        '东吴',
        '汇安',
        '红土创新',
        '西部利得',
        '鑫元',
        '华润元大',
        '新华',
        '长信',
        '银河',
        '中融',
        '国寿安保',
        '泰康',
        '太平',
        '国金',
        '浙商',
        '财通',
        '兴银',
        '苏新',
        '京管泰富',
        '国联',
        '华泰证券',
        '南方基金',
        '南方东英',
    }
)


class IndexHit(NamedTuple):
    """一次指数命中。`core` 是命中的归一化核心名，供日志/审计追溯匹配依据。"""

    index_code: str
    index_name: str
    core: str


def build_company_tokens(names: Iterable[str]) -> Tuple[str, ...]:
    """由公司名派生可剥离 token，按长度降序（保证长名先剥，避免前缀被截断）。"""
    out = set()
    for raw in names:
        name = (raw or '').strip()
        if not name:
            continue
        out.add(name)
        for suffix in _COMPANY_SUFFIXES:
            if name.endswith(suffix) and len(name) > len(suffix) + 1:
                out.add(name[: -len(suffix)])
    out |= _KNOWN_COMPANY_TOKENS
    return tuple(sorted((t for t in out if 2 <= len(t) <= 12), key=len, reverse=True))


def strip_company(name: str, company_tokens: Sequence[str]) -> str:
    """剥离名称中的基金管理人（前缀或后缀形态都出现，见 docstring）。"""
    out = name or ''
    for _ in range(3):
        hit = False
        for token in company_tokens:
            if out.endswith(token) and len(out) > len(token):
                out, hit = out[: -len(token)], True
                break
            if out.startswith(token) and len(out) > len(token):
                out, hit = out[len(token) :], True
                break
        if not hit:
            break
    return out


def normalize(name: str, company_tokens: Sequence[str]) -> str:
    """把产品名归一为「裸指数名」：剥公司名 → 去交易结构/份额/币种噪声 → 去尾字母。

    份额字母只剥**末尾单个字母**（A/C/E/I/O），且在噪声词清完之后做——否则
    「易方达货币ETF」的尾部 `F` 会被误当份额类别切掉（实测踩过）。
    """
    out = strip_company(name, company_tokens)
    for token in _NOISE_TOKENS:
        out = out.replace(token, '')
    if out and out[-1].isascii() and out[-1].isalpha():
        out = out[:-1]
    return out.strip(' -_·．.()（）')


class ChannelNameMatcher:
    """指数名录的匹配器：预编译归一化结果，避免逐 ETF 重算（O(N×M) → O(N×logM)）。

    生命周期内只读，可在 job 内复用一个实例。
    """

    def __init__(
        self,
        company_names: Iterable[str],
        index_entries: Iterable[Tuple[str, str]],
        min_core_len: int = _MIN_CORE_LEN,
    ) -> None:
        """
        Args:
            company_names: 基金管理人名称（`fund_companies.name` / `full_name`）。
            index_entries: `(index_code, index_name)` 序列（来自 `index_catalog`）。
            min_core_len: 归一化核心名的最短长度；低于此长度视为泛词，不参与匹配。
        """
        self._company_tokens = build_company_tokens(company_names)
        table: List[Tuple[str, str, str]] = []
        for code, name in index_entries:
            core = normalize(name, self._company_tokens)
            if len(core) < min_core_len or core in _GENERIC_INDEX_CORES:
                continue
            table.append((code, name, core))
        # 最长优先：保证「中证1000」不被「中证100」吞掉、主题名不被母指数吞掉。
        table.sort(key=lambda item: -len(item[2]))
        self._table = tuple(table)
        self._by_core: Dict[str, List[Tuple[str, str]]] = {}
        for code, name, core in table:
            self._by_core.setdefault(core, []).append((code, name))

    @property
    def company_tokens(self) -> Tuple[str, ...]:
        return self._company_tokens

    @property
    def index_count(self) -> int:
        """参与匹配的指数条数（已剔除泛词与过短核心名）。"""
        return len(self._table)

    def clean(self, name: str) -> str:
        """对外暴露归一化（联接基金匹配侧要复用同一套口径）。"""
        return normalize(name, self._company_tokens)

    def match_index(self, product_name: str) -> Optional[IndexHit]:
        """产品名 → 命中的指数；无命中返回 None。

        选择规则（按优先级）：
        1. **最长核心名** —— 保证主题指数不被母指数吞掉（「沪深300价值」优先于「沪深300」）。
        2. **同长度时取位置最靠后**（后缀对齐）。

        为什么必须有规则 2（2026-09-11 实测踩坑）：`中证军工`(399967) 与 `军工龙头`(931066)
        核心名同长 4 字，仅按长度排序时命中谁取决于 `index_catalog` 的原始行序——
        「广发中证军工龙头ETF」（归一为「中证军工龙头」）会被错配到「中证军工」。
        指数名通常落在 ETF 名末尾，故同长度下后缀对齐可稳定选中正确标的。
        """
        cleaned = self.clean(product_name)
        if not cleaned:
            return None
        best = None  # (排序键, code, index_name, core)
        best_len = None
        for code, index_name, core in self._table:
            pos = cleaned.find(core)
            if pos < 0:
                continue
            core_len = len(core)
            if best_len is None:
                best_len = core_len
            elif core_len < best_len:
                break  # 表按核心名长度降序，其后只会更短
            key = (core_len, pos)
            if best is None or key > best[0]:
                best = (key, code, index_name, core)
        if best is None:
            return None
        return IndexHit(best[1], best[2], best[3])

    def etf_candidates(self, core: str) -> List[Tuple[str, str]]:
        """归一化核心名 → 候选 ETF `[(code, name)]`（供 ETF↔联接 消歧）。"""
        return self._by_core.get(core, [])


def pick_manager(name: str, company_tokens: Sequence[str]) -> Optional[str]:
    """从产品名**前缀**抽管理人（「嘉实中证500ETF联接A」→「嘉实」）。

    为什么不查 `funds.company_id`：2026-09-11 实测联接基金 2177 只里仅 **89 只**
    有 `company_id`（`fund_list_job` 不回填该列，见 #1402 的同类问题），不可依赖。
    基金简称的命名惯例是「管理人简称 + 产品名」，前缀法覆盖率远高于该列。
    """
    for token in company_tokens:
        if name.startswith(token) and len(name) > len(token):
            return token
    return None
