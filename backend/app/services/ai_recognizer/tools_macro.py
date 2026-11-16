# -*- coding: utf-8 -*-
"""账本精灵·宏观指标只读工具（#1502 步骤 2）。

为什么独立成模块
----------------
``tools.py`` 被 ``scripts/guard_service_size.py`` 冻结在 644 行（只减不增）；
``tools_fund.py`` 已占「基金个体」维度。宏观指标（GDP / CPI / PPI / PMI / M2 /
社融 / LPR …）既不是「我的账户」也不是「某只基金」，语义上自成一域，故新建本模块，
由 ``tools_domain`` 统一装配。

三条纪律
--------
1. **一次调用完成「检索 → 选择 → 取数」**：本项目的 Agent 是约束式单工具选择，
   模型不会自己连调两步（见 :mod:`app.services.adapters.wind_macro` 模块头）。
2. **歧义不猜**：多口径候选回 ``ambiguous: true`` + 候选清单，让模型换精确问法重试。
   取第一个候选是这里最容易犯、也最难被发现的错——它会把「现价 GDP」当成「不变价
   同比」讲给用户。
3. **口径随数据一起下发**：``change_vs_prev`` 是「最新值减上期值」，对同比/环比类
   指标是**增速的变化（百分点）**，不是涨跌幅。这条不写清，叙事必然讲错。

出参投影：最多 40 期、单次 ≤ 2KB，与基金工具同一预算纪律。

预筛线索口径
------------
``tool_budget._DOMAIN_CUES['macro']`` 只认**专有指标名**（GDP / CPI / PMI / M2 / LPR …），
刻意**不含**「同比 / 增长 / 数据」——这三个词在「这只基金近一年同比涨了多少」里也出现，
误命中会把宏观工具白装进纯基金提问（宏观域省 78% 掉到跨域只省 40%，且不报错，只变贵）。
新增线索时沿用这条判据：问句里**只有**宏观提问才会出现的词，才算线索。
"""

from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

from app.core.time_utils import today_shanghai
from app.services.adapters import wind_macro

#: 默认/上限期数：宏观指标是月季频，8 期足够看趋势；40 期覆盖十年月度
_DEFAULT_PERIODS = 8
_MAX_PERIODS = 40
#: 歧义时回几个候选：够模型挑，又不挤占上下文
_MAX_CANDIDATES = 8
#: 频率 → 单期天数。认不出按「季」：宏观指标最常见，且窗口偏大只会多取（多花流量），
#: 偏小才会取空——取空是故障，多取只是费用。
_DAYS_PER_FREQ = ((('日', 'd'), 3), (('周', 'w'), 10), (('月', 'm'), 31), (('季', 'q'), 92), (('年', 'y', 'a'), 366))
#: 窗口下/上限：低于两年会让季频指标取不满 8 期；上限二十年防止模型传离谱期数
_MIN_WINDOW_DAYS = 730
_MAX_WINDOW_DAYS = 7300


def _periods_of(raw: object) -> int:
    """期数归一：缺省 8，越界 clamp 到 ``[1, 40]``，非整数一律回默认值。

    schema 只声明了 ``minimum``/``maximum``，但 ``tools._validate_value`` **不校验**
    这两个关键字（只认 type / enum / pattern），所以边界必须在这里兜——否则模型传
    999 会拉一个几十年的窗口，一次调用烧掉几十 KB。
    """
    if isinstance(raw, bool) or not isinstance(raw, int):
        return _DEFAULT_PERIODS
    return max(1, min(_MAX_PERIODS, raw))


def _window_days(freq: Optional[str], periods: int) -> int:
    """按频率推算取数窗口（天）：``periods`` 期 + 60 天发布滞后余量。"""
    text = str(freq or '').strip().lower()
    per_period = 92
    for keys, days in _DAYS_PER_FREQ:
        if text.startswith(keys):
            per_period = days
            break
    return min(max(periods * per_period + 60, _MIN_WINDOW_DAYS), _MAX_WINDOW_DAYS)


def _pick_indicator(candidates: List[dict], question: str) -> Optional[dict]:
    """在候选里定指标；定不了返回 ``None``（= 歧义，交给调用方回候选）。

    三级判据，逐级收紧：
    1. 只有一条候选 → 就是它；
    2. 某候选归一化后**等于**问句 → 用户已经给了精确名；
    3. 问句是某候选名的**连续子串**且唯一 → 用户给的是精确名的片段。
    其余一律判歧义。**不按「相关度最高」挑**：上游顺序是检索得分序，不是口径优先级。
    """
    if len(candidates) == 1:
        return candidates[0]
    want = wind_macro.normalize(question)
    for cand in candidates:
        if wind_macro.normalize(cand['name']) == want:
            return cand
    contained = [c for c in candidates if want and want in wind_macro.normalize(c['name'])]
    if len(contained) == 1:
        return contained[0]
    return None


def _series_for(series: List[dict], name: str) -> Optional[dict]:
    """从上游返回的多条序列里取目标指标（精确名优先，归一化后唯一才回退）。"""
    for row in series:
        if row['name'] == name:
            return row
    want = wind_macro.normalize(name)
    hits = [r for r in series if wind_macro.normalize(r['name']) == want]
    return hits[0] if len(hits) == 1 else None


