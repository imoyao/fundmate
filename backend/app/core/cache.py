# -*- coding: utf-8 -*-
"""CacheService：框架无关的缓存薄接口（#892 架构决策，2026-08-08 拍板）。

设计约束（issue #892「Redis 预留」节）：
- **框架无关**：不 import flask、不绑 Flask-Caching——Flask→FastAPI 迁移不受影响。
- **默认后端 = 进程内 LRU + 文件**：LRU 抗高频重复读，文件层抗冷启动（进程重启后
  首次访问免重算）。文件层目录由 :func:`resolve_cache_file_dir` **唯一**解析
  （env `CACHE_FILE_DIR`，缺省系统临时目录），可经构造参数 `file_dir=` 覆盖——便于
  按环境指定，也让测试能注入 `tmp_path` 做用例级隔离（#1531）。该解析入口是全仓
  「文件缓存落哪儿」的单一真相源：温度计 fetchers 经它取目录（#1537），
  行业拥挤度 / FOF 拥挤度的 parquet·JSON 缓存经 `resolve_cache_subdir()` 分目录（#1539）。
- **Redis 为可选后端、默认关闭**：设 env `CACHE_BACKEND=redis` 且 redis 可导入时启用，
  其余情况静默回退本地后端，调用方零感知（多实例部署才有意义，单机勿开）。
- **数据分级红线**：仅允许缓存自建分析结果与公开行情（温度计/拥挤度等）；
  家庭核心账本数据（持仓明细、交易记录）**禁止**进入任何缓存层，含本接口。
  该约束靠调用方自觉 + code review 把关，本接口不做数据内容嗅探（保持薄）。

挂 Hook 点（本期）：行业拥挤度合成结果（fetch_industry_crowding），冷启动加速。
"""

import os
import pickle
import tempfile
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

# ─────────────────────────── 配置 ───────────────────────────
# env 驱动，避免 import 时读 app config（core 模块互相依赖要克制）。
#
# 注意：env 一律**构造期解析**，不要固化成模块级常量（#1531）。
# 原先是 `_BACKEND = os.environ.get(...)` / `_FILE_DIR = Path(os.environ.get(...))`，
# 导入之后再改 env 就完全无效：测试里写的 `os.environ['CACHE_FILE_DIR'] = tmp_path`
# 成了假隔离（实际仍读写全局临时目录），`CACHE_BACKEND` 的 monkeypatch 也让
# redis 回退用例退化为假阳性。
_DEFAULT_TTL = 600  # 秒；调用方应显式传 ttl
_LRU_MAX = 256  # 条；进程内热点上限
_FILE_PREFIX = 'cache_'
_FILE_DIR_NAME = 'fundmate_cache'


def _env_backend() -> str:
    """后端选择（构造期读 env，理由见上方注释）。"""
    return os.environ.get('CACHE_BACKEND', 'local').lower()


def resolve_cache_file_dir() -> Path:
    """缓存文件层的**唯一**目录解析入口：env `CACHE_FILE_DIR` 优先，否则系统临时目录。

    全仓「文件缓存落哪儿」的单一真相源（#1537）：`CacheService` 与温度计 fetchers
    共用本函数，杜绝「同一个目录、两套实现、只有一套认 env」的部分生效——
    按环境指定目录时只生效一半，比完全不生效更难排查。

    **必须在调用期解析**，不要固化成模块级常量（#1531 / #1537 是同一个坑）：
    常量在 import 那一刻就绑定了当时的环境，之后再设 `CACHE_FILE_DIR` 完全无效，
    `tests/conftest.py::_isolate_cache_file_dir` 会静默失效。

    回归背景（#1531）：该目录**跨进程存活**，残留的 pkl 会在 ttl 内让下一个进程
    直接命中——测试结果因此取决于「上一轮跑过什么」，真失败与污染失败外观一致。
    """
    raw = os.environ.get('CACHE_FILE_DIR')
    return Path(raw) if raw else Path(tempfile.gettempdir()) / _FILE_DIR_NAME


