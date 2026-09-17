# -*- coding: utf-8 -*-
"""py_mini_racer「并发构造」进程级守卫（#1566）。

**WHY**

`py_mini_racer` 内嵌的 V8 里，`PartitionAddressSpace::Init()` 是 check-then-act：

```cpp
void PartitionAddressSpace::Init() {
  if (IsInitialized()) return;              // ← 两个线程可同时穿过这里
  CHECK(!IsConfigurablePoolInitialized());  // ← 第二个线程死在这
  ...
}
```

而上游 `py_mini_racer/_dll.py` 的 `init_mini_racer()` 只把 `_init_lock` 加在
`mr_init_v8`（DLL/V8 初始化）上，**没有覆盖 `_mini_racer.py` 里的 `mr_init_context`
（isolate 创建）**——偏偏那个 configurable pool 是**首次创建 isolate 时**才初始化的。

akshare 里有多个接口**每次调用都新建一个 `MiniRacer()`**（实测本仓在用的至少 8 个：
`stock_zh_index_daily` / `stock_hk_index_daily_sina` / `fund_etf_hist_sina` /
`index_us_stock_sina` / `stock_zh_a_daily` / `bond_zh_cov` 等）。只要两处**并发**触发，
第二个线程就命中 `CHECK(!IsConfigurablePoolInitialized())` → `ImmediateCrash()`。

探市页 / 投资概览页正是这个形态：`market_service.MarketOverviewService.get_overview()`
用 `ThreadPoolExecutor(max_workers=6)` 并发取 20 个资产，其中 5 个走新浪指数。

**为什么 Python 层没法兜底**：V8 的 `ImmediateCrash()` 在 Windows 上是
`__fastfail(FAST_FAIL_FATAL_APP_EXIT)`——**Fast Fail 不执行任何 handler、`atexit`
或信号回调**，栈帧直接 dump 完就终止进程（exit code `0xC0000409`）。所以
`try/except`、`faulthandler`、Flask 的 errorhandler 全部无效，**只能在事前串行化**。

**HOW**

把 `MiniRacer.__init__` 包一层进程级 `RLock`——`mr_init_context` 就在 `__init__` 内部
（经 `_make_context` 上下文管理器）被调用，锁住构造即锁住它。

**为什么 patch 类方法，而不是替换 `py_mini_racer.MiniRacer` 这个名字**：
akshare 里存在两种导入形态——`import py_mini_racer` 后 `py_mini_racer.MiniRacer()`
（如 `index/index_stock_zh.py`），以及 `from py_mini_racer import MiniRacer`
（如 `air/air_zhenqi.py`）。后者在 akshare 子模块**导入时**就把类对象绑定进了它自己的
globals，替换模块属性对它无效。而 patch **类对象的方法**对两种形态、以及任何已持有的
引用一律生效，因此不必去遍历 akshare 子模块做二次替换——**这是「覆盖所有路径」的关键**。

**为什么只锁构造，不锁 eval/call**：不同 `MiniRacer` 是各自独立的 V8 isolate，
构造完成后并发改用实测安全；把 eval/call 也锁上只会把探市页取数全串行化，
牺牲首屏时间却买不到额外安全性。

**实测依据**（Windows / Python 3.12 / mini-racer 0.14.1，各跑 10 轮 8 线程并发构造）：

| 模式 | 结果 |
| --- | --- |
| 无保护并发构造 | 成功 2 / **崩溃 8** |
| 仅构造加锁 | **成功 10 / 崩溃 0** |
| 构造 + eval 全加锁 | 成功 10 / 崩溃 0 |

**崩溃现场可观测**

Fast Fail 下进程内无法补救，只能「事前留痕」。但**不能走 loguru**：
`logging_config.setup_file_logging()` 的 file sink 是 `enqueue=True`，日志先进后台
队列，进程被硬杀时队列内容随之丢失——恰好丢掉崩溃前最后一条。故本模块用独立的、
同步 `write + flush` 的轨迹文件（`write` 返回即数据已进 OS page cache，进程之后再死
也不会丢）。文件按 `{pid}` 命名，避免 dev server 与 scheduler-daemon 互写。

**已知代价**：每次构造多一次「加锁 + 写一行轨迹」，相对 mini-racer 本身
~0.1~0.17s/次的构造开销可忽略。可用 `V8_GUARD_ENABLED=0` 整体关闭（应急），
`V8_GUARD_TRACE=0` 只关轨迹文件。
"""

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, TextIO

from loguru import logger

from app.core.time_utils import now_shanghai

