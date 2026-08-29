# -*- coding: utf-8 -*-
# File : test_nav_service.py
"""NavService 净值统一入口测试（#1133）。

覆盖此前零测试覆盖的核心分支：
- 库优先：库中存在较新净值时不发起远程请求
- 远程兜底：库中缺失/过旧时触发远程，并回写结果
- 不阻塞：远程异常不影响整体返回
- allow_remote=False：同步请求路径绝不触网（曾因默认值 True 导致 10s 超时）
"""

from datetime import date, timedelta
from unittest.mock import patch

from app.domains.funds.models import DailyWorth
from app.services.nav_service import NavService

# patch 目标：nav_service 模块内引用的名字（视图/服务内 import 的名字）
FETCH = 'app.services.nav_service.FundService._fetch_one_nav'
PERSIST = 'app.services.nav_service.FundService._persist_navs'


def _seed(db, fund_code: str, nav: float, nav_date: date):
    db.add(
        DailyWorth(
            fund_code=fund_code,
            unit_nav=nav,
            acc_nav=nav,
            date=nav_date,
        )
    )
    db.commit()


def test_latest_navs_reads_db_without_remote(db):
    """库中有较新净值 → 直接返回，不发起远程。"""
    _seed(db, '005827', 2.5, date.today())

    with patch(FETCH) as mock_fetch:
        result = NavService.get_latest_navs(db, ['005827'])

    assert result == {'005827': 2.5}
    mock_fetch.assert_not_called()


def test_latest_navs_falls_back_to_remote_when_missing(db):
    """库中无数据 → 触发远程拉取，并回写库。"""
    with patch(FETCH, return_value=1.25) as mock_fetch, patch(PERSIST) as mock_persist:
        result = NavService.get_latest_navs(db, ['110011'])

    assert result == {'110011': 1.25}
    mock_fetch.assert_called_once()
    mock_persist.assert_called_once()


def test_latest_navs_refetches_when_stale(db):
    """库中数据过旧（超出 stale_threshold_days）→ 触发远程刷新并覆盖旧值。"""
    _seed(db, '005827', 2.0, date.today() - timedelta(days=10))

    with patch(FETCH, return_value=2.8) as mock_fetch, patch(PERSIST):
        result = NavService.get_latest_navs(db, ['005827'])

    assert result == {'005827': 2.8}
    mock_fetch.assert_called_once()


def test_remote_failure_does_not_block(db):
    """远程拉取抛异常 → 不阻塞，回退到库中已有值，缺失项静默略过。"""
    _seed(db, '005827', 2.5, date.today())

    with patch(FETCH, side_effect=RuntimeError('网络超时')):
        result = NavService.get_latest_navs(db, ['005827', '999999'])

    assert result == {'005827': 2.5}


def test_allow_remote_false_never_touches_network(db):
    """同步路径 allow_remote=False 绝不触网，即使库中无数据。"""
    with patch(FETCH) as mock_fetch:
        result = NavService.get_latest_navs(db, ['999999'], allow_remote=False)

    assert result == {}
    mock_fetch.assert_not_called()


def test_empty_codes_short_circuit(db):
    """空列表直接返回，不查库也不触网。"""
    with patch(FETCH) as mock_fetch:
        assert NavService.get_latest_navs(db, []) == {}
    mock_fetch.assert_not_called()
