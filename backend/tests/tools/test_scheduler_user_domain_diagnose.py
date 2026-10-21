# -*- coding: utf-8 -*-
"""user 域（Postgres）连接诊断的回归网（#2462）。

事故形态：CI runner（GitHub Actions）**没有 IPv6 出口**，而 Supabase 的直连端口
5432 只提供 IPv6 ⇒ libpq 报 `Network is unreachable`。
这句话看不出「该换 pooler 端点」或「该把调度换到有 IPv6 的机器上」，
排查只能靠猜——本文件钉住「诊断要直接给出这两条出路」。

另外钉住一条：两域**各自独立**探测——撞上哪一域就停在哪一域，排查就得多跑一轮。
"""

import socket
import urllib.parse

import pytest
import sqlalchemy

from app.tools import scheduler


def _parsed(url: str):
    return urllib.parse.urlparse(url)


def _only_ipv6(monkeypatch):
    """让 DNS 只解析出 AAAA 记录（Supabase 直连端口的真实形态）。"""
    monkeypatch.setattr(
        scheduler.socket,
        'getaddrinfo',
        lambda *a, **k: [(socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('2406:db8::1', 5432))],
    )


def test_ipv6_only_user_domain_points_to_pooler(monkeypatch):
    """IPv6-only 直连 + 无 IPv6 出口 ⇒ 诊断必须点名 pooler 端点这条出路。"""
    _only_ipv6(monkeypatch)
    exc = RuntimeError(
        '(psycopg2.OperationalError) connection to server at "db.example.supabase.co" '
        '(2406:db8::1), port 5432 failed: Network is unreachable'
    )

    text = scheduler._user_domain_failure_message(
        _parsed('postgresql://postgres:pw@db.example.supabase.co:5432/postgres'), exc
    )

    assert 'IPv6' in text, text
    assert 'pooler' in text, text
    assert 'Network is unreachable' in text, text
    # 凭据不得出现在诊断文案里
    assert ':pw@' not in text, text


def test_generic_user_domain_failure_reports_raw_error(monkeypatch):
    """非「网络不可达」的失败要如实报原始错误（不要一律套 IPv6 结论）。"""
    _only_ipv6(monkeypatch)
    exc = RuntimeError('password authentication failed for user "postgres"')

    text = scheduler._user_domain_failure_message(
        _parsed('postgresql://postgres:pw@db.example.supabase.co:5432/postgres'), exc
    )

    assert 'password authentication failed' in text, text
    assert 'pooler' not in text, '不是网络不可达时，不该误导到 pooler'


def test_ipv4_reachable_host_does_not_get_ipv6_conclusion(monkeypatch):
    """host 有 IPv4 记录时，不该套「只有 IPv6」的结论。"""
    monkeypatch.setattr(
        scheduler.socket,
        'getaddrinfo',
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.2.3.4', 5432))],
    )
    exc = RuntimeError('Network is unreachable')

    text = scheduler._user_domain_failure_message(
        _parsed('postgresql://postgres:pw@db.example.supabase.co:5432/postgres'), exc
    )

    assert 'pooler' not in text, text
    assert 'Network is unreachable' in text, text


def test_resolve_ip_families_handles_dns_failure(monkeypatch):
    """DNS 解析失败不得把诊断带崩（返回空集即可）。"""

    def _boom(*a, **k):
        raise OSError('nope')

    monkeypatch.setattr(scheduler.socket, 'getaddrinfo', _boom)
    assert scheduler._resolve_ip_families('db.example.supabase.co', 5432) == set()


def test_user_domain_is_probed_even_when_market_probe_fails(monkeypatch):
    """两域独立探测：market 探失败也要把 user 域探完（否则排查得多跑一轮）。"""
    from app.core import db_factory

    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('TURSO_DATABASE_URL', 'turso://foo.turso.io/mydb?authToken=tk')
    monkeypatch.setenv('SUPABASE_DATABASE_URL', 'postgresql://postgres:pw@db.example.supabase.co:5432/postgres')

    def _market_boom(*a, **k):
        raise RuntimeError('market boom')

    monkeypatch.setattr(db_factory.DatabaseFactory, 'create', classmethod(lambda cls, *a, **k: _market_boom()))

    user_probed = []

    def _user_engine(*a, **k):
        user_probed.append(True)
        raise sqlalchemy.exc.OperationalError('connection refused')

    monkeypatch.setattr(sqlalchemy, 'create_engine', _user_engine)

    with pytest.raises(Exception):
        scheduler._diagnose_db()

    assert user_probed, 'user 域没有被探测'
