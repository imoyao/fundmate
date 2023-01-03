#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2023/01/03 17:50
from typing import Union

from backend.fundmate import settings
from backend.fundmate.fund.models import Fund, FundPortfolio, Mgr


def lookup_collection(collection_type: str, identify: str) -> Union[Fund, FundPortfolio, Mgr, None]:
    """
    根据识别码和类标识查询对应的类实例
    :param collection_type:
    :param identify:
    :return:
    """
    type_tables = {
        settings.SupportCollectionsEnum.fund.dk_value: Fund,
        settings.SupportCollectionsEnum.portfolio.dk_value: FundPortfolio,
        settings.SupportCollectionsEnum.managers.dk_value: Mgr,
        #  FIXME: 目前先支持基金，其他待完善
        # settings.SupportCollectionsEnum.index.dk_value:Index,
        # settings.SupportCollectionsEnum.stock.dk_value:Stock,
        # settings.SupportCollectionsEnum.bond.dk_value:Bond,
        # settings.SupportCollectionsEnum.futures.dk_value:Futures,
        # settings.SupportCollectionsEnum.financial_product.dk_value:FinancialProduct,

    }
    collections_cls = type_tables.get(collection_type)
    if collections_cls:
        col_inst = collections_cls.lookup(identify)
        return col_inst
    return None
