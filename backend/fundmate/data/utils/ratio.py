#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Administrator at 2022/2/24 22:58
import copy
import re
from typing import Dict, List, Optional, Union

import portion

from backend.fundmate import settings
from backend.fundmate.excepts import IsClosedDurationError, ParseError
from backend.fundmate.fund.models import FeeRatio, Fund, PurchaseRule, RedeemRule


class BaseRatio:
    """
    蛋卷基金和韭圈儿共同使用的基础类
    """
    MONTH_SPLIT_STR = '个月'
    DURATION_STR = '个封闭期'
    USD_STR = settings.SupportCurrencyEnum.USD.display
    HKD_STR = settings.SupportCurrencyEnum.HKD.display
    CNY_STR = '元'
    WAN_STR = '万'
    HM_STR = '亿'
    REPLACE_MAP = {
        'w': WAN_STR,
        'wusd': f'{WAN_STR}{USD_STR}',
        'whkd': f'{WAN_STR}{HKD_STR}',
        'usd': USD_STR,
        'cny': CNY_STR,
        'hkd': HKD_STR,
        'hm': HM_STR,
        'd': '天',
        'y': '年',
        'r': '日',
        'm': MONTH_SPLIT_STR,
        'c': DURATION_STR,
    }
    PER_USD = f'{USD_STR}/笔'
    PER_CNY = f'{CNY_STR}/笔'
    PER_HKD = f'{HKD_STR}/笔'

    def re_mark_replace_flag(self, ipt):
        """
        根据结尾获取字段自定义标识
        :param ipt:
        :return:
        """
        for k, v in self.REPLACE_MAP.items():
            if v in ipt:
                if self.REPLACE_MAP.get('wusd') in ipt:
                    return 'wusd'
                elif self.REPLACE_MAP.get('usd') in ipt:
                    return 'usd'
                elif self.REPLACE_MAP.get('whkd') in ipt:
                    return 'whkd'
                elif self.REPLACE_MAP.get('hkd') in ipt:
                    return 'hkd'
                return k

    def suffix_str_to_num(self, suffix_str: str, replace_flag: str = 'w') -> Union[int, float]:
        """
        带后缀的字符串进行截取，最终获取到数字
        >>> br = BaseRatio()
        >>> br.suffix_str_to_num('100万')
        1000000.0
        >>> br.suffix_str_to_num('7.0天')
        7
        >>> br.suffix_str_to_num('1个月')
        30
        >>> br.suffix_str_to_num('2.0年')
        730

        >>> br.suffix_str_to_num('20亿')
        2000000000

        :param replace_flag: 替代标识，可以替代的后缀
        :param suffix_str: 被替换字符
        :return:
        """
        if not replace_flag != 'w':
            replace_flag = self.re_mark_replace_flag(suffix_str)

        replace_str = self.REPLACE_MAP.get(replace_flag)
        try:
            is_excepted_suffix = suffix_str.endswith(replace_str)
        except (AttributeError, TypeError):
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
            if replace_flag in ['w', 'wusd', 'whkd']:
                return float(no_suffix_str) * 10000
            elif replace_flag == 'y':
                # convert year to day
                int_day = int(float(no_suffix_str)) * 365
            elif replace_flag == 'hm':
                # convert year to day
                int_day = int(float(no_suffix_str)) * 100000000
            elif replace_flag == 'm':
                # convert year to day
                int_day = int(float(no_suffix_str)) * 30
            elif replace_flag in ['usd', 'cny', 'd', 'r', 'hkd']:
                int_day = int(float(no_suffix_str))
            elif replace_flag == 'c':
                raise IsClosedDurationError(f'封闭期基金信息: “{suffix_str}” 无法解析信息。')
            else:
                raise ValueError(f'The suffix_str:{suffix_str} can not be parsed.')
            return int_day

        raise ParseError(f'The suffix_str:{suffix_str} is not end with {replace_str}.')

    def make_purchase_info(self, range_str: str) -> Optional[Dict]:
        """
        构建申购信息
        :param range_str:
        :return:
        """
        portion_info = self.parse_portion(range_str)

        if portion_info:
            lower_bounds = portion_info.lower
            upper_bounds = portion_info.upper
            if upper_bounds is portion.inf:
                upper_bounds = None
            return {'start_quota': lower_bounds, 'end_quota': upper_bounds}

    def make_redeem_info(self, range_str: str) -> Optional[Dict]:
        """
        构建赎回信息
        :param range_str:
        :return:
        """
        portion_info = self.parse_portion(range_str)

        if portion_info:
            lower_bounds = portion_info.lower
            upper_bounds = portion_info.upper
            if upper_bounds is portion.inf:
                upper_bounds = None
            return {'start_day': lower_bounds, 'end_day': upper_bounds}

    @staticmethod
    def is_money_suffix(suffix_str: str) -> bool:
        """
        代表金额范围的字段
        :param suffix_str:
        :return:
        """
        money_suffix = ['元', '万']
        for suffix in money_suffix:
            if suffix_str.endswith(suffix):
                return True
        return False

    def purchase_rate(self,
                      purchase_info_list: list,
                      money_key: str = 'money',
                      rate_key: str = 'rate') -> Optional[list]:
        """
        重写解析费率的逻辑
        :param rate_key:
        :param money_key:
        :param purchase_info_list:
        :return:
        """
        purchase_items = list()
        for purchase_info in purchase_info_list:
            info = self.purchase_parser(purchase_info, money_key=money_key, rate_key=rate_key)
            purchase_items.append(info)
        return purchase_items

    def redeem_rate(self, redeem_info_list: list, time_key='time', rate_key='rate') -> Optional[list]:
        """
        费率信息处理
        :param redeem_info_list:
        :param time_key:
        :param rate_key:
        :return:
        """
        redeem_items = list()
        for redeem_info in redeem_info_list:
            info = self.redeem_parser(redeem_info, time_key=time_key, rate_key=rate_key)
            redeem_items.append(info)
        return redeem_items

    def remove_percent(self, x: str) -> float:
        """
        去除字符串的%字符
        >>> fr = BaseRatio()
        >>> fr.remove_percent('1.5%')
        1.5

        :param x:
        :return:
        """
        return float(x.strip('%'))

    def replace_suffix_currency(self, with_suffix_amount: str) -> Optional[str]:
        """
        >>> br = BaseRatio()
        >>> a = '1000元/笔'
        >>> b = '1000美元/笔'
        >>> c = '1000港元/笔'
        >>> br.replace_suffix_currency(a)
        '1000'
        >>> br.replace_suffix_currency(b)
        '1000'
        >>> br.replace_suffix_currency(c)
        '1000'

        :param with_suffix_amount:
        :return:
        """
        if self.PER_USD in with_suffix_amount:
            amount = with_suffix_amount.replace(self.PER_USD, '')
        elif self.PER_HKD in with_suffix_amount:
            amount = with_suffix_amount.replace(self.PER_HKD, '')
        elif self.PER_CNY in with_suffix_amount:
            amount = with_suffix_amount.replace(self.PER_CNY, '')
        else:
            raise ParseError(f'Invalidate amount {with_suffix_amount}.')
        return amount

    def redeem_parser(self, redeem_info: dict, time_key='time', rate_key='rate') -> Optional[Dict]:
        range_str = redeem_info.get(time_key)
        rate = redeem_info.get(rate_key)
        if range_str:
            _portion_info = self.make_redeem_info(range_str)
            rate_info = {
                'rate': self.remove_percent(rate),
            }
            if _portion_info:
                _portion_info.update(rate_info)
            return _portion_info
        else:
            if rate:
                return {'start_day': 0, 'end_day': None, 'rate': self.remove_percent(rate)}

    def purchase_parser(self, purchase_info: dict, money_key: str = 'money', rate_key: str = 'rate') -> Optional[Dict]:
        """
        解析申购信息
        :param rate_key:
        :param money_key:
        :param purchase_info:
        :return:
        """

        def no_discount(rate: float) -> float:
            return rate * 10

        def is_usd_rate(with_suffix_amount: str, rate: float) -> float:
            """
            如果收费是美元，则获取的结果即为真实费率
            :param with_suffix_amount:
            :param rate:
            :return:
            """
            return self.USD_STR in with_suffix_amount

        def is_ukd_rate(with_suffix_amount: str, rate: float) -> float:
            """
            如果收费是美元，则获取的结果即为真实费率
            :param with_suffix_amount:
            :param rate:
            :return:
            """
            return self.HKD_STR in with_suffix_amount

        range_str = purchase_info.get(money_key)
        rate = purchase_info.get(rate_key)
        # 如果有实际的，则保存实际费率
        source_rate = purchase_info.get('source', None)
        if source_rate:
            rate = source_rate
        if range_str:
            portion_info = self.make_purchase_info(range_str)
            upper_bounds = portion_info.get('end_quota')
            if upper_bounds is not None:
                discount_rate = self.remove_percent(rate)
                # # 默认打折
                # is_give_discount = True
                # # 港元和美元的rate即为正式费率，人民币获取的rate是打折后的费率，真实费率需要*10
                # if is_ukd_rate(range_str, discount_rate) or is_usd_rate(range_str, discount_rate):
                #     is_give_discount = False
                #
                # if is_give_discount:
                #     real_rate = no_discount(discount_rate)
                # else:
                #     real_rate = discount_rate

                # 直接保存rate即可
                rate_info = {'rate': discount_rate}
            else:
                # 处理最后一个区间使用固定金额的情况
                last_is_rate = rate.endswith('%')
                if not last_is_rate:
                    amount = self.replace_suffix_currency(rate)
                    rate_info = {'fee_amount': float(amount)}
                else:
                    real_rate = self.remove_percent(rate)
                    # if not is_usd_rate(range_str, discount_rate):
                    #     real_rate = no_discount(discount_rate)
                    # else:
                    #     real_rate = discount_rate
                    rate_info = {'rate': real_rate}

            portion_info.update(rate_info)
            _rule_info = portion_info.copy()

        else:
            # 免费 007471
            start_quota = 0
            amount = 0

            _rule_info = {
                'start_quota': start_quota,
                'end_quota': None,
                'fee_amount': float(amount),
            }
        return _rule_info

    @staticmethod
    def save_fee_info(fund_code: str, fee_info_tb: list, fee_type):
        """
        申购、赎回费率写入数据库
        :param fund_code: 基金编码
        :param fee_info_tb: 费率信息表
        :param fee_type: 费率类型
        :return:
        """
        key = 'redeem_rule_id'  # 字典的key
        if fee_type == settings.FeeTypeEnum.purchase:
            key = 'purchase_rule_id'
            class_name = PurchaseRule
        else:
            class_name = RedeemRule

        fee_type_enums = settings.FeeTypeEnum.values()
        fee_types = [fee_item.value for fee_item in fee_type_enums]

        if fee_type.dk_value not in fee_types:
            raise KeyError(f'The fee_type should be item of in {str(settings.FeeTypeEnum)}')

        _fund_inst = Fund.filter_by_code(fund_code)
        fund_id = _fund_inst.id
        fd_code = _fund_inst.fund_code
        assert fd_code == fund_code

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
                'fund_code': fund_code,
                'fee_amount': fee_amount,
            }
            query_args = {'fund_id': fund_id, 'fund_code': fund_code, key: rule_id, 'fee_type': fee_type}
            FeeRatio.insert_or_update(query_args, do_log_flag=True, **_rate_info)

    def re_split_with_comparison_operators(self, interval_str: str) -> List:
        """
        按照比较符号将字段分割
        :param interval_str:
        :return:
        """
        re_str = self.replace_co_equality(interval_str)
        replaced_ws = self.replace_whitespace(re_str)
        replaced_str = self.replaced_day(replaced_ws)
        reg_items = re.split(r'[<>≤≥\s]', replaced_str)
        # keep sort
        sorted_li = sorted(set(reg_items), key=reg_items.index)
        if '' in sorted_li:
            sorted_li.remove('')
        return sorted_li

    @staticmethod
    def replace_co_equality(raw_str: str) -> str:
        """
        将字符串中的:
        “>=”替换为“≥”
        “<=”替换为“≤”
        '＞'替换为“>”
        '＜'替换为“<”
        正则查找更加方便
        :param raw_str:
        :return:
        """
        to_be_replaced_symbols = ['<=', '>=', '＞', '＜']
        replace_with_symbols = ['≤', '≥', '>', '<']
        symbols_dict = dict(zip(to_be_replaced_symbols, replace_with_symbols))
        for symbol in symbols_dict.keys():
            if symbol in raw_str:
                raw_str = raw_str.replace(symbol, symbols_dict.get(symbol))

        return raw_str

    def replace_whitespace(self, with_whitespace_str: str) -> str:
        return with_whitespace_str.replace(' ', '')

    def replaced_day(self, day_with_suffix: str) -> str:
        """
        将字符串中的‘Y<7 日’替换为“Y<7天”
        >>> br = BaseRatio()
        >>> br.replaced_day('Y<7 日')
        'Y<7天'

        :param day_with_suffix:
        :return:
        """
        return day_with_suffix.replace(' 日', '天')

    def comparison_operators_in_str(self, with_co_str: str) -> Optional[List]:
        """
        找出字段中的比较运算符
        :param with_co_str:
        :return:
        """
        re_str = self.replace_co_equality(with_co_str)
        regex = re.compile(r'[＞>≧≥＜<≤≦]')
        co_lists = regex.findall(re_str)
        if co_lists:
            return co_lists

    def parse_less_single(self, item_key: str, sorted_li: List) -> portion:
        bound = sorted_li[1]
        # 金钱的话，直接转为改为闭区间即可
        upper_bounds = self.suffix_str_to_num(bound)
        is_add_upper = False
        # 时间序列，默认+1
        if not self.is_money_suffix(bound):
            if item_key == 'less_single_c':
                # 时间+1
                is_add_upper = True
        if is_add_upper:
            upper_bounds += 1
        intervals = portion.closedopen(0, upper_bounds)
        return intervals

    def parse_more_single(self, item_key: str, sorted_li: List) -> portion:
        """
        带大于号的边界值数据处理
        :param item_key:
        :param sorted_li:
        :return:
        """
        left_range_str = sorted_li[1]
        # 金钱的话，直接转为改为闭区间即可
        lower_bounds = self.suffix_str_to_num(left_range_str)
        is_add_lower = False
        # 时间序列，默认+1
        if not self.is_money_suffix(left_range_str):
            if item_key == 'more_single_o':
                # 时间+1
                is_add_lower = True
        if is_add_lower:
            lower_bounds += 1
        intervals = portion.closedopen(lower_bounds, portion.inf)
        return intervals

    def parse_more_both_side(self, item_key: str, sorted_li: List, co_lists: List) -> portion:
        # 小的在右边
        upper, _, lower = sorted_li
        lower_bounds = self.suffix_str_to_num(lower)
        upper_bounds = self.suffix_str_to_num(upper)
        if not self.is_money_suffix(lower):
            first_co = co_lists[0]
            is_minus_lower = False
            is_add_upper = False
            is_add_lower = False

            if first_co == '>':
                if item_key == 'more_o':
                    if lower_bounds != 0:
                        is_minus_lower = True

            elif first_co == '≥':
                # 时间+1
                is_add_upper = True
                if item_key == 'more_co':
                    is_add_lower = True

            if is_minus_lower:
                if lower_bounds != 0:
                    lower_bounds -= 1
            if is_add_lower:
                lower_bounds += 1
            if is_add_upper:
                upper_bounds += 1
        intervals = portion.closedopen(lower_bounds, upper_bounds)
        return intervals

    def parse_less_both_side(self, item_key: str, sorted_li: List, co_lists: List) -> Optional[portion.Bound]:
        lower, _, upper = sorted_li
        try:
            lower_bounds = self.suffix_str_to_num(lower)
            upper_bounds = self.suffix_str_to_num(upper)
        except ParseError:
            return None
        if not self.is_money_suffix(lower):
            first_co = co_lists[0]
            is_minus_lower = False
            is_add_upper = False
            if first_co == '<':
                # 时间+1
                is_minus_lower = True
                if item_key == 'less_oc':
                    is_add_upper = True
            elif first_co == '≤':
                # 时间+1
                if item_key == 'less_c':
                    is_add_upper = True
            if is_minus_lower:
                if lower_bounds != 0:
                    lower_bounds -= 1
            if is_add_upper:
                upper_bounds += 1
        intervals = portion.closedopen(lower_bounds, upper_bounds)
        return intervals

    def parse_portion(self, range_str_with_co: str) -> portion:
        """
        根据分割符返回区间
        :param range_str_with_co:
        :return:返回左闭右开(closedopen)的区间（'[1,5)'）
        """
        co_lists = self.comparison_operators_in_str(range_str_with_co)
        sorted_li = self.re_split_with_comparison_operators(range_str_with_co)
        '''
        o:open
        c:closed
        oc:openclosed
        co:closedopen
        '''
        comp_items = {
            'less_o': ['<', '<'],
            'less_c': ['≤', '≤'],
            'less_oc': ['<', '≤'],
            'less_co': ['≤', '<'],
            'less_single_c': ['≤'],
            'less_single_o': ['<'],
            'more_o': ['>', '>'],
            'more_c': ['≥', '≥'],
            'more_oc': ['>', '≥'],
            'more_co': ['≥', '>'],
            'more_single_c': ['≥'],
            'more_single_o': ['>'],
        }

        val_lists = list(comp_items.values())
        if co_lists in val_lists:
            item_index = val_lists.index(co_lists)
            item_key = list(comp_items.keys())[item_index]
            if item_key in ['less_single_c', 'less_single_o']:
                try:
                    assert len(sorted_li) == 2
                except AssertionError:
                    raise ParseError(f'费率区间信息：{range_str_with_co} 无法处理！')
                interval_item = self.parse_less_single(item_key, sorted_li)
            elif item_key in ['more_single_c', 'more_single_o']:
                assert len(sorted_li) == 2
                interval_item = self.parse_more_single(item_key, sorted_li)
            elif item_key in ['less_o', 'less_c', 'less_oc', 'less_co']:
                # 两边都有边界值
                assert len(sorted_li) == 3
                interval_item = self.parse_less_both_side(item_key, sorted_li, co_lists)
            elif item_key in ['more_o', 'more_c', 'more_oc', 'more_co']:
                # 两边都有边界值
                assert len(sorted_li) == 3
                interval_item = self.parse_more_both_side(item_key, sorted_li, co_lists)
            else:
                raise ParseError(f'字段：{range_str_with_co}获取到的区间分割符为：{co_lists}')
        else:
            raise ParseError(f'无法解析字段：{range_str_with_co}，{co_lists} 不在预测字符集{val_lists}中。')

        return interval_item


def all_comparison_operators():
    less_intervals = ['＜', '<']
    right_intervals = less_intervals + ['<=', '≤', '≦']
    # 大于符号集
    more_intervals = ['＞', '>']
    left_intervals = more_intervals + ['≧', '≥', '>=']
    return ''.join(left_intervals + right_intervals)


if __name__ == '__main__':
    br = BaseRatio()
    result = br.parse_portion('7天 ≤ 持有期限 ≤ 30天')
    print(result)
    assert result == portion.closedopen(7, 31)
