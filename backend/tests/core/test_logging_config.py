# -*- coding: utf-8 -*-
"""#1551 回归测试：loguru 文件日志落盘配置。

背景：批跑出问题时唯一现场是 CMD 窗口的滚动输出，窗口一关证据就没了
（#1550 的 fund_nav 货基去重缺陷因此静默一个月）。本模块给 stderr 之外
再加一路「按天轮转 + 保留 7 天」的文件 sink。

这里只断言**我们自己决定的那部分**（目录解析、级别、保留天数、开关、文件名、
写盘内容）；「7 天的文件到底怎么删」是 loguru 的职责，不越界替它测。
"""

import os
import subprocess
import sys
import textwrap
from datetime import timedelta
from pathlib import Path

import pytest
from loguru import logger

from app.core import logging_config
from app.core.time_utils import now_shanghai, today_shanghai


@pytest.fixture(autouse=True)
def _clean_sink():
    """每个用例前后都摘掉文件 sink，避免污染其他用例（写文件 + 改全局状态）"""
    logging_config.reset_for_tests()
    yield
    logging_config.reset_for_tests()


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    """把日志目录指到用例私有 tmp，并强制打开 sink。

    必须显式 `LOG_ENABLED=1`：pytest 进程默认不落盘（见 `_in_test_process`），
    否则本文件的用例会全部拿到 None。
    """
    directory = tmp_path / 'logs'
    monkeypatch.setenv('LOG_DIR', str(directory))
    monkeypatch.setenv('LOG_ENABLED', '1')
    monkeypatch.delenv('LOG_LEVEL', raising=False)
    monkeypatch.delenv('LOG_RETENTION_DAYS', raising=False)
    return directory


def test_setup_is_idempotent(log_dir):
    """重复调用不得重复挂载 sink（app 包可能被多次导入）"""
    first = logging_config.setup_file_logging()
    second = logging_config.setup_file_logging()

    assert first is not None
    assert first == second


def test_log_lines_land_on_disk_with_cmd_identical_format(log_dir):
    """写盘内容与 CMD 一致：时间 / 级别 / 模块:函数:行号 都在"""
    logging_config.setup_file_logging()
    logger.info('批跑排查用标记 1551')
    logger.complete()  # enqueue=True 是异步写，必须冲刷才能断言

    files = list(log_dir.glob('fundmate_*.log'))
    assert len(files) == 1, f'应产出当日单个日志文件，实际 {files}'
    assert files[0].name == f'fundmate_{today_shanghai():%Y-%m-%d}.log'

    content = files[0].read_text(encoding='utf-8')
    assert '批跑排查用标记 1551' in content
    assert '| INFO' in content
    assert 'test_logging_config' in content  # name:function:line 段


def test_default_policy_is_daily_rotation_and_seven_days(log_dir, monkeypatch):
    """保留 7 天 + 每日 00:00 轮转 —— 这是对外承诺的口径，改动必须让测试红"""
    monkeypatch.setenv('LOG_RETENTION_DAYS', '7')
    assert logging_config.setup_file_logging() is not None

    assert logging_config.DEFAULT_ROTATION == '00:00'
    assert logging_config.retention_days() == 7
    assert logging_config.DEFAULT_RETENTION_DAYS == 7
    assert logging_config.log_level() == 'DEBUG'  # 批跑排查要看到 HTTP / 重试细节


def test_default_log_dir_is_backend_logs(log_dir, monkeypatch):
    """未设 LOG_DIR 时落 backend/logs（与 cwd 无关，不能落到用户桌面或仓库根）"""
    monkeypatch.delenv('LOG_DIR', raising=False)

    assert logging_config.log_dir() == logging_config.BACKEND_DIR / 'logs'
    assert logging_config.log_dir().name == 'logs'


def test_log_enabled_zero_disables_sink(log_dir, monkeypatch):
    """LOG_ENABLED=0 时整体关闭（CI / 临时排查），且不创建目录"""
    monkeypatch.setenv('LOG_ENABLED', '0')

    assert logging_config.setup_file_logging() is None
    assert not log_dir.exists()


def test_test_process_does_not_write_logs_by_default(tmp_path, monkeypatch):
    """pytest 进程默认不落盘：否则跑一遍测试就往仓库里写 DEBUG 噪音并霸占 7 天窗口"""
    monkeypatch.delenv('LOG_ENABLED', raising=False)
    monkeypatch.setenv('LOG_DIR', str(tmp_path / 'logs'))

    assert logging_config._in_test_process() is True  # 本用例本身就跑在 pytest 里
    assert logging_config.setup_file_logging() is None
    assert not (tmp_path / 'logs').exists()


