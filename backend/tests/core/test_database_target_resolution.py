# -*- coding: utf-8 -*-
"""运行库连接解析与「连错库」防线（#2344）

## 为什么要有这组用例

2026-10-18 实测事故：用 `--target-file` 跑 334 只基金的修复性重同步，日志报
`enriched 0 / skipped 0 / errors 0`、`status=success`、耗时 9.7 秒——**一只都没处理**。

机制（取证后修正过一次，见 issue #2344 更正评论）：CLI 的会话本来就经
`_RoutingSessionMaker` 走 db_factory，真正的坑是

1. `APP_ENV` 未设 → `get_app_env()` 返回 **production** → `for_app('production')`
   只看 `TURSO_DATABASE_URL` / `DATABASE_URL`，**`DEV_DATABASE_URL` 被静默忽略**
   → 回退到 cwd 相对的 `sqlite:///./invest.db`（在 worktree 里就是一个空库）；
2. `database.SQLALCHEMY_DATABASE_URL` 是与引擎解析**并行的第二套口径**，读它做推断
   可能拿到一个根本没在用的库——排查时被它带偏过。

本组用例钉住三件事：解析口径唯一、忽略的变量可见、配置指向的库不存在时拒绝继续。
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import database
from app.core.db_factory import (
    app_database_configured_vars,
    app_database_source_var,
    app_database_url,
    get_app_env,
    ignored_app_db_env_vars,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

DB_ENV_VARS = (
    'APP_ENV',
    'FLASK_ENV',
    'DATABASE_URL',
    'DEV_DATABASE_URL',
    'STAGING_DATABASE_URL',
    'TURSO_DATABASE_URL',
)


def _neutral_env(**overrides: str) -> dict[str, str]:
    """子进程环境：先中和本机 .env 里的真实库串，再叠加用例指定值。

    不中和的后果（#1727 同一教训）：子进程继承真 Turso / 真 dev 串，断言全部失去意义。
    """
    base = {k: v for k, v in os.environ.items() if k not in DB_ENV_VARS}
    return {**base, **overrides}


@pytest.fixture(autouse=True)
def _clean_db_env(monkeypatch, tmp_path):
    """每个用例从「什么都没配 + cwd 下无 invest.db」的干净状态出发。"""
    for name in DB_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    yield


class TestAppDatabaseUrl:
    """唯一解析入口 `app_database_url()` 的优先级（#2344 验收项）"""

    def test_app_env_unset_falls_back_to_production_branch(self, monkeypatch):
        """APP_ENV 未设 → production 分支：只认 TURSO_/DATABASE_URL"""
        assert get_app_env() == 'production'
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///D:/x/prod.db')
        assert app_database_url() == 'sqlite:///D:/x/prod.db'

    def test_dev_database_url_ignored_when_app_env_unset(self, monkeypatch):
        """**本次事故的根因**：APP_ENV 未设时 DEV_DATABASE_URL 静默失效"""
        monkeypatch.setenv('DEV_DATABASE_URL', 'sqlite:///D:/x/dev.db')
        assert app_database_url() == 'sqlite:///./invest.db', 'APP_ENV 未设时 DEV_ 变量不参与解析'
        assert ignored_app_db_env_vars() == ['DEV_DATABASE_URL'], '被忽略的变量必须被报出来'

    def test_development_prefers_dev_url(self, monkeypatch):
        monkeypatch.setenv('APP_ENV', 'development')
        monkeypatch.setenv('DEV_DATABASE_URL', 'sqlite:///D:/x/dev.db')
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///D:/x/prod.db')
        assert app_database_url() == 'sqlite:///D:/x/dev.db'
        assert ignored_app_db_env_vars() == ['DATABASE_URL'], 'development 下 DATABASE_URL 不参与解析且要报出来'

    def test_production_prefers_turso(self, monkeypatch):
        """production 分支是 ``TURSO or DATABASE_URL``：两者都参与解析，TURSO 胜出。

        注意 ``DATABASE_URL`` 在这里**不算「被忽略」**——它是合法回退（过渡期设计），
        只是排在后面没赢；把它算成 ignored 会让「production 只配了 DATABASE_URL」这种
        正常部署报出一堆假警告。
        """
        monkeypatch.setenv('TURSO_DATABASE_URL', 'libsql://turso.example')
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///D:/x/prod.db')
        assert app_database_url() == 'libsql://turso.example'
        assert ignored_app_db_env_vars() == []
        assert app_database_source_var() == 'TURSO_DATABASE_URL'
        assert app_database_configured_vars() == ['TURSO_DATABASE_URL', 'DATABASE_URL']

    def test_production_database_url_only_is_effective(self, monkeypatch):
        """只配 DATABASE_URL 的 production 部署是常态：它必须算「生效」而非「忽略」"""
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///D:/x/prod.db')
        assert app_database_source_var() == 'DATABASE_URL'
        assert ignored_app_db_env_vars() == []

    def test_configured_vars_reflects_participating_only(self, monkeypatch):
        monkeypatch.setenv('APP_ENV', 'development')
        monkeypatch.setenv('DEV_DATABASE_URL', 'sqlite:///D:/x/dev.db')
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///D:/x/prod.db')
        assert app_database_configured_vars() == ['DEV_DATABASE_URL']


