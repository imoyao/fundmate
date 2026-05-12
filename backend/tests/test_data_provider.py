# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/12 18:36
# File : test_data_provider.py
import pytest

from app.core.database import SessionLocal
from app.domains.funds.models import DailyWorth, Fund
from app.domains.securities.models import Security
from app.services.data_provider import DataProvider


def test_sync_fund_daily_worth(app):
    # 先确保基金信息存在
    with SessionLocal() as db:
        if not db.query(Fund).filter_by(fund_code='000001').first():
            db.add(Fund(fund_code='000001', name='华夏成长'))
            db.commit()
    DataProvider.sync_fund_daily_worth('000001', days_back=30)
    with SessionLocal() as db:
        worths = db.query(DailyWorth).filter_by(fund_code='000001').all()
        assert len(worths) > 0


@pytest.mark.skip(reason='网络波动，待网络稳定后再启用')
def test_sync_security_info(app):
    """同步证券基本信息"""
    DataProvider.sync_security_info('600519', market='CN_A')
    with SessionLocal() as db:
        sec = db.query(Security).filter_by(symbol='600519').first()
        assert sec is not None
        assert sec.name is not None
