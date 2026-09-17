# -*- coding: utf-8 -*-
"""#1551 回归测试：loguru 文件日志落盘配置。

背景：批跑出问题时唯一现场是 CMD 窗口的滚动输出，窗口一关证据就没了
（#1550 的 fund_nav 货基去重缺陷因此静默一个月）。本模块给 stderr 之外
再加一路「按天轮转 + 保留 7 天」的文件 sink。

这里只断言**我们自己决定的那部分**（目录解析、级别、保留天数、开关、文件名、
写盘内容）；「7 天的文件到底怎么删」是 loguru 的职责，不越界替它测。
"""

import pytest
from loguru import logger

from app.core import logging_config
from app.core.time_utils import today_shanghai


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