class TestLegacySymbolSharesOneResolver:
    """`SQLALCHEMY_DATABASE_URL` 必须与引擎解析一致（并行口径是事故的帮凶）

    ⚠️ 这里**必须**用子进程探针，不能 `importlib.reload(app.core.database)`：
    该模块在导入期执行 `Base = declarative_base()`，reload 会换一个**空 metadata**，
    而所有模型已注册在旧 Base 上——同进程后续用例随即 `KeyError: 'funds'` /
    建表缺失。实测过一次：整目录跑 tests/core 从 432 全过变成 106 失败，
    而真凶是这条测试自己。同类探针见 test_db_lazy_engine.py。
    """

    @staticmethod
    def _probe(env: dict[str, str]) -> str:
        """在干净子进程里打印 legacy 符号与唯一解析入口的取值。"""
        code = (
            'from app.core.database import SQLALCHEMY_DATABASE_URL;'
            'from app.core.db_factory import app_database_url;'
            'print(SQLALCHEMY_DATABASE_URL);'
            'print(app_database_url())'
        )
        proc = subprocess.run(
            [sys.executable, '-c', code],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(BACKEND_DIR),
            env=_neutral_env(**env),
        )
        assert proc.returncode == 0, f'探针子进程失败:\n{proc.stderr}'
        lines = [line for line in proc.stdout.splitlines() if '://' in line]
        return '\n'.join(lines[-2:])

    def test_legacy_symbol_matches_resolver_under_development(self):
        out = self._probe(
            {
                'APP_ENV': 'development',
                'DEV_DATABASE_URL': 'sqlite:///D:/x/dev.db',
                'DATABASE_URL': 'sqlite:///D:/x/prod.db',
            }
        )
        assert out == 'sqlite:///D:/x/dev.db\nsqlite:///D:/x/dev.db', out

    def test_legacy_symbol_matches_resolver_under_production(self):
        out = self._probe({'DATABASE_URL': 'sqlite:///D:/x/prod.db'})
        assert out == 'sqlite:///D:/x/prod.db\nsqlite:///D:/x/prod.db', out

    def test_legacy_symbol_no_longer_honours_database_url_under_development(self, monkeypatch):
        """旧实现在 development 下会读出 DATABASE_URL——那正是「与引擎不一致」的偏差。

        改动后它与引擎一致（都走 DEV_DATABASE_URL 口径），因此**不再是**那个 URL。
        """
        monkeypatch.setenv('APP_ENV', 'development')
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///D:/x/only-prod.db')
        assert app_database_url() != 'sqlite:///D:/x/only-prod.db'


class TestTargetPreflight:
    """预检：配置指向的库不存在 → 拒绝继续（否则 SQLite 静默建空库）"""

    def test_missing_configured_file_is_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setenv('APP_ENV', 'development')
        monkeypatch.setenv('DEV_DATABASE_URL', f'sqlite:///{tmp_path / "nope.db"}')
        err = database.check_database_target_ready()
        assert err is not None
        assert '不存在' in err and '空库' in err, '错误文案要说清后果（静默建空库）与处置'

    def test_existing_configured_file_passes(self, monkeypatch, tmp_path):
        target = tmp_path / 'ok.db'
        target.touch()
        monkeypatch.setenv('APP_ENV', 'development')
        monkeypatch.setenv('DEV_DATABASE_URL', f'sqlite:///{target}')
        assert database.check_database_target_ready() is None

    def test_unconfigured_fresh_env_is_allowed(self):
        """什么都没配 + 文件不存在 = 全新环境，交给 init_db 建表，不得拦"""
        assert database.check_database_target_ready() is None

    def test_remote_url_is_not_checked_locally(self, monkeypatch):
        monkeypatch.setenv('TURSO_DATABASE_URL', 'libsql://turso.example')
        assert database.check_database_target_ready() is None


