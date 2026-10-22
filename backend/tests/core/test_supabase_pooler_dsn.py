# -*- coding: utf-8 -*-
"""Supabase 直连串 → pooler 端点改写（#2460 / #2462）。

为什么需要这条改写：Supabase 新项目的**直连**端点 `db.<ref>.supabase.co:5432`
只给 IPv6，而 GitHub Actions runner 没有 IPv6 出口 ⇒ libpq 报
`Network is unreachable`，每日调度整轮跑不起来（#1490 挂了 58 天）。
pooler 端点有 A 记录，且沿用同一份 DB 密码（用户名改 `postgres.<ref>`），
所以「给出端点」即可就地改写，不必改 secret、更不必把密码搬进仓库。

本文件钉住三组事：

1. **改写的形状**：host / 端口 / 用户名换掉，密码与库名、query 参数原样保留；
2. **不该动的场合**：没给端点、已经是 pooler、别的 Postgres、SQLite —— 一律零改动；
3. **真的接上了线**：`DatabaseConfig.for_user()` 与 `DatabaseFactory.build()`
   实际建引擎时用的是改写后的 URL（只测纯函数会被「函数写了但没人调」骗过）。
"""

import urllib.parse

import pytest

from app.core import db_factory

REF = 'owhbssypqaghpnjoxlkx'
DIRECT_HOST = f'db.{REF}.supabase.co'
POOLER_HOST = 'aws-1-ap-southeast-1.pooler.supabase.com'
DIRECT_URL = f'postgresql://postgres:{urllib.parse.quote("p@ss w0rd", safe="")}@{DIRECT_HOST}:5432/postgres'


@pytest.fixture(autouse=True)
def _clear_pooler_env(monkeypatch):
    """每个用例从「没配端点」出发，避免开发机上的真实 env 影响断言。"""
    monkeypatch.delenv(db_factory.POOLER_HOST_ENV, raising=False)
    monkeypatch.delenv(db_factory.POOLER_PORT_ENV, raising=False)


# ── 1. 改写的形状 ──


def test_direct_url_is_rewritten_to_pooler():
    """直连串 ⇒ pooler 串：host 换掉、用户名为租户限定形式、密码原样保留。"""
    out = db_factory.rewrite_supabase_direct_to_pooler(DIRECT_URL, pooler_host=POOLER_HOST)
    parsed = urllib.parse.urlparse(out)

    assert parsed.hostname == POOLER_HOST
    assert parsed.username == f'postgres.{REF}'
    # 密码按**原始百分号编码**原样搬运：Python 3.12 的 urlparse().password 不解码，
    # 若改写时再 quote 一次就会二次编码（p%40ss → p%2540ss）⇒ 连库报密码错。
    assert f'@{POOLER_HOST}' in out
    assert ':p%40ss%20w0rd@' in out, f'密码段被改动：{parsed.netloc}'
    assert parsed.path == '/postgres'
    assert parsed.scheme == 'postgresql'


def test_pooler_port_defaults_to_session_mode_5432():
    """默认端口是 5432（session 模式）——语义最接近直连，避开事务池的换连接语义。"""
    out = db_factory.rewrite_supabase_direct_to_pooler(DIRECT_URL, pooler_host=POOLER_HOST)
    assert urllib.parse.urlparse(out).port == db_factory.POOLER_DEFAULT_PORT == 5432


def test_pooler_port_can_be_overridden_by_env(monkeypatch):
    """需要压连接数时可用 `SUPABASE_POOLER_PORT=6543` 走 transaction 模式。"""
    monkeypatch.setenv(db_factory.POOLER_HOST_ENV, POOLER_HOST)
    monkeypatch.setenv(db_factory.POOLER_PORT_ENV, '6543')

    out = db_factory.rewrite_supabase_direct_to_pooler(DIRECT_URL)

    assert urllib.parse.urlparse(out).port == 6543


def test_invalid_port_env_falls_back_to_default():
    """端口写错不许炸启动：回退 5432（否则一条拼错的 env 会让整轮调度起不来）。"""
    out = db_factory.rewrite_supabase_direct_to_pooler(DIRECT_URL, pooler_host=POOLER_HOST, pooler_port='not-a-port')
    assert urllib.parse.urlparse(out).port == 5432


