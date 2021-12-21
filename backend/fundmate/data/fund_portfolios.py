#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/20 10:55
@file: fund_portfolios.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 基金组合信息入库

一些备忘链接：[深入分析15个基金组合之后，我有这些发现-雪球](https://xueqiu.com/4778574435/199049616?page=15)
"""
from flask import current_app

import pandas as pd
from sqlalchemy import create_engine

from backend.fundmate.data.danjuan.combination import Strategy as DJStrategy
from backend.fundmate.data.qieman.combination import Strategy as QMStrategy
from backend.fundmate.database import get_table_name
from backend.fundmate.excepts import NotSupportPlatError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import PLAT_TYPE, FundCombinationHoldDetail, FundPortfolio, FundPortfolioAdjustHistory
from backend.fundmate.libs.pysnowflake import snowflake

config = current_app.config
SQLALCHEMY_DATABASE_URI = config.get('SQLALCHEMY_DATABASE_URI')


class InitPortfolio:

    def __init__(self):
        self.dj_po = DJStrategy()
        self.qm_po = QMStrategy()
        self.engine = create_engine(SQLALCHEMY_DATABASE_URI)

    def parse_portfolios(self, portfolios, plat_flag: str):
        if plat_flag == 'dj':
            po_inst = self.dj_po
        elif plat_flag == 'qm':
            po_inst = self.qm_po
        else:
            raise NotSupportPlatError('暂不支持该平台数据获取！')
        plat_flag_int = PLAT_TYPE.get(plat_flag)
        for po_code in portfolios:
            po_detail = po_inst.detail(po_code)
            po_code = po_detail.get('code')

            query_args = {
                'platform': plat_flag_int,
                'code': po_code,
            }
            is_exists = FundPortfolio.check_is_exists(query_args)
            po_detail['platform'] = plat_flag_int
            po_detail['is_visible'] = True
            if not is_exists:
                portfolio_code = FundPortfolio.gen_random_digit()
                po_detail['portfolio_code'] = portfolio_code
                po_obj = FundPortfolio.create(**po_detail)
            else:
                # 该接口只用于初始化，对于已存在的，应该用专门接口去更新
                continue
                # po_obj = FundPortfolio.update(**po_detail)
            trade_info = None
            if plat_flag == 'dj':
                trade_info = po_inst.pagination_trade_info(po_code)
            elif plat_flag == 'qm':
                trade_info = po_inst.pagination_trade_info(po_code, is_desc=False)
            if trade_info:
                portfolio_code = po_obj.portfolio_code
                sf = snowflake.generator()

                for trade_item in trade_info:
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
                    adjust_obj = FundPortfolioAdjustHistory.create(**adjust_detail)
                    # 调仓信息记录
                    if not isinstance(trading_elements, pd.DataFrame):
                        trading_elements = pd.DataFrame(trading_elements)
                    trading_elements['adjust_id'] = adjust_obj.adjust_id
                    tb_name = get_table_name(FundCombinationHoldDetail)
                    trading_elements.to_sql(name=tb_name, con=self.engine, if_exists='append', index=False)

    def init_danjuan(self):
        plat_flag = 'dj'
        portfolios = self.dj_po.get()
        self.parse_portfolios(portfolios, plat_flag)
        logger.success(f'蛋卷基金组合 {portfolios} 爬取完成!')

    def init_qieman(self):
        plat_flag = 'qm'
        portfolios = self.qm_po.get()
        self.parse_portfolios(portfolios, plat_flag)
        logger.success(f'且慢基金组合 {portfolios} 爬取完成!')

    def init_portfolio(self):
        """
        初始化组合
        :return:
        """
        self.init_qieman()
        self.init_danjuan()


if __name__ == '__main__':
    po = InitPortfolio()
    po.init_portfolio()
