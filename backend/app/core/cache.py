# -*- coding: utf-8 -*-
"""CacheService：框架无关的缓存薄接口（#892 架构决策，2026-08-08 拍板）。

设计约束（issue #892「Redis 预留」节）：
- **框架无关**：不 import flask、不绑 Flask-Caching——Flask→FastAPI 迁移不受影响。
- **默认后端 = 进程内 LRU + 文件**：LRU 抗高频重复读，文件层抗冷启动（进程重启后
  首次访问免重算，复用 fetchers._cached 的 pickle 模式）。
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
_BACKEND = os.environ.get('CACHE_BACKEND', 'local').lower()
_FILE_DIR = Path(os.environ.get('CACHE_FILE_DIR', Path(tempfile.gettempdir()) / 'fundmate_cache'))
_DEFAULT_TTL = 600  # 秒；调用方应显式传 ttl
_LRU_MAX = 256  # 条；进程内热点上限
_FILE_PREFIX = 'cache_'


class CacheService:
    """两级本地缓存（LRU + 文件），Redis 可选预留。

    用法::

        cache = CacheService(namespace='crowding')
        val = cache.get_or_set('industry_crowding:20260910', ttl=3600, producer=fetch)
    """

    def __init__(self, namespace: str = 'default', default_ttl: int = _DEFAULT_TTL):
        self._ns = namespace.strip().replace('/', '_') or 'default'
        self._default_ttl = default_ttl
        self._lru: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._backend = self._resolve_backend()
        self._file_dir: Optional[Path] = _FILE_DIR
        if self._file_dir is not None:
            try:
                self._file_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                self._file_dir = None  # 文件层不可用时静默退化为纯 LRU

    # ─────────────── 后端解析 ───────────────
    def _resolve_backend(self) -> str:
        """redis 仅在 env 显式指定且 redis 可导入时启用，否则回退 local（默认关）。"""
        if _BACKEND == 'redis':
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
        """写入两级缓存；任一层失败静默（缓存故障不阻断主链路）。"""
        full = f'{self._ns}:{key}'
        expire_at = time.time() + (ttl if ttl is not None else self._default_ttl)
        with self._lock:
            self._lru[full] = (expire_at, value)
            self._lru.move_to_end(full)
            while len(self._lru) > _LRU_MAX:
                self._lru.popitem(last=False)
        if self._backend == 'local':
            self._file_set(full, value, ttl if ttl is not None else self._default_ttl)

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
        """主动失效（两级同删）。"""
        full = f'{self._ns}:{key}'
        with self._lock:
            self._lru.pop(full, None)
        if self._backend == 'local' and self._file_dir is not None:
            try:
                (self._file_dir / f'{_FILE_PREFIX}{_safe_name(full)}.pkl').unlink(missing_ok=True)
            except OSError:
                pass

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
                return None
            # 文件命中回填 LRU，加速后续访问
            with self._lock:
                self._lru[full] = (expire_at, value)
                self._lru.move_to_end(full)
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
