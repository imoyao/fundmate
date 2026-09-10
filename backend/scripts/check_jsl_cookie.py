# -*- coding: utf-8 -*-
"""集思录 Cookie 自检（#1400）。

一条命令判断 `JSL_COOKIE` 是否仍被集思录识别为**已登录**，避免
「可转债同步回来只有 30 条」时不知原因。

集思录登录态由 `kbzw__user_login`（长效「记住我」token）承担，
`kbzw__Session` 仅会话级；token 在同账号重新登录/退出时会被轮换失效。

用法（在 backend 目录；-m 以便 cwd 进入 sys.path）：
    pdm run python -m scripts.check_jsl_cookie

输出：
    [1] cookie 是否存在与长度
    [2] 实际返回条数 / 全量条数
    [3] 服务端提示（游客 或 正常）
    → 判定 cookie 是否有效
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from app.core.requests_patch import install_requests_patch

# 显式加载 backend/.env：app 包的 load_dotenv 在函数内（仅 import 包不会触发），
# 独立脚本必须自己加载，否则 os.getenv 恒为空。
load_dotenv(Path(__file__).resolve().parents[1] / '.env')

URL = 'https://www.jisilu.cn/data/cbnew/cb_list_new/'
PAYLOAD = {
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


def main() -> int:
    # 触发 app 包初始化（含 backend/.env 加载），并给 requests 打上统一补丁
    install_requests_patch()

    cookie = os.getenv('JSL_COOKIE')
    label = bool(cookie)
    print(f'[1] JSL_COOKIE 已配置: {label}，长度: {len(cookie or "")}')
    if not cookie:
        print('[FAIL] 未配置 JSL_COOKIE（写入 backend/.env 后重试）')
        return 1

    headers = {
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'cookie': cookie,
        'origin': 'https://www.jisilu.cn',
        'referer': 'https://www.jisilu.cn/data/cbnew/',
        'user-agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36'
        ),
        'x-requested-with': 'XMLHttpRequest',
    }
    params = {'___jsl': f'LST___t={int(time.time() * 1000)}'}

    try:
        resp = requests.post(URL, params=params, json=PAYLOAD, headers=headers, timeout=25)
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        print(f'[FAIL] 请求集思录失败: {e}')
        return 1

    rows = data.get('rows', [])
    total = data.get('all')
    warn = str(data.get('warn') or '')
    print(f'[2] 返回条数: {len(rows)}，全量(上市): {total}')
    print(f'[3] 服务端提示: {json.dumps(warn, ensure_ascii=True)}')

    # 判定口径：只有服务端明确提示"游客"才算未登录。
    # 不能用 len(rows) < total —— listed='Y' 过滤下 313/315 属正常（未上市/退市不返回）。
    if '游客' in warn:
        print('[WARN] 仍为游客口径 → cookie 未被识别为已登录。')
        print('       处理：浏览器登录集思录（勾选记住我）→ F12 Network → 复制任意')
        print('       jisilu.cn 请求 Request Headers 里的整行 cookie → 覆盖 JSL_COOKIE。')
        return 2

    print(f'[OK] cookie 有效：已登录，返回 {len(rows)} 条转债（全量 {total}）。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
