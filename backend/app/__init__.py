# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/8 21:08
# File : __init__.py.py

import logging

# 导入形态守卫：本包内全部使用 `from app.xxx` 顶级绝对导入，要求 `app` 必须是
# 顶级包（标准启动：cwd=backend + flask --app app.main:app，见 AGENTS.md）。
# 若以 backend.app 等子包形态被导入（如从仓库根 `--app backend.app.main` 启动），
# 顶级 app 不存在，后续导入必然 ModuleNotFoundError 且 traceback 极其迷惑
# （2026-09-09 实测：/api/watchlist/items/ 全量 500）。
# 不在此做 sys.path 自愈：那会让 backend.app 与 app 两份包对象并存（双份
# Base/engine，状态分裂），比启动失败更隐蔽。故快速失败并给出指引。
if __name__ != 'app':
    raise ImportError(
        f'app 包被以子包形态导入（{__name__}），顶级包 app 不存在，无法继续。'
        '唯一标准启动方式：cd backend && pdm run flask --app app.main:app run --debug'
        '（仓库根可执行 dev.cmd，其内部已切到 backend；见 AGENTS.md / scripts/dev.ps1）。'
        'IDE 运行配置请把 Working Directory 设为 backend/、启动目标设为 app.main。'
    )

from loguru import logger

# 全局请求补丁：进程启动时让所有 akshare/requests 调用自动走「浏览器头 + 连接复用 + 重试」会话，
# 缓解东方财富按 IP 限流/临时封导致的 RemoteDisconnected（详见 app/core/requests_patch.py；根因仍待退出代理后 diag 验收）。
from app.core.requests_patch import install_requests_patch

install_requests_patch()

# akshare 全局限速配置（request_interval=3 / use_thread=False）已下沉到
# app.core.akshare_lazy.get_akshare()，在首次真正使用 akshare 时才加载并应用，
# 避免应用启动期就 import akshare（约 3s），从而加快 flask reloader 的重载速度。


class InterceptHandler(logging.Handler):
    """将标准库 logging 日志转发到 loguru"""

    def emit(self, record: logging.LogRecord) -> None:
        # 获取 loguru 对应的日志级别，如果找不到则直接使用数字级别
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        # 将异常信息、调用栈等附加信息一并传递
        logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())


# 挂载拦截器：把第三方库（werkzeug/urllib3/akshare 等）经 stdlib logging 产生的日志
# 统一接入 loguru，避免与业务日志分家。此前 InterceptHandler 仅定义未挂载，属历史遗漏。
# force=True 覆盖可能存在的默认 root handler；进程启动时执行一次，重复 import 幂等。
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
