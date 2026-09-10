# -*- coding: utf-8 -*-
"""集思录 Cookie 自检（#1400）。

一条命令判断 `JSL_COOKIE` 是否仍被集思录识别为**已登录**，避免
「可转债同步回来只有 30 条」时不知原因。

集思录登录态由 `kbzw__user_login`（长效「记住我」token）承担，
`kbzw__Session` 仅会话级；token 在同账号重新登录/退出时会被轮换失效。

用法（在 backend 目录；-m 以便 cwd 进入 sys.path）：
    pdm run python -m scripts.check_jsl_cookie

退出码：0=有效；1=未配置；2=已失效；3=请求失败
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.services.jsl_session import check_jsl_cookie

# 显式加载 backend/.env：app 包的 load_dotenv 在函数内（仅 import 包不会触发），
# 独立脚本必须自己加载，否则 os.getenv 恒为空。
# 放在 import 之后调用即可——check_jsl_cookie 是「调用期」读环境变量。
load_dotenv(Path(__file__).resolve().parents[1] / '.env')


def main() -> int:
    status = check_jsl_cookie()
    print(f'[1] JSL_COOKIE 已配置: {status.present}，长度: {status.cookie_len}')
    if not status.present:
        print('[FAIL] 未配置 JSL_COOKIE（写入 backend/.env 后重试）')
        return 1
    if status.error:
        print(f'[FAIL] 请求集思录失败: {status.error}')
        return 3

    print(f'[2] 返回条数: {status.rows}，全量(上市): {status.total}')
    print(f'[3] 服务端提示: {json.dumps(status.warn, ensure_ascii=True)}')

    if not status.ok:
        print('[WARN] 仍为游客口径 → cookie 未被识别为已登录。')
        print('       处理：浏览器登录集思录（勾选记住我）→ F12 Network → 复制任意')
        print('       jisilu.cn 请求 Request Headers 里的整行 cookie → 覆盖 JSL_COOKIE。')
        return 2

    print(f'[OK] cookie 有效：{status.summary}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
