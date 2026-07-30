# -*- coding: utf-8 -*-
"""
市场温度模块常量集中定义

将分散在 fetchers 中的 URL、请求头、阈值等"魔法值"统一抽到此处，
避免在多处重复书写、便于维护。
"""

from typing import Dict

# ─── 东财：全市场成交额 ───
EASTMONEY_BOARDS: Dict[str, str] = {
    '上证': '1.000001',
    '深证': '0.399001',
    '北证': '0.899050',
}
EASTMONEY_HOSTS = ['push2.eastmoney.com', 'push2delay.eastmoney.com']
EASTMONEY_REFERER = 'https://quote.eastmoney.com/'

# ─── 集思录 ───
JISILU_CB_URL = 'https://www.jisilu.cn/data/indicator/get_cb_temperature/'
JISILU_INDICATOR_URL = 'https://www.jisilu.cn/data/indicator/get_last_indicator/'
JISILU_REFERER = 'https://www.jisilu.cn/data/indicator/'

# ─── 且慢 MCP（Streamable HTTP）───
QIEMAN_MCP_URL = 'https://stargate.yingmi.com/mcp/v2'
QIEMAN_PROTOCOL_VERSION = '2024-11-05'
QIEMAN_CLIENT_INFO = {'name': 'fundmate', 'version': '1.0.0'}
QIEMAN_TOOL = 'GetLatestQuotations'

# ─── 有知有行 ───
YOUZHIYOUXING_URL = 'https://youzhiyouxing.cn/thermometer'

# ─── 韭圈儿 ───
JIUCASHUO_URL = 'https://app.jiucaishuo.com/'

# ─── 概览链接（展示用）───
LINKS = {
    'qieman': 'https://qieman.com/',
    'youzhiyouxing': 'https://youzhiyouxing.cn/thermometer',
    'jisilu': 'https://www.jisilu.cn/data/indicator/',
    'jiucaishuo': 'https://app.jiucaishuo.com/',
    'eastmoney': 'https://quote.eastmoney.com/',
}


# ─── 标签阈值函数（集中管理"魔法数字"）───
def label_volume(total: float) -> str:
    """全市场成交额定性标签。"""
    return '放量' if total > 12000 else ('缩量' if total < 8000 else '温和')


def label_temp(value: float) -> str:
    """温度定性标签（可转债温度等）。"""
    return '偏高' if value > 70 else ('适中' if value > 40 else '偏低')


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
