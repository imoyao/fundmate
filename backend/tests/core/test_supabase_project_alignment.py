# -*- coding: utf-8 -*-
"""Supabase 项目一致性自检（#2764）。

`SUPABASE_URL`（Auth / JWKS）与 `SUPABASE_DATABASE_URL`（user 域库）是两个独立变量。
配成不同项目时系统不会报任何错——验签通过、写库也成功，只是「认证主体在 A 项目、
users 映射在 B 项目」，表现为同一个邮箱两条记录、用户名解析串到另一个项目。
本文件钉住两件事：① ref 抽取对三种真实连接串形态都成立；② 不一致必须 fail fast。
"""

import pytest

from app.core.db_factory import supabase_project_ref, validate_supabase_project_alignment


@pytest.mark.parametrize(
    ('url', 'expected'),
    [
        # 项目 URL（SUPABASE_URL / 前端 VITE_SUPABASE_URL）
        ('https://abcdefghijklmnop.supabase.co', 'abcdefghijklmnop'),
        ('https://abcdefghijklmnop.supabase.co/', 'abcdefghijklmnop'),
        # 直连串：db.<ref>.supabase.co
        (
            'postgresql://postgres:pwd@db.abcdefghijklmnop.supabase.co:5432/postgres',
            'abcdefghijklmnop',
        ),
        # pooler 串：host 里没有 ref，用户名是 postgres.<ref>
        (
            'postgresql://postgres.abcdefghijklmnop:pwd@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres',
            'abcdefghijklmnop',
        ),
        # 非 Supabase（Neon 灾备 / 本地 SQLite）：抽不出就不猜
        ('postgresql://user:pwd@neon.example.com:5432/db', None),
        ('sqlite:///./invest.db', None),
        ('', None),
    ],
)
def test_supabase_project_ref(url, expected):
    assert supabase_project_ref(url) == expected


def test_mismatch_raises(monkeypatch):
    """auth 与 db 指向不同项目 → 拒绝启动，而不是默默跑。"""
    monkeypatch.setenv('SUPABASE_URL', 'https://aaa.supabase.co')
    monkeypatch.setenv(
        'SUPABASE_DATABASE_URL',
        'postgresql://postgres:pwd@db.bbb.supabase.co:5432/postgres',
    )
    with pytest.raises(RuntimeError, match='不同的 Supabase 项目'):
        validate_supabase_project_alignment()


def test_pooler_url_counts_as_same_project(monkeypatch):
    """pooler 端点（无 ref 的 host）也要能认出来，否则生产自检会漏。"""
    monkeypatch.setenv('SUPABASE_URL', 'https://ccc.supabase.co')
    monkeypatch.setenv(
        'SUPABASE_DATABASE_URL',
        'postgresql://postgres.ccc:pwd@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres',
    )
    assert validate_supabase_project_alignment() == 'ccc'


def test_missing_side_skips(monkeypatch):
    """只配一侧（本地单库 / 只开 Auth）没有可比对象，不得报错。"""
    monkeypatch.setenv('SUPABASE_URL', 'https://ccc.supabase.co')
    monkeypatch.delenv('SUPABASE_DATABASE_URL', raising=False)
    assert validate_supabase_project_alignment() is None


def test_non_supabase_database_skips(monkeypatch):
    """user 域换成 Neon 等非 Supabase PG 属既有设计（§7 灾备），不得误报。"""
    monkeypatch.setenv('SUPABASE_URL', 'https://ccc.supabase.co')
    monkeypatch.setenv('SUPABASE_DATABASE_URL', 'postgresql://u:p@neon.example.com:5432/db')
    assert validate_supabase_project_alignment() is None
