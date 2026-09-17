# -*- coding: utf-8 -*-
"""py_mini_racer 并发构造守卫回归用例（#1566）。

**为什么全部开子进程**：被守的缺陷是 V8 的 `ImmediateCrash()`（Windows Fast Fail），
会直接杀掉宿主进程——`try/except`、pytest 的异常捕获、`faulthandler` 全都拦不住。
在测试进程内验证「崩没崩」等于让 pytest 自己送命。故所有涉及 MiniRacer 构造的断言
一律交给子进程，用退出码判定。

**跨平台策略**：`PartitionAddressSpace` 配置池的竞态是 Windows 实测复现的
（本机 8/10 崩），Linux/macOS 的虚拟地址空间预留机制不同、未必复现。因此：

- 「**无守卫必须崩**」的对照用例只在 Windows 跑（在别的平台测不出差异，会假红）；
- 「**有守卫必须不崩**」的正向用例跨平台安全，CI 上始终执行。

⚠️ **CI 绿 ≠ Windows 已修好**：akshare 的依赖是**平台条件式**的，两个平台装的是**不同的包**
（目录都叫 `py_mini_racer/`）——Windows/macOS 装 `mini-racer`（0.14.1），Linux（含 CI）装
`py-mini-racer`（0.6.0）。两者都在 `MiniRacer.__init__` 内调 `mr_init_context`（故守卫的
patch 点跨版本一致），但 **0.6.0 没有 `close()`**，且老 V8 未必带 PartitionAlloc 的那个
CHECK。因此本文件在 Linux 上只能证明「未回归」，**崩溃缺陷的有效覆盖在 Windows**。
凡版本相关的 API 调用一律走 `exercise_mini_racer`（`getattr` 防御）。

**对照实验设计**：两组都走真实的 `import app`（即在包导入期自动安装守卫），
唯一变量是 `V8_GUARD_ENABLED`。这样跑的既是守卫本身，也顺带验证了应急开关有效。

**注意断言强度**：子进程「非零退出」**不等于**「被 V8 中止」——脚本自身的
`SyntaxError` / `IndentationError` 同样是退出码 1。故对照用例除退出码外，还要断言
stderr 里没有 Python 层错误、且脚本没有跑完（跑完会打印哨兵串）。早期版本正因
只看退出码，把一处脚本缩进错误当成了「成功复现崩溃」。
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Dict, Optional

import pytest

# tests/test_v8_guard.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[1]

_CONCURRENT_WORKERS = 8

# 跨版本安全的「试跑 + 释放」片段（零缩进，直接拼进子进程脚本）。
#
# ⚠️ akshare 的依赖是**平台条件式**的，两个平台装的是**不同的包**（目录都叫 `py_mini_racer/`）：
#   - Windows / macOS：`mini-racer`（锁 0.14.1）—— 有 `eval` + **有** `close()`
#   - Linux（含 CI）  ：`py-mini-racer`（锁 0.6.0）—— 有 `eval`，**没有** `close()`（靠 `__del__`）
# 直接写 `mr.close()` 会让 CI 红——本 PR 实测踩到过。故一律 `getattr` 防御。
# `eval('1 + 1') == 2` 在两个版本都成立（均走 `to_python()` 转换，已核 0.6.0 源码）。
_EXERCISE_MR = """def exercise_mini_racer(mr):
    assert mr.eval('1 + 1') == 2
    closer = getattr(mr, 'close', None)
    if callable(closer):
        closer()
"""

# 子进程脚本的无缩进前缀：N 个线程同时构造 MiniRacer（复刻探市页 6 线程并发取数的形态）。
_CONCURRENT_CONSTRUCT = f"""
import threading

workers = {_CONCURRENT_WORKERS}

{_EXERCISE_MR}

def _construct_once(errors):
    try:
        from py_mini_racer import MiniRacer

        mr = MiniRacer()
        exercise_mini_racer(mr)
    except BaseException as exc:  # noqa: BLE001
        errors.append(repr(exc))


