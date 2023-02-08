#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2023/01/03 17:50
import enum
from typing import Union

from backend.fundmate import settings
from backend.fundmate.collection.models import CategoriesOfCollection, Collection, LabelsOfCollection
from backend.fundmate.fund.models import Fund, FundPortfolio, Manager
from backend.fundmate.libs.dataklasses import dataklass
from backend.fundmate.settings import DEFAULT_CATEGORY_NAME


@dataklass
class LabelData:
    """
    预置labels
    """
    name: str
    color: str
    desc: str


JZ = LabelData('价值', '#1BA784', '注重风险控制，强调安全边际，主要赚价值回归的钱')
CZ = LabelData('成长', '#D42517',
               '更加关注企业的增速和增长的潜力，力求在企业爆发性成长前中期买入，赚取戴维斯双击的钱，在高成长性难以持续后卖出')
ZL = LabelData('质量', '#1661AB',
               '看重公司的盈利能力，认为投资是慢慢变富，复利增长比爆发增长更重要。长期持有行业好、有护城河、有竞争优势、商业模式好、高 ROE、高质量的好公司')
JH = LabelData('均衡', '#D1E2DE', '无惧市场风格变换，注重性价比，追求更稳定的超额收益')
JQD = LabelData('景气度', '#F3BF4C', '对企业景气调查中的定性指标通过定量方法加工汇总，关注拐点和趋势')
ZQ = LabelData('周期', '#50616D', '对企业景气调查中的定性指标通过定量方法加工汇总，关注拐点和趋势')
ZXP = LabelData('中小盘', '#C0C4C3', '波动大、流动性较差、成长性强、机构研究覆盖少、散户参与多')
DP = LabelData('大盘', '#11659A', '确定性高，蓝筹白马')
ZS = LabelData('择时', '#1661AB', '信奉周期，追求抄底，低买高卖')


@enum.unique
class LabelsEnum(enum.Enum):
    """
    系统预置label
    """
    JZ = JZ
    CZ = CZ
    ZL = ZL
    JH = JH
    JQD = JQD
    ZQ = ZQ
    ZXP = ZXP
    DP = DP
    ZS = ZS


def lookup_collection(collection_type: str, identify: str) -> Union[Fund, FundPortfolio, Manager, None]:
    """
    根据识别码和类标识查询对应的类实例
    :param collection_type:
    :param identify:
    :return:
    """
    type_tables = {
        settings.SupportCollectionsEnum.fund.dk_value: Fund,
        settings.SupportCollectionsEnum.portfolio.dk_value: FundPortfolio,
        settings.SupportCollectionsEnum.managers.dk_value: Manager,
        #  FIXME: 目前先支持基金，其他待完善
        # settings.SupportCollectionsEnum.index.dk_value:Index,
        # settings.SupportCollectionsEnum.stock.dk_value:Stock,
        # settings.SupportCollectionsEnum.bond.dk_value:Bond,
        # settings.SupportCollectionsEnum.futures.dk_value:Futures,
        # settings.SupportCollectionsEnum.fin_product.dk_value:FinancialProduct,

    }
    collections_cls = type_tables.get(collection_type)
    if collections_cls:
        col_inst = collections_cls.lookup(identify)
        return col_inst
    return None


def create_default_labels(user_id: str):
    """
    用户首次添加自选时创建默认labels
    1. 用户第一次添加自选时创建
    2. 用户删除所有预置自选后不再重复创建
    :return:
    """
    if Collection.is_first_collect(user_id):
        for item in LabelsEnum:
            label = item.value
            data = {
                'name': label.name,
                'color': label.color,
                'desc': label.desc,
                'creator_id': user_id
            }
            LabelsOfCollection.create(**data)
        return 0


def create_default_category(user_id: str, category_type: str):
    """
    自选分类创建默认分组
    :return:
    """
    if Collection.is_first_collection_of_col_type(user_id, category_type):
        if category_type in settings.SupportCollectionsEnum.input():
            data = {
                'name': DEFAULT_CATEGORY_NAME,
                'category_type': category_type,
                'creator_id': user_id
            }
            _inst = CategoriesOfCollection.create(**data)
            return _inst
