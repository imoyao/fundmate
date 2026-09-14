# -*- coding: utf-8 -*-
"""集思录会话（Cookie）自检与保活（#1400）。

集思录没有开放 API；登录态靠浏览器 Cookie（`kbzw__user_login` 长效 token +
`kbzw__Session` 会话级）。**程序化登录不可取**：需过验证码，且账号/密码字段有 JS
加密（社区通行做法是 Selenium 驱动真实浏览器），成本与风险（存密码、验证码识别）
都高于收益。

故本项目采用**「自检 + 定时触碰」保活**：
- 定时（建议每日、带 jitter）调用 `check_jsl_cookie()`；
- 有效 → 记 INFO，同时产生一次带登录态的访问（等同 keep-alive）；
- 失效 → 记 WARNING，提示重新复制 Cookie 到 JSL_COOKIE。

配套命令：
    pdm run python -m scripts.check_jsl_cookie     # 手工自检
    pdm run scheduler --check-jsl                  # 定时自检（可挂 cron，建议带 --jitter）
"""

import os
import time
from dataclasses import dataclass
from typing import Optional

import requests
from loguru import logger

from app.core.requests_patch import install_requests_patch

JSL_LIST_URL = 'https://www.jisilu.cn/data/cbnew/cb_list_new/'

# 与 akshare bond_cb_jsl 同构的 payload；rp 取大值以一次拿全（登录态下不受 30 条游客限制）
_JSL_PAYLOAD = {
    'fprice': '',
    'tprice': '',
    'curr_iss_amt': '',
    'volume': '',
    'svolume': '',
    'premium_rt': '',
    'ytm_rt': '',
    'market': '',
    'rating_cd': '',
    'is_search': 'N',
    'btype': '',
    'listed': 'Y',
    'qflag': 'N',
    'sw_cd': '',
    'bond_ids': '',
    'rp': '1000',
    'page': '1',
}

_JSL_HEADERS = {
    'accept': 'application/json, text/javascript, */*; q=0.01',
    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'origin': 'https://www.jisilu.cn',
    'referer': 'https://www.jisilu.cn/data/cbnew/',
    'user-agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36'
    ),
    'x-requested-with': 'XMLHttpRequest',
}


@dataclass
class JslCookieStatus:
    """Cookie 健康状态。"""

    present: bool  # 是否配置了 JSL_COOKIE
    cookie_len: int
    ok: bool  # 是否被识别为已登录
    rows: int = 0
    total: Optional[int] = None
    warn: str = ''
    error: Optional[str] = None

    @property
    def summary(self) -> str:
        if self.error:
            return f'请求失败: {self.error}'
        if not self.present:
            return '未配置 JSL_COOKIE'
        if self.ok:
            return f'已登录，返回 {self.rows} 条转债（全量 {self.total}）'
        return f'仍为游客口径（{self.rows}/{self.total}），cookie 失效，需重新复制'


def check_jsl_cookie(cookie: Optional[str] = None, timeout: int = 25) -> JslCookieStatus:
    """探测 JSL_COOKIE 是否仍被集思录识别为已登录。

    判定口径：**只有服务端明确提示「游客」才算失效**——不能用 `rows < total`
    （`listed='Y'` 过滤下 313/315 属正常，未上市/退市不返回）。
    """
    install_requests_patch()
    cookie = cookie if cookie is not None else os.getenv('JSL_COOKIE')
    if not cookie:
        return JslCookieStatus(present=False, cookie_len=0, ok=False)

    headers = dict(_JSL_HEADERS, cookie=cookie)
    params = {'___jsl': f'LST___t={int(time.time() * 1000)}'}
    try:
        resp = requests.post(JSL_LIST_URL, params=params, json=_JSL_PAYLOAD, headers=headers, timeout=timeout)
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        return JslCookieStatus(present=True, cookie_len=len(cookie), ok=False, error=str(e))

    rows = data.get('rows') or []
    warn = str(data.get('warn') or '')
    return JslCookieStatus(
        present=True,
        cookie_len=len(cookie),
        ok='游客' not in warn,
        rows=len(rows),
        total=data.get('all'),
        warn=warn,
    )


def keepalive_jsl_session() -> JslCookieStatus:
    """保活：跑一次自检（带登录态访问），并按结果记日志。"""
    status = check_jsl_cookie()
    if status.ok:
        logger.info(f'[JSL] 保活检查通过：{status.summary}')
    else:
        logger.warning(f'[JSL] 保活检查失败：{status.summary}（请重新登录集思录并更新 JSL_COOKIE）')
    return status