def test_invalid_retention_falls_back_to_default(log_dir, monkeypatch):
    """非法 / 越界的 retention 不得让配置炸掉，回落默认值"""
    monkeypatch.setenv('LOG_RETENTION_DAYS', '不是数字')
    assert logging_config.retention_days() == logging_config.DEFAULT_RETENTION_DAYS

    monkeypatch.setenv('LOG_RETENTION_DAYS', '0')
    assert logging_config.retention_days() == logging_config.DEFAULT_RETENTION_DAYS


def test_unwritable_dir_does_not_break_startup(tmp_path, monkeypatch):
    """日志目录不可写时只降级为一行警告，绝不拦住应用启动

    构造真实故障态：把 LOG_DIR 指到一个**已存在的文件**上，
    `mkdir(parents=True, exist_ok=True)` 会抛 FileExistsError（OSError 子类）。
    """
    blocker = tmp_path / 'not-a-dir'
    blocker.write_text('占位文件', encoding='utf-8')
    monkeypatch.setenv('LOG_DIR', str(blocker / 'logs'))

    assert logging_config.setup_file_logging() is None


# ── 进程时区不变式（#1805）──────────────────────────────────────────────────
# 为什么原先的测试抓不住这个 bug（也是它活了很久的原因）：
#  1) 唯一沾边的断言是 `test_log_lines_land_on_disk_with_cmd_identical_format` 里的
#     「日志文件名日期 == today_shanghai() 日期」。它**只在上海 00:00–08:00 有效**：
#     本地时区被弄成 UTC 时，只有那个窗口内日期才会错一天，其余 16 小时恒绿；
#  2) 更是**平台实现依赖**的：Windows 无 `time.tzset`，CRT 一旦缓存过本地时区，
#     `TZ` 的改动就不再生效；而 pytest 进程自身早就取过本地时间，于是 bug 在测试进程内
#     根本不可见（真跑到应用新进程才现形）。
# 下面两条断言与「几点跑」「在哪个平台跑」都无关。

_BACKEND_DIR = Path(__file__).resolve().parents[2]

# 子进程脚本：**进程第一步**就设 TZ（值由父进程经 argv 传入），再比本地时间与上海时间。
# 刻意不让子进程自己去 import app：import 过程会先取本地时间，CRT 缓存后 TZ 就失效了
# ——那正是这个缺陷在测试里「隐身」的机制。
_TZ_PROBE = textwrap.dedent(
    """
    import datetime
    import os
    import sys
    import time

    os.environ['TZ'] = sys.argv[1]
    if hasattr(time, 'tzset'):
        time.tzset()

    local = datetime.datetime.now().replace(tzinfo=None)
    utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    shanghai = utc + datetime.timedelta(hours=8)
    print(int(abs((local - shanghai).total_seconds())))
    """
)


def _tz_probe_drift(tz_name: str) -> int:
    """在全新解释器里「先设 TZ 再取本地时间」，返回与上海时间的偏差秒数。"""
    env = {k: v for k, v in os.environ.items() if k != 'TZ'}
    proc = subprocess.run(
        [sys.executable, '-c', _TZ_PROBE, tz_name],
        cwd=str(_BACKEND_DIR),
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    assert proc.returncode == 0, f'子进程失败：{proc.stderr}'
    return int(proc.stdout.strip().splitlines()[-1])


def test_platform_tz_name_means_shanghai_on_this_platform():
    """写进 `TZ` 的时区串必须被当前平台解析成 UTC+8（#1805）。

    Windows 的 MSVCRT 只认 POSIX 形式：喂它 IANA 名 `Asia/Shanghai` 会解析失败并
    **静默回退 UTC**（实测偏差 28800s）。本断言在 Windows 上对旧实现必红，
    在 POSIX 上（IANA + tzset）同样通过——即「用对平台写法」这一契约。
    """
    tz_name = logging_config.resolve_tz_name()
    drift = _tz_probe_drift(tz_name)
    assert drift < 60, (
        f'TZ={tz_name!r} 在本平台得到的本地时间与上海差 {drift}s：Windows 上不能用 IANA 名'
        f'（MSVCRT 会回退 UTC），应写 POSIX 形式 {logging_config.SHANGHAI_TZ_POSIX!r}'
    )


def test_local_time_drift_helper_reports_hour_level_skew(monkeypatch):
    """启动自检用的偏差助手：整小时级错位必须被算出来（#1805）"""
    frozen = now_shanghai().replace(tzinfo=None) - timedelta(hours=7)

    class _FrozenDatetime:
        @staticmethod
        def now():
            return frozen

    monkeypatch.setattr(logging_config, 'datetime', _FrozenDatetime)

    assert logging_config.local_time_drift_seconds() == pytest.approx(7 * 3600, abs=1)


def test_local_time_is_shanghai_in_this_process():
    """对齐后，本进程的本地时间即上海时间（正常环境必须为 0 偏差）"""
    logging_config._align_process_timezone_to_shanghai()

    assert logging_config.local_time_drift_seconds() < logging_config.TIME_SKEW_TOLERANCE_SECONDS
