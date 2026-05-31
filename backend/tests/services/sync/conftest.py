# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 12:29
# File : conftest.py
# tests/services/sync/conftest.py
from unittest.mock import patch

import pytest

import app.domains.price_history.models  # noqa: F401
import app.models.sync_log  # noqa: F401


@pytest.fixture(autouse=True)
def skip_lock(monkeypatch):
    """绕过文件锁，避免测试时锁文件冲突"""
    monkeypatch.setattr('app.services.sync.orchestrator.acquire_lock', lambda x: True)


@pytest.fixture
def mock_xalpha():
    with patch('app.services.sync.adapters.xalpha_adapter.xa') as mock:
        yield mock


@pytest.fixture
def mock_akshare():
    with patch('app.services.sync.adapters.akshare_adapter.ak') as mock:
        yield mock
