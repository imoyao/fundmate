#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/8/10 11:30
from pathlib import Path
from typing import Union

from xalpha.cons import rget_json

from backend.fundmate import settings, utils
from backend.fundmate.data.utils import data_parser
from backend.fundmate.excepts import EmptyError, UnexpectedArgsError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import FeeRatio, Fund, InRule, OutRule

abs_current_path = Path.cwd().resolve()
FUND_SYMBOLS_SAVE_FP = f'{str(abs_current_path)}/fund_symbols.json'


class DKHS:

    @staticmethod
    def api():
        """
        获取所有api
        """
        _url = 'https://www.dkhs.com/api/v1'
        _resp = rget_json(_url)
        return _resp

    def fatch_fund_info(self):
        """
        基金编码对应特殊编号写入数据库（从网站抓取之后直接写入）
        此操作在写入数据库的同时还会写入json文件
        ---

        可以用到的字段：
        symbol      带符号的编码
        charge_mode     收费模式（前端/后端）
        investment_risk     风险等级
        fund_name   全名
        abbr_name   通用名称

        ---

        {
            'id': 102026494,
            'symbol': 'FP012651',
            'code': '012651',
            'symbol_type': 3,
            'symbol_stype': 301,
            'symbol_stype_display': '混合型',
            'abbr_name': '博时半导体主题混合C',
            'chi_spell': 'bsbdtzthhc',
            'list_status': 1,
            'is_margin': False,
            'net_value': 1.028,
            'net_cumulative': 1.028,
            'tradedate': '2021-08-06',
            'year_yld': 0.0,
            'tenthou_unit_incm': 0.0,
            'percent_day': -4.21170332,
            'percent_month': None,
            'percent_season': None,
            'percent_week': -4.2117,
            'percent_six_month': None,
            'percent_year': None,
            'percent_tyear': 2.8,
            'latest_cp_rate': 2.8,
            'end_shares': '',
            'is_recommended': False,
            'recommend_title': None,
            'recommend_desc': None,
            'allow_fixed': False,
            'amount_fixed_min': None,
            'amount_fixed_max': None,
            'allow_trade': False,
            'allow_buy': False,
            'allow_sell': False,
            'trade_status': -1,
            'fare_ratio_buy': None,
            'discount_rate_buy': None,
            'fare_ratio_sell': None,
            'discount_rate_sell': None,
            'amount_min_buy': None,
            'amount_max_buy': None,
            'shares_min_sell': None,
            'shares_max_sell': None,
            'shares_min': None,
            'investment_risk': 5,
            'investment_risk_display': '高',
            'charge_mode': 1,
            'charge_mode_display': '前端',
            't_days_sell': 3,
            'company': 200002130,
            'recommend_percent_value': None,
            'recommend_percent_display': '近一月收益率',
            'is_bao': False,
            'year_yld_avg_month': None,
            'tenthou_unit_incm_avg_month': None,
            'percent_twyear': None,
            'percent_three_year': None,
            'percent_five_year': None,
            'percent_all': 2.8,
            'score': None,
            'analyse_description': None,
            'mana_name': '博时基金管理有限公司',
            'fund_name': '博时半导体主题混合型证券投资基金',
            'rank_fund_manager_index': None,
            'rank_fund_manager_total': None,
            'rank_asset_index': None,
            'rank_asset_total': None,
            'end_asset': '0.00',
            'company_score': 96,
            'asset_score': 0,
            'profitability': 0,
            'sharpe_ratio': 0,
            'anti_risk': 0,
            'recommend_percent_fixed_value': None,
            'recommend_percent_fixed_display': '近3年定投收益',
            'subscription_status': 2,
            'allow_subscribe': False,
            'subscribe_start_date': '2021-06-27T16:00:00Z',
            'subscribe_end_date': '2021-07-16T07:00:00Z',
            'amount_subscribe_min': None,
            'amount_subscribe_max': None,
            'fare_ratio_subscribe': None,
            'discount_rate_subscribe': None,
            'track_target': None,
            'track_target_name': None,
            'percent_year_fixed': 0.0,
            'percent_twyear_fixed': None,
            'percent_three_year_fixed': None,
            'percent_five_year_fixed': 0.0,
            'score_description': None,
            'stability': 0,
            'excess_income': 0,
            'index_following': 0,
            'experience': 0,
            'timing_selection': 0,
            'stock_selection': 0,
            'allow_sell2bao': True,
            'trade_status_display': '未知',
            'bull_market': '0.00',
            'bear_market': '0.00',
            'seesawing_market': '0.00',
            'org_heavy_scale': None,
            'estab_date': '半年',
            'company_csname': '博时基金',
            'discount_fare_ratio_buy': None,
            'fare_ratio_all': '0.00',
            'fnd_stype': None,
            'fnd_stype_display': None,
            'asset_type_display': None,
            'style_type_display': None,
            'score_short': None,
            'score_medium': None,
            'score_long': None,
            'recommend_period': 5,
            'recommend_period_display': '近一年',
            'recommend_period_length': '短期',
            'recommend_score': None,
            'price_mode': 0,
            'excess_income_year': None,
            'follow_percent_year': None,
            'allow_convert': False,
            'percent_yld': None,
            'strategy_type': 0,
            'strategy_type_display': '无',
            'retreat_rate': None,
            'fluctuate_rate': None
        }
        """
        _url = 'http://www.dkhs.com/api/v1/symbols/funds/'
        _resp = rget_json(_url)
        # results = _resp.get('results')
        raw_data = list()
        total_page = _resp.get('total_page')
        symbols_lists = list()
        for page in range(1, total_page + 1):
            params = {'page': page}
            item_resp = rget_json(_url, params=params)
            item_results = item_resp.get('results')
            raw_data.extend(item_results)
            page_item = list()
            for fund in item_results:
                # 基金基本类型
                code = fund.get('code')
                symbol = fund.get('symbol')
                charge_mode = fund.get('charge_mode')
                abbr_name = fund.get('abbr_name')
                investment_risk = int(fund.get('investment_risk'))
                fund = {
                    'code': code,
                    'symbol': symbol,
                    'charge_mode': charge_mode,
                    'investment_risk': investment_risk,
                    'fund_name': fund.get('fund_name'),
                    'abbr_name': abbr_name,
                }
                fund_inst = self.update_fund_info(code, symbol, charge_mode, investment_risk, abbr_name)
                if fund_inst:
                    logger.success(f'Update {fund_inst} successfully.')

                page_item.append(fund)

            logger.info(f'Data from page:{page} has finished.')
            symbols_lists.extend(page_item)
        # 保存裸数据到文件
        utils.write_json_data(raw_data, FUND_SYMBOLS_SAVE_FP)
        return symbols_lists

    @staticmethod
    def update_fund_info(code: str, symbol: str, charge_mode: int, investment_risk: Union[int, str], abbr_name: str):
        """
        更新某基金信息（包括前缀、风险等级，收费模式<前端（1）/后端（0）>）
        :param code: 基金编码
        :param symbol: 更新信息之前缀，来自基金决策宝
        :param charge_mode:收费模式，前端（1）或者后端（0）
        :param investment_risk:风险等级
        :param abbr_name:基金名称（非全称）
        :return:
        """
        if charge_mode == 2:  # 源数据中用1/2表示前端和后端，我们强制改为0/1,其中1为前端
            charge_mode = 0
        investment_risk = int(investment_risk) if isinstance(investment_risk, str) else investment_risk
        symbol_prefix = symbol.replace(code, '')
        fund_inst = Fund.filter_by_code(code)
        if fund_inst:
            is_usable_risk = investment_risk in settings.RiskTypeEnum.input()
            is_usable_symbol = symbol_prefix in settings.SymbolTypeEnum.input()
            is_usable_charge_mode = charge_mode in [0, 1]
            if all([is_usable_risk, is_usable_symbol, is_usable_charge_mode]):
                if symbol_prefix == settings.SymbolTypeEnum.UN.dk_name:
                    # 如果是未知，则默认值没有必要更新
                    fund_inst.update(risk_level=investment_risk, is_fe_charge_mode=charge_mode)
                else:
                    fund_inst.update(symbol_prefix=symbol_prefix,
                                     risk_level=investment_risk,
                                     is_fe_charge_mode=charge_mode)
                return fund_inst
            else:
                raise UnexpectedArgsError(f'Please check your arguments:investment_risk:{investment_risk},'
                                          f'symbol_val:{symbol_prefix},charge_mode:{charge_mode}')
        else:
            logger.error(f'<Fund({code!r}, {abbr_name!r})> info get failed from DB,please check it.')

    @staticmethod
    def search_symbol(fund_code: str) -> Union[str, None]:
        """
        通过搜索接口查询symbol
        :param fund_code: 基金编码
        :return:
        """
        # 特殊处理  FIXME：退市基金此处会获取失败，返回信息类似：FP**Z；还有一部分查询的返回结果是信托产品，如:202010
        special_list = ['202010']
        if fund_code in special_list:
            raise ValueError(f'The code:{fund_code} will return incorrect info,we will skip it.')
        _url = f'https://www.dkhs.com/api/v1/se' \
               f'arch/symbols/?symbol_type=3&page_size=1&q={fund_code}'
        _resp = rget_json(_url)
        if _resp:
            results = _resp.get('results')
            if results:
                fund_obj = results[0]
                symbol = fund_obj.get('symbol')
                code = fund_obj.get('code')
                if code == fund_code:
                    symbol_prefix = symbol.replace(code, '')
                    if symbol_prefix in settings.SymbolTypeEnum.input():
                        return symbol_prefix
                else:
                    logger.info(f'Get unexpected code:{code}.')
                    raise UnexpectedArgsError(f'Please check your fund code {fund_code},it returns code {code}.')

                logger.error(f'Get unexpected symbol:{symbol}.')
            else:
                # FIXME: 此处获取symbol失败，则交易费率信息需要手动更新或者使用别的方式进行爬取
                logger.error(f'Get symbol error of fund code:{fund_code}.')
                raise UnexpectedArgsError(f'Get symbol error of fund code:{fund_code}.')

    def parse_json_to_db(self):
        """
        从json文件中读取文件并更新信息到数据库，这个接口应该作为search_symbol的补充
        （目前该接口只能获取到部分基金的信息）
        """
        fund_data_list = data_parser.get_data_from_json(FUND_SYMBOLS_SAVE_FP)
        for fund in fund_data_list:
            code = fund.get('code')
            symbol = fund.get('symbol')
            charge_mode = fund.get('charge_mode')
            abbr_name = fund.get('abbr_name')
            investment_risk = int(fund.get('investment_risk'))
            fund_inst = self.update_fund_info(code, symbol, charge_mode, investment_risk, abbr_name)
            if fund_inst:
                logger.success(f'Update {fund_inst} successfully.')
        return 0

    def transfer_rule(self, fund_id: str, fee_type: int, fee_amount: float, rule_item: dict, rule_info: dict):
        is_in = False
        if fee_type in [1, 2]:
            is_in = True
            rule_class = InRule
        else:
            rule_class = OutRule
        # FIXME: 有的rule是存在的，为什么log还是created xx?
        _rule_inst = rule_class.insert_or_update(rule_info, **rule_info)
        rule_id = _rule_inst.id
        fare_ratio = rule_item.get('fare_ratio')
        if fare_ratio:
            rate = float(fare_ratio) if not isinstance(fare_ratio, float) else fare_ratio
        else:
            rate = None
        rate_info = {
            'fund_id': fund_id,
            'rule_id': rule_id,
            'fee_type': fee_type,
            'rate': rate,
            'fee_amount': fee_amount,
        }
        if is_in:
            rate_info.update({'in_rule_id': rule_id})
        else:
            rate_info.update({'out_rule_id': rule_id})
        return rate_info

    def fee_ratio(self, fund_code: str):
        """
        FIXME: 该接口命中率太低，需要找别的接口替换
        根据基金决策宝网站信息更新费率
        数据来源：[兴全合润混合(SZ163406)_基金净值_费率_行情走势](https://www.dkhs.com/s/SZ163406/) “交易须知” 子页面
        :param fund_code: 基金编码
        :return:
        """
        symbol_prefix = 'UN'
        _fund_inst = Fund.filter_by_code(fund_code)
        if _fund_inst:
            symbol_prefix = _fund_inst.symbol_prefix

        if symbol_prefix == 'UN':
            raise UnexpectedArgsError(f'The symbol of fund {fund_code} is unknown,Please check or update it.')

        _url = f'https://www.dkhs.com/api/v1/symbols/{symbol_prefix}{fund_code}/fare_ratio/'
        _resp = rget_json(_url)
        fund_id = _fund_inst.id
        if _resp:
            if isinstance(_resp, dict):
                errors = _resp.get('errors')
                if errors:
                    err_msg = errors.get('symbol_error')
                    raise UnexpectedArgsError(err_msg)

            for item in _resp:
                direction = item.get('direction')
                fee_amount = None
                # 申购和买入
                if direction in [0, 6]:
                    min_balance = item.get('min_balance')
                    max_balance = item.get('max_balance')
                    if direction == 0:
                        fee_type = settings.FeeTypeEnum.subscribe
                    else:
                        fee_type = settings.FeeTypeEnum.purchase

                    # 最大值时按照固定收费，同时修改上限为正无穷
                    if max_balance == '0.00':
                        min_fare = item.get('min_fare')
                        max_fare = item.get('max_fare')
                        if min_fare == max_fare:
                            fee_amount = float(min_fare)
                            max_balance = None
                    # 更新规则表
                    rule_info = {
                        'start_quota': min_balance,
                        'end_quota': max_balance,
                    }

                elif direction == 1:
                    fee_type = settings.FeeTypeEnum.redeem
                    start_day = item.get('min_hold')
                    end_day = item.get('max_hold')

                    rule_info = {
                        'start_day': start_day,
                        'end_day': end_day,
                    }

                rate_info = self.transfer_rule(fund_id, fee_type, fee_amount, item, rule_info)
                if rate_info:
                    rule_id = rate_info.pop('rule_id')
                    # FIXME: rule_id is bug! see:save_fee_info
                    query_args = {'fund_id': fund_id, 'rule_id': rule_id, 'fee_type': fee_type}
                    FeeRatio.insert_or_update(query_args, do_log_flag=True, **rate_info)
        else:
            raise EmptyError(f'The href: {_url} from remote get empty response.')
        return _resp


jcb = DKHS()
if __name__ == '__main__':
    # print(jcb.api())
    print(jcb.parse_json_to_db())