def _project(pick: dict, row: dict, ordered: List, periods: int, begin: date, end: date) -> dict:
    """叙事投影：只留叙事要用的字段，并把口径写进 ``caveats``。"""
    latest_day, latest_val = ordered[-1]
    prev = ordered[-2] if len(ordered) > 1 else None
    return {
        'found': True,
        'indicator': row['name'],
        'freq': row.get('freq') or pick.get('freq'),
        'unit': row.get('unit'),
        'requested_periods': periods,
        'returned_periods': len(ordered),
        'window': f'{begin.isoformat()}~{end.isoformat()}',
        'latest': {'date': latest_day.isoformat(), 'value': latest_val},
        'prev': {'date': prev[0].isoformat(), 'value': prev[1]} if prev else None,
        'change_vs_prev': round(latest_val - prev[1], 4) if prev else None,
        'points': [{'date': day.isoformat(), 'value': value} for day, value in ordered],
        'source': 'Wind EDB',
        'as_of': end.isoformat(),
        'caveats': [
            'points 是上游原值，单位随指标（百分比 / 亿元 / 点等），本工具不做换算。',
            'change_vs_prev = 最新值 − 上期值；若指标本身是同比/环比，这是增速的变化（百分点），不是涨跌幅。',
            '缺失期表示上游无值，未补 0；只回已发布数据，不含预测。',
        ],
    }


def _tool_query_macro_indicator(params: dict) -> dict:
    """查国家级宏观指标时间序列（检索 → 选择 → 取数，全在一次调用内完成）。"""
    question = str(params.get('question') or '').strip()
    periods = _periods_of(params.get('periods'))
    if not wind_macro.is_available():
        # 未配置 ≠ 故障：前者是可选组件未启用，后者该抛（由 ToolExecutor 转 error）
        return {'available': False, 'reason': '宏观数据源（Wind EDB）未配置，无法查询宏观指标。'}

    candidates = wind_macro.search_indicators(question)
    if not candidates:
        return {
            'found': False,
            'query': question,
            'reason': '上游指标库里没有匹配项，换一种说法（如「中国GDP当季同比」「制造业PMI」）再试。',
        }

    pick = _pick_indicator(candidates, question)
    if pick is None:
        return {
            'found': True,
            'ambiguous': True,
            'query': question,
            'candidates': candidates[:_MAX_CANDIDATES],
            'reason': '命中多个口径，不替用户猜。请用候选里的精确指标名重新提问一次。',
        }

    end = today_shanghai()
    begin = end - timedelta(days=_window_days(pick.get('freq'), periods))
    row = _series_for(wind_macro.fetch_series(pick['name'], begin, end), pick['name'])
    if row is None or not row['points']:
        # adapter 已滤掉空序列，这里仍要判：工具不能依赖 adapter 的过滤细节，
        # 否则 adapter 一改（比如为了别的场景保留空条目）这里就 IndexError
        return {
            'found': False,
            'indicator': pick['name'],
            'query': question,
            'window': f'{begin.isoformat()}~{end.isoformat()}',
            'reason': '上游未返回该指标在窗口内的数据点（可能尚未发布或已停更）。',
        }
    # 窗口按「期数 + 余量」推算，日频会多取（40 期窗口约 120 个交易日）：
    # 只留最近 periods 期，与 requested_periods 对齐，避免出参与模型预期不符
    return _project(pick, row, sorted(row['points'].items())[-periods:], periods, begin, end)


MACRO_TOOLS_METADATA: List[dict] = [
    {
        'name': 'query_macro_indicator',
        'description': '查国家级宏观指标的时间序列：GDP、CPI、PPI、PMI、M2、社融、'
        '工业增加值、固定资产投资、进出口、失业率、LPR、国债收益率、汇率等。'
        '当用户问「最近 GDP 增速多少」「CPI 高不高」「制造业 PMI 是多少」'
        '「现在利率/汇率什么水平」「宏观环境怎么样」时使用。'
        '**不用于**某只基金或我的账户的盈亏涨跌（那是基金/账户域的工具）。'
        '内部先在上游指标库检索再取序列：若命中多个口径（同一指标常有现价/不变价/同比），'
        '返回 ambiguous=true 与 candidates 清单——此时**不要猜**，用候选里的精确指标名重试一次。'
        'periods 是返回最近多少期（默认 8，最大 40）；freq 是上游频率。'
        'points 是上游原值，单位随指标，不要自行换算；change_vs_prev 是「最新值减上期值」，'
        '若指标本身是同比/环比，这是增速变化（百分点），不是涨跌幅。'
        '只回已发布数据、不预测；available=false 表示数据源未配置，如实告知无法查询',
        'parameters': {
            'type': 'object',
            'properties': {
                'question': {
                    'type': 'string',
                    'description': '要查的宏观指标：自然语言（如「中国GDP当季同比」）或候选清单里的精确指标名',
                },
                'periods': {
                    'type': 'integer',
                    'minimum': 1,
                    'maximum': _MAX_PERIODS,
                    'description': f'返回最近多少期，默认 {_DEFAULT_PERIODS}，最大 {_MAX_PERIODS}',
                },
            },
            'required': ['question'],
        },
    },
]

_MACRO_TOOL_FUNCS: Dict[str, Callable[[dict], dict]] = {
    'query_macro_indicator': _tool_query_macro_indicator,
}


def install_macro_tools(register: Callable[[str, Callable], None], metadata: List[dict]) -> None:
    """把宏观工具接进注册表与元数据清单（由 ``tools_domain`` 装配，调用点唯一）。"""
    for name, func in _MACRO_TOOL_FUNCS.items():
        register(name, func)
    metadata.extend(MACRO_TOOLS_METADATA)


__all__ = ['MACRO_TOOLS_METADATA', 'install_macro_tools']
