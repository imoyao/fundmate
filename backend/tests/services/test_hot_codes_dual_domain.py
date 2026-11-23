# -*- coding: utf-8 -*-
"""#3091 回归：热集口径在**双库**拓扑下也必须读得到、且读的是 user 库。

## 为什么这个文件不放进 `test_local_checks.py` 顺手跑

`tests/conftest.py` 的 `app` 夹具把 `engine`（market）与 `user_engine`（user）都指到
**同一个**临时文件库，并把 `DatabaseFactory._engines` 里两个域指到同一对引擎。这个形态
让「裸 `text()` 查 positions」在本地与 PR 上一直绿，而在生产（market=Turso / user=Supabase）
上必然报「热集来源表缺失: positions」——2026-11-12 起每日调度连续红 6 天的真因。

盲区是**结构性**的（同 `scripts/check_cross_domain_query.py` 头部「不覆盖」第 3 条：
字符串形式的原始 SQL 静态扫不到），所以只能用**真的摆出双库拓扑**的动态用例来堵：

| 用例 | 钉住的行为 |
|---|---|
| `test_hot_codes_reads_user_db_not_market_db` | 读的是 user 库：market 库里放同名表 + 不同内容当干扰项 |
| `test_missing_user_table_raises_plain_exception` | 缺表抛 `HotCodesUnavailable`（普通异常），**不再是 `SystemExit`** |
| `test_run_due_checks_survives_dual_domain` | 整条巡检通道（冷集 + 份额）在生产拓扑下不 error、且落库成基线 |
| `test_system_exit_from_check_is_contained` | 巡检里任何 `BaseException` 都只变成一行 `error`，不带走进程 |
"""

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.database import Base, get_session
from app.core.db_factory import DATA_DOMAIN_REGISTRY, DOMAIN_APP, DOMAIN_MARKET, DOMAIN_USER, DatabaseFactory
from app.services import cold_set_guard, local_checks, position_share_audit
from app.services.hot_codes import HotCodesUnavailable, read_hot_codes


def _user_domain_tables():
    """user 域的表名（唯一事实源 = `DATA_DOMAIN_REGISTRY`，不手写清单）。"""
    return [
        name for name, domain in DATA_DOMAIN_REGISTRY.items() if domain == DOMAIN_USER and name in Base.metadata.tables
    ]


def _file_engine(path):
    """测试库引擎：临时文件 + QueuePool（与 conftest 的连接/事务模型一致）。"""
    return create_engine(
        f'sqlite:///{path.as_posix()}',
        connect_args={'check_same_thread': False, 'timeout': 5},
        poolclass=QueuePool,
    )


def _patch_domains(monkeypatch, market, user):
    """把两个域分别指到两套引擎上（模块属性 / 工厂缓存 / 会话工厂三处都要改）。

    第三处不能省：`app` 夹具会把 `db_factory.user_session_factory` 换成一个绑在**它自己的**
    测试库上的 sessionmaker（`tests/conftest.py`），`user_session_factory()` 是**晚绑定**
    调用，所以只改 `_engines` 还不够——第一版实测读到的是 app 夹具的空库 ⇒ 热集恒为空集。
    """
    monkeypatch.setattr('app.core.database.engine', market)
    monkeypatch.setattr('app.core.database.user_engine', user)
    monkeypatch.setattr(
        DatabaseFactory,
        '_engines',
        {DOMAIN_APP: market, DOMAIN_MARKET: market, DOMAIN_USER: user},
    )
    import app.core.db_factory as db_factory

    monkeypatch.setattr(db_factory, 'user_session_factory', lambda: sessionmaker(bind=user))
    monkeypatch.setattr(db_factory, 'market_session_factory', lambda: sessionmaker(bind=market))


@pytest.fixture
def split_db(app, tmp_path, monkeypatch):
    """生产形态：market 库里**没有** user 域的表，user 库是独立文件。"""
    market = _file_engine(tmp_path / '_split_market.db')
    user = _file_engine(tmp_path / '_split_user.db')
    Base.metadata.create_all(bind=market)
    Base.metadata.create_all(bind=user)
    # 复刻生产：market 库里没有 user 域的表（先全建再删，省去按依赖顺序建表的麻烦；
    # 「单库时这行删不到东西」正是本用例要防的盲区）
    market_tables = _user_domain_tables()
    assert market_tables, 'user 域表清单不能为空，否则本夹具就成了单库'
    with market.begin() as conn:
        for name in market_tables:
            conn.execute(text('DROP TABLE IF EXISTS %s' % name))
    _patch_domains(monkeypatch, market, user)
    yield market, user
    market.dispose()
    user.dispose()


