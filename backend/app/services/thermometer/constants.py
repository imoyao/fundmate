# -*- coding: utf-8 -*-
"""
市场温度模块常量集中定义

将分散在 fetchers 中的 URL、请求头、阈值等"魔法值"统一抽到此处，
避免在多处重复书写、便于维护。
"""

from enum import Enum
from typing import Dict

from app.core.utils import to_float as _to_float


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


# ─── 本地缓存（统一走 app.core.cache.CacheService，#1537）───
# 命名空间与键名集中在此：CacheService 的落盘文件名是 `cache_{namespace}_{key}.pkl`，
# 改名等于换缓存（旧文件成孤儿、首跑重算一次），故不要散落到 fetcher 里。
THERMOMETER_CACHE_NAMESPACE = 'thermometer'
# 自算估值分位（股债利差）：akshare 侧 CPI 历史约 19 页顺序下载、单次 20+ 秒，
# 而数据日内变化极小——缓存 12 小时可大幅缩短同步耗时。
SELF_CALC_CACHE_KEY = 'self_calc'
SELF_CALC_CACHE_TTL = 12 * 3600


# ─── 标签阈值函数（集中管理"魔法数字"）───
def label_volume(total: float) -> str:
    """全市场成交额定性标签。"""
    return '放量' if total > 12000 else ('缩量' if total < 8000 else '温和')


# ─── 数据新鲜度守卫（#1431）───
# 温度类数据的最新 collected_at 距今超过该天数即视为「陈旧」，前端须显式提示，
# 不允许静默展示旧快照。取 5 天以容纳周末 + 单个节假日。
FRESHNESS_THRESHOLD_DAYS = 5


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
