# -*- coding: utf-8 -*-
"""温度计的三处文件缓存目录与 `CACHE_FILE_DIR` 同源（#1539）。

背景（#1531 → #1537 → #1539 是同一个坑，已连犯三次）：这些目录原先都是**模块级常量**，
`os.path.join(HERE, 'cache', ...)` 直接写死在**源码树内**——

- `industry_crowding.CACHE_DIR`      → `cache/baostock_pb`
- `industry_crowding.EM_HIST_CACHE_DIR` → `cache/em_industry_hist`
- `fundfof_crowding.CACHE_DIR`       → `cache/fundfof_crowding`

常量在 **import 那一刻**就绑定了环境，于是「按环境指定缓存目录」（容器 / 只读文件系统 /
CI / 测试隔离）只生效一半：`app/core/cache.py` 认 `CACHE_FILE_DIR`，这三处不认。
更糟的是源码树目录**不可写**的场景（只读挂载 / 打包分发）会让缓存静默失败。

修复后三条契约（对应 issue 的验收标准）：

1. 三处目录都由 `resolve_cache_subdir()` 从 `resolve_cache_file_dir()` 派生，
   **不再是源码树内的硬编码路径**；
2. 解析发生在**调用期**——import 之后再改 `CACHE_FILE_DIR` 立刻生效
   （本文件的 `test_*_at_call_time` 就是这条的回归守卫：退回模块常量即失败）；
3. 派生文件路径（`latest.json` / `latest_track.json` / `history_*.json`）都落在该目录下。
"""

import tempfile
from pathlib import Path

from app.core.cache import resolve_cache_file_dir, resolve_cache_subdir
from app.services.thermometer import fundfof_crowding as fc
from app.services.thermometer import industry_crowding as ic

# 目录解析函数 → 它应在 `<CACHE_FILE_DIR>` 下占用的子目录名
_DIR_RESOLVERS = {
    'baostock_pb': ic.baostock_cache_dir,
    'em_industry_hist': ic.em_hist_cache_dir,
    'fundfof_crowding': fc.fundfof_cache_dir,
}

# 这三处原先写死的源码树目录（用于断言「不再往这儿写」）
_LEGACY_SOURCE_DIRS = {
    'baostock_pb': Path(ic.__file__).parent / 'cache' / 'baostock_pb',
    'em_industry_hist': Path(ic.__file__).parent / 'cache' / 'em_industry_hist',
    'fundfof_crowding': Path(fc.__file__).parent / 'cache' / 'fundfof_crowding',
}


def _isolated_dir(tmp_path: Path) -> Path:
    """conftest 的 `_isolate_cache_file_dir` 写入的用例私有目录。"""
    return tmp_path / 'fundmate_cache'


class TestSubdirResolver:
    def test_subdir_under_cache_file_dir(self):
        """子目录必须挂在 `resolve_cache_file_dir()` 之下（单一真相源）。"""
        assert resolve_cache_subdir('probe') == resolve_cache_file_dir() / 'probe'

    def test_subdir_follows_env_at_call_time(self, tmp_path, monkeypatch):
        """`resolve_cache_subdir()` 调用期读 env：改 env 立刻生效。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path / 'a'))
        assert resolve_cache_subdir('probe') == tmp_path / 'a' / 'probe'
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path / 'b'))
        assert resolve_cache_subdir('probe') == tmp_path / 'b' / 'probe'

    def test_subdir_default_under_temp_dir(self, monkeypatch):
        """未设 env 时缺省仍在系统临时目录下，不落源码树。"""
        monkeypatch.delenv('CACHE_FILE_DIR', raising=False)
        resolved = resolve_cache_subdir('probe')
        assert resolved.parent == resolve_cache_file_dir()
        assert str(resolved).startswith(str(Path(tempfile.gettempdir())))


class TestThermometerCacheDirs:
    def test_all_dirs_under_cache_file_dir(self, tmp_path, monkeypatch):
        """三处目录都在 `<CACHE_FILE_DIR>` 下，且彼此不重叠（验收 1）。"""
        root = tmp_path / 'custom'
        monkeypatch.setenv('CACHE_FILE_DIR', str(root))

        resolved = {name: Path(fn()) for name, fn in _DIR_RESOLVERS.items()}
        for name, path in resolved.items():
            assert path == root / name, f'{name} 未随 CACHE_FILE_DIR 解析：{path}'
        assert len(set(resolved.values())) == 3, '三处缓存目录发生重叠，会互相覆盖'

    def test_all_dirs_follow_env_change_at_call_time(self, tmp_path, monkeypatch):
        """**核心回归守卫**：import 之后再改 env 仍生效（验收 2）。

        若把任一处退回模块级常量，常量在 import 时已绑定当时的环境，
        第二次 setenv 后该目录不再移动 → 本用例精确失败。
        """
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path / 'first'))
        before = {name: fn() for name, fn in _DIR_RESOLVERS.items()}
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path / 'second'))
        after = {name: fn() for name, fn in _DIR_RESOLVERS.items()}

        for name in _DIR_RESOLVERS:
            assert before[name] != after[name], f'{name} 未随 CACHE_FILE_DIR 变化，疑似被固化成 import 期常量'
            assert after[name] == str(tmp_path / 'second' / name)

    def test_dirs_not_in_source_tree(self, tmp_path, monkeypatch):
        """缓存目录**不再**落在源码树内（#1539 的核心诉求）。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path))
        for name, fn in _DIR_RESOLVERS.items():
            resolved = Path(fn()).resolve()
            legacy = _LEGACY_SOURCE_DIRS[name].resolve()
            assert resolved != legacy, f'{name} 仍指向源码树目录 {legacy}'
            assert legacy not in resolved.parents, f'{name} 落在了源码树内的 {resolved}'

    def test_isolated_by_conftest_fixture(self, tmp_path):
        """conftest 的 autouse 隔离夹具覆盖这三处，且不污染全局临时目录。"""
        expected = _isolated_dir(tmp_path)
        for name, fn in _DIR_RESOLVERS.items():
            assert Path(fn()) == expected / name, f'{name} 未被 conftest 隔离夹具覆盖'

        fc._write_cache({'items': []}, 'sw')
        written = expected / 'fundfof_crowding' / fc.CACHE_FILE_NAME
        assert written.exists(), 'fundfof 缓存未落进用例私有目录'
        assert not (_LEGACY_SOURCE_DIRS['fundfof_crowding'] / fc.CACHE_FILE_NAME).exists(), (
            'fundfof 缓存仍写进源码树，#1539 未生效'
        )

    def test_derived_file_paths_under_cache_dir(self, tmp_path, monkeypatch):
        """派生文件路径（latest / track / history）都在解析出的目录下（验收 3）。"""
        root = tmp_path / 'custom'
        monkeypatch.setenv('CACHE_FILE_DIR', str(root))
        cache_dir = Path(fc.fundfof_cache_dir())

        assert Path(fc._cache_file('sw')).parent == cache_dir
        assert Path(fc._cache_file('sw')).name == fc.CACHE_FILE_NAME
        assert Path(fc._cache_file('track')).parent == cache_dir
        assert Path(fc._history_cache_file('sw', 'crowding', 'weekly', 'value')).parent == cache_dir
        assert ic._em_cache_path('000985.SH') == str(cache_dir.parent / 'em_industry_hist' / '000985_SH.parquet')
