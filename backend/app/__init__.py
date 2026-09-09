# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/8 21:08
# File : __init__.py.py

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# 导入形态对齐：本包内全部使用 `from app.xxx` 顶级绝对导入，要求顶级包名
# 必须是 app（标准启动：cwd=backend + flask --app app.main:app，见 AGENTS.md）。
# 若以 backend.app 等子包形态被导入（如 --app backend.app.main、IDE 运行配置
# Working Directory 指向仓库根），此处把运行环境自动对齐标准形态：
#   1. backend 目录注入 sys.path；
#   2. 把本模块别名注册为顶级 'app'——sys.modules 两个键指向**同一个**
#      包对象，后续 `from app.xxx` 命中同一份包，不会产生双份 Base/engine
#      的状态分裂（这正是不能简单「import 重载自愈」的原因）；
#   3. chdir 到 backend 并加载 backend/.env（对齐 sqlite 相对路径与环境变量）。
# 标准形态（__name__ == 'app'）整块短路，零开销。
if __name__ != 'app':
    _BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
    if _BACKEND_DIR not in sys.path:
        sys.path.insert(0, _BACKEND_DIR)
    sys.modules['app'] = sys.modules[__name__]
    os.chdir(_BACKEND_DIR)
    load_dotenv(os.path.join(_BACKEND_DIR, '.env'))
    logging.getLogger(__name__).warning(
        'app 包以子包形态（%s）被导入，已自动对齐标准形态（sys.path/cwd/.env）。'
        '建议改用标准启动：cd backend && pdm run flask --app app.main:app run --debug',
        __name__,
    )

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