def resolve_cache_subdir(name: str) -> Path:
    """`resolve_cache_file_dir()` 下的命名子目录（#1539）。

    供**非 pickle 值对象**的大型缓存分目录使用（parquet / CSV / JSON 等）：它们不便走
    `CacheService` 的「pickle 一个值 + `expire_at` 写进文件」语义，但**目录**仍必须只有
    一个真相源——否则又会回到「改 `CACHE_FILE_DIR` 只生效一半」的老问题
    （#1531 → #1537 → #1539 已连犯三次）。

    同样**必须调用期解析**，理由见 :func:`resolve_cache_file_dir`。

    Raises:
        ValueError: `name` 是绝对路径。``Path`` 的 `/` 语义下 `root / '/etc'` 会直接返回
            ``'/etc'``——子目录就此跳出了缓存根目录，本函数「一切落盘都在同一个根之下」
            的契约被静默打破（正是 #1531 / #1537 / #1539 要对付的「目录没有单一真相源」）。
            调用方一律传相对名字，故这是**契约自检**而非容错分支。
    """
    if Path(name).is_absolute():
        raise ValueError(f'resolve_cache_subdir 只接受相对子目录名，收到绝对路径：{name!r}')
    return resolve_cache_file_dir() / name


class CacheService:
    """两级本地缓存（LRU + 文件），Redis 可选预留。

    用法::

        cache = CacheService(namespace='crowding')
        val = cache.get_or_set('industry_crowding:20260910', ttl=3600, producer=fetch)

    Args:
        namespace: 命名空间，隔离不同业务的键。
        default_ttl: 未显式传 ttl 时的默认过期秒数。
        file_dir: 文件层目录。缺省取 env `CACHE_FILE_DIR`（未设则系统临时目录）；
            显式传入优先于 env，测试用它注入 `tmp_path` 做用例级隔离（#1531）。
    """

    def __init__(
        self,
        namespace: str = 'default',
        default_ttl: int = _DEFAULT_TTL,
        file_dir: Path | str | None = None,
    ):
        self._ns = namespace.strip().replace('/', '_') or 'default'
        self._default_ttl = default_ttl
        self._lru: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._backend = self._resolve_backend()
        self._file_dir: Optional[Path] = Path(file_dir) if file_dir is not None else resolve_cache_file_dir()
        if self._file_dir is not None:
            try:
                self._file_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                self._file_dir = None  # 文件层不可用时静默退化为纯 LRU

    # ─────────────── 后端解析 ───────────────
    def _resolve_backend(self) -> str:
        """redis 仅在 env 显式指定且 redis 可导入时启用，否则回退 local（默认关）。

        env 在构造期读取（#1531）：读模块级常量会让 monkeypatch `CACHE_BACKEND`
        的用例测不到本分支（假阳性），本方法则保证「进程内改 env 后新建实例」生效。
        """
        if _env_backend() == 'redis':
            try:
                import redis  # noqa: F401

                return 'redis'
            except ImportError:
                logger.warning('CACHE_BACKEND=redis 但 redis 未安装，回退本地缓存')
        return 'local'

    # ─────────────── 公开接口 ───────────────
    def get(self, key: str) -> Optional[Any]:
        """命中返回值，未命中/过期/异常返回 None（缓存永不抛异常打断业务）。"""
        full = f'{self._ns}:{key}'
        now = time.time()
        # L1: LRU
        with self._lock:
            hit = self._lru.get(full)
            if hit is not None:
                expire_at, value = hit
                if now < expire_at:
                    self._lru.move_to_end(full)
                    return value
                del self._lru[full]
        # L2: 文件（local 后端）
        if self._backend == 'local':
            return self._file_get(full, now)
        # redis 预留：本期不实现连接管理，接入时补
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """写入两级缓存；任一层失败静默（缓存故障不阻断主链路）。

        `value is None` 直接忽略：`get()` 以 None 表示未命中，写进去会让该键永久 miss，
        与 `get_or_set`「producer 返回 None 即不写入」的约定保持一致（#1491 评审）。
        """
        if value is None:
            return
        full = f'{self._ns}:{key}'
        ttl = ttl if ttl is not None else self._default_ttl
        expire_at = time.time() + ttl
        with self._lock:
            self._lru_put(full, expire_at, value)
        if self._backend == 'local':
            self._file_set(full, value, ttl)

    def get_or_set(self, key: str, producer: Callable[[], Any], ttl: Optional[int] = None) -> Any:
        """命中即返；未命中调 producer 并写缓存（语义对齐 fetchers._cached）。"""
        val = self.get(key)
        if val is not None:
            return val
        data = producer()
        # 约定：producer 返回 None 视为「本次无可缓存」，不写入，避免 None 被当命中
        if data is not None:
            self.set(key, data, ttl)
        return data

    def invalidate(self, key: str) -> None:
        """主动失效（两级同删）。

        文件删除放在同一把锁内（#1491 评审）：与 `_file_get` 的「回填 LRU」互斥，
        避免已失效的数据又被回填回 L1 造成失效不彻底。
        """
        full = f'{self._ns}:{key}'
        with self._lock:
            self._lru.pop(full, None)
            if self._backend == 'local' and self._file_dir is not None:
                _unlink_quiet(self._file_dir / f'{_FILE_PREFIX}{_safe_name(full)}.pkl')

    # ─────────────── LRU 内部 ───────────────
    def _lru_put(self, full: str, expire_at: float, value: Any) -> None:
        """写入 L1 并按 _LRU_MAX 淘汰（调用方须持 self._lock）。

        `set` 与 `_file_get` 回填共用同一策略：此前回填路径漏了淘汰，
        文件命中较多时 LRU 可越过上限（#1491 评审）。
        """
        self._lru[full] = (expire_at, value)
        self._lru.move_to_end(full)
        while len(self._lru) > _LRU_MAX:
            self._lru.popitem(last=False)

    # ─────────────── 文件层 ───────────────
    def _file_get(self, full: str, now: float) -> Optional[Any]:
        if self._file_dir is None:
            return None
        path = self._file_dir / f'{_FILE_PREFIX}{_safe_name(full)}.pkl'
        try:
            if not path.exists():
                return None
            with open(path, 'rb') as fh:
                expire_at, value = pickle.load(fh)
            if now >= expire_at:
                # 过期即删除：否则后续每次 get 都要重复读盘并再次判定过期（#1491 评审）
                _unlink_quiet(path)
                return None
            # 文件命中回填 LRU（含上限淘汰，与 set 同策略），加速后续访问
            with self._lock:
                # 持锁确认文件仍在，避免与 invalidate 竞态时把已失效数据回填回 L1（#1491 评审）
                if not path.exists():
                    return None
                self._lru_put(full, expire_at, value)
            return value
        except Exception:  # noqa: BLE001 - 文件损坏/版本不兼容等一律当未命中
            return None

    def _file_set(self, full: str, value: Any, ttl: int) -> None:
        if self._file_dir is None:
            return
        path = self._file_dir / f'{_FILE_PREFIX}{_safe_name(full)}.pkl'
        try:
            with open(path, 'wb') as fh:
                pickle.dump((time.time() + ttl, value), fh)
        except Exception:  # noqa: BLE001 - 不可序列化/磁盘满等静默
            pass


def _safe_name(key: str) -> str:
    """key 中文件系统敏感字符替换为下划线（namespace 已在构造时清理）。"""
    return ''.join(c if c.isalnum() or c in '-_.' else '_' for c in key)


def _unlink_quiet(path: Path) -> None:
    """删除缓存文件且不抛异常（缓存层故障一律静默）。"""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
