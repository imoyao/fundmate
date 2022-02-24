#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Administrator at 2022/2/24 22:58
import copy
import re
from typing import List, Union

from backend.fundmate import settings
from backend.fundmate.excepts import ParseError, UnpackError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import FeeRatio, Fund, PurchaseRule, RedeemRule


class BaseRatio:
    """
    蛋卷基金和韭圈儿共同使用的基础类
    """
    MONTH_SPLIT_STR = '个月'
    REPLACE_MAP = {
        'w': '万',
        'd': '天',
        'y': '年',
        'm': MONTH_SPLIT_STR,
    }

    def re_mark_replace_flag(self, ipt):
        """
        对于天的处理，需要根据输入重新处理
        :param ipt:
        :return:
        """
        for k, v in self.REPLACE_MAP.items():
            if v in ipt:
                return k

    def suffix_str_to_num(self, suffix_str: str, replace_flag: str = 'w') -> Union[int, float]:
        """
        带后缀的字符串进行截取，最终获取到数字
        >>> self.suffix_str_to_num('100万')
        1000000
        >>> self.suffix_str_to_num('7.0天')
        7
        >>> self.suffix_str_to_num('1个月')
        30
        >>> self.suffix_str_to_num('2.0年')
        730

        :param replace_flag: 替代标识，可以替代的后缀
        :param suffix_str: 被替换字符
        :return:
        """
        if not replace_flag != 'w':
            replace_flag = self.re_mark_replace_flag(suffix_str)

        replace_str = self.REPLACE_MAP.get(replace_flag)
        try:
            is_excepted_suffix = suffix_str.endswith(replace_str)
        except AttributeError:
            is_excepted_suffix = False

        if is_excepted_suffix:
            '''
            # FIXME：py3.9: see also: https://docs.python.org/3/library/stdtypes.html#str.removesuffix
            ```
            >>> 'MiscTests'.removesuffix('Tests')
            'Misc'
            >>> 'TmpDirMixin'.removesuffix('Tests')
            'TmpDirMixin'
            ```
            '''
            no_suffix_str = suffix_str.replace(replace_str, '')
            if replace_flag == 'w':
                return float(no_suffix_str) * 10000
            elif replace_flag == 'd':
                int_day = 7
                try:
                    int_day = int(float(no_suffix_str))
                except ValueError:
                    if no_suffix_str.startswith('='):
                        # fixme:000005,需要特殊处理（(0,6]）
                        no_suffix_str = no_suffix_str.replace('=', '')
                        int_day = int(float(no_suffix_str)) + 1
            elif replace_flag == 'y':
                # convert year to day
                int_day = int(float(no_suffix_str)) * 365
            elif replace_flag == 'm':
                # convert year to day
                int_day = int(float(no_suffix_str)) * 30
            else:
                raise ValueError(f'The suffix_str:{suffix_str} can not be parsed.')
            return int_day

        raise ValueError(f'The suffix_str:{suffix_str} is not end with {replace_str}.')

    def parse_first(self, range_str: str) -> float:
        """
        买入金额<100.0万  -> 1000000
        :param range_str:
        :return:
        """
        split_signal = '<'
        if split_signal in range_str:
            data_li = range_str.split(split_signal)
            data_str = data_li[-1]
            float_wan = self.suffix_str_to_num(data_str)
            return float_wan
        raise ValueError(f"Don't have {split_signal} in the range_str:{range_str}.")

    def first_quota(self, first_info: dict) -> dict:
        """
        有始有终 最小优惠额度
        :param first_info:
        :return:
        """
        range_str = first_info.get('name')
        rate = first_info.get('value')
        end_quota = self.parse_first(range_str)
        _rule_info = {
            'start_quota': 0,
            'end_quota': end_quota,
            'rate': float(rate),
        }
        return _rule_info

    def _parse_both_limit(self, qt_name: str, p_type: str = 'q') -> List[float]:
        """
        对于一个区间字符串（详见示例），使用正则提取前后区间的数字并返回
        # 一月按照30天计算

        Examples:
        ```
        >>> self._parse_both_limit('100.0万<=买入金额<500.0万')
        [1000000.0,5000000.0]
        >>> self._parse_both_limit("0.0天<持有期限<30.0天")
        [0,30]
        >>> self._parse_both_limit("365.0天<=持有期限<2.0年")
        [365,730]
        >>> self._parse_both_limit("2.0年<=持有期限<3.0年")
        [730,1095]
        >>> self._parse_both_limit('7天 ≤ 持有期限 < 1个月')
        [7,30]
        >>> self._parse_both_limit('7天 ≤ 持有期限 < 30天')
        [7,30]

        ```
        :param qt_name: 被匹配的字符串，从中匹配数字
        :param p_type: 匹配规则，可以是额度（q）或者天数（d）
        :return:
        """
        except_types = ['q', 'd']
        if p_type not in except_types:
            raise KeyError(f'The p_type: {p_type} should in {except_types},while `q` for quota,`d` for day.')

        if qt_name.endswith('年'):
            if p_type == 'd':
                day_year_match_exp = r'(\d+\.?\d*)天.+?(\d+\.?\d*)年'
                regex = re.compile(day_year_match_exp)
                dy_reg_mat = regex.findall(qt_name)
                if dy_reg_mat:
                    start_day, end_year = dy_reg_mat[0]
                    no_suffix_li = [int(float(start_day)), int(float(end_year)) * 365]
                    return no_suffix_li
                else:
                    # 2.0年<=持有期限<3.0年
                    yy_match_exp = r'(\d+\.?\d*)年.+?(\d+\.?\d*)年'
                    regex = re.compile(yy_match_exp)
                    dy_reg_mat = regex.findall(qt_name)
                    if dy_reg_mat:
                        ret = dy_reg_mat[0]
                        no_suffix_li = [int(float(year)) * 365 for year in ret]
                        return no_suffix_li
                    else:
                        # 1个月<=持有期限<1年
                        mon_match_exp = fr'(\d+\.?\d*){self.MONTH_SPLIT_STR}.+?(\d+\.?\d*)年'
                        regex = re.compile(mon_match_exp)
                        dm_reg_mat = regex.findall(qt_name)
                        if dm_reg_mat:
                            m, y = dm_reg_mat[0]
                            no_suffix_li = [int(float(m) * 30), int(float(y)) * 365]
                            return no_suffix_li

        elif qt_name.endswith(self.MONTH_SPLIT_STR):
            if p_type == 'd':
                day_mon_match_exp = fr'(\d+\.?\d*)天.+?(\d+\.?\d*){self.MONTH_SPLIT_STR}'
                regex = re.compile(day_mon_match_exp)
                dy_reg_mat = regex.findall(qt_name)
                if dy_reg_mat:
                    start_day, end_month = dy_reg_mat[0]
                    no_suffix_li = [int(float(start_day)), int(float(end_month)) * 30]
                    return no_suffix_li
                else:
                    # 1个月<=持有期限<3个月
                    mon_match_exp = fr'(\d+\.?\d*){self.MONTH_SPLIT_STR}.+?(\d+\.?\d*){self.MONTH_SPLIT_STR}'
                    regex = re.compile(mon_match_exp)
                    dm_reg_mat = regex.findall(qt_name)
                    if dm_reg_mat:
                        ret = dm_reg_mat[0]
                        no_suffix_li = [int(float(mon)) * 30 for mon in ret]
                        return no_suffix_li

        if p_type == 'q':
            match_exp = r'(\d+.\d*)万'
        else:
            match_exp = r'(\d*.\d*)天'

        regex = re.compile(match_exp)
        reg_mat = regex.findall(qt_name)
        if reg_mat:
            if p_type == 'q':
                # 匹配出来是万，需要转换为元
                no_suffix_li = [float(num) * 10000 for num in reg_mat]
            else:
                no_suffix_li = [int(float(num)) for num in reg_mat]
            return no_suffix_li
        raise ValueError(f"The given str: {qt_name} doesn't match regexp.")

    def parse_middle(self, mid_list):
        """
        [{
                'name': '100.0万<=买入金额<500.0万',
                'value': '1.2'
            }, {
                'name': '500.0万<=买入金额<1000.0万',
                'value': '0.8'
            }]
        :return:
        """
        mid_qta = []
        for item in mid_list:
            name = item.get('name')
            rate = item.get('value')
            float_wan_li = self._parse_both_limit(name)
            s_qt, e_qt = float_wan_li
            qt_info = {
                'start_quota': s_qt,
                'end_quota': e_qt,
                'rate': float(rate),
            }
            mid_qta.append(qt_info)
        return mid_qta

    def parse_last(self, range_str: str, replace_flag='w', split_signal: str = '<=') -> Union[float, int]:
        """
        对末尾数据进行解析，取边界值
        Examples:
        ```
        >>> parse_last('1000.0万<=买入金额')
        10000000.0
        >>> parse_last('180.0天<=持有期限')
        180
        >>> parse_last('购买金额 ≥ 1000万')
        10000000.0
        >>> parse_last('持有期限 ≥ 1个月',replace_flag='m')
        30
        ```
        :param range_str:
        :param replace_flag:
        :param split_signal:分割符
        :return:
        """
        if split_signal in range_str:
            if split_signal == '<=':
                data_li = range_str.split(split_signal)
                data_str = data_li[0]
                no_suffix_num = self.suffix_str_to_num(data_str, replace_flag=replace_flag)
                return no_suffix_num
            else:
                data_li = range_str.split(split_signal)
                data_str = data_li[1]
                no_suffix_num = self.suffix_str_to_num(data_str, replace_flag=replace_flag)
                return no_suffix_num
        else:
            if '<' in range_str:
                # 270.0天<持有期限
                no_suffix_num = self.parse_last(range_str, replace_flag=replace_flag, split_signal='<')
                return no_suffix_num

            raise ValueError(f"Don't have {split_signal} in the range_str:{range_str}.")

    def last_quota(self, last_info: dict) -> dict:
        """
        结束时只有开始值，此时按照固定额收费
        """
        range_str = last_info.get('name')
        amount = last_info.get('value')
        start_quota = self.parse_last(range_str)

        _rule_info = {
            'start_quota': start_quota,
            'end_quota': None,
            'fee_amount': float(amount),
        }
        return _rule_info

    def last_level(self, last_info: dict, split_signal: str = '<='):
        """
        最低档赎回费信息
        :param split_signal:
        :param last_info:
        :return:
        """
        range_str = last_info.get('name')
        rate = last_info.get('value')
        start_day = self.parse_last(range_str, replace_flag='d', split_signal=split_signal)
        _rule_info = {
            'start_day': start_day,
            'end_day': None,
            'rate': float(rate),
        }
        return _rule_info

    def declare_rate(self, declare_rate_table: list) -> Union[list, None]:
        if len(declare_rate_table) >= 2:
            first, *mid, last = declare_rate_table
            f_qt = self.first_quota(first)
            mid_qt = list()
            l_qt = list()
            if mid:
                mid_qt = self.parse_middle(mid)
            if last:
                l_qt = self.last_quota(last)
            qt_list = [f_qt]
            if mid_qt:
                qt_list.extend(mid_qt)
            if l_qt:
                qt_list.append(l_qt)
        elif len(declare_rate_table) == 1:
            # {'name': '0.0万<买入金额', 'value': '0.0'}
            # 费率与购入金额无关（固定费率）
            last = declare_rate_table[0]
            l_qt = self.last_quota(last)
            qt_list = [l_qt]
        else:
            raise UnpackError(f'declare_rate_table:{declare_rate_table}')
        return qt_list

    def withdraw_rate(self, withdraw_rate_table: list):
        """
        将数据：
        ```
        # 注意此数据中 raw data 本身有重复数据（001778）
        [{
            "name": "0.0天<持有期限<7.0天",
            "value": "1.5"
        }, {
            "name": "7.0天<=持有期限<30.0天",
            "value": "0.5"
        }, {
            "name": "30.0天<=持有期限<180.0天",
            "value": "0.1"
        }, {
            "name": "180.0天<=持有期限",
            "value": "0.0"
            "value": "0.0"
        }]
        ```
        :return:
        """
        if len(withdraw_rate_table) >= 2:
            *no_last, last = withdraw_rate_table
            try:
                qt_list = self._parse_day_have_both(no_last)  # 解析阈值
            except ParseError:
                qt_list = list()
            if last:
                l_qt = self.last_level(last)
                qt_list.append(l_qt)
        elif len(withdraw_rate_table) == 1:  # 只有一个，即免费
            free_item = withdraw_rate_table[0]
            l_qt = self.last_level(free_item)
            qt_list = [l_qt]
        else:
            raise UnpackError(f'withdraw_rate_table:{withdraw_rate_table}')
        return qt_list

    @staticmethod
    def save_fee_info(fund_code: str, fee_info_tb: list, fee_type: int):
        """
        申购、赎回费率写入数据库
        FIXME: duplicated with transfer_rule
        :param fund_code: 基金编码
        :param fee_info_tb: 费率信息表
        :param fee_type: 费率类型
        :return:
        """
        key = 'redeem_rule_id'  # 字典的key
        if fee_type == 2:
            key = 'purchase_rule_id'
            class_name = PurchaseRule
        else:
            class_name = RedeemRule
        fee_types = [item.dk_value for item in settings.FeeTypeEnum]
        if fee_type not in fee_types:
            raise KeyError(f'The fee_type should be Integer in {fee_types}')

        _fund_inst = Fund.filter_by_code(fund_code)
        fund_id = _fund_inst.id

        for rule_info in fee_info_tb:
            # 要么按照费率收费要么按照金额收费，至少有一个
            cp_rf = copy.deepcopy(rule_info)
            if 'rate' in cp_rf:
                fare_ratio = cp_rf.pop('rate')
                rate = float(fare_ratio) if not isinstance(fare_ratio, float) else fare_ratio
                fee_amount = None
            else:
                rate = None
                fee_amount = cp_rf.pop('fee_amount')
            rule_inst = class_name.insert_or_update(cp_rf, do_log_flag=True, **cp_rf)
            rule_id = rule_inst.id

            _rate_info = {
                key: rule_id,
                'fund_id': fund_id,  # **注意**：在创建时，必须有fund_id
                'fee_type': fee_type,
                'rate': rate,
                'fee_amount': fee_amount,
            }
            query_args = {'fund_id': fund_id, key: rule_id, 'fee_type': fee_type}
            FeeRatio.insert_or_update(query_args, do_log_flag=True, **_rate_info)

    def _parse_day_have_both(self, mid_info: Union[list, dict]) -> list:
        """"
        两边数值，中间分隔符的情况
        Examples:

        ## 第一种情况
        >>> [{
            "name": "7.0天<=持有期限<30.0天",
            "value": "0.5"
        }, {
            "name": "30.0天<=持有期限<180.0天",
            "value": "0.1"
        }]

        ## 第二种情况

        >>> [{
            "name": "0.0天<持有期限<7.0天",
            "value": "1.5"
        }]

        """

        def parse_item(mid_info_: dict) -> dict:
            """
            解析收费规则
            :param mid_info_:
            :return:
            """
            range_str = mid_info_.get('name')
            rate = mid_info_.get('value')
            float_day_li = self._parse_both_limit(range_str, p_type='d')
            try:
                s_qt, e_qt = float_day_li
            except ValueError as e:
                err_msg = f'Error: {e} to unpack {float_day_li},raw str is {range_str}'
                # 不够两个无法处理
                logger.error(err_msg)
                raise ParseError(err_msg)
            '''
            hack：特殊数据处理
            convert:
            {'start_day': 6, 'end_day': 91, 'rate': 0.3},
              {'start_day': 90, 'end_day': 181, 'rate': 0.2},
              {'start_day': 180, 'end_day': 271, 'rate': 0.1},
            to:
              {'start_day': 7, 'end_day': 90, 'rate': 0.3},
              {'start_day': 90, 'end_day': 180, 'rate': 0.2},
              {'start_day': 180, 'end_day': 270, 'rate': 0.1},
            '''
            if e_qt:
                if str(e_qt).endswith('1'):
                    e_qt -= 1
                    if s_qt == 6:
                        s_qt = 7
                _results = {
                    'start_day': s_qt,
                    'end_day': e_qt,
                    'rate': float(rate),
                }
                return _results

        results = []
        if isinstance(mid_info, list):
            for item in mid_info:
                qt_info = parse_item(item)
                results.append(qt_info)
        else:
            results = parse_item(mid_info)
        return results


def filter_comparison_operators(interval_str):
    ret = re.split(r'[>=<≤≥\s]', interval_str)
    sorted_li = sorted(set(ret), key=ret.index)
    if '' in sorted_li:
        sorted_li.remove('')
    return sorted_li


if __name__ == '__main__':

    test_list = [
        '7天 ≤ 持有期限 < 1个月', '100.0万<=买入金额<500.0万', '7天 ≤ 持有期限 < 1个月', '7天 ≤ 持有期限 < 30天', '1个月 ≤ 持有期限 < 1年',
        '1个月<=持有期限<3个月', '1年 ≤ 持有期限 < 2年', '持有期限 ≥ 1个月', '持有期限 >= 1个月', '持有期限 > 1个月', '持有期限 < 7天'
    ]
    for item in test_list:
        ret = filter_comparison_operators(item)
        print(ret)