def test_query_params_and_dbname_are_preserved(monkeypatch):
    """query 里的连接参数（如 sslmode）是调用方的意图，改写时不许丢。"""
    monkeypatch.setenv(db_factory.POOLER_HOST_ENV, POOLER_HOST)
    url = f'{DIRECT_URL}?sslmode=require&application_name=fundmate'

    parsed = urllib.parse.urlparse(db_factory.rewrite_supabase_direct_to_pooler(url))
    params = urllib.parse.parse_qs(parsed.query)

    assert parsed.path == '/postgres'
    assert params == {'sslmode': ['require'], 'application_name': ['fundmate']}


# ── 2. 不该动的场合（零行为变化）──


def test_no_pooler_host_keeps_direct_url():
    """未配端点 ⇒ 原样返回。本机有 IPv6 时直连照旧可用，不能因为代码升级就连不上。"""
    assert db_factory.rewrite_supabase_direct_to_pooler(DIRECT_URL) == DIRECT_URL


def test_already_pooler_url_is_idempotent(monkeypatch):
    """已经把 secret 换成 pooler 串的人，不该被二次改写（幂等）。"""
    monkeypatch.setenv(db_factory.POOLER_HOST_ENV, POOLER_HOST)
    pooler_url = f'postgresql://postgres.{REF}:pw@{POOLER_HOST}:5432/postgres'

    assert db_factory.rewrite_supabase_direct_to_pooler(pooler_url) == pooler_url


@pytest.mark.parametrize(
    'url',
    [
        'postgresql://user:pw@db.example.com:5432/app',  # 其它 Postgres（Neon 等）
        'postgresql://user:pw@ep-cool-name-123.eu-central-1.aws.neon.tech/neondb',
        # 同一个 supabase.co 下但**不是**数据库直连端点的 host（如 API 域名）不动：
        # 判据是 `db.` 前缀 + `.supabase.co` 后缀，缺一不改——否则把用户写错的
        # 连接串「顺手修正」成能连的库，问题被藏起来（#2460 探针 P3 咬的就是这条）。
        f'postgresql://user:pw@api.{REF}.supabase.co:5432/postgres',
        'sqlite:///./invest.db',
        'sqlite+libsql://foo.turso.io/mydb?authToken=tk',
        '',
    ],
)
def test_other_urls_are_untouched(url, monkeypatch):
    monkeypatch.setenv(db_factory.POOLER_HOST_ENV, POOLER_HOST)
    assert db_factory.rewrite_supabase_direct_to_pooler(url) == url


# ── 3. 接线：真的在建引擎时生效 ──


def test_for_user_rewrites_when_pooler_host_is_set(monkeypatch):
    """`DatabaseConfig.for_user` 是 user 域 URL 的唯一入口，改写必须在这里生效。

    只钉纯函数是不够的：诊断日志与 engine 都读 `.url`，接线漏了就等于没修。
    """
    monkeypatch.setenv('SUPABASE_DATABASE_URL', DIRECT_URL)
    monkeypatch.setenv(db_factory.POOLER_HOST_ENV, POOLER_HOST)

    cfg = db_factory.DatabaseConfig.for_user('production')

    assert urllib.parse.urlparse(cfg.url).hostname == POOLER_HOST
    assert urllib.parse.urlparse(cfg.url).username == f'postgres.{REF}'


def test_for_user_keeps_direct_when_pooler_host_is_absent(monkeypatch):
    """回归闸门：不配端点时行为与改动前完全一致（否则等于偷偷换库）。"""
    monkeypatch.setenv('SUPABASE_DATABASE_URL', DIRECT_URL)

    cfg = db_factory.DatabaseConfig.for_user('production')

    assert urllib.parse.urlparse(cfg.url).hostname == DIRECT_HOST


def test_build_creates_engine_with_rewritten_url(monkeypatch):
    """最外层确认：`DatabaseFactory.build()` 交给 create_engine 的是 pooler 串。"""
    captured = {}

    def _fake_create_engine(url, **kwargs):  # noqa: ANN001, ARG001
        captured['url'] = url
        return object()

    monkeypatch.setenv('SUPABASE_DATABASE_URL', DIRECT_URL)
    monkeypatch.setenv(db_factory.POOLER_HOST_ENV, POOLER_HOST)
    monkeypatch.setattr(db_factory, 'create_engine', _fake_create_engine)

    db_factory.DatabaseFactory.build(db_factory.DOMAIN_USER, env='production')

    assert urllib.parse.urlparse(captured['url']).hostname == POOLER_HOST
    assert urllib.parse.urlparse(captured['url']).port == 5432