@pytest.fixture
def fake_domains(app, tmp_path, monkeypatch):
    """一对**手搓**的同名表：只保留 `symbol` 列，用来分辨「到底读了哪个库」。

    `app` 必须显式列进签名：autouse 的 `clean_db` 会拉起 `app` 夹具，而它同样会重写
    `DatabaseFactory._engines`；不声明依赖时两者的执行顺序不保证，本夹具的引擎可能被
    它覆盖掉（第一版实测：读到 app 夹具的空库 ⇒ 断言拿到的热集是空集）。
    """
    market = _file_engine(tmp_path / '_fake_market.db')
    user = _file_engine(tmp_path / '_fake_user.db')
    with market.begin() as conn:
        for table in ('positions', 'watchlist', 'transactions'):
            conn.execute(text('CREATE TABLE %s (symbol TEXT)' % table))
        conn.execute(text("INSERT INTO positions (symbol) VALUES ('999999')"))
    with user.begin() as conn:
        for table in ('positions', 'watchlist', 'transactions'):
            conn.execute(text('CREATE TABLE %s (symbol TEXT)' % table))
        conn.execute(text("INSERT INTO positions (symbol) VALUES ('000001')"))
        conn.execute(text("INSERT INTO transactions (symbol) VALUES ('519771')"))
        # 非 6 位数字的标的（带前缀/带市场后缀）不算场外基金代码，不进热集
        conn.execute(text("INSERT INTO watchlist (symbol) VALUES ('SH600519')"))
    _patch_domains(monkeypatch, market, user)
    yield market, user
    market.dispose()
    user.dispose()


def test_hot_codes_reads_user_db_not_market_db(fake_domains):
    """热集必须来自 user 库：market 库里那张同名 `positions` 是干扰项。"""
    market, user = fake_domains
    assert inspect(market).has_table('positions') and inspect(user).has_table('positions')

    codes = read_hot_codes()

    assert codes == {'000001', '519771'}, '读到 market 库的 999999 就说明取数落错了域'
    assert '999999' not in codes


def test_missing_user_table_raises_plain_exception(app, tmp_path):
    """缺表要抛普通异常（`HotCodesUnavailable`），不能是 `SystemExit`。

    `SystemExit` 会穿透巡检的 `except Exception`，把已经跑完的每日调度进程带走
    （#3091：退出码 1 + 摘要没写 + 告警卡把真因写成「可能崩在建连阶段」）。

    这里刻意用一个**一次性引擎 + 显式会话**（`read_hot_codes(session=...)`），不接管全局
    引擎：`clean_db` 的收尾会按「当前 bind 有哪些表」逐表 DELETE，删掉一张全局可见的
    user 表会让它自己在 teardown 里报 `no such table`（第一版实测踩到）。
    """
    eng = _file_engine(tmp_path / '_partial_user.db')
    with eng.begin() as conn:
        conn.execute(text('CREATE TABLE positions (symbol TEXT)'))
        conn.execute(text('CREATE TABLE watchlist (symbol TEXT)'))
        # 故意缺 transactions：三张来源表缺一张就必须报错，不能按「另外两张够用」继续
    db = Session(bind=eng)
    try:
        with pytest.raises(HotCodesUnavailable) as err:
            read_hot_codes(db)
    finally:
        db.close()
        eng.dispose()

    assert 'transactions' in str(err.value)
    assert not isinstance(err.value, SystemExit)


def test_run_due_checks_survives_dual_domain(split_db):
    """整条巡检通道在生产拓扑下不 error，且结论落库成基线。

    修复前：冷集巡检一开跑就 `SystemExit`（market 库里没有 positions），进程在写
    `data/last_run_summary.json` **之前**退出 ⇒ 本次 run 被判红。
    """
    results = local_checks.run_due_checks()
    statuses = {row['job_name']: row['status'] for row in results}

    assert set(statuses) == {cold_set_guard.GUARD_JOB_NAME, position_share_audit.JOB_NAME}
    assert statuses[cold_set_guard.GUARD_JOB_NAME] == 'success'
    assert 'error' not in statuses.values(), statuses

    # 落库成基线：否则 `due_checks` 会认为「从未跑过」并每天重试（#3091 连红 6 天的形态）
    with get_session() as db:
        rows = db.execute(text('SELECT job_name FROM sync_logs')).fetchall()
    assert cold_set_guard.GUARD_JOB_NAME in {row[0] for row in rows}


def test_system_exit_from_check_is_contained():
    """巡检是旁路：`SystemExit` 也只能变成它自己那一行 `error`。"""
    spec = local_checks.LocalCheckSpec(
        job_name='probe',
        cron='10 4 * * mon',
        runner=lambda: (_ for _ in ()).throw(SystemExit('来源表缺失')),
        description='探针',
    )

    result = local_checks.run_local_check(spec)

    assert result['status'] == 'error'
    assert '来源表缺失' in result['error']