# ─────────────────────────── 进程级唯一锁 ───────────────────────────
# 保护 MiniRacer 的**构造**。用 RLock 而非 Lock：万一将来构造路径内部再触发一次
# 同类构造（当前没有），RLock 只会重入而不会自锁死。
_V8_CONSTRUCT_LOCK = threading.RLock()

# 幂等标记：挂在被 patch 后的 `__init__` 上。用函数属性而非模块级 bool，
# 这样即使本模块被 reload（模块级状态重置）也不会把同一个类重复包装多层。
_PATCH_MARKER = '_v8_guard_patched'

# 轨迹文件句柄（懒打开，行缓冲）。**必须由 _trace_lock 保护**：`construct begin` 那一条是
# 在 `_V8_CONSTRUCT_LOCK` **之外**写的（刻意如此，用来记录「谁在等锁」），因此多线程会并发
# 进入 `_trace`——不设锁会让 write 交错、甚至在重开文件时踩坏句柄。
_trace_fp: Optional[TextIO] = None
_trace_bytes = 0
_trace_lock = threading.Lock()

# 轨迹文件大小上限。崩溃现场关心的永远是**最近**几条，故超限直接重开清空而非轮转
# ——轮转会把现场挤进另一份文件里，反而更难找。上限的意义：dev server 长跑时，
# 一次探市页取数就要写约 10 行，没有上限会持续膨胀。
_MAX_TRACE_BYTES = 512 * 1024

# 预热是否已成功完成（模块级；flask reloader 在 Windows 上是重启新进程，不存在跨重载残留）。
_warmed_up = False

_FALSY = {'0', 'false', 'no', 'off'}


def _env_flag(name: str, default: bool = True) -> bool:
    """读布尔环境变量；空值取 default，其余按 0/false/no/off 判定为假。"""
    raw = os.getenv(name, '').strip().lower()
    if not raw:
        return default
    return raw not in _FALSY


def _in_test_process() -> bool:
    """当前是否 pytest 进程。

    与 `app.core.logging_config._in_test_process` 同一判据、同一理由：测试进程里
    默认别往仓库写文件（`tests/conftest.py` 的 `app` fixture 每个用例都调 `create_app()`，
    而 `import app` 一个进程只发生一次，不拦就会把轨迹文件写进 `backend/logs/`）。
    """
    return 'pytest' in sys.modules or 'PYTEST_CURRENT_TEST' in os.environ


def _trace_enabled() -> bool:
    """轨迹开关：`V8_GUARD_TRACE` 显式取值优先；未设置时**测试进程默认关闭**。

    验收/排查场景用 `V8_GUARD_TRACE=1` + `V8_GUARD_TRACE_DIR=<tmp>` 显式打开。
    """
    raw = os.getenv('V8_GUARD_TRACE', '').strip().lower()
    if raw in _FALSY:
        return False
    if raw:
        return True
    return not _in_test_process()


def _backend_logs_dir() -> Path:
    """backend/logs（与 logging_config 同口径：app/core/v8_guard.py -> backend）"""
    return Path(__file__).resolve().parents[2] / 'logs'


def _trace_path() -> Path:
    """轨迹文件路径：`V8_GUARD_TRACE_DIR` 优先，否则 backend/logs；带 pid 防多进程互写。"""
    raw = os.getenv('V8_GUARD_TRACE_DIR', '').strip()
    directory = Path(raw) if raw else _backend_logs_dir()
    return directory / f'v8_guard_trace_{os.getpid()}.log'


def _open_trace_file() -> None:
    """（重新）打开轨迹文件并清零计数。调用方须持有 `_trace_lock`。"""
    global _trace_fp, _trace_bytes
    if _trace_fp is not None:
        try:
            _trace_fp.close()
        except Exception:  # noqa: BLE001 - 关旧句柄失败不应阻塞重开
            pass
    path = _trace_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # buffering=1 -> 文本模式行缓冲，每条 \n 结尾的写入立即 flush 到 OS。
    _trace_fp = open(path, 'w', encoding='utf-8', buffering=1)  # noqa: SIM115
    _trace_bytes = 0


def _trace(message: str) -> None:
    """同步追加一行崩溃现场轨迹（失败静默——留痕不该反过来拦住业务）。

    线程安全：`construct begin` 在构造锁**之外**写，故本函数自带锁。
    锁序恒为 `_V8_CONSTRUCT_LOCK` -> `_trace_lock`，无反向获取，不会死锁。
    """
    global _trace_bytes
    if not _trace_enabled():
        return
    try:
        line = f'{now_shanghai().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]} | pid={os.getpid()} | {message}\n'
        payload = len(line.encode('utf-8'))
        with _trace_lock:
            if _trace_fp is None or _trace_bytes + payload > _MAX_TRACE_BYTES:
                _open_trace_file()
            _trace_fp.write(line)
            _trace_bytes += payload
    except Exception:  # noqa: BLE001 - 留痕失败不得影响取数
        pass


