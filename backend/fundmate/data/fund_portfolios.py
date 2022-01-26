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
@ update:
- 2022-01-06 11:16:55：
1. 基金组合添加好买基金平台；
2. 组合初始化支持通过指定flag来更新部分平台的基金组合

组合分析：[深入分析15个基金组合之后，我有这些发现-雪球](https://xueqiu.com/4778574435/199049616?page=15)
"""
import datetime
from typing import Dict, List, Optional

from flask import current_app

import pandas as pd
from sqlalchemy import and_, create_engine

from backend.fundmate.app import db
from backend.fundmate.data.danjuan.combination import Strategy as DJStrategy
from backend.fundmate.data.howbuy.combination import Strategy as HBStrategy
from backend.fundmate.data.qieman.combination import Strategy as QMStrategy
from backend.fundmate.database import get_table_name
from backend.fundmate.excepts import FundQueryError, NotSupportPlatError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import (
    FundPortfolio,
    FundPortfolioAdjustHistory,
    FundPortfolioHoldDetail,
    FundPortfolioMgr,
)
from backend.fundmate.libs.pysnowflake import snowflake
from backend.fundmate.settings import PlatTypeEnum

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
        self.hb_po = HBStrategy()
        self.engine = create_engine(SQLALCHEMY_DATABASE_URI)

    def get_strategy(self, plat_str: str):
        strategies = {
            'dj': self.dj_po,
            'qm': self.qm_po,
            'hb': self.hb_po,
        }
        strategy_obj = strategies.get(plat_str)
        return strategy_obj

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
            tb_name = get_table_name(FundPortfolioHoldDetail)
            trading_elements.to_sql(name=tb_name, con=self.engine, if_exists='append', index=False)
            logger.info(f'{adjust_instance}')
        return 0


class InitPortfolio(BasePortfolio):
    """
    初始化组合时调用该接口
    """

    def __init__(self, is_init_qieman: bool = True, is_init_danjuan: bool = True, is_init_howbuy: bool = True):
        super().__init__()
        self.init_config = {
            'qm': is_init_qieman,
            'dj': is_init_danjuan,
            'hb': is_init_howbuy,
        }

    @staticmethod
    def upsert_mgr(plat_flag: str, mgr_info: Optional[Dict] = None) -> str:
        """
        根据平台特征码和编码查找用户，若无则新建
        :param plat_flag: 
        :param mgr_info: 
        :return: 
        """
        if plat_flag in ['qm', 'dj']:
            mgr_code = mgr_info.get('plat_code')
            mgr_instance = FundPortfolioMgr.query.filter_by(plat_code=mgr_code, platform=plat_flag).one_or_none()
        elif plat_flag == 'hb':
            mgr_name = mgr_info.get('name')
            mgr_instance = FundPortfolioMgr.query.filter_by(name=mgr_name, platform=plat_flag).one_or_none()

        if mgr_instance is None:
            mgr_code = FundPortfolioMgr.gen_mgr_code()
            mgr_info['code'] = mgr_code
            mgr_info['platform'] = plat_flag
            mgr_instance = FundPortfolioMgr.create(**mgr_info)
            logger.success(f'组合管理者 {mgr_instance} 创建成功！')
        return mgr_instance.code

    def create_portfolio(self, plt_code: str, plat_flag: str):
        po_inst = self.get_strategy(plat_flag)
        if not po_inst:
            raise NotSupportPlatError(f'暂不支持该平台 {plat_flag} 数据获取！')
        fpo = FundPortfolio.query.filter_by(code=plt_code, platform=plat_flag).one_or_none()
        if fpo is None:
            po_detail = po_inst.detail(plt_code)
            mgr_info = po_detail.pop('mgr_info')
            # 创建组合管理员
            mgr_code = self.upsert_mgr(plat_flag, mgr_info)
            portfolio_code = FundPortfolio.gen_portfolio_code()
            po_detail['mgr_code'] = mgr_code
            po_detail['platform'] = plat_flag
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
        elif plat_flag in ['qm', 'hb']:  # 且慢和好买返回的信息默认最近调仓在最前面
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
        # 配置为True且在支持列表中
        plat_types = [item.dk_name for item in PlatTypeEnum]
        support_platforms = [plt for plt in self.init_config if self.init_config[plt] is True and plt in plat_types]
        for plat_flag in support_platforms:
            po_obj = self.get_strategy(plat_flag)
            portfolios = po_obj.list_all()
            if plat_flag != 'hb':
                for po_code in portfolios:
                    fpo = self.create_portfolio(po_code, plat_flag)
                    if fpo:
                        logger.success(f'基金组合 {fpo} 信息保存完成!')
            else:
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
        dj_obj = self.dj_po
        self.update_no_total(dj_obj, plt_code, portfolio_code)

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

    def update_no_total(self, query_instance, plt_code: str, portfolio_code: str):
        total = query_instance.total_times(plt_code)
        record_count = FundPortfolioAdjustHistory.adjust_count(portfolio_code)
        if total is not None:
            if record_count < total:
                adjust_size = total - record_count
                # 直接通过获取相应数量的调仓信息，total_times接口不会返回调仓信息
                trade_info = query_instance.pagination_trade_info(plt_code, size=adjust_size)
                if trade_info:
                    self.persist_trade_info(portfolio_code, trade_info)
                else:
                    logger.error(f'获取组合 {portfolio_code} 调仓信息出错，请检查确认……')
            else:
                logger.info(f'组合 {portfolio_code} 期间未发生调仓……')
        else:
            logger.error('获取组合信息出错，请检查网络连接……')

    def update_howbuy(self, plt_code: str, portfolio_code: str):
        """
        周期性更新好买基金平台组合

        该操作和蛋卷一致，只是调用的实例不同
        :return:
        """
        hb_obj = self.hb_po
        self.update_no_total(hb_obj, plt_code, portfolio_code)

    def update_portfolio(self):
        """
        更新数据库中已经记录的组合
        1. 查询是否需要更新，依靠get_last_adjust_date
        2. 对比adjust_count，如果数据库和API获取不一致，说明发生调仓
        3. 调用persist_trade_info保存调仓记录
        :return:
        """
        # 未定义和平台自有不需要更新
        fpos = db.session.query(FundPortfolio).filter(
            and_(
                FundPortfolio.platform != PlatTypeEnum.undefined.dk_name,
                FundPortfolio.platform != PlatTypeEnum.own.dk_name,
            ))
        # 遍历获取组合是否调仓，如果调仓，则将其信息存入数据库
        for po_item in fpos:
            plt_code = po_item.code
            portfolio_code = po_item.portfolio_code
            po_last_adjust_date = po_item.last_adjust_date
            po_platform = po_item.platform
            po_obj = self.get_strategy(po_platform)
            last_trade_date_fmt = po_obj.get_last_adjust_date(plt_code)
            if po_last_adjust_date != last_trade_date_fmt:
                # 调仓详情
                po_details = po_obj.detail(plt_code)
                annualized_rate_of_return = po_details.get('annualized_rate_of_return')
                invest_rate_of_return = po_details.get('invest_rate_of_return')
                if po_platform in ['qm', 'dj']:
                    risk_type = po_details.get('risk_type')
                    update_detail = {
                        'risk_type': risk_type,
                        'annualized_rate_of_return': annualized_rate_of_return,
                        'invest_rate_of_return': invest_rate_of_return,
                        'update_time': datetime.datetime.utcnow(),
                        'last_adjust_date': last_trade_date_fmt,
                    }
                elif po_platform == 'hb':
                    # 好买基金的风险信息为手动填写，不需要更新
                    update_detail = {
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
                elif po_platform == 'hb':
                    self.update_howbuy(plt_code, portfolio_code)


if __name__ == '__main__':
    # 初始化，需要保证在Flask上下文中调用
    is_init_qieman = False
    is_init_danjuan = False
    is_init_howbuy = True
    po = InitPortfolio(is_init_qieman, is_init_danjuan, is_init_howbuy)
    po.init_portfolio()
    # 日常更新组合调仓信息等
    update_po = UpdatePortfolio()
    update_po.update_portfolio()
