#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/8/18 16:46
"""
更新基金费率的脚本
1. 尝试韭圈儿解析数据
2. 对于韭圈儿更新失败的，尝试蛋卷基金？
"""
from typing import Dict, List, Optional

from backend.fundmate.data.danjuan.base import dj_fd
from backend.fundmate.data.dkhs.base import frt
from backend.fundmate.data.fundb.base import FundFeeRatio
from backend.fundmate.excepts import CrawlerException, EmptyError, UnexpectedArgsError, UnpackError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import FeeRatio, Fund
'''
网页显示如下：
## 认购费率

| 适用金额              | 适用期限 | 原费率|天天基金优惠费率 |
|-------------------|------|--------------|
| 小于100万元           | ---  | 1.20%        |
| 大于等于100万元，小于200万元 | ---  | 0.80%        |
| 大于等于200万元，小于500万元 | ---  | 0.30%        |
| 大于等于500万元         | ---  | 每笔1000元      |

## 申购费率

| 适用金额              | 适用期限 | 原费率|天天基金优惠费率银行卡购买|活期宝购买            |
|-------------------|------|------------------------------------|
| 小于100万元           | ---  | 1.50%|0.15%|0.15% |
| 大于等于100万元，小于200万元 | ---  | 1.00%|0.10%|0.10% |
| 大于等于200万元，小于500万元 | ---  | 0.50%|0.05%|0.05% |
| 大于等于500万元         | ---  | 每笔1000元                            |

## 赎回费率

| 适用金额 | 适用期限         | 赎回费率  |
|------|--------------|-------|
| ---  | 小于7天         | 1.50% |
| ---  | 大于等于7天，小于30天 | 0.75% |
| ---  | 大于等于30天，小于1年 | 0.50% |
| ---  | 大于等于1年，小于2年  | 0.25% |
| ---  | 大于等于2年       | 0.00% |

## 运作费率

| 项目     | 费率 (每年)        |
|--------|------------|
| 管理费率   | 1.50%  |
| 托管费率   | 0.25% |
| 销售服务费率 | 0.00% |

## 备注

1. 基金管理费、托管费、销售服务费从基金资产中每日计提。每个工作日公告的基金净值已扣除管理费和托管费，无需投资者在每笔交易中另行支付。部分基金管理费以浮动方式提取，具体请以基金公司相关公告为准。

2. 买入费率和收益计算时间计算方法如下：

    净买入金额=买入金额/(1+买入费率)

    买入费用=买入金额-净买入金额

'''


def get_no_ratio_funds() -> List:
    """
    获取没有添加费率规则的基金列表
    FIXME: 对于封闭期基金，需要排除或者另行处理
    :return:
    """
    # 查询id不在fee_ratio，注意distinct用法
    has_rule_fd_code_lists = [ratio.fund_code for ratio in FeeRatio.query.distinct(FeeRatio.fund_code).all()]
    # 注意not_in 用法
    fund_lists = Fund.query.filter(Fund.fund_code.not_in(has_rule_fd_code_lists)).all()
    return fund_lists


def jcb_init_rate(fund_code: str):
    """
    决策宝数据初始化
    :param fund_code:
    :return:
    """
    if not fund_code:
        fund_lists = get_no_ratio_funds()
        failed_counts = 0
        not_success_set = set()

        for fd in fund_lists:
            fund_code = fd.fund_code
            try:
                ret = frt.rate(fund_code)
            except (UnexpectedArgsError, EmptyError) as e:
                logger.error(f'Fund {fund_code} get Error:{e}')
                ret = None
                not_success_set.add(fund_code)

        if not_success_set:
            failed_counts = len(not_success_set)
            logger.warning(
                f'Hits:{failed_counts} of fund failed to update fee ratio while {len(fund_lists) - failed_counts} '
                f'success,they are:{not_success_set}')
        pass_rate = f'{1 - (failed_counts / len(fund_lists)):.2f} %'
        logger.info(f'pass rate: {pass_rate}')
    else:
        try:
            ret = frt.rate(fund_code)
        except (UnexpectedArgsError, EmptyError):
            ret = None
            logger.warning(f'Failed to update fee ratio of {fund_code}.')
    return ret


def dj_init_fr(fund_code: Optional[str] = None):
    """
    蛋卷基金数据
    :return:
    """
    if not fund_code:
        fund_lists = get_no_ratio_funds()
        failed_counts = 0
        if fund_lists:
            not_success_set = set()
            for fd in fund_lists:
                fund_code = fd.fund_code
                try:
                    ret = dj_fd.rate(fund_code, to_db=True)
                except (UnpackError, ValueError) as e:
                    ret = None
                    logger.error(f'Fund {fund_code} get Error:{e}')
                    not_success_set.add(fund_code)

            if not_success_set:
                failed_counts = len(not_success_set)
                logger.warning(
                    f'Hits:{failed_counts} of fund failed to update fee ratio while {len(fund_lists) - failed_counts} '
                    f'success,they are:{not_success_set}')

        pass_rate = f'{1 - (failed_counts / len(fund_lists)):.2f} %'
        logger.info(f'pass rate: {pass_rate}')
    else:
        try:
            ret = dj_fd.rate(fund_code, to_db=True)
        except (UnexpectedArgsError, EmptyError):
            ret = None
            logger.error(f'Failed to update fee ratio of {fund_code}.')
    return ret


def jq_init_fr(fund_code: Optional[str] = None, to_db=False) -> Optional[Dict]:
    """
    韭圈儿数据（有反爬）
    :return:
    """
    jq_fr = FundFeeRatio()
    if not fund_code:
        fund_lists = get_no_ratio_funds()
        not_success_set = set()
        failed_counts = 0

        for fd in fund_lists:
            fund_code = fd.fund_code
            try:
                result = jq_fr.rate(fund_code, to_db=to_db)
            except CrawlerException as e:
                result = None
                logger.error(f'Fund {fund_code} get Error:{e}')
                not_success_set.add(fund_code)

        if not_success_set:
            failed_counts = len(not_success_set)
            logger.warning(
                f'Hits:{failed_counts} of fund failed to update fee ratio while {len(fund_lists) - failed_counts} '
                f'success,they are:{not_success_set}')
        pass_rate = f'{1 - (failed_counts / len(fund_lists)):.2f} %'
        logger.info(f'pass rate: {pass_rate}')
    else:
        try:
            result = jq_fr.rate(fund_code, to_db=to_db)
        except CrawlerException as e:
            result = None
            logger.info(f'Failed to update fee ratio of {fund_code} with error:{e}')
    return result


def fee_ratio(fund_code: Optional[str] = None, to_db=True):
    """
    初始化或者更新费率信息（支持更新单个）
    蛋卷数据没有反爬但是部分数据有误；
    韭圈数据暂时没有发现问题，但是有反爬
    :return:
    """
    result = jq_init_fr(fund_code, to_db=to_db)
    return result


if __name__ == '__main__':
    ret = fee_ratio(fund_code='007450')
    print(ret)
