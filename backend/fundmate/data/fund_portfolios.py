#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/20 10:55
@file: fund_portfolios.py
@author: imoyao
@email: immoyao@gmail.com
@desc:
1. InitPortfolio类用于基金组合信息入库；
2. UpdatePortfolio 类用于已有组合调仓信息更新

组合分析：[深入分析15个基金组合之后，我有这些发现-雪球](https://xueqiu.com/4778574435/199049616?page=15)
"""
import datetime
from typing import Dict, List, Optional

from flask import current_app

import pandas as pd
from sqlalchemy import create_engine

from backend.fundmate.app import db
from backend.fundmate.data.danjuan.combination import Strategy as DJStrategy
from backend.fundmate.data.qieman.combination import Strategy as QMStrategy
from backend.fundmate.database import get_table_name
from backend.fundmate.excepts import FundQueryError, NotSupportPlatError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import (
    PLAT_TYPE,
    FundCombinationHoldDetail,
    FundPortfolio,
    FundPortfolioAdjustHistory,
    FundPortfolioMgr,
)
from backend.fundmate.libs.pysnowflake import snowflake

config = current_app.config
SQLALCHEMY_DATABASE_URI = config.get('SQLALCHEMY_DATABASE_URI')


def sort_trade_info_by_date(trade_info: List, sort_key: str = 'trade_date') -> List:
    """
    调仓历史写入数据库时应该按照日期升序排序
    :return:
    """
    trade_info_df = pd.DataFrame(trade_info)
    sorted_trade_info_df = trade_info_df.sort_values(by=sort_key, ascending=True)
    sorted_trade_info = sorted_trade_info_df.to_dict(orient='records')
    return sorted_trade_info


class BasePortfolio:
    """
    将初始化和更新公用的接口提出来
    """

    def __init__(self):
        self.dj_po = DJStrategy()
        self.qm_po = QMStrategy()
        self.engine = create_engine(SQLALCHEMY_DATABASE_URI)

    def get_strategy(self, plat_str: str):
        strategies = {
            'dj': self.dj_po,
            'qm': self.qm_po,
        }
        stra_obj = strategies.get(plat_str)
        return stra_obj

    def persist_trade_info(self, portfolio_code: str, trade_info: List):
        sf = snowflake.generator()
        trade_info_sorted_by_date_asc = sort_trade_info_by_date(trade_info)
        for trade_item in trade_info_sorted_by_date_asc:
            plat_trading_id = trade_item.get('trading_id')
            trade_date = trade_item.get('trade_date')
            remark = trade_item.get('remark')
            trading_elements = trade_item.get('trading_elements')

            adjust_id = next(sf)
            adjust_detail = {
                'portfolio_code': portfolio_code,
                'update_date': trade_date,
                'adjust_id': adjust_id,
                'plat_trade_id': plat_trading_id,
                'desc': remark,
            }
            # 调仓历史记录
            adjust_instance = FundPortfolioAdjustHistory.create(**adjust_detail)
            # 调仓组成基金比例信息记录
            if not isinstance(trading_elements, pd.DataFrame):
                trading_elements = pd.DataFrame(trading_elements)
            trading_elements['adjust_id'] = adjust_instance.adjust_id
            tb_name = get_table_name(FundCombinationHoldDetail)
            trading_elements.to_sql(name=tb_name, con=self.engine, if_exists='append', index=False)
            logger.info(f'{adjust_instance}')
        return 0


class InitPortfolio(BasePortfolio):
    """
    初始化组合时调用该接口
    """

    def __init__(self):
        super().__init__()

    def upsert_mgr(self, plat_flag: str, mgr_info: Optional[Dict] = None) -> str:
        """
        根据平台特征码和编码查找用户，若无则新建
        :param plat_flag: 
        :param mgr_info: 
        :return: 
        """
        mgr_code = mgr_info.get('code')
        plat_flag_int = PLAT_TYPE.get(plat_flag)
        unique_query_arg = {
            'plat_code': mgr_code,
            'platform': plat_flag_int,
        }
        mgr_instance = FundPortfolioMgr.query.filter_by(**unique_query_arg).one_or_none()
        if not mgr_instance:
            mgr_code = FundPortfolioMgr.gen_mgr_code()
            mgr_info['code'] = mgr_code
            mgr_instance = FundPortfolioMgr.create(**mgr_info)
        return mgr_instance.code

    def create_portfolio(self, plt_code: str, plat_flag: str):
        po_inst = self.get_strategy(plat_flag)
        if not po_inst:
            raise NotSupportPlatError(f'暂不支持该平台 {plat_flag} 数据获取！')
        plat_flag_int = PLAT_TYPE.get(plat_flag)
        fpo = FundPortfolio.query.filter_by(code=plt_code, platform=plat_flag_int).one_or_none()
        if fpo is None:
            po_detail = po_inst.detail(plt_code)
            mgr_info = po_detail.pop('mgr_info')
            # 创建组合管理员
            mgr_code = self.upsert_mgr(plat_flag, mgr_info)
            portfolio_code = FundPortfolio.gen_random_digit()
            po_detail['mgr_code'] = mgr_code
            po_detail['platform'] = plat_flag_int
            po_detail['is_visible'] = True
            po_detail['portfolio_code'] = portfolio_code
            po_detail['update_time'] = datetime.datetime.utcnow()
            po_obj = FundPortfolio.create(**po_detail)
        else:
            logger.warning(f'组合 {fpo} 已存在，更新平台组合请使用 `UpdatePortfolio` 类')
            return None

        trade_info = None
        if plat_flag == 'dj':
            trade_info = po_inst.pagination_trade_info(plt_code)
        elif plat_flag == 'qm':
            trade_info = po_inst.pagination_trade_info(plt_code, is_desc=False)
        if trade_info:
            portfolio_code = po_obj.portfolio_code
            self.persist_trade_info(portfolio_code, trade_info)
        else:
            logger.warning(f'获取组合 {po_obj} 调仓信息失败！')
        return po_obj

    def init_portfolio(self):
        """
        初始化组合
        :return:
        """
        # support_platforms = PLAT_TYPE.keys()
        support_platforms = ['qm', 'dj']
        for plat_flag in support_platforms:
            po_obj = self.get_strategy(plat_flag)
            portfolios = po_obj.list_all()
            for po_code in portfolios:
                fpo = self.create_portfolio(po_code, plat_flag)
                if fpo:
                    logger.success(f'基金组合 {fpo} 信息保存完成!')


class UpdatePortfolio(BasePortfolio):
    """
    批量更新且慢、蛋卷基金、etc组合
    """

    def __init__(self):
        super().__init__()

    def update_danjuan(self, plt_code: str, portfolio_code: str):
        """
        周期性更新蛋卷基金组合
        :param plt_code:
        :param portfolio_code:
        :return:
        """
        if not plt_code.startswith('CSI'):
            raise FundQueryError(f'请检查输入的平台组合编号 {plt_code} 是否正确？')
        total = self.dj_po.total_times(plt_code)
        record_count = FundPortfolioAdjustHistory.adjust_count(portfolio_code)
        if total is not None:
            if record_count < total:
                adjust_size = total - record_count
                # 蛋卷基金的直接获取就行，total_times接口不会返回调仓信息
                trade_info = self.dj_po.pagination_trade_info(plt_code, size=adjust_size)
                if trade_info:
                    self.persist_trade_info(portfolio_code, trade_info)
                else:
                    logger.error(f'获取组合 {portfolio_code} 调仓信息出错，请检查确认……')
            else:
                logger.info(f'组合 {portfolio_code} 期间未发生调仓……')
        else:
            logger.error('获取组合信息出错，请检查网络连接……')

    def update_qieman(self, plt_code: str, portfolio_code: str):
        """
        周期性更新且慢基金组合
        :param plt_code:
        :param portfolio_code:
        :return:
        """
        if not plt_code.startswith('ZH'):
            raise FundQueryError(f'请检查输入的平台组合编号 {plt_code} 是否正确？')

        adjust_info = self.qm_po.adjustments(plt_code)
        if adjust_info:
            total = adjust_info.get('total')
            size = adjust_info.get('size')
            record_count = FundPortfolioAdjustHistory.adjust_count(portfolio_code)
            # 发生了调仓
            if record_count < total:
                # 期间调整的次数
                adjust_size = total - record_count
                if adjust_size < size:  # 从里面获取即可
                    adjust_content = adjust_info.get('content')
                    # 只获取最近没有更新的期信息
                    amend_adjust_content = adjust_content[:adjust_size]
                    trade_info = self.qm_po.trade_history(amend_adjust_content)
                else:
                    trade_info = self.qm_po.pagination_trade_info(plt_code, size=adjust_size, is_desc=True)
                if trade_info:
                    self.persist_trade_info(portfolio_code, trade_info)
                else:
                    logger.error(f'获取组合 {portfolio_code} 调仓信息出错，请检查确认……')
            else:
                logger.info(f'组合 {portfolio_code} 期间未发生调仓……')
        else:
            logger.error('获取组合信息出错，请检查网络连接……')

    def update_portfolio(self):
        """
        更新数据库中已经记录的组合
        1. 查询是否需要更新，依靠get_last_adjust_date
        2. 对比adjust_count，如果数据库和API获取不一致，说明发生调仓
        3. 调用persist_trade_info保存调仓记录
        :return:
        """
        fpos = db.session.query(FundPortfolio).filter(FundPortfolio.platform != 0)
        # 遍历获取组合是否调仓，如果调仓，则将其信息存入数据库
        for po_item in fpos:
            plt_code = po_item.code
            portfolio_code = po_item.portfolio_code
            po_last_adjust_date = po_item.last_adjust_date
            po_platform = po_item.platform
            # plat_str = PLAT_MAP.get(po_platform)
            po_obj = self.get_strategy(po_platform)
            last_trade_date_fmt = po_obj.get_last_adjust_date(plt_code)
            if po_last_adjust_date != last_trade_date_fmt:
                # 调仓详情
                po_details = po_obj.detail(plt_code)
                risk_type = po_details.get('risk_type')
                annualized_rate_of_return = po_details.get('annualized_rate_of_return')
                invest_rate_of_return = po_details.get('invest_rate_of_return')
                update_detail = {
                    'risk_type': risk_type,
                    'annualized_rate_of_return': annualized_rate_of_return,
                    'invest_rate_of_return': invest_rate_of_return,
                    'update_time': datetime.datetime.utcnow(),
                    'last_adjust_date': last_trade_date_fmt,
                }
                # 更新组合基本信息
                fpo = FundPortfolio.query.filter_by(portfolio_code=portfolio_code).one_or_none()
                if fpo:
                    fpo.update(**update_detail)
                if po_platform == 'qm':
                    self.update_qieman(plt_code, portfolio_code)

                elif po_platform == 'dj':
                    self.update_danjuan(plt_code, portfolio_code)


if __name__ == '__main__':
    # 初始化调用
    po = InitPortfolio()
    po.init_portfolio()
    # 日常更新组合调仓信息等
    update_po = UpdatePortfolio()
    update_po.update_portfolio()
