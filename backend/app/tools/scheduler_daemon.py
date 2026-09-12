# -*- coding: utf-8 -*-
# app/tools/scheduler_daemon.py
"""本机常驻的每日调度**守护进程**入口（#1467）。

与「应用内启动」（`SCHEDULER_ENABLED=1` 时由 `create_app()` 起调度）等价，只是把宿主
换成独立进程：适合「不打开 Web 应用也想每天更新数据」的场景（例如前端只当查看器）。

同一台机器上两者**只会有一个真正生效**——单实例锁（`data/daily_scheduler.lock`）在
`app/services/daily_scheduler.py` 里，先到先得，后者只会在日志里说明一句就退出。

用法:
    pdm run scheduler-daemon           # 常驻，Ctrl+C 退出
    pdm run scheduler-daemon --force   # 忽略 SCHEDULER_ENABLED 开关，强制常驻

退出码:
    0  正常退出（Ctrl+C / 收到终止信号）
    1  未能启动（开关未开 / 锁被其它进程持有 / 启动异常）
"""

import argparse
import signal
import sys
import threading
from dataclasses import replace
from pathlib import Path

# 将 backend/ 加入 Python 路径 —— 必须在 import app 之前（同 sync_cli / scheduler）
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from loguru import logger  # noqa: E402

from app.core.database import init_db  # noqa: E402
from app.services.daily_scheduler import (  # noqa: E402
    load_config,
    shutdown_daily_scheduler,
    start_daily_scheduler,
)

# 守护进程不经过 Flask 应用工厂，必须自己保证「全量表集合已注册」再 init_db()，
# 否则跨域外键解析失败或表静默缺失（daily_scheduler 模块顶部已集中导入全部域模型，
# 本文件 import 它即完成注册——此处不做重复导入，避免两份清单漂移）。


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='多多贝本机常驻每日调度守护进程')
    parser.add_argument(
        '--force',
        action='store_true',
        help='忽略 SCHEDULER_ENABLED 开关，强制启动（显式跑本命令即视为要开）',
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    # 显式指定 backend/.env：从任意工作目录（计划任务 / 快捷方式）启动都能读到配置
    load_dotenv(BACKEND_DIR / '.env')
    args = _parse_args(argv)

    config = load_config()
    if args.force and not config.enabled:
        config = replace(config, enabled=True)
        logger.info('已按 --force 覆盖 SCHEDULER_ENABLED')

    init_db()

    scheduler = start_daily_scheduler(config)
    if scheduler is None:
        logger.error(
            '调度器未启动（开关未开 / 单实例锁被其它进程持有 / 测试或 CI 环境）。'
            '用 `pdm run scheduler --status` 查看原因。'
        )
        return 1

    stop = threading.Event()

    def _on_signal(signum, _frame):  # noqa: ANN001 - signal handler 签名固定
        logger.info(f'收到信号 {signum}，准备退出常驻调度')
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError, AttributeError):  # pragma: no cover - 非主线程/平台差异
            logger.debug(f'信号 {sig} 无法注册，忽略')

    logger.info('每日调度守护进程已就绪（Ctrl+C 退出）')
    try:
        while not stop.wait(1):
            pass
    finally:
        shutdown_daily_scheduler(wait=False)
        logger.info('每日调度守护进程已退出')
    return 0


if __name__ == '__main__':
    sys.exit(main())
