# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/1 20:49
# File : test_template_config.py
# tests/services/importer/test_template_config.py

from app.services.importer.template_config import get_template_filepath, get_template_info


def test_get_template_info_exists():
    info = get_template_info('fund')
    assert info is not None
    assert info.filename == 'showbuy_fund_template.csv'


def test_get_template_info_missing():
    assert get_template_info('nonexistent') is None


def test_get_template_filepath():
    path = get_template_filepath('fund')
    assert path is not None
    assert path.name == 'showbuy_fund_template.csv'
