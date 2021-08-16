#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/8/10 11:30
import json
from pathlib import Path

from xalpha.cons import rget_json

from backend.fundmate import settings
from backend.fundmate.data.utils import data_parser
from backend.fundmate.excepts import UnexpectedArgsError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import Fund

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

    def fund_symbols(self):
        """
        基金编码对应特殊编号需要写入数据库

        ---

        可以用到的字段：
        symbol      带符号的编码
        charge_mode     收费模式（前端/后端）
        investment_risk     风险等级
        fund_name   全名

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
        symbol_type_set = set()
        investment_risk_set = set()
        for page in range(1, total_page + 1):
            params = {'page': page}
            item_resp = rget_json(_url, params=params)
            item_results = item_resp.get('results')
            raw_data.extend(item_results)
            page_item = list()
            for fund in item_results:
                # 基金类型
                symbol_stype_display = fund.get('symbol_stype_display')
                # symbol_map = {
                #     'symbol_type': fund.get('symbol_type'),
                #     'symbol_stype': fund.get('symbol_stype'),
                #     'symbol_stype_display': symbol_stype_display,
                # }
                # print(symbol_map)
                symbol_type_set.add(symbol_stype_display)

                investment_risk = fund.get('investment_risk')
                investment_risk_set.add(investment_risk)
                # investment_risk_display = fund.get('investment_risk_display')
                # risk_map = {
                #     'investment_risk': investment_risk,
                #     'investment_risk_display': investment_risk_display,
                # }
                # print(risk_map)

                fund = {
                    'code': fund.get('code'),
                    'symbol': fund.get('symbol'),
                    'charge_mode': fund.get('charge_mode'),
                    'investment_risk': fund.get('investment_risk'),
                    'fund_name': fund.get('fund_name'),
                }
                page_item.append(fund)
                # TODO: 这部分数据需要保存到数据库中

            logger.info(f'Data from page:{page} has finished.')
            symbols_lists.extend(page_item)
        # print(f'investment_risk_set:{investment_risk_set}')
        # print(f'symbol_type_set:{symbol_type_set}')
        # print(f'SYMBOLS_LISTS:{symbols_lists}')
        # 保存文件
        with open(FUND_SYMBOLS_SAVE_FP, 'w') as f:
            json.dump(raw_data, f, ensure_ascii=False)
        return symbols_lists

    def read_json_to_db(self):
        """
        从json文件中读取文件并更新信息到数据库
        """
        fund_data_list = data_parser.get_data_from_json(FUND_SYMBOLS_SAVE_FP)
        symbol_set = set()
        for fund in fund_data_list:
            code = fund.get('code')
            symbol = fund.get('symbol')
            charge_mode = fund.get('charge_mode')
            if charge_mode == 2:  # 源数据中用1/2表示前端和后端，我们强制改为0/1,其中1为前端
                charge_mode = 0
            investment_risk = int(fund.get('investment_risk'))
            symbol_prefix = symbol.replace(code, '')
            symbol_set.add(symbol_prefix)
            fund_inst = Fund.filter_by_code(code)
            if fund_inst:
                is_usable_risk = investment_risk in settings.RISK_TYPE.values()
                is_usable_symbol = symbol_prefix in settings.SYMBOL_TYPE.keys()
                is_usable_charge_mode = charge_mode in [0, 1]
                if all([is_usable_risk, is_usable_symbol, is_usable_charge_mode]):
                    fund_inst.update(symbol_prefix=symbol_prefix,
                                     risk_level=investment_risk,
                                     is_fe_charge_mode=charge_mode)
                else:
                    raise UnexpectedArgsError(f'Please check your arguments:investment_risk:{investment_risk},'
                                              f'symbol_val:{symbol_prefix},charge_mode:{charge_mode}')
            else:
                abbr_name = fund.get('abbr_name')
                logger.error(f'<Fund({code!r}, {abbr_name!r})> info get failed from DB,please check it.')

            logger.success(f'Update {fund_inst} successfully.')
        print(symbol_set)

    def fee_raito(self, fund_code: str):
        """
        [兴全合润混合(SZ163406)_基金净值_费率_行情走势](https://www.dkhs.com/s/SZ163406/) “交易须知” 子页面
        """
        _url = f'https://www.dkhs.com/api/v1/symbols/FP{fund_code}/fare_ratio/'
        _resp = rget_json(_url)
        return _resp


jcb = DKHS()
if __name__ == '__main__':
    # print(jcb.api())
    print(jcb.read_json_to_db())