class TestCliPreflightExitCode:
    """CLI 预检必须**以非 0 退出**（#2344 验收项）。

    「拦了但退出码仍是 0」与没拦等价：CI / 脚本只看退出码。
    旧实现的 `if __name__ == '__main__': main()` 正好丢弃了返回值——
    所以这条用例钉的是「return 值接得进退出码」这件事本身。
    """

    @staticmethod
    def _run_cli(env: dict[str, str], extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
        backend_dir = BACKEND_DIR
        return subprocess.run(
            [sys.executable, str(backend_dir / 'app' / 'tools' / 'sync_metadata.py'), *(extra_args or [])],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(backend_dir),
            env=_neutral_env(**env),
        )

    def test_missing_target_exits_non_zero_and_explains(self, tmp_path):
        missing = tmp_path / 'definitely-not-here.db'
        proc = self._run_cli(
            {
                'APP_ENV': 'development',
                'DEV_DATABASE_URL': f'sqlite:///{missing.as_posix()}',
            },
            extra_args=['--job', '__no_such_job__'],
        )
        assert proc.returncode != 0, f'预检失败却返回 0，等于没拦。stdout={proc.stdout[-500:]}'
        assert '不存在' in proc.stderr and '空库' in proc.stderr, proc.stderr[-500:]
        assert not missing.exists(), '预检必须在 SQLite 建库之前拦下'

    def test_snapshot_export_is_also_preflighted(self, tmp_path):
        """`--snapshot` 同样会碰库：导出空快照与「什么都没做」等价，必须一起拦

        预检曾被放在 `--snapshot` 分支之后 → 那条路径完全绕过它。
        变异探针要求：去掉 snapshot 的预检覆盖时，**预检的特定报错文案**不出现、
        改成 snapshot 分支自己的报错（"市场域库不存在"），用例要能咬住这个差异。
        """
        missing = tmp_path / 'no-such.db'
        proc = self._run_cli(
            {
                'APP_ENV': 'development',
                'DEV_DATABASE_URL': f'sqlite:///{missing.as_posix()}',
            },
            extra_args=['--snapshot', str(tmp_path / 'out.snapshot')],
        )
        # 预检拦下时：退出码 2、报错含「配置的运行库文件不存在」（在 stderr）且快照文件未建
        assert proc.returncode == 2, (
            f'预检失败必须退出码 2，实际 {proc.returncode}。stdout={proc.stdout[-500:]} stderr={proc.stderr[-500:]}'
        )
        assert '配置的运行库文件不存在' in proc.stderr, (
            '预检报错要有特定文案（在 stderr），否则无法与 snapshot 分支自查区分'
        )
        assert not (tmp_path / 'out.snapshot').exists(), '预检失败却导出了快照文件'

    def test_cli_prints_target_before_running(self, tmp_path):
        """启动输出里能直接看出连的是哪个库文件（#2344 验收项）"""
        existing = tmp_path / 'ok.db'
        existing.touch()
        proc = self._run_cli(
            {
                'APP_ENV': 'development',
                'DEV_DATABASE_URL': f'sqlite:///{existing.as_posix()}',
            },
            # 预检放行后，给一个不存在的 job 让它在 job 解析处失败——顺带证明
            # 「预检不是唯一拦点、也没把后续流程吞掉」
            extra_args=['--job', '__no_such_job__'],
        )
        assert '运行库目标' in proc.stdout, proc.stdout[-800:]
        assert existing.as_posix() in proc.stdout, '报告里要能看到实际文件路径'

    """连接目标必须看得见（#2344 验收项：日志/启动输出能看出连的是哪个库文件）"""

    def test_report_mentions_url_and_ignored_vars(self, monkeypatch):
        monkeypatch.setenv('DEV_DATABASE_URL', 'sqlite:///D:/x/dev.db')
        report = database.describe_database_targets()
        assert 'production' in report
        assert 'sqlite:///./invest.db' in report
        assert 'DEV_DATABASE_URL' in report and '忽略' in report

    def test_report_marks_unconfigured_default(self):
        report = database.describe_database_targets()
        assert 'cwd' in report, '未配置时要说明用的是 cwd 缺省'

    def test_report_names_the_winner_not_just_the_configured_ones(self, monkeypatch):
        """配了不等于生效：被前者覆盖的变量必须点名，否则排查会被带偏"""
        monkeypatch.setenv('TURSO_DATABASE_URL', 'libsql://turso.example')
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///D:/x/prod.db')
        report = database.describe_database_targets()
        assert '来自 TURSO_DATABASE_URL' in report
        assert '被覆盖' in report and 'DATABASE_URL' in report
