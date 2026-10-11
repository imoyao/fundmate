# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/9
# File : data_sources.py
# app/core/data_sources.py
"""数据来源的**对外表述**（#1969）。

用户看不懂 `price_history` / `daily_worth` / `akshare_sina` —— 那是我们的表名和抓取
管线内部码。详情页脚注要回答的是「这些数字最终来自哪个网站」，所以来源必须先映射成
站点名再上屏。

为什么收在 core 而不是各 service 各写一份：同一个来源会同时出现在走势、区间行情、
资料三个区块（#1967/#1968/#1969），各写一份必然漂移，改一次要改 N 处。

口径说明与来源**分开**：来源回答「哪来的」，口径回答「怎么算的」（前复权收盘价 /
未复权高低 / 单位净值）。两者都由后端给，前端只负责排版——否则前端要维护一份
「close 对应前复权」这类业务知识，那是后端的事。
"""

from __future__ import annotations

# 内部来源码 → 面向用户的站点名。
# 取值来源：price_history.source（实测库内为 akshare_sina 11246 / akshare_em 1959 /
# akshare 3）、各 adapter 的落库 source、以及无 source 列时按同步链路指定的固定来源。
DATA_SOURCE_LABELS: dict[str, str] = {
    # 场内日线（akshare_adapter.fetch_stock_price）
    'akshare_sina': '新浪财经',  # ak.stock_zh_a_daily / bond_zh_hs_cov_daily
    'akshare_em': '东方财富',  # ak.fund_etf_hist_em
    'akshare_spot': '东方财富',  # ak.stock_zh_a_spot_em（当日实时兜底）
    'akshare': 'AKShare',  # 早期/未细分来源的存量行
    # 指数与名录
    'sina': '新浪财经',
    'csindex': '中证指数',
    'cni': '国证指数',
    # 可转债与公告
    'akshare_jsl': '集思录',
    'akshare_bond_zh_cov': '集思录',
    'akshare_cninfo': '巨潮资讯',
    'akshare_fund_ann': '东方财富',
    # 场外基金净值（xalpha → 天天基金 pingzhongdata / lsjz）
    'xalpha': '天天基金',
}

# 场外基金净值的来源：`daily_worth` 表**没有 source 列**，净值整条链路都由
# xalpha 走天天基金（`fund.eastmoney.com/pingzhongdata/{code}.js` 与 `f10/lsjz`），
# 故这里给常量而非查列。
FUND_NAV_SOURCE_LABEL = '天天基金'


def data_source_label(code: str | None) -> str:
    """内部来源码 → 站点名。

    未收录的码**原样返回**而不是换成「未知」：库里出现新来源码时，宁可让排查的人
    直接看到 `akshare_xxx`，也不要用一个笼统词把线索抹掉。
    """
    raw = (code or '').strip()
    if not raw:
        return ''
    return DATA_SOURCE_LABELS.get(raw, raw)
