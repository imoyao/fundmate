# app/core/logging_config.py
"""loguru 文件日志落盘（#1551）。

**WHY**：批跑（本机常驻调度 / `pdm run sync` CLI）出问题时，唯一现场是那扇 CMD
窗口的滚动输出——窗口一关，证据就没了。#1550 的 `fund_nav` 货基去重缺陷正因此
静默了整整一个月：失败只活在控制台里，`sync_logs` 审计表和磁盘上都没有痕迹。

本模块在 loguru 默认的 stderr sink **之外**再加一路「按天轮转 + 保留 N 天」的
文件 sink，由 `app/__init__.py` 调用一次即可覆盖全部入口——Flask dev server、
`pdm run sync --job`、`pdm run scheduler-daemon`、`pdm run invoke grab.*`
都要经过 `import app`，不需要每个入口各写一遍。

**刻意不做 `logger.remove()`**：前台可见性不退化，文件只是多一份留档。

**默认不在 pytest 进程里落盘**：`tests/conftest.py` 的 `app` fixture 每个用例都调
`create_app()`，而 `import app` 一个进程只发生一次——不拦的话，测试跑一遍就会把 DEBUG
级噪音写进 `backend/logs/` 并霸占 7 天保留窗口。需要时用 `LOG_ENABLED=1` 强制打开。

**已知限制（多进程）**：本机可能同时有两个进程写同一份日志（dev server 与
`scheduler-daemon`；`backend/data/daily_scheduler.lock` 只保证**调度**不重复，
不保证**进程**唯一）。文件名带 `{process.id}` 能让两进程各写各的，但 loguru 的
retention 清理是按「文件名里的时间占位符」生成 glob 的，多一个占位符就清不掉旧文件。
两者只能取一，此处选**保留策略可用**，代价是跨零点轮转存在竞态（最坏情况是某次
rename 失败并打一行错误日志）。详见 `docs/dev/scheduler-tasks.md`。
"""

import os
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

# backend/ 目录：app/core/logging_config.py -> app/core -> app -> backend
BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_LOG_DIR = BACKEND_DIR / 'logs'

# 轮转：每日 00:00。批跑是「一天一批」的节奏，按天切文件最贴合排查习惯
# （「上周三那批为什么失败」= 直接翻那天的文件），也天然给出 7 个文件的上界。
DEFAULT_ROTATION = '00:00'
DEFAULT_RETENTION_DAYS = 7  # 用户口径：批跑问题回溯一周够用
DEFAULT_LEVEL = 'DEBUG'

# 与 loguru 默认格式保持逐字一致：文件里看到的行 = CMD 里看到的行，
# 排查时不必在两套格式之间换算。
LOG_FORMAT = '{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}'

_TRUTHY = {'0', 'false', 'no', 'off'}

# 已挂载的 sink id（幂等标记）。函数级 global 而非模块级常量：测试需要重置。
_sink_id: Optional[int] = None


def _in_test_process() -> bool:
    """当前是否 pytest 进程。

    与 `daily_scheduler._in_test_process()` 同一判据、同一理由（那边是「别拉起后台线程」，
    这边是「别往仓库里写日志」）：`tests/conftest.py` 的 `app` fixture 每个用例都调
    `create_app()`，`import app` 只发生一次，于是文件 sink 会在测试进程里挂上，
    把 DEBUG 级测试噪音写进 `backend/logs/` 并霸占 7 天保留窗口。
    `PYTEST_CURRENT_TEST` 只在测试运行期存在，故同时看 `pytest` 是否已进 `sys.modules`。
    """
    return 'pytest' in sys.modules or 'PYTEST_CURRENT_TEST' in os.environ


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    """读正整数环境变量；缺失/非法/越界一律回落 default"""
    raw = os.getenv(name, '').strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning(f'环境变量 {name}={raw!r} 不是整数，回落默认值 {default}')
        return default
    if value < minimum:
        logger.warning(f'环境变量 {name}={value} 小于 {minimum}，回落默认值 {default}')
        return default
    return value


def log_dir() -> Path:
    """日志目录：`LOG_DIR` 优先（相对路径按当前工作目录解析），否则 `backend/logs`"""
    raw = os.getenv('LOG_DIR', '').strip()
    return Path(raw) if raw else DEFAULT_LOG_DIR


def log_level() -> str:
    """文件 sink 级别：`LOG_LEVEL`（默认 DEBUG，批跑排查需要看到 HTTP 与重试细节）"""
    return os.getenv('LOG_LEVEL', '').strip().upper() or DEFAULT_LEVEL


def retention_days() -> int:
    """日志保留天数：`LOG_RETENTION_DAYS`（默认 7）"""
    return _int_env('LOG_RETENTION_DAYS', DEFAULT_RETENTION_DAYS)


def setup_file_logging() -> Optional[int]:
    """挂载文件 sink（幂等）。返回 sink id；被禁用或目录不可写时返回 None。

    - `LOG_ENABLED=0` 时整体关闭；
    - 测试进程里默认不落盘（见 `_in_test_process`），显式 `LOG_ENABLED=1` 可强制打开；
    - 目录不可写**不抛异常**：日志配置失败不该拦住应用启动，降级为一行警告。
    """
    global _sink_id

    explicit = os.getenv('LOG_ENABLED', '').strip().lower()
    if explicit in _TRUTHY:
        return _sink_id
    if not explicit and _in_test_process():
        return None
    if _sink_id is not None:
        return _sink_id

    directory = log_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning(f'日志目录不可用，跳过文件日志：{directory}（{exc}）')
        return None

    try:
        _sink_id = logger.add(
            str(directory / 'fundmate_{time:YYYY-MM-DD}.log'),
            level=log_level(),
            format=LOG_FORMAT,
            rotation=DEFAULT_ROTATION,
            retention=f'{retention_days()} days',
            compression='zip',  # DEBUG 级一天几十 MB，压缩后约 1/10
            encoding='utf-8',
            enqueue=True,  # 调度器在 APScheduler 线程里跑 job，必须线程安全
        )
    except Exception as exc:  # noqa: BLE001 - 日志配置失败不得拦住启动
        logger.warning(f'文件日志挂载失败（已降级为仅 stderr）：{exc}')
        return None

    logger.info(f'文件日志已启用：{directory}｜级别={log_level()}｜每日轮转｜保留 {retention_days()} 天')
    return _sink_id


def reset_for_tests() -> None:
    """移除已挂载的文件 sink 并清空幂等标记（仅测试使用）"""
    global _sink_id
    if _sink_id is not None:
        try:
            logger.complete()  # 冲刷 enqueue 队列，避免残留写入落到已删文件
        except Exception:  # noqa: BLE001 - 测试清理不得影响用例结果
            pass
        logger.remove(_sink_id)
        _sink_id = None