def run_round():
    errors = []
    threads = [threading.Thread(target=_construct_once, args=(errors,)) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors
"""


def _run_subprocess(code: str, env_extra: Optional[Dict[str, str]] = None, timeout: int = 180):
    """在 backend/ 下跑一段脚本，返回 CompletedProcess。

    `code` 必须是**已顶格**的完整脚本；缩进由调用方（各测试内的 `textwrap.dedent`）
    处理——不要在这里统一 dedent，前缀常量与后置片段的缩进不一致时 dedent 会失效。
    """
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, '-c', code],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=timeout,
    )


def _python_level_error(stderr: str) -> bool:
    """stderr 里是否出现 Python 层错误（用于把「脚本自身报错」与「V8 中止」区分开）。"""
    return any(marker in stderr for marker in ('SyntaxError', 'IndentationError', 'Traceback', 'NameError'))


def test_guard_installed_on_app_import():
    """包导入期必须已装好守卫，且构造被「标记」。

    `MiniRacer` 的两种导入形态（`import py_mini_racer` 与
    `from py_mini_racer import MiniRacer`）绑定的是**同一个类对象**，
    因此 patch 类方法即为全覆盖——这里断言的就是这个前提。
    """
    from py_mini_racer import MiniRacer

    from app.core.v8_guard import _PATCH_MARKER, guard_status, install_v8_guard

    status = guard_status()
    assert status['available'] is True, status
    assert status['patched'] is True, f'守卫未安装：{status}'
    # 后端包必须可识别：Windows 是 `mini-racer`，Linux（CI）是 `py-mini-racer`。
    # 这条断言把「跑的是哪个 V8 实现」钉住——排障时最容易被它误导。
    assert status['backend'] != 'unknown', status
    assert getattr(MiniRacer.__init__, _PATCH_MARKER, False) is True

    # 幂等：重复安装不得把同一个类重复包装（否则锁会层层叠加）。
    install_v8_guard()
    assert getattr(MiniRacer.__init__, _PATCH_MARKER, False) is True


def test_guarded_concurrent_construct_does_not_abort():
    """#1566 验收标准 1+2：装守卫后，并发构造 MiniRacer 不得 abort（跨平台正向断言）。"""
    code = _CONCURRENT_CONSTRUCT + textwrap.dedent(
        """
        from app.core.v8_guard import guard_status

        status = guard_status()
        assert status['patched'] is True, f'守卫未安装：{status}'

        for round_no in range(3):
            round_errors = run_round()
            assert not round_errors, f'第 {round_no} 轮构造抛异常：{round_errors}'

        print('GUARDED_OK')
        """
    )

    proc = _run_subprocess(code, env_extra={'V8_GUARD_ENABLED': '1'})

    assert not _python_level_error(proc.stderr), f'脚本自身报错：\n{proc.stderr}'
    assert proc.returncode == 0, (
        f'装守卫后仍被中止（returncode={proc.returncode}；0xC0000409 即 V8 Fast Fail）\n'
        f'STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}'
    )
    assert 'GUARDED_OK' in proc.stdout, proc.stdout


@pytest.mark.skipif(sys.platform != 'win32', reason='配置池竞态为 Windows 实测复现，其他平台不复现')
def test_unguarded_concurrent_construct_repro_aborts():
    """对照：`V8_GUARD_ENABLED=0` 关掉守卫后，并发构造必须仍能复现进程中止。

    这是**缺陷存在性**的守卫——若某天它不再崩（例如 mini-racer 上游修好了
    `mr_init_context` 的竞态），说明本 workaround 可以撤掉了，此用例会红以提醒。
    """
    code = _CONCURRENT_CONSTRUCT + textwrap.dedent(
        """
        from app.core.v8_guard import guard_status

        assert guard_status()['patched'] is False, '开关未生效，守卫仍被安装'

        # 竞态是概率性的（本机实测单轮约 80% 崩），故多轮提升复现率；
        # 任意一轮命中 Fast Fail 都会直接终结本进程，后面的轮次根本没机会跑。
        for round_no in range(5):
            round_errors = run_round()
            assert not round_errors, f'第 {round_no} 轮抛 Python 层异常：{round_errors}'

        print('NO_CRASH')
        """
    )

    proc = _run_subprocess(code, env_extra={'V8_GUARD_ENABLED': '0'})

    assert not _python_level_error(proc.stderr), f'脚本自身报错（不是复现到崩溃）：\n{proc.stderr}'
    assert 'NO_CRASH' not in proc.stdout, (
        f'未复现崩溃：关掉守卫后并发构造 5 轮仍全部成功。\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}'
    )
    assert proc.returncode != 0, f'进程既没跑完也没中止？returncode={proc.returncode}'


def test_trace_file_records_construct_scene(tmp_path):
    """#1566 验收标准 3：崩溃现场可观测——轨迹文件须留下构造前后的记录。

    刻意**不走 loguru**：文件 sink 是 `enqueue=True`（`logging_config`），日志在后台
    线程的队列里排队，进程被 Fast Fail 杀掉时队列内容随之丢失。本用例断言的是那条
    同步落盘的独立通道确实在工作。
    """
    code = _EXERCISE_MR + textwrap.dedent(
        """
        import app  # noqa: F401  —— 触发包导入期安装守卫

        from py_mini_racer import MiniRacer

        mr = MiniRacer()
        exercise_mini_racer(mr)
        print('TRACE_OK')
        """
    )

    proc = _run_subprocess(
        code,
        env_extra={
            'V8_GUARD_ENABLED': '1',
            'V8_GUARD_TRACE': '1',
            'V8_GUARD_TRACE_DIR': str(tmp_path),
        },
    )

    assert proc.returncode == 0, f'STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}'
    assert 'TRACE_OK' in proc.stdout, proc.stdout

    traces = list(tmp_path.glob('v8_guard_trace_*.log'))
    assert traces, f'未生成轨迹文件，目录内容：{list(tmp_path.iterdir())}'

    content = traces[0].read_text(encoding='utf-8')
    assert 'construct begin' in content, content
    assert 'construct ok' in content, content
    # 现场定位信息：必须能看出是哪个调用方在构造。
    assert 'caller=' in content, content


def test_trace_file_is_bounded(tmp_path):
    """轨迹文件必须有大小上限。

    dev server 长期驻留，一次探市页取数就要写约 10 行；没有上限会持续膨胀成一个
    与业务无关的巨无霸文件。上限语义是「超限即重开清空」而非轮转——崩溃现场关心的
    永远是最近几条，轮转反而会把现场挤进另一份文件里更难找。
    """
    code = _EXERCISE_MR + textwrap.dedent(
        """
        import pathlib

        import app  # noqa: F401

        from app.core import v8_guard
        from py_mini_racer import MiniRacer

        # 把上限压到 128 字节，使几乎每次写入都触发一次「重开清空」
        v8_guard._MAX_TRACE_BYTES = 128  # noqa: SLF001

        for _ in range(20):
            mr = MiniRacer()
            exercise_mini_racer(mr)

        path = pathlib.Path(v8_guard.guard_status()['trace_path'])
        size = path.stat().st_size
        # 不设上限的话 20 次构造约 2800 字节；设了上限后文件始终只剩最近几行。
        assert size < 600, f'轨迹文件未被上限约束：{size} 字节'
        assert 'construct ok' in path.read_text(encoding='utf-8')
        print('TRACE_BOUNDED_OK', size)
        """
    )

    proc = _run_subprocess(
        code,
        env_extra={
            'V8_GUARD_ENABLED': '1',
            'V8_GUARD_TRACE': '1',
            'V8_GUARD_TRACE_DIR': str(tmp_path),
        },
    )

    assert proc.returncode == 0, f'STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}'
    assert 'TRACE_BOUNDED_OK' in proc.stdout, proc.stdout


# ---------------------------------------------------------------------------
# 后端 API 差异的回归覆盖（本机 Windows 即可执行，不需要 Linux）
#
# 起因：本 PR 首版在预热里直接写 `mr.close()`，本机（Windows，`mini-racer 0.14.1`）全绿，
# CI（Linux，`py-mini-racer 0.6.0`）直接红——0.6.0 的 `MiniRacer` 没有 `close()`。
# 这类「本机绿、CI 红」的坑必须能用本机复现的手段钉住，故此处用假模块复刻两个平台的
# API 形状，把「预热不得因 API 差异而误判失败」变成断言。
# ---------------------------------------------------------------------------

_FAKE_SCRIPT = """
import sys
import types


class FakeMiniRacer:
    __BODY__


_fake = types.ModuleType('py_mini_racer')
_fake.MiniRacer = FakeMiniRacer
sys.modules['py_mini_racer'] = _fake

import app  # noqa: F401  —— 触发包导入期安装守卫（会拿到上面注入的假模块）

from app.core.v8_guard import _PATCH_MARKER, guard_status

status = guard_status()
assert status['patched'] is True, status
assert getattr(FakeMiniRacer.__init__, _PATCH_MARKER, False) is True, f'假类未被 patch：{status}'
assert status['warmed_up'] is True, (
    f'预热被误判为失败。status={status}；预热的语义是「构造已完成」——'
    f'`eval` / `close` 都只是 best-effort，任何 API 缺失或报错都不得推翻它。'
)
print('FAKE_BACKEND_OK')
"""

# 复刻 Linux 的 `py-mini-racer 0.6.0`：有 eval、**没有 close**（靠 __del__ 释放）。
_BODY_NO_CLOSE = """
def __init__(self):
    pass


def eval(self, code):
    return 2
"""

# close() 存在但报错（探活/释放失败不得影响预热结论）。
_BODY_CLOSE_RAISES = """
def __init__(self):
    pass


def eval(self, code):
    return 2


def close(self):
    raise RuntimeError('fake close failure')
"""

# eval 报错（构造已成功 → V8 已初始化，预热目标已达成）。
_BODY_EVAL_RAISES = """
def __init__(self):
    pass


def eval(self, code):
    raise RuntimeError('fake eval failure')
"""


def _fake_backend_script(body: str) -> str:
    """把假类的方法体填进模板（缩进交给 textwrap，避免手写空格出错）。"""
    return _FAKE_SCRIPT.replace('    __BODY__', textwrap.indent(textwrap.dedent(body).strip(), '    '))


@pytest.mark.parametrize(
    ('case', 'body'),
    [
        ('no-close（Linux py-mini-racer 0.6.0 形状）', _BODY_NO_CLOSE),
        ('close 报错', _BODY_CLOSE_RAISES),
        ('eval 报错', _BODY_EVAL_RAISES),
    ],
    ids=['no-close', 'close-raises', 'eval-raises'],
)
def test_warmup_tolerates_backend_api_variance(case, body):
    """预热必须容忍后端包的 API 差异——API 缺失/报错不得把预热误判为失败。"""
    proc = _run_subprocess(_fake_backend_script(body), env_extra={'V8_GUARD_ENABLED': '1'})

    assert not _python_level_error(proc.stderr), f'[{case}] 脚本自身报错：\n{proc.stderr}'
    assert proc.returncode == 0, f'[{case}] STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}'
    assert 'FAKE_BACKEND_OK' in proc.stdout, f'[{case}] {proc.stdout}'
