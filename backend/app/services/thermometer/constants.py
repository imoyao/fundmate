# -*- coding: utf-8 -*-
"""
市场温度模块常量集中定义

将分散在 fetchers 中的 URL、请求头、阈值等"魔法值"统一抽到此处，
避免在多处重复书写、便于维护。
"""

from enum import Enum
from typing import Dict, Optional


# ─── 温度档位枚举（唯一权威来源）───
# 所有「温度类」指标的定性档位必须取自此处，禁止在 fetchers / service 中
# 硬编码 '偏低' / '适中' / '偏高' 或混用 '正常' 等近义词，避免前后端语义割裂。
class TempLevel(str, Enum):
    LOW = '偏低'
    MID = '适中'
    HIGH = '偏高'


# ─── 东财：全市场成交额 ───
EASTMONEY_BOARDS: Dict[str, str] = {
    '上证': '1.000001',
    '深证': '0.399001',
    '北证': '0.899050',
}
EASTMONEY_HOSTS = ['push2.eastmoney.com', 'push2delay.eastmoney.com']
EASTMONEY_REFERER = 'https://quote.eastmoney.com/'

# ─── 新浪：全市场成交额兜底（#1431；东财 push2 限流时的替代源）───
# 新浪 s_ 前缀简版行情字段：名称,点位,涨跌额,涨跌幅,成交量,成交额。
# 单位差异（实测）：沪/深 成交额为「万元」，北证为「元」——故按板块给出换算除数（→ 亿元）。
SINA_VOLUME_BOARDS: Dict[str, tuple] = {
    '上证': ('s_sh000001', 1e4),
    '深证': ('s_sz399001', 1e4),
    '北证': ('s_bj899050', 1e8),
}
SINA_VOLUME_URL = 'https://hq.sinajs.cn/list=' + ','.join(v[0] for v in SINA_VOLUME_BOARDS.values())
SINA_REFERER = 'https://finance.sina.com.cn'

# ─── 集思录 ───
JISILU_CB_URL = 'https://www.jisilu.cn/data/indicator/get_cb_temperature/'
JISILU_INDICATOR_URL = 'https://www.jisilu.cn/data/indicator/get_last_indicator/'
JISILU_REFERER = 'https://www.jisilu.cn/data/indicator/'

# ─── 且慢 MCP（Streamable HTTP）───
QIEMAN_MCP_URL = 'https://stargate.yingmi.com/mcp/v2'
QIEMAN_PROTOCOL_VERSION = '2024-11-05'
QIEMAN_CLIENT_INFO = {'name': 'fundmate', 'version': '1.0.0'}
QIEMAN_TOOL = 'GetLatestQuotations'  # 市场温度计
QIEMAN_STRATEGY_DETAIL_TOOL = 'GetStrategyDetails'  # 投顾组合概览/风险收益指标
QIEMAN_STRATEGY_COMPOSITION_TOOL = 'BatchGetStrategiesComposition'  # 投顾组合持仓

# 且慢组合概览（GetStrategyDetails）中文字段 → 归一化英文键（实测 2026-09）。
# 集中在此便于接口扩字段时只改一处，勿散落到 fetcher / job。
QIEMAN_STRATEGY_DETAIL_FIELDS: Dict[str, str] = {
    '策略代码': 'code',
    '策略名称': 'name',
    '策略简介': 'summary',
    '策略描述': 'desc',
    '策略成立时间': 'estab_date',
    '策略风险等级': 'risk_level',
    '管理人名称': 'org_name',
    '管理人简介': 'org_intro',
    '管理人头像': 'org_avatar',
    '是否实名认证': 'verified',
    '策略净值': 'nav',
    '最新净值日期': 'nav_date',
    '日收益率': 'return_1d',
    '周收益率': 'return_1w',
    '月收益率': 'return_1m',
    '季度收益率': 'return_1q',
    '半年收益率': 'return_6m',
    '年收益率': 'return_1y',
    '成立以来收益率': 'return_since_incep',
    '最大回撤': 'max_drawdown',
    '夏普比率': 'sharpe_ratio',
    '波动率': 'volatility',
    '年化收益率': 'annual_return',
    'url': 'url',
}

#: 上述字段中「带百分号的字符串」集合，归一化时剥 % 转 float（'20.32%' → 20.32）
QIEMAN_STRATEGY_PCT_FIELDS = frozenset(
    {
        'return_1d',
        'return_1w',
        'return_1m',
        'return_1q',
        'return_6m',
        'return_1y',
        'return_since_incep',
        'max_drawdown',
        'volatility',
        'annual_return',
    }
)

#: 上述字段中的纯数值字段，归一化时直接转 float
QIEMAN_STRATEGY_NUM_FIELDS = frozenset({'nav', 'sharpe_ratio'})

#: GetStrategyDetails 单次可传的组合代码上限（接口 pageSize 上限 100，留余量）
QIEMAN_STRATEGY_BATCH_SIZE = 50

# ─── 有知有行 ───
YOUZHIYOUXING_URL = 'https://youzhiyouxing.cn/thermometer'

# ─── 韭圈儿 ───
JIUCASHUO_URL = 'https://app.jiucaishuo.com/'

# ─── 概览链接（展示用）───
LINKS = {
    'qieman': 'https://qieman.com/',
    'youzhiyouxing': 'https://youzhiyouxing.cn/thermometer',
    'jisilu': 'https://www.jisilu.cn/data/indicator/',
    'jiucaishuo': 'https://funddb.cn/tool/fear/',
    'eastmoney': 'https://quote.eastmoney.com/',
}


# ─── 标签阈值函数（集中管理"魔法数字"）───
def label_volume(total: float) -> str:
    """全市场成交额定性标签。"""
    return '放量' if total > 12000 else ('缩量' if total < 8000 else '温和')


# ─── 数据新鲜度守卫（#1431）───
# 温度类数据的最新 collected_at 距今超过该天数即视为「陈旧」，前端须显式提示，
# 不允许静默展示旧快照。取 5 天以容纳周末 + 单个节假日。
FRESHNESS_THRESHOLD_DAYS = 5


def _to_float(value: object) -> Optional[float]:
    """把温度输入安全转 float；无法转换（字符串脏值 '--'/空串/None）返回 None。

    集思录等数据源改版后，数值字段可能以字符串形式返回（如 '22.75'），
    也可能返回 '--'/'N/A'/空串等不可解析脏值。统一在此容错，
    避免 label_temp 内 ``value > 70`` 出现 str 与 int 比较的运行时崩溃。
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s or s in ('--', 'N/A', 'NA', 'null', 'None'):
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def label_temp(value: object) -> str:
    """温度定性标签（可转债温度 / 综合温度等）。唯一权威来源，禁止散落副本。

    输入容错：字符串数值（如 '22.75'）、脏值（'--'/空串/None）均安全处理，
    解析失败返回 '未知'，不会因类型不匹配抛出 TypeError。
    """
    v = _to_float(value)
    if v is None:
        return '未知'
    if v > 70:
        return TempLevel.HIGH.value
    if v > 40:
        return TempLevel.MID.value
    return TempLevel.LOW.value


def label_fear(n) -> str:
    """恐惧贪婪指数定性标签（0-100）。"""
    if n is None:
        return '未知'
    if n < 10:
        return '极度恐惧'
    if n < 25:
        return '恐惧'
    if n < 45:
        return '偏恐惧'
    if n < 55:
        return '中性'
    if n < 75:
        return '偏贪婪'
    if n < 90:
        return '贪婪'
    return '极度贪婪'
