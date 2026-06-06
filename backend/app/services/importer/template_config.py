# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/1 20:47
# File : template_config.py
# app/services/importer/template_config.py
"""
导入模板配置。

集中管理所有模板文件的名称和路径，提供统一的获取方式。
不依赖文件系统，便于测试。
"""

from dataclasses import dataclass
from pathlib import Path

import app


@dataclass(frozen=True)
class TemplateInfo:
    """单个模板的元数据"""

    key: str  # 模板标识（如 'fund', 'stock', 'standard'）
    filename: str  # 实际文件名（如 'showbuy_fund_template.csv'）
    label: str  # 下载时显示的文字


# 所有支持的模板
TEMPLATES = {
    'fund': TemplateInfo('fund', 'showbuy_fund_template.csv', '基金标准模板'),
    'stock': TemplateInfo('stock', 'showbuy_stock_template.csv', '股票标准模板'),
    'standard': TemplateInfo('standard', 'showbuy_import_template.csv', '通用标准模板'),
}


def get_template_info(key: str) -> TemplateInfo | None:
    """根据 key 获取模板信息，不存在返回 None"""
    return TEMPLATES.get(key)


def get_template_filepath(key: str) -> Path | None:
    """获取模板文件的绝对路径，模板不存在返回 None"""
    info = get_template_info(key)
    if info is None:
        return None
    return Path(app.__path__[0]).parent / 'static' / 'templates' / info.filename
