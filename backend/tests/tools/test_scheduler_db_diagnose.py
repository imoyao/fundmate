# -*- coding: utf-8 -*-
"""`app/tools/scheduler.py::_diagnose_db` 的失败语义测试（#1490）。

事故形态：每日调度自 2026-09-04 起 **25 次全红、零成功**，报错是
``Hrana: api error: status=308 Permanent Redirect, body=Redirecting``。
而当时这段诊断的文案写的是「host 已被服务端重定向」——把排查引向
「Turso 迁移了 host」这个错误方向；真因是两个更朴素的问题：

1. 注入的 secret 里**没有 authToken**（只有 host）；
2. `sqlalchemy-libsql` 0.2.0 方言默认 `secure=False` ⇒ 客户端走**明文 http**，
   而 Turso 边缘对明文请求回 308（跳同路径 https），客户端不自动跟随。

本文件钉住「诊断要说人话、且在连上之前就说人话」：
缺 authToken 时**快速失败**并点名 authToken，而不是让人去查一个看不懂的 308。
"""

import pytest

from app.tools.scheduler import _diagnose_db


def _prod_env(monkeypatch, turso_url: str):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('TURSO_DATABASE_URL', turso_url)
    monkeypatch.setenv('DATABASE_URL', turso_url)
    monkeypatch.setenv('SUPABASE_DATABASE_URL', 'postgresql://u:p@db.example.supabase.co:5432/postgres')


def test_missing_auth_token_fails_fast(monkeypatch):
    """Turso 连接串没有 authToken ⇒ 立刻失败并点名 authToken（而不是连上去撞 308）。"""
    _prod_env(monkeypatch, 'turso://foo.turso.io/mydb')

    with pytest.raises(RuntimeError) as exc:
        _diagnose_db()

    assert 'authToken' in str(exc.value)


def test_missing_auth_token_does_not_attempt_connection(monkeypatch):
    """失败必须发生在**建连之前**：连都不该连（否则又是一条看不懂的 308）。"""
    from app.core import db_factory

    called = []
    monkeypatch.setattr(
        db_factory.DatabaseFactory,
        'create',
        classmethod(lambda cls, *a, **k: called.append(a) or None),
    )
    _prod_env(monkeypatch, 'turso://foo.turso.io/mydb')

    with pytest.raises(RuntimeError):
        _diagnose_db()

    assert called == [], '缺 token 时不应尝试建连'


def test_non_turso_url_skips_probe(monkeypatch):
    """非 Turso（本地 SQLite / Postgres）不做 Hrana 探测，也不因缺 token 而失败。"""
    _prod_env(monkeypatch, 'sqlite:///./invest.db')

    # 不抛异常即通过（探测分支不进入）
    _diagnose_db()