def _caller_hint() -> str:
    """取调用栈里第一个「非 py_mini_racer、非本模块」的帧，用于崩溃现场定位。

    典型输出 `akshare.index.index_stock_zh:304`（= 新浪指数取数）或
    `app.services.market_service:351`，直接指向是哪个调用方在并发构造。
    """
    frame = sys._getframe(1)
    while frame is not None:
        module = frame.f_globals.get('__name__', '')
        if module and not module.startswith('py_mini_racer') and module != __name__:
            return f'{module}:{frame.f_lineno}'
        frame = frame.f_back
    return '<unknown>'


def _patch_mini_racer_class(cls: Any) -> bool:
    """把 `cls.__init__` 包成「先落痕、再加锁、再构造」。返回是否本次新包装。"""
    original = cls.__init__
    if getattr(original, _PATCH_MARKER, False):
        return False

    def guarded_init(self: Any, *args: Any, **kwargs: Any) -> None:
        # 落痕放在加锁**之前**：若要等锁，这行会告诉我们「谁在等」；
        # 若锁本身出问题，也能看到「谁进来了」。
        _trace(f'construct begin | caller={_caller_hint()}')
        with _V8_CONSTRUCT_LOCK:
            original(self, *args, **kwargs)
        _trace('construct ok')

    guarded_init.__wrapped__ = original  # type: ignore[attr-defined]
    guarded_init.__doc__ = original.__doc__
    setattr(guarded_init, _PATCH_MARKER, True)

    cls.__init__ = guarded_init
    return True


def _warmup_once() -> bool:
    """在**单线程**上下文里先把 V8 的首次初始化做掉。

    把「首次构造 isolate」这个危险动作从运行期（6 个线程同时涌入）挪到启动期
    （单线程、无人竞争）。这不是构造锁的替代品，而是纵深防御 + 顺手省掉首请求
    的 V8 冷启动开销（实测 ~0.1~0.2s）。
    """
    global _warmed_up
    if _warmed_up:
        return True
    try:
        from py_mini_racer import MiniRacer
    except ImportError:
        return False

    started = time.monotonic()
    try:
        mr = MiniRacer()
        try:
            mr.eval('1 + 1')
        finally:
            # 显式关闭，避免预热实例的 isolate 吊到进程退出才回收。
            mr.close()
    except Exception as exc:  # noqa: BLE001 - 预热失败不得拦住应用启动
        logger.warning(f'V8 预热失败（已降级为仅依赖构造锁，功能不受影响）：{exc}')
        return False

    _warmed_up = True
    logger.info(f'V8 预热完成（{time.monotonic() - started:.2f}s），并发构造窗口已前移')
    return True


def install_v8_guard(warmup: bool = True) -> bool:
    """安装进程级守卫（幂等）。返回是否可用。

    在 `app/__init__.py` 的包导入期调用，覆盖 Flask dev server / `pdm run sync` /
    `scheduler-daemon` / `invoke grab.*` 全部入口（与 `install_requests_patch` 同位置、同理由）。

    `py_mini_racer` 未安装时**返回 False 而不抛异常**：本函数的职责是「有 V8 就保护它」，
    不是「强制环境必须有 V8」；在包导入期抛异常会让整个应用起不来。
    """
    if not _env_flag('V8_GUARD_ENABLED', True):
        logger.warning('V8_GUARD_ENABLED=0：已跳过 MiniRacer 并发构造守卫（#1566 的崩溃风险自担）')
        return False

    try:
        from py_mini_racer import MiniRacer
    except ImportError as exc:
        logger.debug(f'py_mini_racer 不可用，跳过 V8 并发构造守卫：{exc}')
        return False

    if _patch_mini_racer_class(MiniRacer):
        logger.info('V8 并发构造守卫已安装：MiniRacer() 构造串行化（#1566）')

    if warmup:
        _warmup_once()
    return True


def guard_status() -> Dict[str, Any]:
    """诊断用：当前守卫状态（供测试与排查读取，不参与业务逻辑）。"""
    try:
        from py_mini_racer import MiniRacer as _cls
    except ImportError:
        return {'available': False}

    init = _cls.__init__
    return {
        'available': True,
        'patched': bool(getattr(init, _PATCH_MARKER, False)),
        'warmed_up': _warmed_up,
        'trace_enabled': _trace_enabled(),
        'trace_path': str(_trace_path()),
    }
